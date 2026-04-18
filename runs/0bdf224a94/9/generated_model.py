import cadquery as cq

def build_model():
    # 1. 主轮廓 (XZ平面) - 修复上一轮自交/重叠线段导致的OCC内核崩溃
    # 采用简洁的L型+斜面支撑，确保所有线段长度>0且无自交
    profile = cq.Workplane("XZ") \
        .moveTo(0, 0) \
        .lineTo(120, 0) \
        .lineTo(120, 10) \
        .lineTo(80, 10) \
        .lineTo(20, 110) \
        .lineTo(10, 110) \
        .lineTo(10, 120) \
        .lineTo(0, 120) \
        .close()

    width = 100.0
    model = profile.extrude(width)

    # 2. 防滑凸点阵列 (优化布尔运算稳定性)
    # 斜面中心估算，绕Y轴旋转贴合斜面
    slope_center = (50, 0, 60)
    slope_angle = 59.0
    slope_wp = cq.Workplane("XZ").transformed(rotate=(0, slope_angle, 0), offset=slope_center)

    # 生成点阵并严格限制在实体投影范围内
    pts = [(x, y) for x in range(-15, 16, 5) for y in range(-15, 16, 5)]
    pts = [(x, y) for x, y in pts if (x**2 + y**2) < 180]

    bumps = slope_wp.pushPoints(pts).circle(1.0).extrude(0.6)
    model = model.union(bumps)

    # 3. 边缘倒角 (应力集中缓解 & 打印友好)
    # 仅对平行于Y轴的轮廓边及顶底边进行倒角，避免内部拓扑冲突
    model = model.edges("|Y").fillet(2.0)
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.0)

    # 4. 拓扑清理
    model = model.clean()
    return model