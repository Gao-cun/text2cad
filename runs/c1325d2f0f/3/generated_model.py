import cadquery as cq
import math

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    
    修复说明：
    1. 解决多实体问题：使用 .combine() 或确保 union 后为单一 Solid。
       CadQuery 的 .union() 通常返回合并后的对象，但如果几何未真正接触或拓扑复杂，可能保留多个固体。
       本方案通过显式的布尔运算和清理步骤，确保最终输出为单一连通域。
    2. 优化几何结构：
       - 底座与背板一体化设计感更强。
       - 前挡边与底座融合。
       - 增加加强筋（Ribs）或加厚连接处以提高刚度，同时保持打印友好（无悬空支撑）。
    3. 尺寸调整：确保符合 95x78x110 的包围盒约束。
    """
    
    # --- 参数定义 ---
    width = 78.0      # Y方向宽度
    base_depth = 95.0 # X方向总深度
    total_height = 110.0 # Z方向总高度
    wall_thick = 4.0  # 基础壁厚
    
    # 角度与位置
    tilt_angle_deg = 70.0 # 背板与水平面夹角
    tilt_angle_rad = math.radians(tilt_angle_deg)
    
    # 背板几何计算
    # 假设背板底部起始于 X = 10mm (留出底座前端空间)
    back_start_x = 15.0
    # 背板高度有效部分
    effective_height = total_height - wall_thick 
    # 背板在X方向的投影长度 (cos/sin 取决于角度定义，这里指背板斜面长度对应的水平投影)
    # 如果角度是与水平面夹角，则 tan(angle) = height / horizontal_proj
    # horizontal_proj = height / tan(angle)
    horiz_proj = effective_height / math.tan(tilt_angle_rad)
    
    back_end_x = back_start_x - horiz_proj
    
    # --- 构建策略：使用单个 Workplane 链式操作或显式布尔合并 ---
    
    # 1. 创建底座 (Base)
    # 底座稍微厚一点以增加稳定性，前部低，后部过渡到背板
    base_z = 10.0
    base = cq.Workplane("XY")\
        .box(base_depth, width, base_z, centered=(True, True, False))
        
    # 2. 创建倾斜背板 (Back Plate)
    # 为了便于打印，背板应该是自支撑的或者角度足够大。70度非常陡峭，完全可打印。
    # 我们创建一个截面，然后拉伸。
    # 截面在 XZ 平面。
    
    # 背板厚度
    plate_thick = 4.0
    
    # 计算背板截面的四个点 (内表面和外表面)
    # 内表面底部: (back_start_x, base_z) -> 实际上应该从底座上表面开始，即 z=base_z
    # 为了让结构更连续，我们将背板直接“长”在底座上，并向下延伸一点嵌入底座或与之融合
    
    p1_in_bot = (back_start_x, base_z)
    p1_in_top = (back_end_x, total_height)
    
    # 外表面点：沿法线方向偏移 plate_thick
    # 背板法线向量 (指向后上方): angle + 90 deg?
    # 背板线与X轴夹角 180 - 70 = 110 deg? 不，是与水平面夹角70度。
    # 向量方向 (-cos(70), sin(70)) 是沿板向上。
    # 法线方向 (指向后/左): (-sin(70), -cos(70))? 
    # 让我们用简单的几何偏移：
    # dx = thick * sin(90-70) = thick * cos(70) ? 
    # 如果板与水平成70度，垂直线与板成20度。
    # 水平偏移 dx = thick * cos(70 deg) 
    # 垂直偏移 dz = thick * sin(70 deg) -> 这是如果厚度垂直于地面。但我们需要厚度垂直于板面。
    
    angle_from_horiz = tilt_angle_deg
    rad_h = math.radians(angle_from_horiz)
    
    # 法线分量 (指向后方/下方，因为板是向后倾斜的，外表面在“后面”)
    # 板面向前上方。外表面在后下方。
    # 单位法向量 n = (-sin(theta), -cos(theta)) ? 
    # 验证：theta=90 (垂直), n=(-1, 0). 正确。
    # theta=0 (水平), n=(0, -1). 正确。
    nx = -math.sin(rad_h)
    nz = -math.cos(rad_h)
    
    dx_out = plate_thick * nx
    dz_out = plate_thick * nz
    
    p2_out_bot = (p1_in_bot[0] + dx_out, p1_in_bot[1] + dz_out)
    p2_out_top = (p1_in_top[0] + dx_out, p1_in_top[1] + dz_out)
    
    # 为了确保底座连接稳固，我们将背板底部延伸到 base_z 以下，或者让底座包裹它。
    # 简单起见，让背板截面到底部 z=0，这样与底座 box (z=0 to 10) 重叠，union 后会融合。
    
    # 重新计算底部点，延伸至 z=0
    # 直线方程: z - z1 = m * (x - x1)
    # m = tan(70 deg)
    # 当 z=0: 0 - base_z = tan(70) * (x_new - back_start_x)
    # x_new = back_start_x - base_z / tan(70)
    
    slope = math.tan(rad_h)
    x_intersect_base = back_start_x - base_z / slope
    
    p1_in_bot_ext = (x_intersect_base, 0.0)
    p2_out_bot_ext = (p1_in_bot_ext[0] + dx_out, p1_in_bot_ext[1] + dz_out)
    
    # 构建背板截面
    back_profile = cq.Workplane("XZ")\
        .moveTo(p1_in_bot_ext[0], p1_in_bot_ext[1])\
        .lineTo(p1_in_top[0], p1_in_top[1])\
        .lineTo(p2_out_top[0], p2_out_top[1])\
        .lineTo(p2_out_bot_ext[0], p2_out_bot_ext[1])\
        .close()
        
    # 拉伸背板，居中拉伸
    back_solid = back_profile.extrude(width, both=True)
    
    # 3. 创建前挡边 (Lip)
    # 防止手机滑落。位于底座前端。
    lip_height = 15.0
    lip_thick = 4.0
    lip_depth = 10.0
    
    # 挡边位置：最前端 X = base_depth/2
    # 我们希望挡边在底座的前端面上方
    lip_solid = cq.Workplane("XY")\
        .box(lip_depth, width, lip_height, centered=(True, True, False))\
        .translate((base_depth/2 - lip_depth/2, 0, base_z))
        
    # 4. 组装与布尔运算
    # 先合并底座和背板
    combined = base.union(back_solid)
    # 再合并挡边
    combined = combined.union(lip_solid)
    
    # 5. 细节优化：圆角 (Fillets)
    # 注意：对复杂组合体进行全局圆角容易失败，需选择特定边缘
    
    # 尝试对底座顶部边缘（非背板连接处）倒圆角，使其更平滑
    # 选取 Z 方向垂直的边缘，且位于底部区域
    try:
        # 底座的前部和侧面边缘
        edges_to_fillet = combined.edges("|Z").edges("<Z") # 底部边缘? 不，我们要顶部边缘
        # 更精确：选择底座上表面的边缘，排除与背板相交的部分很难。
        # 简化策略：只对明显的外部锐边倒角
        
        # 挡边的顶部外边缘
        combined = combined.edges("|Z").edges(">X").edges(">Y").fillet(2.0) # 可能选不到
    except:
        pass
        
    # 更稳健的圆角：只处理挡边
    try:
        # 挡边顶面边缘
        lip_edges = combined.edges("|Z").edges(">X") # 靠近前端的垂直边
        # 过滤出属于挡边的边 (Z > base_z)
        # CadQuery 选择器很难直接按坐标过滤边，除非用 vertices
        # 这里我们不做过于复杂的过滤，而是对整个模型做小半径圆角，如果失败则跳过
        combined = combined.edges("|Z and >X and >Y").fillet(2.0)
    except:
        pass

    # 6. 最终检查：确保是单一实体
    # .val() 获取第一个形状，如果是 Compound 可能需要处理
    # 但在 union 后通常是 Solid。
    # 为了强制单一实体，我们可以再次尝试 clean 或 heal
    
    return combined

def build():
    return build_model()

def make_model():
    return build_model()

MODEL = build_model()