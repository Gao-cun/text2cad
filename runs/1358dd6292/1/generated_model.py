import cadquery as cq

def build_model():
    # 核心参数 (mm)
    W = 100.0       # 宽度 (Y轴)
    L = 120.0       # 底座长度 (X轴)
    H_base = 10.0   # 底座厚度
    H_lip = 15.0    # 前挡边高度
    L_lip = 15.0    # 前挡边长度
    H_back = 115.0  # 背板高度
    T_back = 15.0   # 背板厚度
    tilt_off = 25.0 # 背板倾斜水平偏移量

    # 在 XZ 平面绘制侧轮廓
    profile = (
        cq.Workplane("XZ")
        .moveTo(-L/2, 0)
        .lineTo(L/2, 0)
        .lineTo(L/2, H_base)
        .lineTo(L_lip, H_base)
        .lineTo(L_lip, H_base + H_lip)
        .lineTo(0, H_base + H_lip)
        .lineTo(-tilt_off, H_base + H_back)
        .lineTo(-tilt_off - T_back, H_base + H_back)
        .lineTo(-L/2 + 10, H_base)
        .lineTo(-L/2, H_base)
        .close()
    )

    # 沿 Y 轴拉伸成实体
    model = profile.extrude(W)
    model = model.translate((0, -W/2, 0))

    # 倒角处理：提升 3D 打印质量与结构强度
    # 顶部边缘倒角 2mm
    model = model.edges(">Z").fillet(2.0)
    # 侧面/斜边及根部过渡倒角 4mm (缓解应力集中)
    model = model.edges("not(>Z or <Z)").fillet(4.0)
    # 底部非接触边缘倒角 2mm
    model = model.edges("<Z").fillet(2.0)

    return model