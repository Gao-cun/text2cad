import cadquery as cq

def build_model():
    # 2D profile in XY plane (Y is vertical axis per prompt)
    # Designed for ~65° viewing angle, 100mm depth, 105mm height
    profile = cq.Workplane("XY").polyline([
        (0, 0),      # Back-bottom (aligns with fixed boundary X=0)
        (100, 0),    # Front-bottom (aligns with load boundary X=100)
        (100, 12),   # Front-top (base thickness)
        (55, 105),   # Backplate top-front (slope ~64.2°)
        (35, 105),   # Backplate top-back
        (35, 12),    # Inner wall top
        (45, 12),    # Phone lip front
        (45, 17),    # Phone lip top
        (35, 17)     # Phone lip back
    ]).close()

    # Extrude along Z axis to 80mm width
    solid = profile.extrude(80)

    # Center width along Z axis
    solid = solid.translate((0, 0, -40))

    # Apply 0.8mm chamfers to top and side edges for safety and printability
    # Avoid chamfering the bottom resting face to ensure bed adhesion
    solid = solid.edges(">Y").chamfer(0.8).edges("|Z").chamfer(0.8)

    return solid