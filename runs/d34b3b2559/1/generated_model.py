from __future__ import annotations

import cadquery as cq

def build_model():
    return (
        cq.Workplane("XY")
        .box(80.0, 40.0, 40.0)
        .translate((80.0 / 2.0, 0.0, 0.0))
    )
