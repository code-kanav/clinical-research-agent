from __future__ import annotations

from langchain_core.messages import HumanMessage

from clinical_research_agent._utils import format_prompt, llm_wait, load_prompt, parse_json_response
from clinical_research_agent.config import get_llm, get_settings
from clinical_research_agent.state import ResearchState

MAX_CLAIMS = 30

_prompt_template: str | None = None


def _get_prompt() -> str:
    global _prompt_template
    if _prompt_template is None:
        _prompt_template = load_prompt("synthesizer")
    return _prompt_template


def run_synthesizer(state: ResearchState) -> dict:
    """Produces final structured literature review with inline citations.

    Formats claims + papers into a prompt and calls the LLM to synthesize.
    Returns the review text and a deduplicated reference list.
    """
    settings = get_settings()
    llm = get_llm(settings)

    claims_with_citations = _format_claims(state["papers"], state["claims"])
    paper_references = _format_paper_references(state["papers"])

    prompt = format_prompt(
        _get_prompt(),
        question=state["question"],
        claims_with_citations=claims_with_citations,
        paper_references=paper_references,
    )

    if settings.debug:
        print(f"[synthesizer] synthesizing from {len(state['claims'])} claims across {len(state['papers'])} papers...", flush=True)

    itok = otok = 0
    try:
        llm_wait()
        response = llm.invoke([HumanMessage(content=prompt)])  # type: ignore[union-attr]
        usage = getattr(response, "usage_metadata", None) or {}
        itok = int(usage.get("input_tokens", 0))
        otok = int(usage.get("output_tokens", 0))
        content = str(response.content)
        try:
            data = parse_json_response(content)
            review = str(data.get("review") or content)
            citations: list[str] = list(data.get("references") or [])
        except Exception:
            review = content
            citations = _extract_references_from_text(content)
    except Exception as exc:
        review = (
            f"Synthesis failed: {exc}\n\n"
            f"Papers found: {len(state['papers'])}\n"
            f"Claims extracted: {len(state['claims'])}"
        )
        citations = []

    if settings.debug:
        print(f"[synthesizer] done  review_len={len(review)} citations={len(citations)} tokens={itok}+{otok}", flush=True)

    return {"review": review, "citations": citations, "input_tokens": itok, "output_tokens": otok}


def _format_claims(papers: list[dict], claims: list[dict], limit: int = MAX_CLAIMS) -> str:
    papers_by_id = {p["id"]: p for p in papers}
    lines: list[str] = []
    for i, claim in enumerate(claims[:limit], 1):
        paper = papers_by_id.get(claim["paper_id"], {})
        authors = paper.get("authors") or []
        first_author_last = (authors[0].split()[-1] if authors else "Unknown")
        year = paper.get("year", "?")
        title_short = (paper.get("title") or "")[:55]
        citation = f"[{first_author_last} et al., {year}]"
        lines.append(f"{i}. {claim['claim']} {citation}")
    if len(claims) > limit:
        lines.append(f"(... {len(claims) - limit} additional claims omitted for brevity)")
    return "\n".join(lines) if lines else "No claims available."


def _format_paper_references(papers: list[dict]) -> str:
    lines: list[str] = []
    for p in papers:
        authors = p.get("authors") or []
        first_author_last = authors[0].split()[-1] if authors else "Unknown"
        year = p.get("year", "?")
        title = p.get("title", "Unknown title")
        source = p.get("source", "?")
        url = p.get("url") or p.get("doi") or ""
        lines.append(f"- [{first_author_last} et al., {year}] {title}. Source: {source}. {url}")
    return "\n".join(lines) if lines else "No papers available."


def _extract_references_from_text(text: str) -> list[str]:
    lines = text.splitlines()
    refs: list[str] = []
    in_refs = False
    for line in lines:
        stripped = line.strip()
        if "**References**" in stripped or stripped.startswith("## References"):
            in_refs = True
            continue
        if in_refs and stripped:
            refs.append(stripped)
    return refs
