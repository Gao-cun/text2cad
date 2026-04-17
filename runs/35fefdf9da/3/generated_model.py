import cadquery as cq
import math

def build_model():
    base_len, base_wid, base_thk = 80.0, 60.0, 4.0
    sup_thk = 3.5
    angle_deg = 60.0
    slot_w, slot_d = 12.0, 5.0
    fillet_r = 3.0
    chamfer_r = 2.0

    rad = math.radians(angle_deg)
    sup_h = 110.0
    sup_len = sup_h / math.sin(rad)
    dx = sup_len * math.cos(rad)
    top_x = -dx
    top_z = base_thk + sup_h

    # 1. 底座
    base = cq.Workplane("XZ").rect(base_len, base_thk).extrude(base_wid).translate((0, -base_wid/2, 0))

    # 2. 支撑板轮廓
    nx, nz = math.sin(rad), math.cos(rad)
    p_front_start = (0, base_thk)
    p_front_end = (top_x, top_z)
    p_back_end = (top_x + sup_thk * nx, top_z + sup_thk * nz)
    p_back_start = (sup_thk * nx, base_thk + sup_thk * nz)
    p_drop = (sup_thk * nx, base_thk)

    profile = (cq.Workplane("XZ")
        .moveTo(*p_front_start)
        .lineTo(*p_front_end)
        .lineTo(*p_back_end)
        .lineTo(*p_back_start)
        .lineTo(*p_drop)
        .lineTo(*p_front_start)
        .close())

    support = profile.extrude(base_wid).translate((0, -base_wid/2, 0))

    # 3. 布尔合并
    solid = base.union(support)

    # 4. 根部圆角 (应力释放) - 使用Python过滤避免选择器语法错误
    root_edges = [e for e in solid.edges().vals() if abs(e.Center().x) < 0.5 and base_thk - 0.5 < e.Center().z < base_thk + 0.5]
    if root_edges:
        solid = solid.edges(root_edges).fillet(fillet_r)

    # 5. 侧面边缘倒角 (避开x=0固定面)
    side_edges = [e for e in solid.edges("|Y").vals() if e.Center().x > 0.5]
    if side_edges:
        solid = solid.edges(side_edges).chamfer(chamfer_r)

    # 6. 顶部 U 型卡槽
    groove = (cq.Workplane("XZ")
        .box(sup_thk + 2, slot_w, slot_d, centered=(True, True, False))
        .rotate((0, 0, 0), (0, 1, 0), -angle_deg)
        .translate((top_x, 0, top_z)))
    solid = solid.cut(groove)

    # 7. 顶部边缘微倒角防刮手
    top_edges = [e for e in solid.edges().vals() if e.Center().z > top_z - 0.5]
    if top_edges:
        solid = solid.edges(top_edges).chamfer(1.0)

    return solid

model = build_model()