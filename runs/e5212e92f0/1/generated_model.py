import cadquery as cq

def build_model():
    """
    构建一个圆筒形笔筒，中间有隔板将空间一分为二。
    高度设定为100mm，外径80mm，内径74mm（壁厚3mm），隔板厚度2mm。
    """
    # 参数定义
    height = 100.0
    outer_radius = 40.0
    wall_thickness = 3.0
    inner_radius = outer_radius - wall_thickness
    separator_thickness = 2.0
    
    # 1. 创建空心圆柱体 (笔筒主体)
    # 使用 circle 生成面，然后 extrude 拉伸成实体
    # 先画外圆，再切掉内圆形成管状
    tube = (
        cq.Workplane("XY")
        .circle(outer_radius)
        .extrude(height)
        .faces(">Z")
        .workplane()
        .circle(inner_radius)
        .cutThruAll()
    )
    
    # 2. 创建中间隔板
    # 隔板是一个矩形板，长度等于内径直径，高度等于笔筒高度，厚度为 separator_thickness
    # 位置在圆心，沿 X 轴方向分割 Y 轴空间，或者沿 Y 轴分割 X 轴空间。这里选择沿 Y 轴放置，分割左右。
    separator = (
        cq.Workplane("XY")
        .box(2 * inner_radius, separator_thickness, height)
        .translate((0, 0, height / 2)) # 确保中心对齐，默认 box 中心在原点
    )
    
    # 3. 布尔运算：将隔板与笔筒主体合并
    # 注意：隔板必须完全嵌入笔筒内部，且与笔筒壁相交以形成封闭空间
    model = tube.union(separator)
    
    # 4. 可选：底部封底 (通常笔筒需要有底)
    # 上面的 cutThruAll 可能会把底也挖空，取决于实现。
    # 更稳健的做法是：
    # 1. 建立实心圆柱
    # 2. 挖去内部圆柱（保留底部或不保留）
    # 3. 插入隔板
    
    # 重新构建更稳健的几何逻辑：
    # 步骤 A: 创建带底的空心圆柱
    base_thickness = 3.0
    solid_cyl = cq.Workplane("XY").circle(outer_radius).extrude(height)
    inner_cut = cq.Workplane("XY").circle(inner_radius).extrude(height - base_thickness)
    tube_with_base = solid_cyl.cut(inner_cut.translate((0, 0, base_thickness)))
    
    # 步骤 B: 创建隔板
    # 隔板尺寸：宽 2*inner_radius, 厚 separator_thickness, 高 height - base_thickness (坐在底座上)
    # 为了让隔板稳固，它应该接触到底座
    sep_height = height - base_thickness
    separator_plate = (
        cq.Workplane("XY")
        .box(2 * inner_radius, separator_thickness, sep_height)
        .translate((0, 0, base_thickness + sep_height / 2))
    )
    
    # 步骤 C: 合并
    final_model = tube_with_base.union(separator_plate)
    
    return final_model

# 入口点
MODEL = build_model()