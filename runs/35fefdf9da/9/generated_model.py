import cadquery as cq
import math

def build_model():
    base_len, base_wid, base_thk = 80.0, 60.0, 4.0
    sup_h = 110.0
    angle_deg = 60.0
    slot_w, slot_d = 12.0, 5.0
    fillet_r = 3.0
    chamfer_r = 1.5

    # 计算前倾面水平投影长度，确保前表面与底座呈60度夹角
    dx = (sup_h - base_thk) / math.tan(math.radians(angle_deg))
    x_top = base_len - dx

    # 构建XZ截面轮廓
    pts = [
        (0, 0),
        (base_len, 0),
        (base_len, base_thk),
        (x_top, sup_h),
        (0, sup_h)
    ]

    # 拉伸并平移至目标坐标系中心
    solid = (cq.Workplane("XZ")
        .polyline(pts)
        .close()
        .extrude(base_wid)
        .translate((0, -base_wid/2, -sup_h/2)))

    # 顶部U型卡槽 (沿前表面法向切入)
    slot_box = (cq.Workplane("XZ")
        .box(10, slot_w, slot_d, centered=(True, True, False))
        .rotate((0, 0, 0), (0, 1, 0), -30)
        .translate((x_top + 2, 0, sup_h)))

    solid = solid.cut(slot_box).clean()

    # 关键特征修饰
    # 1. 背部根部倒角 (缓解应力集中)
    solid = solid.edges("<Z and <X").fillet(fillet_r)
    # 2. 顶部前缘倒角 (防刮手/引导手机)
    solid = solid.edges(">Z and >X").chamfer(chamfer_r)
    # 3. 底部前缘倒角 (视觉过渡)
    solid = solid.edges("<Z and >X").chamfer(chamfer_r)

    return solid

model = build_model()