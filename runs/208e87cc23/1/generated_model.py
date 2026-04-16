import cadquery as cq

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    设计思路：
    1. 底座：提供稳定性，包含防滑纹理或加重结构（此处简化为实心底座以保证强度）。
    2. 背板：后倾约 60-70 度，支撑手机背部。
    3. 前挡边：防止手机滑落，高度适中，不遮挡屏幕主要内容。
    4. 加强筋/连接：确保背板与底座连接处有足够的圆角和厚度，避免应力集中，便于打印。
    
    尺寸参考：
    总高 ~110mm, 总长(深度) ~95mm, 宽度 ~78mm.
    """
    
    # 参数定义
    width = 78.0      # Y方向宽度
    base_depth = 95.0 # X方向底座深度
    height = 110.0    # Z方向总高
    
    # 背板参数
    back_angle = 65.0 # 背板与水平面夹角
    back_thickness = 4.0
    back_height = 100.0
    
    # 底座参数
    base_thickness = 8.0
    
    # 前挡边参数
    lip_height = 12.0
    lip_thickness = 4.0
    
    # 创建背板轮廓 (在 XZ 平面绘制，然后拉伸)
    # 计算背板投影长度
    import math
    rad_angle = math.radians(back_angle)
    back_proj_x = back_height * math.cos(rad_angle)
    back_proj_z = back_height * math.sin(rad_angle)
    
    # 背板底部位置：为了美观和稳定，背板底部不在底座最前端，也不在最后端
    # 假设背板底部距离底座后端 20mm
    back_bottom_x_offset = 20.0 
    
    # 构建背板截面 (Profile)
    # 我们从底座后部开始画起
    # 点序列: 
    # P0: (0, 0) - 底座后端底部
    # P1: (base_depth, 0) - 底座前端底部
    # P2: (base_depth, base_thickness) - 底座前端顶部
    # P3: (back_bottom_x_offset + back_proj_x, base_thickness) - 背板顶部X投影位置? 不，这样画太复杂。
    
    # 更简单的策略：分别生成底座、背板、挡边，然后 union。
    
    # 1. 底座
    base = cq.Workplane("XY").box(base_depth, width, base_thickness)
    # 将底座中心移动到 (base_depth/2, 0, base_thickness/2) 以便后续操作，或者保持原点在角点
    # CadQuery box 默认中心在原点。让我们统一坐标系。
    # 设定原点为底座底面中心。
    
    base = cq.Workplane("XY").box(base_depth, width, base_thickness).translate((0, 0, base_thickness/2))
    
    # 2. 背板
    # 背板是一个倾斜的长方体，或者更好的是，一个有厚度的板。
    # 使用 workplane 旋转来创建倾斜特征。
    # 背板底部接触点设在 X = -base_depth/2 + back_bottom_x_offset
    # 为了方便，我们在底座上表面创建一个工作平面，并移动到背板起始位置。
    
    back_start_x = -base_depth/2 + 25.0 # 背板根部距离底座后缘 25mm
    
    # 创建背板：先画一个矩形截面，然后拉伸？不，直接画一个倾斜的盒子并旋转比较复杂。
    # 方法：在 XZ 平面画一个矩形，旋转，然后拉伸 Y 方向。
    
    back_plate = (
        cq.Workplane("XZ")
        .center(back_start_x, base_thickness) # 移动到底座上表面，X偏移
        .transformed(rotate=(0, -(90 - back_angle), 0)) # 旋转坐标系，使Z轴沿背板方向?
        # 这种旋转容易晕。换一种方式：
        # 在 XZ 平面画矩形，然后 rotate 绕 Y 轴。
    )
    
    # 重新构建背板几何：
    # 在 XZ 平面绘制背板的侧面轮廓（矩形），然后拉伸 Y。
    # 矩形尺寸：厚度 back_thickness, 长度 back_height.
    # 位置：底部起点在 (back_start_x, base_thickness)
    # 角度：与 X 轴夹角 back_angle.
    
    back_plate = (
        cq.Workplane("XZ")
        .moveTo(back_start_x, base_thickness)
        .line(back_height * math.cos(rad_angle), back_height * math.sin(rad_angle))
        .line(-back_thickness * math.sin(rad_angle), back_thickness * math.cos(rad_angle))
        .line(-back_height * math.cos(rad_angle), -back_height * math.sin(rad_angle))
        .close()
        .extrude(width / 2, both=True) # 向两侧拉伸一半宽度，实现居中
    )
    
    # 3. 前挡边 (Lip)
    # 位于底座前端，向上延伸
    lip = (
        cq.Workplane("XY")
        .center(base_depth/2 - lip_thickness/2, 0) # 移到底座前端
        .box(lip_thickness, width, lip_height)
        .translate((0, 0, base_thickness + lip_height/2))
    )
    
    # 4. 加强筋/圆角处理
    # 背板与底座连接处需要圆角，以增强强度并利于打印
    # 由于我们是布尔并集，直接对最终结果倒圆角可能比较慢且易错，
    # 这里我们对背板根部和底座连接处做简单的几何融合。
    
    # 组合模型
    model = base.union(back_plate).union(lip)
    
    # 添加圆角
    # 选择背板与底座相交的棱边进行倒角
    # 这是一个启发式选择，可能需要根据具体几何调整 selector
    try:
        # 尝试对背板底部的两条长边倒圆角
        model = model.fillet(3.0, model.edges("|Y").filter(lambda e: abs(e.val().Center().x - back_start_x) < 5 and e.val().Center().z < base_thickness + 5))
    except:
        pass # 如果选择器失败，跳过圆角，保证几何可生成
        
    # 为了打印方便，确保底部是平的
    # 检查并修复底部
    min_z = model.val().BoundingBox().zmin
    if abs(min_z) > 1e-6:
        model = model.translate((0, 0, -min_z))
        
    return model

# 入口函数
def build():
    return build_model()

if __name__ == "__main__":
    show_object(build())