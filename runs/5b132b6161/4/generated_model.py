import cadquery as cq

def build_model():
    # 1. 主体轮廓 (XZ平面): 底座 + 连续斜面背板
    # 底座: X[0,120], Z[0,10]
    # 背板: 从(30,10)斜向上至(0,120)，倾角约75°，满足FDM免支撑
    prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(120, 0)
        .lineTo(120, 10)
        .lineTo(30, 10)
        .lineTo(0, 120)
        .close()
    )
    # 拉伸宽度90mm，居中于Y=0
    main = prof.extrude(90).translate((0, -45, 0))

    # 2. 两侧垂直限位挡边 (Side Walls)
    # 贴合主体两侧，形成U型托槽，适配70-80mm手机
    side_l = cq.Workplane("XY").box(100, 4, 100, centered=(False, False, False)).translate((10, -47, 10))
    side_r = cq.Workplane("XY").box(100, 4, 100, centered=(False, False, False)).translate((10, 43, 10))
    model = main.union(side_l).union(side_r)

    # 3. 底部手机限位挡边 (Bottom Lip)
    # 防止手机下滑，与底座前缘融合(微降0.1mm确保布尔体积重叠)
    lip = cq.Workplane("XY").box(10, 85, 5, centered=(False, True, False)).translate((110, 0, 9.9))
    model = model.union(lip)

    # 4. 背部防滑凸条 (Anti-slip Ridges)
    # 在背部垂直面(X=0)添加3条横向凸条，增强摩擦
    for z in [40, 75, 110]:
        ridge = cq.Workplane("YZ").box(2, 80, 2, centered=(False, True, False)).translate((-1, 0, z))
        model = model.union(ridge)

    # 5. 几何修复与流形检查
    model = model.clean()

    # 6. 边缘倒角 (Fillet)
    # 统一对外部可见边进行R=2.0倒角，消除应力集中与锐边
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.0)
    model = model.edges(">X").fillet(2.0)
    model = model.edges("<X").fillet(2.0)
    model = model.edges(">Y").fillet(2.0)
    model = model.edges("<Y").fillet(2.0)

    return model