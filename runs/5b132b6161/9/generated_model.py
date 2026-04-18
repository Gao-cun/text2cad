import cadquery as cq

def build_model():
    # 1. 底座 (Base) - 提供稳固支撑，尺寸 120x100x10
    base = cq.Workplane("XY").box(120, 100, 10, centered=False)

    # 2. 斜面背板 (Slope Backrest) - 一体化连续延伸，无悬垂
    # 轮廓在YZ平面：从底座后缘(Y=0, Z=10)向前至Y=45，再斜向上至Y=0, Z=120
    slope_profile = (
        cq.Workplane("YZ")
        .moveTo(0, 10)
        .lineTo(45, 10)
        .lineTo(0, 120)
        .close()
    )
    slope = slope_profile.extrude(120)

    # 3. 底部防滑挡唇 (Bottom Lip) - 防止手机向前滑落
    # 与底座及斜面起始处充分重叠，确保布尔融合
    lip = cq.Workplane("XY").box(120, 6, 4, centered=False).translate((0, 42, 10))

    # 4. 两侧限位挡边 (Side Walls) - 约束手机左右位移
    # 位于斜面有效支撑区两侧，厚度3mm，高度25mm
    wall_l = cq.Workplane("XY").box(120, 3, 25, centered=False).translate((0, 12, 10))
    wall_r = cq.Workplane("XY").box(120, 3, 25, centered=False).translate((0, 35, 10))

    # 5. 背部防滑凸条 (Anti-slip Ridges) - 防止手机向后倾倒
    # 附着于背部垂直面(Y=0)，Z向等距分布，与主体一体成型
    ridge1 = cq.Workplane("XZ").box(120, 2, 2, centered=False).translate((0, -1, 100))
    ridge2 = cq.Workplane("XZ").box(120, 2, 2, centered=False).translate((0, -1, 110))
    ridge3 = cq.Workplane("XZ").box(120, 2, 2, centered=False).translate((0, -1, 118))
    ridges = ridge1.union(ridge2).union(ridge3)

    # 6. 拓扑融合与清理
    # 逐步Union并依赖默认combine=True生成单一实体
    model = base.union(slope)
    model = model.union(lip)
    model = model.union(wall_l)
    model = model.union(wall_r)
    model = model.union(ridges)
    model = model.clean()

    # 7. 全局倒角 - 消除应力集中，优化FDM层纹与手感
    # 半径2.0mm满足承重根部强化与打印安全要求
    model = model.edges().fillet(2.0)

    return model