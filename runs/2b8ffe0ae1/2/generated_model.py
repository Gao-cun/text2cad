import cadquery as cq
import math

def build_model():
    # 核心参数 (mm)
    L, W, H_base = 90.0, 80.0, 10.0
    H_back = 105.0
    tilt_deg = 15.0
    thick_back = 12.0
    Z_phone = 15.0
    front_lip_len = 10.0
    side_lip_w = 2.0
    side_lip_h = 5.0
    inner_gap = 70.0
    fillet_r = 2.5
    foot_r = 3.0
    foot_h = 1.5

    # 1. 主体轮廓 (XZ平面绘制，沿Y轴拉伸)
    dx = (H_back - Z_phone) * math.tan(math.radians(tilt_deg))
    x_back_start = 15.0
    x_back_top = x_back_start + dx
    x_front_lip = L - front_lip_len

    profile_pts = [
        (0, 0), (L, 0), (L, H_base),
        (x_front_lip, H_base), (x_front_lip, Z_phone),
        (x_back_start, Z_phone), (x_back_top, H_back),
        (x_back_top + thick_back, H_back),
        (x_back_top + thick_back, H_base),
        (0, H_base), (0, 0)
    ]

    main = (
        cq.Workplane('XZ')
        .polyline(profile_pts)
        .close()
        .extrude(W)
    )

    # 2. 侧边挡边 (Y方向限位，适配65-80mm手机宽度)
    lip_len = x_front_lip - x_back_start
    lip_y1 = (W - inner_gap) / 2
    lip_y2 = W - lip_y1 - side_lip_w
    lip_x = x_back_start + lip_len / 2

    side_lip = cq.Workplane('XY').workplane(offset=Z_phone - 0.05).box(lip_len, side_lip_w, side_lip_h)
    lip1 = side_lip.translate((lip_x - L/2, lip_y1, 0))
    lip2 = side_lip.translate((lip_x - L/2, lip_y2, 0))

    # 3. 底部防滑脚垫 (4个圆柱凸台)
    foot = cq.Workplane('XY').circle(foot_r).extrude(foot_h)
    feet = cq.Workplane('XY')
    for fx, fy in [(15, 15), (15, W-15), (L-15, 15), (L-15, W-15)]:
        feet = feet.union(foot.translate((fx, fy, -foot_h + 0.05)))

    # 4. 布尔合并 (确保单一实体)
    model = main.union(lip1).union(lip2).union(feet)

    # 5. 倒角处理 (避开底面接触区，半径>=2.0mm满足应力与打印要求)
    model = model.edges().notSelector('<Z').fillet(fillet_r)

    return model