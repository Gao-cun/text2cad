import cadquery as cq

def build_model():
    # 主轮廓 (XZ平面)，严格闭合，避免自交与非流形拓扑
    pts = [
        (0, -55),    # 底座左下
        (100, -55),  # 底座右下 (总长100)
        (100, -45),  # 底座右上
        (20, -45),   # 斜面起点
        (67, 55),    # 斜面顶点 (倾角约65°)
        (67, 56.5),  # 顶部挡边外顶
        (65, 56.5),  # 顶部挡边内顶
        (65, 55),    # 顶部挡边内底
        (10, -30),   # 背部斜面底端
        (10, -55),   # 背部垂直墙底端
        (0, -55),    # 闭合
    ]
    main = cq.Workplane("XZ").polyline(pts).close().extrude(80).translate((0, -40, 0))
    
    # 先对主体进行安全倒角，避免合并后拓扑复杂化引发网格错误
    main = main.edges().chamfer(0.5)

    # 背部三角加强筋 (厚度2mm，居中布置)
    rib_pts = [(10, -30), (10, -45), (20, -45)]
    rib = cq.Workplane("XZ").polyline(rib_pts).close().extrude(2).translate((0, -1, 0))

    # 底部后挡块 (10x5mm，防滑抗倾覆)
    stop = cq.Workplane("XZ").rect(10, 5).extrude(80).translate((0, -40, -56.0))

    # 合并几何并清理内部面
    model = main.union(rib).union(stop).clean()
    
    return model

MODEL = build_model()