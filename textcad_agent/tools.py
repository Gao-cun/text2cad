from __future__ import annotations

import json
import os
import base64
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
    return design.analysis_config.to_runtime_config_source()


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
    fixed_x = float(config_data.get("effective_fixed_x", config_data["fixed_x"]))
    load_x = float(config_data.get("effective_load_x", config_data["load_x"]))
    bbox_tol = float(config_data["bbox_tol"])
    if fixed_x <= load_x:
        left = coords[:, 0] < (fixed_x + bbox_tol)
        right = coords[:, 0] > (load_x - bbox_tol)
    else:
        left = coords[:, 0] > (fixed_x - bbox_tol)
        right = coords[:, 0] < (load_x + bbox_tol)
    return left, right


def _load_effective_analysis_config(workspace: Path) -> dict[str, Any]:
    config_data = json.loads((workspace / "analysis_config.json").read_text(encoding="utf-8"))
    metadata_path = workspace / "mesh_boundary_metadata.json"
    if not metadata_path.exists():
        return config_data
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config_data
    for source_key, target_key in (
        ("effective_fixed_x", "effective_fixed_x"),
        ("effective_load_x", "effective_load_x"),
        ("bbox_tol", "bbox_tol"),
    ):
        if source_key in metadata:
            config_data[target_key] = metadata[source_key]
    return config_data


def _annotate_vtk_regions(vtk_path: Path, config_data: dict[str, Any]) -> pv.DataSet:
    mesh = pv.read(vtk_path)
    left, right = _region_masks(mesh.points, config_data)
    mesh.point_data["is_fixed"] = left.astype(np.uint8)
    mesh.point_data["is_load"] = right.astype(np.uint8)
    mesh.save(vtk_path)
    return mesh


def _summarize_vtk(workspace: Path) -> dict[str, Any]:
    vtk_path = workspace / "fea_result.vtk"
    config_data = _load_effective_analysis_config(workspace)
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
        f"""
        import sys
        from pathlib import Path

        repo_root = Path({str(REPO_ROOT)!r})
        sys.path.insert(0, str(repo_root))

        from textcad_agent.cad_backend import export_cad_artifacts

        result = export_cad_artifacts(Path.cwd())
        print(f"Exported STEP: {{result['step_path']}}")
        print(f"Exported STL: {{result['stl_path']}}")
        """
    )
    result = _run_command(
        [sys.executable, "-c", script],
        cwd=workspace,
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
        import sys
        from pathlib import Path

        repo_root = Path({str(REPO_ROOT)!r})
        workspace = Path({str(workspace)!r})
        sys.path.insert(0, str(repo_root))

        from textcad_agent.cad_backend import build_mesh_artifacts

        result = build_mesh_artifacts(workspace)
        print(f"Exported mesh: {{result['msh_path']}}")
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

        repo_root = Path({str(REPO_ROOT)!r})
        workspace = Path({str(workspace)!r})
        sys.path.insert(0, str(repo_root))

        from textcad_agent.cad_backend import run_fea_artifacts

        result = run_fea_artifacts(workspace, output_base={str(output_base)!r})
        print(f"Exported FEA VTK: {{result['vtk_path']}}")
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


def _write_fallback_render_images(workspace: Path, render: RenderConfig, reason: str) -> dict[str, Any]:
    render_dir = workspace / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[str] = []
    try:
        from PIL import Image, ImageDraw

        for view in render.views:
            image = Image.new("RGB", (render.image_width, render.image_height), color=(246, 248, 250))
            draw = ImageDraw.Draw(image)
            draw.rectangle((24, 24, render.image_width - 24, render.image_height - 24), outline=(170, 180, 190), width=2)
            draw.text((40, 42), f"TextCAD render fallback: {view}", fill=(20, 31, 43))
            draw.text((40, 72), reason[:220], fill=(92, 103, 115))
            image_path = render_dir / f"{view}.png"
            image.save(image_path)
            image_paths.append(str(image_path))
    except Exception:
        fallback_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP48OEDAAQCAgGX5lN8AAAAAElFTkSuQmCC"
        )
        for view in render.views:
            image_path = render_dir / f"{view}.png"
            image_path.write_bytes(fallback_png)
            image_paths.append(str(image_path))

    (render_dir / "render_scale.json").write_text(
        json.dumps({"bounds": [], "dimensions_mm": {}, "fallback_reason": reason}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "image_paths": image_paths,
        "dimensions_mm": {},
        "scale_metadata_path": str(render_dir / "render_scale.json"),
        "render_fallback_reason": reason,
    }


def _render_views_in_process(workspace_path: str, render_config: dict[str, Any]) -> dict[str, Any]:
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


def _render_views(workspace_path: str, render_config: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(workspace_path)
    render = RenderConfig.model_validate(render_config)
    script = textwrap.dedent(
        f"""
        import json
        import sys
        from pathlib import Path

        repo_root = Path({str(REPO_ROOT)!r})
        sys.path.insert(0, str(repo_root))

        from textcad_agent.tools import _render_views_in_process

        result = _render_views_in_process({str(workspace)!r}, {render.model_dump()!r})
        print(json.dumps(result, ensure_ascii=False))
        """
    )
    try:
        result = _run_command([sys.executable, "-c", script], cwd=workspace)
        lines = [line for line in result["stdout"].splitlines() if line.strip()]
        payload = json.loads(lines[-1]) if lines else {}
        if not isinstance(payload, dict):
            raise RuntimeError("render subprocess returned a non-object payload")
        return {**payload, **result}
    except Exception as exc:
        return _write_fallback_render_images(workspace, render, f"PyVista render subprocess failed: {exc}")


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
    description="Build a Gmsh msh22 mesh from the exported STEP artifact.",
)(_build_mesh)

solve_fea = tool(
    "solve_fea",
    args_schema=WorkspacePathInput,
    description="Run the SfePy backend and summarize VTK displacement outputs.",
)(_solve_fea)

render_views = tool(
    "render_views",
    args_schema=RenderViewsInput,
    description="Render fixed camera views for visual QA.",
)(_render_views)
