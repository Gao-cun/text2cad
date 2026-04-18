import cadquery as cq

def build_model():
    # 基础参数
    base_w = 90.0
    base_d = 80.0
    base_h = 5.0
    lip_h = 12.0
    back_top_z = 105.0
    thickness = 6.0

    # 在XZ平面绘制侧轮廓 (Y为挤出方向)
    profile = (
        cq.Workplane("XZ")
        .moveTo(-base_w/2, 0)
        .lineTo(base_w/2, 0)
        .lineTo(base_w/2, base_h)
        .lineTo(15, base_h)
        .lineTo(15, lip_h)
        .lineTo(10, lip_h)
        .lineTo(10, base_h)
        .lineTo(-10, back_top_z)
        .lineTo(-10 - thickness, back_top_z)
        .lineTo(-12, base_h)
        .lineTo(-base_w/2, base_h)
        .close()
    )

    # 沿Y轴挤出
    model = profile.extrude(base_d)

    # 居中Y轴
    model = model.translate((0, -base_d/2, 0))

    # 倒角处理：缓解应力集中，提升3D打印表面质量
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.5)
    model = model.edges(">X").fillet(1.5)
    model = model.edges("<X").fillet(2.0)

    # 背部减重孔（优化材料分布与打印冷却）
    cutout = cq.Workplane("XZ").circle(22).extrude(base_d + 20)
    cutout = cutout.translate((-13, -base_d/2 - 10, 55))
    model = model.cut(cutout)

    return model