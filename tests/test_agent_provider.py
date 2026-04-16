from __future__ import annotations

from textcad_agent.agent import AgentRuntime, ModelEndpoint


def test_model_endpoint_reads_qwen_openai_compatible_config(monkeypatch):
    monkeypatch.setenv("TEXTCAD_DEFAULT_MODEL", "qwen-max")
    monkeypatch.setenv("TEXTCAD_DEFAULT_PROVIDER", "openai")
    monkeypatch.setenv("TEXTCAD_DEFAULT_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("TEXTCAD_DEFAULT_API_KEY", "dashscope-key")

    endpoint = ModelEndpoint.from_env(
        role="design",
        default_model="gpt-4.1",
        default_provider="openai",
    )

    assert endpoint.model == "qwen-max"
    assert endpoint.model_provider == "openai"
    assert endpoint.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert endpoint.resolved_api_key() == "dashscope-key"


def test_runtime_passes_provider_config_to_init_chat_model(monkeypatch):
    captured: dict[str, object] = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr("textcad_agent.agent.init_chat_model", fake_init_chat_model)
    runtime = AgentRuntime(
        role_model_configs={
            "design": ModelEndpoint(
                role="design",
                model="qwen-plus",
                model_provider="openai",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="dashscope-key",
            )
        }
    )

    model = runtime._get_chat_model("design")

    assert model["model"] == "qwen-plus"
    assert captured["model_provider"] == "openai"
    assert captured["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert captured["api_key"] == "dashscope-key"


def test_runtime_uses_role_specific_timeout_for_chat_model(monkeypatch):
    captured_calls: list[dict[str, object]] = []

    def fake_init_chat_model(**kwargs):
        captured_calls.append(dict(kwargs))
        return dict(kwargs)

    monkeypatch.setattr("textcad_agent.agent.init_chat_model", fake_init_chat_model)
    monkeypatch.setenv("TEXTCAD_VISUAL_TIMEOUT_S", "75")
    runtime = AgentRuntime(
        role_model_configs={
            "design": ModelEndpoint(
                role="design",
                model="qwen3.6-plus",
                model_provider="openai",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="dashscope-key",
            ),
            "visual": ModelEndpoint(
                role="visual",
                model="qwen3.6-plus",
                model_provider="openai",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="dashscope-key",
            ),
        }
    )

    design_model = runtime._get_chat_model("design")
    visual_model = runtime._get_chat_model("visual")

    assert design_model["timeout"] == 180.0  # new default for design role
    assert visual_model["timeout"] == 75.0  # overridden by TEXTCAD_VISUAL_TIMEOUT_S=75
    assert len(captured_calls) == 2


def test_runtime_disables_qwen3_thinking_by_default(monkeypatch):
    captured: dict[str, object] = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return dict(kwargs)

    monkeypatch.setattr("textcad_agent.agent.init_chat_model", fake_init_chat_model)
    runtime = AgentRuntime(
        role_model_configs={
            "design": ModelEndpoint(
                role="design",
                model="qwen3.6-plus",
                model_provider="openai",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="dashscope-key",
            )
        }
    )

    model = runtime._get_chat_model("design")

    assert model["extra_body"] == {"enable_thinking": False}
    assert captured["extra_body"] == {"enable_thinking": False}


def test_runtime_allows_env_override_for_qwen3_thinking(monkeypatch):
    captured: dict[str, object] = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return dict(kwargs)

    monkeypatch.setenv("TEXTCAD_DESIGN_ENABLE_THINKING", "true")
    monkeypatch.setattr("textcad_agent.agent.init_chat_model", fake_init_chat_model)
    runtime = AgentRuntime(
        role_model_configs={
            "design": ModelEndpoint(
                role="design",
                model="qwen3.6-plus",
                model_provider="openai",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="dashscope-key",
            )
        }
    )

    model = runtime._get_chat_model("design")

    assert model["extra_body"] == {"enable_thinking": True}
    assert captured["extra_body"] == {"enable_thinking": True}


def test_runtime_keeps_offline_fallback_without_credentials(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TEXTCAD_DEFAULT_MODEL",
        "TEXTCAD_DEFAULT_PROVIDER",
        "TEXTCAD_DEFAULT_BASE_URL",
        "TEXTCAD_DEFAULT_API_KEY",
        "TEXTCAD_CLARIFY_MODEL",
        "TEXTCAD_CLARIFY_PROVIDER",
        "TEXTCAD_CLARIFY_BASE_URL",
        "TEXTCAD_CLARIFY_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    runtime = AgentRuntime()
    assert runtime._get_chat_model("clarify") is None


def test_visual_runtime_uses_longer_timeout_and_trims_images(monkeypatch):
    monkeypatch.setenv("TEXTCAD_VISUAL_TIMEOUT_S", "75")
    monkeypatch.setenv("TEXTCAD_VISUAL_MAX_IMAGES", "2")
    runtime = AgentRuntime()

    assert runtime._timeout_for_role("visual") == 75.0
    assert runtime._select_visual_image_paths(
        [
            "/tmp/iso_back.png",
            "/tmp/top.png",
            "/tmp/iso_front.png",
            "/tmp/side.png",
        ]
    ) == ["/tmp/iso_front.png", "/tmp/side.png"]


def test_qwen_visual_defaults_apply_dashscope_pixel_cap():
    runtime = AgentRuntime()
    endpoint = ModelEndpoint(
        role="visual",
        model="qwen3.6-plus",
        model_provider="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="dashscope-key",
    )
    assert runtime._visual_max_pixels(endpoint) == 1310720


def test_qwen_messages_fold_system_prompt_into_user_message():
    runtime = AgentRuntime(
        role_model_configs={
            "design": ModelEndpoint(
                role="design",
                model="qwen3.6-plus",
                model_provider="openai",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="dashscope-key",
            )
        }
    )

    messages = runtime._text_messages("design", "系统指令", "用户内容")

    assert len(messages) == 1
    assert messages[0].type == "human"
    assert "系统指令" in messages[0].content
    assert "用户内容" in messages[0].content


def test_normalize_design_payload_accepts_nested_qwen_style_config():
    runtime = AgentRuntime()
    clarified_spec = {
        "request_summary": "手机支架",
        "object_type": "phone_stand",
        "backend_config": {
            "length_mm": 95.0,
            "width_mm": 78.0,
            "height_mm": 110.0,
            "fixed_x": 0.0,
            "load_x": 95.0,
            "bbox_tol": 0.2,
            "load_vector_n": [0.0, -1.0, 0.0],
            "young_modulus_mpa": 3500.0,
            "poisson_ratio": 0.36,
        },
    }
    payload = {
        "cadquery_code": "import cadquery as cq\n\ndef build_model():\n    return cq.Workplane('XY').box(1,1,1)\n",
        "analysis_config": {
            "material": {"name": "PLA", "youngs_modulus_mpa": 4200, "poissons_ratio": 0.33},
            "boundary_conditions": {
                "fixed_box": [0.0, -39.0, -55.0, 0.0, 39.0, 55.0],
                "load_box": [95.0, -39.0, -55.0, 95.0, 39.0, 55.0],
                "load_vector": [0.0, -2.0, 0.0],
            },
            "mesh_settings": {"element_size": 2.0},
        },
        "render_config": {
            "camera_presets": ["iso_front", "side"],
            "view_port": {"camera_position": [1, 2, 3]},
            "style": {"show_edges": True},
        },
    }

    normalized = runtime._normalize_design_payload(payload, clarified_spec)

    assert normalized["analysis_config"]["young_modulus_mpa"] == 4200.0
    assert normalized["analysis_config"]["poisson_ratio"] == 0.33
    assert normalized["analysis_config"]["fixed_x"] == 0.0
    assert normalized["analysis_config"]["load_x"] == 95.0
    assert normalized["analysis_config"]["load_vector_n"] == [0.0, -2.0, 0.0]
    assert normalized["render_config"]["views"] == ["iso_front", "side"]
