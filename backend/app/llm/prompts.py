"""Loads versioned prompt files from the top-level prompts/ folder.

Format:
    ---
    version: 0.1.0
    ---
    <system prompt text>

The version is stored in every audit, so an old audit can always be traced
to the exact prompt that produced it.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.core.config import BACKEND_DIR

PROMPTS_DIR = BACKEND_DIR.parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str


@cache
def load_prompt(relative_path: str) -> Prompt:
    path = PROMPTS_DIR / relative_path
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path}: prompt must start with a '---' header")
    header, _, body = raw[4:].partition("\n---\n")
    fields = dict(line.split(":", 1) for line in header.splitlines() if ":" in line)
    version = fields.get("version", "").strip()
    if not version:
        raise ValueError(f"{path}: header must contain 'version:'")
    return Prompt(name=Path(relative_path).stem, version=version, text=body.strip())
