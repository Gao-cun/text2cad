import cadquery as cq

def build_model():
    # 1. 底座与背部斜面一体化轮廓 (XZ平面)
    # 调整顶部高度至125mm以贴近目标尺寸，保持约60度倾角
    prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(120, 0)
        .lineTo(120, 10)
        .lineTo(85, 10)
        .lineTo(20, 125)
        .lineTo(0, 125)
        .close()
    )
    # 沿Y轴拉伸100mm形成主体
    main_body = prof.extrude(100)

    # 2. 安全倒角处理 (在布尔切割前进行，避免内部拓扑奇异)
    # 移除导致崩溃的 |Y 选择器，仅对可见外轮廓边缘施加2.0mm倒角
    main_body = main_body.edges(">Z").fillet(2.0)
    main_body = main_body.edges("<Z").fillet(2.0)
    main_body = main_body.edges(">X").fillet(2.0)
    main_body = main_body.edges("<X").fillet(2.0)

    # 3. 底部手机限位挡边 (Lip)
    lip = cq.Workplane("XY").box(25, 100, 6, centered=(False, False, False)).translate((85, 0, 10))
    model = main_body.union(lip)

    # 4. 切割U型手机托槽 (Cut U-Channel)
    # 保留两侧10mm侧壁，中间80mm宽度，深度贯穿
    cut_block = cq.Workplane("XY").box(100, 80, 125, centered=(False, False, False)).translate((10, 10, 0))
    model = model.cut(cut_block)

    # 5. 背部防滑凸条 (Anti-slip Ridges)
    # 沿斜面分布，宽度略小于托槽(76mm)以避免布尔运算干涉
    for z in [40, 70, 100]:
        x_pos = 85 - (65 / 115) * (z - 10)
        ridge = cq.Workplane("XY").box(2, 76, 2, centered=(False, False, False)).translate((x_pos - 1, 12, z - 1))
        model = model.union(ridge)

    # 6. 几何清理
    model = model.clean()
    return model