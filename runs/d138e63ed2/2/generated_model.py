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

    # 1. 构建空心圆柱筒体（使用 shell 保证外壁光滑且底部封闭）
    cylinder = cq.Workplane("XY").circle(outer_r).extrude(height).faces(">Z").shell(-wall_thick)

    # 2. 构建垂直隔板
    # 隔板高度略低于筒体，底部贴合筒底内面
    divider = cq.Workplane("XY").box(
        inner_r * 2, part_thick, height - bottom_thick,
        centered=(True, True, False)
    ).translate((0, 0, bottom_thick))

    # 3. 组合实体
    model = cylinder.union(divider)

    # 4. 倒角处理
    # 隔板与内壁交接的垂直边（仅这两条垂直边存在，使用选择器避免传入列表导致API报错）
    model = model.edges("|Z").fillet(fillet_r)
    # 顶部外边缘轻微倒角，提升手感与3D打印质量
    model = model.edges(">Z").fillet(1.0)

    return model