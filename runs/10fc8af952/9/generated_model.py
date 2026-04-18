import cadquery as cq
import math

def build_model():
    L, W, H = 120.0, 100.0, 130.0
    base_h = 12.0
    back_thick = 8.0
    rib_thick = 5.0

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
    main_body = main_prof.extrude(W)

    # 2. 倒角处理：避开底面接触边，仅对顶部及侧边倒角
    main_body = main_body.edges(">Z").fillet(2.0)

    # 3. 根部加强筋
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(10.0, base_h)
        .lineTo(25.0, base_h)
        .lineTo(25.0, 60.0)
        .close()
    )
    rib = rib_prof.extrude(rib_thick).translate((0, (W - rib_thick) / 2, 0))
    model = main_body.union(rib)

    # 4. 前端侧挡边
    guide_w, guide_h, guide_d = 4.0, 6.0, 10.0
    guide_y = 35.0
    guide1 = cq.Workplane("XY").box(guide_w, guide_d, guide_h).translate((110.0, guide_y, base_h + guide_h / 2))
    guide2 = cq.Workplane("XY").box(guide_w, guide_d, guide_h).translate((110.0, -guide_y, base_h + guide_h / 2))
    guides = guide1.union(guide2).edges(">Z").fillet(1.0)
    model = model.union(guides)

    # 5. 顶部限位挡边
    stop_x = 45 - back_thick
    stop = cq.Workplane("XY").box(3.0, 80.0, 8.0).translate((stop_x - 1.5, 0, H - 5 + 4.0))
    stop = stop.edges(">Z").fillet(1.0)
    model = model.union(stop)

    # 6. 背部防滑凹槽
    face_cx = (25 + 45 - back_thick) / 2
    face_cz = (base_h + H - 5) / 2
    angle = math.degrees(math.atan2((H - 5) - base_h, 45 - 25))

    anti_slip = (
        cq.Workplane("XZ")
        .transformed(offset=(face_cx, 0, face_cz), rotate=(0, angle, 0))
        .rarray(5.0, 5.0, 5, 6)
        .rect(2.5, 0.8)
        .extrude(0.6)
    )
    model = model.cut(anti_slip)

    # 7. 平移至第一象限原点
    bbox = model.BoundingBox()
    model = model.translate((-bbox.xmin, -bbox.ymin, -bbox.zmin))
    return model