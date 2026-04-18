from __future__ import annotations

import pytest
from pydantic import ValidationError

from textcad_agent.state import AnalysisConfig, ClarifiedSpec, DesignPayload, DesignStatus, PhysicsReview, RenderConfig, VisualReview


def test_clarified_spec_validates_expected_fields():
    spec = ClarifiedSpec(
        request_summary="test",
        length_mm=100.0,
        width_mm=10.0,
        height_mm=10.0,
        fixed_boundary=[0.0, -5.0, -5.0, 0.0, 5.0, 5.0],
        load_boundary=[100.0, -5.0, -5.0, 100.0, 5.0, 5.0],
        load_vector_n=[0.0, -50.0, 0.0],
    )
    assert spec.length_mm == 100.0
    assert spec.missing_high_risk_fields == []


def test_design_payload_rejects_invalid_vector_shape():
    with pytest.raises(ValidationError):
        DesignPayload(
            cadquery_code="def build_model():\n    return None\n",
            analysis_config=AnalysisConfig(
                length_mm=100.0,
                width_mm=10.0,
                height_mm=10.0,
                fixed_x=0.0,
                load_x=100.0,
                load_vector_n=[0.0, -50.0],
            ),
            render_config=RenderConfig(),
        )


def test_analysis_config_can_be_derived_from_clarified_spec():
    spec = ClarifiedSpec(
        request_summary="phone stand",
        length_mm=90.0,
        width_mm=70.0,
        height_mm=100.0,
        fixed_boundary=[0.0, -35.0, -50.0, 0.0, 35.0, 50.0],
        load_boundary=[90.0, -35.0, -50.0, 90.0, 35.0, 50.0],
        load_vector_n=[0.0, -5.0, 0.0],
    )

    backend = AnalysisConfig.from_clarified_spec(spec)

    assert backend.fixed_x == 0.0
    assert backend.load_x == 90.0
    assert backend.load_vector_n == [0.0, -5.0, 0.0]


def test_review_models_accept_pass_alias():
    visual = VisualReview(**{"pass": True, "issues": [], "missing_requirements": [], "recommended_edits": []})
    physics = PhysicsReview(
        **{"pass": False, "max_disp_mm": 10.0, "max_stress_mpa": None, "violations": ["too large"], "recommended_edits": ["thicken beam"]}
    )
    design = DesignStatus()
    assert visual.passed is True
    assert visual.backend == "heuristic_fallback"
    assert physics.passed is False
    assert design.state == "pending"
