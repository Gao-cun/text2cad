from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from textcad_agent.web import (
    TaskRecord,
    TextCADWebService,
    _coerce_max_iterations,
    _coerce_max_no_improvement,
    _coerce_min_improvement_delta,
    _create_http_server,
    _runtime_policy_snapshot,
    build_run_payload,
    list_run_summaries,
    resolve_run_file,
    resolve_web_asset,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_create_http_server_uses_next_port_when_requested_port_is_busy():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        occupied_port = occupied.getsockname()[1]

        server = _create_http_server("127.0.0.1", occupied_port, max_port_attempts=5)
        try:
            assert server.server_address[1] != occupied_port
        finally:
            server.server_close()


def test_create_http_server_strict_port_raises_when_requested_port_is_busy():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        occupied_port = occupied.getsockname()[1]

        with pytest.raises(OSError):
            _create_http_server("127.0.0.1", occupied_port, strict_port=True)


def test_build_run_payload_reads_iteration_artifacts(tmp_path):
    iteration_dir = tmp_path / "run-demo" / "1"
    render_dir = iteration_dir / "renders"
    render_dir.mkdir(parents=True)

    _write_json(
        iteration_dir / "clarified_spec.json",
        {
            "request_summary": "桌面手机支架",
            "object_type": "phone_stand",
            "design_brief": "一体化极简支架",
            "length_mm": 90.0,
            "width_mm": 80.0,
            "height_mm": 110.0,
            "unit_system": "mm",
            "material_name": "PLA",
            "material_young_mpa": 3500.0,
            "material_poisson": 0.36,
            "fixed_boundary": [0, 0, 0, 1, 1, 1],
            "load_boundary": [0, 0, 0, 1, 1, 1],
            "load_vector_n": [0, 0, -2],
            "bbox_tol": 0.2,
            "missing_high_risk_fields": [],
            "assumptions": [],
            "visual_requirements": [],
        },
    )
    _write_json(iteration_dir / "analysis_config.json", {"length_mm": 90.0})
    _write_json(iteration_dir / "render_config.json", {"views": ["iso_front"]})
    _write_json(iteration_dir / "physics_review.json", {"pass": True, "max_disp_mm": 0.3})
    _write_json(iteration_dir / "visual_review.json", {"pass": True, "issues": []})
    _write_json(iteration_dir / "renders" / "render_scale.json", {"dimensions_mm": {"x": 90.0}})

    (iteration_dir / "generated_model.py").write_text("def build_model():\n    return None\n", encoding="utf-8")
    (iteration_dir / "design_request.txt").write_text("请生成支架", encoding="utf-8")
    (iteration_dir / "engineering_prompt.txt").write_text("工程基线说明", encoding="utf-8")
    (iteration_dir / "revision_brief.txt").write_text("修复前挡边", encoding="utf-8")
    (iteration_dir / "physics_report.txt").write_text("最大位移 0.3 mm", encoding="utf-8")
    (iteration_dir / "model.stl").write_bytes(b"solid demo")
    (iteration_dir / "model.step").write_bytes(b"step")
    (render_dir / "iso_front.png").write_bytes(b"png")

    payload = build_run_payload(tmp_path / "run-demo", runs_root=tmp_path)

    assert payload["run_id"] == "run-demo"
    assert payload["status"] == "success"
    assert payload["iteration_count"] == 1
    assert payload["request_summary"] == "桌面手机支架"
    assert payload["iterations"][0]["artifacts"]["stl"].endswith("/api/files/run-demo/1/model.stl")
    assert payload["iterations"][0]["render_images"][0]["url"].endswith("/api/files/run-demo/1/renders/iso_front.png")
    assert payload["iterations"][0]["revision_brief"] == "修复前挡边"

    summaries = list_run_summaries(tmp_path)
    assert summaries[0]["run_id"] == "run-demo"
    assert summaries[0]["status"] == "success"


def test_build_run_payload_tolerates_invalid_json_artifacts(tmp_path):
    iteration_dir = tmp_path / "run-bad-json" / "1"
    iteration_dir.mkdir(parents=True)
    (iteration_dir / "clarified_spec.json").write_text("", encoding="utf-8")
    (iteration_dir / "physics_review.json").write_text("{bad", encoding="utf-8")

    payload = build_run_payload(tmp_path / "run-bad-json", runs_root=tmp_path)

    assert payload["run_id"] == "run-bad-json"
    assert payload["status"] == "partial"
    assert payload["iterations"][0]["clarified_spec"] == {}
    assert payload["iterations"][0]["physics_review"] == {}


def test_task_record_tracks_stage_updates_and_tokens():
    task = TaskRecord(
        task_id="task-1",
        prompt="生成桌面支架",
        thread_id="thread-1",
        max_iterations=7,
        max_no_improvement=0,
        min_improvement_delta=0.08,
    )

    task.mark_started()
    task.apply_update("clarify_spec", {"run_id": "run-1", "iteration": 1})
    task.apply_update(
        "build_cad",
        {
            "workspace_path": "/tmp/run-1/1",
            "compile_retry_count": 2,
            "token_usage": {"total_tokens": 256, "prompt_tokens": 128, "completion_tokens": 128},
        },
    )

    snapshot = task.to_dict()

    assert snapshot["status"] == "running"
    assert snapshot["run_id"] == "run-1"
    assert snapshot["current_stage"] == "build_cad"
    assert snapshot["compile_retry_count"] == 2
    assert snapshot["token_usage"]["total_tokens"] == 256
    assert snapshot["pipeline_phase"] == "clarifying"
    assert snapshot["run_ready"] is False
    assert snapshot["max_iterations"] == 7
    assert snapshot["runtime_policy"]["max_iterations"] == 7
    assert snapshot["max_no_improvement"] == 0
    assert snapshot["runtime_policy"]["max_no_improvement"] == 0
    assert snapshot["min_improvement_delta"] == 0.08
    assert snapshot["runtime_policy"]["min_improvement_delta"] == 0.08
    assert len(snapshot["stage_history"]) == 3


def test_task_record_reports_run_ready_after_run_dir_exists(tmp_path):
    (tmp_path / "run-1").mkdir()
    task = TaskRecord(task_id="task-1", prompt="生成桌面支架", thread_id="thread-1")
    task.apply_update(
        "ingest_request",
        {
            "run_id": "run-1",
            "pipeline_phase": "generating",
            "final_status": "running",
        },
    )

    snapshot = task.to_dict(runs_root=tmp_path)

    assert snapshot["run_ready"] is True
    assert snapshot["pipeline_phase"] == "generating"
    assert snapshot["pipeline_phase_label"] == "工程生成"


def test_task_record_exposes_failure_snapshot():
    task = TaskRecord(task_id="task-1", prompt="坏代码", thread_id="thread-1")

    task.apply_update(
        "static_validate",
        {
            "compile_status": {
                "stage": "static_validate",
                "success": False,
                "error_message": "语法错误",
            },
            "design_status": {"state": "model_ok", "used_model": True},
            "tool_logs": {"static_validate": "语法错误"},
            "pipeline_phase": "revising",
        },
    )
    task.mark_finished(
        {
            "final_status": "failed",
            "pipeline_phase": "failed",
            "compile_status": task.compile_status,
            "design_status": task.design_status,
            "tool_logs": task.tool_logs,
            "feedback_history": ["工具执行失败（static_validate）：语法错误"],
        }
    )

    snapshot = task.to_dict()

    assert snapshot["status"] == "failed"
    assert snapshot["pipeline_phase"] == "failed"
    assert snapshot["compile_status"]["error_message"] == "语法错误"
    assert snapshot["result_summary"]["compile_error"] == "语法错误"
    assert snapshot["feedback_history"] == ["工具执行失败（static_validate）：语法错误"]
    assert snapshot["tool_logs"]["static_validate"] == "语法错误"


def test_task_record_exposes_awaiting_user_snapshot_and_reserved_response():
    task = TaskRecord(task_id="task-1", prompt="承重支架", thread_id="thread-1")

    task.apply_update(
        "clarify_spec",
        {
            "final_status": "awaiting_user",
            "pipeline_phase": "clarifying",
            "clarification_request": {
                "missing_fields": ["load_vector_n"],
                "assumptions": ["默认 PLA"],
            },
        },
    )
    task.record_clarification({"load_vector_n": [0, 0, -5]})

    snapshot = task.to_dict()

    assert snapshot["status"] == "awaiting_user"
    assert snapshot["final_status"] == "awaiting_user"
    assert snapshot["clarification_request"]["missing_fields"] == ["load_vector_n"]
    assert snapshot["clarification_request"]["user_response"] == {"load_vector_n": [0, 0, -5]}
    assert snapshot["clarification_request"]["resume_status"] == "reserved"


def test_task_record_exposes_success_summary():
    task = TaskRecord(task_id="task-1", prompt="生成桌面支架", thread_id="thread-1")

    task.mark_finished(
        {
            "final_status": "success",
            "pipeline_phase": "completed",
            "workspace_path": "/tmp/run-1/1",
            "compile_status": {"stage": "solve_fea", "success": True},
            "design_status": {"state": "model_ok", "used_model": True},
            "physics_review": {"pass": True},
            "visual_review": {"pass": True, "backend": "remote_model"},
            "fea_results": {"max_disp_mm": 0.3},
            "feedback_history": [],
        }
    )

    snapshot = task.to_dict()

    assert snapshot["status"] == "success"
    assert snapshot["pipeline_phase_label"] == "完成"
    assert snapshot["result_summary"]["physics_pass"] is True
    assert snapshot["result_summary"]["visual_backend"] == "remote_model"
    assert snapshot["result_summary"]["max_disp_mm"] == 0.3


def test_web_service_records_reserved_clarification(tmp_path):
    service = TextCADWebService(runs_root=tmp_path)
    task_id = "task-1"
    service.tasks._tasks[task_id] = TaskRecord(task_id=task_id, prompt="需要补参的支架", thread_id="thread-1")

    snapshot = service.record_task_clarification(task_id, {"load_vector_n": [0, 0, -1]})

    assert snapshot is not None
    assert snapshot["clarification_request"]["resume_status"] == "reserved"


def test_runtime_policy_snapshot_and_policy_validation(monkeypatch):
    monkeypatch.delenv("TEXTCAD_MAX_ITERATIONS", raising=False)
    monkeypatch.setenv("TEXTCAD_DEFAULT_MAX_ITERATIONS", "6")
    monkeypatch.setenv("TEXTCAD_MAX_NO_IMPROVEMENT", "4")

    policy = _runtime_policy_snapshot(max_no_improvement=0, min_improvement_delta=0.12)

    assert policy["max_iterations"] == 6
    assert policy["max_iterations_source"] == "TEXTCAD_DEFAULT_MAX_ITERATIONS"
    assert policy["max_no_improvement"] == 0
    assert policy["min_improvement_delta"] == 0.12
    assert _coerce_max_iterations("", default=5) == 5
    assert _coerce_max_iterations("8") == 8
    assert _coerce_max_no_improvement("", default=3) == 3
    assert _coerce_max_no_improvement("0") == 0
    assert _coerce_min_improvement_delta("", default=0.05) == 0.05
    assert _coerce_min_improvement_delta("0.15") == 0.15

    with pytest.raises(ValueError):
        _coerce_max_iterations("0")
    with pytest.raises(ValueError):
        _coerce_max_iterations("not-a-number")
    with pytest.raises(ValueError):
        _coerce_max_no_improvement("-1")
    with pytest.raises(ValueError):
        _coerce_min_improvement_delta("1.5")


def test_web_service_health_exposes_runtime_without_secret_values(tmp_path, monkeypatch):
    monkeypatch.setenv("TEXTCAD_DESIGN_MODEL", "qwen3.6-plus")
    monkeypatch.setenv("TEXTCAD_DESIGN_PROVIDER", "openai")
    monkeypatch.setenv("TEXTCAD_DESIGN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("TEXTCAD_DESIGN_API_KEY", "secret-key")
    monkeypatch.setenv("TEXTCAD_DESIGN_TIMEOUT_S", "180")
    monkeypatch.setenv("TEXTCAD_DESIGN_ENABLE_THINKING", "false")

    (tmp_path / "run-1").mkdir()
    service = TextCADWebService(runs_root=tmp_path)

    health = service.get_health()

    assert health["status"] == "ok"
    assert health["runs_root_exists"] is True
    assert health["run_count"] == 1
    assert health["model_policy"]["design"]["model"] == "qwen3.6-plus"
    assert health["model_policy"]["design"]["api_key_configured"] is True
    assert health["model_policy"]["design"]["timeout_s"] == 180.0
    assert "secret-key" not in json.dumps(health)


def test_resolve_run_file_rejects_escape(tmp_path):
    run_dir = tmp_path / "run-safe" / "1"
    run_dir.mkdir(parents=True)
    (run_dir / "model.stl").write_text("demo", encoding="utf-8")

    assert resolve_run_file(tmp_path, "run-safe", 1, "model.stl") == run_dir / "model.stl"

    with pytest.raises(FileNotFoundError):
        resolve_run_file(tmp_path, "run-safe", 1, "../secret.txt")


def test_resolve_web_asset_rejects_escape():
    asset = resolve_web_asset("index.html")
    assert asset.name == "index.html"
    assert resolve_web_asset("favicon.svg").name == "favicon.svg"

    with pytest.raises(FileNotFoundError):
        resolve_web_asset("../secret.txt")
