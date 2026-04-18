import cadquery as cq

def build_model():
    # 核心设计参数 (单位: mm)
    L, W, H = 120.0, 100.0, 130.0
    base_h = 10.0

    # 1. 主体轮廓 (XZ平面) - 保持原拓扑
    main_body = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, base_h)
        .lineTo(0, H)
        .lineTo(0, 0)
        .close()
        .extrude(W)
    )

    # 2. 底部限位挡边 (防手机滑落)
    lip_d, lip_h, lip_w = 6.0, 8.0, 80.0
    lip_y_start = (W - lip_w) / 2
    # 修正Y轴定位使其贴合前表面(Y=0)
    lip = cq.Workplane("XZ").box(lip_d, lip_h, lip_w).translate((lip_d/2, lip_w/2, lip_y_start + lip_w/2))
    model = main_body.union(lip)

    # 3. 防滑凸点阵列 (使用 pushPoints 替代循环 union，修复 TypeError)
    points = [(y, z) for z in range(30, 110, 15) for y in range(20, 80, 15)]
    bumps = cq.Workplane("YZ").pushPoints(points).circle(1.0).extrude(-1.0)
    model = model.union(bumps)

    # 4. 边缘倒角处理 (R=2.0mm)
    model = model.edges("|Y").fillet(2.0)

    # 5. 几何清理
    model = model.clean()
    return model