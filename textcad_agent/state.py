from __future__ import annotations

import textwrap
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClarifiedSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_summary: str = ""
    object_type: str = ""
    design_brief: str = ""
    design_goals: list[str] = Field(default_factory=list)
    style_keywords: list[str] = Field(default_factory=list)
    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    unit_system: Literal["mm"] = "mm"
    material_name: str = "PLA"
    material_young_mpa: float = Field(default=3500.0, gt=0)
    material_poisson: float = Field(default=0.36, ge=0.0, lt=0.5)
    fixed_boundary: list[float]
    load_boundary: list[float]
    load_vector_n: list[float]
    bbox_tol: float = Field(default=0.2, gt=0)
    missing_high_risk_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    visual_requirements: list[str] = Field(default_factory=list)

    @field_validator("fixed_boundary", "load_boundary")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 6:
            raise ValueError("Bounding box must contain 6 floats.")
        return value

    @field_validator("load_vector_n")
    @classmethod
    def validate_vector(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("Load vector must contain 3 floats.")
        return value


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    fixed_x: float
    load_x: float
    bbox_tol: float = Field(default=0.2, gt=0)
    load_vector_n: list[float]
    young_modulus_mpa: float = Field(default=3500.0, gt=0)
    poisson_ratio: float = Field(default=0.36, ge=0.0, lt=0.5)

    @field_validator("load_vector_n")
    @classmethod
    def validate_vector(cls, value: list[float]) -> list[float]:
        if len(value) != 3:
            raise ValueError("Load vector must contain 3 floats.")
        return value

    @classmethod
    def from_clarified_spec(cls, spec: "ClarifiedSpec") -> "AnalysisConfig":
        fixed_x = float((spec.fixed_boundary[0] + spec.fixed_boundary[3]) / 2.0)
        load_x = float((spec.load_boundary[0] + spec.load_boundary[3]) / 2.0)
        return cls(
            length_mm=spec.length_mm,
            width_mm=spec.width_mm,
            height_mm=spec.height_mm,
            fixed_x=fixed_x,
            load_x=load_x,
            bbox_tol=spec.bbox_tol,
            load_vector_n=spec.load_vector_n,
            young_modulus_mpa=spec.material_young_mpa,
            poisson_ratio=spec.material_poisson,
        )

    def to_runtime_config_source(self) -> str:
        analysis = self.model_dump()
        return textwrap.dedent(
            f"""
            from pathlib import Path

            length_mm = {analysis["length_mm"]}
            width_mm = {analysis["width_mm"]}
            height_mm = {analysis["height_mm"]}
            fixed_x = {analysis["fixed_x"]}
            load_x = {analysis["load_x"]}
            bbox_tol = {analysis["bbox_tol"]}
            load_vector_n = {tuple(analysis["load_vector_n"])}
            young_modulus_mpa = {analysis["young_modulus_mpa"]}
            poisson_ratio = {analysis["poisson_ratio"]}

            REPO_ROOT = Path(__file__).resolve().parent
            STEP_PATH = REPO_ROOT / "model.step"
            STL_PATH = REPO_ROOT / "model.stl"
            MSH_PATH = REPO_ROOT / "model.msh"
            """
        ).lstrip()


class RenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    views: list[str] = Field(default_factory=lambda: ["iso_front", "iso_back", "top", "side"])
    image_width: int = Field(default=1024, gt=0)
    image_height: int = Field(default=768, gt=0)


class DesignPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cadquery_code: str = Field(min_length=1)
    analysis_config: AnalysisConfig
    render_config: RenderConfig = Field(default_factory=RenderConfig)
    self_check_notes: list[str] = Field(default_factory=list)


class DesignStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = "pending"
    error_message: str | None = None
    code_changed: bool | None = None
    used_model: bool = False


class VisualReview(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    passed: bool = Field(alias="pass")
    is_present: bool | None = None
    issues: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    recommended_edits: list[str] = Field(default_factory=list)
    backend: str = "heuristic_fallback"
    fallback_reason: str | None = None


class PhysicsReview(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    passed: bool = Field(alias="pass")
    max_disp_mm: float | None = None
    max_stress_mpa: float | None = None
    violations: list[str] = Field(default_factory=list)
    recommended_edits: list[str] = Field(default_factory=list)


class CompileStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    success: bool
    syntax_ok: bool = True
    security_ok: bool = True
    error_message: str | None = None


class AgentState(TypedDict, total=False):
    user_prompt: str
    clarified_spec: dict[str, Any]
    engineering_prompt: str
    assumptions: list[str]
    design_payload: dict[str, Any]
    design_request: str
    latest_revision_brief: str
    physics_report: str
    review_artifacts: dict[str, Any]
    design_status: dict[str, Any]
    run_id: str
    iteration: int
    compile_retry_count: int
    token_usage: dict[str, Any]
    workspace_path: str
    compile_status: dict[str, Any]
    tool_logs: dict[str, str]
    fea_results: dict[str, Any]
    vtk_paths: list[str]
    image_paths: list[str]
    visual_review: dict[str, Any]
    physics_review: dict[str, Any]
    feedback_history: list[str]
    clarification_request: dict[str, Any]
    final_status: Literal["running", "awaiting_user", "success", "failed"]
