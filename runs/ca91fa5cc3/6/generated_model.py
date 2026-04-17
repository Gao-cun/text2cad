import cadquery as cq

def build_model():
    # 底座：长100mm，宽80mm，高10mm。X范围[0, 100]，Z范围[-55, -45]
    base = cq.Workplane("XZ").box(100, 80, 10).translate((50, 0, -50))

    # 背部支撑板：厚10mm，宽80mm，高110mm。倾斜25°（与水平面成65°）
    # 初始中心在(0,0,0)，平移使底部前角位于(20, 0, -45)
    back_plate = cq.Workplane("XZ").box(10, 80, 110).translate((15, 0, 10))
    # 绕Y轴旋转-25度，旋转轴心设在底部前角(20, 0, -45)
    back_plate = back_plate.rotate((20, 0, -45), (0, 1, 0), -25)

    # 底部前挡边：厚10mm，宽80mm，高10mm。X范围[35, 45]，Z范围[-45, -35]
    # 与背板底部形成约10mm手机卡槽，兼容8-12mm厚度
    front_lip = cq.Workplane("XZ").box(10, 80, 10).translate((40, 0, -40))

    # 顶部限位挡边：厚2mm，宽80mm，高1.5mm。位于背板顶部前侧
    top_stopper = cq.Workplane("XZ").box(2, 80, 1.5).translate((65, 0, 55))

    # 后部防倾覆配重块：厚10mm，宽80mm，高5mm。X范围[0, 10]，Z范围[-55, -50]
    rear_block = cq.Workplane("XZ").box(10, 80, 5).translate((5, 0, -52.5))

    # 布尔并集构建单一水密实体
    model = base.union(back_plate).union(front_lip).union(top_stopper).union(rear_block)

    # 全局0.5mm倒角，消除锐边，提升打印成功率与网格质量
    try:
        model = model.edges().chamfer(0.5)
    except Exception:
        pass

    return model

MODEL = build_model()