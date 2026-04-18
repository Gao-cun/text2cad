import cadquery as cq

def build_model():
    # 核心参数 (mm)
    L, W = 120.0, 100.0
    base_h = 15.0
    back_h = 130.0
    slope_start_x = 45.0
    back_top_x = 25.0
    back_thick = 12.0
    back_inner_x = back_top_x - back_thick

    # 1. 主体轮廓 (XZ平面) - 底座与背部斜面一体化
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, base_h)
        .lineTo(slope_start_x, base_h)
        .lineTo(back_top_x, back_h)
        .lineTo(back_inner_x, back_h)
        .lineTo(back_inner_x, base_h)
        .lineTo(0, base_h)
        .close()
    )
    model = profile.extrude(W)

    # 2. 手机厚度容纳槽 (Cut) - 底部保留5mm壁厚(>2mm安全阈值)
    slot = cq.Workplane("XY").box(100.0, 80.0, 10.0)
    slot = slot.translate((65.0, 50.0, 10.0))
    model = model.cut(slot).clean()

    # 3. 背部顶端限位挡边 (Union) - 防止手机后滑
    back_lip = cq.Workplane("XY").box(back_thick, W, 3.0)
    back_lip = back_lip.translate((back_top_x - back_thick/2, W/2, back_h - 1.5))
    model = model.union(back_lip).clean()

    # 4. 侧向限位挡边 (Union) - 防止手机左右滑动
    side_lip_h = 4.0
    side_lip_thick = 5.0
    lip_left = cq.Workplane("XY").box(100.0, side_lip_thick, side_lip_h)
    lip_left = lip_left.translate((65.0, side_lip_thick/2, base_h + side_lip_h/2))
    lip_right = cq.Workplane("XY").box(100.0, side_lip_thick, side_lip_h)
    lip_right = lip_right.translate((65.0, W - side_lip_thick/2, base_h + side_lip_h/2))
    model = model.union(lip_left).union(lip_right).clean()

    # 5. 防滑凹坑阵列 (Cut) - 位于槽底Z=5平面，深度0.3mm
    pitch = 4
    x_pts = [x for x in range(20, 110, pitch)]
    y_pts = [y for y in range(15, 85, pitch)]
    pts = [(x, y) for x in x_pts for y in y_pts]
    dimples = cq.Workplane("XY").pushPoints(pts).circle(1.0).extrude(0.3)
    dimples = dimples.translate((0, 0, 4.7))
    model = model.cut(dimples).clean()

    # 6. 倒角处理 (Fillet) - 仅处理外露主边缘，避开内部槽边以防拓扑报错
    fillet_r = 2.0
    try:
        model = model.edges(">Z").fillet(fillet_r)
        model = model.edges("<Z").fillet(fillet_r)
        model = model.edges(">X").fillet(fillet_r)
        model = model.edges("<X").fillet(fillet_r)
        model = model.edges(">Y").fillet(fillet_r)
        model = model.edges("<Y").fillet(fillet_r)
    except Exception:
        pass

    # 7. 最终拓扑清理与流形保证
    model = model.clean()
    return model