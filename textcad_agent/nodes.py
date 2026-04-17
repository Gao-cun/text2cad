from __future__ import annotations

import ast
import os
import uuid
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

ALLOWED_IMPORT_ROOTS = {"__future__", "cadquery", "math", "typing"}
DISALLOWED_CALLS = {"open", "exec", "eval", "compile", "input", "__import__"}
DISALLOWED_ATTR_ROOTS = {"os", "sys", "subprocess", "shutil", "socket", "requests", "httpx", "pathlib"}
BUILD_ENTRYPOINTS = {"build_model", "build", "make_model"}
MODEL_VARIABLES = {"MODEL", "model"}


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
        issues = visual_review.get("issues", []) + visual_review.get("missing_requirements", [])
        recommendations = visual_review.get("recommended_edits", [])
        parts.append("视觉审查未通过：" + "；".join(issues + recommendations))

    return "\n".join(part for part in parts if part).strip()


def _plane_x_from_bbox(bbox: list[float]) -> float:
    return float((bbox[0] + bbox[3]) / 2.0)


def _collect_static_validation_errors(code: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"CAD 代码语法错误: {exc.msg} (line {exc.lineno})"]

    has_entrypoint = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    errors.append(f"不允许导入模块: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                errors.append(f"不允许 from-import 模块: {module}")
        elif isinstance(node, ast.FunctionDef) and node.name in BUILD_ENTRYPOINTS:
            has_entrypoint = True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in MODEL_VARIABLES:
                    has_entrypoint = True
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_CALLS:
                errors.append(f"不允许调用危险函数: {node.func.id}")
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id in DISALLOWED_ATTR_ROOTS:
                    errors.append(f"不允许调用危险模块 API: {node.func.value.id}.{node.func.attr}")

    if not has_entrypoint:
        errors.append("CAD 代码必须定义 build_model()/build()/make_model() 或 MODEL/model。")

    return errors


def make_ingest_request_node():
    def ingest_request(state: AgentState) -> dict[str, Any]:
        return {
            "run_id": uuid.uuid4().hex[:10],
            "iteration": 1,
            "feedback_history": [],
            "tool_logs": {},
            "vtk_paths": [],
            "assumptions": [],
            "engineering_prompt": "",
            "design_request": "",
            "latest_revision_brief": "",
            "physics_report": "",
            "review_artifacts": {},
            "design_status": DesignStatus().model_dump(),
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
            "clarification_request": {
                "missing_fields": spec.missing_high_risk_fields,
                "assumptions": spec.assumptions,
            },
        }
        if spec.missing_high_risk_fields:
            update["final_status"] = "awaiting_user"
            return Command(update=update, goto="await_user_clarification")

        update["final_status"] = "running"
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
                "final_status": "running",
            },
            goto="engineer_spec",
        )

    return await_user_clarification


def make_engineer_spec_node():
    def engineer_spec(state: AgentState) -> dict[str, Any]:
        spec = ClarifiedSpec.model_validate(state["clarified_spec"])
        backend = AnalysisConfig(
            length_mm=spec.length_mm,
            width_mm=spec.width_mm,
            height_mm=spec.height_mm,
            fixed_x=_plane_x_from_bbox(spec.fixed_boundary),
            load_x=_plane_x_from_bbox(spec.load_boundary),
            bbox_tol=spec.bbox_tol,
            load_vector_n=spec.load_vector_n,
            young_modulus_mpa=spec.material_young_mpa,
            poisson_ratio=spec.material_poisson,
        )
        spec_dict = spec.model_dump()
        spec_dict["backend_config"] = backend.model_dump()
        return {
            "clarified_spec": spec_dict,
            "assumptions": spec.assumptions,
        }

    return engineer_spec


def make_design_generate_node(runtime):
    def design_generate(state: AgentState) -> dict[str, Any]:
        prev_code = state.get("design_payload", {}).get("cadquery_code", "")
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
                "tool_logs": logs,
            }

        payload_dict = payload.model_dump()
        notes = payload_dict.get("self_check_notes", [])
        used_model = not any("heuristic fallback used" in str(note).lower() for note in notes)
        code_changed = True if not prev_code else (
            _normalized_code_signature(prev_code) != _normalized_code_signature(payload_dict["cadquery_code"])
        )

        if prev_code and latest_revision_brief and not code_changed:
            status = DesignStatus(
                state="unchanged_after_failed_review",
                error_message="收到上一轮审查反馈后，生成代码没有发生实质变化。",
                code_changed=False,
                used_model=used_model,
            )
            compile_status = CompileStatus(
                stage="design_generate",
                success=False,
                error_message=status.error_message,
            )
            logs["design_generate"] = "design_generate: unchanged_after_failed_review"
            return {
                "design_payload": payload_dict,
                "design_request": design_request,
                "design_status": status.model_dump(),
                "compile_status": compile_status.model_dump(),
                "tool_logs": logs,
            }

        status_value = "model_ok" if used_model else "heuristic_fallback"
        status = DesignStatus(
            state=status_value,
            error_message=None,
            code_changed=code_changed,
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
            "compile_status": {},
            "workspace_path": "",
            "fea_results": {},
            "image_paths": [],
            "visual_review": {},
            "physics_review": {},
            "physics_report": "",
            "latest_revision_brief": "",
            "review_artifacts": {},
            "tool_logs": logs,
        }

    return design_generate


def make_static_validate_node():
    def static_validate(
        state: AgentState,
    ) -> Command[Literal["materialize_workspace", "feedback_merge"]]:
        design_status = state.get("design_status", {})
        if design_status.get("state") in {"failed", "unchanged_after_failed_review"}:
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
                },
                goto="feedback_merge",
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
                },
                goto="feedback_merge",
            )

        payload = DesignPayload.model_validate(state["design_payload"])
        errors = _collect_static_validation_errors(payload.cadquery_code)
        if errors:
            status = CompileStatus(
                stage="static_validate",
                success=False,
                syntax_ok=not any("语法错误" in item for item in errors),
                security_ok=not any("不允许" in item for item in errors),
                error_message="；".join(errors),
            )
            return Command(
                update={
                    "compile_status": status.model_dump(),
                    "tool_logs": _merge_logs(state, "static_validate", status.error_message or ""),
                },
                goto="feedback_merge",
            )

        status = CompileStatus(stage="static_validate", success=True)
        return Command(
            update={
                "compile_status": status.model_dump(),
                "tool_logs": _merge_logs(state, "static_validate", "Static validation passed."),
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
            "tool_logs": _merge_logs(state, "materialize_workspace", str(result)),
        }

    return materialize_workspace_node


def make_build_cad_node():
    def build_cad_node(state: AgentState) -> Command[Literal["build_mesh", "feedback_merge"]]:
        try:
            result = build_cad.invoke({"workspace_path": state["workspace_path"]})
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="build_cad", success=False, error_message=str(exc))
            return Command(
                update={
                    "compile_status": status.model_dump(),
                    "tool_logs": _merge_logs(state, "build_cad", str(exc)),
                },
                goto="feedback_merge",
            )

        status = CompileStatus(stage="build_cad", success=True)
        log = "\n".join(item for item in [result.get("stdout", ""), result.get("stderr", "")] if item).strip()
        return Command(
            update={
                "compile_status": status.model_dump(),
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
            "tool_logs": _merge_logs(state, "build_mesh", log),
        }

    return build_mesh_node


def make_solve_fea_node():
    def solve_fea_node(state: AgentState) -> dict[str, Any]:
        if not state.get("compile_status", {}).get("success", False):
            failure_message = state.get("compile_status", {}).get("error_message", "Mesh build failed.")
            return {
                "fea_results": {},
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
                "tool_logs": _merge_logs(state, "solve_fea", log or "solve_fea completed."),
            }
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="solve_fea", success=False, error_message=str(exc))
            update = {
                "compile_status": status.model_dump(),
                "fea_results": {},
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
                "tool_logs": _merge_logs(state, "render_views", log),
            }
        except Exception as exc:  # pragma: no cover - exercised via integration
            status = CompileStatus(stage="render_views", success=False, error_message=str(exc))
            return {
                "compile_status": status.model_dump(),
                "image_paths": [],
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
            "tool_logs": _merge_logs(state, "visual_qa", log),
            "review_artifacts": _merge_review_artifacts(state, visual_review=review_dict),
        }

    return visual_qa


def make_revision_brief_node():
    def revision_brief(state: AgentState) -> dict[str, Any]:
        brief = _compose_revision_brief(state)
        log_message = "No revision brief needed." if not brief else "Revision brief composed for current iteration."
        update: dict[str, Any] = {
            "latest_revision_brief": brief,
            "tool_logs": _merge_logs(state, "revision_brief", log_message),
            "review_artifacts": _merge_review_artifacts(
                state,
                physics_review=state.get("physics_review", {}),
                visual_review=state.get("visual_review", {}),
                physics_report=state.get("physics_report", ""),
                latest_revision_brief=brief,
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
        }

    return feedback_merge


def make_decide_next_node(runtime):
    def decide_next(state: AgentState) -> Command[Literal["design_generate", "__end__"]]:
        design_state = state.get("design_status", {}).get("state", "pending")
        compile_ok = state.get("compile_status", {}).get("success", False)
        physics_ok = state.get("physics_review", {}).get("pass", False)
        visual_ok = state.get("visual_review", {}).get("pass", False)

        if design_state in {"failed", "unchanged_after_failed_review"}:
            return Command(update={"final_status": "failed"}, goto="__end__")

        if compile_ok and physics_ok and visual_ok:
            return Command(update={"final_status": "success"}, goto="__end__")

        if state.get("iteration", 1) >= runtime.max_iterations:
            return Command(update={"final_status": "failed"}, goto="__end__")

        return Command(
            update={
                "iteration": state.get("iteration", 1) + 1,
                "final_status": "running",
            },
            goto="design_generate",
        )

    return decide_next
