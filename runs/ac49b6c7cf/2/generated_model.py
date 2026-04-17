import cadquery as cq

def build_model():
    # 主轮廓：底座 + 手机前挡边 + 65°倾斜背板
    # 背板倾角精确计算：tan(65°)≈2.1445，高度88mm对应水平投影41mm
    main_profile = [
        (0, 0), (100, 0), (100, 12),
        (92, 12), (92, 22), (86, 22), (86, 12), # 前挡边（限位手机）
        (76, 12), (35, 100), (25, 100), (25, 12), # 65°背板（顶部缩短至100mm降低悬臂）
        (0, 12), (0, 0)
    ]
    main_body = cq.Workplane("XY").polyline(main_profile).close().extrude(80, both=True)

    # 三角加强肋：位于背板根部，提升抗弯刚度，倾角>45°满足免支撑打印
    rib_profile = [
        (68, 12), (50, 62), (40, 62), (40, 12)
    ]
    rib = cq.Workplane("XY").polyline(rib_profile).close().extrude(80, both=True)

    # 合并几何体
    model = main_body.union(rib)

    # 边缘倒角处理 (0.5-1mm)，防割手并优化视觉
    model = model.edges(">Y").chamfer(0.8)
    model = model.edges("<Y").chamfer(0.5)
    model = model.edges("|Z").chamfer(0.5)

    # 平移至Y轴中心，适配固定/加载边界盒范围
    model = model.translate((0, -50, 0))

    return model

MODEL = build_model()