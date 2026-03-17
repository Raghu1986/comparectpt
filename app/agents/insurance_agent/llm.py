import json
import re
from collections.abc import Callable
from base64 import b64encode
from typing import Any

from anthropic import APIError as AnthropicAPIError
from anthropic import AsyncAnthropic
from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI, BadRequestError
from pydantic import ValidationError

from app.agents.insurance_agent.models import (
    InsuranceDocumentInput,
    InsuranceExtractionResult,
    InsuranceMergeResult,
    LLMConfig,
    LLMModel,
    LLMProvider,
    PremiumExtractionResult,
    PremiumMergeResult,
)
from app.core.config import Settings


DEFAULT_MODEL_BY_PROVIDER = {
    LLMProvider.OPENAI: LLMModel.GPT_5,
    LLMProvider.ANTHROPIC: LLMModel.CLAUDE_HAIKU_4_5,
}

ANTHROPIC_MAX_DOCUMENT_CHARS = 120000
OPENAI_TEMP_FILE_TTL_SECONDS = 3600


class LLMInvocationError(RuntimeError):
    pass


class InsuranceLLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        timeout = settings.LLM_REQUEST_TIMEOUT_SECONDS
        self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout) if settings.OPENAI_API_KEY else None
        self._anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=timeout) if settings.ANTHROPIC_API_KEY else None

    async def close(self) -> None:
        if self._anthropic_client:
            await self._anthropic_client.close()
        if self._openai_client:
            await self._openai_client.close()

    async def generate_json(self, *, prompt: str, document: InsuranceDocumentInput | str, config: LLMConfig) -> str:
        provider = config.provider
        model = self.resolve_model(config)

        if provider == LLMProvider.OPENAI:
            return await self._generate_with_openai(model=model, prompt=prompt, document=document, temperature=config.temperature)
        if provider == LLMProvider.ANTHROPIC:
            return await self._generate_with_anthropic(
                model=model,
                prompt=prompt,
                document=document,
                temperature=config.temperature,
                chunk_parser=self.parse_extraction,
                chunk_merger=self._merge_extraction_results,
            )

        raise LLMInvocationError(f"Unsupported provider: {config.provider.value}")

    async def generate_premium_json(self, *, prompt: str, document: InsuranceDocumentInput | str, config: LLMConfig) -> str:
        provider = config.provider
        model = self.resolve_model(config)

        if provider == LLMProvider.OPENAI:
            return await self._generate_with_openai(model=model, prompt=prompt, document=document, temperature=config.temperature)
        if provider == LLMProvider.ANTHROPIC:
            return await self._generate_with_anthropic(
                model=model,
                prompt=prompt,
                document=document,
                temperature=config.temperature,
                chunk_parser=self.parse_premium_extraction,
                chunk_merger=self._merge_premium_extraction_results,
            )

        raise LLMInvocationError(f"Unsupported provider: {config.provider.value}")

    def parse_extraction(self, response_text: str) -> InsuranceExtractionResult:
        try:
            return InsuranceExtractionResult.model_validate(self._load_json(response_text))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise LLMInvocationError(f"Extraction response was not valid page-aware JSON: {exc}") from exc

    def parse_merge(self, response_text: str) -> InsuranceMergeResult:
        try:
            result = InsuranceMergeResult.model_validate(self._load_json(response_text))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise LLMInvocationError(f"Merge response was not valid page-aware JSON: {exc}") from exc
        return self._normalize_merge_result(result)

    def parse_premium_extraction(self, response_text: str) -> PremiumExtractionResult:
        try:
            payload = self._normalize_premium_extraction_payload(self._load_json(response_text))
            return PremiumExtractionResult.model_validate(payload)
        except (ValidationError, json.JSONDecodeError, TypeError) as exc:
            raise LLMInvocationError(f"Premium extraction response was not valid JSON: {exc}") from exc

    def parse_premium_merge(self, response_text: str) -> PremiumMergeResult:
        try:
            result = PremiumMergeResult.model_validate(self._load_json(response_text))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise LLMInvocationError(f"Premium merge response was not valid JSON: {exc}") from exc
        return result

    def resolve_model(self, config: LLMConfig) -> LLMModel:
        return config.model or DEFAULT_MODEL_BY_PROVIDER[config.provider]

    async def _generate_with_openai(self, *, model: LLMModel, prompt: str, document: InsuranceDocumentInput | str, temperature: float) -> str:
        if not self._openai_client:
            raise LLMInvocationError("OPENAI_API_KEY is not configured.")

        request_args = {
            "model": model.value,
            "instructions": prompt,
            "input": await self._build_openai_input(document),
        }
        if self._openai_supports_temperature(model):
            request_args["temperature"] = temperature

        try:
            response = await self._openai_client.responses.create(**request_args)
        except BadRequestError as exc:
            raise LLMInvocationError(self._format_provider_error(exc)) from exc
        except OpenAIAPIError as exc:
            raise LLMInvocationError(f"OpenAI request failed: {exc}") from exc

        return response.output_text.strip()

    async def _generate_with_anthropic(
        self,
        *,
        model: LLMModel,
        prompt: str,
        document: InsuranceDocumentInput | str,
        temperature: float,
        chunk_parser: Callable[[str], Any],
        chunk_merger: Callable[[list[Any]], Any],
    ) -> str:
        if not self._anthropic_client:
            raise LLMInvocationError("ANTHROPIC_API_KEY is not configured.")

        try:
            response = await self._anthropic_client.messages.create(
                model=model.value,
                system=prompt,
                messages=[{"role": "user", "content": self._build_anthropic_input(document)}],
                max_tokens=4096,
                temperature=temperature,
            )
            return self._extract_anthropic_text(response).strip()
        except AnthropicAPIError as exc:
            if isinstance(document, InsuranceDocumentInput) and self._is_prompt_too_long_error(exc):
                return await self._generate_with_anthropic_chunked_text(
                    model=model,
                    prompt=prompt,
                    document=document,
                    temperature=temperature,
                    chunk_parser=chunk_parser,
                    chunk_merger=chunk_merger,
                )
            raise LLMInvocationError(f"Anthropic request failed: {exc}") from exc

    async def _generate_with_anthropic_chunked_text(
        self,
        *,
        model: LLMModel,
        prompt: str,
        document: InsuranceDocumentInput,
        temperature: float,
        chunk_parser: Callable[[str], Any],
        chunk_merger: Callable[[list[Any]], Any],
    ) -> str:
        if not document.pages:
            raise LLMInvocationError(
                "Anthropic fallback needs extracted page text, but none was available for this document."
            )

        chunk_results: list[Any] = []
        for chunk_text in self._build_page_chunks(document, max_chars=ANTHROPIC_MAX_DOCUMENT_CHARS):
            try:
                response = await self._anthropic_client.messages.create(
                    model=model.value,
                    system=prompt,
                    messages=[{"role": "user", "content": self._build_document_text_input(chunk_text)}],
                    max_tokens=4096,
                    temperature=temperature,
                )
            except AnthropicAPIError as exc:
                raise LLMInvocationError(f"Anthropic request failed during chunked fallback: {exc}") from exc

            chunk_results.append(chunk_parser(self._extract_anthropic_text(response).strip()))

        merged = chunk_merger(chunk_results)
        return merged.model_dump_json(by_alias=True)

    @staticmethod
    def _build_document_text_input(document_text: str) -> str:
        return (
            "Insurance document text follows. The page markers are authoritative. "
            "Every extracted item must include its source page number.\n\n"
            f"{document_text}"
        )

    async def _build_openai_input(self, document: InsuranceDocumentInput | str) -> list[dict[str, object]]:
        if isinstance(document, str):
            return [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": self._build_document_text_input(document),
                        }
                    ],
                }
            ]

        uploaded_file = await self._openai_client.files.create(
            file=(
                document.filename,
                document.content,
                document.content_type or "application/pdf",
            ),
            purpose="user_data",
            expires_after={"anchor": "created_at", "seconds": OPENAI_TEMP_FILE_TTL_SECONDS},
        )
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Review the uploaded insurance document directly. "
                            "Return JSON only. Every extracted item must include its source page number."
                        ),
                    },
                    {
                        "type": "input_file",
                        "file_id": uploaded_file.id,
                    },
                ],
            }
        ]

    def _build_anthropic_input(self, document: InsuranceDocumentInput | str) -> str | list[dict[str, object]]:
        if isinstance(document, str):
            return self._build_document_text_input(document)

        return [
            {
                "type": "text",
                "text": (
                    "Review the uploaded insurance document directly. "
                    "Return JSON only. Every extracted item must include its source page number."
                ),
            },
            {
                "type": "document",
                "title": document.filename,
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64encode(document.content).decode("ascii"),
                },
            },
        ]

    @staticmethod
    def _build_page_chunks(document: InsuranceDocumentInput, *, max_chars: int) -> list[str]:
        chunks: list[str] = []
        current_sections: list[str] = []
        current_length = 0

        for page in document.pages:
            text = page.text.strip() or "[No extractable text found on this page.]"
            section = f"--- Page {page.page_number} ---\n{text}"
            section_length = len(section) + 2

            if current_sections and current_length + section_length > max_chars:
                chunks.append("\n\n".join(current_sections))
                current_sections = []
                current_length = 0

            if section_length > max_chars:
                if current_sections:
                    chunks.append("\n\n".join(current_sections))
                    current_sections = []
                    current_length = 0
                chunks.append(section)
                continue

            current_sections.append(section)
            current_length += section_length

        if current_sections:
            chunks.append("\n\n".join(current_sections))

        return chunks

    @staticmethod
    def _merge_extraction_results(results: list[InsuranceExtractionResult]) -> InsuranceExtractionResult:
        return InsuranceExtractionResult(
            policy_numbers=[item for result in results for item in result.policy_numbers],
            policy_periods=[item for result in results for item in result.policy_periods],
            insurance_companies=[item for result in results for item in result.insurance_companies],
            named_insured_and_mailing_addresses=[
                item for result in results for item in result.named_insured_and_mailing_addresses
            ],
            notes=[note for result in results for note in result.notes],
        )

    @staticmethod
    def _merge_premium_extraction_results(results: list[PremiumExtractionResult]) -> PremiumExtractionResult:
        return PremiumExtractionResult(
            premiums=[item for result in results for item in result.premiums],
        )

    @staticmethod
    def _normalize_premium_extraction_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and "premiums" in payload:
            items = payload["premiums"]
        elif isinstance(payload, dict):
            items = [payload]
        else:
            raise TypeError("Premium extraction payload must be a JSON object or array.")

        premiums: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                raise TypeError("Each premium extraction item must be a JSON object.")

            value = item.get("Premium(TP1)")
            if value is None:
                value = item.get("value")
            if value is None:
                continue
            if str(value).strip().lower() == "not found":
                continue

            premiums.append(
                {
                    "line_of_business": item.get("line_of_business"),
                    "value": value,
                    "page": item.get("pagenumber", item.get("page")),
                }
            )

        return {"premiums": premiums}

    def _normalize_merge_result(self, result: InsuranceMergeResult) -> InsuranceMergeResult:
        normalized_changes = []
        for change in result.field_level_changes:
            if change.field == "insurance_companies" and self._company_values_equivalent(change.current_value, change.prior_value):
                change.change_type = "unchanged"
            normalized_changes.append(change)

        result.field_level_changes = normalized_changes
        if self._company_values_equivalent(
            self._serialize_company_values(result.current_term.insurance_companies),
            self._serialize_company_values(result.prior_term.insurance_companies),
        ):
            if not any("insurance compan" in summary.lower() and "change" in summary.lower() for summary in result.comparison_summary):
                return result

            result.comparison_summary = [
                summary
                for summary in result.comparison_summary
                if not ("insurance compan" in summary.lower() and "change" in summary.lower())
            ]
        return result

    @staticmethod
    def _serialize_company_values(companies) -> str | None:
        if not companies:
            return None
        return "; ".join(company.value for company in companies if company.value)

    def _company_values_equivalent(self, current_value: str | None, prior_value: str | None) -> bool:
        if not current_value or not prior_value:
            return current_value == prior_value

        current_aliases = self._expand_company_aliases(current_value)
        prior_aliases = self._expand_company_aliases(prior_value)

        for current_alias in current_aliases:
            for prior_alias in prior_aliases:
                if current_alias == prior_alias:
                    return True
                if current_alias and prior_alias and (current_alias in prior_alias or prior_alias in current_alias):
                    return True
        return False

    def _expand_company_aliases(self, value: str) -> set[str]:
        aliases = set()
        for part in re.split(r"[;,/]|\\band\\b", value, flags=re.IGNORECASE):
            normalized = self._normalize_company_name(part)
            if normalized:
                aliases.add(normalized)
        whole_value = self._normalize_company_name(value)
        if whole_value:
            aliases.add(whole_value)
        return aliases

    @staticmethod
    def _normalize_company_name(value: str) -> str:
        normalized = value.casefold()
        normalized = normalized.replace("&", " and ")
        normalized = re.sub(r"[^a-z0-9\\s]", " ", normalized)
        normalized = re.sub(r"\\b(the|inc|llc|corp|corporation|co|company|insurance)\\b", " ", normalized)
        normalized = re.sub(r"\\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _is_prompt_too_long_error(exc: AnthropicAPIError) -> bool:
        return "prompt is too long" in str(exc).lower()

    @staticmethod
    def _extract_anthropic_text(response) -> str:
        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        if not text_blocks:
            raise LLMInvocationError("Anthropic response did not contain text output.")
        return "".join(text_blocks)

    @staticmethod
    def _load_json(response_text: str) -> dict:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return json.loads(cleaned)

    @staticmethod
    def _openai_supports_temperature(model: LLMModel) -> bool:
        return model not in {LLMModel.GPT_5, LLMModel.GPT_5_4, LLMModel.GPT_5_MINI}

    @staticmethod
    def _format_provider_error(exc: Exception) -> str:
        return str(exc)
