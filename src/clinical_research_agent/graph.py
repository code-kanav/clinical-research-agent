from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from clinical_research_agent.agents.critic import route_after_critic, run_critic
from clinical_research_agent.agents.planner import run_planner
from clinical_research_agent.agents.reader import run_reader
from clinical_research_agent.agents.search import run_search
from clinical_research_agent.agents.synthesizer import run_synthesizer
from clinical_research_agent.state import ResearchState


def build_graph() -> Any:
    """Wire the LangGraph state machine.

    Flow:
        Planner → Search ↔ Reader (search ReAct loop is internal to Search node)
              → Critic → [refine → Search | continue → Synthesizer] → END

    Critic loop is bounded by MAX_REFINEMENTS in agents/critic.py.
    """
    builder: StateGraph = StateGraph(ResearchState)

    builder.add_node("planner", run_planner)
    builder.add_node("search", run_search)
    builder.add_node("reader", run_reader)
    builder.add_node("critic", run_critic)
    builder.add_node("synthesizer", run_synthesizer)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "search")
    builder.add_edge("search", "reader")
    builder.add_edge("reader", "critic")
    builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "refine": "search",
            "continue": "synthesizer",
        },
    )
    builder.add_edge("synthesizer", END)

    return builder.compile()


# Compiled once at import time; reused across CLI invocations.
graph = build_graph()
