from __future__ import annotations

import config
import numpy as np
from sfepy.mechanics.matcoefs import stiffness_from_youngpoisson


filename_mesh = str(config.MSH_PATH)

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
    "Left": (f"vertices in (x < {config.fixed_x + config.bbox_tol})", "facet"),
    "Right": (f"vertices in (x > {config.load_x - config.bbox_tol})", "facet"),
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
