from __future__ import annotations

"""Evaluation harness for the clinical research agent.

Usage:
    python evals/run.py                       # run all 10 questions
    python evals/run.py --question-id q01     # single question
    python evals/run.py --skip-faithfulness   # skip LLM judge (faster, no cost)
"""

import sys
import time
from pathlib import Path

import yaml

# Allow running as a script without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clinical_research_agent.config import get_settings
from clinical_research_agent.graph import graph
from clinical_research_agent.observability.tracing import setup_tracing

from evals.metrics import (
    QueryMetrics,
    compute_citation_accuracy,
    compute_faithfulness,
    compute_recency,
    estimate_cost,
)

_QUESTIONS_FILE = Path(__file__).parent / "questions.yaml"
_RESULTS_FILE = Path(__file__).parent / "results.md"


def _initial_state(question: str) -> dict:
    return {
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
        "debug": False,
    }


def run_question(q: dict, settings: object, skip_faithfulness: bool = False) -> QueryMetrics:
    from clinical_research_agent.config import Settings
    assert isinstance(settings, Settings)

    start = time.perf_counter()
    try:
        result = graph.invoke(_initial_state(q["question"]))
        latency = time.perf_counter() - start

        papers = list(result.get("papers") or [])
        review = str(result.get("review") or "")
        itok = int(result.get("input_tokens") or 0)
        otok = int(result.get("output_tokens") or 0)

        faithfulness = 0.0
        if not skip_faithfulness and review:
            faithfulness = compute_faithfulness(
                review,
                q.get("expected_themes") or [],
                settings.judge_model,
                settings.anthropic_api_key,
            )

        return QueryMetrics(
            question_id=q["id"],
            question=q["question"],
            papers_found=len(papers),
            claims_found=len(result.get("claims") or []),
            citation_accuracy=compute_citation_accuracy(papers),
            recency_3yr=compute_recency(papers, years=3),
            faithfulness=faithfulness,
            input_tokens=itok,
            output_tokens=otok,
            cost_usd=estimate_cost(itok, otok, settings.active_model()),
            latency_seconds=latency,
        )

    except Exception as exc:
        return QueryMetrics(
            question_id=q["id"],
            question=q["question"],
            error=str(exc),
            latency_seconds=time.perf_counter() - start,
        )


def _write_results_md(metrics: list[QueryMetrics], settings: object) -> None:
    from clinical_research_agent.config import Settings
    assert isinstance(settings, Settings)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Evaluation Results",
        "",
        f"Run: {now}  ",
        f"Model: `{settings.active_model()}` | Judge: `{settings.effective_judge_model()}`",
        "",
        "| id | question (truncated) | papers | claims | citation_acc | recency_3yr | faithfulness | cost_usd | latency_s | error |",
        "|----|----------------------|:------:|:------:|:------------:|:-----------:|:------------:|:--------:|:---------:|-------|",
    ]
    for m in metrics:
        q_short = m.question[:55].replace("|", "\\|") + ("…" if len(m.question) > 55 else "")
        err = (m.error or "")[:40].replace("|", "\\|")
        lines.append(
            f"| {m.question_id} | {q_short} | {m.papers_found} | {m.claims_found} "
            f"| {m.citation_accuracy:.2f} | {m.recency_3yr:.2f} | {m.faithfulness:.2f} "
            f"| ${m.cost_usd:.4f} | {m.latency_seconds:.1f} | {err} |"
        )

    ok = [m for m in metrics if not m.error]
    if ok:
        avg_faith = sum(m.faithfulness for m in ok) / len(ok)
        avg_rec = sum(m.recency_3yr for m in ok) / len(ok)
        avg_lat = sum(m.latency_seconds for m in ok) / len(ok)
        total_cost = sum(m.cost_usd for m in metrics)
        lines += [
            "",
            "## Summary",
            f"- Questions run: {len(metrics)} ({len(ok)} succeeded, {len(metrics)-len(ok)} failed)",
            f"- Avg faithfulness: {avg_faith:.2f}",
            f"- Avg recency (3yr): {avg_rec:.2f}",
            f"- Avg latency: {avg_lat:.1f}s",
            f"- Total cost: ${total_cost:.4f}",
        ]

    _RESULTS_FILE.write_text("\n".join(lines) + "\n")
    print(f"Results written to {_RESULTS_FILE}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run clinical research agent evaluation")
    parser.add_argument("--question-id", help="Run a single question by id (e.g. q01)")
    parser.add_argument("--skip-faithfulness", action="store_true", help="Skip LLM judge calls (faster)")
    args = parser.parse_args()

    setup_tracing()
    settings = get_settings()

    data = yaml.safe_load(_QUESTIONS_FILE.read_text())
    questions: list[dict] = data["questions"]

    if args.question_id:
        questions = [q for q in questions if q["id"] == args.question_id]
        if not questions:
            print(f"No question with id={args.question_id!r}")
            sys.exit(1)

    print(f"Running {len(questions)} question(s) | model={settings.active_model()} | skip_faithfulness={args.skip_faithfulness}")
    print("-" * 70)

    all_metrics: list[QueryMetrics] = []
    for q in questions:
        print(f"[{q['id']}] {q['question'][:65]}")
        m = run_question(q, settings, skip_faithfulness=args.skip_faithfulness)
        all_metrics.append(m)
        status = f"  → papers={m.papers_found} claims={m.claims_found} faith={m.faithfulness:.2f} cost=${m.cost_usd:.4f} lat={m.latency_seconds:.1f}s"
        if m.error:
            status = f"  → ERROR: {m.error[:60]}"
        print(status)

    _write_results_md(all_metrics, settings)

    ok = [m for m in all_metrics if not m.error]
    print("\n=== Summary ===")
    print(f"Completed: {len(ok)}/{len(all_metrics)}")
    if ok:
        print(f"Avg faithfulness : {sum(m.faithfulness for m in ok)/len(ok):.2f}")
        print(f"Avg recency (3yr): {sum(m.recency_3yr for m in ok)/len(ok):.2f}")
        print(f"Total cost       : ${sum(m.cost_usd for m in all_metrics):.4f}")
        print(f"Avg latency      : {sum(m.latency_seconds for m in ok)/len(ok):.1f}s")


# Import after sys.path manipulation
from datetime import datetime  # noqa: E402

if __name__ == "__main__":
    main()
