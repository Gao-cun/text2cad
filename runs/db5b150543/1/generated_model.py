import cadquery as cq

def build_model():
    # 核心参数定义
    OD = 100.0
    HEIGHT = 150.0
    WALL_THICK = 3.0
    PARTITION_THICK = 3.0
    BOTTOM_THICK = 4.0
    TOP_FILLET_R = 1.5
    JUNCTION_FILLET_R = 2.0

    ID = OD - 2 * WALL_THICK
    INNER_HEIGHT = HEIGHT - BOTTOM_THICK

    # 1. 构建外圆柱实体
    outer_cyl = cq.Workplane("XY").circle(OD / 2).extrude(HEIGHT)

    # 2. 切除内部空腔（保留底部厚度）
    inner_void = cq.Workplane("XY").circle(ID / 2).extrude(INNER_HEIGHT)
    shell = outer_cyl.cut(inner_void)

    # 3. 创建垂直隔板
    partition = cq.Workplane("XY").box(PARTITION_THICK, ID, INNER_HEIGHT).translate((0, 0, BOTTOM_THICK))

    # 4. 布尔合并
    solid = shell.union(partition)

    # 5. 顶部边缘倒角（防割手 & 改善层纹）
    solid = solid.edges(">Z").fillet(TOP_FILLET_R)

    # 6. 隔板与筒壁连接处倒角（应力分散）
    # 选择平行于Z轴且非顶/底面的垂直边（即隔板四角与内壁交汇处）
    junc_edges = solid.edges("|Z and not >Z and not <Z")
    solid = junc_edges.fillet(JUNCTION_FILLET_R)

    return solid