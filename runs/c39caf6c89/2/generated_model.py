import cadquery as cq

def build_model():
    # 核心参数 (单位: mm)
    outer_r = 45.0
    wall_th = 3.0
    inner_r = outer_r - wall_th
    height = 150.0
    base_th = 4.0
    div_th = 3.0
    div_h = height - base_th
    top_fillet = 2.0
    conn_fillet = 2.0

    # 坐标系居中，匹配固定边界盒要求 (Z: -75 ~ 75)
    z_start = -height / 2.0

    # 1. 底座
    base = cq.Workplane("XY", origin=(0, 0, z_start)).circle(outer_r).extrude(base_th)

    # 2. 筒壁 (外圆柱 - 内圆柱)
    outer_shell = cq.Workplane("XY", origin=(0, 0, z_start + base_th)).circle(outer_r).extrude(div_h)
    inner_void = cq.Workplane("XY", origin=(0, 0, z_start + base_th)).circle(inner_r).extrude(div_h)
    shell = outer_shell.cut(inner_void)

    # 3. 垂直隔板 (Y方向微扩0.05mm确保布尔运算拓扑干净，消除零厚度面)
    divider = cq.Workplane("XY", origin=(0, 0, z_start + base_th)).box(div_th, inner_r * 2 + 0.05, div_h)

    # 4. 合并为单一实体并清理内部重叠面
    body = base.union(shell).union(divider).clean()

    # 5. 顶部边缘倒角 (外圈、内圈、隔板顶边)
    body = body.edges(">Z").fillet(top_fillet)

    # 6. 隔板与内壁连接处垂直倒角 (仅作用于隔板垂直棱边，缓解应力集中)
    body = body.edges("|Z").fillet(conn_fillet)

    # 确保返回单一Solid对象
    return body.val()