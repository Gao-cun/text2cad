import cadquery as cq

def build_model():
    # 坐标系约定：Y轴垂直向上，X轴水平向前，Z轴水平侧向
    # 轮廓设计：底部基座(100x10) + 68°倾斜背板 + 前端15mm防滑挡边
    pts = [
        (0, 0),
        (100, 0),
        (100, 10),
        (65, 10),
        (65, 15),
        (60, 15),
        (60, 10),
        (20, 110),
        (10, 110),
        (10, 10),
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

    # 对顶部和底部水平边缘进行0.8mm倒角，符合防割手与极简工业风要求
    model = model.edges(">Y").chamfer(0.8)
    model = model.edges("<Y").chamfer(0.8)

    return model

MODEL = build_model()