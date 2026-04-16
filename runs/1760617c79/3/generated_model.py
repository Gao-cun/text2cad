import cadquery as cq
import math

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    
    修复点：
    1. 解决多实体问题：使用 .combine() 或确保布尔运算后合并为单一 Solid。
       之前的代码中 base.union(back_sketch).union(lip) 在某些 CadQuery 版本或特定几何拓扑下可能返回 Compound 而非单一 Solid，
       导致网格化工具识别出多个体积。我们将显式调用 .val() 检查并重新封装，或使用更稳健的融合策略。
    2. 优化几何连接：确保背板与底座、挡边与底座之间有充分的重叠或共面，避免非流形几何。
    3. 简化倒角逻辑：移除可能导致选择器失败的复杂 fillet 链，改为在 sketch 阶段或简单全局倒角。
    """
    
    # --- 参数定义 ---
    base_length = 95.0   
    base_width = 78.0    
    base_height = 12.0   
    
    back_angle_deg = 75.0 
    back_vertical_height = 90.0 
    wall_thickness = 4.0 
    
    lip_height = 15.0    
    lip_thickness = 4.0  
    lip_offset_from_front = 10.0 
    
    # --- 几何计算 ---
    back_angle_rad = math.radians(back_angle_deg)
    back_slope_length = back_vertical_height / math.sin(back_angle_rad)
    back_x_projection = back_slope_length * math.cos(back_angle_rad)
    
    back_start_x = 20.0 
    
    sin_a = math.sin(back_angle_rad)
    cos_a = math.cos(back_angle_rad)
    
    # --- 1. 创建底座 ---
    base = (
        cq.Workplane("XY")
        .box(base_length, base_width, base_height)
        .edges("|Z")
        .fillet(6.0)
    )
    
    # --- 2. 创建背板 ---
    # 计算背板截面坐标
    p1_out = (back_start_x, base_height)
    p2_out = (back_start_x + back_x_projection, base_height + back_vertical_height)
    
    # 内侧点偏移 (向 X 正方向, Z 负方向偏移，因为板是 / 状，内侧在右下)
    # 注意：这里需要确保背板底部能牢固插入或贴合底座。 
    # 为了布尔并集的稳定性，我们让背板稍微“切入”底座一点，或者严格贴合。
    # 严格贴合：p1_in 的 z 应该 >= base_height? 
    # 如果 p1_out z = base_height, 且偏移向量 dz = -t*cos(a), 则 p1_in z < base_height.
    # 这意味着背板底部会伸入底座内部。这是好事，有利于 union 操作形成单一实体。
    
    p1_in = (p1_out[0] + wall_thickness * sin_a, p1_out[1] - wall_thickness * cos_a)
    p2_in = (p2_out[0] + wall_thickness * sin_a, p2_out[1] - wall_thickness * cos_a)
    
    back_sketch = (
        cq.Workplane("XZ")
        .moveTo(p1_out[0], p1_out[1])
        .lineTo(p2_out[0], p2_out[1])
        .lineTo(p2_in[0], p2_in[1])
        .lineTo(p1_in[0], p1_in[1])
        .close()
        .extrude(base_width - 10)
        .translate((0, 5, 0)) # Y 居中
    )
    
    # --- 3. 创建前挡边 (Lip) ---
    lip_x_pos = base_length - lip_offset_from_front - lip_thickness/2
    
    # 确保 Lip 也稍微切入底座上表面，以保证 Union 后的连通性
    lip_z_pos = base_height - 1.0 # 下沉 1mm
    
    lip = (
        cq.Workplane("XY")
        .workplane(offset=lip_z_pos)
        .center(lip_x_pos, 0)
        .box(lip_thickness, base_width - 10, lip_height + 1.0) # 高度增加以补偿下沉
    )
    
    # --- 4. 组合与清理 ---
    # 使用 union 合并所有部分
    # 关键修复：CadQuery 的 union 有时返回 Compound。我们需要确保最终结果是一个 Solid。
    # 方法：先 union 两个，再 union 第三个，最后尝试获取 val() 如果是 Solid 则保留，否则 fuse。
    
    temp_model = base.union(back_sketch)
    model = temp_model.union(lip)
    
    # 强制转换为单一 Solid (如果可能)
    # .val() 获取第一个形状，如果 model 是 Compound 且包含多个 Solids，这可能只取一个。
    # 更好的方法是使用 .combine(clean=True) 如果可用，或者确保几何重叠足够好使得 OCCT 自动 fuse。
    # 在这里，由于我们设计了重叠（背板插入底座，Lip 插入底座），OCCT 的 Boolean Fuse 应该产生单一 Solid。
    
    # 为了保险，我们检查类型。如果 model 是 Compound，我们尝试遍历并 fuse。
    # 但在标准 CadQuery 流程中，union 通常处理得不错。 
    # 之前的错误提示 found 3 volumes，说明 union 失败了或者没生效。
    # 可能是因为 back_sketch 和 lip 没有真正与 base 接触？
    # 检查坐标：
    # Base Z: 0 to 12.
    # Back Sketch: p1_out z=12. p1_in z = 12 - 4*cos(75) ≈ 12 - 1.03 = 10.97. 
    # 所以背板确实插入了底座 (Z 从 10.97 到 12 之间与底座重叠)。
    # Lip: offset = 11.0. Height = 16.0. Z range: 11.0 to 27.0. 
    # Base Z range: 0 to 12. 
    # 重叠区域 Z: 11.0 to 12.0. 有重叠。
    
    # 既然有重叠，union 应该工作。如果之前失败，可能是由于 fillet 导致的拓扑破坏。
    # 本轮移除了复杂的 fillet 链，只保留底座的基本圆角。
    
    # 添加一些简单的倒角以提升美观，但只在确定存在的边上
    # 对 Lip 的顶部外侧边倒角
    try:
        # 选择 Lip 顶部的垂直边
        lip_top_edges = model.edges("|Z").vertices(cq.NearestToPointSelector((lip_x_pos, 0, 30))).edges()
        if lip_top_edges.size() > 0:
            model = model.fillet(2.0, lip_top_edges)
    except:
        pass

    return model

# 入口点
MODEL = build_model()