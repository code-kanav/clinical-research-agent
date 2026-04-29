from __future__ import annotations

from langchain_core.messages import HumanMessage

from clinical_research_agent._utils import format_prompt, llm_wait, load_prompt, parse_json_response
from clinical_research_agent.config import get_llm, get_settings
from clinical_research_agent.state import ResearchState

MAX_PAPERS = 5  # cap LLM calls: 1 per paper

_prompt_template: str | None = None


def _get_prompt() -> str:
    global _prompt_template
    if _prompt_template is None:
        _prompt_template = load_prompt("reader")
    return _prompt_template


def run_reader(state: ResearchState) -> dict:
    """Tool use: calls LLM once per paper to extract structured claims from abstracts.

    Only processes papers not yet claimed (safe for critic refinement cycles).
    Sorts by recency, caps at MAX_PAPERS to bound LLM call count.
    """
    settings = get_settings()
    llm = get_llm(settings)

    claimed_ids = {c["paper_id"] for c in state["claims"]}
    unread = [p for p in state["papers"] if p.get("abstract") and p["id"] not in claimed_ids]
    unread = sorted(unread, key=lambda p: p.get("year") or 0, reverse=True)[:MAX_PAPERS]

    if not unread:
        if settings.debug:
            print("[reader] no new papers to read", flush=True)
        return {"claims": [], "input_tokens": 0, "output_tokens": 0}

    if settings.debug:
        print(f"[reader] extracting claims from {len(unread)} papers...", flush=True)

    new_claims: list[dict] = []
    total_in = total_out = 0
    for paper in unread:
        claims, itok, otok = _extract_claims(llm, paper, settings.debug)
        new_claims.extend(claims)
        total_in += itok
        total_out += otok

    if settings.debug:
        print(f"[reader] done  papers={len(unread)} claims={len(new_claims)} tokens={total_in}+{total_out}", flush=True)

    return {"claims": new_claims, "input_tokens": total_in, "output_tokens": total_out}


def _extract_claims(llm: object, paper: dict, debug: bool = False) -> tuple[list[dict], int, int]:
    authors = paper.get("authors", [])
    authors_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")

    prompt = format_prompt(
        _get_prompt(),
        title=paper.get("title") or "",
        authors=authors_str or "Unknown",
        year=str(paper.get("year") or "Unknown"),
        abstract=paper.get("abstract") or "",
    )

    try:
        llm_wait()
        response = llm.invoke([HumanMessage(content=prompt)])  # type: ignore[union-attr]
        usage = getattr(response, "usage_metadata", None) or {}
        itok = int(usage.get("input_tokens", 0))
        otok = int(usage.get("output_tokens", 0))

        data = parse_json_response(str(response.content))
        raw = data.get("claims") or []

        result: list[dict] = []
        for item in raw:
            if isinstance(item, str):
                result.append({"paper_id": paper["id"], "paper_title": paper.get("title", ""), "claim": item, "confidence": 1.0})
            elif isinstance(item, dict) and item.get("claim"):
                result.append({
                    "paper_id": paper["id"],
                    "paper_title": paper.get("title", ""),
                    "claim": item["claim"],
                    "confidence": float(item.get("confidence", 1.0)),
                })
        return result, itok, otok

    except Exception as exc:
        if debug:
            print(f"  [reader] failed {paper['id']}: {exc}")
        return [], 0, 0
