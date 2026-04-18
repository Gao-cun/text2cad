import cadquery as cq
import math

def build_model():
    # 核心参数
    base_w, base_d, base_h = 90.0, 80.0, 5.0
    plate_w = 70.0
    plate_h = 80.0
    plate_thick = 15.0
    tilt_deg = 20.0  # 相对垂直方向后倾角
    tilt_rad = math.radians(tilt_deg)
    run = plate_h * math.tan(tilt_rad)  # 水平投影偏移量

    # 1. 底座
    base = cq.Workplane("XY").box(base_w, base_d, base_h)

    # 2. 背部支撑板 (YZ平面绘制梯形截面，沿X轴拉伸)
    # 定位策略：使支撑面下部精确落入 load_boundary Y:[-38, -32] 区间
    y_front_bot = -38.0
    y_back_bot = y_front_bot + plate_thick
    y_back_top = y_back_bot + run
    y_front_top = y_front_bot + run
    z_top = base_h + plate_h

    profile = cq.Workplane("YZ").moveTo(y_front_bot, base_h) \
        .lineTo(y_back_bot, base_h) \
        .lineTo(y_back_top, z_top) \
        .lineTo(y_front_top, z_top) \
        .close()

    backrest = profile.extrude(plate_w, both=True)

    # 3. 前挡边 (手机底部限位)
    lip_w, lip_d, lip_h = 65.0, 5.0, 5.0
    lip = cq.Workplane("XY").box(lip_w, lip_d, lip_h)
    # 附着于支撑板顶部前缘，向前(-Y)突出
    lip = lip.translate((0, y_front_top - lip_d/2, z_top + lip_h/2))

    # 4. 布尔合并
    model = base.union(backrest).union(lip)

    # 5. 倒角与圆角 (应力缓解 & 打印优化)
    # 底部接触面保持平整，仅做微小倒角防割手
    model = model.edges("<Z").fillet(1.0)
    # 顶部外露边缘
    model = model.edges(">Z").fillet(2.0)
    # 垂直侧边及过渡边
    model = model.edges("|Z").fillet(2.0)
    # 手机接触前沿倒角防刮
    model = model.faces(">Z").edges("<Y").chamfer(1.0)
    # 挡边外侧圆角
    model = model.faces("<Y").edges(">Z").fillet(1.5)

    return model