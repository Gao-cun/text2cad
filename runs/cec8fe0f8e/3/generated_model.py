import cadquery as cq

def build_model():
    # 核心参数 (mm)
    base_len, base_wid, base_h = 120.0, 100.0, 12.0
    slot_depth = 10.0
    slope_start_x, slope_end_x = 70.0, 100.0
    stand_h = 110.0
    top_lip_h, top_lip_w = 3.0, 5.0
    front_lip_h = 2.0
    fillet_r = 2.0

    # 1. 侧视轮廓 (XZ平面) - 一体化主体
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(base_len, 0)
        .lineTo(base_len, base_h)
        .lineTo(slope_end_x, base_h)
        .lineTo(slope_end_x, stand_h)
        .lineTo(slope_end_x - top_lip_w, stand_h)
        .lineTo(slope_end_x - top_lip_w, stand_h + top_lip_h)
        .lineTo(slope_end_x - top_lip_w - 2, stand_h + top_lip_h)
        .lineTo(slope_end_x - top_lip_w - 2, stand_h)
        .lineTo(slope_start_x, base_h)
        .lineTo(10, base_h)
        .lineTo(10, base_h + front_lip_h)
        .lineTo(0, base_h + front_lip_h)
        .close()
    )

    # 2. 沿Y轴拉伸
    model = profile.extrude(base_wid)

    # 3. 手机厚度容纳槽 (Cut) - 预留10mm深度，底部保留2mm壁厚
    slot_cut = cq.Workplane("XY").box(80.0, 80.0, slot_depth).translate((50.0, 50.0, base_h - slot_depth/2))
    model = model.cut(slot_cut)

    # 4. 侧向限位挡边 (Union)
    stop_h, stop_w, stop_len = 15.0, 5.0, 80.0
    stop1 = cq.Workplane("XY").box(stop_len, stop_w, stop_h).translate((50.0, 5.0 + stop_w/2, base_h + stop_h/2))
    stop2 = cq.Workplane("XY").box(stop_len, stop_w, stop_h).translate((50.0, 95.0 - stop_w/2, base_h + stop_h/2))
    model = model.union(stop1).union(stop2)

    # 5. 防滑凹坑阵列 (Cut) - 使用切割替代独立凸点，彻底解决多实体/非流形问题
    grip_points = [(x, y) for x in range(22, 88, 6) for y in range(22, 88, 6)]
    grip_cuts = cq.Workplane("XY").pushPoints(grip_points).circle(1.5).extrude(0.5).translate((0, 0, 2))
    model = model.cut(grip_cuts)

    # 6. 边缘倒角 (Fillet) - 提升手感与打印成功率
    model = model.edges().fillet(fillet_r)

    # 7. 拓扑清理，确保单一闭合实体
    model = model.clean()
    return model