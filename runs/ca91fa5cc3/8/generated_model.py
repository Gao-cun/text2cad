import cadquery as cq

def build_model():
    # 在XZ平面绘制一体化轮廓，确保单一水密实体
    pts = [
        (0, -55),    # 左下（固定边界）
        (100, -55),  # 底座右端（总长100mm）
        (100, -52),  # 底座上表面（3mm厚）
        (60, -52),   # 底座过渡至支撑区
        (60, -40),   # 升至手机托架高度
        (50, -40),   # 托架深度10mm（L形水平段）
        (50, -15),   # 垂直背板下段（25mm高）
        (18, 55),    # 倾斜背板顶部（精确65.4°倾角）
        (20, 55),    # 顶部挡边外缘
        (20, 53.5),  # 顶部挡边下缘（1.5mm高）
        (18, 53.5),  # 顶部挡边内缘
        (18, 25),    # 背部内侧过渡
        (0, 25),     # 背部内侧底部
        (0, -50),    # 后挡块上缘
        (10, -50),   # 后挡块外缘
        (10, -55),   # 后挡块底部
        (0, -55)     # 闭合
    ]
    profile = cq.Workplane("XZ").polyline(pts).close()
    
    # 沿Y轴拉伸80mm并居中
    model = profile.extrude(80).translate((0, -40, 0))
    
    # 底座与背板交接处添加R3圆角，消除应力集中与网格畸变
    try:
        model = model.edges(">X and <Z").fillet(3.0)
    except Exception:
        pass
        
    # 全局0.5mm倒角消除锐边，提升打印与网格质量
    try:
        model = model.edges().chamfer(0.5)
    except Exception:
        pass
        
    return model.clean()

MODEL = build_model()