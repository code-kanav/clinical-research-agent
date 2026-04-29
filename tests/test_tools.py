from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Unit tests — import and basic contract only, no network
# ---------------------------------------------------------------------------

def test_pubmed_importable() -> None:
    from clinical_research_agent.tools.pubmed import search_pubmed
    assert callable(search_pubmed)


def test_semantic_scholar_importable() -> None:
    from clinical_research_agent.tools.semantic_scholar import search_semantic_scholar
    assert callable(search_semantic_scholar)


def test_arxiv_importable() -> None:
    from clinical_research_agent.tools.arxiv import search_arxiv
    assert callable(search_arxiv)


def test_pubmed_xml_parser_empty_input() -> None:
    from clinical_research_agent.tools.pubmed import _parse_xml
    assert _parse_xml("") == []
    assert _parse_xml("<bad xml") == []


def test_arxiv_feed_parser_empty_input() -> None:
    from clinical_research_agent.tools.arxiv import _parse_feed
    assert _parse_feed("") == []


# ---------------------------------------------------------------------------
# Integration tests — live network calls
# Run with: pytest --integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pubmed_returns_papers() -> None:
    from clinical_research_agent.tools.pubmed import search_pubmed
    results = search_pubmed("semaglutide weight loss RCT", max_results=3)
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("title" in p and "abstract" in p for p in results)


@pytest.mark.integration
def test_semantic_scholar_returns_papers() -> None:
    from clinical_research_agent.tools.semantic_scholar import search_semantic_scholar
    results = search_semantic_scholar("GLP-1 agonist obesity", max_results=3)
    assert isinstance(results, list)
    assert len(results) > 0


@pytest.mark.integration
def test_arxiv_returns_papers() -> None:
    from clinical_research_agent.tools.arxiv import search_arxiv
    results = search_arxiv("machine learning clinical prediction", max_results=3)
    assert isinstance(results, list)
    assert len(results) > 0
