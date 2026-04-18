import cadquery as cq

def build_model():
    # 核心设计参数 (单位: mm)
    L, W, H = 120.0, 100.0, 130.0
    base_h = 10.0
    backrest_x = 20.0
    backrest_thick = 15.0
    backrest_w = 80.0
    backrest_h = 120.0  # 调整至总高130
    rib_len = 75.0
    rib_h = 75.0
    lip_h = 8.0
    lip_x_offset = 10.0

    # 1. 底座
    base = cq.Workplane("XY").box(L, W, base_h, centered=(False, False, False))

    # 2. 背部支撑板
    backrest_y = (W - backrest_w) / 2
    backrest = cq.Workplane("XY").box(
        backrest_thick, backrest_w, backrest_h,
        centered=(False, False, False)
    ).translate((backrest_x, backrest_y, base_h))

    # 3. 三角加强筋 (45度支撑，消除悬垂)
    rib_x_start = backrest_x + backrest_thick
    rib_x_end = rib_x_start + rib_len
    rib_profile = cq.Workplane("XZ").moveTo(rib_x_start, base_h) \
        .lineTo(rib_x_end, base_h) \
        .lineTo(rib_x_start, base_h + rib_h) \
        .close()
    rib = rib_profile.extrude(backrest_w).translate((0, backrest_y, 0))

    # 4. 顶部限位挡边
    lip = cq.Workplane("XY").box(
        backrest_thick + lip_x_offset, backrest_w, lip_h,
        centered=(False, False, False)
    ).translate((backrest_x - lip_x_offset, backrest_y, base_h + backrest_h - lip_h))

    # 5. 组合主体
    model = base.union(backrest).union(rib).union(lip)

    # 6. 防滑凸点阵列
    y_start = int(backrest_y + 10)
    y_end = int(backrest_y + backrest_w - 10)
    z_start = int(base_h + 20)
    z_end = int(base_h + backrest_h - 20)
    y_pts = [y for y in range(y_start, y_end, 12)]
    z_pts = [z for z in range(z_start, z_end, 12)]
    points = [(y, z) for z in z_pts for y in y_pts]
    bumps = cq.Workplane("YZ").workplane(offset=backrest_x) \
        .pushPoints(points).circle(1.5).extrude(-1.0)
    model = model.union(bumps)

    # 7. 安全倒角 (修复原 |Y 选择器导致的 T型交界边报错)
    # 仅对外露的上下水平边和左右垂直边进行倒角，避开底座/背板/加强筋交汇的内部边
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.0)
    model = model.edges(">X").fillet(2.0)
    model = model.edges("<X").fillet(2.0)

    # 8. 几何清理与流形验证
    model = model.clean()
    return model