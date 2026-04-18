import cadquery as cq

def build_model():
    # 核心尺寸参数 (mm)
    L, W, H = 120.0, 100.0, 130.0
    base_h = 12.0
    back_thick = 8.0
    rib_thick = 6.0
    stop_h = 10.0
    stop_thick = 4.0
    guide_h = 8.0
    guide_w = 5.0

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

    # 3. 加强筋
    rib_x0 = back_x0
    rib_x1 = back_x0 - 40.0
    rib_z1 = back_z0 + 60.0
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(rib_x0, back_z0)
        .lineTo(rib_x0, rib_z1)
        .lineTo(rib_x1, back_z0)
        .close()
    )
    rib = rib_prof.workplane(offset=-rib_thick/2).extrude(rib_thick)

    # 4. 顶部限位挡边
    stop_prof = (
        cq.Workplane("XZ")
        .moveTo(back_x1, back_z1)
        .lineTo(back_x1 + stop_thick, back_z1)
        .lineTo(back_x1 + stop_thick, back_z1 + stop_h)
        .lineTo(back_x1, back_z1 + stop_h)
        .close()
    )
    stop = stop_prof.workplane(offset=-W/2 + 10).extrude(W - 20)

    # 5. 前端侧挡边
    guide1 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((back_x1 + 5, W/2 - 15, base_h + guide_h/2))
    guide2 = cq.Workplane("XY").box(guide_w, guide_w, guide_h).translate((back_x1 + 5, -W/2 + 15, base_h + guide_h/2))

    # 合并主体
    model = base.union(back_plate).union(rib).union(stop).union(guide1).union(guide2)

    # 6. 安全倒角
    model = model.clean()
    model = model.edges(">Z").fillet(1.5)
    model = model.edges("<Z").fillet(1.5)
    model = model.edges("<X").fillet(3.0)  # 根部应力过渡区

    # 7. 平移至第一象限，严格对齐分析边界盒
    # 修复：BoundingBox 是底层 Shape 的方法，需通过 .val() 调用
    bbox = model.val().BoundingBox()
    model = model.translate((-bbox.xmin, -bbox.ymin, -bbox.zmin))

    # 清理拓扑，确保单一闭合流形实体
    model = model.clean()
    return model