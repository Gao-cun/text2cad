import cadquery as cq

def build_model():
    # 2D profile in XY plane. Y is vertical.
    # Explicitly designed to guarantee exact planar faces at X=0 (fixed) and X=100 (load)
    profile = cq.Workplane("XY").polyline([
        (0, 0),       # Back-bottom
        (100, 0),     # Front-bottom
        (100, 18),    # Front-top (includes phone stop height)
        (95, 18),     # Phone stop setback
        (95, 12),     # Phone stop base
        (55, 105),    # Backplate top-front (~65 deg slope)
        (0, 105),     # Backplate top-back
        (0, 0)        # Closes loop
    ]).close()

    # Extrude along Z to 80mm width
    solid = profile.extrude(80)

    # Center width along Z axis
    solid = solid.translate((0, 0, -40))

    # Apply 0.8mm chamfers to top edges only for safety and printability
    # Explicitly avoid chamfering boundary faces (X=0, X=100) and bottom face (Y=0)
    # to preserve exact planar geometry for FEA constraint mapping
    solid = solid.edges(">Y").chamfer(0.8)

    return solid