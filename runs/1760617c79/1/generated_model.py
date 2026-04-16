import cadquery as cq

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    设计思路：
    1. 底座：提供稳定性，包含防滑纹理或加重结构（此处简化为实心以保证强度）。
    2. 背板：后倾约 75-80 度，支撑手机背部。
    3. 前挡边：防止手机滑落，高度适中不遮挡屏幕底部关键操作区。
    4. 加强筋/连接：确保背板与底座连接处有足够的圆角和厚度，避免应力集中且便于打印。
    
    尺寸参考：
    总高: ~110mm
    总长(X): ~95mm (从后端到前端)
    总宽(Y): ~78mm
    """
    
    # 参数定义
    base_length = 95.0   # X方向总长
    base_width = 78.0    # Y方向总宽
    base_height = 10.0   # 底座厚度
    back_height = 100.0  # 背板垂直投影高度
    back_angle = 75.0    # 背板与水平面夹角
    lip_height = 12.0    # 前挡边高度
    lip_thickness = 4.0  # 前挡边厚度
    wall_thickness = 3.0 # 壁厚/主要结构厚度
    
    # 计算几何关键点
    # 背板底部起始位置 (假设背板底部距离底座后端有一定距离，或者直接从后端开始)
    # 为了稳定性，底座后端留出一部分作为配重区，背板从 x=15mm 处开始升起
    back_start_x = 15.0
    
    # 创建底座
    # 使用圆角矩形底座，增加美观度和安全性
    base = (
        cq.Workplane("XY")
        .box(base_length, base_width, base_height)
        .edges("|Z")
        .fillet(5.0)
    )
    
    # 创建背板
    # 背板是一个倾斜的平板，底部与底座连接，顶部自由
    # 我们需要计算背板的长度，使其垂直高度约为 back_height
    # L * sin(angle) = back_height => L = back_height / sin(angle)
    import math
    back_plate_length = back_height / math.sin(math.radians(back_angle))
    
    # 背板的工作平面：在底座上表面，沿X轴移动 back_start_x，然后绕Y轴旋转
    # 注意：CadQuery 的 rotateAboutCenter 或 workplane 变换
    # 更简单的方法：先画一个竖直的板，然后旋转
    
    back_plate = (
        cq.Workplane("XZ")
        .center(back_start_x + (base_length - back_start_x)/2, base_height + back_height/2) # 定位中心有点复杂，改用相对定位
        .transformed(offset=(back_start_x, 0, base_height), rotate=(0, -(90 - back_angle), 0))
        .box(wall_thickness, base_width - 10, back_plate_length) # 宽度略小于底座，留出边缘
        .edges("|Y")
        .fillet(2.0)
    )
    
    # 上述方法可能导致定位偏差，采用更稳健的构造法：
    # 1. 在 XZ 平面绘制背板的侧面轮廓（一条线或矩形）
    # 2. 拉伸 (extrude) 成实体
    
    # 重新构建背板：
    # 侧视图轮廓：从 (back_start_x, base_height) 开始，角度为 back_angle
    # 终点 X = back_start_x + back_plate_length * cos(90-angle)? 
    # 角度是与水平面夹角。dx = L * cos(angle), dz = L * sin(angle)
    dx = back_plate_length * math.cos(math.radians(back_angle))
    dz = back_plate_length * math.sin(math.radians(back_angle))
    
    end_x = back_start_x + dx
    end_z = base_height + dz
    
    # 为了确保连接稳固，我们在背板底部增加一个三角形加强肋或直接加厚连接处
    # 这里使用一个简单的倾斜矩形拉伸
    
    back_solid = (
        cq.Workplane("XZ")
        .moveTo(back_start_x, base_height)
        .line(dx, dz)
        .line(-wall_thickness, 0) # 回退厚度
        .line(-dx, -dz)
        .close()
        .extrude(base_width - 10) # 两侧各留 5mm 间隙
        .translate((0, 5, 0)) # 居中 Y 方向: (78 - (78-10))/2 = 5
    )
    
    # 添加前挡边 (Lip)
    # 位于底座前端，稍微靠后一点，防止手机滑出
    # 位置：X 方向接近前端，例如 x = base_length - 15
    lip_x_pos = base_length - 15.0
    
    lip = (
        cq.Workplane("XY")
        .workplane(offset=base_height)
        .center(lip_x_pos, 0)
        .box(lip_thickness, base_width - 10, lip_height)
        .edges("|Z")
        .fillet(2.0)
    )
    
    # 组合所有部分
    model = base.union(back_solid).union(lip)
    
    # 优化：在背板和底座连接处添加圆角，减少应力集中，改善打印质量
    # 由于是布尔运算后的结果，直接选边可能不稳定，但在简单几何下可行
    # 或者在设计之初就融合。这里尝试对连接处倒角
    
    # 为了代码的鲁棒性，不进行复杂的自动选边倒角，而是依靠几何重叠的自然过渡
    # 如果需要更平滑，可以在 back_solid 底部增加一个小的过渡块
    
    return model

# 入口点
MODEL = build_model()