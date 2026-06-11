from __future__ import annotations

import difflib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Literal

from langgraph.types import Command, interrupt

from .state import (
    AgentState,
    AnalysisConfig,
    ClarifiedSpec,
    CompileStatus,
    DesignStatus,
    DesignPayload,
    PhysicsReview,
    VisualReview,
)
from .tools import build_cad, build_mesh, materialize_workspace, persist_iteration_artifacts, render_views, solve_fea
from .validation import collect_static_validation_result

DEFAULT_ALLOWED_REPAIR_ACTIONS = [
    "adjust_dimensions",
    "adjust_thickness",
    "adjust_angle",
    "adjust_position",
    "add_support_ribs",
    "add_or_adjust_chamfers_fillets",
    "strengthen_connections",
    "fix_cadquery_api_or_syntax",
    "fix_printability_issues",
]

DEFAULT_FORBIDDEN_REPAIR_ACTIONS = [
    "do_not_delete_base_or_main_body",
    "do_not_delete_main_support_surface",
    "do_not_change_object_category",
    "do_not_create_detached_or_floating_parts",
    "do_not_ignore_previous_code",
    "do_not_rewrite_all_geometry_when_local_repair_is_sufficient",
]

BAD_GEOMETRY_KEYWORDS = (
    "detached",
    "floating",
    "missing base",
    "missing main support",
    "main component",
    "category changed",
    "wrong object",
    "悬空",
    "脱离",
    "缺少底座",
    "缺少主体",
    "类别错误",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _state_float(state: AgentState, name: str, default: float) -> float:
    try:
        return float(state.get(name, default))
    except (TypeError, ValueError):
        return default


def _state_int(state: AgentState, name: str, default: int) -> int:
    try:
        return int(state.get(name, default))
    except (TypeError, ValueError):
        return default


def _clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _code_change_ratio(previous_code: str, current_code: str) -> float:
    if not previous_code and not current_code:
        return 0.0
    if not previous_code or not current_code:
        return 1.0
    similarity = difflib.SequenceMatcher(None, previous_code, current_code).ratio()
    return max(0.0, min(1.0, 1.0 - similarity))


def _merge_logs(state: AgentState, stage: str, content: str) -> dict[str, str]:
    merged = dict(state.get("tool_logs", {}))
    merged[stage] = content
    return merged


def _append_feedback(state: AgentState, message: str) -> list[str]:
    feedback = list(state.get("feedback_history", []))
    if message:
        feedback.append(message)
    return feedback


def _merge_review_artifacts(state: AgentState, **updates: Any) -> dict[str, Any]:
    merged = dict(state.get("review_artifacts", {}))
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged


def _normalized_code_signature(code: str) -> str:
    return "\n".join(line.strip() for line in code.splitlines() if line.strip())


def _visual_text_blob(visual_review: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("issues", "missing_requirements", "recommended_edits", "preserve_components", "forbidden_repairs"):
        value = visual_review.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    for defect in visual_review.get("defects") or []:
        if isinstance(defect, dict):
            parts.extend(str(defect.get(key, "")) for key in ("component", "issue", "repair_action"))
    return " ".join(parts).lower()


def _structured_defects_from_visual(visual_review: dict[str, Any]) -> list[dict[str, Any]]:
    defects = visual_review.get("defects")
    if isinstance(defects, list) and defects:
        return [item for item in defects if isinstance(item, dict)]

    extracted: list[dict[str, Any]] = []
    raw_items: list[str] = []
    for key in ("issues", "missing_requirements", "recommended_edits"):
        value = visual_review.get(key)
        if isinstance(value, list):
            raw_items.extend(str(item) for item in value if str(item).strip())
    for item in raw_items:
        lowered = item.lower()
        component = "unknown"
        if "base" in lowered or "底座" in item:
            component = "base"
        elif "support" in lowered or "支撑" in item:
            component = "support"
        elif "lip" in lowered or "挡边" in item:
            component = "front_lip"
        elif "rib" in lowered or "加强" in item:
            component = "rib"
        extracted.append(
            {
                "component": component,
                "issue": item,
                "severity": 2,
                "repair_action": item,
                "target_parameter": None,
                "suggested_change": None,
            }
        )
    return extracted


def build_structured_revision(state: AgentState) -> dict[str, Any]:
    visual_review = state.get("visual_review", {}) or {}
    physics_review = state.get("physics_review", {}) or {}
    iteration = int(state.get("iteration", 1) or 1)

    visual_defects = _structured_defects_from_visual(visual_review)
    physics_constraints: list[str] = []
    for key in ("violations", "recommended_edits"):
        value = physics_review.get(key)
        if isinstance(value, list):
            physics_constraints.extend(str(item) for item in value if str(item).strip())
    if state.get("physics_report"):
        physics_constraints.append(str(state["physics_report"]))

    must_fix: list[dict[str, Any]] = list(visual_defects)
    for item in physics_constraints:
        must_fix.append(
            {
                "component": "structure",
                "issue": item,
                "severity": 2,
                "repair_action": item,
                "target_parameter": None,
                "suggested_change": None,
            }
        )

    preserve_components = [
        str(item)
        for item in (visual_review.get("preserve_components") or [])
        if str(item).strip()
    ]
    forbidden = [
        str(item)
        for item in (visual_review.get("forbidden_repairs") or [])
        if str(item).strip()
    ]
    for item in DEFAULT_FORBIDDEN_REPAIR_ACTIONS:
        if item not in forbidden:
            forbidden.append(item)

    return {
        "mode": "repair" if iteration >= 2 else "generate",
        "must_preserve": preserve_components,
        "must_fix": must_fix,
        "allowed_actions": list(DEFAULT_ALLOWED_REPAIR_ACTIONS),
        "forbidden_actions": forbidden,
        "minimal_change_required": iteration >= 2,
        "physics_constraints": physics_constraints,
        "visual_constraints": visual_defects,
    }


def _compose_revision_brief(state: AgentState) -> str:
    parts: list[str] = []

    design_status = state.get("design_status", {})
    if design_status.get("state") == "failed":
        message = design_status.get("error_message") or "设计模型调用或解析失败。"
        parts.append(f"设计生成失败：{message}")
    elif design_status.get("state") == "unchanged_after_failed_review":
        message = design_status.get("error_message") or "收到审查反馈后代码未发生变化。"
        parts.append(f"设计修复未生效：{message}")

    compile_status = state.get("compile_status", {})
    if compile_status and not compile_status.get("success", True):
        stage = compile_status.get("stage", "unknown")
        error = compile_status.get("error_message", "unknown error")
        parts.append(f"工具执行失败（{stage}）：{error}")

    physics_review = state.get("physics_review", {})
    if physics_review and not physics_review.get("pass", True):
        physics_report = (state.get("physics_report") or "").strip()
        if physics_report:
            parts.append(f"力学分析报告：{physics_report}")
        else:
            violations = physics_review.get("violations", [])
            recommendations = physics_review.get("recommended_edits", [])
            parts.append("物理审查未通过：" + "；".join(violations + recommendations))

    visual_review = state.get("visual_review", {})
    if visual_review and not visual_review.get("pass", True):
        defects = _structured_defects_from_visual(visual_review)
        issues = visual_review.get("issues", []) + visual_review.get("missing_requirements", [])
        recommendations = visual_review.get("recommended_edits", [])
        if defects:
            defect_lines = [
                f"{item.get('component', 'unknown')}：{item.get('issue', '')} -> {item.get('repair_action', '')}"
                for item in defects
            ]
            issues = issues + defect_lines
        parts.append("视觉审查未通过：" + "；".join(issues + recommendations))

    return "\n".join(part for part in parts if part).strip()


def _read_render_dimensions(workspace_path: str) -> dict[str, float]:
    if not workspace_path:
        return {}
    path = Path(workspace_path) / "renders" / "render_scale.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    dims = data.get("dimensions_mm") or data.get("dimensions") or {}
    if not isinstance(dims, dict):
        return {}
    result: dict[str, float] = {}
    for key in ("x", "y", "z"):
        try:
            result[key] = float(dims[key])
        except (KeyError, TypeError, ValueError):
            continue
    return result


def compute_quality_score(state: AgentState, runtime: Any | None = None) -> dict[str, Any]:
    compile_status = state.get("compile_status", {}) or {}
    visual_review = state.get("visual_review", {}) or {}
    physics_review = state.get("physics_review", {}) or {}
    workspace_path = state.get("workspace_path", "") or ""
    step_path = Path(workspace_path) / "model.step" if workspace_path else None
    stl_path = Path(workspace_path) / "model.stl" if workspace_path else None
    has_step_stl = bool(step_path and step_path.exists() and stl_path and stl_path.exists())

    penalties: list[str] = []
    reasons: list[str] = []

    if compile_status.get("success") and has_step_stl:
        compile_score = 1.0
        reasons.append("CAD build exported STEP/STL.")
    elif compile_status.get("success"):
        compile_score = 0.3
        reasons.append("Static/tool stage passed but final STEP/STL was not available.")
    else:
        compile_score = 0.0 if compile_status.get("stage") == "static_validate" else 0.3
        penalties.append("build_failed")
        reasons.append(str(compile_status.get("error_message") or "Build/static validation failed."))

    numeric_visual = [
        visual_review.get("semantic_score"),
        visual_review.get("geometry_score"),
        visual_review.get("printability_score"),
    ]
    numeric_visual_scores = [float(item) for item in numeric_visual if isinstance(item, (int, float))]
    if numeric_visual_scores:
        visual_score = sum(_clamp_score(item) for item in numeric_visual_scores) / len(numeric_visual_scores)
    elif visual_review.get("pass") is True:
        visual_score = 1.0
    elif visual_review.get("object_present") is True or visual_review.get("is_present") is True:
        visual_score = 0.6
    elif visual_review.get("object_present") is False or visual_review.get("is_present") is False:
        visual_score = 0.2
    else:
        visual_score = 0.7 if not visual_review else 0.4
    if visual_review.get("is_present") is True or visual_review.get("object_present") is True:
        visual_score = max(visual_score, 0.6)

    geometry_score = _clamp_score(visual_review.get("geometry_score"), default=0.8 if has_step_stl else 0.2)
    dims = _read_render_dimensions(workspace_path)
    if dims:
        values = [value for value in dims.values() if value > 0]
        if not values:
            geometry_score = min(geometry_score, 0.1)
            penalties.append("empty_or_zero_dimension_model")
        elif max(values) / max(min(values), 1e-6) > 25.0:
            geometry_score = min(geometry_score, 0.45)
            penalties.append("model_dimensions_extremely_abnormal")
        elif max(values) > 1000.0 or min(values) < 0.5:
            geometry_score = min(geometry_score, 0.5)
            penalties.append("model_dimensions_extremely_abnormal")

    blob = _visual_text_blob(visual_review)
    for keyword in BAD_GEOMETRY_KEYWORDS:
        if keyword in blob:
            geometry_score = min(geometry_score, 0.45)
            penalties.append(keyword.replace(" ", "_"))

    max_disp = physics_review.get("max_disp_mm")
    limit = float(getattr(runtime, "displacement_limit_mm", 5.0))
    if physics_review.get("pass") is True:
        physics_score = 1.0
    elif isinstance(max_disp, (int, float)):
        if max_disp <= limit:
            physics_score = 1.0
        else:
            physics_score = max(0.1, 1.0 - min(0.9, (float(max_disp) - limit) / max(limit, 1e-6)))
    elif state.get("fea_results", {}).get("max_disp_mm") is not None:
        physics_score = 0.7
    else:
        physics_score = 0.7

    design_status = state.get("design_status", {}) or {}
    if design_status.get("code_changed") is False and state.get("latest_revision_brief"):
        penalties.append("generated_code_unchanged_while_repair_needed")
    if design_status.get("large_rewrite"):
        penalties.append("large_rewrite_in_repair_mode")

    penalty_value = min(0.5, 0.08 * len(set(penalties)))
    score = (
        0.30 * compile_score
        + 0.35 * visual_score
        + 0.15 * geometry_score
        + 0.20 * physics_score
        - penalty_value
    )
    score = _clamp_score(score)
    return {
        "iteration": state.get("iteration", 1),
        "score": score,
        "compile_score": _clamp_score(compile_score),
        "visual_score": _clamp_score(visual_score),
        "geometry_score": _clamp_score(geometry_score),
        "physics_score": _clamp_score(physics_score),
        "penalty_value": penalty_value,
        "penalties": sorted(set(penalties)),
        "reasons": reasons,
        "change_ratio": design_status.get("change_ratio"),
        "repair_mode": bool(state.get("repair_mode", False)),
    }


def _plane_x_from_bbox(bbox: list[float]) -> float:
    return float((bbox[0] + bbox[3]) / 2.0)


def _collect_static_validation_errors(code: str) -> list[str]:
    return collect_static_validation_result(code).errors


def make_ingest_request_node():
    def ingest_request(state: AgentState) -> dict[str, Any]:
        return {
            "run_id": uuid.uuid4().hex[:10],
            "iteration": 1,
            "compile_retry_count": 0,
            "token_usage": {},
            "feedback_history": [],
            "tool_logs": {},
            "vtk_paths": [],
            "assumptions": [],
            "engineering_prompt": "",
            "design_request": "",
            "latest_revision_brief": "",
            "structured_revision": {},
            "physics_report": "",
            "review_artifacts": {},
            "design_status": DesignStatus().model_dump(),
            "pipeline_phase": "clarifying",
            "best_iteration": None,
            "best_score": None,
            "best_code": None,
            "best_run_dir": None,
            "best_model_step": None,
            "best_model_stl": None,
            "best_visual_review": None,
            "best_physics_review": None,
            "best_compile_status": None,
            "best_quality_report": None,
            "no_improvement_count": 0,
            "quality_history": [],
            "repair_mode": False,
            "stop_reason": "",
            "final_iteration": None,
            "final_score": None,
            "returned_model_source": "",
            "latest_model_step": "",
            "latest_model_stl": "",
            "final_status": "running",
        }

    return ingest_request


def make_clarify_spec_node(runtime):
    def clarify_spec(state: AgentState) -> Command[Literal["await_user_clarification", "engineer_spec"]]:
        spec = runtime.clarify(state["user_prompt"], state.get("feedback_history", []))
        spec_dict = spec.model_dump()
        engineering_prompt = runtime.build_engineering_prompt(state["user_prompt"], spec_dict)
        update = {
            "clarified_spec": spec_dict,
            "engineering_prompt": engineering_prompt,
            "assumptions": spec.assumptions,
            "token_usage": runtime.token_usage_snapshot(),
            "clarification_request": {
                "missing_fields": spec.missing_high_risk_fields,
                "assumptions": spec.assumptions,
            },
        }
        if spec.missing_high_risk_fields:
            update["final_status"] = "awaiting_user"
            update["pipeline_phase"] = "clarifying"
            return Command(update=update, goto="await_user_clarification")

        update["final_status"] = "running"
        update["pipeline_phase"] = "generating"
        return Command(update=update, goto="engineer_spec")

    return clarify_spec


def make_await_user_clarification_node(runtime):
    def await_user_clarification(
        state: AgentState,
    ) -> Command[Literal["engineer_spec"]]:
        payload = {
            "message": "请补充高风险工程参数后继续。",
            "missing_fields": state.get("clarification_request", {}).get("missing_fields", []),
            "current_spec": state.get("clarified_spec", {}),
        }
        response = interrupt(payload)
        updated = dict(state["clarified_spec"])
        if isinstance(response, dict):
            updated.update(response)
        updated["missing_high_risk_fields"] = []
        spec = ClarifiedSpec.model_validate(updated)
        return Command(
            update={
                "clarified_spec": spec.model_dump(),
                "engineering_prompt": runtime.build_engineering_prompt(
                    state.get("user_prompt", spec.request_summary),
                    spec.model_dump(),
                ),
                "assumptions": spec.assumptions,
                "clarification_request": {},
                "pipeline_phase": "generating",
                "final_status": "running",
            },
            goto="engineer_spec",
        )

    return await_user_clarification


def make_engineer_spec_node():
    def engineer_spec(state: AgentState) -> dict[str, Any]:
        spec = ClarifiedSpec.model_validate(state["clarified_spec"])
        backend = AnalysisConfig.from_clarified_spec(spec)
        spec_dict = spec.model_dump()
        spec_dict["backend_config"] = backend.model_dump()
        return {
            "clarified_spec": spec_dict,
            "assumptions": spec.assumptions,
            "pipeline_phase": "generating",
        }

    return engineer_spec


def make_design_generate_node(runtime):
    def design_generate(state: AgentState) -> dict[str, Any]:
        prev_code = state.get("design_payload", {}).get("cadquery_code", "")
        repair_mode = bool(state.get("iteration", 1) >= 2 and _env_bool("TEXTCAD_ENABLE_CONSERVATIVE_REPAIR", True))
        engineering_prompt = state.get("engineering_prompt") or runtime.build_engineering_prompt(
            state["user_prompt"], state["clarified_spec"]
        )
        latest_revision_brief = state.get("latest_revision_brief", "")
        design_request = runtime.build_design_request(
            prompt=state["user_prompt"],
            engineering_prompt=engineering_prompt,
            clarified_spec=state["clarified_spec"],
            latest_revision_brief=latest_revision_brief,
            previous_code=prev_code,
            structured_revision=state.get("structured_revision", {}),
            repair_mode=repair_mode,
        )
        feedback_for_design = [latest_revision_brief] if latest_revision_brief else list(state.get("feedback_history", []))

        logs = _merge_logs(
            state,
            "design_generate_prompt_shape",
            (
                f"engineering_prompt={bool(engineering_prompt)} "
                f"previous_code={bool(prev_code)} "
                f"latest_revision_brief={bool(latest_revision_brief)}"
            ),
        )
        try:
            payload = runtime.design(
                state["user_prompt"],
                state["clarified_spec"],
                feedback_for_design,
                prev_code,
                engineering_prompt=engineering_prompt,
                latest_revision_brief=latest_revision_brief,
                structured_revision=state.get("structured_revision", {}),
                repair_mode=repair_mode,
            )
        except Exception as exc:
            status = DesignStatus(
                state="failed",
                error_message=str(exc),
                code_changed=None,
                used_model=True,
            )
            compile_status = CompileStatus(stage="design_generate", success=False, error_message=str(exc))
            logs["design_generate"] = f"design_generate: failed — {exc}"
            return {
                "design_request": design_request,
                "design_status": status.model_dump(),
                "compile_status": compile_status.model_dump(),
                "token_usage": runtime.token_usage_snapshot(),
                "pipeline_phase": "failed",
                "tool_logs": logs,
            }

        payload_dict = payload.model_dump()
        notes = payload_dict.get("self_check_notes", [])
        used_model = not any("heuristic fallback used" in str(note).lower() for note in notes)
        current_code = payload_dict["cadquery_code"]
        code_changed = True if not prev_code else (
            _normalized_code_signature(prev_code) != _normalized_code_signature(current_code)
        )
        change_ratio = _code_change_ratio(prev_code, current_code) if prev_code else 1.0
        max_change_ratio = _env_float("TEXTCAD_REPAIR_MAX_CHANGE_RATIO", 0.60)
        large_rewrite = bool(repair_mode and change_ratio > max_change_ratio)

        if prev_code and latest_revision_brief and not code_changed:
            status = DesignStatus(
                state="unchanged_after_feedback",
                error_message="收到上一轮审查反馈后，生成代码没有发生实质变化；将由质量门控决定是否接受保守不变结果。",
                code_changed=False,
                change_ratio=change_ratio,
                large_rewrite=False,
                used_model=used_model,
            )
            logs["design_generate"] = "design_generate: unchanged_after_feedback"
            return {
                "design_payload": payload_dict,
                "design_request": design_request,
                "design_status": status.model_dump(),
                "token_usage": runtime.token_usage_snapshot(),
                "repair_mode": repair_mode,
                "pipeline_phase": "generating",
                "tool_logs": logs,
            }

        status_value = "model_ok" if used_model else "heuristic_fallback"
        status = DesignStatus(
            state=status_value,
            error_message=None,
            code_changed=code_changed,
            change_ratio=change_ratio,
            large_rewrite=large_rewrite,
            used_model=used_model,
        )
        if used_model:
            log_entry = "design_generate: model ok"
        else:
            log_entry = "design_generate: heuristic fallback — " + "; ".join(notes)
        logs["design_generate"] = log_entry
        return {
            "design_payload": payload_dict,
            "design_request": design_request,
            "design_status": status.model_dump(),
            "compile_retry_count": state.get("compile_retry_count", 0),
            "token_usage": runtime.token_usage_snapshot(),
            "repair_mode": repair_mode,
            "compile_status": {},
            "workspace_path": "",
            "fea_results": {},
            "image_paths": [],
            "visual_review": {},
            "physics_review": {},
            "physics_report": "",
            "latest_revision_brief": "",
            "review_artifacts": {},
            "pipeline_phase": "generating",
            "tool_logs": logs,
        }

    return design_generate


def make_static_validate_node():
    def static_validate(
        state: AgentState,
    ) -> Command[Literal["materialize_workspace", "quality_gate"]]:
        design_status = state.get("design_status", {})
        if design_status.get("state") in {"failed"}:
            compile_status = state.get("compile_status", {})
            message = compile_status.get("error_message") or design_status.get("error_message") or "Design generation failed."
            return Command(
                update={
                    "compile_status": {
                        "stage": compile_status.get("stage", "design_generate"),
                        "success": False,
                        "syntax_ok": compile_status.get("syntax_ok", True),
                        "security_ok": compile_status.get("security_ok", True),
                        "error_message": message,
                    },
                    "tool_logs": _merge_logs(state, "static_validate", f"Skipped static validation: {message}"),
                    "pipeline_phase": "revising",
                },
                goto="quality_gate",
            )

        if "design_payload" not in state:
            message = "design_payload 缺失，无法进入静态校验。"
            return Command(
                update={
                    "compile_status": CompileStatus(
                        stage="static_validate",
                        success=False,
                        error_message=message,
                    ).model_dump(),
                    "tool_logs": _merge_logs(state, "static_validate", message),
                    "pipeline_phase": "revising",
                },
                goto="quality_gate",
            )

        payload = DesignPayload.model_validate(state["design_payload"])
        validation = collect_static_validation_result(payload.cadquery_code)
        if validation.errors:
            status = CompileStatus(
                stage="static_validate",
                success=False,
                syntax_ok=validation.syntax_ok,
                security_ok=validation.security_ok,
                error_message="；".join(validation.errors),
            )
            return Command(
                update={
                    "compile_status": status.model_dump(),
                    "tool_logs": _merge_logs(state, "static_validate", status.error_message or ""),
                    "pipeline_phase": "revising",
                },
                goto="quality_gate",
            )

        status = CompileStatus(stage="static_validate", success=True)
        return Command(
            update={
                "compile_status": status.model_dump(),
                "tool_logs": _merge_logs(state, "static_validate", "Static validation passed."),
                "pipeline_phase": "generating",
            },
            goto="materialize_workspace",
        )

    return static_validate


def make_materialize_workspace_node():
    def materialize_workspace_node(state: AgentState) -> dict[str, Any]:
        result = materialize_workspace.invoke(
            {
                "run_id": state["run_id"],
                "iteration": state["iteration"],
                "design_payload": state["design_payload"],
                "clarified_spec": state["clarified_spec"],
                "engineering_prompt": state.get("engineering_prompt", ""),
                "latest_revision_brief": state.get("latest_revision_brief", ""),
                "physics_report": state.get("physics_report", ""),
                "design_request": state.get("design_request", ""),
                "physics_review": state.get("physics_review", {}),
                "visual_review": state.get("visual_review", {}),
            }
        )
        return {
            "workspace_path": result["workspace_path"],
            "pipeline_phase": "generating",
            "tool_logs": _merge_logs(state, "materialize_workspace", str(result)),
        }

    return materialize_workspace_node


def make_build_cad_node():
    def build_cad_node(state: AgentState) -> Command[Literal["build_mesh", "quality_gate"]]:
        try:
            result = build_cad.invoke({"workspace_path": state["workspace_path"]})
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="build_cad", success=False, error_message=str(exc))
            return Command(
                update={
                    "compile_status": status.model_dump(),
                    "pipeline_phase": "revising",
                    "tool_logs": _merge_logs(state, "build_cad", str(exc)),
                },
                goto="quality_gate",
            )

        status = CompileStatus(stage="build_cad", success=True)
        log = "\n".join(item for item in [result.get("stdout", ""), result.get("stderr", "")] if item).strip()
        return Command(
            update={
                "compile_status": status.model_dump(),
                "pipeline_phase": "generating",
                "tool_logs": _merge_logs(state, "build_cad", log or "build_cad completed."),
            },
            goto="build_mesh",
        )

    return build_cad_node


def make_build_mesh_node():
    def build_mesh_node(state: AgentState) -> dict[str, Any]:
        try:
            result = build_mesh.invoke({"workspace_path": state["workspace_path"]})
            status = CompileStatus(stage="build_mesh", success=True)
            log = "\n".join(item for item in [result.get("stdout", ""), result.get("stderr", "")] if item).strip()
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="build_mesh", success=False, error_message=str(exc))
            log = str(exc)
        return {
            "compile_status": status.model_dump(),
            "pipeline_phase": "generating" if status.success else "revising",
            "tool_logs": _merge_logs(state, "build_mesh", log),
        }

    return build_mesh_node


def make_solve_fea_node():
    def solve_fea_node(state: AgentState) -> dict[str, Any]:
        if not state.get("compile_status", {}).get("success", False):
            failure_message = state.get("compile_status", {}).get("error_message", "Mesh build failed.")
            return {
                "fea_results": {},
                "pipeline_phase": "revising",
                "tool_logs": _merge_logs(state, "solve_fea", f"Skipped solve_fea: {failure_message}"),
            }

        try:
            result = solve_fea.invoke({"workspace_path": state["workspace_path"]})
            status = CompileStatus(stage="solve_fea", success=True)
            log = "\n".join(item for item in [result.get("stdout", ""), result.get("stderr", "")] if item).strip()
            vtk_paths = list(state.get("vtk_paths", []))
            vtk_path = result.get("vtk_path")
            if isinstance(vtk_path, str) and vtk_path:
                vtk_paths.append(vtk_path)
            update = {
                "compile_status": status.model_dump(),
                "fea_results": {
                    key: value
                    for key, value in result.items()
                    if key not in {"stdout", "stderr", "command"}
                },
                "vtk_paths": vtk_paths,
                "pipeline_phase": "reviewing",
                "tool_logs": _merge_logs(state, "solve_fea", log or "solve_fea completed."),
            }
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="solve_fea", success=False, error_message=str(exc))
            update = {
                "compile_status": status.model_dump(),
                "fea_results": {},
                "pipeline_phase": "revising",
                "tool_logs": _merge_logs(state, "solve_fea", str(exc)),
            }
        return update

    return solve_fea_node


def make_render_views_node():
    def render_views_node(state: AgentState) -> dict[str, Any]:
        payload = DesignPayload.model_validate(state["design_payload"])
        try:
            result = render_views.invoke(
                {
                    "workspace_path": state["workspace_path"],
                    "render_config": payload.render_config.model_dump(),
                }
            )
            log = f"Rendered {len(result['image_paths'])} views."
            return {
                "image_paths": result["image_paths"],
                "pipeline_phase": "reviewing",
                "tool_logs": _merge_logs(state, "render_views", log),
            }
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="render_views", success=False, error_message=str(exc))
            return {
                "compile_status": status.model_dump(),
                "image_paths": [],
                "pipeline_phase": "revising",
                "tool_logs": _merge_logs(state, "render_views", str(exc)),
            }

    return render_views_node


def make_physics_qa_node(runtime):
    def physics_qa(state: AgentState) -> dict[str, Any]:
        fea_results = state.get("fea_results", {})
        violations: list[str] = []
        recommendations: list[str] = []
        max_disp = fea_results.get("max_disp_mm")
        max_stress = fea_results.get("max_stress_mpa")
        if max_disp is None:
            violations.append("有限元结果缺失，无法获得最大位移。")
            recommendations.append("优先修复 CAD/网格/求解环节，再重新生成。")
        elif max_disp > runtime.displacement_limit_mm:
            violations.append(
                f"最大位移 {max_disp:.3f} mm 超过阈值 {runtime.displacement_limit_mm:.3f} mm。"
            )
            recommendations.append("增加支撑区域厚度、缩短悬臂长度，或降低载荷。")

        if max_stress is not None and max_stress > runtime.stress_limit_mpa:
            violations.append(
                f"最大应力 {max_stress:.3f} MPa 超过阈值 {runtime.stress_limit_mpa:.3f} MPa。"
            )
            recommendations.append("增加截面尺寸或优化受力路径。")

        review = PhysicsReview(
            **{
                "pass": len(violations) == 0,
                "max_disp_mm": max_disp,
                "max_stress_mpa": max_stress,
                "violations": violations,
                "recommended_edits": recommendations,
            }
        )
        review_dict = review.model_dump(by_alias=True)
        return {
            "physics_review": review_dict,
            "pipeline_phase": "reviewing",
            "review_artifacts": _merge_review_artifacts(state, physics_review=review_dict),
        }

    return physics_qa


def make_physics_report_node(runtime):
    def physics_report(state: AgentState) -> dict[str, Any]:
        report, log = runtime.generate_physics_report(
            state.get("clarified_spec", {}),
            state.get("fea_results", {}),
            state.get("physics_review", {}),
        )
        return {
            "physics_report": report,
            "token_usage": runtime.token_usage_snapshot(),
            "pipeline_phase": "reviewing",
            "tool_logs": _merge_logs(state, "physics_report", log),
            "review_artifacts": _merge_review_artifacts(
                state,
                physics_report=report,
                physics_review=state.get("physics_review", {}),
            ),
        }

    return physics_report


def make_visual_qa_node(runtime):
    def visual_qa(state: AgentState) -> dict[str, Any]:
        review, log = runtime.review_visual_with_meta(
            state["user_prompt"],
            state.get("clarified_spec", {}),
            state.get("image_paths", []),
            state.get("feedback_history", []),
        )
        review_dict = review.model_dump(by_alias=True)
        return {
            "visual_review": review_dict,
            "token_usage": runtime.token_usage_snapshot(),
            "pipeline_phase": "reviewing",
            "tool_logs": _merge_logs(state, "visual_qa", log),
            "review_artifacts": _merge_review_artifacts(state, visual_review=review_dict),
        }

    return visual_qa


def make_revision_brief_node():
    def revision_brief(state: AgentState) -> dict[str, Any]:
        structured_revision = build_structured_revision(state)
        brief = _compose_revision_brief(state)
        log_message = "No revision brief needed." if not brief else "Revision brief composed for current iteration."
        update: dict[str, Any] = {
            "latest_revision_brief": brief,
            "structured_revision": structured_revision,
            "pipeline_phase": "revising" if brief else "reviewing",
            "tool_logs": _merge_logs(state, "revision_brief", log_message),
            "review_artifacts": _merge_review_artifacts(
                state,
                physics_review=state.get("physics_review", {}),
                visual_review=state.get("visual_review", {}),
                physics_report=state.get("physics_report", ""),
                latest_revision_brief=brief,
                structured_revision=structured_revision,
            ),
        }
        workspace_path = state.get("workspace_path", "")
        if workspace_path:
            persist_iteration_artifacts.invoke(
                {
                    "workspace_path": workspace_path,
                    "engineering_prompt": state.get("engineering_prompt", ""),
                    "latest_revision_brief": brief,
                    "physics_report": state.get("physics_report", ""),
                    "design_request": state.get("design_request", ""),
                    "physics_review": state.get("physics_review", {}),
                    "visual_review": state.get("visual_review", {}),
                }
            )
        return update

    return revision_brief


def make_feedback_merge_node():
    def feedback_merge(state: AgentState) -> dict[str, Any]:
        brief = (state.get("latest_revision_brief") or "").strip()
        if not brief:
            brief = _compose_revision_brief(state)

        feedback = list(state.get("feedback_history", []))
        if brief and (not feedback or feedback[-1] != brief):
            feedback.append(brief)
        return {
            "feedback_history": feedback,
            "latest_revision_brief": brief,
            "pipeline_phase": "revising" if brief else "reviewing",
        }

    return feedback_merge


def make_quality_gate_node(runtime):
    def quality_gate(state: AgentState) -> dict[str, Any]:
        quality = compute_quality_score(state, runtime)
        quality_history = list(state.get("quality_history", []))
        quality_history.append(quality)

        workspace_path = state.get("workspace_path", "") or ""
        step_path = str(Path(workspace_path) / "model.step") if workspace_path else ""
        stl_path = str(Path(workspace_path) / "model.stl") if workspace_path else ""
        latest_model_step = step_path if step_path and Path(step_path).exists() else ""
        latest_model_stl = stl_path if stl_path and Path(stl_path).exists() else ""

        best_score = state.get("best_score")
        min_delta = _state_float(state, "min_improvement_delta", _env_float("TEXTCAD_MIN_IMPROVEMENT_DELTA", 0.03))
        enable_best = _env_bool("TEXTCAD_ENABLE_BEST_SO_FAR", True)
        can_promote = bool(enable_best and latest_model_step and latest_model_stl and state.get("design_payload"))
        improved = bool(can_promote and (best_score is None or quality["score"] > float(best_score) + min_delta))

        update: dict[str, Any] = {
            "quality_history": quality_history,
            "final_score": quality["score"],
            "latest_model_step": latest_model_step,
            "latest_model_stl": latest_model_stl,
            "pipeline_phase": "revising" if quality["penalties"] else state.get("pipeline_phase", "reviewing"),
        }

        if improved:
            update.update(
                {
                    "best_iteration": state.get("iteration"),
                    "best_score": quality["score"],
                    "best_code": (state.get("design_payload") or {}).get("cadquery_code"),
                    "best_run_dir": workspace_path,
                    "best_model_step": latest_model_step,
                    "best_model_stl": latest_model_stl,
                    "best_visual_review": state.get("visual_review", {}),
                    "best_physics_review": state.get("physics_review", {}),
                    "best_compile_status": state.get("compile_status", {}),
                    "best_quality_report": quality,
                    "no_improvement_count": 0,
                    "returned_model_source": "best_so_far",
                }
            )
        else:
            update["no_improvement_count"] = int(state.get("no_improvement_count", 0) or 0) + 1

        return update

    return quality_gate


def make_decide_next_node(runtime):
    def decide_next(state: AgentState) -> Command[Literal["design_generate", "__end__"]]:
        design_state = state.get("design_status", {}).get("state", "pending")
        compile_status = state.get("compile_status", {})
        compile_ok = compile_status.get("success", False)
        physics_ok = state.get("physics_review", {}).get("pass", False)
        visual_ok = state.get("visual_review", {}).get("pass", False)
        review_cycle_completed = bool(state.get("physics_review")) or bool(state.get("visual_review"))
        best_exists = bool(state.get("best_model_stl") or state.get("best_model_step"))
        final_update = {
            "final_iteration": state.get("iteration"),
            "final_score": state.get("final_score"),
            "returned_model_source": "best_so_far" if best_exists else "latest",
        }
        if best_exists and state.get("best_run_dir"):
            final_update["workspace_path"] = state.get("best_run_dir")

        max_no_improvement = _state_int(state, "max_no_improvement", _env_int("TEXTCAD_MAX_NO_IMPROVEMENT", 2))
        if (
            max_no_improvement > 0
            and best_exists
            and int(state.get("no_improvement_count", 0) or 0) >= max_no_improvement
        ):
            return Command(
                update={
                    **final_update,
                    "final_status": "success",
                    "stop_reason": "no_quality_improvement",
                    "pipeline_phase": "completed",
                },
                goto="__end__",
            )

        if design_state in {"failed"}:
            if best_exists:
                return Command(
                    update={
                        **final_update,
                        "final_status": "success",
                        "stop_reason": "design_failed_returned_best",
                        "pipeline_phase": "completed",
                    },
                    goto="__end__",
                )
            return Command(update={**final_update, "final_status": "failed", "pipeline_phase": "failed"}, goto="__end__")

        if compile_ok and physics_ok and visual_ok:
            return Command(
                update={**final_update, "final_status": "success", "stop_reason": "accepted", "pipeline_phase": "completed"},
                goto="__end__",
            )

        if not review_cycle_completed:
            if compile_status.get("stage") == "static_validate":
                if state.get("iteration", 1) >= runtime.max_iterations:
                    if best_exists:
                        return Command(
                            update={
                                **final_update,
                                "final_status": "success",
                                "stop_reason": "max_iterations_returned_best",
                                "pipeline_phase": "completed",
                            },
                            goto="__end__",
                        )
                    return Command(
                        update={**final_update, "final_status": "failed", "pipeline_phase": "failed"},
                        goto="__end__",
                    )
                return Command(
                    update={
                        "iteration": state.get("iteration", 1) + 1,
                        "compile_retry_count": 0,
                        "pipeline_phase": "revising",
                        "final_status": "running",
                    },
                    goto="design_generate",
                )
            next_retry_count = state.get("compile_retry_count", 0) + 1
            if next_retry_count > runtime.max_compile_retries_per_iteration:
                if best_exists:
                    return Command(
                        update={
                            **final_update,
                            "final_status": "success",
                            "stop_reason": "compile_retry_limit_returned_best",
                            "pipeline_phase": "completed",
                        },
                        goto="__end__",
                    )
                return Command(update={**final_update, "final_status": "failed", "pipeline_phase": "failed"}, goto="__end__")
            return Command(
                update={
                    "compile_retry_count": next_retry_count,
                    "pipeline_phase": "revising",
                    "final_status": "running",
                },
                goto="design_generate",
            )

        if state.get("iteration", 1) >= runtime.max_iterations:
            if best_exists:
                return Command(
                    update={
                        **final_update,
                        "final_status": "success",
                        "stop_reason": "max_iterations_returned_best",
                        "pipeline_phase": "completed",
                    },
                    goto="__end__",
                )
            return Command(update={**final_update, "final_status": "failed", "pipeline_phase": "failed"}, goto="__end__")

        return Command(
            update={
                "iteration": state.get("iteration", 1) + 1,
                "compile_retry_count": 0,
                "pipeline_phase": "revising",
                "final_status": "running",
            },
            goto="design_generate",
        )

    return decide_next
