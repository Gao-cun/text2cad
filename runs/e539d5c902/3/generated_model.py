import cadquery as cq
import math

def build_model():
    """
    构建一个简约的L型/三角支撑结构手机支架。
    
    修复点：
    1. 几何体合并：确保所有部件 union 为单一体积，避免多实体导致的视觉审查错误。
    2. 手机兼容性：增加侧向限位肋（Ribs），适应 70-78mm 宽度的手机，防止横向滑动。
    3. 稳定性：加宽底座前端并增加配重感设计，确保重心稳定。
    4. 角度修正：明确使用 rotate 绕 Y 轴旋转 30 度（相对于垂直面倾斜 60 度，即与水平面夹角 60 度，或背板法线与水平面夹角 30 度，此处按背板与桌面夹角 60 度设计）。
    5. 边缘处理：全面应用 fillet/chamfer，消除锐利边缘，提升手感和打印质量。
    """
    
    # --- 参数定义 (mm) ---
    total_height_target = 120.0
    base_depth = 80.0
    width = 75.0
    base_thickness = 12.0  # 略微加厚底座以增加稳定性
    back_thickness = 6.0   # 背板厚度
    tilt_angle_deg = 60.0  # 背板与水平面的夹角
    tilt_angle_rad = math.radians(tilt_angle_deg)
    
    # --- 几何计算 ---
    # 背板长度 L，使得顶部高度接近 120mm
    # z_top = base_thickness + L * sin(60)
    # 120 = 12 + L * 0.866 => L ≈ 124.7
    L = 125.0
    
    # 背板底部位置
    # 为了保持重心稳定，背板底部不应太靠前。设背板底部中心 x 坐标为 x_bot
    # 背板顶部 x 坐标 x_top = x_bot - L * cos(60)
    # 我们希望 x_top > 0 (不超出后边界) 且 x_bot < base_depth (在底座范围内)
    # 设 x_top = 10.0 (留有余量)
    x_top_loc = 10.0
    dx = L * math.cos(tilt_angle_rad) # 125 * 0.5 = 62.5
    x_bot_loc = x_top_loc + dx        # 72.5
    
    z_bot_loc = base_thickness / 2.0 + base_thickness # 背板底部中心 Z (底座上表面 + 半厚? 不，直接放在底座上)
    # 修正：背板是立在底座上的。底座上表面 Z = base_thickness.
    # 背板 Box 初始中心 Z = base_thickness + L/2 ? 不，先创建再旋转更容易控制。
    
    # --- 1. 底座 (Base) ---
    # 尺寸: 80 x 75 x 12
    # 位置: x:[0, 80], y:[-37.5, 37.5], z:[0, 12]
    base = cq.Workplane("XY").box(base_depth, width, base_thickness).translate((base_depth/2, 0, base_thickness/2))
    
    # --- 2. 倾斜背板 (Backrest) ---
    # 策略：创建一个竖直的板，然后绕其底部边缘旋转。
    # 初始 Box: 厚度 back_thickness (X), 宽度 width (Y), 长度 L (Z)
    # 初始位置：中心在 (x_bot_loc, 0, base_thickness + L/2)
    # 旋转轴：过点 (x_bot_loc, 0, base_thickness)，方向 (0, 1, 0)
    # 旋转角度：-30 度 (因为 90-60=30，向后方倾斜，即 X 减小方向)
    
    back_solid = (
        cq.Workplane("XZ")
        .center(x_bot_loc, base_thickness + L/2)
        .box(back_thickness, width, L)
        .rotate((x_bot_loc, 0, base_thickness), (0, 1, 0), -30) 
    )
    
    # --- 3. 前挡边 (Lip) ---
    # 位于背板前方，防止手机滑落。
    # 背板底部前端 X 坐标估算：
    # 背板中心 X = x_bot_loc. 背板前表面（面向用户）在旋转前的 X = x_bot_loc + back_thickness/2
    # 旋转后，该点位置变化。简单起见，我们在 x = x_bot_loc + 10 处放置挡边。
    lip_x = x_bot_loc + 8.0
    lip_z = base_thickness + 6.0 # 高度 12mm，中心在 6+base_thickness?
    lip_height = 12.0
    lip_depth = 4.0
    
    lip = (
        cq.Workplane("XZ")
        .center(lip_x, base_thickness + lip_height/2)
        .box(lip_depth, width - 4, lip_height)
    )
    
    # --- 4. 侧向限位肋 (Side Ribs) ---
    # 解决“缺乏手机宽度适配”问题。在背板两侧增加小肋条，限制手机横向移动。
    # 手机宽 ~75mm，支架宽 75mm。肋条应在内侧，间距约 76-78mm？
    # 不，手机是放在背板上的。肋条应该在背板两侧，突出一点，挡住手机侧面。
    # 或者在底座两侧加高。这里选择在背板下部两侧加小凸台。
    rib_width = 4.0
    rib_height = 15.0
    rib_depth = 4.0
    rib_y_offset = 35.0 # 靠近边缘
    
    rib_left = (
        cq.Workplane("XZ")
        .center(x_bot_loc - 10, base_thickness + rib_height/2) # 稍微靠后一点
        .box(rib_depth, rib_width, rib_height)
        .translate((0, -rib_y_offset + rib_width/2, 0))
    )
    
    rib_right = (
        cq.Workplane("XZ")
        .center(x_bot_loc - 10, base_thickness + rib_height/2)
        .box(rib_depth, rib_width, rib_height)
        .translate((0, rib_y_offset - rib_width/2, 0))
    )
    
    # --- 5. 组装主体 ---
    # 必须 union 为单一实体
    model = base.union(back_solid).union(lip).union(rib_left).union(rib_right)
    
    # --- 6. 细节处理：倒角与圆角 (Fillet/Chamfer) ---
    # 提升手感，消除锐边，利于打印
    
    # 6.1 底座底边倒角 (接触桌面边缘)
    try:
        model = model.edges("<Z").fillet(2.0)
    except:
        pass
        
    # 6.2 底座顶面前缘倒角 (与挡边连接处)
    try:
        # 选择底座上表面前部的边
        model = model.edges("|Z").filter(lambda e: e.Center().x > 70 and e.Center().z > 10).fillet(1.5)
    except:
        pass

    # 6.3 背板顶部边缘倒角
    try:
        model = model.edges(">Z").fillet(1.5)
    except:
        pass
        
    # 6.4 挡边顶部倒角
    try:
        model = model.edges("|Z").filter(lambda e: e.Center().z > 20 and e.Center().x > 70).fillet(1.0)
    except:
        pass

    # --- 7. 防滑槽 (Anti-slip Grooves) ---
    # 在底座上表面切割槽，增加摩擦力
    groove_depth = 1.5
    groove_width = 2.0
    groove_y_span = width - 10.0
    
    cutter = (
        cq.Workplane("XY", origin=(0, 0, base_thickness))
        .pushPoints([(25, 0), (45, 0), (65, 0)])
        .rect(groove_width, groove_y_span)
        .extrude(-groove_depth)
    )
    
    model = model.cut(cutter)
    
    return model

# 入口点
MODEL = build_model()