import cadquery as cq

def build_model():
    # 核心参数 (单位: mm)
    outer_r = 45.0
    wall_th = 3.0
    inner_r = outer_r - wall_th
    height = 150.0
    base_th = 4.0
    div_th = 3.0
    top_fillet = 2.0
    conn_fillet = 2.0

    # 坐标系对齐：底部 Z=-75，顶部 Z=75
    z_base = -height / 2.0
    z_wall = z_base + base_th
    wall_h = height - base_th

    # 1. 底座
    base = cq.Workplane("XY", origin=(0, 0, z_base)).circle(outer_r).extrude(base_th)

    # 2. 筒壁 (外圆柱 - 内圆柱)
    outer_cyl = cq.Workplane("XY", origin=(0, 0, z_wall)).circle(outer_r).extrude(wall_h)
    inner_cyl = cq.Workplane("XY", origin=(0, 0, z_wall)).circle(inner_r).extrude(wall_h)
    shell = outer_cyl.cut(inner_cyl)

    # 3. 垂直隔板 (Y向微扩0.05mm确保布尔运算拓扑干净，消除零厚度面)
    divider = cq.Workplane("XY", origin=(0, 0, z_wall)).box(div_th, inner_r * 2 + 0.05, wall_h)

    # 4. 融合为单一实体 (移除 .clean() 避免 OpenCASCADE 拓扑破坏，使用标准 union)
    body = base.union(shell).union(divider)

    # 5. 顶部边缘倒角
    body = body.edges(">Z").fillet(top_fillet)

    # 6. 隔板与内壁连接处垂直倒角 (缓解应力集中)
    body = body.edges("|Z").fillet(conn_fillet)

    # 确保返回单一 Solid 对象，避免网格化工具识别为 Compound 或 Shell
    return body.solids().val()