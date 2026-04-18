import cadquery as cq

def build_model():
    # 核心尺寸参数 (mm)
    L, W, H = 120.0, 100.0, 130.0
    base_h = 10.0
    back_thick = 8.0
    rib_thick = 6.0
    rib_h = 60.0
    stop_h = 8.0
    stop_thick = 3.0
    guide_h = 6.0
    guide_w = 4.0
    guide_inner_half = 35.0

    # 1. 底座
    base = cq.Workplane("XY").box(L, W, base_h)

    # 2. 背板 (斜面支撑)
    x_bottom = -20.0
    x_top = -40.0
    back_prof = (
        cq.Workplane("XZ")
        .moveTo(x_bottom, base_h)
        .lineTo(x_top, H)
        .lineTo(x_top - back_thick, H)
        .lineTo(x_bottom - back_thick, base_h)
        .close()
    )
    back_plate = back_prof.extrude(W, both=True)

    # 3. 三角加强筋
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(x_bottom, base_h)
        .lineTo(x_bottom, base_h + rib_h)
        .lineTo(x_bottom - rib_h, base_h)
        .close()
    )
    rib = rib_prof.extrude(rib_thick, both=True)

    # 4. 顶部限位挡边
    stop_prof = (
        cq.Workplane("XZ")
        .moveTo(x_top, H)
        .lineTo(x_top + stop_thick, H)
        .lineTo(x_top + stop_thick, H + stop_h)
        .lineTo(x_top, H + stop_h)
        .close()
    )
    stop = stop_prof.extrude(W * 0.8, both=True)

    # 5. 前端侧挡边
    guide_x = 35.0
    guide1 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((guide_x, guide_inner_half, base_h + guide_h/2))
    guide2 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((guide_x, -guide_inner_half, base_h + guide_h/2))

    # 合并主体
    model = base.union(back_plate).union(rib).union(stop).union(guide1).union(guide2)

    # 6. 防滑凹槽 (简化为3条平行直槽，避免复杂阵列导致的拓扑错误)
    groove_depth = 1.5
    groove_w = 2.0
    groove_len = W * 0.7
    groove_cut = (
        cq.Workplane("XZ")
        .moveTo(x_bottom - 0.5, -15).rect(groove_w, groove_depth)
        .moveTo(x_bottom - 0.5, 0).rect(groove_w, groove_depth)
        .moveTo(x_bottom - 0.5, 15).rect(groove_w, groove_depth)
        .extrude(groove_len, both=True)
    )
    model = model.cut(groove_cut)

    # 7. 倒角处理 (移除导致崩溃的 |Z 选择器，仅保留水平边缘倒角以保证流形稳定)
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.0)

    # 清理拓扑
    model = model.clean()
    return model