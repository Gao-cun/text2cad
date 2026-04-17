import cadquery as cq

def build_model():
    # 定义XY平面轮廓（Y为垂直方向，X为深度方向）
    # 轮廓设计：底座+68°倾斜背板+底部手机挡边，一体化实心结构
    profile = (
        cq.Workplane("XY")
        .polyline([
            (0, 0),     # 底部后缘（对齐固定边界X=0）
            (100, 0),   # 底部前缘
            (100, 10),  # 底座上表面前缘
            (60, 110),  # 背板顶端前缘（约68°倾角，符合60-70°要求）
            (45, 110),  # 背板顶端后缘
            (45, 10),   # 内侧垂直面
            (65, 10),   # 手机挡边前缘
            (65, 15),   # 挡边上表面
            (45, 15),   # 挡边后缘
            (45, 10)    # 闭合至内侧
        ])
        .close()
        .extrude(80)
    )

    # 沿Z轴居中，使模型宽度为80mm（Z: -40 ~ 40）
    model = profile.translate((0, 0, -40))

    # 边缘倒角处理（防割手，弱化3D打印层纹，提升视觉质感）
    model = model.edges(">Y").chamfer(1.0)
    model = model.edges("<Y").chamfer(0.5)
    model = model.edges(">X").chamfer(0.8)

    return model