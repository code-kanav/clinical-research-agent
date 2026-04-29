from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Unit tests — no LLM calls, no network
# ---------------------------------------------------------------------------

def test_graph_builds() -> None:
    from clinical_research_agent.graph import graph
    assert graph is not None


def test_graph_invoke_with_mocked_llm() -> None:
    """Full graph traversal — LLM stubbed to return deterministic JSON at each node."""
    from langchain_core.messages import AIMessage
    from clinical_research_agent.graph import graph

    planner_response = AIMessage(
        content='{"sub_queries": ["GLP-1 agonists weight loss RCT"], "rationale": "test"}'
    )
    reader_response = AIMessage(
        content='{"claims": [{"claim": "Drug X reduced weight by 10%.", "confidence": 0.9}]}'
    )
    critic_response = AIMessage(
        content='{"verdict": "continue", "reasoning": "sufficient", "missing_perspectives": [], "suggested_queries": []}'
    )
    synthesizer_response = AIMessage(
        content='{"review": "## Summary\\nDrug X is effective.", "references": ["[Smith et al., 2023] Title."]}'
    )

    call_count = [0]
    responses = [planner_response, reader_response, critic_response, synthesizer_response]

    def fake_invoke(messages):  # type: ignore[no-untyped-def]
        r = responses[min(call_count[0], len(responses) - 1)]
        call_count[0] += 1
        return r

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = fake_invoke

    with patch("clinical_research_agent.agents.planner.get_llm", return_value=fake_llm), \
         patch("clinical_research_agent.agents.reader.get_llm", return_value=fake_llm), \
         patch("clinical_research_agent.agents.critic.get_llm", return_value=fake_llm), \
         patch("clinical_research_agent.agents.synthesizer.get_llm", return_value=fake_llm), \
         patch("clinical_research_agent.agents.search._fetch_all_sources", return_value=[
             {"id": "pmid:1", "title": "Paper A", "abstract": "Abstract A.", "authors": ["Smith J"], "year": 2023, "source": "pubmed"}
         ]), \
         patch("clinical_research_agent.agents.search._evaluate", return_value={"action": "accept", "reasoning": "good"}):

        result = graph.invoke({
            "question": "test question",
            "sub_queries": [],
            "papers": [],
            "claims": [],
            "critic_feedback": None,
            "refinement_count": 0,
            "review": None,
            "citations": [],
            "debug": False,
        })

    assert result["question"] == "test question"
    assert result["sub_queries"] == ["GLP-1 agonists weight loss RCT"]
    assert len(result["papers"]) == 1
    assert len(result["claims"]) >= 1
    assert result["review"] is not None
    assert "effective" in result["review"]


def test_planner_with_mocked_llm() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.planner import run_planner

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"sub_queries": ["query A", "query B"], "rationale": "test"}'
    )
    state = {
        "question": "GLP-1 agonists for weight loss", "sub_queries": [], "papers": [], "claims": [],
        "critic_feedback": None, "refinement_count": 0, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.planner.get_llm", return_value=fake_llm):
        out = run_planner(state)  # type: ignore[arg-type]
    assert out["sub_queries"] == ["query A", "query B"]


def test_planner_fallback_on_bad_json() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.planner import run_planner

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content="Sorry I cannot help.")
    state = {
        "question": "original question", "sub_queries": [], "papers": [], "claims": [],
        "critic_feedback": None, "refinement_count": 0, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.planner.get_llm", return_value=fake_llm):
        out = run_planner(state)  # type: ignore[arg-type]
    assert out["sub_queries"] == ["original question"]


def test_reader_extracts_claims() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.reader import run_reader

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"claims": [{"claim": "Drug X reduced weight.", "confidence": 0.9}]}'
    )
    state = {
        "question": "test", "sub_queries": [], "claims": [],
        "papers": [{"id": "pmid:1", "title": "Title", "abstract": "Abstract.", "authors": ["Smith J"], "year": 2023, "source": "pubmed"}],
        "critic_feedback": None, "refinement_count": 0, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.reader.get_llm", return_value=fake_llm):
        out = run_reader(state)  # type: ignore[arg-type]
    assert len(out["claims"]) == 1
    assert out["claims"][0]["paper_id"] == "pmid:1"
    assert out["claims"][0]["confidence"] == 0.9


def test_reader_skips_already_claimed_papers() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.reader import run_reader

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content='{"claims": [{"claim": "New claim.", "confidence": 1.0}]}')
    state = {
        "question": "test", "sub_queries": [],
        "papers": [
            {"id": "pmid:1", "title": "Already read", "abstract": "Abstract.", "authors": [], "year": 2023, "source": "pubmed"},
            {"id": "pmid:2", "title": "New paper", "abstract": "Abstract.", "authors": [], "year": 2024, "source": "pubmed"},
        ],
        "claims": [{"paper_id": "pmid:1", "paper_title": "Already read", "claim": "Old claim.", "confidence": 1.0}],
        "critic_feedback": None, "refinement_count": 0, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.reader.get_llm", return_value=fake_llm):
        out = run_reader(state)  # type: ignore[arg-type]
    # Only pmid:2 processed (pmid:1 already claimed)
    assert fake_llm.invoke.call_count == 1
    assert out["claims"][0]["paper_id"] == "pmid:2"


def test_critic_returns_continue_verdict() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.critic import run_critic

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"verdict": "continue", "reasoning": "enough evidence", "missing_perspectives": [], "suggested_queries": []}'
    )
    state = {
        "question": "test", "sub_queries": [], "papers": [],
        "claims": [{"paper_id": "pmid:1", "paper_title": "T", "claim": "C", "confidence": 1.0}],
        "critic_feedback": None, "refinement_count": 0, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.critic.get_llm", return_value=fake_llm):
        out = run_critic(state)  # type: ignore[arg-type]
    assert out["critic_feedback"]["verdict"] == "continue"
    assert out["refinement_count"] == 0  # not incremented on "continue"


def test_critic_increments_count_on_refine() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.critic import run_critic

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"verdict": "refine", "reasoning": "missing RCTs", "missing_perspectives": ["RCTs"], "suggested_queries": ["semaglutide RCT"]}'
    )
    state = {
        "question": "test", "sub_queries": [], "papers": [], "claims": [],
        "critic_feedback": None, "refinement_count": 1, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.critic.get_llm", return_value=fake_llm):
        out = run_critic(state)  # type: ignore[arg-type]
    assert out["critic_feedback"]["verdict"] == "refine"
    assert out["refinement_count"] == 2  # incremented


def test_critic_route_forces_continue_at_max() -> None:
    from clinical_research_agent.agents.critic import MAX_REFINEMENTS, route_after_critic
    state = {
        "question": "test", "sub_queries": [], "papers": [], "claims": [],
        "critic_feedback": {"verdict": "refine", "reasoning": "", "missing_perspectives": [], "suggested_queries": []},
        "refinement_count": MAX_REFINEMENTS,
        "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    assert route_after_critic(state) == "continue"  # type: ignore[arg-type]


def test_synthesizer_parses_json_response() -> None:
    from langchain_core.messages import AIMessage
    from clinical_research_agent.agents.synthesizer import run_synthesizer

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"review": "## Summary\\nGLP-1 agonists reduce weight.", "references": ["[Smith et al., 2023] Title. pubmed."]}'
    )
    state = {
        "question": "GLP-1 for weight loss", "sub_queries": [],
        "papers": [{"id": "pmid:1", "title": "Title", "abstract": "Abs.", "authors": ["Smith J"], "year": 2023, "source": "pubmed", "url": "https://pubmed.ncbi.nlm.nih.gov/1/"}],
        "claims": [{"paper_id": "pmid:1", "paper_title": "Title", "claim": "Reduces weight.", "confidence": 0.9}],
        "critic_feedback": None, "refinement_count": 0, "review": None, "citations": [], "debug": False, "input_tokens": 0, "output_tokens": 0,
    }
    with patch("clinical_research_agent.agents.synthesizer.get_llm", return_value=fake_llm):
        out = run_synthesizer(state)  # type: ignore[arg-type]
    assert "GLP-1 agonists reduce weight" in out["review"]
    assert len(out["citations"]) == 1


def test_search_dedup() -> None:
    from clinical_research_agent.agents.search import _dedup
    papers = [
        {"id": "pmid:1", "title": "Same Title", "source": "pubmed"},
        {"id": "s2:abc", "title": "Same Title", "source": "semantic_scholar"},
        {"id": "pmid:2", "title": "Different Title", "source": "pubmed"},
    ]
    result = _dedup(papers)
    assert len(result) == 2
    assert result[0]["id"] == "pmid:1"


# ---------------------------------------------------------------------------
# Integration tests — live API keys + network
# Run with: pytest --integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_full_graph_real_llm() -> None:
    """End-to-end graph with real LLM and real search APIs."""
    from clinical_research_agent.graph import graph
    result = graph.invoke({
        "question": "GLP-1 agonists for weight loss non-diabetic",
        "sub_queries": [], "papers": [], "claims": [],
        "critic_feedback": None, "refinement_count": 0,
        "review": None, "citations": [], "debug": True, "input_tokens": 0, "output_tokens": 0,
    })
    assert result["review"] is not None
    assert len(result["sub_queries"]) >= 1
    assert len(result["papers"]) > 0
