import cadquery as cq

def build_model():
    # 核心参数 (mm)
    base_L, base_W, base_H = 120.0, 100.0, 10.0
    backrest_H = 120.0
    tray_start_x = 40.0
    tray_end_x = -20.0
    tray_start_z = 10.0
    tray_end_z = 18.0
    lip_h = 12.0
    lip_thick = 4.0
    side_lip_h = 10.0
    side_lip_thick = 4.0

    # 1. 主体轮廓 (XZ平面) -> 移除导致崩溃的2D fillet，改为3D实体后处理
    profile = cq.Workplane("XZ")
    (profile.moveTo(-60, 0)
            .lineTo(60, 0)
            .lineTo(60, base_H)
            .lineTo(tray_start_x, base_H)
            .lineTo(tray_start_x, tray_start_z + 2)
            .lineTo(tray_end_x, tray_end_z)
            .lineTo(tray_end_x, tray_end_z + 5)
            .lineTo(-40, tray_end_z + 5)
            .lineTo(-40, base_H + backrest_H)
            .lineTo(-60, base_H + backrest_H)
            .lineTo(-60, base_H)
            .close())

    main_body = profile.extrude(base_W, both=True)

    # 2. 前挡边 (防手机前滑)
    front_lip = cq.Workplane("XY").box(lip_thick, base_W - 10, lip_h)
    front_lip = front_lip.translate((tray_start_x - lip_thick/2 + 0.5, 0, tray_start_z + lip_h/2))

    # 3. 后挡边 (防手机后仰滑落)
    back_lip = cq.Workplane("XY").box(lip_thick, base_W - 10, lip_h + 4)
    back_lip = back_lip.translate((tray_end_x + lip_thick/2 - 0.5, 0, tray_end_z + (lip_h + 4)/2))

    # 4. 侧挡边 (防左右滑动)
    side_lip = cq.Workplane("XY").box(tray_start_x - tray_end_x + 1, side_lip_thick, side_lip_h)
    left_lip = side_lip.translate(((tray_start_x + tray_end_x)/2, -base_W/2 - side_lip_thick/2 + 0.5, (tray_start_z + tray_end_z)/2))
    right_lip = side_lip.translate(((tray_start_x + tray_end_x)/2, base_W/2 + side_lip_thick/2 - 0.5, (tray_start_z + tray_end_z)/2))

    # 5. 布尔合并 (确保重叠 > 0.1mm，生成单一闭合实体)
    model = main_body.union(front_lip).union(back_lip).union(left_lip).union(right_lip)

    # 6. 3D 边缘倒角 (防割手 & 视觉优化)
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(1.5)

    model = model.clean()
    return model