from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.insurance_agent.llm import InsuranceLLMClient
from app.agents.insurance_agent.models import (
    DocumentMetadata,
    ExtractionExecution,
    InsuranceComparisonResponse,
    InsuranceDocumentInput,
    InsuranceExtractionResult,
    InsuranceMergeResult,
    LLMConfig,
    MergeExecution,
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


async def _run_current_prompt(state: InsuranceGraphState, llm_client: InsuranceLLMClient) -> InsuranceGraphState:
    response = await llm_client.generate_json(
        prompt=state["current_prompt"],
        document=state["current_document"],
        config=state["llm_config"],
    )
    return {"current_response": response, "current_structured": llm_client.parse_extraction(response)}


async def _run_prior_prompt(state: InsuranceGraphState, llm_client: InsuranceLLMClient) -> InsuranceGraphState:
    response = await llm_client.generate_json(
        prompt=state["prior_prompt"],
        document=state["prior_document"],
        config=state["llm_config"],
    )
    return {"prior_response": response, "prior_structured": llm_client.parse_extraction(response)}


async def _merge_responses(state: InsuranceGraphState, llm_client: InsuranceLLMClient) -> InsuranceGraphState:
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
    return {"merged_response": response, "merged_structured": llm_client.parse_merge(response)}


def build_insurance_graph(llm_client: InsuranceLLMClient):
    async def current_prompt_node(state: InsuranceGraphState) -> InsuranceGraphState:
        return await _run_current_prompt(state, llm_client)

    async def prior_prompt_node(state: InsuranceGraphState) -> InsuranceGraphState:
        return await _run_prior_prompt(state, llm_client)

    async def merge_node(state: InsuranceGraphState) -> InsuranceGraphState:
        return await _merge_responses(state, llm_client)

    graph = StateGraph(InsuranceGraphState)
    graph.add_node("current_prompt", current_prompt_node)
    graph.add_node("prior_prompt", prior_prompt_node)
    graph.add_node("merge", merge_node)

    graph.add_edge(START, "current_prompt")
    graph.add_edge("current_prompt", "prior_prompt")
    graph.add_edge("prior_prompt", "merge")
    graph.add_edge("merge", END)

    return graph.compile()


async def run_insurance_comparison(
    *,
    current_document: InsuranceDocumentInput,
    prior_document: InsuranceDocumentInput,
    current_prompt: str,
    prior_prompt: str,
    merge_prompt: str,
    llm_config: LLMConfig,
    llm_client: InsuranceLLMClient,
) -> InsuranceComparisonResponse:
    app = build_insurance_graph(llm_client)
    final_state = await app.ainvoke(
        {
            "current_document": current_document,
            "prior_document": prior_document,
            "current_prompt": current_prompt,
            "prior_prompt": prior_prompt,
            "merge_prompt": merge_prompt,
            "llm_config": llm_config,
        }
    )

    model = llm_client.resolve_model(llm_config)
    return InsuranceComparisonResponse(
        provider=llm_config.provider,
        model=model,
        current_document=DocumentMetadata(
            filename=current_document.filename,
            content_type=current_document.content_type,
            page_count=current_document.page_count,
        ),
        prior_document=DocumentMetadata(
            filename=prior_document.filename,
            content_type=prior_document.content_type,
            page_count=prior_document.page_count,
        ),
        current_extraction=ExtractionExecution(
            prompt=current_prompt,
            response=final_state["current_response"],
            structured_output=final_state["current_structured"],
        ),
        prior_extraction=ExtractionExecution(
            prompt=prior_prompt,
            response=final_state["prior_response"],
            structured_output=final_state["prior_structured"],
        ),
        merged_output=MergeExecution(
            prompt=merge_prompt,
            response=final_state["merged_response"],
            structured_output=final_state["merged_structured"],
        ),
    )
