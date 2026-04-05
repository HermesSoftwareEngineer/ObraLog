from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RELATIVE_INSTRUCTIONS_PATH = "backend/agents/context/instructions.txt"


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_instructions_path() -> Path:
    raw_path = os.environ.get("AGENT_INSTRUCTIONS_FILE", DEFAULT_RELATIVE_INSTRUCTIONS_PATH).strip()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = get_project_root() / candidate
    return candidate


def read_agent_instructions() -> str:
    path = get_instructions_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_agent_instructions(content: str) -> Path:
    path = get_instructions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
