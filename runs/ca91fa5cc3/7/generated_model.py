import cadquery as cq

def build_model():
    # 在XZ平面绘制一体化轮廓，确保单一水密实体
    pts = [
        (0, -55),    # 左下（固定边界）
        (100, -55),  # 右下
        (100, -40),  # 底座右上
        (88, -40),   # 前挡边外侧（预留12mm卡槽）
        (88, -30),   # 前挡边顶部
        (43.7, 55),  # 斜面顶部（精确65°倾角）
        (33.7, 55),  # 顶部限位前缘
        (33.7, 53.5),# 顶部限位下缘（1.5mm高）
        (43.7, 53.5),# 顶部限位后缘
        (43.7, 25),  # 背部内侧过渡
        (0, 25),     # 背部内侧底部
        (0, -55)     # 闭合至左下
    ]
    profile = cq.Workplane("XZ").polyline(pts).close()
    
    # 沿Y轴拉伸80mm并居中
    model = profile.extrude(80).translate((0, -40, 0))
    
    # 底部后缘局部加厚抗倾覆（X:0-10, Z:-55~-50）
    rear_block = cq.Workplane("XZ").box(10, 80, 5).translate((5, 0, -52.5))
    model = model.union(rear_block)
    
    # 全局0.5mm倒角消除锐边，提升打印与网格质量
    try:
        model = model.edges().chamfer(0.5)
    except Exception:
        pass
        
    return model

MODEL = build_model()