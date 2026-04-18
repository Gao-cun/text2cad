import cadquery as cq

def build_model():
    # 核心参数 (mm)
    L, W = 120.0, 100.0
    base_h = 14.0
    back_top_x = 20.0
    back_top_z = 130.0
    slope_start_x = 30.0
    slot_depth = 10.0
    slot_x_start = 20.0
    slot_x_len = 100.0
    slot_y_start = 10.0
    slot_y_len = 80.0
    side_lip_h = 4.0
    side_lip_thick = 4.0
    top_lip_h = 3.0
    top_lip_thick = 2.0
    fillet_r = 2.0

    # 1. 主体轮廓 (XZ平面) - 底座与背部斜面一体化
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, base_h)
        .lineTo(slope_start_x, base_h)
        .lineTo(back_top_x, back_top_z)
        .lineTo(back_top_x - 2, back_top_z)
        .lineTo(back_top_x - 2, 18)
        .lineTo(0, 18)
        .close()
    )
    model = profile.extrude(W)

    # 2. 背部顶端限位挡边 (Union)
    top_lip = cq.Workplane("XY").box(top_lip_thick, W, top_lip_h)
    top_lip = top_lip.translate((back_top_x - top_lip_thick/2, W/2, back_top_z - top_lip_h/2 + 0.05))
    model = model.union(top_lip)

    # 3. 侧向限位挡边 (Union)
    lip_left = cq.Workplane("XY").box(slot_x_len, side_lip_thick, side_lip_h)
    lip_left = lip_left.translate((slot_x_start + slot_x_len/2, side_lip_thick/2, base_h + side_lip_h/2 - 0.05))
    lip_right = cq.Workplane("XY").box(slot_x_len, side_lip_thick, side_lip_h)
    lip_right = lip_right.translate((slot_x_start + slot_x_len/2, W - side_lip_thick/2, base_h + side_lip_h/2 - 0.05))
    model = model.union(lip_left).union(lip_right)

    # 4. 手机厚度容纳槽 (Cut)
    slot = cq.Workplane("XY").box(slot_x_len, slot_y_len, slot_depth)
    slot = slot.translate((slot_x_start + slot_x_len/2, slot_y_start + slot_y_len/2, base_h - slot_depth/2))
    model = model.cut(slot)

    # 5. 防滑凹坑阵列 (Cut) - 修复 pitch 为整数以兼容 range()
    pitch = 4
    x_pts = [x for x in range(25, 115, pitch)]
    y_pts = [y for y in range(15, 85, pitch)]
    dimples = cq.Workplane("XY").pushPoints([(x, y) for x in x_pts for y in y_pts]).circle(1.0).extrude(0.5)
    dimples = dimples.translate((0, 0, base_h - 0.25))
    model = model.cut(dimples)

    # 6. 倒角处理 (Fillet)
    model = model.edges("<Z").fillet(fillet_r)
    model = model.edges(">Z").fillet(1.5)
    model = model.edges("|Z").fillet(1.0)

    # 7. 拓扑清理与流形保证
    model = model.clean()
    return model