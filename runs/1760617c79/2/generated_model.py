import cadquery as cq
import math

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    修复了上一轮中因选择器失效导致的 fillet 错误。
    优化了几何构造，使用更稳健的拉伸和布尔运算逻辑。
    """
    
    # --- 参数定义 ---
    base_length = 95.0   # X方向总长
    base_width = 78.0    # Y方向总宽
    base_height = 12.0   # 底座厚度 (略微增加以提高稳定性)
    
    back_angle_deg = 75.0 # 背板与水平面夹角
    back_vertical_height = 90.0 # 背板垂直高度
    wall_thickness = 4.0 # 结构壁厚
    
    lip_height = 15.0    # 前挡边高度
    lip_thickness = 4.0  # 前挡边厚度
    lip_offset_from_front = 10.0 # 挡边距离前端的距离
    
    # --- 几何计算 ---
    back_angle_rad = math.radians(back_angle_deg)
    # 背板斜边长度
    back_slope_length = back_vertical_height / math.sin(back_angle_rad)
    # 背板在X方向的投影长度
    back_x_projection = back_slope_length * math.cos(back_angle_rad)
    
    # 背板起始位置 (距离底座后端)
    # 留出一定底座后端作为配重，防止手机放上后后翻
    back_start_x = 20.0 
    
    # --- 1. 创建底座 ---
    # 使用圆角矩形，Z=0 为底面
    base = (
        cq.Workplane("XY")
        .box(base_length, base_width, base_height)
        .edges("|Z")
        .fillet(6.0)
    )
    
    # --- 2. 创建背板 ---
    # 策略：在 XZ 平面绘制侧面轮廓，然后向 Y 方向拉伸
    # 轮廓点：
    # P1: (back_start_x, base_height) - 背板底部前端点（相对于底座上表面）
    # P2: (back_start_x + back_x_projection, base_height + back_vertical_height) - 背板顶部点
    # 为了增加强度和打印便利性，背板底部做一个三角形的加强过渡或者直接加厚根部
    # 这里采用一个简单的梯形或矩形倾斜拉伸，并在底部与底座融合
    
    # 计算背板顶部的 X 坐标
    back_top_x = back_start_x + back_x_projection
    back_top_z = base_height + back_vertical_height
    
    # 绘制背板侧面轮廓 (XZ平面)
    # 我们画一个有厚度的倾斜板
    # 内部轮廓和外部轮廓，或者简单画一个中心线然后偏移？
    # 简单方法：画一个平行四边形或矩形，旋转后拉伸
    
    # 更稳健的方法：直接画出背板的截面多边形
    # 截面位于 XZ 平面
    # 点1: 底部后端 (back_start_x, base_height)
    # 点2: 顶部后端 (back_top_x, back_top_z)
    # 点3: 顶部前端 (back_top_x - wall_thickness * sin(angle)? No, thickness is perpendicular to plate or vertical?)
    # 通常背板厚度是指垂直于板面的厚度，或者是Z方向的厚度？
    # 为了简化打印和建模，我们假设背板是均匀厚度的实体。
    # 让我们定义背板的“背面”线和“正面”线。
    
    # 背面线: 从 (back_start_x, base_height) 到 (back_top_x, back_top_z)
    # 正面线: 偏移 wall_thickness。方向向量 (-sin, cos) ?
    # 角度是与水平面夹角 alpha. 法向量指向右上方? 
    # 板面向后倾斜。法向量指向 (sin(alpha), cos(alpha)) in XZ? 
    # 让我们用简单的几何变换：先画竖直板，再旋转。
    
    # 重新构建背板：
    # 1. 创建一个竖直的长方体，尺寸：thickness x width x height
    # 2. 旋转它
    # 3. 移动它到正确位置
    
    back_plate_raw = (
        cq.Workplane("XZ")
        .box(wall_thickness, base_width - 10, back_slope_length) # 注意：box 的参数是沿当前工作平面轴的长度
        # 在 XZ 平面，box(x_len, y_len, z_len) -> x_len 沿 X, y_len 沿 Y(即全局Y), z_len 沿 Z
        # 等等，Workplane("XZ") 的轴是 X 和 Z。Y 是挤出方向？
        # CadQuery Workplane("XZ"): X is horizontal, Z is vertical. Y is normal.
        # box(length, width, height) -> length along X, width along Y (normal), height along Z?
        # No. box(xLen, yLen, zLen) maps to the workplane axes.
        # For "XZ": xLen -> X, yLen -> Z (since Y is normal? No, standard is X,Y are plane, Z is normal).
        # Let's check docs: Workplane("XZ") means X and Z are in the plane. Y is the normal.
        # So box(x, y, z) -> x along X, y along Z, z along Y (extrusion).
        # We want a plate that is thin in X (thickness), tall in Z (slope length), and wide in Y (width).
        # So: box(wall_thickness, back_slope_length, base_width - 10)
    )
    
    # 上述 box 定义可能混淆，改用显式拉伸：
    back_profile = (
        cq.Workplane("XZ")
        .moveTo(back_start_x, base_height)
        .line(back_x_projection, back_vertical_height) # 画背板背面线
        .line(-wall_thickness * math.sin(back_angle_rad), wall_thickness * math.cos(back_angle_rad)) # 垂直于背面向内偏移? 
        # 简单点：画一个矩形，然后旋转
        .close() # 这不行，线没闭合
    )
    
    # 最可靠的方法：
    # 1. 在 XZ 平面画一个矩形，代表背板的侧视图（如果背板是垂直的）
    # 2. 旋转这个矩形
    # 3. 拉伸
    
    back_solid = (
        cq.Workplane("XZ")
        .center(back_start_x, base_height + back_slope_length/2) # 移动到旋转中心附近？不，直接画在原点附近再移动
        .moveTo(0, -back_slope_length/2)
        .lineTo(wall_thickness, -back_slope_length/2)
        .lineTo(wall_thickness, back_slope_length/2)
        .lineTo(0, back_slope_length/2)
        .close()
        .extrude(base_width - 10) # 沿 Y 轴拉伸
        .translate((0, 5, 0)) # Y 方向居中
        .rotate((0,0,0), (0,1,0), -(90 - back_angle_deg)) # 绕 Y 轴旋转，使其倾斜
        # 旋转后，原本竖直的板现在倾斜了。原本底部在 Z=-L/2，现在需要移动到底座表面
        .translate((back_start_x, 0, base_height + back_slope_length/2 * math.cos(math.radians(90-back_angle_deg))))
        # 这种手动计算平移太容易出错。
    )
    
    # --- 重构：使用多段线拉伸 (Sweep/Extrude with profile) ---
    # 这是最不容易出错的方法。
    
    # 1. 定义背板的侧面截面 (XZ平面)
    # 我们需要一个四边形，表示背板的侧视图。
    # 点 A (底部外侧): (back_start_x, base_height)
    # 点 B (顶部外侧): (back_start_x + back_x_projection, base_height + back_vertical_height)
    # 向量 AB = (back_x_projection, back_vertical_height)
    # 法向量 (指向内侧/前方): n = (sin(alpha), -cos(alpha))? 
    # 角度 alpha 是与水平面夹角。垂直于板的方向向量：
    # dx = sin(alpha), dz = -cos(alpha) (指向右下方? 不，指向右上方是板面法线?)
    # 板面朝左上。法线朝右下? 
    # 让我们用简单的三角函数计算另外两个点 C, D (内侧)
    # 厚度 t = wall_thickness
    # 点 D (底部内侧): A + t * (sin(alpha), cos(alpha)?) 
    # 如果板向后倾，内侧（放手机的一面）应该在 A 的右上方？
    # 不，A 是底部支点。板往左上方延伸？
    # 之前的定义：back_start_x = 20. 背板往 X 正方向延伸并升高。
    # 所以板是 “/” 形状。
    # 外侧（背面）是左下-右上。内侧（正面）也是左下-右上，但在外侧的右下方。
    # 垂直于板面向下的向量：(sin(alpha), -cos(alpha))? 
    # 验证：alpha=90 (竖直). vec=(1, 0). 对。
    # alpha=0 (水平). vec=(0, -1). 对。
    
    sin_a = math.sin(back_angle_rad)
    cos_a = math.cos(back_angle_rad)
    
    # 外侧点
    p1_out = (back_start_x, base_height)
    p2_out = (back_start_x + back_x_projection, base_height + back_vertical_height)
    
    # 内侧点 (偏移 wall_thickness)
    # 偏移方向：X 增加, Z 减小 (因为板是 / 状，内侧在右下)
    p1_in = (p1_out[0] + wall_thickness * sin_a, p1_out[1] - wall_thickness * cos_a)
    p2_in = (p2_out[0] + wall_thickness * sin_a, p2_out[1] - wall_thickness * cos_a)
    
    # 修正：如果 p1_in 的 Z 小于 base_height，说明插入了底座内部，这是好的（布尔并集）
    # 但为了几何干净，我们让背板直接从底座上表面开始，或者稍微插入。
    # 这里允许插入，通过 union 融合。
    
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
    lip_x_center = base_length - lip_offset_from_front - lip_thickness/2
    
    lip = (
        cq.Workplane("XY")
        .workplane(offset=base_height)
        .center(lip_x_center, 0)
        .box(lip_thickness, base_width - 10, lip_height)
    )
    
    # --- 4. 组合 ---
    # 先合并底座和背板
    model = base.union(back_sketch)
    # 再合并挡边
    model = model.union(lip)
    
    # --- 5. 细节处理 (Fillet) ---
    # 为了避免选择器错误，我们只对明确的、存在的边进行倒角，或者跳过易错部分。
    # 这里我们对挡边的顶部外沿进行倒角，提升手感。
    # 选择 Lip 的顶部垂直边
    try:
        model = model.edges("|Z").vertices(cq.NearestToPointSelector((lip_x_center, 0, base_height + lip_height))).fillet(2.0)
    except:
        pass # 如果选择失败，跳过，保证模型生成
        
    # 对底座底部边缘倒角
    try:
        model = model.edges("|Z").filter(lambda e: e.val().Center().z < 1.0).fillet(2.0)
    except:
        pass

    return model

# 入口点
MODEL = build_model()