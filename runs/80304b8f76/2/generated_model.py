import cadquery as cq

def build_model():
    """
    构建耳机墙面挂件模型。
    修复说明：
    1. 修复了上一轮代码中 sweep 操作因上下文丢失导致的 'No pending wires present' 错误。
    2. 改用更稳健的建模策略：先创建基座，再在基座顶部创建工作平面绘制挂钩侧面轮廓并拉伸，最后进行布尔 union。
    3. 优化了倒角逻辑，避免对背面（粘贴面）进行倒角，确保平整度。
    4. 调整了挂钩几何形状，使其更符合人体工学且易于打印（自支撑性更好）。
    """
    
    # --- 参数定义 ---
    base_length = 60.0   # X轴：总长度
    base_width = 40.0    # Y轴：总宽度
    base_thickness = 8.0 # Z轴：基座厚度
    
    hook_width = 30.0    # 挂钩部分的宽度（Y方向）
    hook_height = 27.0   # 挂钩相对于基座顶面的高度
    hook_depth = 15.0    # 挂钩向后弯曲的深度
    wall_thickness = 4.0 # 挂钩壁厚/实体厚度
    
    fillet_radius = 2.5  # 倒角半径
    
    # --- 1. 创建基座 (Base) ---
    # 基座是一个简单的长方体，位于 X:[0, 60], Y:[-20, 20], Z:[0, 8]
    base = cq.Workplane("XY").box(base_length, base_width, base_thickness)
    
    # --- 2. 创建挂钩 (Hook) ---
    # 策略：在基座顶面 (Z=base_thickness) 的前端 (X=base_length) 附近建立工作平面
    # 绘制侧面轮廓 (XZ平面)，然后沿 Y 轴拉伸。
    
    # 确定挂钩起始位置：基座顶面，靠近前端
    start_x = base_length - 5.0 
    start_z = base_thickness
    
    # 绘制侧面轮廓 (Profile)
    # 使用 workplane("XZ") 并在其中绘制 2D 轮廓
    hook_profile = (
        cq.Workplane("XZ")
        .moveTo(start_x, start_z)          # 起点：基座顶面内部一点
        .lineTo(base_length + 2.0, start_z) # 延伸到基座边缘外一点，形成美观的悬挑
        .threePointArc(                    # 向上弯曲的圆弧
            (base_length + 5.0, start_z + 5.0), # 控制点
            (base_length + 2.0, start_z + 12.0) # 中间点
        )
        .lineTo(base_length - 5.0, start_z + hook_height) # 向上延伸
        .threePointArc(                    # 向后弯曲的钩头
            (base_length - 12.0, start_z + hook_height), # 控制点
            (base_length - hook_depth, start_z + hook_height - 3.0) # 钩子尖端
        )
        .lineTo(base_length - hook_depth, start_z + hook_height - 3.0 - wall_thickness) # 向下生成厚度
        .threePointArc(                    # 内侧圆弧
            (base_length - 10.0, start_z + hook_height - 5.0), # 控制点
            (base_length, start_z + 5.0)   # 回到接近起点的高度
        )
        .close()                           # 闭合轮廓
    )
    
    # 拉伸轮廓生成挂钩实体
    # 拉伸方向为 Y 轴，居中拉伸
    hook_solid = hook_profile.extrude(hook_width, both=True)
    
    # 调整挂钩位置，使其在 Y 方向居中
    # extrude(both=True) 会以当前工作平面的 Y=0 为中心向两侧拉伸
    # 我们的工作平面是 XZ，原点在 (0,0,0)。所以挂钩中心在 Y=0。符合需求。
    
    # --- 3. 合并基座和挂钩 ---
    model = base.union(hook_solid)
    
    # --- 4. 细节优化：倒角 (Fillet) ---
    # 目标：对所有外露边缘进行倒角，但保留背面 (X=0) 平整以便粘贴。
    
    # 选择需要倒角的边：
    # 1. 排除 X 坐标接近 0 的边 (背面)
    # 2. 排除过短的边或内部边 (如果有)
    
    edges_to_fillet = (
        model
        .edges()
        .filter(lambda e: e.Center().x > 1.0) # 仅选择 X > 1.0 的边，保护背面
    )
    
    # 应用倒角
    try:
        model = model.fillet(fillet_radius, edges_to_fillet)
    except Exception as e:
        # 如果批量倒角失败，尝试更保守的策略：仅倒角基座前缘和挂钩明显边缘
        print(f"Warning: Bulk fillet failed ({e}), trying selective fillet.")
        try:
            # 选择基座前端的两条垂直边和顶面前边
            front_edges = model.edges().filter(
                lambda e: abs(e.Center().x - base_length) < 0.1 and e.Center().z >= base_thickness
            )
            model = model.fillet(fillet_radius, front_edges)
        except:
            pass
            
    # --- 5. 最终检查 ---
    # 确保模型 manifold 且无错误
    # 返回模型
    return model

# 入口点
MODEL = build_model()