from __future__ import annotations

from textcad_agent.prompts import (
    CLARIFY_SYSTEM_PROMPT,
    DESIGN_SYSTEM_PROMPT,
    PHYSICS_REPORT_SYSTEM_PROMPT,
    VISUAL_SYSTEM_PROMPT,
    load_prompt,
)


def test_prompt_templates_load_from_resources():
    assert "需求澄清代理" in CLARIFY_SYSTEM_PROMPT
    assert "设计代理" in DESIGN_SYSTEM_PROMPT
    assert "力学分析报告代理" in PHYSICS_REPORT_SYSTEM_PROMPT
    assert "视觉审查代理" in VISUAL_SYSTEM_PROMPT
    assert "json" in CLARIFY_SYSTEM_PROMPT.lower()
    assert "json" in DESIGN_SYSTEM_PROMPT.lower()
    assert "json" in VISUAL_SYSTEM_PROMPT.lower()


def test_load_prompt_returns_named_template():
    prompt = load_prompt("design_system")
    assert "build_model" in prompt
    assert "工程审查报告" in load_prompt("physics_report_system")
