from __future__ import annotations

import json
from typing import Any, Callable


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def build_clarify_request(prompt: str, feedback_history: list[str], schema_hint: Callable[[str], str]) -> str:
    return (
        f"原始需求：{prompt}\n"
        f"历史反馈：{feedback_history}\n"
        f"{schema_hint('ClarifiedSpec')}\n"
        "请先理解自由文本需求，再补全设计意图、尺寸、视觉要求、边界盒、载荷向量和必要假设。"
    )


def build_physics_report_request(
    clarified_spec: dict[str, Any],
    fea_results: dict[str, Any],
    physics_review: dict[str, Any],
) -> str:
    return (
        f"澄清规格：{clarified_spec}\n"
        f"有限元摘要：{fea_results}\n"
        f"物理审查结果：{physics_review}\n"
        "请输出一段简洁工程报告，用于指导下一轮几何修复。"
    )


def build_visual_review_request(
    prompt: str,
    clarified_spec: dict[str, Any],
    feedback_history: list[str],
    schema_hint: Callable[[str], str],
) -> str:
    return (
        f"{schema_hint('VisualReview')}\n"
        "结合原始需求、澄清规格和渲染图，判断几何语义是否满足要求。"
        f"\n原始需求：{prompt}"
        f"\n澄清规格：{clarified_spec}"
        f"\n历史反馈：{feedback_history}"
    )


def build_engineering_prompt(prompt: str, clarified_spec: dict[str, Any]) -> str:
    spec = dict(clarified_spec)
    spec.pop("backend_config", None)
    goals = _to_string_list(spec.get("design_goals"))
    styles = _to_string_list(spec.get("style_keywords"))
    assumptions = _to_string_list(spec.get("assumptions"))
    visual_requirements = _to_string_list(spec.get("visual_requirements"))
    length_mm = float(spec.get("length_mm") or 0.0)
    width_mm = float(spec.get("width_mm") or 0.0)
    height_mm = float(spec.get("height_mm") or 0.0)
    load_vector = spec.get("load_vector_n") or [0.0, -1.0, 0.0]
    fixed_boundary = spec.get("fixed_boundary") or []
    load_boundary = spec.get("load_boundary") or []
    return (
        "工程基线说明\n"
        f"- 原始需求：{prompt}\n"
        f"- 设计摘要：{spec.get('design_brief') or spec.get('request_summary') or prompt}\n"
        f"- 对象类型：{spec.get('object_type') or 'generic_printable_object'}\n"
        f"- 目标尺寸（mm）：长 {length_mm:.2f}，宽 {width_mm:.2f}，高 {height_mm:.2f}\n"
        f"- 材料：{spec.get('material_name') or 'PLA'}，杨氏模量 {float(spec.get('material_young_mpa') or 3500.0):.2f} MPa，泊松比 {float(spec.get('material_poisson') or 0.36):.2f}\n"
        f"- 固定边界盒：{fixed_boundary}\n"
        f"- 加载边界盒：{load_boundary}\n"
        f"- 试探载荷向量（N）：{load_vector}\n"
        f"- 设计目标：{'; '.join(goals) if goals else '满足用户核心用途并可打印'}\n"
        f"- 风格关键词：{', '.join(styles) if styles else 'printable, clean'}\n"
        f"- 视觉要求：{'; '.join(visual_requirements) if visual_requirements else prompt}\n"
        f"- 默认假设：{'; '.join(assumptions) if assumptions else '无'}\n"
        "- 执行说明：以上边界盒、试探载荷和材料参数是当前求解后端的默认分析上下文，不是造型本身的唯一解；若你为了更符合真实物体语义而调整几何，请在 self_check_notes 中说明。\n"
        "- 约束：必须生成可执行的 CadQuery 代码，几何应可网格化、可渲染、可进入后续力学和视觉审查。\n"
    )


def build_design_request(
    *,
    prompt: str,
    engineering_prompt: str,
    latest_revision_brief: str,
    previous_code: str = "",
    structured_revision: dict[str, Any] | None = None,
    repair_mode: bool = False,
    schema_hint: Callable[[str], str],
) -> str:
    structured_revision = structured_revision or {}
    if repair_mode:
        sections = [
            "Repair Mode\n"
            "You are repairing an existing CadQuery model.\n\n"
            "Hard constraints:\n"
            "1. Preserve the overall object category and topology.\n"
            "2. Do not remove existing primary parts unless explicitly instructed.\n"
            "3. Do not create detached or floating components.\n"
            "4. Prefer parameter changes over structural rewrites.\n"
            "5. Only modify the minimum necessary code blocks.\n"
            "6. Preserve correct existing components such as base plate, back support, front lip, holes, ribs, and main body.\n"
            "7. If the previous model is mostly correct, keep it and make small repairs.\n"
            "8. Do not redesign from scratch.\n"
            "9. Do not change the coordinate system unless necessary.\n"
            "10. Do not replace the entire modeling strategy unless the previous code cannot compile.",
            f"Original engineering prompt:\n{engineering_prompt.strip()}",
            f"Previous CadQuery code:\n```python\n{previous_code}\n```",
            "Structured defects:\n"
            f"{json.dumps(structured_revision.get('must_fix', []), ensure_ascii=False, indent=2)}",
            "Preserve components:\n"
            f"{json.dumps(structured_revision.get('must_preserve', []), ensure_ascii=False, indent=2)}",
            "Forbidden actions:\n"
            f"{json.dumps(structured_revision.get('forbidden_actions', []), ensure_ascii=False, indent=2)}",
            "Allowed repair actions:\n"
            f"{json.dumps(structured_revision.get('allowed_actions', []), ensure_ascii=False, indent=2)}",
            "Latest physics report:\n"
            f"{json.dumps(structured_revision.get('physics_constraints', []), ensure_ascii=False, indent=2)}",
            "Latest visual review / structured revision:\n"
            f"{json.dumps(structured_revision.get('visual_constraints', []), ensure_ascii=False, indent=2)}",
            f"Latest revision brief:\n{latest_revision_brief or 'No natural-language brief; rely on structured defects.'}",
            "Task:\n"
            "Return the repaired complete CadQuery code, but make the minimum necessary changes.",
        ]
    else:
        sections = [
            "Generate Mode\n"
            "You are generating a CadQuery model from scratch according to the engineering specification.\n"
            "Return complete executable CadQuery code.",
            engineering_prompt.strip(),
            "实现边界与优先级\n"
            "- 必须输出可执行 CadQuery 代码，并保留 build_model()/build()/make_model() 或 MODEL/model 入口。\n"
            "- 不要退化成无语义方块，除非用户需求本身就是简单实体。\n"
            "- analysis_config 主要服务当前后端执行；如果你认为几何语义需要微调其中的分析假设，可以调整，但必须在 self_check_notes 里说明原因。\n",
        ]
        if latest_revision_brief:
            sections.append(f"本轮修复摘要\n{latest_revision_brief}")
        else:
            sections.append("本轮修复摘要\n首轮生成，请直接根据工程基线构建满足需求的 3D 打印模型。")
    sections.append(
        "输出要求\n"
        f"{schema_hint('DesignPayload')}\n"
        "self_check_notes 中必须说明本轮修改点、仍未满足项和任何阻碍。\n"
        f"原始需求参考：{prompt}"
    )
    return "\n\n".join(section.strip() for section in sections if section and section.strip())
