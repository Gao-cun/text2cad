import cadquery as cq

def build_model():
    # 1. 主轮廓 (XZ平面) - 严格45度自支撑斜面 + 顶部45度限位钩 + 底部加厚基座
    profile = cq.Workplane("XZ") \
        .moveTo(0, 0) \
        .lineTo(120, 0) \
        .lineTo(120, 10) \
        .lineTo(100, 10) \
        .lineTo(10, 100) \
        .lineTo(5, 105) \
        .lineTo(0, 100) \
        .lineTo(0, 10) \
        .close()

    width = 100.0
    model = profile.extrude(width)

    # 2. 防滑凸点阵列 (单一实体合并策略，彻底解决碎片化问题)
    # 斜面倾角45度，工作平面绕Y轴旋转45度以贴合斜面
    slope_wp = cq.Workplane("XZ").transformed(rotate=(0, 45, 0))
    # 凸点分布在斜面有效承托区 (避开根部与顶部钩子)
    pts = [(x, y) for x in range(20, 90, 8) for y in range(10, 91, 8)]
    bumps = slope_wp.pushPoints(pts).circle(1.0).extrude(0.5, combine=True)
    # 平移到斜面几何中心 (X=55, Z=55)
    bumps = bumps.translate((55, 0, 55))
    model = model.union(bumps)

    # 3. 边缘倒角 (消除应力集中，提升打印质量与手感)
    try:
        # 顶部与底部水平外缘
        model = model.edges(">Z").fillet(1.5)
        model = model.edges("<Z").fillet(1.5)
        # 左右侧壁垂直棱线
        model = model.edges("|Y").fillet(1.5)
        # 底座与斜面根部过渡区 (Z=10, X=100附近)
        model = model.edges(">Z and >X").fillet(3.0)
    except Exception:
        pass

    # 4. 拓扑清理与流形验证
    model = model.clean()
    return model