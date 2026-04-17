import cadquery as cq

def build_model():
    # 坐标系约定：Y轴垂直向上，Z轴为深度，X轴为宽度
    # 轮廓点 (Y, Z) 定义一体化截面
    pts = [
        (0, -40),    # 底座后缘底部
        (0, 40),     # 底座前缘底部
        (15, 40),    # 底座前缘顶部
        (15, 30),    # 手机挡边内侧底部
        (15, 25),    # 手机挡边顶部
        (15, 15),    # 背板起始过渡点
        (105, -27),  # 背板顶部前缘 (倾角约65°)
        (105, -40),  # 背板顶部后缘
        (0, -40)     # 闭合回路
    ]

    # 在YZ平面绘制轮廓并沿X轴拉伸100mm
    model = cq.Workplane("YZ").polyline(pts).close().extrude(100)
    # 沿X轴居中，使模型对称
    model = model.translate((-50, 0, 0))

    # 底部防滑凹槽 (在底座上表面Y=15处切割)
    groove1 = cq.Workplane("XZ").workplane(offset=15).rect(80, 1.5).extrude(-1)
    groove2 = cq.Workplane("XZ").workplane(offset=15).rect(80, 1.5).translate((0, -15, 0)).extrude(-1)
    model = model.cut(groove1).cut(groove2)

    # 边缘倒角处理 (0.8mm，优化打印层纹过渡与防割手)
    model = model.edges("|X").fillet(0.8)
    
    return model

MODEL = build_model()