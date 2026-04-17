import cadquery as cq

def build_model():
    # 1. 车身主体侧面轮廓 (XZ平面)
    body_profile = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(115, 0)
        .lineTo(115, 8)
        .lineTo(100, 14)
        .lineTo(80, 24)
        .lineTo(60, 27)
        .lineTo(40, 27)
        .lineTo(20, 24)
        .lineTo(5, 14)
        .lineTo(0, 8)
        .close()
    )
    body = body_profile.extrude(48).translate((0, -24, 0))

    # 2. 车顶/驾驶舱轮廓
    roof_profile = (
        cq.Workplane("XZ")
        .moveTo(22, 24)
        .lineTo(30, 32)
        .lineTo(50, 35)
        .lineTo(70, 35)
        .lineTo(88, 32)
        .lineTo(95, 24)
        .close()
    )
    roof = roof_profile.extrude(44).translate((0, -22, 0))

    # 3. 组合车身与车顶
    car = body.union(roof)

    # 4. 车轮 (4个圆柱，与车身一体)
    wheel_r = 11.0
    wheel_w = 14.0
    wheel_x = [22.0, 93.0]
    wheels = []
    for x in wheel_x:
        w = cq.Workplane("YZ").circle(wheel_r).extrude(wheel_w).translate((x, -wheel_w/2, wheel_r))
        wheels.append(w)
    car = car.union(*wheels)

    # 5. 底盘底座 (增加稳定性，微凸防滑)
    base = cq.Workplane("XY").box(118, 52, 4).translate((57.5, 0, -2))
    car = car.union(base)

    # 6. 车窗与车门轮廓 (浅切槽，非镂空)
    window_cut = (
        cq.Workplane("XZ")
        .moveTo(26, 27)
        .lineTo(33, 33)
        .lineTo(49, 35)
        .lineTo(67, 35)
        .lineTo(84, 33)
        .lineTo(91, 27)
        .close()
        .extrude(46)
        .translate((0, -23, 0))
    )
    window_cut = window_cut.translate((0, 0, 0.8))
    car = car.cut(window_cut)

    # 7. 局部圆角优化 (替换全局圆角以避免拓扑错误，仅处理顶部/垂直边缘)
    try:
        car = car.edges(">Z or <Z").fillet(1.5)
    except Exception:
        car = car.chamfer(1.0)

    # 8. 尺寸适配与定位 (目标 120x55x45)
    bb = car.val().BoundingBox()
    s = min(120.0/(bb.xmax-bb.xmin), 55.0/(bb.ymax-bb.ymin), 45.0/(bb.zmax-bb.zmin))
    
    # 修复 scale 报错：使用底层 Solid 的 Scaled 方法并重新包装为 Workplane
    scaled_solid = car.val().Scaled(s)
    car = cq.Workplane("XY").newObject([scaled_solid])

    bb2 = car.val().BoundingBox()
    car = car.translate((-bb2.xmin, -bb2.ymin, -bb2.zmin))

    return car

MODEL = build_model()