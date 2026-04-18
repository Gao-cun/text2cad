from __future__ import annotations

import importlib.util
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


def find_single_face(x_value: float, name: str, bbox_tol: float) -> int:
    import gmsh

    candidates: list[tuple[float, int]] = []
    for dim, tag in gmsh.model.getEntities(2):
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(dim, tag)
        if abs(xmin - x_value) <= bbox_tol and abs(xmax - x_value) <= bbox_tol:
            yz_area = max(ymax - ymin, 0.0) * max(zmax - zmin, 0.0)
            candidates.append((yz_area, tag))

    if not candidates:
        raise RuntimeError(f"Failed to find {name} face near x={x_value}.")

    candidates.sort(reverse=True)
    best_area, best_tag = candidates[0]
    if len(candidates) > 1 and abs(candidates[1][0] - best_area) <= 1e-6:
        raise RuntimeError(f"Expected a unique dominant {name} face near x={x_value}, found candidates: {candidates}")
    return best_tag


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

        fixed_face = find_single_face(config.fixed_x, "fixed", config.bbox_tol)
        load_face = find_single_face(config.load_x, "load", config.bbox_tol)
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
    problem_path = Path(__file__).resolve().parent / "3_solve_fea.py"
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
