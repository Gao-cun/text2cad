from __future__ import annotations

import gmsh

import config


def find_single_face(x_value: float, name: str) -> int:
    tol = config.bbox_tol
    candidates: list[tuple[float, int]] = []
    for dim, tag in gmsh.model.getEntities(2):
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(dim, tag)
        if abs(xmin - x_value) <= tol and abs(xmax - x_value) <= tol:
            yz_area = max(ymax - ymin, 0.0) * max(zmax - zmin, 0.0)
            candidates.append((yz_area, tag))

    if not candidates:
        raise RuntimeError(f"Failed to find {name} face near x={x_value}.")

    candidates.sort(reverse=True)
    best_area, best_tag = candidates[0]
    if len(candidates) > 1 and abs(candidates[1][0] - best_area) <= 1e-6:
        raise RuntimeError(
            f"Expected a unique dominant {name} face near x={x_value}, found candidates: {candidates}"
        )
    return best_tag


def main() -> None:
    if not config.STEP_PATH.exists():
        raise FileNotFoundError(
            f"Missing STEP file {config.STEP_PATH}. Run `python mvp/1_build_cad.py` first."
        )

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
    gmsh.model.add("beam")
    try:
        gmsh.model.occ.importShapes(str(config.STEP_PATH))
        gmsh.model.occ.synchronize()

        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"Expected exactly one solid volume, found {len(volumes)}: {volumes}")

        fixed_face = find_single_face(config.fixed_x, "fixed")
        load_face = find_single_face(config.load_x, "load")
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

    print(f"Exported mesh: {config.MSH_PATH}")


if __name__ == "__main__":
    main()
