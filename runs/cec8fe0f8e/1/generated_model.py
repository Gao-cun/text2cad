import cadquery as cq

def build_model():
    # 核心尺寸参数 (mm)
    base_len = 120.0
    base_wid = 100.0
    base_h = 10.0
    stand_h = 115.0
    front_lip_x = 10.0
    front_lip_h = 10.0
    slope_start_x = 20.0
    slope_end_x = 82.0
    top_lip_w = 10.0
    back_wall_x = 100.0
    fillet_r = 2.5

    # 1. 绘制XZ平面侧视轮廓
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(base_len, 0)
        .lineTo(base_len, base_h)
        .lineTo(back_wall_x, base_h)
        .lineTo(slope_end_x, stand_h)
        .lineTo(slope_end_x - top_lip_w, stand_h)
        .lineTo(slope_start_x, base_h)
        .lineTo(front_lip_x, base_h)
        .lineTo(front_lip_x, base_h + front_lip_h)
        .lineTo(0, base_h + front_lip_h)
        .close()
    )

    # 2. 沿Y轴拉伸生成实体
    model = profile.extrude(base_wid)

    # 3. 全局倒角 (应力释放 & 3D打印友好)
    model = model.edges().fillet(fillet_r)

    return model