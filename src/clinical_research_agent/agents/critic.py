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
        _prompt_template = load_prompt("critic")
    return _prompt_template


def run_critic(state: ResearchState) -> dict:
    """Self-reflection: evaluates claim coverage and returns continue or refine verdict.

    Increments refinement_count when verdict is "refine" so route_after_critic
    can enforce the MAX_REFINEMENTS ceiling without needing to track it separately.
    """
    settings = get_settings()
    llm = get_llm(settings)

    if state.get("debug"):
        print(f"[critic] evaluating {len(state['claims'])} claims from {len(state['papers'])} papers...", flush=True)

    claims_summary = _summarize_claims(state["claims"])
    prompt = format_prompt(
        _get_prompt(),
        question=state["question"],
        claims_summary=claims_summary,
        paper_count=str(len(state["papers"])),
        refinement_count=str(state["refinement_count"]),
        max_refinements=str(MAX_REFINEMENTS),
    )

    itok = otok = 0
    try:
        llm_wait()
        response = llm.invoke([HumanMessage(content=prompt)])  # type: ignore[union-attr]
        usage = getattr(response, "usage_metadata", None) or {}
        itok = int(usage.get("input_tokens", 0))
        otok = int(usage.get("output_tokens", 0))
        data = parse_json_response(str(response.content))
        verdict = str(data.get("verdict", "continue"))
    except Exception:
        verdict = "continue"
        data = {"verdict": "continue", "reasoning": "evaluation failed", "missing_perspectives": [], "suggested_queries": []}

    new_count = state["refinement_count"] + (1 if verdict == "refine" else 0)

    if state.get("debug"):
        print(f"[critic] verdict={verdict} refinement_count={new_count}/{MAX_REFINEMENTS}", flush=True)
        if data.get("missing_perspectives"):
            print(f"  gaps: {data['missing_perspectives']}", flush=True)

    return {
        "critic_feedback": {
            "verdict": verdict,
            "reasoning": data.get("reasoning", ""),
            "missing_perspectives": data.get("missing_perspectives") or [],
            "suggested_queries": data.get("suggested_queries") or [],
        },
        "refinement_count": new_count,
        "input_tokens": itok,
        "output_tokens": otok,
    }


def route_after_critic(state: ResearchState) -> str:
    """Conditional edge: routes to synthesizer or back to search.

    Forces synthesis once MAX_REFINEMENTS is reached, even if critic still wants to refine.
    """
    if state["refinement_count"] >= MAX_REFINEMENTS:
        return "continue"
    feedback = state.get("critic_feedback") or {}
    return str(feedback.get("verdict", "continue"))


def _summarize_claims(claims: list[dict], limit: int = 20) -> str:
    if not claims:
        return "No claims extracted yet."
    lines = [f"- {c['claim'][:120]} (from: {c.get('paper_title', '')[:50]})" for c in claims[:limit]]
    if len(claims) > limit:
        lines.append(f"... and {len(claims) - limit} more claims")
    return "\n".join(lines)
