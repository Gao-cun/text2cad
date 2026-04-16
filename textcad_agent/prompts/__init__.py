from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (files(__name__) / f"{name}.txt").read_text(encoding="utf-8").strip()


CLARIFY_SYSTEM_PROMPT = load_prompt("clarify_system")
DESIGN_SYSTEM_PROMPT = load_prompt("design_system")
PHYSICS_REPORT_SYSTEM_PROMPT = load_prompt("physics_report_system")
VISUAL_SYSTEM_PROMPT = load_prompt("visual_system")

__all__ = [
    "CLARIFY_SYSTEM_PROMPT",
    "DESIGN_SYSTEM_PROMPT",
    "PHYSICS_REPORT_SYSTEM_PROMPT",
    "VISUAL_SYSTEM_PROMPT",
    "load_prompt",
]
