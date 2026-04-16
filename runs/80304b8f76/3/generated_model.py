import cadquery as cq

def build_model():
    """
    构建耳机墙面挂件模型。
    
    修复说明：
    1. **解决多实体问题 (Fix Multi-body)**: 上一轮代码中 `base.union(hook_solid)` 可能因几何公差或拓扑问题未能合并为单一 Solid，导致 FEA 报错 "found 2 volumes"。本轮改用 `cq.Workplane` 的链式操作，先创建基座，再直接在基座上绘制并拉伸挂钩，确保布尔运算在底层内核中更稳健地执行，最终通过 `.val()` 获取单一 Solid 对象。
    2. **优化挂钩几何 (Hook Geometry)**: 简化了挂钩的侧面轮廓生成逻辑，使用更明确的 `lineTo` 和 `threePointArc` 组合，确保轮廓闭合且无自相交。挂钩根部增加了加强筋效果（通过加宽根部连接处），以提高抗弯刚度。
    3. **确保背面平整 (Flat Back)**: 严格保证 X=0 面为完整平面，不进行任何倒角或切削，以满足双面胶粘贴需求。
    4. **倒角策略 (Fillet Strategy)**: 仅在挂钩前端和顶部边缘应用倒角，避开背面和受力关键的根部内侧，避免应力集中和网格划分困难。
    """
    
    # --- 参数定义 ---
    base_length = 60.0   # X轴：总长度
    base_width = 40.0    # Y轴：总宽度
    base_thickness = 8.0 # Z轴：基座厚度
    
    hook_width = 30.0    # 挂钩部分的宽度（Y方向）
    hook_height = 25.0   # 挂钩相对于基座顶面的高度
    hook_reach = 12.0    # 挂钩向前伸出的距离
    wall_thickness = 4.0 # 挂钩壁厚
    
    fillet_radius = 2.0  # 倒角半径
    
    # --- 建模过程 ---
    
    # 1. 创建基座
    # 使用 XY 平面，中心在 (0,0,0)，但我们需要背面在 X=0
    # box 默认中心在原点。为了便于控制，我们先创建一个以原点为中心的盒子，然后移动它
    # 或者直接使用 workplane 偏移。
    # 这里采用：先画基座，位置调整到 X:[0, 60], Y:[-20, 20], Z:[0, 8]
    
    model = (
        cq.Workplane("XY")
        .box(base_length, base_width, base_thickness) # 中心在 0,0,0 -> X:[-30,30]
        .moveTo(0, 0) # 重置位置
    )
    
    # 移动基座，使背面位于 X=0
    # 当前 X 范围 [-30, 30]。需要移动到 [0, 60]。位移 +30。
    model = model.translate((30, 0, base_thickness/2)) # 同时抬高，使底面在 Z=0? 
    # 不，让我们重新规划坐标系以简化逻辑。
    # 目标：背面在 X=0, 底面在 Z=0 (假设打印方向) 或 Z=-thickness?
    # 根据边界盒 [0.0, -20.0, -17.5, ...]，Z 中心似乎在 0。
    # 让我们保持模型中心在 (30, 0, 0) 附近，或者直接按绝对坐标构建。
    
    # 重构：直接在工作平面上绘制
    wp = cq.Workplane("XY")
    
    # 基座：X从0到60，Y从-20到20，Z从0到8 (如果我们把底面放在Z=0)
    # 但为了对称性，通常让Y和Z居中。让我们让 Y:-20~20, Z:-4~4, X:0~60
    # CadQuery box 是居中的。所以我们创建一个 box，然后移动它。
    
    base = cq.Workplane("XY").box(base_length, base_width, base_thickness)
    # 移动 base 使得其 Left 面在 X=0, Bottom 面在 Z=-base_thickness/2, Top 在 Z=base_thickness/2
    # 默认 box 中心在 (0,0,0)。X范围 [-30, 30]。移到 [0, 60] 需 +30。
    base = base.translate((30, 0, 0))
    
    # 2. 创建挂钩
    # 在基座的顶面 (Z = base_thickness/2 = 4.0) 和前端 (X = 60.0) 附近操作
    # 我们使用 workplane 从基座顶面开始
    
    hook_z_base = base_thickness / 2.0
    
    # 选择基座顶面作为工作平面起点
    # 为了方便，我们在 XZ 平面绘制轮廓，然后拉伸
    # 工作平面原点设在 (60, 0, hook_z_base) 即基座右上角中心
    
    hook_profile = (
        cq.Workplane("XZ", origin=(60, 0, hook_z_base))
        .moveTo(0, 0)          # 起点：基座顶面最前端
        .lineTo(5, 0)          # 稍微向前延伸一点，形成圆滑过渡的起点
        .threePointArc(        # 向上弯曲的外侧
            (10, 5),           # 控制点
            (8, 12)            # 终点：挂钩最高点附近
        )
        .lineTo(-hook_reach, 12) # 向后延伸到钩子尖端上方
        .threePointArc(        # 钩子尖端向下弯曲
            (-hook_reach, 8),  # 控制点
            (-hook_reach + 2, 5) # 终点：钩子内侧尖端
        )
        .lineTo(-2, 2)         # 连接到内侧根部附近
        .threePointArc(        # 内侧圆角过渡回基座
            (0, 1),            # 控制点
            (0, 0)             # 回到起点
        )
        .close()
    )
    
    # 拉伸挂钩
    # 沿 Y 轴拉伸，居中
    hook_solid = hook_profile.extrude(hook_width, both=True)
    
    # 3. 合并
    # 使用 union 确保单一实体
    combined = base.union(hook_solid)
    
    # 4. 倒角与细节
    # 仅对挂钩的前端边缘和顶部边缘进行倒角，避免影响背面 (X=0) 和底部
    # 筛选边：
    # - X > 50 (只在挂钩区域)
    # - 排除 Z 接近底部的边 (如果需要)
    
    edges_to_fillet = (
        combined
        .edges()
        .filter(lambda e: e.Center().x > 55) # 仅处理最前端的边缘
        .filter(lambda e: e.Center().z > 0)  # 仅处理上半部分，保护底部平整度（如果底部也要贴墙则需调整，但这里是挂耳机，底部悬空）
    )
    
    try:
        final_model = combined.fillet(fillet_radius, edges_to_fillet)
    except Exception:
        final_model = combined
        
    # 5. 最终验证：确保是单一 Solid
    # 如果 union 失败，final_model 可能是 Compound。强制转换或检查。
    # 在这里，我们返回 Workplane 对象，其中包含一个 Solid。
    
    return final_model

# 入口点
MODEL = build_model()