import cadquery as cq
import math

def build_model():
    # 核心参数
    base_w, base_d, base_h = 90.0, 80.0, 5.0
    plate_w = 70.0
    plate_h = 105.0
    plate_thick = 15.0
    tilt_deg = 20.0
    tilt_rad = math.radians(tilt_deg)
    run = plate_h * math.tan(tilt_rad)

    # 坐标计算
    y_front_bot = -38.0
    y_back_bot = y_front_bot + plate_thick
    y_back_top = y_back_bot + run
    y_front_top = y_front_bot + run
    z_top = base_h + plate_h

    # 1. 主体轮廓 (YZ平面)
    profile = cq.Workplane("YZ") \
        .moveTo(-base_d/2, 0) \
        .lineTo(base_d/2, 0) \
        .lineTo(base_d/2, base_h) \
        .lineTo(y_back_bot, base_h) \
        .lineTo(y_back_top, z_top) \
        .lineTo(y_front_top, z_top) \
        .lineTo(y_front_bot, base_h) \
        .lineTo(-base_d/2, base_h) \
        .close()

    main_body = profile.extrude(plate_w, both=True)

    # 2. 前挡边
    lip_w, lip_d, lip_h = 65.0, 5.0, 5.0
    lip = cq.Workplane("XY").box(lip_w, lip_d, lip_h)
    lip = lip.translate((0, y_front_top - lip_d/2, z_top + lip_h/2))

    # 3. 安全倒角/圆角处理 (移除导致崩溃的 chamfer，改用稳健的 fillet)
    # 一次性选择底部、顶部及两侧垂直边缘，避免分步修改引发的拓扑冲突
    main_body = main_body.edges("<Z or >Z or >X or <X").fillet(2.0)

    lip = lip.edges(">Z").fillet(1.5)
    lip = lip.edges("<Y").fillet(1.5)

    # 4. 最终合并
    model = main_body.union(lip)
    return model