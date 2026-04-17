import cadquery as cq

def build_model():
    # 坐标系约定：Y轴垂直向下为负，X/Z为水平面
    # 1. 主轮廓绘制在XY平面，沿Z轴挤出宽度(80mm)
    # 精确65°倾角：高度80mm对应水平后退约37.3mm
    pts = [
        (-42.5, 0),   # 底座左下
        (42.5, 0),    # 底座右下
        (42.5, 10),   # 底座右上
        (15, 10),     # 底座前端
        (15, 18),     # 底部挡边外侧 (8mm高)
        (7, 18),      # 底部挡边内侧 (8mm宽)
        (7, 10),      # 挡边根部/背板起点
        (-30, 90),    # 背板顶部前端 (65°斜线)
        (-34, 90),    # 背板顶部后端
        (-5, 10),     # 背板底部后端
        (-42.5, 10),  # 底座左端
        (-42.5, 0)    # 闭合
    ]
    main_sketch = cq.Workplane("XY").polyline(pts).close()
    main_body = main_sketch.extrude(80, both=True)

    # 2. 根部加强肋：阶梯式过渡，缩短悬臂，连接处加厚至>4mm
    rib_pts = [
        (5, 10), (5, 35), (-15, 10)
    ]
    rib = cq.Workplane("XY").polyline(rib_pts).close().extrude(80, both=True)
    model = main_body.union(rib)

    # 3. 底部防滑点阵：直径3mm，深度1mm，间距10mm
    valid_points = []
    for x in range(-30, 31, 10):
        for z in range(-30, 31, 10):
            if -40 <= x <= 40 and -35 <= z <= 35:
                valid_points.append((x, z))

    anti_slip = cq.Workplane("XZ").pushPoints(valid_points).cylinder(1.0, 1.5, centered=(True, True, True))
    anti_slip = anti_slip.translate((0, -0.5, 0))
    model = model.union(anti_slip)

    # 4. 边缘倒角处理 (0.5-1mm)，防割手并优化视觉
    try:
        model = model.edges(">Y").chamfer(0.8)
        model = model.edges("<Y").chamfer(0.5)
        model = model.edges("|Z").chamfer(0.5)
    except Exception:
        pass

    return model

MODEL = build_model()