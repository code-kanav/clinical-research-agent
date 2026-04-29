from __future__ import annotations

from typing import Optional

from clinical_research_agent.tools._utils import RateLimiter, get_cached, http_get, make_key, set_cached

SS_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,authors,year,externalIds,openAccessPdf"

_rate_limiter = RateLimiter(calls_per_second=0.9)  # conservative; key gives ~100/s


def search_semantic_scholar(
    query: str,
    max_results: int = 5,
    fields: str = SS_FIELDS,
) -> list[dict]:
    from clinical_research_agent.config import get_settings

    # fields included in key so different field requests cache separately
    key = make_key("s2", query, str(max_results), fields)
    cached = get_cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
        _rate_limiter._interval = 0.01  # ~100 req/s with key

    _rate_limiter.wait()
    resp = http_get(
        SS_SEARCH,
        params={"query": query, "limit": max_results, "fields": fields},
        headers=headers,
    )

    papers = [_to_paper(d) for d in resp.json().get("data", []) if d.get("abstract")]
    set_cached(key, papers)
    return papers


def _to_paper(d: dict) -> dict:
    external = d.get("externalIds") or {}
    doi: Optional[str] = external.get("DOI")
    pmid: Optional[str] = external.get("PubMed")

    url: Optional[str] = None
    pdf = d.get("openAccessPdf")
    if pdf and isinstance(pdf, dict):
        url = pdf.get("url")
    if not url and d.get("paperId"):
        url = f"https://www.semanticscholar.org/paper/{d['paperId']}"

    return {
        "id": f"s2:{d.get('paperId', '')}",
        "title": (d.get("title") or "").strip(),
        "abstract": (d.get("abstract") or "").strip(),
        "authors": [a["name"] for a in (d.get("authors") or []) if a.get("name")],
        "year": d.get("year"),
        "source": "semantic_scholar",
        "url": url,
        "doi": doi,
        "pmid": pmid,
    }
