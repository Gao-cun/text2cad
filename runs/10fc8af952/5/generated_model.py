import cadquery as cq
import math

def build_model():
    L, W, H = 120.0, 100.0, 130.0
    base_h = 12.0
    back_thick = 8.0
    rib_thick = 5.0
    stop_h = 8.0
    stop_thick = 3.0
    guide_h = 6.0
    guide_w = 4.0

    # 1. 底座
    base = cq.Workplane("XY").box(L, W, base_h)

    # 2. 背板 (XZ平面绘制，Y向拉伸)
    back_x0 = 20.0
    back_x1 = 45.0
    back_z0 = base_h
    back_z1 = H
    back_prof = (
        cq.Workplane("XZ")
        .moveTo(back_x0, back_z0)
        .lineTo(back_x1, back_z1)
        .lineTo(back_x1 - back_thick, back_z1)
        .lineTo(back_x0 - back_thick, back_z0)
        .close()
    )
    back_plate = back_prof.workplane(offset=-W/2).extrude(W)

    # 3. 加强筋 (三角肋，连接底座后缘与背板内侧)
    rib_x0 = 10.0
    rib_x1 = back_x0
    rib_z1 = back_z0 + 50.0
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(rib_x0, back_z0)
        .lineTo(rib_x1, back_z0)
        .lineTo(rib_x1, rib_z1)
        .close()
    )
    rib = rib_prof.workplane(offset=-rib_thick/2).extrude(rib_thick)

    # 4. 顶部限位挡边 (防止手机后滑)
    stop_prof = (
        cq.Workplane("XZ")
        .moveTo(back_x1, back_z1)
        .lineTo(back_x1 - stop_thick, back_z1)
        .lineTo(back_x1 - stop_thick, back_z1 + stop_h)
        .lineTo(back_x1, back_z1 + stop_h)
        .close()
    )
    stop = stop_prof.workplane(offset=-40).extrude(80)

    # 5. 前端侧挡边 (约束手机宽度 70-80mm)
    guide_x = 90.0
    guide1 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((guide_x, 37.5, base_h + guide_h/2))
    guide2 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((guide_x, -37.5, base_h + guide_h/2))

    # 合并主体
    model = base.union(back_plate).union(rib).union(stop).union(guide1).union(guide2)
    model = model.clean()

    # 6. 背部防滑特征
    face_center_x = (back_x0 + back_x1 - back_thick) / 2
    face_center_z = (back_z0 + back_z1) / 2
    angle = math.degrees(math.atan2(back_z1 - back_z0, back_x1 - back_x0))
    anti_slip_solid = (
        cq.Workplane("XZ")
        .transformed(offset=(face_center_x, 0, face_center_z), rotate=(0, angle, 0))
        .rarray(4, 4, 6, 8)
        .rect(2.0, 0.5)
        .extrude(0.3)
    )
    model = model.cut(anti_slip_solid)
    model = model.clean()

    # 7. 全局倒角处理 (提升手感与消除应力集中)
    model = model.edges("<X").fillet(3.0)
    model = model.edges(">Z").fillet(1.5)
    model = model.edges("<Z").fillet(1.5)
    model = model.edges("|Y").fillet(1.5)
    model = model.clean()

    # 8. 平移至第一象限，严格对齐分析边界盒
    # 修复：Workplane 对象无 BoundingBox 方法，需通过 .val() 获取底层 Shape
    bbox = model.val().BoundingBox()
    model = model.translate((-bbox.xmin, -bbox.ymin, -bbox.zmin))
    model = model.clean()
    return model