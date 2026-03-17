from typing import TypedDict

from app.agents.insurance_agent.llm import InsuranceLLMClient
from app.agents.insurance_agent.models import (
    InsuranceDocumentInput,
    InsuranceExtractionResult,
    InsuranceMergeResult,
    LLMConfig,
)


class InsuranceGraphState(TypedDict, total=False):
    current_document: InsuranceDocumentInput
    prior_document: InsuranceDocumentInput
    current_prompt: str
    prior_prompt: str
    merge_prompt: str
    llm_config: LLMConfig
    current_response: str
    prior_response: str
    merged_response: str
    current_structured: InsuranceExtractionResult
    prior_structured: InsuranceExtractionResult
    merged_structured: InsuranceMergeResult


def build_current_prompt_node(llm_client: InsuranceLLMClient):
    async def current_prompt_node(state: InsuranceGraphState) -> InsuranceGraphState:
        response = await llm_client.generate_json(
            prompt=state["current_prompt"],
            document=state["current_document"],
            config=state["llm_config"],
        )
        return {
            "current_response": response,
            "current_structured": llm_client.parse_extraction(response),
        }

    return current_prompt_node


def build_prior_prompt_node(llm_client: InsuranceLLMClient):
    async def prior_prompt_node(state: InsuranceGraphState) -> InsuranceGraphState:
        response = await llm_client.generate_json(
            prompt=state["prior_prompt"],
            document=state["prior_document"],
            config=state["llm_config"],
        )
        return {
            "prior_response": response,
            "prior_structured": llm_client.parse_extraction(response),
        }

    return prior_prompt_node


def build_merge_node(llm_client: InsuranceLLMClient):
    async def merge_node(state: InsuranceGraphState) -> InsuranceGraphState:
        merged_input = (
            "Current term extraction JSON:\n"
            f"{state['current_response']}\n\n"
            "Prior term extraction JSON:\n"
            f"{state['prior_response']}"
        )
        response = await llm_client.generate_json(
            prompt=state["merge_prompt"],
            document=merged_input,
            config=state["llm_config"],
        )
        return {
            "merged_response": response,
            "merged_structured": llm_client.parse_merge(response),
        }

    return merge_node
