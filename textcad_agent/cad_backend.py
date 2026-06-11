from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


def resolve_workspace(workspace: str | Path | None = None) -> Path:
    if workspace is not None:
        return Path(workspace).resolve()
    cwd = Path.cwd()
    if (cwd / "config.py").exists():
        return cwd.resolve()
    return Path(__file__).resolve().parent


def _load_module_from_path(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_cadquery_runtime() -> None:
    import cadquery as cq

    try:
        from cadquery.occ_impl.geom import BoundBox
    except Exception:
        BoundBox = None

    if BoundBox is not None and not hasattr(BoundBox, "min"):
        BoundBox.min = property(lambda self: SimpleNamespace(X=self.xmin, Y=self.ymin, Z=self.zmin))
    if BoundBox is not None and not hasattr(BoundBox, "max"):
        BoundBox.max = property(lambda self: SimpleNamespace(X=self.xmax, Y=self.ymax, Z=self.zmax))

    if not getattr(cq.Workplane.fillet, "_textcad_safe_patch", False):
        original_fillet = cq.Workplane.fillet

        def _safe_fillet(self, radius):
            try:
                return original_fillet(self, radius)
            except Exception as exc:
                message = str(exc).lower()
                if "edges be selected" in message or "command not done" in message:
                    return self.parent if getattr(self, "parent", None) is not None else self
                raise

        _safe_fillet._textcad_safe_patch = True  # type: ignore[attr-defined]
        cq.Workplane.fillet = _safe_fillet

    if not getattr(cq.Workplane.chamfer, "_textcad_safe_patch", False):
        original_chamfer = cq.Workplane.chamfer

        def _safe_chamfer(self, length, length2=None):
            try:
                if length2 is None:
                    return original_chamfer(self, length)
                return original_chamfer(self, length, length2)
            except Exception as exc:
                message = str(exc).lower()
                if "edges be selected" in message or "command not done" in message:
                    return self.parent if getattr(self, "parent", None) is not None else self
                raise

        _safe_chamfer._textcad_safe_patch = True  # type: ignore[attr-defined]
        cq.Workplane.chamfer = _safe_chamfer


def _resolve_generated_model(module: ModuleType) -> Any:
    for candidate_name in ("build_model", "build", "make_model"):
        candidate = getattr(module, candidate_name, None)
        if callable(candidate):
            return candidate()
    return getattr(module, "MODEL", None) or getattr(module, "model", None)


def _default_beam_model(config: ModuleType) -> Any:
    import cadquery as cq

    return (
        cq.Workplane("XY")
        .box(config.length_mm, config.width_mm, config.height_mm)
        .translate((config.length_mm / 2.0, 0.0, 0.0))
    )


def export_cad_artifacts(workspace: str | Path | None = None) -> dict[str, str]:
    import cadquery as cq

    resolved_workspace = resolve_workspace(workspace)
    config = _load_module_from_path("workspace_config", resolved_workspace / "config.py")
    _patch_cadquery_runtime()
    generated_model_path = resolved_workspace / "generated_model.py"
    if generated_model_path.exists():
        generated_model = _load_module_from_path("generated_model", generated_model_path)
        model = _resolve_generated_model(generated_model)
        if model is None:
            raise RuntimeError("Generated CAD code must define build_model()/build()/make_model() or MODEL/model.")
    else:
        model = _default_beam_model(config)

    cq.exporters.export(model, str(config.STEP_PATH))
    cq.exporters.export(model, str(config.STL_PATH))
    return {
        "step_path": str(config.STEP_PATH),
        "stl_path": str(config.STL_PATH),
    }


MESH_BOUNDARY_METADATA_NAME = "mesh_boundary_metadata.json"


def _model_bbox() -> tuple[float, float, float, float, float, float]:
    import gmsh

    entities = gmsh.model.getEntities(3) or gmsh.model.getEntities(2)
    if not entities:
        raise RuntimeError("Imported STEP contains no meshable volume or surface entities.")
    boxes = [gmsh.model.getBoundingBox(dim, tag) for dim, tag in entities]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        min(box[2] for box in boxes),
        max(box[3] for box in boxes),
        max(box[4] for box in boxes),
        max(box[5] for box in boxes),
    )


def _x_face_candidates(x_value: float, bbox_tol: float) -> list[tuple[float, int]]:
    import gmsh

    candidates: list[tuple[float, int]] = []
    for dim, tag in gmsh.model.getEntities(2):
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(dim, tag)
        if abs(xmin - x_value) <= bbox_tol and abs(xmax - x_value) <= bbox_tol:
            yz_area = max(ymax - ymin, 0.0) * max(zmax - zmin, 0.0)
            candidates.append((yz_area, tag))
    return candidates


def find_single_face(x_value: float, name: str, bbox_tol: float) -> int:
    candidates = _x_face_candidates(x_value, bbox_tol)
    if not candidates:
        raise RuntimeError(f"Failed to find {name} face near x={x_value}.")

    candidates.sort(reverse=True)
    best_area, best_tag = candidates[0]
    if len(candidates) > 1 and abs(candidates[1][0] - best_area) <= 1e-6:
        raise RuntimeError(f"Expected a unique dominant {name} face near x={x_value}, found candidates: {candidates}")
    return best_tag


def _select_single_face(
    requested_x: float,
    fallback_x: float,
    name: str,
    bbox_tol: float,
) -> tuple[int, float, str | None]:
    try:
        return find_single_face(requested_x, name, bbox_tol), requested_x, None
    except RuntimeError as requested_error:
        try:
            fallback_tag = find_single_face(fallback_x, name, bbox_tol)
        except RuntimeError:
            raise requested_error
        return (
            fallback_tag,
            fallback_x,
            f"{name} face requested at x={requested_x} was not found; using model bbox x={fallback_x}.",
        )


def _write_mesh_boundary_metadata(
    workspace: Path,
    *,
    requested_fixed_x: float,
    requested_load_x: float,
    effective_fixed_x: float,
    effective_load_x: float,
    bbox_tol: float,
    model_bbox: tuple[float, float, float, float, float, float],
    fallback_reasons: list[str],
) -> None:
    payload = {
        "requested_fixed_x": requested_fixed_x,
        "requested_load_x": requested_load_x,
        "effective_fixed_x": effective_fixed_x,
        "effective_load_x": effective_load_x,
        "bbox_tol": bbox_tol,
        "model_bbox": {
            "xmin": model_bbox[0],
            "ymin": model_bbox[1],
            "zmin": model_bbox[2],
            "xmax": model_bbox[3],
            "ymax": model_bbox[4],
            "zmax": model_bbox[5],
        },
        "fallback_reasons": fallback_reasons,
    }
    (workspace / MESH_BOUNDARY_METADATA_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_mesh_artifacts(workspace: str | Path | None = None) -> dict[str, str]:
    import gmsh

    resolved_workspace = resolve_workspace(workspace)
    config = _load_module_from_path("workspace_config", resolved_workspace / "config.py")

    if not Path(config.STEP_PATH).exists():
        raise FileNotFoundError(f"Missing STEP file {config.STEP_PATH}. Run CAD export first.")

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.model.add("textcad-model")
    try:
        gmsh.model.occ.importShapes(str(config.STEP_PATH))
        gmsh.model.occ.synchronize()

        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"Expected exactly one solid volume, found {len(volumes)}: {volumes}")

        model_bbox = _model_bbox()
        xmin, xmax = model_bbox[0], model_bbox[3]
        if config.fixed_x <= config.load_x:
            fixed_fallback_x, load_fallback_x = xmin, xmax
        else:
            fixed_fallback_x, load_fallback_x = xmax, xmin

        fixed_face, effective_fixed_x, fixed_reason = _select_single_face(
            config.fixed_x,
            fixed_fallback_x,
            "fixed",
            config.bbox_tol,
        )
        load_face, effective_load_x, load_reason = _select_single_face(
            config.load_x,
            load_fallback_x,
            "load",
            config.bbox_tol,
        )
        if fixed_face == load_face:
            raise RuntimeError(
                "Fixed and load boundary selection resolved to the same face. "
                f"requested_fixed_x={config.fixed_x}, requested_load_x={config.load_x}, "
                f"effective_fixed_x={effective_fixed_x}, effective_load_x={effective_load_x}."
            )

        fallback_reasons = [reason for reason in (fixed_reason, load_reason) if reason]
        _write_mesh_boundary_metadata(
            resolved_workspace,
            requested_fixed_x=float(config.fixed_x),
            requested_load_x=float(config.load_x),
            effective_fixed_x=float(effective_fixed_x),
            effective_load_x=float(effective_load_x),
            bbox_tol=float(config.bbox_tol),
            model_bbox=model_bbox,
            fallback_reasons=fallback_reasons,
        )
        volume_tag = volumes[0][1]

        gmsh.model.addPhysicalGroup(2, [fixed_face], tag=1)
        gmsh.model.setPhysicalName(2, 1, "Fixed")
        gmsh.model.addPhysicalGroup(2, [load_face], tag=2)
        gmsh.model.setPhysicalName(2, 2, "Load")
        gmsh.model.addPhysicalGroup(3, [volume_tag], tag=3)
        gmsh.model.setPhysicalName(3, 3, "Volume")

        gmsh.model.mesh.generate(3)
        gmsh.write(str(config.MSH_PATH))
    finally:
        gmsh.finalize()

    return {"msh_path": str(config.MSH_PATH)}


def run_fea_artifacts(workspace: str | Path | None = None, output_base: str | Path | None = None) -> dict[str, str]:
    from sfepy.scripts.simple import main

    resolved_workspace = resolve_workspace(workspace)
    problem_path = Path(__file__).resolve().parent / "fea_problem.py"
    resolved_output_base = Path(output_base) if output_base is not None else (resolved_workspace / "fea_result")

    previous_argv = list(sys.argv)
    previous_path = list(sys.path)
    sys.path.insert(0, str(resolved_workspace))
    sys.argv = [
        "sfepy-run",
        str(problem_path),
        "-o",
        str(resolved_output_base),
    ]
    try:
        exit_code = main()
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path

    if exit_code not in (0, None):
        raise RuntimeError(f"SfePy exited with status {exit_code}.")

    return {"vtk_path": str(resolved_output_base.with_suffix(".vtk"))}
