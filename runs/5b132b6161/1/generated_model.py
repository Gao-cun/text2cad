import cadquery as cq

def build_model():
    # 核心尺寸参数 (mm)
    base_len = 120.0
    base_wid = 100.0
    base_h = 10.0
    back_h = 120.0
    slope_bottom_x = 90.0
    slope_top_x = 25.0
    top_thick = 10.0
    lip_thick = 10.0

    # 1. 构建XZ平面侧轮廓 (一体化楔形结构)
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(base_len, 0)
        .lineTo(base_len, base_h)
        .lineTo(slope_bottom_x, base_h)
        .lineTo(slope_top_x, back_h)
        .lineTo(slope_top_x - top_thick, back_h)
        .lineTo(slope_top_x - top_thick, base_h)
        .lineTo(slope_top_x - top_thick - lip_thick, base_h)
        .lineTo(slope_top_x - top_thick - lip_thick, 0)
        .close()
    )

    # 2. 沿Y轴拉伸生成实体
    model = profile.extrude(base_wid)

    # 3. 边缘倒角处理 (缓解应力集中 & 提升打印表面质量)
    # 顶部前后边缘
    model = model.edges(">Z").fillet(3.0)
    # 底部前唇边缘
    model = model.edges("<Z and >X").fillet(2.0)
    # 侧面Y向垂直边缘
    model = model.edges("|Y").fillet(2.0)

    return model