import cadquery as cq

def build_model():
    # 核心尺寸参数 (mm)
    length = 120.0
    width = 100.0
    base_h = 10.0
    back_start_x = 85.0
    back_top_x = 15.0
    back_top_z = 130.0
    lip_w = 12.0
    lip_h = 8.0
    r = 2.5

    # 构建XZ截面轮廓
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(length, 0)
        .lineTo(length, base_h)
        .lineTo(length - lip_w, base_h)
        .lineTo(length - lip_w, base_h + lip_h)
        .lineTo(length - lip_w - 10, base_h + lip_h)
        .lineTo(length - lip_w - 10, base_h)
        .lineTo(back_start_x, base_h)
        .lineTo(back_top_x, back_top_z)
        .lineTo(0, back_top_z)
        .lineTo(0, base_h)
        .close()
    )

    # 沿Y轴拉伸成型
    model = profile.extrude(width)

    # 边缘倒角：缓解应力集中，提升3D打印表面质量与手感
    model = model.edges().fillet(r)

    return model