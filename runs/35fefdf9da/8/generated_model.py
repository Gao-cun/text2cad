import cadquery as cq
import math

def build_model():
    base_len, base_wid, base_thk = 80.0, 60.0, 4.0
    sup_thk = 5.0
    angle_deg = 60.0
    slot_w, slot_d = 12.0, 3.0
    fillet_r = 3.0
    chamfer_r = 1.5

    rad = math.radians(angle_deg)
    sup_h = 110.0
    sup_len = sup_h / math.sin(rad)
    dx = sup_len * math.cos(rad)

    ux = math.cos(math.radians(90 - angle_deg))
    uz = math.sin(math.radians(90 - angle_deg))

    pts = [
        (0, 0),
        (base_len, 0),
        (base_len, base_thk),
        (0, base_thk),
        (-dx, base_thk + sup_h),
        (-dx + sup_thk * ux, base_thk + sup_h + sup_thk * uz),
        (sup_thk * ux, base_thk + sup_thk * uz)
    ]

    solid = (cq.Workplane("XZ")
        .polyline(pts)
        .close()
        .extrude(base_wid)
        .translate((0, -base_wid/2, 0)))

    groove = (cq.Workplane("XZ")
        .box(sup_thk + 2, slot_w, slot_d, centered=(True, True, False))
        .rotate((0, 0, 0), (0, 1, 0), -angle_deg)
        .translate((-dx, 0, base_thk + sup_h)))

    # 修复：移除无效的 .heal() 调用，.clean() 已足够清理内部拓扑并保证流形
    solid = solid.cut(groove).clean()

    root_sel = cq.selectors.BoxSelector((-1.0, -base_wid/2, base_thk-0.5), (1.0, base_wid/2, base_thk+0.5))
    solid = solid.edges(root_sel).fillet(fillet_r)

    top_z = base_thk + sup_h
    top_sel = cq.selectors.BoxSelector((-base_len, -base_wid/2, top_z-0.5), (base_len, base_wid/2, top_z+0.5))
    solid = solid.edges(top_sel).chamfer(chamfer_r)

    base_front_sel = cq.selectors.BoxSelector((base_len-0.5, -base_wid/2, -0.5), (base_len+0.5, base_wid/2, 0.5))
    solid = solid.edges(base_front_sel).chamfer(chamfer_r)

    return solid

model = build_model()