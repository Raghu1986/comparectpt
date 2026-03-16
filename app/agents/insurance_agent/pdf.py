from io import BytesIO

from pypdf import PdfReader

from app.agents.insurance_agent.models import InsuranceDocumentInput, PageText


class PdfExtractionError(ValueError):
    pass


def load_pdf_document(content: bytes, filename: str, content_type: str | None = None) -> InsuranceDocumentInput:
    if not content:
        raise PdfExtractionError(f"{filename} is empty.")

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:  # pragma: no cover - defensive for malformed PDFs
        raise PdfExtractionError(f"Unable to read PDF {filename}: {exc}") from exc

    page_count = len(reader.pages)
    if not page_count:
        raise PdfExtractionError(f"{filename} does not contain any pages.")

    return InsuranceDocumentInput(
        filename=filename,
        content_type=content_type,
        content=content,
        page_count=page_count,
    )


def extract_pdf_text(content: bytes, filename: str, content_type: str | None = None) -> InsuranceDocumentInput:
    document = load_pdf_document(content, filename=filename, content_type=content_type)
    reader = PdfReader(BytesIO(content))
    document.pages = [
        PageText(page_number=index, text=(page.extract_text() or ""))
        for index, page in enumerate(reader.pages, start=1)
    ]
    return document
