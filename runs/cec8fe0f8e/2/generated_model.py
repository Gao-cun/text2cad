import cadquery as cq

def build_model():
    # 核心参数 (mm)
    base_len, base_wid, base_h = 120.0, 100.0, 10.0
    slope_start_x, slope_end_x = 20.0, 80.0
    stand_h = 120.0
    top_lip_h, top_lip_w = 3.0, 5.0
    front_lip_h, front_lip_w = 2.0, 10.0
    fillet_r = 2.5

    # 1. 侧视轮廓 (XZ平面) - 一体化斜面主体
    profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(base_len, 0)
        .lineTo(base_len, base_h)
        .lineTo(slope_end_x, base_h)
        .lineTo(slope_end_x - top_lip_w, stand_h)
        .lineTo(slope_end_x - top_lip_w, stand_h + top_lip_h)
        .lineTo(slope_end_x - top_lip_w - 2, stand_h + top_lip_h)
        .lineTo(slope_end_x - top_lip_w - 2, stand_h)
        .lineTo(slope_start_x, base_h)
        .lineTo(front_lip_w, base_h)
        .lineTo(front_lip_w, base_h + front_lip_h)
        .lineTo(0, base_h + front_lip_h)
        .close()
    )

    # 2. 沿Y轴拉伸生成实体
    model = profile.extrude(base_wid)

    # 3. 背部减重/散热开孔 (Cut)
    cut_w, cut_h, cut_d = 60.0, 60.0, 15.0
    cut_box = cq.Workplane("XY").box(cut_w, cut_d, cut_h).translate((base_len/2, base_wid/2, base_h + cut_h/2 + 10))
    model = model.cut(cut_box)

    # 4. 侧向限位挡边 (Union)
    stop_h, stop_w = 4.0, 4.0
    stop_y1, stop_y2 = 10.0, base_wid - 10.0
    stop_z = base_h + 1.0
    side_stop1 = cq.Workplane("XY").box(80.0, stop_w + 0.1, stop_h).translate((base_len/2, stop_y1 + stop_w/2, stop_z))
    side_stop2 = cq.Workplane("XY").box(80.0, stop_w + 0.1, stop_h).translate((base_len/2, stop_y2 - stop_w/2, stop_z))
    model = model.union(side_stop1).union(side_stop2)

    # 5. 底座防滑凸点 (使用 pushPoints 替代易报错的 rarray)
    grip_points = [(x, y) for x in range(20, 100, 10) for y in range(20, 80, 10)]
    grip = cq.Workplane("XY").pushPoints(grip_points).circle(1.2).extrude(0.8)
    model = model.union(grip)

    # 6. 边缘倒角 (提升手感与打印成功率)
    model = model.edges(">Z").fillet(fillet_r)
    model = model.edges("<Z").fillet(fillet_r)

    # 7. 拓扑清理
    model = model.clean()
    return model