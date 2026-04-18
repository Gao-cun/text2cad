import cadquery as cq

def build_model():
    # 核心参数 (mm)
    L, W, H_base = 120.0, 100.0, 14.0
    stand_h = 130.0  # 匹配目标高度
    slope_start_x, slope_end_x = 30.0, 90.0
    lip_h = 15.0
    front_lip_h = 18.0
    fillet_r = 2.0

    # 1. 构建2D轮廓 (XZ平面)
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, H_base)
        .lineTo(slope_end_x, H_base)
        .lineTo(slope_start_x, stand_h)
        .lineTo(slope_start_x - 10, stand_h)
        .lineTo(slope_start_x - 10, stand_h - lip_h)
        .lineTo(slope_start_x, stand_h - lip_h)
        .lineTo(10, H_base)
        .lineTo(10, front_lip_h)
        .lineTo(0, front_lip_h)
        .close()
    )

    # 2. 拉伸主体
    model = profile.extrude(W)

    # 3. 侧向限位挡边 (Union)
    stop_w, stop_h = 5.0, 15.0
    stop1 = cq.Workplane("XY").box(70, stop_w, stop_h).translate((25, stop_w/2, H_base + stop_h/2))
    stop2 = cq.Workplane("XY").box(70, stop_w, stop_h).translate((25, W - stop_w/2, H_base + stop_h/2))
    model = model.union(stop1).union(stop2)

    # 4. 防滑纹理 (Cut)
    grip_points = [(x, y) for x in range(30, 90, 8) for y in range(20, 80, 8)]
    grip_cuts = cq.Workplane("XY").pushPoints(grip_points).circle(1.5).extrude(1.0).translate((0, 0, H_base))
    model = model.cut(grip_cuts)

    # 5. 拓扑清理与倒角 - 修复原代码 .not() 非法语法
    model = model.clean()
    # 使用标准选择器替代非法的 .not() 方法调用，分组处理避免底层布尔运算冲突
    model = model.edges("|Z").fillet(fillet_r)
    model = model.edges("#Z").fillet(fillet_r)

    # 6. 最终清理
    model = model.clean()
    return model