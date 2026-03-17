from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.agents.insurance_agent import (
    InsuranceComparisonResponse,
    InsuranceLLMClient,
    LLMConfig,
    LLMInvocationError,
    LLMModel,
    LLMProvider,
    PdfExtractionError,
    extract_pdf_text,
    get_insurance_prompts,
    run_insurance_comparison,
)
from app.core.config import get_settings

router = APIRouter(prefix="/insurance", tags=["insurance"])

OPENAI_MAX_FILE_BYTES = 50 * 1024 * 1024
ANTHROPIC_MAX_FILE_BYTES = 32 * 1024 * 1024
ANTHROPIC_MAX_PAGES = 100

COMPARE_DESCRIPTION = """
Upload two insurance PDFs and compare them with a LangGraph workflow.

Testing with your sample files:
- `current_term_pdf`: `1003csr117012024121732_cgl_pt00.pdf`
- `prior_term_pdf`: `1003csr117012024121732_cgl_ct00.pdf`
- `provider`: `anthropic` or `openai`
- `model`: optional override such as `claude-haiku-4-5` or `gpt-5`

The API sends uploaded PDFs directly to the model for extraction.
If Anthropic rejects a very large PDF due to context limits, the server automatically falls back to page-chunked extraction and merges those partial results before the final compare step.
""".strip()

COMPARE_RESPONSE_EXAMPLE = {
    "provider": "anthropic",
    "model": "claude-haiku-4-5",
    "current_document": {
        "filename": "1003csr117012024121732_cgl_pt00.pdf",
        "content_type": "application/pdf",
        "page_count": 12,
    },
    "prior_document": {
        "filename": "1003csr117012024121732_cgl_ct00.pdf",
        "content_type": "application/pdf",
        "page_count": 11,
    },
    "current_extraction": {
        "prompt": "Extract the required fields with page numbers.",
        "response": '{"policy_numbers":[{"value":"CPP1234567-89","page":2}],"policy_periods":[{"from":"01/01/2025","to":"01/01/2026","page":2}],"insurance_companies":[{"value":"Sample Insurance Company","page":1}],"named_insured_and_mailing_addresses":[{"named_insured":"Acme LLC","mailing_address":"123 Main St, Dallas, TX 75001","page":3}],"notes":[]}',
        "structured_output": {
            "policy_numbers": [{"value": "CPP1234567-89", "page": 2}],
            "policy_periods": [{"from": "01/01/2025", "to": "01/01/2026", "page": 2}],
            "insurance_companies": [{"value": "Sample Insurance Company", "page": 1}],
            "named_insured_and_mailing_addresses": [
                {
                    "named_insured": "Acme LLC",
                    "mailing_address": "123 Main St, Dallas, TX 75001",
                    "page": 3,
                }
            ],
            "notes": [],
        },
    },
    "prior_extraction": {
        "prompt": "Extract the required fields with page numbers.",
        "response": '{"policy_numbers":[{"value":"CPP1234567-88","page":2}],"policy_periods":[{"from":"01/01/2024","to":"01/01/2025","page":2}],"insurance_companies":[{"value":"Sample Insurance Company","page":1}],"named_insured_and_mailing_addresses":[{"named_insured":"Acme LLC","mailing_address":"123 Main St, Dallas, TX 75001","page":3}],"notes":[]}',
        "structured_output": {
            "policy_numbers": [{"value": "CPP1234567-88", "page": 2}],
            "policy_periods": [{"from": "01/01/2024", "to": "01/01/2025", "page": 2}],
            "insurance_companies": [{"value": "Sample Insurance Company", "page": 1}],
            "named_insured_and_mailing_addresses": [
                {
                    "named_insured": "Acme LLC",
                    "mailing_address": "123 Main St, Dallas, TX 75001",
                    "page": 3,
                }
            ],
            "notes": [],
        },
    },
    "merged_output": {
        "prompt": "Merge both extraction JSON payloads.",
        "response": '{"current_term":{"policy_numbers":[{"value":"CPP1234567-89","page":2}],"policy_periods":[{"from":"01/01/2025","to":"01/01/2026","page":2}],"insurance_companies":[{"value":"Sample Insurance Company","page":1}],"named_insured_and_mailing_addresses":[{"named_insured":"Acme LLC","mailing_address":"123 Main St, Dallas, TX 75001","page":3}],"notes":[]},"prior_term":{"policy_numbers":[{"value":"CPP1234567-88","page":2}],"policy_periods":[{"from":"01/01/2024","to":"01/01/2025","page":2}],"insurance_companies":[{"value":"Sample Insurance Company","page":1}],"named_insured_and_mailing_addresses":[{"named_insured":"Acme LLC","mailing_address":"123 Main St, Dallas, TX 75001","page":3}],"notes":[]},"comparison_summary":["Policy number changed between terms.","Premium TP1 changed from $59,649.00 to $56,818.00"],"field_level_changes":[{"field":"policy_numbers[0]","current_value":"CPP1234567-89","prior_value":"CPP1234567-88","current_page":2,"prior_page":2,"change_type":"changed"},{"field":"Premium(TP1)","current_value":"$56,818.00","prior_value":"$59,649.00","current_page":12,"prior_page":12,"change_type":"changed"}]}',
        "structured_output": {
            "current_term": {
                "policy_numbers": [{"value": "CPP1234567-89", "page": 2}],
                "policy_periods": [{"from": "01/01/2025", "to": "01/01/2026", "page": 2}],
                "insurance_companies": [{"value": "Sample Insurance Company", "page": 1}],
                "named_insured_and_mailing_addresses": [
                    {
                        "named_insured": "Acme LLC",
                        "mailing_address": "123 Main St, Dallas, TX 75001",
                        "page": 3,
                    }
                ],
                "notes": [],
            },
            "prior_term": {
                "policy_numbers": [{"value": "CPP1234567-88", "page": 2}],
                "policy_periods": [{"from": "01/01/2024", "to": "01/01/2025", "page": 2}],
                "insurance_companies": [{"value": "Sample Insurance Company", "page": 1}],
                "named_insured_and_mailing_addresses": [
                    {
                        "named_insured": "Acme LLC",
                        "mailing_address": "123 Main St, Dallas, TX 75001",
                        "page": 3,
                    }
                ],
                "notes": [],
            },
            "comparison_summary": [
                "Policy number changed between terms.",
                "Premium TP1 changed from $59,649.00 to $56,818.00",
            ],
            "field_level_changes": [
                {
                    "field": "policy_numbers[0]",
                    "current_value": "CPP1234567-89",
                    "prior_value": "CPP1234567-88",
                    "current_page": 2,
                    "prior_page": 2,
                    "change_type": "changed",
                },
                {
                    "field": "Premium(TP1)",
                    "current_value": "$56,818.00",
                    "prior_value": "$59,649.00",
                    "current_page": 12,
                    "prior_page": 12,
                    "change_type": "changed",
                }
            ],
        },
    },
}


@router.post(
    "/compare",
    response_model=InsuranceComparisonResponse,
    summary="Compare current and prior insurance PDFs",
    description=COMPARE_DESCRIPTION,
    responses={
        200: {
            "description": "Structured extraction and merged comparison with page numbers.",
            "content": {
                "application/json": {
                    "example": COMPARE_RESPONSE_EXAMPLE,
                }
            },
        },
        400: {
            "description": "Bad input such as a non-PDF upload, unreadable PDF, or invalid model response.",
            "content": {
                "application/json": {
                    "example": {"detail": "1003csr117012024121732_cgl_pt00.pdf must be a PDF."}
                }
            },
        },
        502: {
            "description": "Upstream model/provider failure.",
            "content": {
                "application/json": {
                    "example": {"detail": "Upstream model request failed."}
                }
            },
        },
    },
)
async def compare_insurance_documents(
    current_term_pdf: UploadFile = File(
        ...,
        description="Current term insurance PDF. Example: 1003csr117012024121732_cgl_pt00.pdf",
    ),
    prior_term_pdf: UploadFile = File(
        ...,
        description="Prior term insurance PDF. Example: 1003csr117012024121732_cgl_ct00.pdf",
    ),
    provider: LLMProvider = Form(default=LLMProvider.OPENAI, description="LLM provider: `openai` or `anthropic`."),
    model: LLMModel | None = Form(
        default=None,
        description="Optional model override. Example: `claude-haiku-4-5` or `gpt-5`.",
    ),
    temperature: float = Form(default=0.0, description="Sampling temperature, usually `0.0` for extraction."),
):
    _ensure_pdf(current_term_pdf)
    _ensure_pdf(prior_term_pdf)

    current_bytes = await current_term_pdf.read()
    prior_bytes = await prior_term_pdf.read()

    _validate_file_sizes(
        provider=provider,
        current_filename=current_term_pdf.filename or "current-term.pdf",
        current_bytes=current_bytes,
        prior_filename=prior_term_pdf.filename or "prior-term.pdf",
        prior_bytes=prior_bytes,
    )

    try:
        current_document, prior_document = _build_documents(
            current_bytes=current_bytes,
            current_upload=current_term_pdf,
            prior_bytes=prior_bytes,
            prior_upload=prior_term_pdf,
        )
    except PdfExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _validate_document_limits(
        provider=provider,
        current_document=current_document,
        prior_document=prior_document,
    )

    llm_client = InsuranceLLMClient(get_settings())
    llm_config = LLMConfig(provider=provider, model=model, temperature=temperature)

    try:
        result = await run_insurance_comparison(
            current_document=current_document,
            prior_document=prior_document,
            llm_config=llm_config,
            llm_client=llm_client,
        )
    except LLMInvocationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected upstream/provider failures
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        await llm_client.close()

    return result


@router.get(
    "/prompts",
    summary="Get default insurance prompts",
    description="Returns the default extraction and merge prompts used by the insurance comparison flow.",
)
async def get_default_prompts():
    return get_insurance_prompts()


def _ensure_pdf(upload: UploadFile) -> None:
    filename = (upload.filename or "").lower()
    if filename.endswith(".pdf"):
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{upload.filename or 'Uploaded file'} must be a PDF.",
    )


def _build_documents(*, current_bytes: bytes, current_upload: UploadFile, prior_bytes: bytes, prior_upload: UploadFile):
    current_document = extract_pdf_text(
        current_bytes,
        filename=current_upload.filename or "current-term.pdf",
        content_type=current_upload.content_type,
    )
    prior_document = extract_pdf_text(
        prior_bytes,
        filename=prior_upload.filename or "prior-term.pdf",
        content_type=prior_upload.content_type,
    )
    return current_document, prior_document


def _validate_file_sizes(*, provider: LLMProvider, current_filename: str, current_bytes: bytes, prior_filename: str, prior_bytes: bytes) -> None:
    if provider is LLMProvider.ANTHROPIC:
        max_bytes = ANTHROPIC_MAX_FILE_BYTES
        provider_label = "Anthropic"
    else:
        max_bytes = OPENAI_MAX_FILE_BYTES
        provider_label = "OpenAI"

    for filename, content in ((current_filename, current_bytes), (prior_filename, prior_bytes)):
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{filename} exceeds the {provider_label} file size limit of {max_bytes // (1024 * 1024)} MB.",
            )


def _validate_document_limits(*, provider: LLMProvider, current_document, prior_document) -> None:
    if provider is not LLMProvider.ANTHROPIC:
        return

    for document in (current_document, prior_document):
        if document.page_count > ANTHROPIC_MAX_PAGES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{document.filename} exceeds the Anthropic page limit of {ANTHROPIC_MAX_PAGES} pages.",
            )
