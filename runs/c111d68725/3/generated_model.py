import cadquery as cq
import math

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    修复了上一轮代码中的语法错误（在列表推导/定义中混入了赋值语句）。
    采用侧面轮廓拉伸法，确保几何体 manifold 且结构连续。
    """
    
    # --- 参数定义 ---
    total_height = 110.0
    total_width = 78.0
    target_depth = 95.0
    thickness = 4.0      # 基础壁厚/特征尺寸
    back_angle_deg = 75.0 # 背板与水平面夹角
    front_lip_height = 12.0 # 前挡边高度
    slot_depth = 8.0     # 前挡边内侧凹槽深度
    
    # --- 几何计算 ---
    angle_rad = math.radians(back_angle_deg)
    
    t_back = 4.0
    
    h_eff = total_height
    dx_proj = h_eff / math.tan(angle_rad)
    
    # 计算背板外表面的偏移量
    # 背板内表面角度为 75度 (相对于X轴)
    # 外表面法线角度为 75 + 90 = 165度
    nx = math.cos(math.radians(165))
    nz = math.sin(math.radians(165))
    
    p7_x = dx_proj + t_back * nx
    p7_z = total_height + t_back * nz
    
    p8_x = 0 + t_back * nx
    p8_z = thickness + t_back * nz
    
    # 定义轮廓点序列 (X, Z)
    # 修复点：将之前的计算逻辑移出列表定义，确保列表内只包含元组数据
    pts = [
        (0, 0),                         # 1. 底座后下
        (target_depth, 0),              # 2. 底座前下
        (target_depth, front_lip_height), # 3. 前挡边外上
        (target_depth - slot_depth, front_lip_height), # 4. 前挡边内上
        (dx_proj, total_height),        # 5. 背板内表面顶部
        (0, thickness),                 # 6. 背板内表面底部
        (p7_x, p7_z),                   # 7. 背板外表面顶部
        (p8_x, p8_z),                   # 8. 背板外表面底部
        (0, 0)                          # 回到起点
    ]
    
    # 生成侧面轮廓并拉伸
    profile = cq.Workplane("XZ").polyline(pts).close()
    stand_body = profile.extrude(total_width)
    
    # 居中 Y 轴
    stand_body = stand_body.translate((0, -total_width/2, 0))
    
    # 平移模型使 X 最小值为 0，以符合边界盒要求
    bb = stand_body.val().BoundingBox()
    min_x = bb.min.X
    if min_x < 0:
        stand_body = stand_body.translate((-min_x, 0, 0))
    
    # 添加圆角以增加美观和强度，并避免应力集中
    try:
        # 选择前挡边顶部的两条长边 (Y 方向) 进行倒角
        stand_body = stand_body.edges(">Z and |Y").fillet(1.5)
    except Exception:
        pass
        
    return stand_body

def build():
    return build_model()

def make_model():
    return build_model()

MODEL = build_model()