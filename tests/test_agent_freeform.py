from __future__ import annotations

from textcad_agent.agent import AgentRuntime


def test_heuristic_clarify_supports_freeform_phone_stand_prompt():
    runtime = AgentRuntime()
    spec = runtime._heuristic_clarify("我要一个手机支架，放在桌面上看视频。")

    assert spec.object_type == "phone_stand"
    assert spec.design_brief
    assert spec.design_goals
    assert spec.visual_requirements
    assert spec.missing_high_risk_fields == []
    assert spec.length_mm > 0
    assert spec.width_mm > 0
    assert spec.height_mm > 0


def test_heuristic_design_generates_semantic_phone_stand_geometry():
    runtime = AgentRuntime()
    spec = runtime._heuristic_clarify("我要一个手机支架，放在桌面上看视频。")
    clarified = spec.model_dump()
    clarified["backend_config"] = {
        "length_mm": spec.length_mm,
        "width_mm": spec.width_mm,
        "height_mm": spec.height_mm,
        "fixed_x": 0.0,
        "load_x": spec.length_mm,
        "bbox_tol": spec.bbox_tol,
        "load_vector_n": spec.load_vector_n,
        "young_modulus_mpa": spec.material_young_mpa,
        "poisson_ratio": spec.material_poisson,
    }

    payload = runtime._heuristic_design(clarified)

    assert 'cq.Workplane("XZ")' in payload.cadquery_code
    assert "polyline" in payload.cadquery_code
    assert "phone_stand" in "\n".join(payload.self_check_notes)
