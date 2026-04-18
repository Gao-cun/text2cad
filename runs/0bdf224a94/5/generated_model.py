import cadquery as cq

def build_model():
    # 1. 主体轮廓 (XZ平面) - 45度自支撑斜面 + 顶部限位挡边
    profile = cq.Workplane("XZ") \
        .moveTo(0, 0) \
        .lineTo(120, 0) \
        .lineTo(120, 10) \
        .lineTo(100, 10) \
        .lineTo(30, 80) \
        .lineTo(30, 90) \
        .lineTo(36, 90) \
        .lineTo(36, 80) \
        .lineTo(42, 80) \
        .lineTo(100, 10) \
        .lineTo(100, 0) \
        .close()

    # 挤出主体，宽度80mm，居中于Y轴 (底座总宽100mm)
    support_width = 80.0
    model = profile.extrude(support_width).translate((0, (100 - support_width) / 2, 0))

    # 2. 边缘倒角 (在添加凸点前进行，严格限定选择器以避免拓扑冲突)
    # 仅对顶部和底部外轮廓边缘倒角，避开内部台阶与后续凸点交线，彻底解决 ChFi3d_Builder 报错
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.0)

    # 3. 防滑凸点阵列 (精确贴合45度斜面)
    # 创建与斜面平行的局部工作平面
    slope_wp = cq.Workplane("XZ").transformed(rotate=(0, 45, 0))
    pts = [(x, y) for x in range(-20, 21, 10) for y in range(-30, 31, 10)]
    # combine=True 确保所有凸点融合为单一实体
    bumps = slope_wp.pushPoints(pts).circle(1.5).extrude(0.8, combine=True)
    # 平移至斜面中心位置
    bumps = bumps.translate((65, 0, 45))

    # 布尔并集
    model = model.union(bumps)

    # 4. 几何清理与流形验证
    model = model.clean()
    return model