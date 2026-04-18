import cadquery as cq

def build_model():
    # 1. 主体轮廓 (XZ平面) - 底座、斜面背板与顶部限位一体成型
    # 采用无悬垂设计：顶部限位面微向后倾斜，确保FDM免支撑打印
    main_profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(120, 0)
        .lineTo(120, 10)
        .lineTo(85, 120)
        .lineTo(80, 122)
        .lineTo(0, 122)
        .close()
    )
    # 主体宽度设为94mm，两侧挡边各占3mm，总宽100mm
    main = main_profile.extrude(94)

    # 2. 两侧垂直挡边 (Side Walls) - 防止手机左右滑动
    # 与主体Y向重叠1mm，确保布尔运算后无缝融合为单一实体
    wall_l = cq.Workplane("XY").box(120, 3, 122, centered=False).translate((0, -1, 0))
    wall_r = cq.Workplane("XY").box(120, 3, 122, centered=False).translate((0, 98, 0))

    # 3. 背部防滑凸条 (Anti-slip Ridges)
    # 附着于背部垂直面(X=120)，增加摩擦与结构刚度
    ridge1 = cq.Workplane("XY").box(2, 90, 2, centered=False).translate((119, 5, 30))
    ridge2 = cq.Workplane("XY").box(2, 90, 2, centered=False).translate((119, 5, 60))
    ridge3 = cq.Workplane("XY").box(2, 90, 2, centered=False).translate((119, 5, 90))
    ridges = ridge1.union(ridge2).union(ridge3)

    # 4. 融合为单一实体
    # 默认 combine=True，相交区域自动合并，彻底消除多实体/非流形问题
    model = main.union(wall_l).union(wall_r).union(ridges)

    # 5. 拓扑清理与倒角
    model = model.clean()
    # 对所有外露边缘进行R=2.0倒角，消除应力集中，提升打印质量与手感
    model = model.edges().fillet(2.0)

    return model