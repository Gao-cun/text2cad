import cadquery as cq

def build_model():
    # 轮廓点定义 (X, Y)，X为长度方向，Y为高度方向
    # 精确匹配65°倾角：tan(65°)≈2.1445，高度差100mm对应水平投影≈46.6mm
    pts = [
        (0, 0),
        (100, 0),
        (100, 10),
        (65, 10),
        (65, 15),
        (55, 15),
        (55, 10),
        (10, 110),
        (0, 110),
        (0, 10),
        (0, 0)
    ]

    # 沿Z轴拉伸80mm形成实体，并平移使Z轴居中
    model = (
        cq.Workplane("XY")
        .polyline(pts)
        .close()
        .extrude(80)
        .translate((0, 0, -40))
    )

    # 边缘倒角处理：顶部和底部水平外缘0.8mm倒角，符合防割手与极简工业风
    model = model.edges(">Y").chamfer(0.8)
    model = model.edges("<Y").chamfer(0.8)

    return model

MODEL = build_model()