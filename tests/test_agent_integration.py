from __future__ import annotations

import json
from pathlib import Path

from textcad_agent.agent import AgentRuntime, build_agent
from textcad_agent.state import ClarifiedSpec, DesignPayload, RenderConfig, VisualReview


def _happy_spec() -> ClarifiedSpec:
    return ClarifiedSpec(
        request_summary="stiff beam",
        length_mm=20.0,
        width_mm=40.0,
        height_mm=40.0,
        fixed_boundary=[0.0, -20.0, -20.0, 0.0, 20.0, 20.0],
        load_boundary=[20.0, -20.0, -20.0, 20.0, 20.0, 20.0],
        load_vector_n=[0.0, -1.0, 0.0],
        missing_high_risk_fields=[],
        assumptions=[],
        visual_requirements=["矩形梁"],
    )


def _happy_design(prompt: str, clarified_spec: dict, feedback_history: list[str]) -> DesignPayload:
    backend = clarified_spec["backend_config"]
    code = (
        "from __future__ import annotations\n\n"
        "import cadquery as cq\n\n"
        "def build_model():\n"
        "    return (\n"
        '        cq.Workplane("XY")\n'
        f"        .box({backend['length_mm']}, {backend['width_mm']}, {backend['height_mm']})\n"
        f"        .translate(({backend['length_mm']} / 2.0, 0.0, 0.0))\n"
        "    )\n"
    )
    return DesignPayload(
        cadquery_code=code,
        analysis_config=backend,
        render_config=RenderConfig(),
        self_check_notes=feedback_history,
    )


def _modified_happy_design(prompt: str, clarified_spec: dict, feedback_history: list[str]) -> DesignPayload:
    payload = _happy_design(prompt, clarified_spec, feedback_history)
    return payload.model_copy(
        update={
            "cadquery_code": payload.cadquery_code.replace(
                ".translate((20.0 / 2.0, 0.0, 0.0))",
                ".translate((20.0 / 2.0, 0.0, 0.0))\n        .edges('|Z').fillet(1.0)",
            ),
            "self_check_notes": ["added fillet after review"],
        }
    )


def test_graph_happy_path_runs_end_to_end():
    runtime = AgentRuntime(
        displacement_limit_mm=500.0,
        clarify_fn=lambda prompt, feedback: _happy_spec(),
        design_fn=_happy_design,
        visual_review_fn=lambda prompt, spec, images, feedback: VisualReview(
            **{"pass": True, "issues": [], "missing_requirements": [], "recommended_edits": []}
        ),
    )
    app = build_agent(runtime=runtime, with_memory=False)
    result = app.invoke({"user_prompt": "设计一个刚性很高的测试梁"})
    assert result["final_status"] == "success"
    assert result["workspace_path"]
    assert result["image_paths"]
    assert result["fea_results"]["max_disp_mm"] is not None


def test_graph_retries_after_static_validation_failure():
    attempts = {"count": 0}

    def design_with_one_failure(prompt: str, clarified_spec: dict, feedback_history: list[str]) -> DesignPayload:
        attempts["count"] += 1
        backend = clarified_spec["backend_config"]
        if attempts["count"] == 1:
            return DesignPayload(
                cadquery_code="def build_model(:\n    return None\n",
                analysis_config=backend,
                render_config=RenderConfig(),
                self_check_notes=[],
            )
        return _happy_design(prompt, clarified_spec, feedback_history)

    runtime = AgentRuntime(
        displacement_limit_mm=500.0,
        clarify_fn=lambda prompt, feedback: _happy_spec(),
        design_fn=design_with_one_failure,
        visual_review_fn=lambda prompt, spec, images, feedback: VisualReview(
            **{"pass": True, "issues": [], "missing_requirements": [], "recommended_edits": []}
        ),
    )
    app = build_agent(runtime=runtime, with_memory=False)
    result = app.invoke({"user_prompt": "设计一个允许重试的测试梁"})
    assert result["final_status"] == "success"
    assert result["iteration"] == 2
    assert len(result["feedback_history"]) == 1


def test_graph_persists_engineering_prompt_and_revision_artifacts(tmp_path):
    attempts = {"count": 0}

    def design_with_revision(prompt: str, clarified_spec: dict, feedback_history: list[str]) -> DesignPayload:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return _happy_design(prompt, clarified_spec, feedback_history)
        return _modified_happy_design(prompt, clarified_spec, feedback_history)

    def visual_review(prompt: str, spec: dict, images: list[str], feedback: list[str]) -> VisualReview:
        if not feedback:
            return VisualReview(
                **{
                    "pass": False,
                    "issues": ["缺少前挡边"],
                    "missing_requirements": [],
                    "recommended_edits": ["在承托前缘增加挡边"],
                    "backend": "remote_model",
                }
            )
        return VisualReview(
            **{"pass": True, "issues": [], "missing_requirements": [], "recommended_edits": [], "backend": "remote_model"}
        )

    runtime = AgentRuntime(
        displacement_limit_mm=500.0,
        clarify_fn=lambda prompt, feedback: _happy_spec(),
        design_fn=design_with_revision,
        visual_review_fn=visual_review,
        physics_report_fn=lambda spec, fea, review: "力学分析报告：最大位移 0.1 mm，结构稳定，可优先处理视觉缺陷。",
    )
    app = build_agent(runtime=runtime, with_memory=False)
    result = app.invoke({"user_prompt": "设计一个需要修复的测试梁"})

    assert result["final_status"] == "success"
    assert result["iteration"] == 2
    workspace = Path(result["workspace_path"])
    design_request = (workspace / "design_request.txt").read_text(encoding="utf-8")
    engineering_prompt = (workspace / "engineering_prompt.txt").read_text(encoding="utf-8")
    physics_report = (workspace / "physics_report.txt").read_text(encoding="utf-8")
    visual_review = json.loads((workspace / "visual_review.json").read_text(encoding="utf-8"))
    vtk_paths = result.get("vtk_paths", [])

    assert "工程基线说明" in engineering_prompt
    assert "缺少前挡边" in design_request
    assert "力学分析报告" in physics_report
    assert visual_review["backend"] == "remote_model"
    assert len(vtk_paths) == 2
    assert all(Path(path).exists() for path in vtk_paths)
    assert (workspace / "renders" / "render_scale.json").exists()


def test_graph_fails_when_second_round_code_is_unchanged():
    runtime = AgentRuntime(
        displacement_limit_mm=500.0,
        clarify_fn=lambda prompt, feedback: _happy_spec(),
        design_fn=_happy_design,
        visual_review_fn=lambda prompt, spec, images, feedback: VisualReview(
            **{
                "pass": False,
                "issues": ["缺少前挡边"],
                "missing_requirements": [],
                "recommended_edits": ["增加挡边"],
                "backend": "remote_model",
            }
        ),
        physics_report_fn=lambda spec, fea, review: "力学分析报告：结构基本稳定。",
    )
    app = build_agent(runtime=runtime, with_memory=False)
    result = app.invoke({"user_prompt": "设计一个会卡住修复的测试梁"})

    assert result["final_status"] == "failed"
    assert result["design_status"]["state"] == "unchanged_after_failed_review"


def test_graph_supports_freeform_phone_stand_prompt_end_to_end():
    runtime = AgentRuntime(
        displacement_limit_mm=500.0,
        visual_review_fn=lambda prompt, spec, images, feedback: VisualReview(
            **{"pass": True, "issues": [], "missing_requirements": [], "recommended_edits": []}
        ),
    )
    runtime.clarify_fn = lambda prompt, feedback: runtime._heuristic_clarify(prompt)
    runtime.design_fn = lambda prompt, clarified_spec, feedback: runtime._heuristic_design(clarified_spec)

    app = build_agent(runtime=runtime, with_memory=False)
    result = app.invoke({"user_prompt": "我要一个桌面手机支架，适合竖放看视频，结构尽量简洁，方便 3D 打印。"})

    assert result["final_status"] == "success"
    assert result["clarified_spec"]["object_type"] == "phone_stand"
    assert result["workspace_path"]
    assert result["fea_results"]["max_disp_mm"] is not None
