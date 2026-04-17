import cadquery as cq

def build_model():
    OD = 100.0
    HEIGHT = 150.0
    WALL = 3.0
    PART_THICK = 3.0
    BOT_THICK = 4.0
    TOP_R = 1.5
    JUNC_R = 2.0

    ID = OD - 2 * WALL
    INNER_H = HEIGHT - BOT_THICK
    Z_BASE = -HEIGHT / 2.0

    # 1. 底部环形底板 (Z: -75 ~ -71)
    bottom = cq.Workplane("XY").circle(OD / 2).circle(ID / 2).extrude(BOT_THICK)
    bottom = bottom.translate((0, 0, Z_BASE))

    # 2. 筒壁 (Z: -71 ~ 75)
    wall = cq.Workplane("XY").circle(OD / 2).circle(ID / 2).extrude(INNER_H)
    wall = wall.translate((0, 0, Z_BASE + BOT_THICK))

    # 3. 垂直隔板 (沿Y轴方向，厚度沿X轴)
    partition = cq.Workplane("XY").rect(PART_THICK, ID).extrude(INNER_H)
    partition = partition.translate((0, 0, Z_BASE + BOT_THICK))

    # 4. 布尔合并
    solid = bottom.union(wall).union(partition)

    # 5. 顶部边缘倒角 (防割手 & 改善层纹)
    top_edges = solid.edges(">Z")
    solid = top_edges.fillet(TOP_R)

    # 6. 隔板与筒壁连接处倒角 (应力分散)
    junc_edges = solid.edges("|Z and not (>Z or <Z)")
    solid = junc_edges.fillet(JUNC_R)

    return solid.clean()