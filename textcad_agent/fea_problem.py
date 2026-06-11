from __future__ import annotations

import config
import json
import numpy as np
from pathlib import Path
from sfepy.mechanics.matcoefs import stiffness_from_youngpoisson


filename_mesh = str(config.MSH_PATH)


def _effective_boundary_value(key: str, fallback: float) -> float:
    metadata_path = Path(config.MSH_PATH).with_name("mesh_boundary_metadata.json")
    if not metadata_path.exists():
        return fallback
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    value = payload.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


effective_fixed_x = _effective_boundary_value("effective_fixed_x", config.fixed_x)
effective_load_x = _effective_boundary_value("effective_load_x", config.load_x)
if effective_fixed_x <= effective_load_x:
    fixed_region_expr = f"vertices in (x < {effective_fixed_x + config.bbox_tol})"
    load_region_expr = f"vertices in (x > {effective_load_x - config.bbox_tol})"
else:
    fixed_region_expr = f"vertices in (x > {effective_fixed_x - config.bbox_tol})"
    load_region_expr = f"vertices in (x < {effective_load_x + config.bbox_tol})"

options = {
    "nls": "newton",
    "ls": "ls",
    "output_format": "vtk",
}

fields = {
    "displacement": ("real", "vector", "Omega", 1),
}


def get_load(ts, coors, mode=None, **kwargs):
    if mode == "qp":
        val = np.zeros_like(coors)[..., None]
        val[:, 0, 0] = config.load_vector_n[0]
        val[:, 1, 0] = config.load_vector_n[1]
        val[:, 2, 0] = config.load_vector_n[2]
        return {"val": val}

materials = {
    "solid": (
        {
            "D": stiffness_from_youngpoisson(
                dim=3,
                young=config.young_modulus_mpa,
                poisson=config.poisson_ratio,
            ),
        },
    ),
    "load": "get_load",
}

variables = {
    "u": ("unknown field", "displacement", 0),
    "v": ("test field", "displacement", "u"),
}

functions = {
    "get_load": (get_load,),
}

regions = {
    "Omega": "all",
    "Left": (fixed_region_expr, "facet"),
    "Right": (load_region_expr, "facet"),
}

ebcs = {
    "fix_left": ("Left", {"u.all": 0.0}),
}

integrals = {
    "i": 2,
}

equations = {
    "balance_of_forces": """
        dw_lin_elastic.i.Omega(solid.D, v, u)
        = dw_surface_ltr.i.Right(load.val, v)
    """,
}

solvers = {
    "ls": ("ls.scipy_direct", {}),
    "newton": ("nls.newton", {"i_max": 1, "eps_a": 1e-10}),
}
