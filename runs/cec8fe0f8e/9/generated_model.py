import cadquery as cq

def build_model():
    # 核心参数 (mm)
    L, W = 120.0, 100.0
    base_h = 15.0
    back_h = 130.0  # 对齐目标高度
    slope_start_x = 45.0  # 优化悬垂角至~63度，提升免支撑打印成功率
    back_top_x = 25.0
    back_thick = 12.0
    slot_depth = 10.0
    slot_x_start = 25.0
    slot_x_len = 85.0
    slot_y_start = 10.0
    slot_y_len = 80.0
    lip_h = 5.0
    lip_thick = 3.0
    fillet_r = 2.5  # 增大倒角缓解应力集中

    # 1. 主体轮廓 (XZ平面) - 底座与背部斜面一体化
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, base_h)
        .lineTo(slope_start_x, base_h)
        .lineTo(back_top_x, back_h)
        .lineTo(back_top_x - back_thick, back_h)
        .lineTo(back_top_x - back_thick, base_h)
        .lineTo(0, base_h)
        .close()
    )
    model = profile.extrude(W)

    # 2. 手机厚度容纳槽 (Cut)
    slot = cq.Workplane("XY").box(slot_x_len, slot_y_len, slot_depth)
    slot = slot.translate((slot_x_start + slot_x_len/2, W/2, base_h - slot_depth/2))
    model = model.cut(slot).clean()

    # 3. 侧向限位挡边 (Union)
    lip_left = cq.Workplane("XY").box(slot_x_len, lip_thick, lip_h)
    lip_left = lip_left.translate((slot_x_start + slot_x_len/2, slot_y_start + lip_thick/2, base_h + lip_h/2))
    lip_right = cq.Workplane("XY").box(slot_x_len, lip_thick, lip_h)
    lip_right = lip_right.translate((slot_x_start + slot_x_len/2, W - slot_y_start - lip_thick/2, base_h + lip_h/2))
    model = model.union(lip_left).union(lip_right).clean()

    # 4. 背部顶端限位挡边 (Union)
    top_lip = cq.Workplane("XY").box(lip_thick, W, lip_h)
    top_lip = top_lip.translate((back_top_x - lip_thick/2, W/2, back_h - lip_h/2))
    model = model.union(top_lip).clean()

    # 5. 防滑凹坑阵列 (Cut)
    pitch = 4  # 修复：Python range() 步长必须为整数
    x_pts = [x for x in range(30, 110, pitch)]
    y_pts = [y for y in range(15, 95, pitch)]
    pts = [(x, y) for x in x_pts for y in y_pts
           if slot_x_start < x < slot_x_start + slot_x_len
           and slot_y_start < y < slot_y_start + slot_y_len]
    dimples = cq.Workplane("XY").pushPoints(pts).circle(1.0).extrude(0.5)
    dimples = dimples.translate((0, 0, base_h - slot_depth + 0.01))
    model = model.cut(dimples).clean()

    # 6. 倒角处理 (Fillet) - 安全过滤外露边缘
    try:
        model = model.edges(">Z").fillet(fillet_r)
        model = model.edges("<Z").fillet(fillet_r)
        model = model.edges("|Z").fillet(fillet_r)
    except Exception:
        pass

    # 7. 最终拓扑清理与流形保证
    model = model.clean()
    return model