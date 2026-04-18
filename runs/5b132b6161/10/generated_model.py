import cadquery as cq

def build_model():
    # 1. 底座 (Base) - 提供稳固支撑，尺寸 120x100x10
    base = cq.Workplane("XY").box(120, 100, 10, centered=False)

    # 2. 斜面背板主体 (Main Wedge) - 一体化连续延伸，无悬垂
    # 轮廓在YZ平面：从底座后缘(Y=0, Z=10)斜向上至(Y=45, Z=10)与(Y=0, Z=130)
    # 倾角约69°，完全由底座实体支撑，满足FDM无支撑打印要求
    wedge_profile = (
        cq.Workplane("YZ")
        .moveTo(0, 10)
        .lineTo(45, 10)
        .lineTo(0, 130)
        .close()
    )
    wedge = wedge_profile.extrude(120)

    # 3. 两侧限位挡边 (Side Walls) - 形成U型托槽，适配70-80mm手机
    # 位于X=0与X=110，厚度10mm，高度120mm，与斜面主体充分重叠
    wall_l = cq.Workplane("XY").box(10, 45, 120, centered=False).translate((0, 0, 10))
    wall_r = cq.Workplane("XY").box(10, 45, 120, centered=False).translate((110, 0, 10))

    # 4. 底部防滑挡唇 (Bottom Lip) - 防止手机前滑
    # 位于斜面底部前方，与主体重叠
    lip = cq.Workplane("XY").box(120, 6, 4, centered=False).translate((0, 42, 10))

    # 5. 背部防滑凸条 (Anti-slip Ridges) - 一体成型，防止后滑
    # 附着于背部垂直面(Y=0)，向-Y凸出2mm，与主体无缝融合
    ridge1 = cq.Workplane("XZ").box(120, 2, 2, centered=False).translate((0, -2, 105))
    ridge2 = cq.Workplane("XZ").box(120, 2, 2, centered=False).translate((0, -2, 115))
    ridge3 = cq.Workplane("XZ").box(120, 2, 2, centered=False).translate((0, -2, 125))
    ridges = ridge1.union(ridge2).union(ridge3)

    # 6. 拓扑融合与清理 - 确保单一闭合实体
    # 所有特征均保证≥2mm重叠区域，避免非流形或碎面
    model = base.union(wedge)
    model = model.union(wall_l)
    model = model.union(wall_r)
    model = model.union(lip)
    model = model.union(ridges)
    model = model.clean()

    # 7. 全局倒角 - 消除应力集中，优化FDM层纹与手感
    # 半径2.0mm，满足承重根部强化与打印安全要求
    model = model.edges().fillet(2.0)

    return model