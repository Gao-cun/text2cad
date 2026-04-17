from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from .agent import create_agent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the TextCAD LangGraph production pipeline.")
    parser.add_argument("prompt", nargs="?", help="Natural-language CAD request.")
    parser.add_argument(
        "--tasks-file",
        default=None,
        help="Optional UTF-8 txt file. Each non-empty line is treated as one task prompt.",
    )
    parser.add_argument(
        "--parallel-workers",
        type=int,
        default=None,
        help="Worker count for --tasks-file mode. If omitted, uses TEXTCAD_BATCH_MAX_WORKERS or min(4, task_count).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable batch progress bar output.",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional LangGraph thread id. In batch mode, this is used as the thread-id prefix.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full final state as JSON. In batch mode, prints a JSON list.",
    )
    return parser


def _result_summary(result: dict[str, Any]) -> str:
    lines = [
        f"status: {result.get('final_status', 'unknown')}",
        f"iteration: {result.get('iteration', 'unknown')}",
    ]
    design_status = result.get("design_status") or {}
    if design_status.get("state"):
        lines.append(f"design_status: {design_status['state']}")
    workspace = result.get("workspace_path")
    if workspace:
        lines.append(f"workspace: {workspace}")

    fea_results = result.get("fea_results") or {}
    if fea_results.get("max_disp_mm") is not None:
        lines.append(f"max_disp_mm: {fea_results['max_disp_mm']:.6f}")
    if fea_results.get("vtk_path"):
        lines.append(f"vtk_path: {fea_results['vtk_path']}")

    vtk_paths = result.get("vtk_paths") or []
    if vtk_paths:
        lines.append(f"vtk_files: {len(vtk_paths)}")

    physics_report = (result.get("physics_report") or "").strip()
    if physics_report:
        lines.append("physics_report:")
        lines.append(physics_report)

    visual_review = result.get("visual_review") or {}
    if visual_review.get("backend"):
        lines.append(f"visual_backend: {visual_review['backend']}")

    feedback = result.get("feedback_history") or []
    if feedback:
        lines.append("feedback:")
        lines.extend(f"- {item}" for item in feedback)

    return "\n".join(lines)


def _parse_positive_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def _resolve_parallel_workers(requested: int | None, task_count: int) -> int:
    if task_count <= 1:
        return 1
    if requested is not None and requested > 0:
        return min(requested, task_count)

    from_env = _parse_positive_int(os.getenv("TEXTCAD_BATCH_MAX_WORKERS"))
    if from_env is not None:
        return min(from_env, task_count)
    return min(4, task_count)


def _load_tasks_from_file(tasks_file: str) -> list[str]:
    path = Path(tasks_file)
    if not path.exists() or not path.is_file():
        raise ValueError(f"tasks file not found: {tasks_file}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    tasks = [line for line in lines if line and not line.startswith("#")]
    if not tasks:
        raise ValueError("tasks file contains no usable prompts (non-empty, non-comment lines).")
    return tasks


def _batch_progress_line(done: int, total: int, width: int = 28) -> str:
    ratio = 1.0 if total <= 0 else done / total
    ratio = min(max(ratio, 0.0), 1.0)
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {done}/{total} ({ratio * 100:5.1f}%)"


def _print_batch_progress(done: int, total: int) -> None:
    print(f"\rbatch progress {_batch_progress_line(done, total)}", end="", file=sys.stderr, flush=True)
    if done >= total:
        print("", file=sys.stderr, flush=True)


def _invoke_once(prompt: str, thread_id: str) -> dict[str, Any]:
    app = create_agent()
    config = {"configurable": {"thread_id": thread_id}}
    return app.invoke({"user_prompt": prompt}, config=config)


def _run_batch_tasks(
    tasks: list[str],
    *,
    thread_prefix: str | None,
    parallel_workers: int | None,
    show_progress: bool,
) -> list[dict[str, Any]]:
    workers = _resolve_parallel_workers(parallel_workers, len(tasks))
    results: list[dict[str, Any] | None] = [None] * len(tasks)

    def batch_thread_id(index: int) -> str:
        prefix = thread_prefix or "textcad-batch"
        return f"{prefix}-{index + 1:03d}-{uuid.uuid4().hex[:6]}"

    if show_progress:
        _print_batch_progress(0, len(tasks))

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map: dict[concurrent.futures.Future[dict[str, Any]], tuple[int, str, str]] = {}
        for index, prompt in enumerate(tasks):
            thread_id = batch_thread_id(index)
            future = executor.submit(_invoke_once, prompt, thread_id)
            future_map[future] = (index, prompt, thread_id)

        for future in concurrent.futures.as_completed(future_map):
            index, prompt, thread_id = future_map[future]
            try:
                result = future.result()
                item = {
                    "task_index": index + 1,
                    "thread_id": thread_id,
                    "prompt": prompt,
                    "error": None,
                    "result": result,
                }
            except Exception as exc:  # pragma: no cover - depends on runtime/provider failures
                item = {
                    "task_index": index + 1,
                    "thread_id": thread_id,
                    "prompt": prompt,
                    "error": str(exc),
                    "result": None,
                }
            results[index] = item
            done += 1
            if show_progress:
                _print_batch_progress(done, len(tasks))

    return [item for item in results if item is not None]


def _batch_summary(batch_results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in batch_results:
        task_index = item.get("task_index", "?")
        prompt = item.get("prompt", "")
        error = item.get("error")
        lines.append(f"task[{task_index}] prompt: {prompt}")
        if error:
            lines.append(f"task[{task_index}] runtime_error: {error}")
            continue

        result = item.get("result") or {}
        lines.append(f"task[{task_index}] status: {result.get('final_status', 'unknown')}")
        lines.append(f"task[{task_index}] iteration: {result.get('iteration', 'unknown')}")
        workspace = result.get("workspace_path")
        if workspace:
            lines.append(f"task[{task_index}] workspace: {workspace}")
        max_disp = (result.get("fea_results") or {}).get("max_disp_mm")
        if max_disp is not None:
            lines.append(f"task[{task_index}] max_disp_mm: {max_disp:.6f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    has_prompt = bool(args.prompt)
    has_tasks_file = bool(args.tasks_file)
    if has_prompt == has_tasks_file:
        parser.error("Provide exactly one input source: PROMPT or --tasks-file.")

    if has_tasks_file:
        try:
            tasks = _load_tasks_from_file(args.tasks_file)
        except ValueError as exc:
            parser.error(str(exc))

        batch_results = _run_batch_tasks(
            tasks,
            thread_prefix=args.thread_id,
            parallel_workers=args.parallel_workers,
            show_progress=not args.no_progress,
        )
        if args.json:
            print(json.dumps(batch_results, ensure_ascii=False, indent=2, default=str))
        else:
            print(_batch_summary(batch_results))
        return 1 if any(item.get("error") for item in batch_results) else 0

    thread_id = args.thread_id or f"textcad-cli-{uuid.uuid4().hex[:8]}"
    result = _invoke_once(args.prompt, thread_id)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(_result_summary(result))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
