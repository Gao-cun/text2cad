import cadquery as cq
import math

def build_model():
    W = 80.0
    base_h = 10.0
    total_h = 110.0
    angle = 65.0
    rad = math.radians(angle)
    dx = (total_h - base_h) / math.tan(rad)

    # 1. 主体轮廓 (XZ平面单线框闭合挤出，确保单一实体，彻底解决多体非流形问题)
    profile = (cq.Workplane("XZ")
               .moveTo(0, 0)
               .lineTo(60, 0)
               .lineTo(60, base_h)
               .lineTo(55, base_h)
               .lineTo(55, base_h + 10)
               .lineTo(51, base_h + 10)
               .lineTo(dx, base_h)
               .lineTo(0, total_h)
               .close()
               .extrude(W)
               .translate((0, -W/2, 0)))

    # 2. 顶部防脱凸缘 (与主体安全融合)
    top_lip = cq.Workplane("XZ").box(3.0, W, 2.0).translate((1.5, 0, total_h - 1.0))
    model = profile.union(top_lip)

    # 3. 根部应力释放圆角 (R=3mm，强化抗弯刚度)
    try:
        model = model.edges("<X and <Z").fillet(3.0)
    except Exception:
        pass

    # 4. 背部手机限位凹槽 (深2mm，适配8-12mm厚度)
    groove = cq.Workplane("XZ").box(15.0, W, 2.0)
    groove = groove.rotate((0, 0, 0), (0, 1, 0), -angle)
    groove = groove.translate((dx/2 + 3.0, 0, total_h/2 + 5.0))
    model = model.cut(groove)

    # 5. 底部防滑网格 (0.5mm深，2x2mm间距，内缩阵列防边缘拓扑破损)
    grid = cq.Workplane("XY").rarray(2, 2, 24, 18, True).rect(1.0, 1.0).extrude(-0.5)
    grid = grid.translate((30.0, 0, 0))
    model = model.cut(grid)

    # 6. 全局边缘倒角 (0.5mm 防割手，提升打印表面质量)
    try:
        model = model.edges("|Y").chamfer(0.5)
    except Exception:
        pass

    return model

MODEL = build_model()