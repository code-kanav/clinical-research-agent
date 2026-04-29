from __future__ import annotations

import json
import re
import time
from pathlib import Path
from threading import Lock

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# 10 LLM calls/min = 1 per 6 s; shared across all agents.
_llm_rate_lock = Lock()
_llm_rate_last: float = 0.0
_LLM_MIN_INTERVAL = 0.0  # no rate limiting


def llm_wait() -> None:
    """Block until 6 s have elapsed since the last LLM call."""
    global _llm_rate_last
    with _llm_rate_lock:
        elapsed = time.monotonic() - _llm_rate_last
        remaining = _LLM_MIN_INTERVAL - elapsed
        if remaining > 0:
            time.sleep(remaining)
        _llm_rate_last = time.monotonic()


def load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.txt").read_text()


def format_prompt(template: str, **kwargs: str | int) -> str:
    """Substitute {key} placeholders without touching other curly braces (e.g. JSON examples)."""
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template


def parse_json_response(text: str) -> dict:
    """Parse JSON from an LLM response, stripping markdown code fences if present."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)  # type: ignore[no-any-return]
