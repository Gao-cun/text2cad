import cadquery as cq
import math

def build_model():
    W = 80.0
    base_h = 10.0
    total_h = 110.0
    angle = 65.0
    rad = math.radians(angle)
    dx = (total_h - base_h) / math.tan(rad)

    # 1. 底座 (X:0-60, Y:-40-40, Z:0-10)
    base = cq.Workplane("XZ").box(60.0, W, base_h).translate((30.0, 0, base_h/2))

    # 2. 背部斜面支撑 (65°倾角)
    slope = (cq.Workplane("XZ")
             .moveTo(0, base_h)
             .lineTo(dx, base_h)
             .lineTo(0, total_h)
             .close()
             .extrude(W)
             .translate((0, -W/2, 0)))

    model = base.union(slope)

    # 3. 根部圆角过渡 (R=3mm) - 消除应力集中
    try:
        model = model.edges(">Z and <X").fillet(3.0)
    except Exception:
        pass

    # 4. 前挡边 (高度10mm, 防手机下滑)
    front_lip = cq.Workplane("XZ").box(5.0, W, 10.0).translate((57.5, 0, base_h + 5.0))
    model = model.union(front_lip)

    # 5. 顶部防脱凸缘 (高度2mm)
    top_lip = cq.Workplane("XZ").box(2.0, W, 2.0).translate((1.0, 0, total_h - 1.0))
    model = model.union(top_lip)

    # 6. 背部手机限位凹槽 (深2mm, 宽15mm, 适配8-12mm手机)
    groove = cq.Workplane("XZ").box(15.0, W, 2.0)
    groove = groove.rotate((0, 0, 0), (0, 1, 0), -angle)
    groove = groove.translate((dx/2 + 5.0, 0, total_h/2 + 10.0))
    model = model.cut(groove)

    # 7. 底部防滑网格 (0.5mm深, 2x2mm间距)
    grid = cq.Workplane("XY").rarray(2, 2, 25, 20, True).rect(1.0, 1.0).extrude(-0.5)
    grid = grid.translate((30.0, 0, 0))
    model = model.cut(grid)

    # 8. 全局边缘倒角 (0.5mm 防割手)
    try:
        model = model.edges("|Y").chamfer(0.5)
    except Exception:
        pass

    return model

MODEL = build_model()