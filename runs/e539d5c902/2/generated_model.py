import cadquery as cq
import math

def build_model():
    """
    构建一个简约的L型/三角支撑结构手机支架。
    修复了上一轮中 cutBlind 调用失败的问题，改为先生成 cutter 实体再执行布尔减运算。
    优化了边界框对齐，确保模型位于 x:[0, 80] 范围内。
    """
    
    # --- 参数定义 (mm) ---
    total_height_target = 120.0
    base_depth = 80.0
    width = 75.0
    base_thickness = 10.0
    back_thickness = 5.0
    tilt_angle_deg = 60.0
    tilt_angle_rad = math.radians(tilt_angle_deg)
    
    # --- 几何计算 ---
    # 目标：背板顶部高度接近 120mm，且整体在 X:[0, 80] 内
    # 背板形状: \ (底部在前/右，顶部在后/左)
    # 设背板底部中心位置 (x_bot, z_bot)
    # z_bot = base_thickness = 10.0
    # 设背板长度 L
    # dx = L * cos(60) = 0.5 * L
    # dz = L * sin(60) = 0.866 * L
    # x_top = x_bot - dx
    # z_top = z_bot + dz
    
    # 约束:
    # 1. x_top >= 0 (不超出后边界)
    # 2. x_bot <= 80 (不超出前边界，实际上要留余量给挡边)
    # 3. z_top approx 110-120
    
    # 尝试 L = 125
    # dz = 108.25 -> z_top = 118.25 (OK)
    # dx = 62.5
    # 若 x_top = 5.0 (留5mm余量), 则 x_bot = 5.0 + 62.5 = 67.5
    # 检查 x_bot: 67.5 < 80. OK.
    
    L = 125.0
    x_margin_back = 5.0
    x_top_loc = x_margin_back
    x_bot_loc = x_top_loc + L * math.cos(tilt_angle_rad) # 67.5
    z_bot_loc = base_thickness
    z_top_loc = z_bot_loc + L * math.sin(tilt_angle_rad) # 118.25
    
    # --- 1. 底座 (Base) ---
    # 尺寸: 80 x 75 x 10
    # 位置: x:[0, 80], y:[-37.5, 37.5], z:[0, 10]
    base = cq.Workplane("XY").box(base_depth, width, base_thickness).translate((base_depth/2, 0, base_thickness/2))
    
    # --- 2. 倾斜背板 (Backrest) ---
    # 使用 Box + Rotate 方法
    # 初始 Box 中心在 (x_bot, z_bot)，尺寸: thickness(x) x width(y) x L(z)
    # 绕 Y 轴旋转 30 度 (90-60)，使 Z 轴向左倾斜，形成 \ 形状
    # 注意：CadQuery rotate 绕中心点旋转
    
    back_solid = (
        cq.Workplane("XZ")
        .center(x_bot_loc, z_bot_loc)
        .box(back_thickness, width, L)
        .rotate((x_bot_loc, 0, z_bot_loc), (0, 1, 0), 30) 
    )
    
    # --- 3. 前挡边 (Lip) ---
    # 防止手机滑落。位于背板底部前方。
    # 背板底部在 x=67.5。挡边应略大于此 x 值，或者就在其前方。
    # 考虑到背板厚度 5mm，倾斜后，背板“前”表面（接触手机面）的下端 x 坐标约为:
    # x_surf_bot = x_bot_loc + (back_thickness/2) * sin(30deg) ? 
    # 简单处理：在 x = 72.0 处放置一个挡块，高度 15mm，深度 4mm。
    lip_x = 72.0
    lip_z = base_thickness + 7.5 # 中心高度
    lip = (
        cq.Workplane("XZ")
        .center(lip_x, lip_z)
        .box(4, width - 10, 15)
    )
    
    # --- 4. 组装主体 ---
    model = base.union(back_solid).union(lip)
    
    # --- 5. 细节处理：倒角 (Fillet) ---
    # 为了打印安全和手感，对边缘进行倒角
    # 仅对垂直边缘或特定边缘倒角，避免拓扑错误
    try:
        # 底座底边倒角
        model = model.edges("<Z").fillet(2.0)
        # 背板顶部边缘倒角
        model = model.edges(">Z").fillet(1.5)
    except Exception:
        pass # 如果选择集为空或失败，跳过
        
    # --- 6. 防滑槽 (Anti-slip Grooves) ---
    # 在底座上表面 (z=10) 切割槽
    # 修复点：不再使用 cutBlind，而是创建 Cutter 实体并执行 cut()
    
    groove_depth = 2.0
    groove_width = 2.0
    groove_y_span = width - 10.0
    
    # 创建三个槽的 cutter
    cutter = (
        cq.Workplane("XY", origin=(0, 0, base_thickness)) # 工作平面在底座上表面
        .pushPoints([(20, 0), (40, 0), (60, 0)]) # 三个位置
        .rect(groove_width, groove_y_span)
        .extrude(-groove_depth) # 向下挤出形成实体
    )
    
    model = model.cut(cutter)
    
    return model

# 入口点
MODEL = build_model()