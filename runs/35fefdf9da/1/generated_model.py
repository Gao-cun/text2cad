import cadquery as cq
import math

def build_model():
    # 参数定义
    base_len, base_wid, base_thk = 80.0, 60.0, 4.0
    sup_thk = 3.0
    angle_deg = 60.0
    slot_w, slot_d = 12.0, 5.0
    fillet_r = 3.0

    # 几何计算
    sup_len = 110.0 / math.sin(math.radians(angle_deg))
    dx = sup_len * math.cos(math.radians(angle_deg))
    top_x, top_z = -dx, base_thk + 110.0

    # 支撑板背面偏移向量 (垂直于支撑面，向外)
    nx, nz = math.cos(math.radians(30)), math.sin(math.radians(30))
    p_back_start = (0 + sup_thk * nx, base_thk + sup_thk * nz)
    p_back_end = (top_x + sup_thk * nx, top_z + sup_thk * nz)

    # 构建2D轮廓 (XZ平面)
    profile = (cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(base_len, 0)
        .lineTo(base_len, base_thk)
        .lineTo(0, base_thk)
        .lineTo(top_x, top_z)
        .lineTo(p_back_end[0], p_back_end[1])
        .lineTo(p_back_start[0], p_back_start[1])
        .close())

    # 拉伸为实体
    solid = profile.extrude(base_wid).translate((0, -base_wid / 2, 0))

    # 根部倒角 (仅对平行于Y轴的轮廓边进行倒角，避免影响顶面)
    solid = solid.edges("|Y").fillet(fillet_r)

    # 顶部U型凹槽
    groove = cq.Workplane("XZ").box(sup_thk + 1, slot_w, slot_d, centered=(True, True, False))
    groove = groove.translate((top_x, 0, top_z))
    groove = groove.rotate((top_x, 0, top_z), (0, 1, 0), 30)
    solid = solid.cut(groove)

    # 顶部边缘微倒角防刮手
    solid = solid.edges("|Y and >Z").fillet(1.0)

    return solid

model = build_model()