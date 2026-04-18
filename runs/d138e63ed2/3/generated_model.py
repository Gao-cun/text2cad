import cadquery as cq

def build_model():
    outer_r = 45.0
    wall_thick = 2.5
    inner_r = outer_r - wall_thick
    height = 150.0
    bottom_thick = 2.5
    div_thick = 2.5
    fillet_r = 2.0

    # 1. 筒壁：空心圆柱
    wall = cq.Workplane("XY").circle(outer_r).circle(inner_r).extrude(height)

    # 2. 底板：实心圆盘
    base = cq.Workplane("XY").circle(outer_r).extrude(bottom_thick)

    # 3. 隔板：实体长方体，略宽于内径以确保布尔融合无零厚度面
    divider = cq.Workplane("XY").box(
        inner_r * 2 + 0.2, div_thick, height,
        centered=(True, True, False)
    )

    # 4. 严格合并为单一水密实体
    model = wall.union(base).union(divider)

    # 5. 倒角处理
    # 隔板与内壁交接的垂直边（Y轴附近）
    model = model.edges("|Z").edges("Y<1.5 and Y>-1.5").fillet(fillet_r)
    # 底部边缘（内外圈）
    model = model.edges("<Z").fillet(fillet_r)
    # 顶部边缘
    model = model.edges(">Z").fillet(1.0)

    return model