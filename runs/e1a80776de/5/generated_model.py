import cadquery as cq

def build_model():
    # 1. 车身主体轮廓 (XZ平面)
    body_prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(115, 0)
        .lineTo(115, 10)
        .spline([(100, 15), (80, 25), (60, 28), (40, 28), (20, 25), (5, 15)])
        .lineTo(0, 10)
        .close()
    )
    body = body_prof.extrude(48)

    # 2. 车顶/驾驶舱轮廓
    roof_prof = (
        cq.Workplane("XZ")
        .moveTo(25, 25)
        .spline([(35, 33), (55, 36), (75, 36), (90, 33)])
        .lineTo(95, 25)
        .close()
    )
    roof = roof_prof.extrude(44)
    car = body.union(roof)

    # 3. 车轮 (确保与车身充分重叠以形成单一实体)
    wheel_r = 11.0
    wheel_w = 16.0
    wheel_x = [24.0, 91.0]
    wheels = []
    for x in wheel_x:
        w = cq.Workplane("YZ").circle(wheel_r).extrude(wheel_w).translate((x, -wheel_w/2, wheel_r))
        wheels.append(w)
    car = car.union(*wheels)

    # 4. 加厚底盘底座 (>=2.0mm, 增加稳定性与打印接触面)
    base = cq.Workplane("XY").box(118, 50, 3.0).translate((57.5, 0, -1.5))
    car = car.union(base)

    # 5. 车窗/车门浅浮雕 (替代镂空, 深度0.6mm, 避免FDM悬垂与薄壁)
    win_prof = (
        cq.Workplane("XZ")
        .moveTo(28, 27)
        .spline([(35, 33), (50, 35), (65, 35), (80, 33)])
        .lineTo(88, 27)
        .close()
    )
    win_cut = win_prof.extrude(46).translate((0, -23, 0.6))
    car = car.cut(win_cut)

    # 6. 边缘圆角优化 (前后受力/固定端面R2.0, 上下边缘R1.5)
    try:
        car = car.edges("|X").fillet(2.0)
    except Exception:
        pass
    try:
        car = car.edges(">Z or <Z").fillet(1.5)
    except Exception:
        pass

    # 7. 强制合并为单一水密实体 (解决多实体网格划分失败)
    solids = car.solids().vals()
    if len(solids) > 1:
        fused = solids[0]
        for s in solids[1:]:
            fused = fused.fuse(s)
        car = cq.Workplane("XY").newObject([fused])
    else:
        car = cq.Workplane("XY").newObject([solids[0]])

    # 8. 尺寸适配与定位 (严格对齐目标边界盒 [0, -27.5, -22.5] -> [120, 27.5, 22.5])
    bb = car.val().BoundingBox()
    dx, dy, dz = bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin
    s = min(120.0 / dx, 55.0 / dy, 45.0 / dz)
    scaled = car.val().scale(s)
    car = cq.Workplane("XY").newObject([scaled])

    bb2 = car.val().BoundingBox()
    car = car.translate((-bb2.xmin, -(bb2.ymax + bb2.ymin) / 2, -(bb2.zmax + bb2.zmin) / 2))

    return car

MODEL = build_model()