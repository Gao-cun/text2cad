from __future__ import annotations

import cadquery as cq

def build_model():
    return (
        cq.Workplane("XY")
        .box(20.0, 20.0, 20.0)
        .translate((20.0 / 2.0, 0.0, 0.0))
    )
