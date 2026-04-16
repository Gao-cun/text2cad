from __future__ import annotations

import cadquery as cq

def build_model():
    depth = 95.0
    width = 78.0
    height = 110.0
    lip_height = max(10.0, min(18.0, height * 0.13))
    support_x = max(18.0, depth * 0.19)
    shelf_x = max(support_x + 22.0, depth * 0.57)
    z_bottom = -height / 2.0
    z_top = height / 2.0
    profile = (
        cq.Workplane("XZ")
        .polyline(
            [
                (0.0, z_bottom),
                (depth, z_bottom),
                (depth, z_bottom + lip_height),
                (shelf_x, z_bottom + lip_height),
                (support_x, z_top),
                (0.0, z_top),
            ]
        )
        .close()
    )
    body = profile.extrude(width).translate((0.0, -width / 2.0, 0.0))
    inner_width = max(width - 16.0, width * 0.6)
    cutout = (
        cq.Workplane("XZ")
        .polyline(
            [
                (12.0, z_bottom + 8.0),
                (depth - 14.0, z_bottom + 8.0),
                (max(support_x + 14.0, shelf_x - 10.0), z_bottom + lip_height + 2.0),
                (support_x + 12.0, z_top - 14.0),
                (12.0, z_top - 14.0),
            ]
        )
        .close()
        .extrude(inner_width)
        .translate((0.0, -inner_width / 2.0, 0.0))
    )
    cable_slot = (
        cq.Workplane("XY")
        .box(max(12.0, depth * 0.18), max(18.0, width * 0.32), max(6.0, lip_height * 0.7))
        .translate((depth * 0.52, 0.0, z_bottom + max(6.0, lip_height * 0.35)))
    )
    return body.cut(cutout).cut(cable_slot)
