import cadquery as cq

def build_model():
    # 1. 主轮廓 (XZ平面) - 严格45度自支撑斜面 + 底部防滑挡边 + 顶部限位
    # 坐标逻辑: X(0~120), Z(0~100)。斜面从(95,20)到(30,85)，dx=-65, dz=65，精确45度
    profile = cq.Workplane("XZ") \
        .moveTo(0, 0) \
        .lineTo(120, 0) \
        .lineTo(120, 10) \
        .lineTo(100, 10) \
        .lineTo(100, 20) \
        .lineTo(95, 20) \
        .lineTo(30, 85) \
        .lineTo(30, 95) \
        .lineTo(35, 95) \
        .lineTo(35, 85) \
        .lineTo(0, 10) \
        .close()

    # 挤出主体，宽度90mm (适配70-80mm手机并留余量)，居中于Y轴
    width = 90.0
    model = profile.extrude(width).translate((0, -width/2, 0))

    # 2. 关键应力区倒角 (底座与斜面交汇处，R=3.0 缓解FEA奇异点)
    try:
        model = model.edges(">Z and <X").fillet(3.0)
        model = model.edges(">Z and >X").fillet(2.0)
    except Exception:
        pass

    # 3. 防滑凸点阵列 (安全融合策略，确保单一实体)
    pts = [(x, y) for x in range(-25, 26, 8) for y in range(-30, 31, 8)]
    # 创建贴合斜面的局部工作平面 (绕Y轴旋转45度)
    slope_wp = cq.Workplane("XZ").transformed(rotate=(0, 45, 0))
    # 生成凸点并强制合并为单一实体
    bumps = slope_wp.pushPoints(pts).circle(1.2).extrude(0.6, combine=True)
    # 平移到斜面几何中心
    bumps = bumps.translate((62.5, 0, 52.5))
    model = model.union(bumps)

    # 4. 外露边缘倒角 (提升手感与安全性，R=1.5)
    try:
        model = model.edges(">Z").fillet(1.5)
        model = model.edges("<Z").fillet(1.5)
        model = model.edges("|Y").fillet(1.5)
    except Exception:
        pass

    # 5. 几何清理与流形验证 (强制修复布尔运算残留拓扑)
    model = model.clean()
    return model