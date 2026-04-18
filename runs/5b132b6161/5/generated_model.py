import cadquery as cq

def build_model():
    # 1. 主体轮廓 (XZ平面): 底座 + 连续斜面背板
    # 底座: X[0,120], Z[0,10]
    # 背板: 从(30,10)斜向上至(0,125)，倾角约76°，满足FDM免支撑
    prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(120, 0)
        .lineTo(120, 10)
        .lineTo(30, 10)
        .lineTo(0, 125)
        .close()
    )
    main = prof.extrude(100)

    # 2. 两侧垂直限位挡边 (Side Walls)
    # 适配70-80mm手机，Y向留空10mm
    wall_l = cq.Workplane("XY").box(120, 10, 125, centered=False)
    wall_r = cq.Workplane("XY").box(120, 10, 125, centered=False).translate((0, 90, 0))

    # 3. 顶部后沿限位挡边 (Top Lip)
    lip = cq.Workplane("XY").box(5, 80, 5, centered=False).translate((0, 10, 120))

    # 4. 背部防滑凸条 (Anti-slip Ridges)
    ridge1 = cq.Workplane("YZ").box(2, 80, 2, centered=False).translate((-1, 10, 40))
    ridge2 = cq.Workplane("YZ").box(2, 80, 2, centered=False).translate((-1, 10, 70))
    ridge3 = cq.Workplane("YZ").box(2, 80, 2, centered=False).translate((-1, 10, 100))
    ridges = ridge1.union(ridge2).union(ridge3)

    # 5. 融合所有部件为单一实体
    model = main.union(wall_l).union(wall_r).union(lip).union(ridges)

    # 6. 拓扑清理 (移除无效的 .heal() 调用)
    model = model.clean()

    # 7. 边缘倒角 (Fillet) - 缓解应力集中，提升手感与打印质量
    # 使用组合选择器一次性处理，避免连续选择器导致的拓扑变更冲突
    model = model.edges(">Z or >X").fillet(2.0)

    return model