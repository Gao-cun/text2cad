import cadquery as cq

def build_model():
    # 侧视轮廓 (XZ平面)，X为长度方向，Z为高度方向
    # 轮廓已对齐固定/加载边界盒 Z∈[-55, 55]
    pts = [
        (0, -55),
        (60, -55),
        (60, -45),
        (56, -45),
        (56, -35),
        (46, -35),
        (46, -45),
        (100, 50),
        (100, 55),
        (95, 55),
        (95, 50),
        (0, -45),
        (0, -55)
    ]
    main_body = cq.Workplane("XZ").polyline(pts).close().extrude(80).translate((0, -40, 0))

    # 三角加强筋，位于底座与背板交接处，提升抗弯刚度
    rib_pts = [(56, -45), (70, -45), (56, -30)]
    rib = cq.Workplane("XZ").polyline(rib_pts).close().extrude(80).translate((0, -40, 0))

    model = main_body.union(rib)

    # 全局0.5mm倒角，优化打印层纹过渡与防割手
    model = model.edges("|Y").fillet(0.5)

    return model

MODEL = build_model()