import cadquery as cq

def build_model():
    # 核心设计参数 (单位: mm)
    base_len = 120.0
    base_wid = 100.0
    base_h = 10.0
    back_h = 110.0
    slope_start_x = 20.0
    slope_start_z = 15.0
    slope_end_x = 95.0
    slope_end_z = base_h + back_h
    top_lip_len = 10.0
    top_lip_h = 10.0
    front_lip_len = 10.0
    front_lip_h = 8.0
    fillet_r = 2.0

    # 构建XZ平面侧面轮廓
    pts = [
        (0, 0),
        (base_len, 0),
        (base_len, base_h),
        (slope_end_x + top_lip_len, base_h),
        (slope_end_x + top_lip_len, slope_end_z + top_lip_h),
        (slope_end_x, slope_end_z + top_lip_h),
        (slope_start_x, slope_start_z),
        (slope_start_x - front_lip_len, slope_start_z),
        (slope_start_x - front_lip_len, slope_start_z + front_lip_h),
        (slope_start_x, slope_start_z + front_lip_h),
        (slope_start_x, base_h),
        (0, base_h)
    ]

    # 生成轮廓并沿Y轴挤出
    profile = cq.Workplane("XZ").polyline(pts).close()
    model = profile.extrude(base_wid)

    # 全局倒角：缓解应力集中，优化FDM打印层间结合，提升手感
    model = model.edges().fillet(fillet_r)

    return model