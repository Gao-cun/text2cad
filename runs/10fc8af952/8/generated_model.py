import cadquery as cq
import math

def build_model():
    L, W, H = 120.0, 100.0, 130.0
    base_h = 12.0
    back_thick = 8.0
    rib_thick = 6.0

    # 1. 主体轮廓 (XZ平面)
    main_prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(L, 0)
        .lineTo(L, base_h)
        .lineTo(45, H - 5)
        .lineTo(45 - back_thick, H - 5)
        .lineTo(25, base_h)
        .lineTo(0, base_h)
        .close()
    )
    model = main_prof.workplane(offset=-W/2).extrude(W)

    # 2. 提前对主体进行倒角，避免后续布尔运算产生复杂拓扑导致Fillet失败
    model = model.edges(">Z or <Z or >X or <X").fillet(2.0)

    # 3. 加强筋
    rib_x0 = 10.0
    rib_x1 = 25.0
    rib_z_top = 60.0
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(rib_x0, base_h)
        .lineTo(rib_x1, base_h)
        .lineTo(rib_x1, rib_z_top)
        .close()
    )
    rib = rib_prof.workplane(offset=-rib_thick/2).extrude(rib_thick)
    model = model.union(rib).clean()

    # 4. 前端侧挡边
    guide1 = cq.Workplane("XY").box(4.0, 10.0, 6.0).translate((110.0, 37.5, base_h + 3.0))
    guide2 = cq.Workplane("XY").box(4.0, 10.0, 6.0).translate((110.0, -37.5, base_h + 3.0))
    model = model.union(guide1).union(guide2).clean()

    # 5. 顶部限位挡边
    stop_x = 45 - back_thick
    stop = cq.Workplane("XY").box(3.0, 80.0, 8.0).translate((stop_x - 1.5, 0, H - 5 + 4.0))
    model = model.union(stop).clean()

    # 6. 背部防滑特征
    angle = math.degrees(math.atan2((H - 5) - base_h, 45 - 25))
    face_cx = (25 + 45 - back_thick) / 2
    face_cz = (base_h + H - 5) / 2
    anti_slip = (
        cq.Workplane("XZ")
        .transformed(offset=(face_cx, 0, face_cz), rotate=(0, angle, 0))
        .rarray(3.0, 3.0, 7, 9)
        .circle(0.6)
        .extrude(0.5)
    )
    model = model.cut(anti_slip).clean()

    # 7. 平移至第一象限原点
    bbox = model.solids().val().BoundingBox()
    model = model.translate((-bbox.xmin, -bbox.ymin, -bbox.zmin)).clean()
    return model