from __future__ import annotations

from langchain_core.messages import HumanMessage

from clinical_research_agent._utils import format_prompt, llm_wait, load_prompt, parse_json_response
from clinical_research_agent.config import get_llm, get_settings
from clinical_research_agent.state import ResearchState

MAX_REFINEMENTS = 3

_prompt_template: str | None = None


def _get_prompt() -> str:
    global _prompt_template
    if _prompt_template is None:
        _prompt_template = load_prompt("planner")
    return _prompt_template


def run_planner(state: ResearchState) -> dict:
    """Hierarchical delegation: decomposes question into 3-5 focused sub-queries.

    Calls the LLM with prompts/planner.txt and parses the JSON response.
    Falls back to the original question as a single sub-query on parse failure.
    """
    settings = get_settings()
    if settings.debug:
        print("[planner] decomposing query...", flush=True)

    llm = get_llm(settings)
    prompt = format_prompt(_get_prompt(), question=state["question"])

    llm_wait()
    response = llm.invoke([HumanMessage(content=prompt)])
    content = str(response.content)

    try:
        data = parse_json_response(content)
        sub_queries: list[str] = data.get("sub_queries") or [state["question"]]
    except Exception:
        sub_queries = [state["question"]]

    usage = getattr(response, "usage_metadata", None) or {}
    if settings.debug:
        print(f"[planner] generated {len(sub_queries)} sub-queries: {sub_queries}", flush=True)

    return {
        "sub_queries": sub_queries,
        "critic_feedback": None,
        "refinement_count": 0,
        "review": None,
        "citations": [],
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }
