from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from clinical_research_agent.tools._utils import RateLimiter, get_cached, http_get, make_key, set_cached

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Updated dynamically based on whether NCBI_API_KEY is set.
_rate_limiter = RateLimiter(calls_per_second=3.0)


def _get_rate_limiter() -> RateLimiter:
    from clinical_research_agent.config import get_settings
    cps = 10.0 if get_settings().ncbi_api_key else 3.0
    _rate_limiter._interval = 1.0 / cps
    return _rate_limiter


def search_pubmed(query: str, max_results: int = 5) -> list[dict]:
    from clinical_research_agent.config import get_settings

    key = make_key("pubmed", query, str(max_results))
    cached = get_cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    settings = get_settings()
    rl = _get_rate_limiter()

    base_params: dict[str, str | int] = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    if settings.ncbi_api_key:
        base_params["api_key"] = settings.ncbi_api_key

    rl.wait()
    resp = http_get(f"{EUTILS_BASE}/esearch.fcgi", params=base_params)

    ids: list[str] = resp.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        set_cached(key, [])
        return []

    fetch_params: dict[str, str] = {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"}
    if settings.ncbi_api_key:
        fetch_params["api_key"] = settings.ncbi_api_key

    rl.wait()
    resp = http_get(f"{EUTILS_BASE}/efetch.fcgi", params=fetch_params)

    papers = _parse_xml(resp.text)
    set_cached(key, papers)
    return papers


def _parse_xml(xml_text: str) -> list[dict]:
    papers: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return papers

    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.findtext(".//PMID", "")
            title = (article.findtext(".//ArticleTitle") or "").strip()

            abstract_parts: list[str] = []
            for ab in article.findall(".//AbstractText"):
                label = ab.get("Label", "")
                text = (ab.text or "").strip()
                if text:
                    abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(abstract_parts)

            if not title or not abstract:
                continue

            authors: list[str] = []
            for auth in article.findall(".//Author"):
                last = auth.findtext("LastName", "")
                first = auth.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())

            year: Optional[int] = None
            year_str = article.findtext(".//PubDate/Year", "")
            if year_str and year_str.isdigit():
                year = int(year_str)
            else:
                medline = article.findtext(".//MedlineDate", "")
                m = re.search(r"\b(19|20)\d{2}\b", medline)
                if m:
                    year = int(m.group())

            doi: Optional[str] = None
            for id_el in article.findall(".//ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text

            papers.append({
                "id": f"pmid:{pmid}",
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "year": year,
                "source": "pubmed",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi": doi,
            })
        except Exception:
            continue

    return papers
