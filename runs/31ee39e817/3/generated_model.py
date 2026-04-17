import cadquery as cq
import math

def build_model():
    # 计算65度倾角对应的水平投影长度
    dx = 100.0 / math.tan(math.radians(65.0))

    # 定义侧视轮廓 (X, Z)
    pts = [
        (0, 0),
        (100, 0),
        (100, 10),
        (100, 20),      # 前挡边顶部
        (96, 20),       # 前挡边内侧
        (96, 10),       # 前挡边根部
        (dx, 10),       # 斜面起点
        (0, 110),       # 斜面顶点
        (1.5, 110),     # 顶部凸缘外端
        (1.5, 109),     # 顶部凸缘内侧
        (0, 109),       # 顶部凸缘根部
        (0, 0)          # 闭合
    ]

    # 沿Y轴拉伸80mm，并居中
    model = cq.Workplane("XZ").polyline(pts).close().extrude(80).translate((0, -40, 0))

    # 边缘倒角处理 (0.8mm防割手)
    model = model.edges(">Z").chamfer(0.8)
    model = model.edges("<Z").chamfer(0.8)
    model = model.edges("|Y").chamfer(0.5)

    # 添加背部手机限位凹槽 (适配8-12mm厚度)
    groove = cq.Workplane("XZ").box(15, 80, 2.5)
    groove = groove.rotate((0, 0, 0), (0, 1, 0), -65.0)
    groove = groove.translate((dx/2 + 8, 0, 15))
    model = model.cut(groove)

    # 底部防滑交叉网格 (0.5mm深, 2x2mm间距)
    grid = cq.Workplane("XY").rarray(2, 2, 45, 35, True).rect(1.0, 1.0).extrude(-0.5).translate((50, 0, 0))
    model = model.cut(grid)

    return model

MODEL = build_model()