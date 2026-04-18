import cadquery as cq

def build_model():
    # 1. 主体轮廓 (XZ平面) - 一体化底座与斜面背板
    # 底座: X[0,120], Z[0,10]
    # 背板斜面: 从(70,10)斜向上至(95,125)，倾角约76°，符合人体工学与免支撑打印
    # 顶部与立面闭合形成实体
    prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(120, 0)
        .lineTo(120, 10)
        .lineTo(70, 10)
        .lineTo(95, 125)
        .lineTo(0, 125)
        .close()
    )
    main = prof.extrude(100) # Y: 0 to 100

    # 2. 两侧垂直限位挡边 (Side Walls)
    # 适配70-80mm手机，Y向两侧各留4mm厚度挡边，高度15mm
    wall_l = cq.Workplane("XY").box(95, 4, 15, centered=False).translate((0, 0, 10))
    wall_r = cq.Workplane("XY").box(95, 4, 15, centered=False).translate((0, 96, 10))

    # 3. 顶部后沿限位挡边 (Top Lip)
    # 位于斜面顶端后方，防止手机向后滑落
    lip = cq.Workplane("XY").box(10, 92, 6, centered=False).translate((90, 4, 120))

    # 4. 背部防滑凸条 (Anti-slip Ridges)
    # 附着于背部垂直面/斜面后侧，增加摩擦
    ridge1 = cq.Workplane("YZ").box(2, 80, 2, centered=False).translate((119, 10, 30))
    ridge2 = cq.Workplane("YZ").box(2, 80, 2, centered=False).translate((119, 10, 60))
    ridge3 = cq.Workplane("YZ").box(2, 80, 2, centered=False).translate((119, 10, 90))
    ridges = ridge1.union(ridge2).union(ridge3)

    # 5. 融合为单一实体 (使用glue=True确保流形拓扑，避免非流形报错)
    model = main.union(wall_l, glue=True)
    model = model.union(wall_r, glue=True)
    model = model.union(lip, glue=True)
    model = model.union(ridges, glue=True)

    # 6. 拓扑清理
    model = model.clean()

    # 7. 边缘倒角 (Fillet)
    # 对所有外露边缘进行R=2.0倒角，消除应力集中，提升手感与打印质量
    model = model.edges(">Z or >X").fillet(2.0)

    return model