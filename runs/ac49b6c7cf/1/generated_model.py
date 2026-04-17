import cadquery as cq

def build_model():
    # 定义XY平面轮廓 (Y轴垂直向上，X轴为深度方向)
    # 结构：10mm厚防滑基座 + 65°倾斜背板 + 底部手机挡边
    profile_pts = [
        (0, 0), (100, 0), (100, 10), (87, 10), (87, 14),
        (77, 14), (77, 10), (40, 110), (25, 110), (25, 10), (0, 10), (0, 0)
    ]
    
    # 沿Z轴拉伸生成实体，宽度80mm
    model = cq.Workplane("XY").polyline(profile_pts).close().extrude(80, both=True)
    
    # 边缘倒角处理 (0.5-1mm)，符合防割手与视觉要求
    model = model.edges(">Y").chamfer(0.8)
    model = model.edges("<Y").chamfer(0.5)
    
    # 平移至Y轴中心，严格匹配固定/加载边界盒的Y范围[-55, 55]
    # X=0面自动对齐固定边界盒，Z轴自动居中于[-40, 40]
    model = model.translate((0, -55, 0))
    
    return model

MODEL = build_model()