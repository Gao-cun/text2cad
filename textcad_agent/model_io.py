from __future__ import annotations

import ast
import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROVIDER_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def to_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def to_positive_int_env(value: str | None) -> int | None:
    parsed = to_int(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def to_float_env(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_bool_env(value: str | None) -> bool | None:
    if value in (None, ""):
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def coerce_non_negative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def normalize_token_usage_payload(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, dict):
        return None

    prompt_tokens = None
    for key in ("prompt_tokens", "input_tokens", "prompt_token_count", "input_token_count"):
        prompt_tokens = coerce_non_negative_int(payload.get(key))
        if prompt_tokens is not None:
            break

    completion_tokens = None
    for key in ("completion_tokens", "output_tokens", "completion_token_count", "output_token_count"):
        completion_tokens = coerce_non_negative_int(payload.get(key))
        if completion_tokens is not None:
            break

    total_tokens = coerce_non_negative_int(payload.get("total_tokens"))
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None

    return {
        "prompt_tokens": prompt_tokens or 0,
        "completion_tokens": completion_tokens or 0,
        "total_tokens": total_tokens or 0,
    }


def extract_response_token_usage(response: Any) -> dict[str, int]:
    candidates: list[Any] = [getattr(response, "usage_metadata", None)]
    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        candidates.extend(
            [
                response_metadata.get("token_usage"),
                response_metadata.get("usage"),
                response_metadata,
            ]
        )

    for candidate in candidates:
        normalized = normalize_token_usage_payload(candidate)
        if normalized is not None:
            return normalized
    return {}


def encode_image_as_data_url(path: str) -> str:
    image_path = Path(path)
    mime = "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in {"text", "output_text", "input_text"}:
                    parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


_THINKING_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_thinking_blocks(text: str) -> str:
    """Remove Qwen3 <think>...</think> reasoning blocks before JSON extraction."""
    return _THINKING_RE.sub("", text).strip()


def extract_json_fragment(text: str) -> str:
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    start = -1
    depth = 0
    in_string = False
    escape = False
    opener = ""
    closer = ""
    for index, char in enumerate(text):
        if start == -1 and char in "{[":
            start = index
            opener = char
            closer = "}" if char == "{" else "]"
            depth = 1
            continue
        if start == -1:
            continue
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1].strip()
    return text.strip()


def load_json_payload(text: str) -> Any:
    candidate = extract_json_fragment(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return ast.literal_eval(candidate)


_CODE_BLOCK_RE = re.compile(r"```\w*\n(.*?)```", re.DOTALL)


def load_design_json(text: str) -> Any:
    """Parse JSON from a design model response.

    Tries standard JSON extraction first. If that fails, falls back to pulling
    the CadQuery code from a fenced code block and any remaining JSON from the
    rest of the text. This handles a common Qwen3 pattern where code is rendered
    as a literal code block rather than an escaped JSON string.
    """
    try:
        return load_json_payload(text)
    except Exception:
        pass

    code_match = _CODE_BLOCK_RE.search(text)
    if not code_match:
        raise ValueError("No valid JSON or fenced code block found in design response.")

    code = code_match.group(1)
    remainder = text[: code_match.start()] + text[code_match.end() :]
    try:
        data = load_json_payload(remainder)
        if isinstance(data, dict):
            data.setdefault("cadquery_code", code)
            return data
    except Exception:
        pass

    return {"cadquery_code": code}


def is_qwen_mixed_thinking_model(model_name: str) -> bool:
    lowered = model_name.lower()
    return lowered.startswith("qwen3") or lowered.startswith("qwq")


def supports_enable_thinking_param(model_name: str) -> bool:
    lowered = model_name.lower()
    if "vl" in lowered:
        return False
    return is_qwen_mixed_thinking_model(model_name)


@dataclass(frozen=True)
class ModelEndpoint:
    role: str
    model: str
    model_provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.0
    configured_via_env: bool = False

    @classmethod
    def from_env(
        cls,
        role: str,
        default_model: str,
        default_provider: str | None = None,
        default_temperature: float = 0.0,
    ) -> "ModelEndpoint":
        shared_prefix = "TEXTCAD_DEFAULT_"
        role_prefix = f"TEXTCAD_{role.upper()}_"
        field_names = ("MODEL", "PROVIDER", "BASE_URL", "API_KEY", "TEMPERATURE")

        def read_env(name: str) -> str | None:
            role_value = os.getenv(f"{role_prefix}{name}")
            if role_value is not None:
                return role_value
            return os.getenv(f"{shared_prefix}{name}")

        configured_via_env = any(read_env(name) is not None for name in field_names)
        model_override = read_env("MODEL")
        provider_override = read_env("PROVIDER")
        base_url = read_env("BASE_URL") or None
        api_key = read_env("API_KEY") or None
        temp_raw = read_env("TEMPERATURE")
        temperature = default_temperature if temp_raw in (None, "") else float(temp_raw)
        model = model_override or default_model

        if provider_override:
            provider = provider_override
        elif ":" in model:
            provider = None
        elif base_url:
            provider = "openai"
        elif model_override is None:
            provider = default_provider
        else:
            provider = None

        return cls(
            role=role,
            model=model,
            model_provider=provider,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            configured_via_env=configured_via_env,
        )

    def provider_hint(self) -> str | None:
        if self.model_provider:
            return self.model_provider
        if ":" in self.model:
            return self.model.split(":", 1)[0]
        return None

    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        provider = self.provider_hint()
        if provider is None:
            return None
        env_name = PROVIDER_API_KEY_ENV.get(provider)
        if env_name is None:
            return None
        return os.getenv(env_name)

    def cache_key(self) -> str:
        return json.dumps(
            {
                "role": self.role,
                "model": self.model,
                "model_provider": self.model_provider,
                "base_url": self.base_url,
                "temperature": self.temperature,
                "has_api_key": bool(self.resolved_api_key()),
            },
            sort_keys=True,
        )
