import cadquery as cq

def build_model():
    # 1. 底座 (Base) - 提供稳固支撑，尺寸 120x100x10
    base = cq.Workplane("XY").box(120, 100, 10, centered=False)

    # 2. 斜面支撑主体 (Slope Support) - 在YZ平面绘制轮廓，沿X轴挤出120mm
    # 轮廓起点(0,10)贴合底座后缘，垂直向上至(0,125)，斜向下至(75,15)形成手机靠背
    # 底部自然过渡至底座前部，确保无悬垂结构，FDM免支撑打印
    slope_profile = (
        cq.Workplane("YZ")
        .moveTo(0, 10)
        .lineTo(0, 125)
        .lineTo(75, 15)
        .lineTo(75, 10)
        .lineTo(100, 10)
        .lineTo(100, 0)
        .lineTo(0, 0)
        .close()
    )
    slope = slope_profile.extrude(120)

    # 3. 融合底座与斜面主体
    model = base.union(slope)

    # 4. 两侧垂直挡边 (Side Walls) - 防止手机左右滑动
    # 位于斜面两侧边缘，Y=10 与 Y=72 处，厚度3mm，高度20mm
    wall_l = cq.Workplane("XY").box(120, 3, 20, centered=False).translate((0, 10, 10))
    wall_r = cq.Workplane("XY").box(120, 3, 20, centered=False).translate((0, 72, 10))
    model = model.union(wall_l).union(wall_r)

    # 5. 背部防滑凸条 (Anti-slip Ridges) - 附着于背部垂直面(Y=0)
    # 沿X方向布置，Z=95, 105, 115 处，增加摩擦与顶部限位
    ridge1 = cq.Workplane("XZ").box(120, 1.5, 2, centered=False).translate((0, -1, 95))
    ridge2 = cq.Workplane("XZ").box(120, 1.5, 2, centered=False).translate((0, -1, 105))
    ridge3 = cq.Workplane("XZ").box(120, 1.5, 2, centered=False).translate((0, -1, 115))
    ridges = ridge1.union(ridge2).union(ridge3)
    model = model.union(ridges)

    # 6. 拓扑清理与全局倒角
    model = model.clean()
    # 对所有外露边缘施加 R=2.0 倒角，消除应力集中，优化FDM打印层纹与手感
    model = model.edges().fillet(2.0)

    return model