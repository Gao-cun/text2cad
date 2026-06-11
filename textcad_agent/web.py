from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from .agent import AgentRuntime, create_agent
from .run import SINGLE_RUN_STAGE_LABELS, SINGLE_RUN_STAGE_ORDER, _iter_stream_updates
from .tools import RUNS_ROOT

WEB_ROOT = Path(__file__).resolve().parent / "webapp"

PIPELINE_PHASE_LABELS = {
    "clarifying": "需求澄清",
    "generating": "工程生成",
    "reviewing": "VLM/FEA 审查",
    "revising": "反馈重构",
    "completed": "完成",
    "failed": "失败",
}

MAX_WEB_ITERATIONS = 20
MAX_WEB_NO_IMPROVEMENT = 20


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _runtime_policy_snapshot(
    max_iterations: int | None = None,
    max_no_improvement: int | None = None,
    min_improvement_delta: float | None = None,
) -> dict[str, Any]:
    runtime = AgentRuntime()
    effective_max_iterations = max_iterations if max_iterations is not None else runtime.max_iterations
    effective_max_no_improvement = (
        max_no_improvement if max_no_improvement is not None else _env_int("TEXTCAD_MAX_NO_IMPROVEMENT", 2)
    )
    effective_min_improvement_delta = (
        min_improvement_delta if min_improvement_delta is not None else _env_float("TEXTCAD_MIN_IMPROVEMENT_DELTA", 0.03)
    )
    max_iterations_source = "web_task"
    if max_iterations is None:
        if os.getenv("TEXTCAD_MAX_ITERATIONS"):
            max_iterations_source = "TEXTCAD_MAX_ITERATIONS"
        elif os.getenv("TEXTCAD_DEFAULT_MAX_ITERATIONS"):
            max_iterations_source = "TEXTCAD_DEFAULT_MAX_ITERATIONS"
        else:
            max_iterations_source = "code_default"
    return {
        "max_iterations": effective_max_iterations,
        "max_iterations_source": max_iterations_source,
        "max_compile_retries_per_iteration": runtime.max_compile_retries_per_iteration,
        "max_no_improvement": effective_max_no_improvement,
        "min_improvement_delta": effective_min_improvement_delta,
        "repair_max_change_ratio": _env_float("TEXTCAD_REPAIR_MAX_CHANGE_RATIO", 0.60),
        "web_max_iterations_limit": MAX_WEB_ITERATIONS,
        "web_max_no_improvement_limit": MAX_WEB_NO_IMPROVEMENT,
    }


def _model_policy_snapshot() -> dict[str, Any]:
    runtime = AgentRuntime()
    roles = {}
    for role in ("clarify", "design", "visual"):
        endpoint = runtime._endpoint_for_role(role)
        roles[role] = {
            "model": endpoint.model,
            "provider": endpoint.provider_hint() or "auto",
            "base_url_configured": bool(endpoint.base_url),
            "api_key_configured": bool(endpoint.resolved_api_key()),
            "timeout_s": runtime._timeout_for_role(role),
        }
    return roles


def _coerce_max_iterations(value: Any, default: int | None = None) -> int:
    if value in (None, ""):
        return _runtime_policy_snapshot()["max_iterations"] if default is None else default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_iterations must be an integer.") from exc
    if parsed < 1 or parsed > MAX_WEB_ITERATIONS:
        raise ValueError(f"max_iterations must be between 1 and {MAX_WEB_ITERATIONS}.")
    return parsed


def _coerce_max_no_improvement(value: Any, default: int | None = None) -> int:
    if value in (None, ""):
        return _runtime_policy_snapshot()["max_no_improvement"] if default is None else default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_no_improvement must be an integer.") from exc
    if parsed < 0 or parsed > MAX_WEB_NO_IMPROVEMENT:
        raise ValueError(f"max_no_improvement must be between 0 and {MAX_WEB_NO_IMPROVEMENT}.")
    return parsed


def _coerce_min_improvement_delta(value: Any, default: float | None = None) -> float:
    if value in (None, ""):
        return _runtime_policy_snapshot()["min_improvement_delta"] if default is None else default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_improvement_delta must be a number.") from exc
    if parsed < 0.0 or parsed > 1.0:
        raise ValueError("min_improvement_delta must be between 0 and 1.")
    return parsed


def _iso_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


def _read_json_file(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_text_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _iteration_dirs(run_dir: Path) -> list[Path]:
    items = [path for path in run_dir.iterdir() if path.is_dir() and path.name.isdigit()]
    return sorted(items, key=lambda item: int(item.name))


def _artifact_url(run_id: str, iteration: int, relative_path: str) -> str:
    return f"/api/files/{quote(run_id)}/{iteration}/{quote(relative_path, safe='/')}"


def _infer_iteration_status(iteration_payload: dict[str, Any]) -> str:
    visual_pass = (iteration_payload.get("visual_review") or {}).get("pass")
    physics_pass = (iteration_payload.get("physics_review") or {}).get("pass")
    if visual_pass is True and physics_pass is True and iteration_payload["artifacts"].get("stl"):
        return "success"
    if iteration_payload["artifacts"].get("stl"):
        return "artifact_ready"
    return "partial"


def _compact_result_summary(result: dict[str, Any] | None, *, fallback_error: str = "") -> dict[str, Any]:
    result = result or {}
    compile_status = result.get("compile_status") or {}
    design_status = result.get("design_status") or {}
    physics_review = result.get("physics_review") or {}
    visual_review = result.get("visual_review") or {}
    fea_results = result.get("fea_results") or {}

    return {
        "final_status": result.get("final_status") or ("failed" if fallback_error else "running"),
        "stop_reason": result.get("stop_reason") or "",
        "best_iteration": result.get("best_iteration"),
        "best_score": result.get("best_score"),
        "final_score": result.get("final_score"),
        "returned_model_source": result.get("returned_model_source") or "",
        "pipeline_phase": result.get("pipeline_phase") or "",
        "phase_label": PIPELINE_PHASE_LABELS.get(str(result.get("pipeline_phase") or ""), ""),
        "workspace_path": result.get("workspace_path") or "",
        "compile_stage": compile_status.get("stage", ""),
        "compile_success": compile_status.get("success"),
        "compile_error": compile_status.get("error_message") or fallback_error,
        "design_state": design_status.get("state", ""),
        "design_error": design_status.get("error_message", ""),
        "physics_pass": physics_review.get("pass"),
        "visual_pass": visual_review.get("pass"),
        "visual_backend": visual_review.get("backend", ""),
        "max_disp_mm": fea_results.get("max_disp_mm"),
        "latest_revision_brief": result.get("latest_revision_brief") or "",
        "feedback_count": len(result.get("feedback_history") or []),
    }


def build_iteration_payload(run_id: str, iteration_dir: Path, runs_root: Path = RUNS_ROOT) -> dict[str, Any]:
    iteration = int(iteration_dir.name)
    render_dir = iteration_dir / "renders"
    render_images = []
    if render_dir.exists():
        for image_path in sorted(render_dir.glob("*.png")):
            render_images.append(
                {
                    "name": image_path.name,
                    "url": _artifact_url(run_id, iteration, f"renders/{image_path.name}"),
                }
            )

    artifacts = {
        "stl": _artifact_url(run_id, iteration, "model.stl") if (iteration_dir / "model.stl").exists() else "",
        "step": _artifact_url(run_id, iteration, "model.step") if (iteration_dir / "model.step").exists() else "",
        "mesh": _artifact_url(run_id, iteration, "model.msh") if (iteration_dir / "model.msh").exists() else "",
        "vtk": _artifact_url(run_id, iteration, "fea_result.vtk") if (iteration_dir / "fea_result.vtk").exists() else "",
        "generated_model": (
            _artifact_url(run_id, iteration, "generated_model.py") if (iteration_dir / "generated_model.py").exists() else ""
        ),
        "analysis_config": (
            _artifact_url(run_id, iteration, "analysis_config.json")
            if (iteration_dir / "analysis_config.json").exists()
            else ""
        ),
        "clarified_spec": (
            _artifact_url(run_id, iteration, "clarified_spec.json")
            if (iteration_dir / "clarified_spec.json").exists()
            else ""
        ),
        "render_config": (
            _artifact_url(run_id, iteration, "render_config.json") if (iteration_dir / "render_config.json").exists() else ""
        ),
    }

    payload = {
        "iteration": iteration,
        "workspace_path": str(iteration_dir),
        "artifacts": artifacts,
        "render_images": render_images,
        "clarified_spec": _read_json_file(iteration_dir / "clarified_spec.json") or {},
        "analysis_config": _read_json_file(iteration_dir / "analysis_config.json") or {},
        "render_config": _read_json_file(iteration_dir / "render_config.json") or {},
        "physics_review": _read_json_file(iteration_dir / "physics_review.json") or {},
        "visual_review": _read_json_file(iteration_dir / "visual_review.json") or {},
        "scale_metadata": _read_json_file(iteration_dir / "renders" / "render_scale.json") or {},
        "generated_model_code": _read_text_file(iteration_dir / "generated_model.py"),
        "engineering_prompt": _read_text_file(iteration_dir / "engineering_prompt.txt"),
        "design_request": _read_text_file(iteration_dir / "design_request.txt"),
        "revision_brief": _read_text_file(iteration_dir / "revision_brief.txt"),
        "physics_report": _read_text_file(iteration_dir / "physics_report.txt"),
    }
    payload["status"] = _infer_iteration_status(payload)
    return payload


def build_run_payload(run_dir: Path, runs_root: Path = RUNS_ROOT) -> dict[str, Any]:
    run_id = run_dir.name
    iteration_payloads = [build_iteration_payload(run_id, item, runs_root=runs_root) for item in _iteration_dirs(run_dir)]
    latest = iteration_payloads[-1] if iteration_payloads else {}
    first = iteration_payloads[0] if iteration_payloads else {}
    first_spec = first.get("clarified_spec") or {}
    latest_spec = latest.get("clarified_spec") or {}

    visual_pass = (latest.get("visual_review") or {}).get("pass")
    physics_pass = (latest.get("physics_review") or {}).get("pass")
    if visual_pass is True and physics_pass is True and (latest.get("artifacts") or {}).get("stl"):
        status = "success"
    elif iteration_payloads:
        status = latest.get("status", "partial")
    else:
        status = "empty"

    return {
        "run_id": run_id,
        "status": status,
        "updated_at": _iso_timestamp(run_dir.stat().st_mtime),
        "iteration_count": len(iteration_payloads),
        "latest_iteration": latest.get("iteration"),
        "request_summary": latest_spec.get("request_summary") or first_spec.get("request_summary") or "",
        "object_type": latest_spec.get("object_type") or first_spec.get("object_type") or "",
        "design_brief": latest_spec.get("design_brief") or first_spec.get("design_brief") or "",
        "iterations": iteration_payloads,
    }


def list_run_summaries(runs_root: Path = RUNS_ROOT) -> list[dict[str, Any]]:
    if not runs_root.exists():
        return []

    items: list[dict[str, Any]] = []
    for run_dir in sorted(
        [path for path in runs_root.iterdir() if path.is_dir()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        summary = build_run_payload(run_dir, runs_root=runs_root)
        items.append(
            {
                "run_id": summary["run_id"],
                "status": summary["status"],
                "updated_at": summary["updated_at"],
                "iteration_count": summary["iteration_count"],
                "latest_iteration": summary["latest_iteration"],
                "request_summary": summary["request_summary"],
                "object_type": summary["object_type"],
                "design_brief": summary["design_brief"],
            }
        )
    return items


def resolve_run_file(runs_root: Path, run_id: str, iteration: int, relative_path: str) -> Path:
    base = (runs_root / run_id / str(iteration)).resolve()
    candidate = (base / relative_path).resolve()
    if base not in candidate.parents and candidate != base:
        raise FileNotFoundError("path escapes run directory")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return candidate


def resolve_web_asset(relative_path: str) -> Path:
    candidate = (WEB_ROOT / relative_path).resolve()
    if WEB_ROOT not in candidate.parents and candidate != WEB_ROOT:
        raise FileNotFoundError("path escapes web root")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate


@dataclass
class TaskRecord:
    task_id: str
    prompt: str
    thread_id: str
    max_iterations: int = field(default_factory=lambda: _runtime_policy_snapshot()["max_iterations"])
    max_no_improvement: int = field(default_factory=lambda: _runtime_policy_snapshot()["max_no_improvement"])
    min_improvement_delta: float = field(default_factory=lambda: _runtime_policy_snapshot()["min_improvement_delta"])
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    status: str = "queued"
    current_stage: str = "ingest_request"
    iteration: int = 1
    compile_retry_count: int = 0
    token_usage: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    workspace_path: str = ""
    final_status: str = "running"
    pipeline_phase: str = "clarifying"
    compile_status: dict[str, Any] = field(default_factory=dict)
    design_status: dict[str, Any] = field(default_factory=dict)
    clarification_request: dict[str, Any] = field(default_factory=dict)
    feedback_history: list[str] = field(default_factory=list)
    tool_logs: dict[str, str] = field(default_factory=dict)
    error: str = ""
    result: dict[str, Any] | None = None
    stage_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._append_stage(self.current_stage)

    def _append_stage(self, stage_name: str) -> None:
        self.stage_history.append(
            {
                "stage": stage_name,
                "label": SINGLE_RUN_STAGE_LABELS.get(stage_name, stage_name),
                "at": _iso_timestamp(time.time()),
                "iteration": self.iteration,
                "pipeline_phase": self.pipeline_phase,
                "pipeline_phase_label": PIPELINE_PHASE_LABELS.get(self.pipeline_phase, self.pipeline_phase),
            }
        )

    def apply_update(self, stage_name: str, payload: dict[str, Any]) -> None:
        if "iteration" in payload:
            self.iteration = payload["iteration"]
        if "compile_retry_count" in payload:
            self.compile_retry_count = payload["compile_retry_count"]
        if "token_usage" in payload and isinstance(payload["token_usage"], dict):
            self.token_usage = payload["token_usage"]
        if "run_id" in payload:
            self.run_id = payload["run_id"]
        if "workspace_path" in payload:
            self.workspace_path = payload["workspace_path"]
        if "final_status" in payload:
            self.final_status = payload["final_status"]
            if payload["final_status"] == "awaiting_user":
                self.status = "awaiting_user"
        if "pipeline_phase" in payload:
            self.pipeline_phase = str(payload["pipeline_phase"])
        if "compile_status" in payload and isinstance(payload["compile_status"], dict):
            self.compile_status = payload["compile_status"]
        if "design_status" in payload and isinstance(payload["design_status"], dict):
            self.design_status = payload["design_status"]
        if "clarification_request" in payload and isinstance(payload["clarification_request"], dict):
            self.clarification_request = payload["clarification_request"]
        if "feedback_history" in payload and isinstance(payload["feedback_history"], list):
            self.feedback_history = [str(item) for item in payload["feedback_history"]]
        if "tool_logs" in payload and isinstance(payload["tool_logs"], dict):
            self.tool_logs = {str(key): str(value) for key, value in payload["tool_logs"].items()}
        if stage_name != self.current_stage:
            self.current_stage = stage_name
            self._append_stage(stage_name)

    def mark_started(self) -> None:
        self.status = "running"
        self.started_at = time.time()

    def mark_finished(self, result: dict[str, Any]) -> None:
        self.status = result.get("final_status", "success")
        self.final_status = result.get("final_status", self.final_status)
        self.pipeline_phase = result.get("pipeline_phase", self.pipeline_phase)
        self.finished_at = time.time()
        self.result = result
        self.run_id = result.get("run_id", self.run_id)
        self.workspace_path = result.get("workspace_path", self.workspace_path)
        token_usage = result.get("token_usage")
        if isinstance(token_usage, dict):
            self.token_usage = token_usage
        for attr in ("compile_status", "design_status", "clarification_request", "tool_logs"):
            value = result.get(attr)
            if isinstance(value, dict):
                setattr(self, attr, value)
        feedback = result.get("feedback_history")
        if isinstance(feedback, list):
            self.feedback_history = [str(item) for item in feedback]

    def mark_failed(self, error: str) -> None:
        self.status = "failed"
        self.final_status = "failed"
        self.pipeline_phase = "failed"
        self.error = error
        self.finished_at = time.time()

    def record_clarification(self, response: dict[str, Any]) -> None:
        self.clarification_request = {
            **self.clarification_request,
            "user_response": response,
            "resume_status": "reserved",
            "resume_message": "已记录补充参数；自动续跑接口已预留，后续版本会接入 LangGraph interrupt resume。",
        }

    def to_dict(self, runs_root: Path = RUNS_ROOT) -> dict[str, Any]:
        current_index = (
            SINGLE_RUN_STAGE_ORDER.index(self.current_stage) + 1
            if self.current_stage in SINGLE_RUN_STAGE_ORDER
            else 1
        )
        total = len(SINGLE_RUN_STAGE_ORDER)
        result_for_summary = dict(self.result or {})
        result_for_summary.setdefault("final_status", self.final_status)
        result_for_summary.setdefault("pipeline_phase", self.pipeline_phase)
        result_for_summary.setdefault("workspace_path", self.workspace_path)
        result_for_summary.setdefault("compile_status", self.compile_status)
        result_for_summary.setdefault("design_status", self.design_status)
        result_for_summary.setdefault("feedback_history", self.feedback_history)
        result_for_summary.setdefault("tool_logs", self.tool_logs)
        result_for_summary.setdefault("latest_revision_brief", "")
        runtime_policy = _runtime_policy_snapshot(
            max_iterations=self.max_iterations,
            max_no_improvement=self.max_no_improvement,
            min_improvement_delta=self.min_improvement_delta,
        )
        run_ready = bool(self.run_id and (runs_root / self.run_id).is_dir())
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "thread_id": self.thread_id,
            "max_iterations": self.max_iterations,
            "max_no_improvement": self.max_no_improvement,
            "min_improvement_delta": self.min_improvement_delta,
            "runtime_policy": runtime_policy,
            "created_at": _iso_timestamp(self.created_at),
            "started_at": _iso_timestamp(self.started_at),
            "finished_at": _iso_timestamp(self.finished_at),
            "status": self.status,
            "final_status": self.final_status,
            "pipeline_phase": self.pipeline_phase,
            "pipeline_phase_label": PIPELINE_PHASE_LABELS.get(self.pipeline_phase, self.pipeline_phase),
            "current_stage": self.current_stage,
            "current_stage_label": SINGLE_RUN_STAGE_LABELS.get(self.current_stage, self.current_stage),
            "stage_index": current_index,
            "stage_total": total,
            "progress_ratio": current_index / total,
            "iteration": self.iteration,
            "compile_retry_count": self.compile_retry_count,
            "token_usage": self.token_usage,
            "run_id": self.run_id,
            "run_ready": run_ready,
            "workspace_path": self.workspace_path,
            "error": self.error,
            "compile_status": self.compile_status,
            "design_status": self.design_status,
            "clarification_request": self.clarification_request,
            "feedback_history": list(self.feedback_history),
            "tool_logs": dict(self.tool_logs),
            "result_summary": _compact_result_summary(result_for_summary, fallback_error=self.error),
            "stage_history": list(self.stage_history),
            "result": self.result,
        }


class TaskManager:
    def __init__(self, runs_root: Path = RUNS_ROOT) -> None:
        self.runs_root = runs_root
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)
            return [task.to_dict(self.runs_root) for task in tasks]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return None if task is None else task.to_dict(self.runs_root)

    def record_clarification(self, task_id: str, response: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.record_clarification(response)
            return task.to_dict(self.runs_root)

    def create_task(
        self,
        prompt: str,
        max_iterations: int | None = None,
        max_no_improvement: int | None = None,
        min_improvement_delta: float | None = None,
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:10]
        thread_id = f"textcad-web-{task_id}"
        task = TaskRecord(
            task_id=task_id,
            prompt=prompt,
            thread_id=thread_id,
            max_iterations=_coerce_max_iterations(max_iterations),
            max_no_improvement=_coerce_max_no_improvement(max_no_improvement),
            min_improvement_delta=_coerce_min_improvement_delta(min_improvement_delta),
        )
        with self._lock:
            self._tasks[task_id] = task
        worker = threading.Thread(target=self._run_task, args=(task_id,), daemon=True)
        worker.start()
        return task.to_dict(self.runs_root)

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.mark_started()
            prompt = task.prompt
            thread_id = task.thread_id
            max_iterations = task.max_iterations
            max_no_improvement = task.max_no_improvement
            min_improvement_delta = task.min_improvement_delta

        runtime = AgentRuntime()
        # The web form is an explicit per-task override, so apply it after
        # AgentRuntime has read environment defaults.
        runtime.max_iterations = max_iterations
        app = create_agent(runtime=runtime)
        config = {"configurable": {"thread_id": thread_id}}
        payload = {
            "user_prompt": prompt,
            "max_no_improvement": max_no_improvement,
            "min_improvement_delta": min_improvement_delta,
        }

        try:
            if hasattr(app, "stream"):
                for event in app.stream(payload, config=config, stream_mode="updates"):
                    for stage_name, update in _iter_stream_updates(event):
                        with self._lock:
                            self._tasks[task_id].apply_update(stage_name, update)
            else:
                result = app.invoke(payload, config=config)
                with self._lock:
                    self._tasks[task_id].mark_finished(result)
                return

            if hasattr(app, "get_state"):
                state_snapshot = app.get_state(config)
                result = getattr(state_snapshot, "values", state_snapshot)
            else:
                result = app.invoke(payload, config=config)

            with self._lock:
                self._tasks[task_id].mark_finished(result)
        except Exception as exc:  # pragma: no cover - runtime/provider dependent
            with self._lock:
                self._tasks[task_id].mark_failed(str(exc))


class TextCADWebService:
    def __init__(self, runs_root: Path = RUNS_ROOT) -> None:
        self.runs_root = runs_root
        self.tasks = TaskManager(runs_root=runs_root)

    def list_runs(self) -> list[dict[str, Any]]:
        return list_run_summaries(self.runs_root)

    def get_config(self) -> dict[str, Any]:
        return {"runtime_policy": _runtime_policy_snapshot()}

    def get_health(self) -> dict[str, Any]:
        run_count = len([path for path in self.runs_root.iterdir() if path.is_dir()]) if self.runs_root.exists() else 0
        return {
            "status": "ok",
            "runs_root": str(self.runs_root),
            "runs_root_exists": self.runs_root.exists(),
            "run_count": run_count,
            "runtime_policy": _runtime_policy_snapshot(),
            "model_policy": _model_policy_snapshot(),
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.runs_root / run_id
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError(run_id)
        return build_run_payload(run_dir, runs_root=self.runs_root)

    def get_file(self, run_id: str, iteration: int, relative_path: str) -> Path:
        return resolve_run_file(self.runs_root, run_id, iteration, relative_path)

    def record_task_clarification(self, task_id: str, response: dict[str, Any]) -> dict[str, Any] | None:
        return self.tasks.record_clarification(task_id, response)


class TextCADRequestHandler(BaseHTTPRequestHandler):
    server_version = "TextCADWeb/0.1"

    @property
    def service(self) -> TextCADWebService:
        return self.server.service  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - cosmetic
        return

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        body = path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(path))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/":
            self._send_file(WEB_ROOT / "index.html")
            return
        if path == "/favicon.ico":
            self._send_file(WEB_ROOT / "favicon.svg")
            return
        if path.startswith("/static/"):
            try:
                self._send_file(resolve_web_asset(path.removeprefix("/static/")))
            except FileNotFoundError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "asset not found")
            return
        if path in {"/app.js", "/styles.css"}:
            self._send_file(WEB_ROOT / path.lstrip("/"))
            return
        if path == "/api/tasks":
            self._send_json({"tasks": self.service.tasks.list_tasks()})
            return
        if path == "/api/config":
            self._send_json(self.service.get_config())
            return
        if path == "/api/health":
            self._send_json(self.service.get_health())
            return
        if path.startswith("/api/tasks/"):
            task_id = path.removeprefix("/api/tasks/").strip("/")
            task = self.service.tasks.get_task(task_id)
            if task is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "task not found")
                return
            self._send_json(task)
            return
        if path == "/api/runs":
            self._send_json({"runs": self.service.list_runs()})
            return
        if path.startswith("/api/runs/"):
            run_id = path.removeprefix("/api/runs/").strip("/")
            try:
                self._send_json(self.service.get_run(run_id))
            except FileNotFoundError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "run not found")
            return
        if path.startswith("/api/files/"):
            suffix = path.removeprefix("/api/files/")
            parts = suffix.split("/", 2)
            if len(parts) != 3:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid file path")
                return
            run_id, iteration_text, relative_path = parts
            try:
                iteration = int(iteration_text)
                file_path = self.service.get_file(run_id, iteration, relative_path)
            except (ValueError, FileNotFoundError):
                self._send_error_json(HTTPStatus.NOT_FOUND, "file not found")
                return
            self._send_file(file_path)
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/tasks/") and path.endswith("/clarification"):
            task_id = path.removeprefix("/api/tasks/").removesuffix("/clarification").strip("/")
            try:
                payload = self._read_json_body()
            except (json.JSONDecodeError, ValueError) as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            task = self.service.record_task_clarification(task_id, payload)
            if task is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "task not found")
                return
            self._send_json(task, status=HTTPStatus.ACCEPTED)
            return

        if path != "/api/tasks":
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")
            return

        try:
            payload = self._read_json_body()
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "prompt is required")
            return
        try:
            max_iterations = _coerce_max_iterations(payload.get("max_iterations"))
            max_no_improvement = _coerce_max_no_improvement(payload.get("max_no_improvement"))
            min_improvement_delta = _coerce_min_improvement_delta(payload.get("min_improvement_delta"))
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        task = self.service.tasks.create_task(
            prompt,
            max_iterations=max_iterations,
            max_no_improvement=max_no_improvement,
            min_improvement_delta=min_improvement_delta,
        )
        self._send_json(task, status=HTTPStatus.CREATED)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the TextCAD web console.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the web server to.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind the web server to.")
    parser.add_argument(
        "--strict-port",
        action="store_true",
        help="Fail instead of trying the next available port when --port is already in use.",
    )
    parser.add_argument("--runs-root", default=str(RUNS_ROOT), help="Directory containing TextCAD runs.")
    return parser


def _create_http_server(
    host: str,
    port: int,
    *,
    strict_port: bool = False,
    max_port_attempts: int = 20,
) -> ThreadingHTTPServer:
    attempts = 1 if strict_port else max(1, max_port_attempts)
    last_error: OSError | None = None
    for offset in range(attempts):
        candidate_port = port + offset
        if candidate_port > 65535:
            break
        try:
            return ThreadingHTTPServer((host, candidate_port), TextCADRequestHandler)
        except OSError as exc:
            last_error = exc
            if exc.errno != errno.EADDRINUSE or strict_port:
                raise
    if last_error is not None:
        raise last_error
    raise OSError(errno.EADDRNOTAVAIL, f"No available port found from {port}.")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    service = TextCADWebService(runs_root=Path(args.runs_root).resolve())
    server = _create_http_server(args.host, args.port, strict_port=args.strict_port)
    bound_port = int(server.server_address[1])
    server.service = service  # type: ignore[attr-defined]
    if bound_port != args.port:
        print(f"Port {args.port} is already in use; using {bound_port} instead.")
    print(f"TextCAD web console running at http://{args.host}:{bound_port}")
    print(f"Runs root: {service.runs_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual shutdown
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    raise SystemExit(main())
