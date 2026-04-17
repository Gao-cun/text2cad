import cadquery as cq

def build_model():
    # 定义XY平面轮廓 (X: 深度方向, Y: 垂直方向)
    # 严格保证 X=0 处存在完整、共面的垂直矩形面，直接对齐有限元固定边界条件
    pts = [
        (0, -40),   # 底部后缘
        (0, 40),    # 顶部后缘
        (55, 40),   # 顶部前缘
        (100, 10),  # 斜面末端
        (100, 0),   # 前部底缘
        (80, 0),    # 手机挡边前缘
        (80, 8),    # 挡边顶面
        (65, 8),    # 挡边后缘
        (65, 0),    # 底座前缘
        (0, 0)      # 底座后缘
    ]

    # 生成闭合轮廓
    profile = cq.Workplane("XY").polyline(pts).close()
    
    # 沿Z轴拉伸80mm，并平移至Z轴中心，确保宽度覆盖[-40, 40]
    model = profile.extrude(80).translate((0, 0, -40))

    # 针对底座与背板交接处（X=0, Y=0附近）添加R3.0圆角过渡
    # 消除90°锐角，显著降低悬臂受力下的根部应力集中，提升网格质量
    model = model.edges("|Z and <X").fillet(3.0)

    # 边缘倒角处理，防割手并弱化3D打印层纹
    model = model.edges(">Y").chamfer(1.0)
    model = model.edges("<Y").chamfer(0.5)

    return model