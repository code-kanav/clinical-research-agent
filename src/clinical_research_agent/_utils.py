from __future__ import annotations

import json
import re
from pathlib import Path


_PROMPTS_DIR = Path(__file__).parent / "prompts"


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
