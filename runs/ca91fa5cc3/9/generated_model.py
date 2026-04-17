import cadquery as cq

def build_model():
    # 主轮廓 (XZ平面) - 简化拓扑避免自相交与PLC网格错误
    pts = [
        (0, -55),    # 左下（固定边界）
        (100, -55),  # 右下
        (100, -52),  # 底座上表面
        (60, -52),   # 底座前端过渡
        (60, -45),   # 台阶上沿
        (20, -45),   # 手机托架水平面
        (20, -30),   # 托架与背板交界
        (55, 55),    # 背板顶部（倾角约67.6°）
        (0, 55),     # 顶部后沿
        (0, -55)     # 闭合
    ]
    main = cq.Workplane("XZ").polyline(pts).close().extrude(80).translate((0, -40, 0))
    
    # 顶部前挡边（防前滑，3x80x2mm）
    top_lip = cq.Workplane("XZ").box(3, 80, 2).translate((53.5, -40, 54))
    
    # 底部后挡块（防后滑 & 抗倾覆，10x80x5mm）
    rear_block = cq.Workplane("XZ").box(10, 80, 5).translate((5, -40, -52.5))
    
    # 底部防滑筋（3条，提升摩擦与三点支撑）
    rib1 = cq.Workplane("XZ").box(100, 4, 1.5).translate((50, -38, -54.25))
    rib2 = cq.Workplane("XZ").box(100, 4, 1.5).translate((50, 0, -54.25))
    rib3 = cq.Workplane("XZ").box(100, 4, 1.5).translate((50, 38, -54.25))
    
    # 布尔并集构建单一水密实体
    model = main.union(top_lip).union(rear_block).union(rib1).union(rib2).union(rib3)
    
    # 全局0.5mm倒角消除锐边，提升打印与网格质量
    try:
        model = model.edges().chamfer(0.5)
    except Exception:
        pass
        
    return model.clean()

MODEL = build_model()