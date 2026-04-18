import cadquery as cq
import math

def build_model():
    # 核心尺寸参数 (mm)
    L, W, H = 120.0, 100.0, 130.0
    base_h = 10.0
    back_thick = 8.0
    rib_thick = 5.0
    rib_h = 50.0
    stop_h = 8.0
    stop_thick = 3.0
    guide_h = 6.0
    guide_w = 4.0
    guide_inner = 75.0

    # 1. 底座
    base = cq.Workplane("XY").box(L, W, base_h)
    base = base.edges(">Z").fillet(2.0)  # 底座顶部边缘倒角

    # 2. 背板 (斜面)
    back_prof = (
        cq.Workplane("XZ")
        .moveTo(85, base_h)
        .lineTo(15, H)
        .lineTo(15 - back_thick, H)
        .lineTo(85 - back_thick, base_h)
        .close()
    )
    back_plate = back_prof.extrude(W, both=True)
    # 对背板底部边缘倒角，消除悬臂根部应力集中
    back_plate = back_plate.edges("<Z").fillet(5.0)
    model = base.union(back_plate)

    # 3. 三角加强筋
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(85, base_h)
        .lineTo(85, base_h + rib_h)
        .lineTo(85 - rib_h, base_h)
        .close()
    )
    rib = rib_prof.extrude(rib_thick, both=True)
    model = model.union(rib)

    # 4. 顶部限位挡边
    stop_prof = (
        cq.Workplane("XZ")
        .moveTo(15, H)
        .lineTo(15 + stop_thick, H)
        .lineTo(15 + stop_thick, H + stop_h)
        .lineTo(15, H + stop_h)
        .close()
    )
    stop = stop_prof.extrude(back_thick, both=True)
    stop = stop.edges(">Z").fillet(1.5)
    model = model.union(stop)

    # 5. 前端侧挡边
    y_pos = guide_inner / 2
    guide1 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((L - guide_w/2 - 2, y_pos, base_h + guide_h/2))
    guide2 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((L - guide_w/2 - 2, -y_pos, base_h + guide_h/2))
    guides = guide1.union(guide2).edges(">Z").fillet(1.0)
    model = model.union(guides)

    # 6. 防滑纹理 (最后切割，避免干扰倒角拓扑)
    angle = math.degrees(math.atan2(H - base_h, 85 - 15))
    back_wp = cq.Workplane("XZ").transformed(rotate=(0, angle, 0)).center(0, 65)
    groove_solids = back_wp.rarray(2, 3, 25, 8).rect(1.5, 1.5).extrude(0.3)
    model = model.cut(groove_solids)

    return model