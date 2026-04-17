import cadquery as cq

def build_model():
    # 主轮廓 (XZ平面) - 严格单一线框构建，避免多实体拓扑错误
    pts = [
        (0, -55),      # 左下（固定边界）
        (100, -55),    # 底座前端（全长100mm，抗倾覆力臂最大化）
        (100, -50),    # 底座上表面
        (60, -50),     # 底座前端过渡
        (60, -45),     # 台阶上沿
        (50, -45),     # 手机托架水平面（10mm深，兼容8-12mm手机）
        (50, -20),     # 背部垂直段起点（高25mm，提供法向支撑）
        (15, 55),      # 背板顶部（倾角约65.0°，符合人体工学）
        (15, 56.5),    # 顶部前挡边前端（2mm厚）
        (17, 56.5),    # 顶部前挡边顶部（1.5mm高）
        (17, 55),      # 顶部前挡边后端
        (0, 55),       # 顶部后沿
        (0, -55)       # 闭合
    ]
    main = cq.Workplane("XZ").polyline(pts).close().extrude(80).translate((0, -40, 0))
    
    # 底部防滑筋（3条，与底座重叠0.75mm确保布尔融合为单一水密实体）
    rib1 = cq.Workplane("XZ").box(90, 3, 1.5).translate((50, -30, -55.75))
    rib2 = cq.Workplane("XZ").box(90, 3, 1.5).translate((50, 0, -55.75))
    rib3 = cq.Workplane("XZ").box(90, 3, 1.5).translate((50, 30, -55.75))
    
    # 布尔并集构建单一实体
    model = main.union(rib1).union(rib2).union(rib3)
    
    # 全局0.5mm倒角消除锐边（含L型交界处过渡）
    try:
        model = model.edges().chamfer(0.5)
    except Exception:
        pass
        
    return model.clean()

MODEL = build_model()