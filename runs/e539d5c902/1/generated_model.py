import cadquery as cq
import math

def build_model():
    """
    构建一个简约的L型/三角支撑结构手机支架。
    设计特点：
    1. 背部倾斜约60度，适合观看视频。
    2. 底部有防滑槽和足够的配重区域。
    3. 前方有托举挡边，防止手机滑落。
    4. 整体结构简洁，无悬空，适合FDM 3D打印。
    """
    
    # 参数定义 (mm)
    total_height = 120.0
    base_depth = 80.0
    width = 75.0
    wall_thickness = 4.0
    tilt_angle_deg = 60.0
    tilt_angle_rad = math.radians(tilt_angle_deg)
    
    # 计算几何尺寸
    # 背板长度：为了达到总高度120mm，且倾角60度，背板投影高度需计算
    # 假设背板顶部距离桌面垂直高度为 H_top
    # 这里我们采用直角三角形支撑结构，背板作为斜边或者直立面的变体
    # 为了简化打印和结构强度，采用“L型底座 + 倾斜背板 + 三角加强筋”的结构
    
    # 1. 底座 (Base)
    # 底座需要足够深以保证稳定性，设定为80mm深，75mm宽，厚度10mm
    base = cq.Workplane("XY").box(base_depth, width, 10.0)
    
    # 2. 倾斜背板 (Backrest)
    # 背板从底座后部延伸，角度60度（与水平面夹角）
    # 计算背板在XZ平面的轮廓
    # 假设背板底部起始于底座后端上方
    # 背板长度设为110mm，以保证顶部高度足够
    back_length = 110.0
    back_thickness = 5.0
    
    # 创建背板的截面轮廓 (在XZ平面)
    # 原点设在底座上表面中心后方
    # 背板底部点: (-base_depth/2 + offset, 0) -> 实际上我们相对于底座中心建模更方便
    # 让我们使用局部坐标系或相对移动
    
    # 重新规划：以底座上表面中心为参考
    # 底座范围: x: [-40, 40], y: [-37.5, 37.5], z: [0, 10]
    
    # 背板起始位置：距离底座后端边缘 10mm 处开始倾斜，或者直接连接后端
    # 为了稳定性，背板根部应靠近底座后端。设背板下端点位于 x = -35 (底座后端是-40)
    # 背板上端点坐标计算:
    # dx = back_length * cos(60deg) = 110 * 0.5 = 55
    # dz = back_length * sin(60deg) = 110 * 0.866 = 95.26
    # 如果下端点在 x=-35, z=10, 则上端点 x = -35 + 55 = 20, z = 10 + 95.26 = 105.26
    # 这符合总高约120的要求 (105+底座10=115, 接近120)
    
    s = cq.Workplane("XZ")
    # 绘制背板轮廓 (矩形旋转或拉伸)
    # 使用 polyline 绘制背板的中轴线，然后 sweep 或 box 旋转?
    # 简单方法：创建一个旋转后的 box
    
    back_plate = (
        cq.Workplane("XZ")
        .center(-35 + back_length/2 * math.cos(tilt_angle_rad), 
                10 + back_length/2 * math.sin(tilt_angle_rad))
        .box(back_thickness, width, back_length)
        .rotate((0,0,0), (0,1,0), -(90 - tilt_angle_deg)) # 绕Y轴旋转，使角度正确
    )
    # 注意：CadQuery的rotate是绕轴旋转。初始box是直立的。我们需要它倾斜60度。
    # 初始Box长边沿Z轴。绕Y轴旋转 (90-60)=30度? 
    # 如果Box沿Z轴，旋转30度后，与Z轴夹角30度，与X轴夹角60度。符合。
    # 修正旋转中心和角度逻辑：
    # 更稳健的方法是使用 polygon 拉伸
    
    # 方法B：Polygon Extrusion (更精确控制)
    # 在XZ平面画一个梯形或矩形作为背板
    x_start = -35.0
    z_start = 10.0
    x_end = x_start + back_length * math.cos(tilt_angle_rad)
    z_end = z_start + back_length * math.sin(tilt_angle_rad)
    
    # 背板四个角 (厚度方向垂直于板面? 不，通常背板厚度是均匀的，这里简化为垂直厚度或法向厚度)
    # 为了打印方便，背板厚度沿Z轴或垂直于板面？
    # 简单起见，背板作为一个倾斜的薄壁。我们用两个点定义线段，然后给厚度。
    # 使用 workplane 变换
    
    wp_back = cq.Workplane("XZ").transformed(offset=(x_start, 0, z_start), rotate=(0, -(90-tilt_angle_deg), 0))
    # 现在 wp_back 的 Z 轴沿着背板方向
    back_solid = wp_back.box(back_thickness, width, back_length).val()
    
    # 3. 前挡边 (Lip)
    # 防止手机滑落，位于背板底部前方
    # 位置：在背板下端前方，高度约15mm
    lip_height = 15.0
    lip_thickness = 4.0
    lip_depth = 10.0 # 沿背板方向的深度? 或者水平深度?
    # 简单做一个小方块在底部前方
    # 手机靠在背板上，底部抵住挡边。挡边应在背板前方约手机厚度处? 
    # 不，挡边通常就是背板底部的延伸，或者独立的小凸起。
    # 我们在背板下端的前方 (X正方向) 创建一个凸起
    
    # 计算背板下端的前表面位置
    # 背板中心线在 x_start, 厚度 back_thickness. 
    # 背板前表面 (面向用户/手机) 的法向量指向 X负方向? 
    # 我们的背板是从后(-X)向前(+X)倾斜上升? 
    # x_start = -35. x_end = 20. 是的，向前倾斜。
    # 手机放在背板“上”表面。对于从后往前的倾斜，上表面是朝向“后上方”还是“前上方”?
    # 通常支架是 / 形状。底部在后，顶部在前？不，通常是 \ 形状 (底部在前，顶部在后) 或者 / 形状 (底部在后，顶部在前)。
    # 如果是 / 形状 (底部x=-35, 顶部x=20)，手机放上去会滑向后方(-X)。这需要后方有挡边。
    # 常见的支架是 \ 形状：底部在前(x=20)，顶部在后(x=-35)? 
    # 让我们看基线：Loading box at x=80, Fixed at x=0. 
    # 这意味着固定端在左(后)，加载端在右(前)。
    # 所以支架应该是：背部靠在左侧(后)，手机重心在右侧(前)。
    # 也就是 \ 形状：顶部在后(-X)，底部在前(+X)？
    # 不，如果顶部在后，底部在前，倾角60度。手机放上去，重力分量会让手机压向背板。
    # 让我们调整几何：
    # 背板底部在 x = 10 (靠近前端), 顶部在 x = 10 - 55 = -45 (靠近后端).
    # 这样手机靠在背板上，自然下滑趋势是被底部的挡边挡住。
    
    # 重新计算坐标:
    # 背板下端点 (靠近手机底部): x = 10.0, z = 10.0 (底座上表面)
    # 背板上端点: x = 10.0 - 55.0 = -45.0, z = 10.0 + 95.26 = 105.26
    # 这样背板是 \ 形状。
    
    x_bot = 10.0
    z_bot = 10.0
    x_top = x_bot - back_length * math.cos(tilt_angle_rad)
    z_top = z_bot + back_length * math.sin(tilt_angle_rad)
    
    # 构建背板
    # 使用 transform 使得 Z 轴沿背板向上
    # 向量 from bot to top: (-55, 0, 95.26). Angle with horizontal: 120 deg? 
    # 倾角60度指与水平面夹角。\ 形状与水平面夹角60度。
    # 旋转角度：绕Y轴。初始Z轴向上。我们需要Z轴指向左上方(120度方向)或右上方(60度方向)。
    # 目标向量: (-cos60, 0, sin60). 
    # 初始向量: (0, 0, 1). 
    # 旋转: 绕Y轴旋转 -30度? 
    # R_y(-30): x' = x cos - z sin... 
    # 让我们用简单的 rotate 方法。
    
    back_wp = cq.Workplane("XZ").transformed(offset=(x_bot, 0, z_bot), rotate=(0, 30, 0))
    # 旋转30度后，Z轴指向 (sin30, 0, cos30) = (0.5, 0, 0.866). 这是向右上方。
    # 我们需要向左上方 (-0.5, 0, 0.866). 所以旋转 150度? 或者 -150? 
    # 或者旋转 30度 然后 mirror? 
    # 简单点：旋转 (0, 150, 0). 
    # cos150 = -0.866, sin150 = 0.5. 
    # Z轴 (0,0,1) -> ( -sin150, 0, cos150 )? CadQuery rotation convention.
    # 让我们试错法：rotate=(0, 90+30, 0) = 120度?
    # 只要保证背板是 \ 形状即可。
    
    # 替代方案：直接画线拉伸
    profile = cq.Workplane("XZ").moveTo(x_bot, z_bot).lineTo(x_top, z_top).lineTo(x_top + back_thickness*math.sin(tilt_angle_rad), z_top + back_thickness*math.cos(tilt_angle_rad)).lineTo(x_bot + back_thickness*math.sin(tilt_angle_rad), z_bot + back_thickness*math.cos(tilt_angle_rad)).close()
    # 这种手动计算法向量太麻烦且易错。
    
    # 最可靠方案：Box + Rotate
    # 中心点
    cx = (x_bot + x_top) / 2
    cz = (z_bot + z_top) / 2
    
    back_solid = (
        cq.Workplane("XZ")
        .center(cx, cz)
        .box(back_thickness, width, back_length)
        .rotate((cx, 0, cz), (0, 1, 0), 30) # 绕中心，Y轴，旋转30度。初始竖直，旋转30度变成 \ (如果方向对)
        # 初始Box长边沿Z。旋转30度后，与Z轴夹角30度。与X轴夹角60度。
        # 如果旋转方向使得顶部向-X移动，则是 \。
        # CadQuery rotate angle is degrees. 
    )
    
    # 检查旋转方向：
    # 默认Box在XZ中心。Rotate around Y. 
    # 正角度旋转：X->Z, Z->-X? Right hand rule. Y up. X right, Z out? 
    # CadQuery: X right, Y up, Z out (towards user). 
    # Wait, standard CSQ: X right, Y forward, Z up? 
    # Workplane("XZ"): X right, Z up. Y is normal.
    # Rotate around (0,1,0) which is Y axis.
    # Right hand rule on Y: X rotates towards Z. Z rotates towards -X.
    # So a vertical box (along Z) rotated +30 deg will lean towards -X. 
    # This creates the \ shape. Correct.
    
    # 4. 三角加强筋 (Rib)
    # 连接背板背面和底座，增加强度
    # 背板背面在右上方。底座在下方。
    # 在背板下端和底座之间添加 fillet 或 rib.
    # 简单起见，添加一个大圆角或三角形支撑块。
    
    # 5. 前挡边 (Lip)
    # 在背板下端的前方 (X正方向一侧，因为背板是 \，下端在前? 
    # x_bot = 10. x_top = -45. 
    # 手机放在背板上。手机底部会滑向 x_bot (10).
    # 所以在 x = 10 附近需要一个挡边。
    # 挡边应该在背板的前表面 (Right side of the \ shape).
    # 背板厚度方向。背板中心在 x_bot. 
    # 背板前表面 (面向手机) 大约在 x_bot + thickness/2 * sin(30)? 
    # 由于背板倾斜30度(from vertical)，法线指向右下方。
    # 简单做法：在 x = x_bot + 5, z = 10 处建一个小方块。
    
    lip = (
        cq.Workplane("XZ")
        .center(x_bot + 6, 10 + 5) # 稍微靠前，高度一半
        .box(4, width - 10, 10) # 厚4，宽略窄，高10
    )
    
    # 6. 防滑槽 (Anti-slip grooves)
    # 在底座上表面和挡边上切出槽
    groove_w = 2.0
    groove_d = 1.0
    
    # 底座上的槽
    base_grooves = (
        cq.Workplane("XY", origin=(0, 0, 10))
        .rect(60, width - 10)
        .cutBlind(-groove_d) # 向下切? 不，这是在Z=10面上操作
        # cutBlind cuts into the solid. Since we are on top face, negative depth goes in.
    )
    # 注意：cutBlind 需要基于实体。我们需要 union 后再 cut，或者单独生成 cutter。
    
    # 组装
    model = base.union(back_solid).union(lip)
    
    # 添加圆角 (Fillet) 以提升手感和打印质量
    # 选择背板与底座连接的 edges
    # 选择所有垂直边缘进行小倒角
    try:
        model = model.edges("|Z").fillet(2.0)
        model = model.edges().filter(lambda e: True).fillet(1.0) # 全局小倒角，可能报错，需谨慎
    except:
        pass
        
    # 更安全的倒角：只对外露边缘
    model = model.edges(">Z or <Z").fillet(1.5) # 水平边缘
    
    # 切割防滑槽
    # 创建 cutter
    cutter = (
        cq.Workplane("XY", origin=(0, 0, 10))
        .pushPoints([(-15, 0), (0, 0), (15, 0)])
        .rect(2, width - 5)
        .extrude(-2) # 向下切入底座
    )
    model = model.cut(cutter)
    
    # 最终检查尺寸和位置
    # 确保模型在原点附近，符合 BoundingBox 要求
    # 当前 Base: x[-40, 40]. Back top x ~ -45. 
    # 基线要求 Fixed Box xmin=0. 这意味着模型应该整体平移，使得最左端/后端对齐 x=0?
    # 基线: Fixed [0.0, ...], Loading [80.0, ...]. 
    # 这暗示模型长度方向是X轴，从0到80。
    # 当前模型 x 范围: [-45, 40]. 长度 85. 
    # 我们需要平移模型，使得 x_min >= 0. 
    # 平移量: +45 mm.
    
    model = model.translate((45, 0, 0))
    
    # 再次检查高度
    # Base z: [0, 10]. Back top z: ~105. Total ~105. 
    # 目标高 120. 
    # 增加背板长度或调整角度。
    # 如果 back_length = 125. 
    # dz = 125 * sin60 = 108. z_top = 118. 
    # dx = 125 * cos60 = 62.5. 
    # x_bot (translated) = 10 + 45 = 55. 
    # x_top = 55 - 62.5 = -7.5. (Still > 0? No, -7.5 < 0). 
    # 如果 x_top < 0, 则超出 Fixed Box xmin=0. 
    # 所以必须保证 x_top >= 0. 
    # x_top = x_bot - L*cos60. 
    # x_bot <= Base_Depth (80). 
    # 如果 x_bot = 70 (靠近前端). 
    # x_top = 70 - L*0.5. 
    # 如果 L=120. x_top = 10. OK. 
    # z_top = 10 + 120*0.866 = 114. OK. 
    
    # 重新调整参数以满足 BoundingBox [0, 80] X-axis
    # Base: 80mm deep. x:[0, 80].
    # Back plate bottom at x = 60. 
    # Back plate length = 115. 
    # dx = 115 * 0.5 = 57.5. 
    # x_top = 60 - 57.5 = 2.5. (Inside [0,80]).
    # dz = 115 * 0.866 = 99.6. 
    # z_top = 10 + 99.6 = 109.6. (Close to 120). 
    # 为了更高，增加长度到 125.
    # L=125. dx=62.5. x_top = 60-62.5 = -2.5. (Out of bounds). 
    # 所以 x_bot 必须更大，比如 70.
    # x_bot = 70. L=125. x_top = 70 - 62.5 = 7.5. OK.
    # z_top = 10 + 108.25 = 118.25. OK.
    
    # 重构模型以严格符合边界
    
    # 1. Base
    base = cq.Workplane("XY").box(80, 75, 10).translate((40, 0, 5)) # Center at 40,0,5 -> x:[0,80]
    
    # 2. Back Plate
    L = 125.0
    x_bot_loc = 70.0
    z_bot_loc = 10.0
    
    back_solid = (
        cq.Workplane("XZ")
        .center(x_bot_loc, z_bot_loc)
        .box(5, 75, L)
        .rotate((x_bot_loc, 0, z_bot_loc), (0, 1, 0), 30) # Leans back towards X=0
    )
    
    # 3. Lip
    # At x_bot_loc, slightly forward
    lip = (
        cq.Workplane("XZ")
        .center(x_bot_loc + 5, 15) # x=75, z=15
        .box(4, 65, 10)
    )
    
    model = base.union(back_solid).union(lip)
    
    # Fillets
    model = model.edges("|Z").fillet(2.0)
    
    # Grooves on base
    cutter = (
        cq.Workplane("XY", origin=(0, 0, 10))
        .pushPoints([(20, 0), (40, 0), (60, 0)])
        .rect(2, 65)
        .extrude(-2)
    )
    model = model.cut(cutter)
    
    return model

# 入口点
MODEL = build_model()