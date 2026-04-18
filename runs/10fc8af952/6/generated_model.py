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
    bp_x1, bp_z1 = 50.0, H
    back_prof = (
        cq.Workplane("XZ")
        .moveTo(bp_x0, bp_z0)
        .lineTo(bp_x1, bp_z1)
        .lineTo(bp_x1 - back_thick, bp_z1)
        .lineTo(bp_x0 - back_thick, bp_z0)
        .close()
    )
    back_plate = back_prof.workplane(offset=-W/2).extrude(W)

    # 3. 加强筋 (三角肋)
    rib_x0, rib_x1 = 10.0, bp_x0 - back_thick
    rib_z_top = 60.0
    rib_prof = (
        cq.Workplane("XZ")
        .moveTo(rib_x0, base_h)
        .lineTo(rib_x1, base_h)
        .lineTo(rib_x1, rib_z_top)
        .close()
    )
    rib = rib_prof.workplane(offset=-rib_thick/2).extrude(rib_thick)

    # 4. 顶部限位挡边
    stop_x = bp_x1 - back_thick
    stop = cq.Workplane("XY").box(3.0, 80.0, 8.0).translate((stop_x, 0, bp_z1 + 4.0))

    # 5. 前端侧挡边
    guide1 = cq.Workplane("XY").box(4.0, 10.0, 6.0).translate((110.0, 37.5, base_h + 3.0))
    guide2 = cq.Workplane("XY").box(4.0, 10.0, 6.0).translate((110.0, -37.5, base_h + 3.0))

    # 合并主体
    model = base.union(back_plate).union(rib).union(stop).union(guide1).union(guide2)

    # 6. 背部防滑特征 (优化切割深度与阵列间距，确保布尔运算稳定)
    face_cx = (bp_x0 - back_thick + bp_x1 - back_thick) / 2
    face_cz = (bp_z0 + bp_z1) / 2
    angle = math.degrees(math.atan2(bp_z1 - bp_z0, bp_x1 - bp_x0))
    anti_slip = (
        cq.Workplane("XZ")
        .transformed(offset=(face_cx, 0, face_cz), rotate=(0, angle, 0))
        .rarray(4.0, 4.0, 10, 12)
        .rect(2.0, 2.0)
        .extrude(1.0)
    )
    model = model.cut(anti_slip)

    # 7. 安全倒角处理 (修复原 |Y 选择器导致的 ChFi3d_Builder 拓扑错误)
    # 移除全局 |Y 选择器，仅对水平外轮廓边缘进行倒角，避开内部布尔交界线
    model = model.edges(">Z").fillet(1.5)
    model = model.edges("<Z").fillet(1.5)
    model = model.edges(">X").fillet(1.5)
    model = model.edges("<X").fillet(1.5)
    model = model.clean()

    # 8. 平移至第一象限
    bbox = model.solids().val().BoundingBox()
    model = model.translate((-bbox.xmin, -bbox.ymin, -bbox.zmin))
    model = model.clean()
    return model