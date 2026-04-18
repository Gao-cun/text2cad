import cadquery as cq
import math

def build_model():
    # 参数定义 (单位: mm)
    base_w, base_d, base_h = 90.0, 80.0, 10.0
    backrest_h = 95.0
    tilt_deg = 15.0  # 背板与垂直方向夹角
    backrest_thick = 12.0
    front_lip_h, front_lip_d = 8.0, 15.0
    fillet_r = 3.0

    # 1. 底座
    base = cq.Workplane('XY').box(base_w, base_d, base_h)

    # 2. 背部支撑板 (XZ平面绘制轮廓，沿Y轴拉伸)
    dx = backrest_h * math.tan(math.radians(tilt_deg))
    backrest = (
        cq.Workplane('XZ')
        .moveTo(0, base_h)
        .lineTo(dx, base_h + backrest_h)
        .lineTo(dx + backrest_thick, base_h + backrest_h)
        .lineTo(dx + backrest_thick, base_h)
        .close()
        .extrude(base_d)
        .translate((-base_w / 2, -base_d / 2, 0))
    )

    # 3. 前端挡边
    front_lip = (
        cq.Workplane('XY')
        .workplane(offset=base_h)
        .box(base_w - 10, front_lip_d, front_lip_h)
        .translate((0, base_d / 2 - front_lip_d / 2, 0))
    )

    # 4. 布尔合并
    model = base.union(backrest).union(front_lip)

    # 5. 倒角处理 (缓解应力集中，提升打印质量与手感)
    model = model.edges('>Z or <Z or |Y').fillet(fillet_r)

    # 6. 平移至第一象限以严格对齐固定边界盒 [0,0,0, 90,80,10]
    model = model.translate((base_w / 2, base_d / 2, 0))

    return model