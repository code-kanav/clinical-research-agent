from __future__ import annotations

import os


def setup_tracing() -> None:
    """Enable LangSmith tracing when LANGCHAIN_API_KEY is present in env.

    No-op if the key is absent — safe to call unconditionally.
    Set LANGCHAIN_PROJECT to namespace traces (default: clinical-research-agent).
    """
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    if not api_key:
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "clinical-research-agent")
