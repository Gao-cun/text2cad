import cadquery as cq

def build_model():
    # 参数定义
    outer_r = 45.0
    wall_thick = 2.5
    inner_r = outer_r - wall_thick
    height = 150.0
    bottom_thick = 2.5
    part_thick = 2.5
    fillet_r = 2.5

    # 1. 外圆柱实体
    outer = cq.Workplane("XY").circle(outer_r).extrude(height)

    # 2. 内部挖空（保留底部厚度）
    inner_void = cq.Workplane("XY").circle(inner_r).extrude(height - bottom_thick).translate((0, 0, bottom_thick))

    # 3. 垂直隔板
    part = cq.Workplane("XY").box(inner_r * 2, part_thick, height, centered=(True, True, True)).translate((0, 0, height / 2))

    # 4. 布尔运算组合
    base = outer.cut(inner_void)
    model = base.union(part.val())

    # 5. 内部交接处倒角（缓解应力集中）
    wp = cq.Workplane("XY").newObject([model])
    all_z_edges = wp.edges("|Z").vals()
    # 筛选位于隔板与内壁交界处的垂直边
    junction_edges = [e for e in all_z_edges if abs(e.Center().x) < (inner_r + 0.5) and abs(e.Center().y) < 0.5]

    model = model.fillet(fillet_r, junction_edges)
    return model