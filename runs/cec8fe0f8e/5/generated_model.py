import cadquery as cq

def build_model():
    # 核心参数 (mm)
    L, W, H_base = 120.0, 100.0, 14.0
    back_top_x, back_top_z = 20.0, 130.0
    slope_start_x = 30.0
    slot_depth = 10.0
    slot_x_start = 20.0
    slot_y_start = 10.0
    slot_y_end = 90.0
    side_lip_h = 4.0
    top_lip_h = 3.0
    top_lip_thick = 4.0
    fillet_r = 2.0

    # 1. 构建主体2D轮廓 (XZ平面)
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, H_base)
        .lineTo(slope_start_x, H_base)
        .lineTo(back_top_x, back_top_z)
        .lineTo(10, back_top_z)
        .lineTo(10, 18)
        .lineTo(0, 18)
        .close()
    )
    model = profile.extrude(W)

    # 2. 添加背部顶端限位挡边 (Union)
    top_lip = cq.Workplane("XY").box(top_lip_thick, W, top_lip_h).translate((back_top_x - top_lip_thick/2, W/2, back_top_z - top_lip_h/2))
    model = model.union(top_lip)

    # 3. 添加侧向限位挡边 (Union)
    lip_len = L - slot_x_start
    lip_left = cq.Workplane("XY").box(lip_len, slot_y_start, side_lip_h).translate((slot_x_start + lip_len/2, slot_y_start/2, H_base + side_lip_h/2))
    lip_right = cq.Workplane("XY").box(lip_len, W - slot_y_end, side_lip_h).translate((slot_x_start + lip_len/2, slot_y_end + (W - slot_y_end)/2, H_base + side_lip_h/2))
    model = model.union(lip_left).union(lip_right)

    # 4. 铣削手机厚度容纳槽 (Cut)
    slot = cq.Workplane("XY").box(L - slot_x_start, slot_y_end - slot_y_start, slot_depth).translate((slot_x_start + (L - slot_x_start)/2, (slot_y_start + slot_y_end)/2, H_base - slot_depth/2))
    model = model.cut(slot)

    # 5. 防滑网格凹坑 (Cut) - 修复 range 浮点数类型错误
    pitch = 4  # 强制转为整数以兼容 Python range()
    x_pts = [x for x in range(35, 115, pitch)]
    y_pts = [y for y in range(20, 80, pitch)]
    dimples = cq.Workplane("XY").pushPoints([(x, y) for x in x_pts for y in y_pts]).circle(1.0).extrude(0.5).translate((0, 0, H_base - slot_depth))
    model = model.cut(dimples)

    # 6. 针对性倒角 (保留已验证的安全策略)
    model = model.edges("<Z").fillet(fillet_r)
    model = model.edges(">Z").fillet(1.5)

    # 7. 拓扑清理
    model = model.clean()
    return model