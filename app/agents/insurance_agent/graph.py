from langgraph.graph import END, START, StateGraph

from app.agents.insurance_agent.llm import InsuranceLLMClient
from app.agents.insurance_agent.models import (
    DocumentMetadata,
    ExtractionExecution,
    FieldLevelChange,
    InsuranceComparisonResponse,
    InsuranceDocumentInput,
    LLMConfig,
    MergeExecution,
)
from app.agents.insurance_agent.nodes import (
    InsuranceGraphState,
    build_current_prompt_node,
    build_current_premium_prompt_node,
    build_merge_node,
    build_premium_merge_node,
    build_prior_prompt_node,
    build_prior_premium_prompt_node,
)
from app.agents.insurance_agent.prompts import get_insurance_prompts


def build_insurance_graph(llm_client: InsuranceLLMClient):
    current_prompt_node = build_current_prompt_node(llm_client)
    prior_prompt_node = build_prior_prompt_node(llm_client)
    merge_node = build_merge_node(llm_client)
    current_premium_prompt_node = build_current_premium_prompt_node(llm_client)
    prior_premium_prompt_node = build_prior_premium_prompt_node(llm_client)
    premium_merge_node = build_premium_merge_node(llm_client)

    graph = StateGraph(InsuranceGraphState)
    graph.add_node("current_prompt", current_prompt_node)
    graph.add_node("prior_prompt", prior_prompt_node)
    graph.add_node("merge", merge_node)
    graph.add_node("current_premium_prompt", current_premium_prompt_node)
    graph.add_node("prior_premium_prompt", prior_premium_prompt_node)
    graph.add_node("premium_merge", premium_merge_node)

    graph.add_edge(START, "current_prompt")
    graph.add_edge("current_prompt", "prior_prompt")
    graph.add_edge("prior_prompt", "merge")
    graph.add_edge("merge", "current_premium_prompt")
    graph.add_edge("current_premium_prompt", "prior_premium_prompt")
    graph.add_edge("prior_premium_prompt", "premium_merge")
    graph.add_edge("premium_merge", END)

    return graph.compile()


def _merge_premium_into_result(
    *,
    base_summary: list[str],
    base_changes: list[FieldLevelChange],
    premium_summary: list[str],
    premium_changes: list[FieldLevelChange],
):
    return (
        [*base_summary, *premium_summary],
        [*base_changes, *premium_changes],
    )


async def run_insurance_comparison(
    *,
    current_document: InsuranceDocumentInput,
    prior_document: InsuranceDocumentInput,
    llm_config: LLMConfig,
    llm_client: InsuranceLLMClient,
) -> InsuranceComparisonResponse:
    prompts = get_insurance_prompts()
    current_prompt = prompts["current_prompt"]
    prior_prompt = prompts["prior_prompt"]
    merge_prompt = prompts["merge_prompt"]
    current_premium_prompt = prompts["premium_extraction_prompt_sample"]
    prior_premium_prompt = prompts["premium_extraction_prompt_sample"]
    premium_merge_prompt = prompts["premium_merge_prompt"]

    app = build_insurance_graph(llm_client)
    final_state = await app.ainvoke(
        {
            "current_document": current_document,
            "prior_document": prior_document,
            "current_prompt": current_prompt,
            "prior_prompt": prior_prompt,
            "merge_prompt": merge_prompt,
            "current_premium_prompt": current_premium_prompt,
            "prior_premium_prompt": prior_premium_prompt,
            "premium_merge_prompt": premium_merge_prompt,
            "llm_config": llm_config,
        }
    )

    model = llm_client.resolve_model(llm_config)
    merged_summary, merged_changes = _merge_premium_into_result(
        base_summary=final_state["merged_structured"].comparison_summary,
        base_changes=final_state["merged_structured"].field_level_changes,
        premium_summary=final_state["premium_merged_structured"].comparison_summary,
        premium_changes=final_state["premium_merged_structured"].field_level_changes,
    )
    final_state["merged_structured"].comparison_summary = merged_summary
    final_state["merged_structured"].field_level_changes = merged_changes

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
