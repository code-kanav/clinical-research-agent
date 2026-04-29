from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from pydantic import BaseModel, Field


class Paper(BaseModel):
    id: str
    title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    source: str  # "pubmed" | "semantic_scholar" | "arxiv"
    url: Optional[str] = None
    doi: Optional[str] = None


class Claim(BaseModel):
    paper_id: str
    paper_title: str
    claim: str
    confidence: float = 1.0


class CriticFeedback(BaseModel):
    verdict: str  # "continue" | "refine"
    reasoning: str
    missing_perspectives: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)


class ResearchState(TypedDict):
    """Shared mutable state threaded through the LangGraph graph."""

    # Input
    question: str

    # Planner output
    sub_queries: list[str]

    # Accumulated across search + reader calls (operator.add = list concatenation)
    papers: Annotated[list[dict], operator.add]
    claims: Annotated[list[dict], operator.add]

    # Critic control
    critic_feedback: Optional[dict]
    refinement_count: int

    # Synthesizer output
    review: Optional[str]
    citations: list[str]

    # Token usage — accumulated across all LLM calls via operator.add
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]

    # Runtime flags
    debug: bool
