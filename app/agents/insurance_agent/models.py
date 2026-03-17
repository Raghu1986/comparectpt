from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LLMProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMModel(StrEnum):
    GPT_5 = "gpt-5"
    GPT_5_4 = "gpt-5.4"
    GPT_5_MINI = "gpt-5-mini"
    CLAUDE_OPUS_4_6 = "claude-opus-4-6"
    CLAUDE_HAIKU_4_5 = "claude-haiku-4-5"


class LLMConfig(BaseModel):
    provider: LLMProvider = Field(default=LLMProvider.OPENAI, description="Supported values: openai, anthropic")
    model: LLMModel | None = Field(default=None, description="Override the default model for the provider")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_model_for_provider(self):
        if self.model is None:
            return self

        provider_model_pairs = {
            LLMProvider.OPENAI: {LLMModel.GPT_5, LLMModel.GPT_5_4, LLMModel.GPT_5_MINI},
            LLMProvider.ANTHROPIC: {LLMModel.CLAUDE_OPUS_4_6, LLMModel.CLAUDE_HAIKU_4_5},
        }
        allowed_models = provider_model_pairs[self.provider]
        if self.model not in allowed_models:
            allowed_values = ", ".join(model.value for model in allowed_models)
            raise ValueError(f"Model {self.model.value} is not supported for provider {self.provider.value}. Allowed: {allowed_values}.")
        return self


class DocumentMetadata(BaseModel):
    filename: str
    content_type: str | None = None
    page_count: int


class PolicyNumberMatch(BaseModel):
    value: str
    page: int


class PolicyPeriodMatch(BaseModel):
    from_date: str | None = Field(default=None, alias="from")
    to_date: str | None = Field(default=None, alias="to")
    page: int

    model_config = {"populate_by_name": True}


class InsuranceCompanyMatch(BaseModel):
    value: str
    page: int


class NamedInsuredAddressMatch(BaseModel):
    named_insured: str | None = None
    mailing_address: str | None = None
    page: int


class PremiumMatch(BaseModel):
    line_of_business: str | None = None
    value: str
    page: int


class InsuranceExtractionResult(BaseModel):
    policy_numbers: list[PolicyNumberMatch] = Field(default_factory=list)
    policy_periods: list[PolicyPeriodMatch] = Field(default_factory=list)
    insurance_companies: list[InsuranceCompanyMatch] = Field(default_factory=list)
    named_insured_and_mailing_addresses: list[NamedInsuredAddressMatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FieldLevelChange(BaseModel):
    field: str
    current_value: str | None = None
    prior_value: str | None = None
    current_page: int | None = None
    prior_page: int | None = None
    observation: str | None = None
    change_type: Literal["added", "removed", "changed", "unchanged"]


class InsuranceMergeResult(BaseModel):
    current_term: InsuranceExtractionResult
    prior_term: InsuranceExtractionResult
    comparison_summary: list[str] = Field(default_factory=list)
    field_level_changes: list[FieldLevelChange] = Field(default_factory=list)


class PremiumExtractionResult(BaseModel):
    premiums: list[PremiumMatch] = Field(default_factory=list)


class PremiumMergeResult(BaseModel):
    current_term: PremiumExtractionResult
    prior_term: PremiumExtractionResult
    comparison_summary: list[str] = Field(default_factory=list)
    field_level_changes: list[FieldLevelChange] = Field(default_factory=list)


class PromptExecution(BaseModel):
    prompt: str
    response: str


class ExtractionExecution(PromptExecution):
    structured_output: InsuranceExtractionResult


class MergeExecution(PromptExecution):
    structured_output: InsuranceMergeResult


class InsuranceComparisonResponse(BaseModel):
    provider: LLMProvider
    model: LLMModel
    current_document: DocumentMetadata
    prior_document: DocumentMetadata
    current_extraction: ExtractionExecution
    prior_extraction: ExtractionExecution
    merged_output: MergeExecution


class PageText(BaseModel):
    page_number: int
    text: str


class InsuranceDocumentInput(BaseModel):
    filename: str
    content_type: str | None = None
    content: bytes
    page_count: int
    pages: list[PageText] = Field(default_factory=list)

    def as_prompt_text(self) -> str:
        if not self.pages:
            raise ValueError(f"{self.filename} does not have extracted page text available.")

        sections: list[str] = []
        for page in self.pages:
            text = page.text.strip() or "[No extractable text found on this page.]"
            sections.append(f"--- Page {page.page_number} ---\n{text}")
        return "\n\n".join(sections)
