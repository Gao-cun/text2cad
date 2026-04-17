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

    # 1. 生成外径圆柱实体
    body = cq.Workplane("XY").circle(outer_r).extrude(height)

    # 2. 切除内部空腔，保留底部厚度
    cavity = cq.Workplane("XY", origin=(0, 0, base_th)).circle(inner_r).extrude(height - base_th)
    body = body.cut(cavity)

    # 3. 创建垂直隔板并合并
    divider = cq.Workplane("XY", origin=(0, 0, base_th)).box(div_th, inner_r * 2, div_h)
    body = body.union(divider)

    # 4. 隔板与内壁交接处倒角 (缓解应力集中)
    body = body.edges("|Z").fillet(conn_fillet)

    # 5. 顶部外缘倒角 (防割手/提升触感)
    body = body.edges(">Z").fillet(top_fillet)

    return body