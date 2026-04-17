import cadquery as cq

def build_model():
    # 轮廓点 (Y, Z)，Y为垂直方向，Z为深度方向
    pts = [
        (0, -35),   # 底座后缘底部
        (0, 35),    # 底座前缘底部
        (10, 35),   # 底座前缘顶部
        (10, 25),   # 手机挡边内侧底部
        (15, 25),   # 手机挡边顶部
        (100, -15), # 背板顶部前缘
        (100, -35), # 背板顶部后缘
        (0, -35)    # 闭合
    ]

    # 在YZ平面绘制轮廓并沿X轴拉伸100mm
    model = cq.Workplane("YZ").polyline(pts).close().extrude(100)

    # 底部防滑凹槽 (在底座上表面切出)
    groove = cq.Workplane("YZ").rect(80, 70).extrude(2).translate((0, 9, 0))
    model = model.cut(groove)

    # 边缘倒角处理 (0.5-1mm)
    model = model.edges("|X").fillet(1.0)
    model = model.edges(">X").fillet(0.5)
    model = model.edges("<X").fillet(0.5)

    return model

MODEL = build_model()