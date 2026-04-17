import cadquery as cq
import math

def build_model():
    base_len, base_wid, base_thk = 80.0, 60.0, 4.0
    sup_thk = 3.5
    angle_deg = 60.0
    slot_w, slot_d = 12.0, 5.0
    chamfer_r = 2.0

    rad = math.radians(angle_deg)
    sup_h = 110.0
    sup_len = sup_h / math.sin(rad)
    dx = sup_len * math.cos(rad)
    top_x = -dx
    top_z = base_thk + sup_h

    # 1. 底座 (确保 x=0 处为完整垂直平面以严格匹配固定边界条件)
    base = cq.Workplane("XZ").rect(base_len, base_thk).extrude(base_wid).translate((0, -base_wid/2, 0))

    # 2. 支撑板轮廓 (分步构建避免自相交)
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

    # 3. 布尔合并生成单一水密实体
    solid = base.union(support)

    # 4. 倒角/应力释放 (避开 x=0 背面固定面，改用 chamfer 提升网格质量)
    solid = solid.edges("|Y and not <X").chamfer(chamfer_r)

    # 5. 顶部 U 型卡槽
    groove = (cq.Workplane("XZ")
        .box(sup_thk + 2, slot_w, slot_d, centered=(True, True, False))
        .translate((top_x, 0, top_z))
        .rotate((top_x, 0, top_z), (0, 1, 0), 60))
    solid = solid.cut(groove)

    # 6. 顶部边缘微倒角防刮手
    solid = solid.edges("|Y and >Z").chamfer(1.0)

    return solid

model = build_model()