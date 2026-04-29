#!/usr/bin/env python3
from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from clinical_research_agent.graph import graph
from clinical_research_agent.observability.tracing import setup_tracing

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def _cmd(
    question: str = typer.Argument(..., help="Clinical research question to investigate"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Stream live agent progress"),
) -> None:
    # Flush stdout immediately so agent prints appear as they happen.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    setup_tracing()

    initial_state = {
        "question": question,
        "sub_queries": [],
        "papers": [],
        "claims": [],
        "critic_feedback": None,
        "refinement_count": 0,
        "review": None,
        "citations": [],
        "input_tokens": 0,
        "output_tokens": 0,
        "debug": debug,
    }

    console.print(Panel(Text(question, style="bold"), title="Clinical Research Agent", border_style="blue"))

    try:
        # stream(stream_mode="values") yields the full merged state after each node,
        # so agents can print their own debug lines inline; last chunk is final state.
        result = None
        for result in graph.stream(initial_state, stream_mode="values"):
            pass
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}", style="bold")
        sys.exit(1)

    if result is None:
        console.print("[red]Graph produced no output.[/red]")
        sys.exit(1)

    if debug:
        console.rule("Summary")
        console.print(f"[bold]Sub-queries:[/bold] {result['sub_queries']}")
        console.print(f"[bold]Papers found:[/bold] {len(result['papers'])}")
        console.print(f"[bold]Claims extracted:[/bold] {len(result['claims'])}")
        console.print(f"[bold]Refinement cycles:[/bold] {result['refinement_count']}")
        itok, otok = result.get("input_tokens", 0), result.get("output_tokens", 0)
        if itok or otok:
            console.print(f"[bold]Tokens:[/bold] in={itok} out={otok}")
        console.rule()

    review = result.get("review") or "No review generated."
    console.print(Panel(review, title="Literature Review", border_style="green"))

    citations = result.get("citations") or []
    if citations:
        console.print("\n[bold]References[/bold]")
        for c in citations:
            console.print(f"  {c}")


def main() -> None:
    app()
