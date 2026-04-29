from __future__ import annotations

from langchain_core.messages import HumanMessage

from clinical_research_agent._utils import format_prompt, llm_wait, load_prompt, parse_json_response
from clinical_research_agent.config import get_llm, get_settings
from clinical_research_agent.state import ResearchState
from clinical_research_agent.tools.arxiv import search_arxiv
from clinical_research_agent.tools.pubmed import search_pubmed
from clinical_research_agent.tools.semantic_scholar import search_semantic_scholar

MAX_REACT_ITERATIONS = 1  # skip LLM eval; accept first results to minimise API calls

_prompt_template: str | None = None
_search_tokens: dict[str, int] = {"input": 0, "output": 0}  # reset each run_search call


def _get_prompt() -> str:
    global _prompt_template
    if _prompt_template is None:
        _prompt_template = load_prompt("search")
    return _prompt_template


def run_search(state: ResearchState) -> dict:
    """ReAct loop: for each sub-query, search → evaluate → refine (max 3 iterations).

    On critic-driven refinement cycles, uses suggested_queries from critic_feedback
    instead of the original sub_queries.
    """
    settings = get_settings()
    llm = get_llm(settings)
    _search_tokens["input"] = 0
    _search_tokens["output"] = 0

    if state["refinement_count"] > 0 and state.get("critic_feedback"):
        queries = state["critic_feedback"].get("suggested_queries") or state["sub_queries"]
    else:
        queries = state["sub_queries"]

    if state.get("debug"):
        cycle = state["refinement_count"] + 1
        print(f"[search] cycle={cycle} running {len(queries)} queries...", flush=True)

    new_papers: list[dict] = []
    for sub_query in queries:
        papers = _react_search(llm, sub_query, state.get("debug"))
        new_papers.extend(papers)

    # Deduplicate new_papers internally, then exclude already-collected IDs/titles.
    new_papers = _dedup(new_papers)
    existing_ids = {p["id"] for p in state["papers"]}
    existing_titles = {(p.get("title") or "").lower().strip() for p in state["papers"]}
    fresh = [
        p for p in new_papers
        if p["id"] not in existing_ids
        and (p.get("title") or "").lower().strip() not in existing_titles
    ]

    if state.get("debug"):
        print(f"[search] fetched={len(new_papers)} fresh={len(fresh)} total_after={len(state['papers']) + len(fresh)}", flush=True)

    return {"papers": fresh, "input_tokens": _search_tokens["input"], "output_tokens": _search_tokens["output"]}


def _react_search(llm: object, sub_query: str, debug: bool = False) -> list[dict]:
    current_query = sub_query
    all_papers: list[dict] = []

    for iteration in range(1, MAX_REACT_ITERATIONS + 1):
        batch = _fetch_all_sources(current_query)
        all_papers.extend(batch)

        if debug:
            print(f"  [react] iter={iteration} query={current_query!r} got={len(batch)}", flush=True)

        # Skip LLM eval on final iteration — just accept what we have.
        if iteration == MAX_REACT_ITERATIONS:
            break

        decision = _evaluate(llm, sub_query, current_query, batch, iteration)
        if decision.get("action") == "accept":
            if debug:
                print(f"  [react] accepted at iteration {iteration}", flush=True)
            break

        refined = decision.get("refined_query", "").strip()
        if not refined or refined == current_query:
            break
        current_query = refined

    return all_papers


def _fetch_all_sources(query: str) -> list[dict]:
    papers: list[dict] = []
    for fetch_fn in (search_pubmed, search_semantic_scholar, search_arxiv):
        try:
            papers.extend(fetch_fn(query))  # type: ignore[operator]
        except Exception as exc:
            print(f"  [search] {fetch_fn.__name__} error: {exc}")
    return papers


def _evaluate(llm: object, original_query: str, current_query: str, papers: list[dict], iteration: int) -> dict:
    summary = _summarize(papers)
    prompt = format_prompt(
        _get_prompt(),
        sub_query=original_query,
        current_query=current_query,
        iteration=str(iteration),
        max_iterations=str(MAX_REACT_ITERATIONS),
        paper_count=str(len(papers)),
        paper_summary=summary,
    )
    try:
        llm_wait()
        response = llm.invoke([HumanMessage(content=prompt)])  # type: ignore[union-attr]
        usage = getattr(response, "usage_metadata", None) or {}
        _search_tokens["input"] += int(usage.get("input_tokens", 0))
        _search_tokens["output"] += int(usage.get("output_tokens", 0))
        return parse_json_response(str(response.content))
    except Exception:
        return {"action": "accept", "reasoning": "evaluation failed, accepting results"}


def _summarize(papers: list[dict]) -> str:
    if not papers:
        return "No papers found."
    lines = []
    for i, p in enumerate(papers[:10], 1):
        year = p.get("year", "?")
        src = p.get("source", "?")
        title = (p.get("title") or "untitled")[:90]
        lines.append(f"{i}. [{src}, {year}] {title}")
    if len(papers) > 10:
        lines.append(f"... and {len(papers) - 10} more")
    return "\n".join(lines)


def _dedup(papers: list[dict]) -> list[dict]:
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        pid = p["id"]
        title_key = (p.get("title") or "").lower().strip()
        if pid in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(pid)
        if title_key:
            seen_titles.add(title_key)
        unique.append(p)
    return unique
