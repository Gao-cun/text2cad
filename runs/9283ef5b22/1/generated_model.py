import cadquery as cq

def build_model():
    # 核心参数定义
    OD = 80.0          # 外径 (mm)
    WT = 3.0           # 壁厚 (mm)
    ID = OD - 2 * WT   # 内径 (mm)
    H = 150.0          # 总高度 (mm)
    DT = 3.0           # 隔板厚度 (mm)
    GAP = 5.0          # 顶部预留间隙 (mm)
    DIV_H = H - GAP    # 隔板实际高度 (mm)
    TOP_CHAMFER = 2.0  # 顶部外边缘倒角 (mm)
    JUNC_FILLET = 2.0  # 隔板与筒壁连接处圆角 (mm)

    z_min = -H / 2.0

    # 1. 构建空心圆柱筒体
    outer = cq.Workplane("XY", origin=(0, 0, z_min)).circle(OD / 2.0).extrude(H)
    inner = cq.Workplane("XY", origin=(0, 0, z_min)).circle(ID / 2.0).extrude(H)
    shell = outer.cut(inner)

    # 2. 构建垂直隔板 (沿X轴方向分割)
    divider = cq.Workplane("XY", origin=(0, 0, z_min)).rect(ID, DT).extrude(DIV_H)

    # 3. 布尔并集融合
    part = shell.union(divider)

    # 4. 连接处应力分散圆角
    # 选择所有平行于Z轴的垂直棱边（即隔板两侧与内壁的交界线）
    part = part.edges("|Z").fillet(JUNC_FILLET)

    # 5. 顶部外边缘倒角防割手
    # 选择Z坐标最大的顶面边缘进行倒角
    part = part.edges(">Z").chamfer(TOP_CHAMFER)

    return part