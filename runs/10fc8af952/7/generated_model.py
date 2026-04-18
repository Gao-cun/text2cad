import cadquery as cq
import math

def build_model():
    L, W, H = 120.0, 100.0, 130.0
    base_h = 12.0
    back_thick = 8.0
    rib_thick = 6.0

    # 1. 底座
    base = cq.Workplane("XY").box(L, W, base_h)

    # 2. 背板 (XZ平面绘制，Y向拉伸)
    bp_x0, bp_z0 = 25.0, base_h
    bp_x1, bp_z1 = 45.0, H - 5.0
    back_prof = (
        cq.Workplane("XZ")
        .moveTo(bp_x0, bp_z0)
        .lineTo(bp_x1, bp_z1)
        .lineTo(bp_x1 - back_thick, bp_z1)
        .lineTo(bp_x0 - back_thick, bp_z0)
        .close()
    )
    back_plate = back_prof.workplane(offset=-W/2).extrude(W)

    # 3. 加强筋 (三角肋，消除悬臂风险)
    rib_x0 = 10.0
    rib_x1 = bp_x0 - back_thick
    rib_z_top = 60.0
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(rib_x0, base_h)
        .lineTo(rib_x1, base_h)
        .lineTo(rib_x1, rib_z_top)
        .close()
    )
    rib = rib_prof.workplane(offset=-rib_thick/2).extrude(rib_thick)

    # 合并主体
    model = base.union(back_plate).union(rib).clean()

    # 4. 前端侧挡边 (适配70-80mm手机，内距75mm)
    guide1 = cq.Workplane("XY").box(4.0, 10.0, 6.0).translate((110.0, 37.5, base_h + 3.0))
    guide2 = cq.Workplane("XY").box(4.0, 10.0, 6.0).translate((110.0, -37.5, base_h + 3.0))
    model = model.union(guide1).union(guide2).clean()

    # 5. 顶部限位挡边 (防止手机后滑)
    stop_x = bp_x1 - back_thick
    stop = cq.Workplane("XY").box(3.0, 80.0, 8.0).translate((stop_x - 1.5, 0, bp_z1 + 4.0))
    model = model.union(stop).clean()

    # 6. 背部防滑特征 (圆点阵列切割，深度1.5mm)
    angle = math.degrees(math.atan2(bp_z1 - bp_z0, bp_x1 - bp_x0))
    face_cx = (bp_x0 - back_thick + bp_x1 - back_thick) / 2
    face_cz = (bp_z0 + bp_z1) / 2
    anti_slip = (
        cq.Workplane("XZ")
        .transformed(offset=(face_cx, 0, face_cz), rotate=(0, angle, 0))
        .rarray(3.0, 3.0, 10, 12)
        .circle(0.8)
        .extrude(1.5)
    )
    model = model.cut(anti_slip).clean()

    # 7. 安全倒角处理 (避开内部切割边，仅对外轮廓倒角)
    model = model.edges(">Z").fillet(1.5)
    model = model.edges("<Z").fillet(2.0)
    model = model.edges(">X").fillet(1.5)
    model = model.edges("<X").fillet(1.5)
    model = model.clean()

    # 8. 平移至第一象限
    bbox = model.solids().val().BoundingBox()
    model = model.translate((-bbox.xmin, -bbox.ymin, -bbox.zmin)).clean()
    return model