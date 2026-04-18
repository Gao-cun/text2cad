import cadquery as cq

def build_model():
    L, W = 120.0, 100.0
    base_h = 10.0
    back_w = 80.0
    back_y = (W - back_w) / 2.0

    # 1. 主体轮廓 (XZ平面)
    profile = cq.Workplane("XZ").moveTo(0, 0) \
        .lineTo(L, 0) \
        .lineTo(L, base_h) \
        .lineTo(105, base_h) \
        .lineTo(105, 130) \
        .lineTo(101, 130) \
        .lineTo(101, 135) \
        .lineTo(96, 135) \
        .lineTo(96, 130) \
        .lineTo(25, 10) \
        .lineTo(25, 0) \
        .close()

    # 挤出主体并居中Y轴
    model = profile.extrude(back_w).translate((0, back_y, 0))

    # 2. 边缘倒角 (统一处理，避免复杂选择器引发拓扑错误)
    model = model.edges().fillet(2.0)

    # 3. 防滑凸点阵列 (修正斜面角度以精确贴合背部)
    slope_angle = 59.4
    slope_wp = cq.Workplane("XZ").transformed(rotate=(0, slope_angle, 0))
    pts = [(x, y) for x in range(35, 90, 12) for y in range(15, 65, 12)]
    bumps = slope_wp.pushPoints(pts).circle(1.5).extrude(1.0)
    model = model.union(bumps)

    # 4. 清理几何体 (移除不存在的 .heal() 方法)
    model = model.clean()
    return model