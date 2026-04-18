import cadquery as cq
import math

def build_model():
    # 核心参数 (mm)
    L, W, H = 120.0, 100.0, 130.0
    base_h = 10.0
    tray_x_front = 25.0
    tray_x_back = 10.0
    lip_h = 12.0
    col_h = 65.0
    tilt_deg = 10.0
    backrest_len = 55.0
    backrest_thick = 15.0

    # 计算背板顶部坐标
    dx = backrest_len * math.sin(math.radians(tilt_deg))
    dz = backrest_len * math.cos(math.radians(tilt_deg))
    top_x = tray_x_back - dx
    top_z = base_h + col_h + dz

    # 1. 主体侧轮廓 (XZ平面)
    profile = (
        cq.Workplane("XZ")
        .moveTo(-L/2, 0)
        .lineTo(L/2, 0)
        .lineTo(L/2, base_h)
        .lineTo(tray_x_front, base_h)
        .lineTo(tray_x_front, base_h + lip_h)
        .lineTo(tray_x_back, base_h + lip_h)
        .lineTo(tray_x_back, base_h)
        .lineTo(tray_x_back, base_h + col_h)
        .lineTo(top_x, top_z)
        .lineTo(top_x - backrest_thick, top_z)
        .lineTo(tray_x_back + backrest_thick, base_h + col_h)
        .lineTo(tray_x_back + backrest_thick, base_h)
        .lineTo(-L/2, base_h)
        .close()
    )

    # 2. 拉伸主体
    main_body = profile.extrude(W).translate((0, -W/2, 0))

    # 3. 安全倒角处理 (在布尔运算前执行，确保每条边仅邻接2个面，彻底解决OCC崩溃)
    # 顶部水平边缘 R=2.0
    main_body = main_body.edges(">Z").fillet(2.0)
    # 底部水平边缘 R=1.5 (保证打印床附着)
    main_body = main_body.edges("<Z").fillet(1.5)

    # 4. 侧挡边 (防止手机左右滑动)
    side_lip = cq.Workplane("XY").box(tray_x_front - tray_x_back, 10.0, lip_h)
    left_lip = side_lip.translate((tray_x_back, -W/2 - 5.0, base_h + lip_h/2))
    right_lip = side_lip.translate((tray_x_back, W/2 + 5.0, base_h + lip_h/2))

    # 合并实体
    model = main_body.union(left_lip).union(right_lip)

    return model