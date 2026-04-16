from __future__ import annotations

import argparse
import json
import uuid
from typing import Any

from .agent import create_agent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the TextCAD LangGraph production pipeline.")
    parser.add_argument("prompt", help="Natural-language CAD request.")
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional LangGraph thread id for resumable runs. If omitted, each CLI invocation uses a fresh thread.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full final state as JSON instead of a short summary.",
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    thread_id = args.thread_id or f"textcad-cli-{uuid.uuid4().hex[:8]}"

    app = create_agent()
    config = {"configurable": {"thread_id": thread_id}}
    result = app.invoke({"user_prompt": args.prompt}, config=config)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(_result_summary(result))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
