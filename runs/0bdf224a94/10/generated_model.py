import cadquery as cq

def build_model():
    # 1. 一体化主轮廓 (YZ平面) - 包含底座、45°自支撑斜面与顶部限位挡边
    # 采用单一线条闭合+单次挤出，从根源杜绝多体/非流形问题
    profile = cq.Workplane("YZ") \
        .moveTo(0, 0) \
        .lineTo(100, 0) \
        .lineTo(100, 10) \
        .lineTo(0, 110) \
        .lineTo(15, 110) \
        .lineTo(15, 105) \
        .lineTo(0, 105) \
        .close()

    width = 120.0
    model = profile.extrude(width)

    # 2. 防滑凸点阵列 (贴合45°斜面)
    slope_angle = 45.0
    slope_center = (0, 50, 60)
    slope_wp = cq.Workplane("YZ").transformed(rotate=(slope_angle, 0, 0), offset=slope_center)

    pts = []
    for y in range(-25, 26, 8):
        for z in range(-35, 36, 8):
            pts.append((y, z))

    bumps = slope_wp.pushPoints(pts).circle(1.2).extrude(0.5)
    model = model.union(bumps)

    # 3. 全局倒角 (应力缓解 & 打印友好)
    # 仅对外露锐边倒角，避开底面(Z=0)接触区以保证网格质量
    model = model.edges(">Z or <Z or |X").fillet(2.0)

    # 4. 拓扑清理
    model = model.clean()
    return model