from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
from functools import lru_cache
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROMPT_PATH = BASE_DIR / "prompts" / "nutrition_system.json"

def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")

@lru_cache(maxsize=8)
def load_prompt(path_str: str | None = None) -> Dict[str, Any]:

    path = Path(path_str or os.getenv("PROMPT_PATH", str(DEFAULT_PROMPT_PATH)))
    data = _read_json(path)

    if data.get("role") != "system":
        raise ValueError(f"'role' must be 'system' in {path}")
    if not isinstance(data.get("content"), str) or not data["content"].strip():
        raise ValueError(f"'content' must be a non-empty string in {path}")
    return data

def render_system_content(vars: Dict[str, Any]) -> str:
    from collections import defaultdict
    prompt = load_prompt()
    content = prompt["content"]
    safe_vars = defaultdict(str, **{k: "" if v is None else str(v) for k, v in vars.items()})
    return content.format_map(safe_vars)
