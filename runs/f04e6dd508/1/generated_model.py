from __future__ import annotations

import cadquery as cq

def build_model():
    return (
        cq.Workplane("XY")
        .box(80.0, 80.0, 150.0)
        .translate((80.0 / 2.0, 0.0, 0.0))
        .edges('|Z').fillet(min(2.0, 10.00))
    )
