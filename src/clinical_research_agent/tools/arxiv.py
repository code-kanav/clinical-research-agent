from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from clinical_research_agent.tools._utils import RateLimiter, get_cached, http_get, make_key, set_cached

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"

_rate_limiter = RateLimiter(calls_per_second=0.33)  # 1 req / 3 s per arXiv guidelines


def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    key = make_key("arxiv", query, str(max_results))
    cached = get_cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    _rate_limiter.wait()
    resp = http_get(
        ARXIV_API,
        params={"search_query": f"all:{query}", "max_results": max_results},
    )

    papers = _parse_feed(resp.text)
    set_cached(key, papers)
    return papers


def _parse_feed(xml_text: str) -> list[dict]:
    papers: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return papers

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        try:
            arxiv_id_raw = (entry.findtext(f"{{{ATOM_NS}}}id") or "").strip()
            # e.g. http://arxiv.org/abs/2301.12345v1 → 2301.12345
            arxiv_id = re.sub(r"v\d+$", "", arxiv_id_raw.split("/abs/")[-1])

            title = (entry.findtext(f"{{{ATOM_NS}}}title") or "").strip().replace("\n", " ")
            abstract = (entry.findtext(f"{{{ATOM_NS}}}summary") or "").strip().replace("\n", " ")

            if not title or not abstract:
                continue

            authors: list[str] = [
                (a.findtext(f"{{{ATOM_NS}}}name") or "").strip()
                for a in entry.findall(f"{{{ATOM_NS}}}author")
            ]

            published = entry.findtext(f"{{{ATOM_NS}}}published", "")
            year: Optional[int] = None
            m = re.match(r"(\d{4})", published)
            if m:
                year = int(m.group(1))

            doi_el = entry.find(f"{{{ARXIV_NS}}}doi")
            doi: Optional[str] = doi_el.text if doi_el is not None else None

            papers.append({
                "id": f"arxiv:{arxiv_id}",
                "title": title,
                "abstract": abstract,
                "authors": [a for a in authors if a],
                "year": year,
                "source": "arxiv",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "doi": doi,
            })
        except Exception:
            continue

    return papers
