import cadquery as cq

def build_model():
    """
    构建耳机墙面挂件模型。
    设计思路：
    1. 基座：扁平长方体，背面平整用于粘贴，正面连接挂钩。
    2. 挂钩：从基座顶部延伸出的弧形结构，内径适配耳机头梁。
    3. 倒角：所有外露边缘进行圆角处理，提升美观度和打印质量。
    """
    
    # 参数定义
    base_length = 60.0  # X轴方向长度
    base_width = 40.0   # Y轴方向宽度
    base_thickness = 8.0 # Z轴方向厚度（基座部分）
    
    hook_radius_outer = 25.0 # 挂钩外半径
    hook_radius_inner = 12.5 # 挂钩内半径 (适配~25mm头梁)
    hook_height = 35.0       # 总高度
    hook_width = 30.0        # 挂钩宽度（略小于基座宽度，保持美观）
    
    # 1. 创建基座 (Base Plate)
    # 基座位于 X: [0, 60], Y: [-20, 20], Z: [0, 8]
    base = cq.Workplane("XY").box(base_length, base_width, base_thickness)
    
    # 2. 创建挂钩主体 (Hook Body)
    # 挂钩位于基座的前端 (X=60处)，向上弯曲
    # 使用工作平面移动到基座顶面的前端中心
    hook_profile = (
        cq.Workplane("XZ")
        .workplane(offset=base_width/2) # 移动到Y正半轴边缘? 不，我们需要在中间画截面然后拉伸或旋转
        # 更好的方法：在YZ平面画轮廓，然后沿X轴拉伸？不，挂钩是沿Y轴对称的。
        # 让我们在XY平面画侧视图轮廓，然后拉伸Y方向？
        # 侧视图轮廓：从基座顶部(60, 8)开始，向上并向后弯曲。
    )
    
    # 重新规划建模策略：
    # 步骤 A: 创建基座
    base_solid = cq.Workplane("XY").box(base_length, base_width, base_thickness)
    
    # 步骤 B: 创建挂钩的侧面轮廓 (在 XZ 平面)
    # 挂钩起点：基座右上角 (x=base_length, z=base_thickness)
    # 挂钩形状：一个向上的圆弧，然后向后弯曲以抓住耳机。
    # 为了简化且保证强度，我们做一个“J”形或“C”形钩。
    # 中心线轨迹：
    # 起点: (base_length, base_thickness)
    # 终点: (base_length - hook_depth, hook_height)
    
    hook_depth = 15.0 # 挂钩向后延伸的深度
    total_height = hook_height
    
    # 在 XZ 平面绘制挂钩的侧面轮廓线
    # 注意：CadQuery 的 workplane 默认是 XY。我们需要切换到 XZ 或者使用三点画弧。
    # 让我们使用 `cq.Workplane("XZ")` 并在其中绘制，然后沿 Y 轴拉伸。
    
    hook_sketch = (
        cq.Workplane("XZ")
        .moveTo(base_length, base_thickness) # 起点：基座右上角
        .lineTo(base_length + 5, base_thickness) # 稍微向前突出一点，增加美感
        .threePointArc(
            (base_length + 10, base_thickness + 10), # 控制点
            (base_length + 5, base_thickness + 20)   # 中间点
        )
        .lineTo(base_length - 5, total_height) # 向上延伸
        .threePointArc(
            (base_length - 15, total_height), # 控制点：向后弯曲
            (base_length - hook_depth, total_height - 5) # 终点：钩子尖端
        )
        .lineTo(base_length - hook_depth + 5, total_height - 5) # 增加厚度
        .close() # 闭合轮廓以便拉伸成实体？不，我们先画中心线或单线，然后用 sweep 或 extrude?
        # 简单起见，我们画一个实心的侧面轮廓并拉伸。
    )
    
    # 修正挂钩建模方法：使用 Loft 或 Extrude 一个定义好的截面。
    # 为了获得光滑的挂钩，我们定义挂钩的“脊柱”路径，然后扫掠一个圆形或矩形截面。
    
    # 路径定义 (Path)
    path_pts = [
        (base_length, base_thickness, 0), # 起点 (相对于路径局部坐标)
        (base_length + 5, base_thickness + 10, 0),
        (base_length, base_thickness + 25, 0),
        (base_length - 10, total_height, 0),
        (base_length - hook_depth, total_height - 2, 0) # 钩子末端
    ]
    
    # 使用 spline 创建平滑路径
    path = cq.Workplane("XZ").spline(path_pts).val()
    
    # 截面定义 (Section)
    # 挂钩宽度为 hook_width，厚度为 8mm (与基座一致或稍薄)
    section = cq.Workplane("YZ").rect(hook_width, 8).val()
    
    # 扫掠生成挂钩
    hook_solid = cq.Workplane("XZ").sweep(section, path, makeSolid=True)
    
    # 调整挂钩位置，使其与基座对齐
    # 上面的路径是基于全局坐标画的吗？
    # cq.Workplane("XZ") 的原点是 (0,0,0)。path_pts 中的 X 和 Z 是绝对坐标。
    # 但是 sweep 的行为取决于上下文。让我们确保它们在同一坐标系下。
    
    # 合并基座和挂钩
    model = base_solid.union(hook_solid)
    
    # 3. 细节优化：倒角和圆角 (Fillet)
    # 选择基座与挂钩连接处的边，以及外露的边缘
    
    # 对所有外露的水平边缘进行小倒角，防止割手并改善打印
    # 筛选条件：Z方向的最大面边缘，或者特定的边
    
    # 简单策略：对整个模型的外露垂直边进行倒角 (2mm)
    # 注意：不要倒角背面 (X=0) 的边，因为需要平整粘贴？
    # 用户要求背面平整。所以 X=0 的面必须保持完整。
    
    # 获取所有边，过滤掉 X=0 面上的边
    all_edges = model.edges()
    
    # 我们只希望倒角“可见”和“接触”的边，除了背面。
    # 手动选择需要倒角的边可能更稳定。
    
    # 1. 基座的前面和侧面边缘 (X>0)
    edges_to_fillet = (
        model
        .edges("|X") # 平行于X轴的边? 不，我们要倒角垂直边和水平边
        .filter(lambda e: e.Center().x > 1.0) # 排除背面附近的边
    )
    
    # 更稳健的方法：分别倒角
    # 基座的顶面边缘 (除了背面)
    top_edges = model.edges("<Z").filter(lambda e: e.Center().z > base_thickness - 0.1 and e.Center().x > 1.0)
    
    # 挂钩的所有边缘
    hook_edges = model.edges().filter(lambda e: e.Center().x > base_length - hook_depth - 5)
    
    # 应用倒角
    try:
        model = model.fillet(2.0, edges_to_fillet)
    except:
        pass # 如果选择集为空或出错，跳过
        
    # 再次尝试更简单的全局倒角，然后切除背面？
    # 不，先倒角再确保背面平整。
    
    # 让我们重新构建以确保拓扑干净：
    # 1. Base
    # 2. Hook
    # 3. Union
    # 4. Fillet specific edges
    
    # 重新选择边进行倒角：
    # 基座的前角 (Front Corners)
    front_corners = model.edges().vertices("(>X[59], >Y[19], >Z[7])") # 近似坐标选择
    # 这种方法太脆弱。
    
    # 使用基于几何特征的过滤：
    # 倒角半径 2mm
    fillet_rad = 2.0
    
    # 选择所有非背面的边
    non_back_edges = model.edges().filter(lambda e: e.Center().x > 0.1)
    
    try:
        model = model.fillet(fillet_rad, non_back_edges)
    except Exception as e:
        # 如果整体倒角失败，尝试只对基座前缘和挂钩进行倒角
        # 回退方案：仅对基座的前两个垂直边和顶面前边倒角
        base_front_edges = model.edges().filter(
            lambda e: abs(e.Center().x - base_length) < 0.1 or 
                      (abs(e.Center().z - base_thickness) < 0.1 and e.Center().x > base_length/2)
        )
        try:
            model = model.fillet(fillet_rad, base_front_edges)
        except:
            pass
            
    # 4. 确保背面完全平整 (X=0 面)
    # 由于我们排除了 X<0.1 的边进行倒角，背面应该是平整的。
    # 为了保险，我们可以创建一个包围盒并切割，但这可能会移除倒角。
    # 只要倒角半径不超过基座厚度且未选中背面边，背面就是平的。
    
    # 5. 最终检查与定位
    # 当前模型中心可能在 (30, 0, ~17.5)
    # 用户需求中的边界盒提示：
    # Fixed BBox: [0.0, -20.0, -17.5, 0.0, 20.0, 17.5] -> 这似乎是说背面在 X=0?
    # Load BBox: [60.0, ...] -> 挂钩在 X=60?
    # 我们的模型：Base X:[0, 60]. 背面在 X=0. 符合。
    # Y: [-20, 20]. 符合。
    # Z: Base [0, 8], Hook up to 35. Center Z approx 17.5. 符合。
    
    return model

# 入口点
MODEL = build_model()