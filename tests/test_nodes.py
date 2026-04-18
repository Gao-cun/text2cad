from __future__ import annotations

from textcad_agent.agent import AgentRuntime, ModelEndpoint
from textcad_agent.nodes import (
    _collect_static_validation_errors,
    make_await_user_clarification_node,
    make_design_generate_node,
    make_decide_next_node,
    make_feedback_merge_node,
    make_physics_qa_node,
    make_revision_brief_node,
    make_visual_qa_node,
)
from textcad_agent.state import VisualReview


def test_feedback_merge_collects_compile_and_review_failures():
    node = make_feedback_merge_node()
    state = {
        "feedback_history": [],
        "compile_status": {"success": False, "stage": "build_cad", "error_message": "syntax failure"},
        "physics_review": {"pass": False, "violations": ["disp too high"], "recommended_edits": ["thicken beam"]},
        "visual_review": {"pass": False, "issues": ["missing hole"], "missing_requirements": [], "recommended_edits": ["add hole"]},
    }
    result = node(state)
    assert len(result["feedback_history"]) == 1
    assert "build_cad" in result["feedback_history"][0]
    assert "disp too high" in result["feedback_history"][0]
    assert "missing hole" in result["feedback_history"][0]
    assert result["latest_revision_brief"]


def test_decide_next_routes_to_retry_or_end():
    runtime = AgentRuntime(max_iterations=3)
    node = make_decide_next_node(runtime)

    retry = node(
        {
            "iteration": 1,
            "compile_retry_count": 0,
            "compile_status": {"success": False},
            "physics_review": {},
            "visual_review": {},
        }
    )
    assert retry.goto == "design_generate"
    assert retry.update["compile_retry_count"] == 1

    success = node(
        {
            "iteration": 1,
            "compile_retry_count": 0,
            "compile_status": {"success": True},
            "physics_review": {"pass": True},
            "visual_review": {"pass": True},
        }
    )
    assert success.goto == "__end__"
    assert success.update["final_status"] == "success"


def test_decide_next_does_not_short_circuit_when_visual_presence_is_true_but_reviews_fail():
    runtime = AgentRuntime(max_iterations=3)
    node = make_decide_next_node(runtime)

    decision = node(
        {
            "iteration": 2,
            "compile_retry_count": 0,
            "compile_status": {"success": True},
            "physics_review": {"pass": False},
            "visual_review": {"pass": False, "is_present": True},
        }
    )

    assert decision.goto == "design_generate"
    assert decision.update["iteration"] == 3
    assert decision.update["compile_retry_count"] == 0
    assert decision.update["final_status"] == "running"


def test_decide_next_keeps_same_iteration_for_build_cad_failure():
    runtime = AgentRuntime(max_iterations=3, max_compile_retries_per_iteration=3)
    node = make_decide_next_node(runtime)

    decision = node(
        {
            "iteration": 2,
            "compile_retry_count": 1,
            "compile_status": {"success": False, "stage": "build_cad"},
            "physics_review": {},
            "visual_review": {},
        }
    )

    assert decision.goto == "design_generate"
    assert "iteration" not in decision.update
    assert decision.update["compile_retry_count"] == 2
    assert decision.update["final_status"] == "running"


def test_decide_next_fails_after_compile_retry_limit():
    runtime = AgentRuntime(max_iterations=3, max_compile_retries_per_iteration=2)
    node = make_decide_next_node(runtime)

    decision = node(
        {
            "iteration": 1,
            "compile_retry_count": 2,
            "compile_status": {"success": False, "stage": "build_cad"},
            "physics_review": {},
            "visual_review": {},
        }
    )

    assert decision.goto == "__end__"
    assert decision.update["final_status"] == "failed"


def test_physics_qa_uses_displacement_threshold():
    runtime = AgentRuntime(displacement_limit_mm=5.0)
    node = make_physics_qa_node(runtime)
    result = node({"fea_results": {"max_disp_mm": 12.0, "max_stress_mpa": None}})
    assert result["physics_review"]["pass"] is False
    assert "最大位移" in result["physics_review"]["violations"][0]


def test_static_validate_rejects_bbox_min_max_style_access():
    code = "\n".join(
        [
            "import cadquery as cq",
            "",
            "def build_model():",
            "    body = cq.Workplane('XY').box(10, 10, 10)",
            "    bb = body.val().BoundingBox()",
            "    return body.translate((-bb.min.X, 0, 0))",
        ]
    )

    errors = _collect_static_validation_errors(code)

    assert any("BoundingBox.min.X/max.X" in item for item in errors)


def test_static_validate_rejects_dangerous_alias_calls():
    code = "\n".join(
        [
            "import cadquery as cq",
            "import os as operating_system",
            "",
            "def build_model():",
            "    operating_system.system('echo nope')",
            "    return cq.Workplane('XY').box(10, 10, 10)",
        ]
    )

    errors = _collect_static_validation_errors(code)

    assert any("operating_system.system" in item for item in errors)


def test_await_user_clarification_merges_interrupt_response(monkeypatch):
    monkeypatch.setattr(
        "textcad_agent.nodes.interrupt",
        lambda payload: {"load_vector_n": [0.0, -10.0, 0.0], "missing_high_risk_fields": []},
    )
    runtime = AgentRuntime()
    node = make_await_user_clarification_node(runtime)
    result = node(
        {
            "clarified_spec": {
                "request_summary": "beam",
                "length_mm": 100.0,
                "width_mm": 10.0,
                "height_mm": 10.0,
                "unit_system": "mm",
                "material_name": "PLA",
                "material_young_mpa": 3500.0,
                "material_poisson": 0.36,
                "fixed_boundary": [0.0, -5.0, -5.0, 0.0, 5.0, 5.0],
                "load_boundary": [100.0, -5.0, -5.0, 100.0, 5.0, 5.0],
                "load_vector_n": [0.0, -50.0, 0.0],
                "bbox_tol": 0.2,
                "missing_high_risk_fields": ["load_vector_n"],
                "assumptions": [],
                "visual_requirements": [],
            },
            "clarification_request": {"missing_fields": ["load_vector_n"]},
        }
    )
    assert result.goto == "engineer_spec"
    assert result.update["clarified_spec"]["load_vector_n"] == [0.0, -10.0, 0.0]
    assert result.update["engineering_prompt"]


def test_design_generate_uses_engineering_prompt_and_revision_brief():
    runtime = AgentRuntime()

    def fake_design(prompt: str, clarified_spec: dict, feedback_history: list[str], previous_code: str = "", **kwargs):
        backend = clarified_spec["backend_config"]
        assert kwargs["engineering_prompt"] == "cached engineering prompt"
        assert "需要新增前挡边" in kwargs["latest_revision_brief"]
        assert previous_code == "old code"
        return runtime._heuristic_design(clarified_spec)

    runtime.design = fake_design  # type: ignore[method-assign]
    node = make_design_generate_node(runtime)
    result = node(
        {
            "user_prompt": "手机支架",
            "clarified_spec": {
                "request_summary": "手机支架",
                "length_mm": 90.0,
                "width_mm": 70.0,
                "height_mm": 100.0,
                "unit_system": "mm",
                "material_name": "PLA",
                "material_young_mpa": 3500.0,
                "material_poisson": 0.36,
                "fixed_boundary": [0.0, -35.0, -50.0, 0.0, 35.0, 50.0],
                "load_boundary": [90.0, -35.0, -50.0, 90.0, 35.0, 50.0],
                "load_vector_n": [0.0, -1.0, 0.0],
                "bbox_tol": 0.2,
                "missing_high_risk_fields": [],
                "assumptions": [],
                "visual_requirements": ["前挡边"],
                "backend_config": {
                    "length_mm": 90.0,
                    "width_mm": 70.0,
                    "height_mm": 100.0,
                    "fixed_x": 0.0,
                    "load_x": 90.0,
                    "bbox_tol": 0.2,
                    "load_vector_n": [0.0, -1.0, 0.0],
                    "young_modulus_mpa": 3500.0,
                    "poisson_ratio": 0.36,
                },
            },
            "engineering_prompt": "cached engineering prompt",
            "latest_revision_brief": "视觉审查未通过：需要新增前挡边。",
            "design_payload": {"cadquery_code": "old code"},
            "tool_logs": {},
        }
    )
    assert "cached engineering prompt" in result["design_request"]
    assert "需要新增前挡边" in result["design_request"]


def test_design_generate_fails_when_code_is_unchanged_after_feedback():
    runtime = AgentRuntime()
    node = make_design_generate_node(runtime)
    unchanged_code = (
        "from __future__ import annotations\n\n"
        "import cadquery as cq\n\n"
        "def build_model():\n"
        "    return cq.Workplane(\"XY\").box(20, 20, 20)\n"
    )

    def fake_design(prompt: str, clarified_spec: dict, feedback_history: list[str], previous_code: str = "", **kwargs):
        backend = clarified_spec["backend_config"]
        return runtime._heuristic_design(clarified_spec).model_copy(update={"cadquery_code": unchanged_code})

    runtime.design = fake_design  # type: ignore[method-assign]
    result = node(
        {
            "user_prompt": "测试模型",
            "clarified_spec": {
                "request_summary": "测试模型",
                "length_mm": 20.0,
                "width_mm": 20.0,
                "height_mm": 20.0,
                "unit_system": "mm",
                "material_name": "PLA",
                "material_young_mpa": 3500.0,
                "material_poisson": 0.36,
                "fixed_boundary": [0.0, -10.0, -10.0, 0.0, 10.0, 10.0],
                "load_boundary": [20.0, -10.0, -10.0, 20.0, 10.0, 10.0],
                "load_vector_n": [0.0, -1.0, 0.0],
                "bbox_tol": 0.2,
                "missing_high_risk_fields": [],
                "assumptions": [],
                "visual_requirements": ["应有改动"],
                "backend_config": {
                    "length_mm": 20.0,
                    "width_mm": 20.0,
                    "height_mm": 20.0,
                    "fixed_x": 0.0,
                    "load_x": 20.0,
                    "bbox_tol": 0.2,
                    "load_vector_n": [0.0, -1.0, 0.0],
                    "young_modulus_mpa": 3500.0,
                    "poisson_ratio": 0.36,
                },
            },
            "engineering_prompt": "cached engineering prompt",
            "latest_revision_brief": "视觉审查未通过：请增加挡边。",
            "design_payload": {"cadquery_code": unchanged_code},
            "tool_logs": {},
        }
    )
    assert result["design_status"]["state"] == "unchanged_after_failed_review"


def test_revision_brief_prefers_current_round_feedback():
    node = make_revision_brief_node()
    result = node(
        {
            "latest_revision_brief": "",
            "feedback_history": ["旧反馈：不要再用这个。"],
            "physics_report": "力学分析报告：最大位移 12.0 mm，建议加厚支撑。",
            "physics_review": {"pass": False, "violations": ["最大位移超标"], "recommended_edits": ["加厚支撑"]},
            "visual_review": {
                "pass": False,
                "issues": ["缺少前挡边"],
                "missing_requirements": [],
                "recommended_edits": ["在承托前缘增加挡边"],
            },
            "review_artifacts": {},
            "tool_logs": {},
        }
    )
    assert "旧反馈" not in result["latest_revision_brief"]
    assert "缺少前挡边" in result["latest_revision_brief"]


def test_visual_qa_logs_remote_success(tmp_path):
    runtime = AgentRuntime(
        visual_review_fn=lambda prompt, spec, images, feedback: VisualReview(
            **{
                "pass": True,
                "issues": [],
                "missing_requirements": [],
                "recommended_edits": [],
                "backend": "remote_model",
            }
        )
    )
    node = make_visual_qa_node(runtime)
    image_path = tmp_path / "render.png"
    image_path.write_bytes(b"fake-image")
    result = node(
        {
            "user_prompt": "手机支架",
            "clarified_spec": {},
            "image_paths": [str(image_path)],
            "feedback_history": [],
            "tool_logs": {},
        }
    )
    assert result["visual_review"]["backend"] == "remote_model"
    assert "custom visual_review_fn" in result["tool_logs"]["visual_qa"]


def test_visual_qa_fails_closed_when_remote_visual_review_errors(monkeypatch, tmp_path):
    runtime = AgentRuntime()
    monkeypatch.setattr(
        runtime,
        "_endpoint_for_role",
        lambda role: ModelEndpoint(
            role="visual",
            model="qwen3.6-plus",
            model_provider="openai",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="test-key",
            configured_via_env=True,
        ),
    )
    monkeypatch.setattr(runtime, "_has_role_specific_env_config", lambda role: True)
    monkeypatch.setattr(runtime, "_get_chat_model", lambda role: object())
    monkeypatch.setattr(
        runtime,
        "_invoke_raw_json",
        lambda model, messages, **kwargs: (_ for _ in ()).throw(RuntimeError("invalid json")),
    )
    node = make_visual_qa_node(runtime)
    image_path = tmp_path / "render.png"
    image_path.write_bytes(b"fake-image")
    result = node(
        {
            "user_prompt": "手机支架",
            "clarified_spec": {},
            "image_paths": [str(image_path)],
            "feedback_history": [],
            "tool_logs": {},
        }
    )
    assert result["visual_review"]["pass"] is False
    assert result["visual_review"]["backend"] == "heuristic_fallback"
    assert "Remote visual QA failed" in result["visual_review"]["fallback_reason"]
    assert "Remote visual QA failed" in result["tool_logs"]["visual_qa"]
