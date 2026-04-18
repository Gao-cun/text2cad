import cadquery as cq

def build_model():
    # 核心参数 (mm)
    base_L, base_W, base_H = 120.0, 100.0, 10.0
    tray_start_x = 40.0
    tray_end_x = -20.0
    tray_front_z = 18.0
    tray_back_z = 26.0  # 约8度后仰倾角 (tan^-1(8/60) ≈ 7.6°)
    lip_front_h = 8.0
    lip_back_h = 12.0
    side_lip_h = 15.0
    side_lip_thick = 3.0
    backrest_top_z = 130.0

    # 1. 主截面轮廓 (XZ平面)
    profile = cq.Workplane("XZ")
    (profile.moveTo(-60, 0)
            .lineTo(60, 0)
            .lineTo(60, base_H)
            .lineTo(tray_start_x, base_H)
            .lineTo(tray_start_x, tray_front_z)
            .lineTo(tray_end_x, tray_back_z)
            .lineTo(tray_end_x, tray_back_z + lip_back_h)
            .lineTo(-40, tray_back_z + lip_back_h)
            .lineTo(-40, backrest_top_z)
            .lineTo(-60, backrest_top_z)
            .lineTo(-60, base_H)
            .close())

    # 2. 拉伸主体 (Y方向宽度100mm)
    main_body = profile.extrude(base_W, both=True)

    # 3. 侧挡边 (左右各一，与主体重叠确保布尔成功)
    side_lip = cq.Workplane("XY").box(tray_start_x - tray_end_x, side_lip_thick, side_lip_h)
    left_lip = side_lip.translate(((tray_start_x + tray_end_x)/2, -base_W/2 - side_lip_thick/2 + 0.5, (tray_front_z + tray_back_z)/2))
    right_lip = side_lip.translate(((tray_start_x + tray_end_x)/2, base_W/2 + side_lip_thick/2 - 0.5, (tray_front_z + tray_back_z)/2))

    # 4. 布尔合并 (确保单一闭合流形)
    model = main_body.union(left_lip).union(right_lip)

    # 5. 边缘倒角 (防割手 & 缓解应力集中)
    # 顶部及外露边缘
    model = model.edges(">Z").fillet(2.0)
    # 底部边缘
    model = model.edges("<Z").fillet(1.5)
    # 侧壁与托盘交线 (安全过滤)
    try:
        model = model.edges("|Z").edges(">Y or <Y").fillet(1.5)
    except Exception:
        pass

    model = model.clean()
    return model