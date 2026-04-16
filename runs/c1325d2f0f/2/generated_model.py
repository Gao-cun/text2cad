import cadquery as cq
import math

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    修复了上一轮代码中的缩进错误和逻辑断裂问题。
    """
    
    # 参数定义
    width = 78.0      # 支架宽度
    base_depth = 95.0 # 底座深度
    back_height = 110.0 # 背板最高点高度
    thickness = 4.0   # 壁厚/主体厚度
    lip_height = 12.0 # 前挡边高度
    lip_depth = 15.0  # 前挡边深度
    view_angle = 70.0 # 背板与水平面夹角
    
    # --- 组件 1: 底座 (Base) ---
    base_solid = cq.Workplane("XY")\
        .box(base_depth, width, thickness, centered=(True, True, False))\
        .edges("|Z")\
        .fillet(4.0)
    
    # --- 组件 2: 倾斜背板 (Back Support) ---
    back_width = width - 10.0 
    back_thick = 4.0
    
    # 计算几何位置
    # 背板底部起始X坐标 (相对于中心)，稍微靠后以提供力矩支撑
    back_bottom_x = -20.0 
    
    # 有效高度
    height_eff = back_height - thickness
    rad_angle = math.radians(view_angle)
    
    # 水平投影长度 (向后倾斜，所以X减小)
    proj_len = height_eff / math.tan(rad_angle)
    back_top_x = back_bottom_x - proj_len
    
    # 创建背板侧面轮廓 (在 XZ 平面)
    # 为了简化并保证闭合，我们绘制一个平行四边形或梯形，然后拉伸
    # 这里使用一个简单的矩形旋转或者多边形拉伸
    # 方法：绘制背板的中心线或边缘，然后赋予厚度
    
    # 让我们绘制背板的“背面”轮廓，然后偏移厚度，或者直接绘制实体截面
    # 截面点:
    # P1: 底部前端 (back_bottom_x, thickness)
    # P2: 顶部前端 (back_top_x, back_height)
    # P3: 顶部后端 (back_top_x - back_thick * sin(alpha), back_height + back_thick * cos(alpha)) ? 
    # 简化：假设背板厚度垂直于背板表面，或者简单地垂直厚度？
    # 为了打印方便，通常背板是均匀厚度的板。如果倾斜，垂直切片厚度会变。
    # 最好让背板厚度方向垂直于板面。
    
    angle_from_vert = 90.0 - view_angle # 15度
    rad_vert = math.radians(angle_from_vert)
    
    # 厚度在X和Z方向的投影
    dx_thick = back_thick * math.sin(rad_vert) # 水平分量
    dz_thick = back_thick * math.cos(rad_vert) # 垂直分量
    
    # 轮廓点 (顺时针)
    # 1. 底部内角 (接触手机面底部)
    x1, z1 = back_bottom_x, thickness
    # 2. 顶部内角 (接触手机面顶部)
    x2, z2 = back_top_x, back_height
    # 3. 顶部外角 (背面顶部)
    x3, z3 = x2 - dx_thick, z2 + dz_thick
    # 4. 底部外角 (背面底部)
    x4, z4 = x1 - dx_thick, z1 + dz_thick
    
    back_profile = cq.Workplane("XZ")\
        .moveTo(x1, z1)\
        .lineTo(x2, z2)\
        .lineTo(x3, z3)\
        .lineTo(x4, z4)\
        .close()\
        .extrude(back_width, both=True)
        
    # --- 组件 3: 前挡边 (Lip) ---
    lip_solid = cq.Workplane("XY")\
        .box(lip_depth, width, lip_height, centered=(True, True, False))\
        .translate((base_depth/2 - lip_depth/2, 0, thickness))
        
    # 倒角处理
    try:
        lip_solid = lip_solid.edges("|Z and >X").chamfer(2.0)
    except:
        pass

    # --- 组装 ---
    model = base_solid.union(back_profile).union(lip_solid)
    
    # --- 全局圆角优化 ---
    # 尝试对主要边缘进行圆角，增加美观度和强度
    try:
        # 宽度方向的长边
        model = model.edges("|Y").fillet(2.0)
    except:
        pass
        
    try:
        # 顶部边缘
        model = model.edges(">Z").fillet(1.5)
    except:
        pass

    return model

def build():
    return build_model()

def make_model():
    return build_model()

MODEL = build_model()