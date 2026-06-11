from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from .nodes import (
    make_await_user_clarification_node,
    make_build_cad_node,
    make_build_mesh_node,
    make_clarify_spec_node,
    make_decide_next_node,
    make_design_generate_node,
    make_engineer_spec_node,
    make_feedback_merge_node,
    make_ingest_request_node,
    make_materialize_workspace_node,
    make_physics_report_node,
    make_physics_qa_node,
    make_quality_gate_node,
    make_render_views_node,
    make_revision_brief_node,
    make_solve_fea_node,
    make_static_validate_node,
    make_visual_qa_node,
)
from .prompts import (
    CLARIFY_SYSTEM_PROMPT,
    DESIGN_SYSTEM_PROMPT,
    PHYSICS_REPORT_SYSTEM_PROMPT,
    VISUAL_SYSTEM_PROMPT,
)
from .state import AgentState, ClarifiedSpec, DesignPayload, DesignStatus, PhysicsReview, RenderConfig, VisualReview
from .model_io import (
    PROVIDER_API_KEY_ENV,
    ModelEndpoint,
    encode_image_as_data_url as _encode_image_as_data_url,
    extract_response_token_usage as _extract_response_token_usage,
    extract_text_content as _extract_text_content,
    is_qwen_mixed_thinking_model as _is_qwen_mixed_thinking_model,
    load_design_json as _load_design_json,
    load_json_payload as _load_json_payload,
    strip_thinking_blocks as _strip_thinking_blocks,
    supports_enable_thinking_param as _supports_enable_thinking_param,
    to_bool_env as _to_bool_env,
    to_float_env as _to_float_env,
    to_int as _to_int,
    to_positive_int_env as _to_positive_int_env,
)
from .prompt_builders import (
    build_clarify_request as _build_clarify_request,
    build_design_request as _build_design_request,
    build_engineering_prompt as _build_engineering_prompt,
    build_physics_report_request as _build_physics_report_request,
    build_visual_review_request as _build_visual_review_request,
)

load_dotenv()

ROLE_NAMES = ("clarify", "design", "visual")
HIGH_RISK_FIELDS: set[str] = set()


def _bbox_for_beam_face(length_mm: float, width_mm: float, height_mm: float, x_value: float) -> list[float]:
    return [
        x_value,
        -width_mm / 2.0,
        -height_mm / 2.0,
        x_value,
        width_mm / 2.0,
        height_mm / 2.0,
    ]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in text or keyword in lowered for keyword in keywords)


def _parse_dimensions(prompt: str) -> tuple[float | None, float | None, float | None]:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)",
        r"长\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?\D+宽\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?\D+高\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            values = tuple(float(item) for item in match.groups())
            return values
    return None, None, None


def _parse_load_vector(prompt: str) -> list[float] | None:
    magnitude_match = re.search(r"(\d+(?:\.\d+)?)\s*N", prompt, flags=re.IGNORECASE)
    if not magnitude_match:
        return None
    magnitude = float(magnitude_match.group(1))
    lowered = prompt.lower()
    if "向下" in prompt or "down" in lowered:
        return [0.0, -magnitude, 0.0]
    if "向上" in prompt or "upward" in lowered or "up " in lowered:
        return [0.0, magnitude, 0.0]
    if "向右" in prompt or "right" in lowered:
        return [magnitude, 0.0, 0.0]
    if "向左" in prompt or "left" in lowered:
        return [-magnitude, 0.0, 0.0]
    if "向前" in prompt or "forward" in lowered or "front" in lowered:
        return [0.0, 0.0, magnitude]
    if "向后" in prompt or "backward" in lowered or "back" in lowered:
        return [0.0, 0.0, -magnitude]
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if match:
        return float(match.group(0))
    return None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _normalize_vector(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 3:
        parsed = [_to_float(item) for item in value]
        if all(item is not None for item in parsed):
            return [float(item) for item in parsed if item is not None]
    if not isinstance(value, dict):
        return None

    components = value.get("components") or value.get("vector") or value.get("xyz")
    if isinstance(components, list) and len(components) == 3:
        parsed = [_to_float(item) for item in components]
        if all(item is not None for item in parsed):
            return [float(item) for item in parsed if item is not None]

    magnitude = _to_float(value.get("magnitude_N") or value.get("magnitude") or value.get("value"))
    direction_text = " ".join(
        str(part)
        for part in (
            value.get("direction"),
            value.get("direction_text"),
            value.get("direction_description"),
            value.get("description"),
        )
        if part
    ).lower()
    if magnitude is None:
        magnitude = 1.0
    if any(token in direction_text for token in ("向下", "down", "-y", "negative y")):
        return [0.0, -magnitude, 0.0]
    if any(token in direction_text for token in ("向上", "up", "+y", "positive y")):
        return [0.0, magnitude, 0.0]
    if any(token in direction_text for token in ("向右", "right", "+x", "positive x")):
        return [magnitude, 0.0, 0.0]
    if any(token in direction_text for token in ("向左", "left", "-x", "negative x")):
        return [-magnitude, 0.0, 0.0]
    if any(token in direction_text for token in ("向前", "forward", "+z", "positive z")):
        return [0.0, 0.0, magnitude]
    if any(token in direction_text for token in ("向后", "back", "backward", "-z", "negative z")):
        return [0.0, 0.0, -magnitude]
    return None


def _normalize_bbox(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 6:
        parsed = [_to_float(item) for item in value]
        if all(item is not None for item in parsed):
            return [float(item) for item in parsed if item is not None]
    return None


def _plane_x_from_bbox(bbox: list[float]) -> float:
    return float((bbox[0] + bbox[3]) / 2.0)


def _default_design_profile(prompt: str) -> dict[str, Any]:
    if _contains_any(prompt, ("手机支架", "phone stand", "phone holder", "mobile stand", "手机座")):
        return {
            "object_type": "phone_stand",
            "design_brief": "一个可3D打印的桌面手机支架，包含后倾支撑背板、承托底座和前挡边。",
            "design_goals": [
                "稳定承托手机",
                "结构连续、便于打印",
                "正面留出可视区域，避免完全遮挡设备",
            ],
            "style_keywords": ["clean", "minimal", "functional"],
            "dimensions": (95.0, 78.0, 110.0),
            "visual_requirements": [
                "应有明显后倾支撑面",
                "前端应有挡边避免手机滑落",
                "整体应像桌面手机支架而非实心方块",
            ],
            "assumptions": [
                "未指定设备尺寸时，按常见 6 到 6.7 英寸手机估算支架比例。",
                "默认采用一体式打印结构，优先保证支撑和可打印性。",
            ],
        }

    if _contains_any(prompt, ("支架", "bracket", "holder", "mount", "stand")):
        return {
            "object_type": "stand_bracket",
            "design_brief": "一个通用的 L 形支架或托架，优先保证承托、连接和打印稳定性。",
            "design_goals": [
                "满足支撑/固定类用途",
                "保留足够结构厚度",
                "避免难以打印的悬空特征",
            ],
            "style_keywords": ["structural", "practical"],
            "dimensions": (80.0, 60.0, 90.0),
            "visual_requirements": [
                "应具备明显的承托面或立板",
                "整体轮廓应像支架而非简单立方体",
            ],
            "assumptions": [
                "未给出详细安装对象时，默认生成通用桌面/安装支架比例。",
            ],
        }

    if _contains_any(prompt, ("盒", "盒子", "收纳", "tray", "box", "container", "bin")):
        return {
            "object_type": "tray_box",
            "design_brief": "一个开口的收纳托盘或浅盒体，适合 3D 打印。",
            "design_goals": [
                "保留内部容积",
                "壁厚均匀",
                "避免过重的实心体",
            ],
            "style_keywords": ["clean", "utility"],
            "dimensions": (120.0, 80.0, 45.0),
            "visual_requirements": [
                "应为开口容器，而不是实心块",
                "外观应具备明显的壁厚和内部空腔",
            ],
            "assumptions": [
                "未指定尺寸时，默认生成桌面收纳尺度的浅盒。",
            ],
        }

    return {
        "object_type": "generic_printable_object",
        "design_brief": "一个满足需求语义的可打印实体，优先保证结构清晰、可执行和可审查。",
        "design_goals": [
            "优先满足用户描述的核心用途",
            "保持几何可打印、可网格化",
            "避免退化成没有语义的立方体",
        ],
        "style_keywords": ["printable", "clean"],
        "dimensions": (80.0, 60.0, 40.0),
        "visual_requirements": [prompt],
        "assumptions": [
            "未提供细节时，按通用桌面 3D 打印件的比例自动补全尺寸和结构。",
        ],
    }


def _phone_stand_code(backend: dict[str, Any]) -> str:
    return (
        "from __future__ import annotations\n\n"
        "import cadquery as cq\n\n"
        "def build_model():\n"
        f"    depth = {backend['length_mm']}\n"
        f"    width = {backend['width_mm']}\n"
        f"    height = {backend['height_mm']}\n"
        "    lip_height = max(10.0, min(18.0, height * 0.13))\n"
        "    support_x = max(18.0, depth * 0.19)\n"
        "    shelf_x = max(support_x + 22.0, depth * 0.57)\n"
        "    z_bottom = -height / 2.0\n"
        "    z_top = height / 2.0\n"
        "    profile = (\n"
        '        cq.Workplane("XZ")\n'
        "        .polyline(\n"
        "            [\n"
        "                (0.0, z_bottom),\n"
        "                (depth, z_bottom),\n"
        "                (depth, z_bottom + lip_height),\n"
        "                (shelf_x, z_bottom + lip_height),\n"
        "                (support_x, z_top),\n"
        "                (0.0, z_top),\n"
        "            ]\n"
        "        )\n"
        "        .close()\n"
        "    )\n"
        "    body = profile.extrude(width).translate((0.0, -width / 2.0, 0.0))\n"
        "    inner_width = max(width - 16.0, width * 0.6)\n"
        "    cutout = (\n"
        '        cq.Workplane("XZ")\n'
        "        .polyline(\n"
        "            [\n"
        "                (12.0, z_bottom + 8.0),\n"
        "                (depth - 14.0, z_bottom + 8.0),\n"
        "                (max(support_x + 14.0, shelf_x - 10.0), z_bottom + lip_height + 2.0),\n"
        "                (support_x + 12.0, z_top - 14.0),\n"
        "                (12.0, z_top - 14.0),\n"
        "            ]\n"
        "        )\n"
        "        .close()\n"
        "        .extrude(inner_width)\n"
        "        .translate((0.0, -inner_width / 2.0, 0.0))\n"
        "    )\n"
        "    cable_slot = (\n"
        '        cq.Workplane("XY")\n'
        "        .box(max(12.0, depth * 0.18), max(18.0, width * 0.32), max(6.0, lip_height * 0.7))\n"
        "        .translate((depth * 0.52, 0.0, z_bottom + max(6.0, lip_height * 0.35)))\n"
        "    )\n"
        "    return body.cut(cutout).cut(cable_slot)\n"
    )


def _stand_bracket_code(backend: dict[str, Any]) -> str:
    return (
        "from __future__ import annotations\n\n"
        "import cadquery as cq\n\n"
        "def build_model():\n"
        f"    length = {backend['length_mm']}\n"
        f"    width = {backend['width_mm']}\n"
        f"    height = {backend['height_mm']}\n"
        "    flange = max(6.0, min(14.0, min(length, height) * 0.12))\n"
        "    upright = max(18.0, length * 0.28)\n"
        "    z_bottom = -height / 2.0\n"
        "    z_top = height / 2.0\n"
        "    profile = (\n"
        '        cq.Workplane("XZ")\n'
        "        .polyline(\n"
        "            [\n"
        "                (0.0, z_bottom),\n"
        "                (length, z_bottom),\n"
        "                (length, z_bottom + flange),\n"
        "                (upright, z_bottom + flange),\n"
        "                (upright, z_top),\n"
        "                (0.0, z_top),\n"
        "            ]\n"
        "        )\n"
        "        .close()\n"
        "    )\n"
        "    body = profile.extrude(width).translate((0.0, -width / 2.0, 0.0))\n"
        "    slot_width = max(width - 14.0, width * 0.55)\n"
        "    cutout = (\n"
        '        cq.Workplane("XZ")\n'
        "        .polyline(\n"
        "            [\n"
        "                (flange + 8.0, z_bottom + flange + 4.0),\n"
        "                (length - 10.0, z_bottom + flange + 4.0),\n"
        "                (length - 10.0, z_bottom + flange + 18.0),\n"
        "                (upright + 10.0, z_top - 10.0),\n"
        "                (flange + 8.0, z_top - 10.0),\n"
        "            ]\n"
        "        )\n"
        "        .close()\n"
        "        .extrude(slot_width)\n"
        "        .translate((0.0, -slot_width / 2.0, 0.0))\n"
        "    )\n"
        "    return body.cut(cutout)\n"
    )


def _tray_box_code(backend: dict[str, Any]) -> str:
    return (
        "from __future__ import annotations\n\n"
        "import cadquery as cq\n\n"
        "def build_model():\n"
        f"    length = {backend['length_mm']}\n"
        f"    width = {backend['width_mm']}\n"
        f"    height = {backend['height_mm']}\n"
        "    wall = max(2.4, min(4.0, min(length, width, height) * 0.08))\n"
        "    floor = max(2.8, wall)\n"
        '    outer = cq.Workplane("XY").box(length, width, height).translate((length / 2.0, 0.0, 0.0))\n'
        '    inner = cq.Workplane("XY").box(length - 2.0 * wall, width - 2.0 * wall, height - floor).translate((length / 2.0, 0.0, floor / 2.0))\n'
        "    return outer.cut(inner)\n"
    )


@dataclass
class AgentRuntime:
    displacement_limit_mm: float = 5.0
    stress_limit_mpa: float = 30.0
    max_iterations: int = 3
    max_compile_retries_per_iteration: int = 3
    clarify_model_name: str = "gpt-4.1-mini"
    design_model_name: str = "gpt-4.1"
    visual_model_name: str = "gpt-4.1-mini"
    role_model_configs: dict[str, ModelEndpoint] = field(default_factory=dict)
    clarify_fn: Callable[[str, list[str]], ClarifiedSpec] | None = None
    design_fn: Callable[[str, dict[str, Any], list[str]], DesignPayload] | None = None
    visual_review_fn: Callable[[str, dict[str, Any], list[str], list[str]], VisualReview] | None = None
    physics_report_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], str] | None = None
    _model_cache: dict[str, Any] = field(default_factory=dict)
    _token_usage_totals: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    _token_usage_by_role: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Allow runtime loop limit to be overridden by environment variables.
        self.max_iterations = self._max_iterations_from_env(default=self.max_iterations)
        self.max_compile_retries_per_iteration = self._max_compile_retries_from_env(
            default=self.max_compile_retries_per_iteration
        )

    def _max_iterations_from_env(self, default: int) -> int:
        for env_name in ("TEXTCAD_MAX_ITERATIONS", "TEXTCAD_DEFAULT_MAX_ITERATIONS"):
            parsed = _to_positive_int_env(os.getenv(env_name))
            if parsed is not None:
                return parsed
        return default

    def _max_compile_retries_from_env(self, default: int) -> int:
        for env_name in ("TEXTCAD_MAX_COMPILE_RETRIES", "TEXTCAD_DEFAULT_MAX_COMPILE_RETRIES"):
            parsed = _to_positive_int_env(os.getenv(env_name))
            if parsed is not None:
                return parsed
        return default

    def _record_token_usage(self, role: str | None, response: Any) -> None:
        usage = _extract_response_token_usage(response)
        if not usage:
            return

        for key, value in usage.items():
            self._token_usage_totals[key] = self._token_usage_totals.get(key, 0) + int(value)

        if role is None:
            return

        role_totals = self._token_usage_by_role.setdefault(
            role,
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        for key, value in usage.items():
            role_totals[key] = role_totals.get(key, 0) + int(value)

    def token_usage_snapshot(self) -> dict[str, Any]:
        if not any(self._token_usage_totals.values()) and not self._token_usage_by_role:
            return {}
        return {
            **self._token_usage_totals,
            "by_role": {role: dict(usage) for role, usage in self._token_usage_by_role.items()},
        }

    def _has_role_specific_env_config(self, role: str) -> bool:
        prefix = f"TEXTCAD_{role.upper()}_"
        return any(
            os.getenv(f"{prefix}{suffix}") is not None
            for suffix in ("MODEL", "PROVIDER", "BASE_URL", "API_KEY", "TEMPERATURE")
        )

    def _timeout_for_role(self, role: str, endpoint: ModelEndpoint | None = None) -> float:
        endpoint = endpoint or self._endpoint_for_role(role)

        role_timeout = _to_float_env(os.getenv(f"TEXTCAD_{role.upper()}_TIMEOUT_S"))
        if role_timeout is not None and role_timeout > 0:
            base_timeout = role_timeout
        else:
            default_timeout = _to_float_env(os.getenv("TEXTCAD_DEFAULT_TIMEOUT_S"))
            if default_timeout is not None and default_timeout > 0:
                base_timeout = default_timeout
            else:
                role_defaults = {"visual": 90.0, "design": 180.0, "clarify": 90.0}
                base_timeout = role_defaults.get(role, 60.0)

        if self._enable_thinking_for_role(role, endpoint) is not True:
            return base_timeout

        role_thinking_timeout = _to_float_env(os.getenv(f"TEXTCAD_{role.upper()}_THINKING_TIMEOUT_S"))
        if role_thinking_timeout is not None and role_thinking_timeout > 0:
            return role_thinking_timeout

        default_thinking_timeout = _to_float_env(os.getenv("TEXTCAD_DEFAULT_THINKING_TIMEOUT_S"))
        if default_thinking_timeout is not None and default_thinking_timeout > 0:
            return default_thinking_timeout

        # Reasoning mode may take significantly longer than direct mode.
        return max(base_timeout, 1200.0)

    def _enable_thinking_for_role(self, role: str, endpoint: ModelEndpoint) -> bool | None:
        role_setting = _to_bool_env(os.getenv(f"TEXTCAD_{role.upper()}_ENABLE_THINKING"))
        if role_setting is not None:
            return role_setting

        default_setting = _to_bool_env(os.getenv("TEXTCAD_DEFAULT_ENABLE_THINKING"))
        if default_setting is not None:
            return default_setting

        if _is_qwen_mixed_thinking_model(endpoint.model):
            return False

        return None

    def _extra_body_for_role(self, role: str, endpoint: ModelEndpoint) -> dict[str, Any] | None:
        if not _supports_enable_thinking_param(endpoint.model):
            return None

        enable_thinking = self._enable_thinking_for_role(role, endpoint)
        if enable_thinking is None:
            return None
        return {"enable_thinking": enable_thinking}

    def _prefer_user_only_messages(self, endpoint: ModelEndpoint) -> bool:
        provider_text = " ".join(
            part for part in (endpoint.model, endpoint.base_url or "", endpoint.provider_hint() or "") if part
        ).lower()
        return _is_qwen_mixed_thinking_model(endpoint.model) or "dashscope" in provider_text

    def _text_messages(self, role: str, system_prompt: str, user_text: str) -> list[BaseMessage]:
        endpoint = self._endpoint_for_role(role)
        if self._prefer_user_only_messages(endpoint):
            prompt = ChatPromptTemplate.from_messages(
                [("human", "请遵守以下系统指令：\n{system_prompt}\n\n{user_text}")]
            )
            return prompt.format_messages(system_prompt=system_prompt.strip(), user_text=user_text.strip())
        prompt = ChatPromptTemplate.from_messages([("system", "{system_prompt}"), ("human", "{user_text}")])
        return prompt.format_messages(system_prompt=system_prompt, user_text=user_text)

    def _multimodal_messages(self, role: str, system_prompt: str, content: list[dict[str, Any]]) -> list[BaseMessage]:

        endpoint = self._endpoint_for_role(role)
        if self._prefer_user_only_messages(endpoint):
            merged_content = list(content)
            if merged_content and merged_content[0].get("type") == "text":
                merged_content[0] = {
                    "type": "text",
                    "text": (
                        f"请遵守以下系统指令：\n{system_prompt.strip()}\n\n"
                        f"{merged_content[0].get('text', '').strip()}"
                    ),
                }
            else:
                merged_content.insert(0, {"type": "text", "text": f"请遵守以下系统指令：\n{system_prompt.strip()}"})
            return [HumanMessage(content=merged_content)]
        return [SystemMessage(content=system_prompt), HumanMessage(content=content)]

    def build_clarify_request(self, prompt: str, feedback_history: list[str]) -> str:
        return _build_clarify_request(prompt, feedback_history, self._schema_hint)

    def build_physics_report_request(
        self,
        clarified_spec: dict[str, Any],
        fea_results: dict[str, Any],
        physics_review: dict[str, Any],
    ) -> str:
        return _build_physics_report_request(clarified_spec, fea_results, physics_review)

    def build_visual_review_request(
        self,
        prompt: str,
        clarified_spec: dict[str, Any],
        feedback_history: list[str],
    ) -> str:
        return _build_visual_review_request(prompt, clarified_spec, feedback_history, self._schema_hint)

    def _visual_max_images(self) -> int:
        value = _to_int(os.getenv("TEXTCAD_VISUAL_MAX_IMAGES"))
        if value is None or value <= 0:
            return 3
        return value

    def _visual_max_pixels(self, endpoint: ModelEndpoint) -> int | None:
        value = _to_int(os.getenv("TEXTCAD_VISUAL_MAX_PIXELS"))
        if value is not None and value > 0:
            return value

        endpoint_text = " ".join(
            part for part in (endpoint.model, endpoint.base_url or "", endpoint.provider_hint() or "") if part
        ).lower()
        if "qwen" in endpoint_text or "dashscope" in endpoint_text:
            return 1310720

        return None

    def _select_visual_image_paths(self, image_paths: list[str]) -> list[str]:
        if len(image_paths) <= self._visual_max_images():
            return image_paths

        priority = ("iso_front", "side", "top", "iso_back")
        selected: list[str] = []
        remaining = list(image_paths)

        for name in priority:
            for path in list(remaining):
                if Path(path).stem == name:
                    selected.append(path)
                    remaining.remove(path)
                    break
            if len(selected) >= self._visual_max_images():
                return selected[: self._visual_max_images()]

        selected.extend(remaining)
        return selected[: self._visual_max_images()]

    def build_engineering_prompt(self, prompt: str, clarified_spec: dict[str, Any]) -> str:
        return _build_engineering_prompt(prompt, clarified_spec)

    def build_design_request(
        self,
        prompt: str,
        engineering_prompt: str,
        clarified_spec: dict[str, Any],
        latest_revision_brief: str,
        previous_code: str = "",
        structured_revision: dict[str, Any] | None = None,
        repair_mode: bool = False,
    ) -> str:
        _ = clarified_spec
        return _build_design_request(
            prompt=prompt,
            engineering_prompt=engineering_prompt,
            latest_revision_brief=latest_revision_brief,
            previous_code=previous_code,
            structured_revision=structured_revision,
            repair_mode=repair_mode,
            schema_hint=self._schema_hint,
        )

    def generate_physics_report(
        self,
        clarified_spec: dict[str, Any],
        fea_results: dict[str, Any],
        physics_review: dict[str, Any],
    ) -> tuple[str, str]:
        if self.physics_report_fn is not None:
            report = self.physics_report_fn(clarified_spec, fea_results, physics_review)
            return report, "Physics report used custom physics_report_fn."

        max_disp = fea_results.get("max_disp_mm")
        max_stress = fea_results.get("max_stress_mpa")
        violations = _to_string_list(physics_review.get("violations"))
        recommendations = _to_string_list(physics_review.get("recommended_edits"))
        fallback_report = (
            "力学审查报告\n"
            f"- 最大位移：{max_disp:.6f} mm\n" if max_disp is not None else "力学审查报告\n- 最大位移：缺失\n"
        )
        fallback_report += (
            f"- 最大应力：{max_stress:.6f} MPa\n" if max_stress is not None else "- 最大应力：未提供\n"
        )
        fallback_report += (
            f"- 风险判断：{'；'.join(violations) if violations else '通过当前力学阈值检查'}\n"
            f"- 优先修改建议：{'；'.join(recommendations) if recommendations else '保持当前结构，继续观察视觉审查结果。'}"
        )

        model = self._get_chat_model("clarify") or self._get_chat_model("design")
        if model is None:
            return fallback_report, "Physics report used heuristic fallback."

        messages = self._text_messages(
            "clarify",
            PHYSICS_REPORT_SYSTEM_PROMPT,
            self.build_physics_report_request(clarified_spec, fea_results, physics_review),
        )
        try:
            response = self._invoke_model_with_timeout(
                model,
                messages,
                timeout_s=self._timeout_for_role("clarify"),
                role="physics_report",
            )
            text = _strip_thinking_blocks(_extract_text_content(response.content)).strip()
            if not text:
                raise ValueError("Physics report response was empty.")
            return text, "Physics report used remote text model."
        except Exception as exc:
            return fallback_report, f"Physics report fell back to heuristic text: {exc}"

    def _schema_hint(self, schema_name: str) -> str:
        hints = {
            "ClarifiedSpec": (
                "只返回一个 json object。"
                "顶层字段必须使用这些名字："
                "request_summary, object_type, design_brief, design_goals, style_keywords, "
                "length_mm, width_mm, height_mm, unit_system, material_name, "
                "material_young_mpa, material_poisson, fixed_boundary, load_boundary, "
                "load_vector_n, bbox_tol, missing_high_risk_fields, assumptions, visual_requirements。"
            ),
            "DesignPayload": (
                "只返回一个 json object。"
                "顶层字段必须使用这些名字：cadquery_code, analysis_config, render_config, self_check_notes。"
            ),
            "VisualReview": (
                "只返回一个 json object。"
                "顶层字段必须使用这些名字："
                "object_present, object_category_match, semantic_score, geometry_score, printability_score, "
                "defects, preserve_components, forbidden_repairs, acceptance_decision, "
                "pass, is_present, issues, missing_requirements, recommended_edits。"
            ),
        }
        return hints[schema_name]

    def _invoke_model_with_timeout(
        self,
        model: Any,
        messages: list[Any],
        timeout_s: float = 20.0,
        *,
        role: str | None = None,
    ) -> Any:
        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def worker() -> None:
            try:
                response = model.invoke(messages)
                self._record_token_usage(role, response)
                result["response"] = response
            except BaseException as exc:  # pragma: no cover - depends on provider runtime
                error["exception"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            raise TimeoutError(f"Model invocation timed out after {timeout_s:.1f}s.")
        if "exception" in error:
            raise error["exception"]
        return result["response"]

    def _invoke_raw_json(
        self,
        model: Any,
        messages: list[Any],
        timeout_s: float = 20.0,
        *,
        role: str | None = None,
    ) -> Any:
        response = self._invoke_model_with_timeout(model, messages, timeout_s=timeout_s, role=role)
        text = _strip_thinking_blocks(_extract_text_content(response.content))
        return _load_json_payload(text)

    def _normalize_clarified_spec_payload(self, payload: Any, prompt: str) -> dict[str, Any]:
        base = self._heuristic_clarify(prompt).model_dump()
        if not isinstance(payload, dict):
            return base

        result = dict(base)

        for key in (
            "request_summary",
            "object_type",
            "design_brief",
            "unit_system",
            "material_name",
            "bbox_tol",
            "material_young_mpa",
            "material_poisson",
        ):
            if payload.get(key) is not None:
                result[key] = payload[key]

        engineering_specs = payload.get("engineering_specs")
        if isinstance(engineering_specs, dict):
            result["request_summary"] = engineering_specs.get("request_summary") or result["request_summary"]
            result["object_type"] = str(engineering_specs.get("component_type") or result["object_type"])
            result["design_brief"] = str(engineering_specs.get("design_brief") or result["design_brief"])
            for src, dst in (
                ("length_mm", "length_mm"),
                ("width_mm", "width_mm"),
                ("height_mm", "height_mm"),
                ("young_modulus_mpa", "material_young_mpa"),
                ("young_modulus", "material_young_mpa"),
                ("poisson_ratio", "material_poisson"),
            ):
                value = _to_float(engineering_specs.get(src))
                if value is not None:
                    result[dst] = value
            material = engineering_specs.get("material")
            if material:
                result["material_name"] = str(material)

        for key in ("length_mm", "width_mm", "height_mm"):
            value = _to_float(payload.get(key))
            if value is not None:
                result[key] = value

        bounding_box = payload.get("bounding_box")
        if isinstance(bounding_box, dict):
            min_mm = bounding_box.get("min_mm")
            max_mm = bounding_box.get("max_mm")
            if isinstance(min_mm, list) and isinstance(max_mm, list) and len(min_mm) == 3 and len(max_mm) == 3:
                dims = [abs(float(max_mm[i]) - float(min_mm[i])) for i in range(3)]
                result["length_mm"] = dims[0]
                result["width_mm"] = dims[1]
                result["height_mm"] = dims[2]

        fixed_boundary = payload.get("fixed_boundary")
        load_boundary = payload.get("load_boundary")
        if isinstance(fixed_boundary, list) and len(fixed_boundary) == 6:
            result["fixed_boundary"] = [float(_to_float(item) or 0.0) for item in fixed_boundary]
        if isinstance(load_boundary, list) and len(load_boundary) == 6:
            result["load_boundary"] = [float(_to_float(item) or 0.0) for item in load_boundary]

        vector = None
        explicit_vector = payload.get("load_vector_n")
        if explicit_vector is not None:
            vector = _normalize_vector(explicit_vector)
        elif _parse_load_vector(prompt) is None:
            vector = _normalize_vector(payload.get("load_vector"))
        if vector is not None:
            result["load_vector_n"] = vector

        if not (isinstance(fixed_boundary, list) and len(fixed_boundary) == 6):
            result["fixed_boundary"] = _bbox_for_beam_face(
                float(result["length_mm"]),
                float(result["width_mm"]),
                float(result["height_mm"]),
                0.0,
            )
        if not (isinstance(load_boundary, list) and len(load_boundary) == 6):
            result["load_boundary"] = _bbox_for_beam_face(
                float(result["length_mm"]),
                float(result["width_mm"]),
                float(result["height_mm"]),
                float(result["length_mm"]),
            )
        result["design_goals"] = _to_string_list(payload.get("design_goals")) or result["design_goals"]
        result["style_keywords"] = _to_string_list(payload.get("style_keywords")) or result["style_keywords"]
        result["assumptions"] = _to_string_list(payload.get("assumptions")) or result["assumptions"]
        raw_missing = _to_string_list(payload.get("missing_high_risk_fields"))
        result["missing_high_risk_fields"] = [
            item for item in raw_missing if item in HIGH_RISK_FIELDS and result.get(item) in (None, [], "")
        ]
        result["visual_requirements"] = _to_string_list(payload.get("visual_requirements")) or [prompt]
        if not result["request_summary"]:
            result["request_summary"] = prompt
        return result

    def _normalize_design_payload(self, payload: Any, clarified_spec: dict[str, Any]) -> dict[str, Any]:
        base = self._heuristic_design(clarified_spec).model_dump()
        if not isinstance(payload, dict):
            return base

        result = dict(base)
        code = payload.get("cadquery_code") or payload.get("code") or payload.get("cad_code")
        if code:
            result["cadquery_code"] = str(code)

        analysis_config = payload.get("analysis_config")
        if isinstance(analysis_config, dict):
            merged = dict(result["analysis_config"])
            for key in (
                "length_mm",
                "width_mm",
                "height_mm",
                "fixed_x",
                "load_x",
                "bbox_tol",
                "young_modulus_mpa",
                "poisson_ratio",
            ):
                value = analysis_config.get(key)
                parsed = _to_float(value) if key != "bbox_tol" else _to_float(value)
                if parsed is not None:
                    merged[key] = parsed

            load_vector = _normalize_vector(analysis_config.get("load_vector_n"))
            if load_vector is not None:
                merged["load_vector_n"] = load_vector

            material = analysis_config.get("material")
            if isinstance(material, dict):
                young = _to_float(
                    material.get("young_modulus_mpa")
                    or material.get("youngs_modulus_mpa")
                    or material.get("young_modulus")
                    or material.get("youngs_modulus")
                )
                poisson = _to_float(material.get("poisson_ratio") or material.get("poissons_ratio"))
                if young is not None:
                    merged["young_modulus_mpa"] = young
                if poisson is not None:
                    merged["poisson_ratio"] = poisson

            boundary_conditions = analysis_config.get("boundary_conditions")
            if isinstance(boundary_conditions, dict):
                fixed_box = _normalize_bbox(boundary_conditions.get("fixed_box"))
                load_box = _normalize_bbox(boundary_conditions.get("load_box"))
                if fixed_box is not None:
                    merged["fixed_x"] = _plane_x_from_bbox(fixed_box)
                if load_box is not None:
                    merged["load_x"] = _plane_x_from_bbox(load_box)
                boundary_vector = _normalize_vector(
                    boundary_conditions.get("load_vector_n") or boundary_conditions.get("load_vector")
                )
                if boundary_vector is not None:
                    merged["load_vector_n"] = boundary_vector
                boundary_tol = _to_float(boundary_conditions.get("bbox_tol"))
                if boundary_tol is not None:
                    merged["bbox_tol"] = boundary_tol

            result["analysis_config"] = merged

        render_config = payload.get("render_config")
        if isinstance(render_config, dict):
            merged = dict(result["render_config"])
            views = render_config.get("views") or render_config.get("camera_presets")
            if isinstance(views, list) and views:
                merged["views"] = [str(item) for item in views if item]
            width = _to_float(render_config.get("image_width") or render_config.get("width"))
            height = _to_float(render_config.get("image_height") or render_config.get("height"))
            if width is not None and width > 0:
                merged["image_width"] = int(width)
            if height is not None and height > 0:
                merged["image_height"] = int(height)
            result["render_config"] = merged

        result["self_check_notes"] = _to_string_list(payload.get("self_check_notes")) or result["self_check_notes"]
        return result

    def _normalize_visual_review_payload(self, payload: Any, image_paths: list[str]) -> dict[str, Any]:
        base = self._heuristic_visual_review(image_paths).model_dump(by_alias=True)
        if not isinstance(payload, dict):
            return base

        result = dict(base)

        pass_value = _to_bool(payload.get("pass"))
        if pass_value is None:
            pass_value = _to_bool(payload.get("is_passed"))
        if pass_value is None:
            pass_value = _to_bool(payload.get("passed"))
        if pass_value is not None:
            result["pass"] = pass_value

        explicit_presence = _to_bool(payload.get("is_present"))
        if explicit_presence is not None:
            result["is_present"] = explicit_presence

        object_present = _to_bool(payload.get("object_present"))
        if object_present is None:
            object_present = _to_bool(payload.get("object_exists"))
        if object_present is not None:
            result["object_present"] = object_present
            if explicit_presence is None:
                result["is_present"] = object_present

        category_match = _to_bool(payload.get("object_category_match"))
        if category_match is None:
            category_match = _to_bool(payload.get("category_match"))
        if category_match is not None:
            result["object_category_match"] = category_match

        for score_key in ("semantic_score", "geometry_score", "printability_score"):
            score_value = _to_float(payload.get(score_key))
            if score_value is not None:
                result[score_key] = max(0.0, min(1.0, score_value))

        decision = str(payload.get("acceptance_decision") or "").strip().lower()
        if decision in {"accept", "repair", "reject"}:
            result["acceptance_decision"] = decision

        checklist_presence: list[bool] = []
        checklist_missing: list[str] = []
        checklist_issues: list[str] = []
        feature_checklist = payload.get("feature_checklist")
        if isinstance(feature_checklist, list):
            for item in feature_checklist:
                if not isinstance(item, dict):
                    continue
                presence = _to_bool(item.get("is_present"))
                if presence is None:
                    continue
                checklist_presence.append(presence)
                if presence:
                    continue
                feature_name = str(item.get("feature_name") or item.get("feature") or "未命名特征").strip()
                evidence = str(item.get("evidence") or "").strip()
                checklist_missing.append(feature_name)
                issue = f"缺失特征：{feature_name}"
                if evidence:
                    issue = f"{issue}（{evidence}）"
                checklist_issues.append(issue)

        if checklist_presence and explicit_presence is None:
            result["is_present"] = all(checklist_presence)
            result["object_present"] = all(checklist_presence)

        issues = _to_string_list(payload.get("issues"))
        if not issues:
            issues = _to_string_list(result.get("issues"))
        for issue in checklist_issues:
            if issue not in issues:
                issues.append(issue)

        sanity_check = payload.get("sanity_check")
        if sanity_check is not None:
            sanity_text = str(sanity_check).strip()
            lowered_sanity = sanity_text.lower()
            if sanity_text and (
                "不通过" in sanity_text
                or "未通过" in sanity_text
                or "失败" in sanity_text
                or "fail" in lowered_sanity
            ):
                sanity_issue = f"Sanity check: {sanity_text}"
                if sanity_issue not in issues:
                    issues.append(sanity_issue)
        if issues:
            result["issues"] = issues

        missing_requirements = _to_string_list(payload.get("missing_requirements"))
        if not missing_requirements:
            missing_requirements = _to_string_list(result.get("missing_requirements"))
        for item in checklist_missing:
            if item not in missing_requirements:
                missing_requirements.append(item)
        if missing_requirements:
            result["missing_requirements"] = missing_requirements

        recommended_edits = _to_string_list(payload.get("recommended_edits"))
        if not recommended_edits:
            recommended_edits = _to_string_list(result.get("recommended_edits"))

        revision_feedbacks = payload.get("revision_feedbacks")
        defects = payload.get("defects")
        normalized_defects: list[dict[str, Any]] = []
        if isinstance(defects, list):
            for item in defects:
                if not isinstance(item, dict):
                    continue
                normalized_defects.append(
                    {
                        "component": str(item.get("component") or "unknown"),
                        "issue": str(item.get("issue") or item.get("defect") or ""),
                        "severity": int(_to_float(item.get("severity")) or 2),
                        "repair_action": str(item.get("repair_action") or item.get("geometric_modification") or ""),
                        "target_parameter": item.get("target_parameter"),
                        "suggested_change": item.get("suggested_change"),
                    }
                )
        if isinstance(revision_feedbacks, list):
            for item in revision_feedbacks:
                if isinstance(item, dict):
                    defect = str(item.get("defect") or "").strip()
                    modification = str(item.get("geometric_modification") or item.get("suggestion") or "").strip()
                    if defect and modification:
                        rec = f"{defect}：{modification}"
                    else:
                        rec = defect or modification
                else:
                    rec = str(item).strip()
                if rec and rec not in recommended_edits:
                    recommended_edits.append(rec)
                if rec:
                    normalized_defects.append(
                        {
                            "component": "unknown",
                            "issue": defect if isinstance(item, dict) else rec,
                            "severity": 2,
                            "repair_action": modification if isinstance(item, dict) else rec,
                            "target_parameter": None,
                            "suggested_change": None,
                        }
                    )
        if recommended_edits:
            result["recommended_edits"] = recommended_edits
        if normalized_defects:
            result["defects"] = normalized_defects

        preserve_components = _to_string_list(payload.get("preserve_components"))
        if not preserve_components:
            preserve_components = _to_string_list(payload.get("must_preserve"))
        if preserve_components:
            result["preserve_components"] = preserve_components

        forbidden_repairs = _to_string_list(payload.get("forbidden_repairs"))
        if not forbidden_repairs:
            forbidden_repairs = _to_string_list(payload.get("forbidden_actions"))
        if forbidden_repairs:
            result["forbidden_repairs"] = forbidden_repairs

        if pass_value is None:
            has_failure_signals = bool(result.get("issues")) or bool(result.get("missing_requirements")) or bool(
                result.get("recommended_edits")
            )
            if has_failure_signals:
                result["pass"] = False
            elif result.get("is_present") is not None:
                result["pass"] = bool(result["is_present"])

        if result.get("pass") is True:
            result["acceptance_decision"] = "accept"
        elif result.get("object_present") is False or result.get("object_category_match") is False:
            result["acceptance_decision"] = "reject"
        else:
            result["acceptance_decision"] = "repair"

        return result

    def _endpoint_for_role(self, role: str) -> ModelEndpoint:
        if role in self.role_model_configs:
            return self.role_model_configs[role]

        defaults = {
            "clarify": self.clarify_model_name,
            "design": self.design_model_name,
            "visual": self.visual_model_name,
        }
        if role not in defaults:
            raise KeyError(f"Unsupported role: {role}")

        return ModelEndpoint.from_env(
            role=role,
            default_model=defaults[role],
            default_provider="openai",
            default_temperature=0.0,
        )

    def _get_chat_model(self, role: str):
        endpoint = self._endpoint_for_role(role)
        extra_body = self._extra_body_for_role(role, endpoint)
        timeout_s = self._timeout_for_role(role, endpoint=endpoint)
        cache_key = (
            f"{endpoint.cache_key()}|timeout={timeout_s:.1f}"
            f"|extra_body={json.dumps(extra_body, sort_keys=True, ensure_ascii=False) if extra_body else 'null'}"
        )
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        api_key = endpoint.resolved_api_key()
        provider = endpoint.provider_hint()
        explicit_config = role in self.role_model_configs or endpoint.configured_via_env

        if not explicit_config and not api_key:
            return None

        if explicit_config and provider in PROVIDER_API_KEY_ENV and not api_key:
            env_name = PROVIDER_API_KEY_ENV[provider]
            raise RuntimeError(
                f"{role} 模型已配置为 {endpoint.model!r}，但缺少凭证。"
                f"请设置 {env_name} 或 TEXTCAD_{role.upper()}_API_KEY / TEXTCAD_DEFAULT_API_KEY。"
            )

        kwargs: dict[str, Any] = {
            "model": endpoint.model,
            "max_retries": 1,
            "temperature": endpoint.temperature,
            "timeout": timeout_s,
        }
        if endpoint.model_provider:
            kwargs["model_provider"] = endpoint.model_provider
        if endpoint.base_url:
            kwargs["base_url"] = endpoint.base_url
        if api_key:
            kwargs["api_key"] = api_key
        if extra_body:
            kwargs["extra_body"] = extra_body

        model = init_chat_model(**kwargs)
        self._model_cache[cache_key] = model
        return model

    def _heuristic_clarify(self, prompt: str) -> ClarifiedSpec:
        profile = _default_design_profile(prompt)
        length_mm, width_mm, height_mm = _parse_dimensions(prompt)
        assumptions = list(profile["assumptions"])
        if length_mm is None or width_mm is None or height_mm is None:
            length_mm, width_mm, height_mm = profile["dimensions"]
            assumptions.append(
                f"未识别到明确尺寸，按 {profile['object_type']} 的默认比例生成 {length_mm:.0f}x{width_mm:.0f}x{height_mm:.0f} mm。"
            )

        load_vector = _parse_load_vector(prompt)
        if load_vector is None:
            load_vector = [0.0, -1.0, 0.0]
            assumptions.append("未识别到受力信息时，力学审查阶段默认在 +X 端面施加向下 1N 试探载荷。")

        fixed_boundary = _bbox_for_beam_face(length_mm, width_mm, height_mm, 0.0)
        load_boundary = _bbox_for_beam_face(length_mm, width_mm, height_mm, length_mm)
        assumptions.append("未单独指定分析边界时，默认采用模型在 X 方向的首尾端面做固定端和加载端。")

        return ClarifiedSpec(
            request_summary=prompt,
            object_type=profile["object_type"],
            design_brief=profile["design_brief"],
            design_goals=profile["design_goals"],
            style_keywords=profile["style_keywords"],
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            fixed_boundary=fixed_boundary,
            load_boundary=load_boundary,
            load_vector_n=load_vector,
            missing_high_risk_fields=[],
            assumptions=assumptions,
            visual_requirements=profile["visual_requirements"],
        )

    def clarify(self, prompt: str, feedback_history: list[str]) -> ClarifiedSpec:
        if self.clarify_fn is not None:
            return self.clarify_fn(prompt, feedback_history)

        model = self._get_chat_model("clarify")
        if model is None:
            return self._heuristic_clarify(prompt)

        messages = self._text_messages(
            "clarify",
            CLARIFY_SYSTEM_PROMPT,
            self.build_clarify_request(prompt, feedback_history),
        )
        try:
            payload = self._invoke_raw_json(
                model,
                messages,
                timeout_s=self._timeout_for_role("clarify"),
                role="clarify",
            )
            normalized = self._normalize_clarified_spec_payload(payload, prompt)
            return ClarifiedSpec.model_validate(normalized)
        except Exception:
            return self._heuristic_clarify(prompt)

    def _heuristic_design(
        self,
        clarified_spec: dict[str, Any],
        fallback_reason: str | None = None,
    ) -> DesignPayload:
        backend = clarified_spec["backend_config"]
        object_type = str(clarified_spec.get("object_type") or "")
        summary = str(clarified_spec.get("request_summary") or "")
        if object_type == "phone_stand" or _contains_any(summary, ("手机支架", "phone stand", "phone holder")):
            code = _phone_stand_code(backend)
        elif object_type == "stand_bracket" or _contains_any(summary, ("支架", "bracket", "holder", "stand")):
            code = _stand_bracket_code(backend)
        elif object_type == "tray_box" or _contains_any(summary, ("盒", "盒子", "tray", "box", "container")):
            code = _tray_box_code(backend)
        else:
            code = (
                "from __future__ import annotations\n\n"
                "import cadquery as cq\n\n"
                "def build_model():\n"
                "    return (\n"
                '        cq.Workplane("XY")\n'
                f"        .box({backend['length_mm']}, {backend['width_mm']}, {backend['height_mm']})\n"
                f"        .translate(({backend['length_mm']} / 2.0, 0.0, 0.0))\n"
                "        .edges('|Z').fillet(min(2.0, "
                f"{min(float(backend['width_mm']), float(backend['height_mm'])) / 8.0:.2f}))\n"
                "    )\n"
            )
        notes = ["heuristic fallback used", f"object_type={object_type or 'generic_printable_object'}"]
        if fallback_reason:
            notes.append(f"design_error: {fallback_reason}")
        return DesignPayload(
            cadquery_code=code,
            analysis_config=backend,
            render_config=RenderConfig(),
            self_check_notes=notes,
        )

    def design(
        self,
        prompt: str,
        clarified_spec: dict[str, Any],
        feedback_history: list[str],
        previous_code: str = "",
        *,
        engineering_prompt: str = "",
        latest_revision_brief: str = "",
        structured_revision: dict[str, Any] | None = None,
        repair_mode: bool = False,
    ) -> DesignPayload:
        if self.design_fn is not None:
            return self.design_fn(prompt, clarified_spec, feedback_history)

        model = self._get_chat_model("design")
        if model is None:
            return self._heuristic_design(clarified_spec)

        prompt_text = self.build_design_request(
            prompt=prompt,
            engineering_prompt=engineering_prompt or self.build_engineering_prompt(prompt, clarified_spec),
            clarified_spec=clarified_spec,
            latest_revision_brief=latest_revision_brief,
            previous_code=previous_code,
            structured_revision=structured_revision,
            repair_mode=repair_mode,
        )

        messages = self._text_messages("design", DESIGN_SYSTEM_PROMPT, prompt_text)
        try:
            response = self._invoke_model_with_timeout(
                model,
                messages,
                timeout_s=self._timeout_for_role("design"),
                role="design",
            )
            raw_text = _strip_thinking_blocks(_extract_text_content(response.content))
            payload = _load_design_json(raw_text)
            normalized = self._normalize_design_payload(payload, clarified_spec)
            return DesignPayload.model_validate(normalized)
        except Exception as exc:
            raise RuntimeError(f"Design generation failed: {exc}") from exc

    def _heuristic_visual_review(
        self,
        image_paths: list[str],
        reason: str | None = None,
        fail_closed: bool = False,
    ) -> VisualReview:
        if not image_paths:
            return VisualReview(
                **{
                    "pass": False,
                    "issues": ["未生成渲染截图。"],
                    "missing_requirements": [],
                    "recommended_edits": ["先修复 STL 导出或 PyVista 渲染，再重新审查。"],
                    "object_present": False,
                    "object_category_match": False,
                    "semantic_score": 0.0,
                    "geometry_score": 0.0,
                    "printability_score": 0.0,
                    "defects": [
                        {
                            "component": "render",
                            "issue": "未生成渲染截图。",
                            "severity": 3,
                            "repair_action": "修复 STL 导出或 PyVista 渲染。",
                            "target_parameter": None,
                            "suggested_change": None,
                        }
                    ],
                    "preserve_components": [],
                    "forbidden_repairs": ["不要重写已可编译的主体结构，先修复渲染/导出链路。"],
                    "acceptance_decision": "reject",
                    "backend": "heuristic_fallback",
                    "fallback_reason": reason,
                }
            )
        if fail_closed:
            return VisualReview(
                **{
                    "pass": False,
                    "issues": [reason or "远程视觉审查失败，未能获得可靠的多模态审查结果。"],
                    "missing_requirements": [],
                    "recommended_edits": ["修复远程 VLM 调用或输出解析问题后，再重新执行视觉审查。"],
                    "object_present": True,
                    "object_category_match": None,
                    "semantic_score": 0.4,
                    "geometry_score": 0.4,
                    "printability_score": 0.4,
                    "defects": [
                        {
                            "component": "visual_qa",
                            "issue": reason or "远程视觉审查失败。",
                            "severity": 2,
                            "repair_action": "修复远程 VLM 调用或输出解析问题。",
                            "target_parameter": None,
                            "suggested_change": None,
                        }
                    ],
                    "preserve_components": ["previous_primary_geometry"],
                    "forbidden_repairs": ["不要因 VLM 暂时失败而从零重写模型。"],
                    "acceptance_decision": "repair",
                    "backend": "heuristic_fallback",
                    "fallback_reason": reason,
                }
            )
        return VisualReview(
            **{
                "pass": True,
                "is_present": True,
                "object_present": True,
                "object_category_match": True,
                "semantic_score": 0.75,
                "geometry_score": 0.75,
                "printability_score": 0.75,
                "defects": [],
                "preserve_components": ["visible_primary_geometry"],
                "forbidden_repairs": ["不要删除当前可见主体结构。"],
                "acceptance_decision": "accept",
                "issues": [],
                "missing_requirements": [],
                "recommended_edits": [],
                "backend": "heuristic_fallback",
                "fallback_reason": reason,
            }
        )

    def review_visual_with_meta(
        self,
        prompt: str,
        clarified_spec: dict[str, Any],
        image_paths: list[str],
        feedback_history: list[str],
    ) -> tuple[VisualReview, str]:
        if self.visual_review_fn is not None:
            review = self.visual_review_fn(prompt, clarified_spec, image_paths, feedback_history)
            if not review.backend:
                review = review.model_copy(update={"backend": "custom_visual_fn"})
            return review, "Visual QA used custom visual_review_fn."

        endpoint = self._endpoint_for_role("visual")
        if endpoint.base_url and not self._has_role_specific_env_config("visual") and "visual" not in self.role_model_configs:
            reason = (
                "Visual role resolved to an OpenAI-compatible endpoint, "
                "but no explicit TEXTCAD_VISUAL_* configuration was provided. "
                "Skipped remote VLM and used heuristic fallback."
            )
            return self._heuristic_visual_review(image_paths, reason=reason), reason

        model = self._get_chat_model("visual")
        if model is None:
            reason = "No visual model resolved; used heuristic visual review."
            return self._heuristic_visual_review(image_paths, reason=reason), reason

        selected_image_paths = self._select_visual_image_paths(image_paths)
        visual_max_pixels = self._visual_max_pixels(endpoint)

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self.build_visual_review_request(prompt, clarified_spec, feedback_history),
            }
        ]
        for image_path in selected_image_paths:
            image_url: dict[str, Any] = {"url": _encode_image_as_data_url(image_path)}
            if visual_max_pixels is not None:
                image_url["max_pixels"] = visual_max_pixels
            content.append(
                {
                    "type": "image_url",
                    "image_url": image_url,
                }
            )

        messages = self._multimodal_messages("visual", VISUAL_SYSTEM_PROMPT, content)
        try:
            payload = self._invoke_raw_json(
                model,
                messages,
                timeout_s=self._timeout_for_role("visual"),
                role="visual",
            )
            normalized = self._normalize_visual_review_payload(payload, selected_image_paths)
            review = VisualReview.model_validate(
                {
                    **normalized,
                    "backend": "remote_model",
                    "fallback_reason": None,
                }
            )
            log = (
                f"Remote visual QA succeeded via model={endpoint.model} "
                f"provider={endpoint.provider_hint() or 'auto'} "
                f"images={len(selected_image_paths)} timeout_s={self._timeout_for_role('visual'):.1f} "
                f"max_pixels={visual_max_pixels}."
            )
            return review, log
        except Exception as exc:
            reason = f"Remote visual QA failed via model={endpoint.model}: {exc}"
            return self._heuristic_visual_review(image_paths, reason=reason, fail_closed=True), reason

    def review_visual(
        self,
        prompt: str,
        clarified_spec: dict[str, Any],
        image_paths: list[str],
        feedback_history: list[str],
    ) -> VisualReview:
        review, _ = self.review_visual_with_meta(prompt, clarified_spec, image_paths, feedback_history)
        return review


def build_agent(runtime: AgentRuntime | None = None, with_memory: bool = True):
    runtime = runtime or AgentRuntime()
    workflow = StateGraph(AgentState)

    workflow.add_node("ingest_request", make_ingest_request_node())
    workflow.add_node("clarify_spec", make_clarify_spec_node(runtime), retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("await_user_clarification", make_await_user_clarification_node(runtime))
    workflow.add_node("engineer_spec", make_engineer_spec_node())
    workflow.add_node("design_generate", make_design_generate_node(runtime), retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("static_validate", make_static_validate_node())
    workflow.add_node(
        "materialize_workspace",
        make_materialize_workspace_node(),
        retry_policy=RetryPolicy(max_attempts=3),
    )
    workflow.add_node("build_cad", make_build_cad_node(), retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("build_mesh", make_build_mesh_node())
    workflow.add_node("solve_fea", make_solve_fea_node())
    workflow.add_node("render_views", make_render_views_node(), retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("physics_qa", make_physics_qa_node(runtime))
    workflow.add_node("physics_report", make_physics_report_node(runtime), retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("visual_qa", make_visual_qa_node(runtime), retry_policy=RetryPolicy(max_attempts=3))
    workflow.add_node("revision_brief", make_revision_brief_node())
    workflow.add_node("quality_gate", make_quality_gate_node(runtime))
    workflow.add_node("feedback_merge", make_feedback_merge_node())
    workflow.add_node("decide_next", make_decide_next_node(runtime))

    workflow.add_edge(START, "ingest_request")
    workflow.add_edge("ingest_request", "clarify_spec")
    workflow.add_edge("engineer_spec", "design_generate")
    workflow.add_edge("design_generate", "static_validate")
    workflow.add_edge("materialize_workspace", "build_cad")
    workflow.add_edge("build_mesh", "solve_fea")
    workflow.add_edge("solve_fea", "render_views")
    workflow.add_edge("render_views", "physics_qa")
    workflow.add_edge("physics_qa", "physics_report")
    workflow.add_edge("physics_report", "visual_qa")
    workflow.add_edge("visual_qa", "revision_brief")
    workflow.add_edge("revision_brief", "quality_gate")
    workflow.add_edge("quality_gate", "feedback_merge")
    workflow.add_edge("feedback_merge", "decide_next")

    if with_memory:
        return workflow.compile(checkpointer=MemorySaver())
    return workflow.compile()


def create_agent(runtime: AgentRuntime | None = None):
    return build_agent(runtime=runtime)
