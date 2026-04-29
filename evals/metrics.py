from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class QueryMetrics:
    question_id: str
    question: str
    papers_found: int = 0
    claims_found: int = 0
    citation_accuracy: float = 0.0   # % of paper IDs re-verified as existing via API
    recency_3yr: float = 0.0         # % of papers from last 3 years
    faithfulness: float = 0.0        # LLM-as-judge score 0.0-1.0 vs expected_themes
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


def compute_citation_accuracy(papers: list[dict]) -> float:
    """Fraction of paper IDs that follow valid source-specific ID formats.

    Conservative proxy: checks ID prefix matches source field. A paper retrieved
    from PubMed with a malformed/missing PMID indicates an issue.
    Full API re-verification is available but adds ~1s per paper; call verify_paper_ids()
    for that path.
    """
    if not papers:
        return 1.0
    valid = 0
    for p in papers:
        pid = p.get("id", "")
        src = p.get("source", "")
        if src == "pubmed" and pid.startswith("pmid:") and len(pid) > 5:
            valid += 1
        elif src == "semantic_scholar" and pid.startswith("s2:") and len(pid) > 3:
            valid += 1
        elif src == "arxiv" and pid.startswith("arxiv:") and len(pid) > 6:
            valid += 1
    return valid / len(papers)


def compute_recency(papers: list[dict], years: int = 3) -> float:
    """Fraction of papers published within the last `years` years."""
    if not papers:
        return 0.0
    cutoff = datetime.utcnow().year - years
    recent = sum(1 for p in papers if (p.get("year") or 0) >= cutoff)
    return recent / len(papers)


def compute_faithfulness(
    review: str,
    expected_themes: list[str],
    judge_model: str,  # kept for API compat; actual model comes from get_judge_llm()
    api_key: str,      # kept for API compat; ignored (config drives auth)
) -> float:
    """LLM-as-judge: score whether review covers expected_themes (0.0-1.0).

    Uses get_judge_llm() which picks a cheaper model for the configured provider
    (gemini-1.5-flash for Gemini, claude-haiku for Anthropic).
    """
    if not review or not expected_themes:
        return 0.0

    from langchain_core.messages import HumanMessage

    from clinical_research_agent._utils import parse_json_response
    from clinical_research_agent.config import get_judge_llm

    themes_str = "\n".join(f"- {t}" for t in expected_themes)
    prompt = (
        f"You are evaluating a clinical literature review.\n\n"
        f"Expected themes that should be covered:\n{themes_str}\n\n"
        f"Review to evaluate (first 2000 chars):\n{review[:2000]}\n\n"
        f"Rate 0.0-1.0 how well the review covers the expected themes.\n"
        f"1.0 = all themes covered clearly. 0.0 = no relevant content.\n\n"
        'Return JSON only: {"score": <0.0-1.0>, "covered": ["theme1",...], "missing": ["theme2",...]}'
    )

    try:
        llm = get_judge_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        data = parse_json_response(str(response.content))
        return float(data.get("score", 0.0))
    except Exception:
        return 0.0


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost based on published model pricing (2025-Q2)."""
    pricing: dict[str, tuple[float, float]] = {
        # Anthropic
        "claude-sonnet-4-6": (3.0 / 1_000_000, 15.0 / 1_000_000),
        "claude-haiku-4-5-20251001": (0.25 / 1_000_000, 1.25 / 1_000_000),
        "claude-opus-4-7": (15.0 / 1_000_000, 75.0 / 1_000_000),
        # Gemini on Vertex AI (2025-Q2)
        "gemini-2.5-flash": (0.15 / 1_000_000, 0.60 / 1_000_000),
        "gemini-2.5-pro": (1.25 / 1_000_000, 10.0 / 1_000_000),
        "gemini-2.0-flash": (0.10 / 1_000_000, 0.40 / 1_000_000),
        "gemini-2.0-flash-001": (0.10 / 1_000_000, 0.40 / 1_000_000),
    }
    in_rate, out_rate = pricing.get(model, (0.15 / 1_000_000, 0.60 / 1_000_000))
    return input_tokens * in_rate + output_tokens * out_rate
