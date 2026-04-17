from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv
from langchain.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from .state import ClarifiedSpec, DesignPayload, RenderConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
MVP_DIR = REPO_ROOT / "mvp"
RUNS_ROOT = REPO_ROOT / "runs"


class MaterializeWorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    iteration: int = Field(ge=1)
    design_payload: dict[str, Any]
    clarified_spec: dict[str, Any]
    engineering_prompt: str = ""
    latest_revision_brief: str = ""
    physics_report: str = ""
    design_request: str = ""
    physics_review: dict[str, Any] = Field(default_factory=dict)
    visual_review: dict[str, Any] = Field(default_factory=dict)


class PersistIterationArtifactsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_path: str
    engineering_prompt: str = ""
    latest_revision_brief: str = ""
    physics_report: str = ""
    design_request: str = ""
    physics_review: dict[str, Any] = Field(default_factory=dict)
    visual_review: dict[str, Any] = Field(default_factory=dict)


class WorkspacePathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_path: str


class RenderViewsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_path: str
    render_config: dict[str, Any]


def _analysis_config_content(design: DesignPayload) -> str:
    analysis = design.analysis_config.model_dump()
    lines = [
        "from pathlib import Path",
        "",
        f"length_mm = {analysis['length_mm']}",
        f"width_mm = {analysis['width_mm']}",
        f"height_mm = {analysis['height_mm']}",
        f"fixed_x = {analysis['fixed_x']}",
        f"load_x = {analysis['load_x']}",
        f"bbox_tol = {analysis['bbox_tol']}",
        f"load_vector_n = {tuple(analysis['load_vector_n'])}",
        f"young_modulus_mpa = {analysis['young_modulus_mpa']}",
        f"poisson_ratio = {analysis['poisson_ratio']}",
        "",
        "REPO_ROOT = Path(__file__).resolve().parent",
        'STEP_PATH = REPO_ROOT / "model.step"',
        'STL_PATH = REPO_ROOT / "model.stl"',
        'MSH_PATH = REPO_ROOT / "model.msh"',
    ]
    return "\n".join(lines) + "\n"


def _write_iteration_artifacts(
    workspace: Path,
    *,
    engineering_prompt: str = "",
    latest_revision_brief: str = "",
    physics_report: str = "",
    design_request: str = "",
    physics_review: dict[str, Any] | None = None,
    visual_review: dict[str, Any] | None = None,
) -> None:
    text_files = {
        "engineering_prompt.txt": engineering_prompt,
        "revision_brief.txt": latest_revision_brief,
        "physics_report.txt": physics_report,
        "design_request.txt": design_request,
    }
    for filename, content in text_files.items():
        (workspace / filename).write_text((content or "").rstrip() + "\n", encoding="utf-8")

    json_files = {
        "physics_review.json": physics_review or {},
        "visual_review.json": visual_review or {},
    }
    for filename, payload in json_files.items():
        (workspace / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _run_command(
    command: list[str],
    cwd: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result = {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "command": " ".join(command),
    }
    if completed.returncode != 0:
        combined = (completed.stdout + "\n" + completed.stderr).strip()
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}\n{combined}"
        )
    return result


def _region_masks(coords: np.ndarray, config_data: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    left = coords[:, 0] < (config_data["fixed_x"] + config_data["bbox_tol"])
    right = coords[:, 0] > (config_data["load_x"] - config_data["bbox_tol"])
    return left, right


def _annotate_vtk_regions(vtk_path: Path, config_data: dict[str, Any]) -> pv.DataSet:
    mesh = pv.read(vtk_path)
    left, right = _region_masks(mesh.points, config_data)
    mesh.point_data["is_fixed"] = left.astype(np.uint8)
    mesh.point_data["is_load"] = right.astype(np.uint8)
    mesh.save(vtk_path)
    return mesh


def _summarize_vtk(workspace: Path) -> dict[str, Any]:
    vtk_path = workspace / "fea_result.vtk"
    config_data = json.loads((workspace / "analysis_config.json").read_text(encoding="utf-8"))
    mesh = _annotate_vtk_regions(vtk_path, config_data)
    displacement = mesh.point_data["u"]
    coords = mesh.points
    magnitude = np.linalg.norm(displacement, axis=1)
    left, right = _region_masks(coords, config_data)
    max_index = int(np.argmax(magnitude))
    return {
        "vtk_path": str(vtk_path),
        "max_disp_mm": float(magnitude.max()),
        "max_stress_mpa": None,
        "left_max_disp_mm": float(magnitude[left].max()) if left.any() else None,
        "right_max_disp_mm": float(magnitude[right].max()) if right.any() else None,
        "max_disp_location": coords[max_index].tolist(),
    }


def _materialize_workspace(
    run_id: str,
    iteration: int,
    design_payload: dict[str, Any],
    clarified_spec: dict[str, Any],
    engineering_prompt: str = "",
    latest_revision_brief: str = "",
    physics_report: str = "",
    design_request: str = "",
    physics_review: dict[str, Any] | None = None,
    visual_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    design = DesignPayload.model_validate(design_payload)
    spec_payload = dict(clarified_spec)
    spec_payload.pop("backend_config", None)
    spec = ClarifiedSpec.model_validate(spec_payload)
    workspace = RUNS_ROOT / run_id / str(iteration)
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    (workspace / "generated_model.py").write_text(design.cadquery_code, encoding="utf-8")
    (workspace / "analysis_config.json").write_text(
        json.dumps(design.analysis_config.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "render_config.json").write_text(
        json.dumps(design.render_config.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "clarified_spec.json").write_text(
        json.dumps(spec.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "config.py").write_text(_analysis_config_content(design), encoding="utf-8")
    _write_iteration_artifacts(
        workspace,
        engineering_prompt=engineering_prompt,
        latest_revision_brief=latest_revision_brief,
        physics_report=physics_report,
        design_request=design_request,
        physics_review=physics_review,
        visual_review=visual_review,
    )

    return {
        "workspace_path": str(workspace),
        "generated_model_path": str(workspace / "generated_model.py"),
        "analysis_config_path": str(workspace / "analysis_config.json"),
        "config_path": str(workspace / "config.py"),
    }


def _persist_iteration_artifacts(
    workspace_path: str,
    engineering_prompt: str = "",
    latest_revision_brief: str = "",
    physics_report: str = "",
    design_request: str = "",
    physics_review: dict[str, Any] | None = None,
    visual_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_path)
    _write_iteration_artifacts(
        workspace,
        engineering_prompt=engineering_prompt,
        latest_revision_brief=latest_revision_brief,
        physics_report=physics_report,
        design_request=design_request,
        physics_review=physics_review,
        visual_review=visual_review,
    )
    return {"workspace_path": str(workspace)}


def _build_cad(workspace_path: str) -> dict[str, Any]:
    workspace = Path(workspace_path)
    script = textwrap.dedent(
        """
        from pathlib import Path
        import importlib.util
        from types import SimpleNamespace
        import cadquery as cq
        import config

        try:
            from cadquery.occ_impl.geom import BoundBox
        except Exception:
            BoundBox = None

        if BoundBox is not None and not hasattr(BoundBox, "min"):
            BoundBox.min = property(lambda self: SimpleNamespace(X=self.xmin, Y=self.ymin, Z=self.zmin))
        if BoundBox is not None and not hasattr(BoundBox, "max"):
            BoundBox.max = property(lambda self: SimpleNamespace(X=self.xmax, Y=self.ymax, Z=self.zmax))

        _original_fillet = cq.Workplane.fillet
        def _safe_fillet(self, radius):
            try:
                return _original_fillet(self, radius)
            except Exception as exc:
                message = str(exc).lower()
                if "edges be selected" in message or "command not done" in message:
                    return self.parent if getattr(self, "parent", None) is not None else self
                raise
        cq.Workplane.fillet = _safe_fillet

        _original_chamfer = cq.Workplane.chamfer
        def _safe_chamfer(self, length, length2=None):
            try:
                if length2 is None:
                    return _original_chamfer(self, length)
                return _original_chamfer(self, length, length2)
            except Exception as exc:
                message = str(exc).lower()
                if "edges be selected" in message or "command not done" in message:
                    return self.parent if getattr(self, "parent", None) is not None else self
                raise
        cq.Workplane.chamfer = _safe_chamfer

        module_path = Path("generated_model.py")
        spec = importlib.util.spec_from_file_location("generated_model", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load generated_model.py")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        model = None
        for candidate_name in ("build_model", "build", "make_model"):
            candidate = getattr(module, candidate_name, None)
            if callable(candidate):
                model = candidate()
                break

        if model is None:
            model = getattr(module, "MODEL", None) or getattr(module, "model", None)

        if model is None:
            raise RuntimeError(
                "Generated CAD code must define build_model()/build()/make_model() or MODEL/model."
            )

        cq.exporters.export(model, str(config.STEP_PATH))
        cq.exporters.export(model, str(config.STL_PATH))
        print(f"Exported STEP: {config.STEP_PATH}")
        print(f"Exported STL: {config.STL_PATH}")
        """
    )
    result = _run_command(
        [sys.executable, "-c", script],
        cwd=workspace,
        extra_env={"PYTHONPATH": str(workspace)},
    )
    return {
        "step_path": str(workspace / "model.step"),
        "stl_path": str(workspace / "model.stl"),
        **result,
    }


def _build_mesh(workspace_path: str) -> dict[str, Any]:
    workspace = Path(workspace_path)
    script = textwrap.dedent(
        f"""
        import runpy
        import sys
        from pathlib import Path

        workspace = Path({str(workspace)!r})
        sys.path.insert(0, str(workspace))
        runpy.run_path({str(MVP_DIR / "2_build_mesh.py")!r}, run_name="__main__")
        """
    )
    result = _run_command(
        [sys.executable, "-c", script],
        cwd=workspace,
    )
    return {
        "msh_path": str(workspace / "model.msh"),
        **result,
    }


def _resolve_sfepy_runner() -> str:
    local_runner = Path(sys.executable).with_name("sfepy-run")
    if local_runner.exists():
        return str(local_runner)
    return "sfepy-run"


def _solve_fea(workspace_path: str) -> dict[str, Any]:
    workspace = Path(workspace_path)
    output_base = workspace / "fea_result"
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path

        workspace = Path({str(workspace)!r})
        sys.path.insert(0, str(workspace))
        sys.argv = [
            "sfepy-run",
            {str(MVP_DIR / "3_solve_fea.py")!r},
            "-o",
            {str(output_base)!r},
        ]
        from sfepy.scripts.simple import main

        raise SystemExit(main())
        """
    )
    result = _run_command(
        [sys.executable, "-c", script],
        cwd=workspace,
    )
    summary = _summarize_vtk(workspace)
    summary.update(result)
    return summary


def _camera_vector(view_name: str) -> tuple[float, float, float]:
    vectors = {
        "iso_front": (1.0, 1.0, 1.0),
        "iso_back": (-1.0, -1.0, 1.0),
        "top": (0.0, 0.0, 1.0),
        "side": (1.0, 0.0, 0.0),
    }
    return vectors.get(view_name, (1.0, 1.0, 1.0))


def _render_views(workspace_path: str, render_config: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(workspace_path)
    render = RenderConfig.model_validate(render_config)
    stl_path = workspace / "model.stl"
    render_dir = workspace / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)

    pv.OFF_SCREEN = True
    mesh = pv.read(stl_path)
    bounds = mesh.bounds
    dimensions_mm = {
        "x": float(bounds[1] - bounds[0]),
        "y": float(bounds[3] - bounds[2]),
        "z": float(bounds[5] - bounds[4]),
    }
    dimension_text = (
        "Scale(mm) "
        f"X={dimensions_mm['x']:.1f} "
        f"Y={dimensions_mm['y']:.1f} "
        f"Z={dimensions_mm['z']:.1f}"
    )

    (render_dir / "render_scale.json").write_text(
        json.dumps({"bounds": list(bounds), "dimensions_mm": dimensions_mm}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    image_paths: list[str] = []
    for view in render.views:
        plotter = pv.Plotter(off_screen=True, window_size=(render.image_width, render.image_height))
        plotter.set_background("white")
        plotter.add_mesh(mesh, color="lightgray", show_edges=True)
        plotter.add_bounding_box(color="black", line_width=1)
        plotter.show_bounds(
            grid="back",
            location="outer",
            ticks="outside",
            xtitle="X (mm)",
            ytitle="Y (mm)",
            ztitle="Z (mm)",
            font_size=10,
        )
        plotter.add_text(dimension_text, position="upper_left", font_size=11, color="black")
        plotter.view_vector(_camera_vector(view))
        plotter.camera.zoom(1.15)
        image_path = render_dir / f"{view}.png"
        plotter.screenshot(str(image_path))
        plotter.close()
        image_paths.append(str(image_path))

    return {
        "image_paths": image_paths,
        "dimensions_mm": dimensions_mm,
        "scale_metadata_path": str(render_dir / "render_scale.json"),
    }


materialize_workspace = tool(
    "materialize_workspace",
    args_schema=MaterializeWorkspaceInput,
    description="Create an isolated run workspace and write generated CAD inputs.",
)(_materialize_workspace)

persist_iteration_artifacts = tool(
    "persist_iteration_artifacts",
    args_schema=PersistIterationArtifactsInput,
    description="Write human-readable prompt/review artifacts into the current iteration workspace.",
)(_persist_iteration_artifacts)

build_cad = tool(
    "build_cad",
    args_schema=WorkspacePathInput,
    description="Execute generated CadQuery code and export STEP/STL artifacts.",
)(_build_cad)

build_mesh = tool(
    "build_mesh",
    args_schema=WorkspacePathInput,
    description="Reuse the MVP gmsh backend to create an msh22 mesh.",
)(_build_mesh)

solve_fea = tool(
    "solve_fea",
    args_schema=WorkspacePathInput,
    description="Reuse the MVP SfePy backend and summarize VTK displacement outputs.",
)(_solve_fea)

render_views = tool(
    "render_views",
    args_schema=RenderViewsInput,
    description="Render fixed camera views for visual QA.",
)(_render_views)
