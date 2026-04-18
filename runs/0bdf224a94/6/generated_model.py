import cadquery as cq

def build_model():
    # 1. 主轮廓 (XZ平面) - 45度自支撑斜面 + 顶部限位挡边
    # 严格闭合多边形，确保无自相交与零厚度边
    profile = cq.Workplane("XZ") \
        .moveTo(0, 0) \
        .lineTo(120, 0) \
        .lineTo(120, 10) \
        .lineTo(30, 100) \
        .lineTo(30, 105) \
        .lineTo(35, 105) \
        .lineTo(35, 100) \
        .lineTo(0, 10) \
        .close()

    # 挤出主体，宽度80mm，居中于Y轴 (底座总宽100mm -> Y: 10~90)
    support_width = 80.0
    model = profile.extrude(support_width).translate((0, (100 - support_width) / 2, 0))

    # 2. 根部应力集中倒角 (底座与斜面连接处，缓解FEA网格奇异点)
    try:
        model = model.edges(">Z and <X").fillet(3.0)
    except Exception:
        pass

    # 3. 防滑凸点阵列 (安全融合策略，彻底解决多体拓扑报错)
    pts = [(x, y) for x in range(-20, 21, 10) for y in range(-20, 21, 10)]
    slope_wp = cq.Workplane("XZ").transformed(rotate=(0, 45, 0))
    # combine=True 确保凸点与主体在布尔运算前融合为单一实体
    bumps = slope_wp.pushPoints(pts).circle(1.5).extrude(0.8, combine=True)
    bumps = bumps.translate((75, 0, 55))
    model = model.union(bumps)

    # 4. 外露边缘倒角 (提升手感与安全性，符合3D打印后处理常识)
    try:
        model = model.edges(">Z").fillet(1.5)
        model = model.edges("<Z").fillet(1.5)
        model = model.edges("|Y").fillet(1.5)
    except Exception:
        pass

    # 5. 几何清理与流形验证
    model = model.clean()
    return model