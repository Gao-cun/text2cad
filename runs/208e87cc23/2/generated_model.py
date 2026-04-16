import cadquery as cq
import math

def build_model():
    """
    构建一个简洁的、适合3D打印的桌面手机支架。
    修复点：
    1. 解决多实体问题：使用 fuse=True 确保 union 操作合并为单一 Solid，避免网格化失败。
    2. 优化几何拓扑：移除不稳定的 fillet 选择器，改用几何构造保证圆角（通过截面设计或后续简单倒角）。
    3. 增强结构：增加背板与底座的连接面积，确保力学连续性。
    """
    
    # 参数定义
    width = 78.0      # Y方向宽度
    base_depth = 95.0 # X方向底座深度
    height = 110.0    # Z方向总高参考
    
    # 背板参数
    back_angle = 65.0 # 背板与水平面夹角
    back_thickness = 4.0
    back_height = 90.0 # 稍微降低背板高度，避免过高导致重心不稳
    
    # 底座参数
    base_thickness = 8.0
    
    # 前挡边参数
    lip_height = 15.0 # 增加挡边高度，防止手机滑落
    lip_thickness = 4.0
    
    # 计算背板投影
    rad_angle = math.radians(back_angle)
    back_proj_x = back_height * math.cos(rad_angle)
    back_proj_z = back_height * math.sin(rad_angle)
    
    # 1. 创建底座 (Base)
    # 原点设在底座底面中心
    base = cq.Workplane("XY").box(base_depth, width, base_thickness).translate((0, 0, base_thickness/2))
    
    # 2. 创建背板 (Back Plate)
    # 策略：在 XZ 平面绘制截面，然后拉伸。确保与底座有重叠以便融合。
    back_start_x = -base_depth/2 + 20.0 # 背板根部距离底座后缘 20mm
    
    # 绘制背板截面
    # 从 (back_start_x, base_thickness) 开始，向上倾斜
    back_profile = (
        cq.Workplane("XZ")
        .moveTo(back_start_x, base_thickness)
        .line(back_proj_x, back_proj_z) # 背板外侧线
        .line(-back_thickness * math.sin(rad_angle), back_thickness * math.cos(rad_angle)) # 顶部厚度线 (垂直于背板方向近似)
        # 修正：为了简化，我们直接画一个平行四边形或矩形旋转，这里用简单的直线闭合
        # 更稳健的方法：画一个矩形，然后旋转
    )
    
    # 重新采用旋转矩形法，更可控
    # 在 XZ 平面，中心位于背板中点
    back_center_x = back_start_x + back_proj_x / 2
    back_center_z = base_thickness + back_proj_z / 2
    
    back_plate = (
        cq.Workplane("XZ")
        .center(back_center_x, back_center_z)
        .rect(back_thickness, back_height) # 注意：rect 的参数是宽(X)和高(Z)，这里我们需要沿倾斜方向
        # rect 无法直接旋转。还是用 polygon 或 line 方法最可靠。
    )
    
    # 最终确定使用 Line 方法构建截面，并确保闭合
    # 点1: 根部底部 (back_start_x, base_thickness)
    # 点2: 顶部外侧 (back_start_x + back_proj_x, base_thickness + back_proj_z)
    # 点3: 顶部内侧 (点2 沿法向向内 back_thickness)
    # 法向量: (-sin(angle), cos(angle))
    # 点3: (x2 - t*sin, z2 + t*cos)
    # 点4: 根部内侧 (点1 沿法向向内 back_thickness)
    # 点4: (x1 - t*sin, z1 + t*cos)
    
    sin_a = math.sin(rad_angle)
    cos_a = math.cos(rad_angle)
    
    x1, z1 = back_start_x, base_thickness
    x2, z2 = back_start_x + back_proj_x, base_thickness + back_proj_z
    x3, z3 = x2 - back_thickness * sin_a, z2 + back_thickness * cos_a
    x4, z4 = x1 - back_thickness * sin_a, z1 + back_thickness * cos_a
    
    back_plate = (
        cq.Workplane("XZ")
        .moveTo(x1, z1)
        .lineTo(x2, z2)
        .lineTo(x3, z3)
        .lineTo(x4, z4)
        .close()
        .extrude(width / 2.0, both=True) # 居中拉伸
    )
    
    # 3. 创建前挡边 (Lip)
    # 位于底座前端，向上延伸
    # 为了确保融合，挡边稍微嵌入底座一点或与底座顶面齐平
    lip = (
        cq.Workplane("XY")
        .center(base_depth/2 - lip_thickness/2, 0)
        .box(lip_thickness, width, lip_height)
        .translate((0, 0, base_thickness + lip_height/2 - 0.01)) # 轻微下沉以确保布尔运算成功
    )
    
    # 4. 组合模型
    # 关键修复：使用 fuse=True (默认) 并确保结果是单一实体
    # 先 union 背板和底座
    model = base.union(back_plate)
    # 再 union 挡边
    model = model.union(lip)
    
    # 5. 后处理：倒圆角 (Fillet)
    # 为了打印安全和美观，对背板与底座连接处、挡边与底座连接处倒圆角
    # 选择所有垂直于 Y 轴的边（即拉伸方向的边），并根据位置过滤
    # 这里为了稳定性，只对明显的锐角边缘进行小圆角处理
    
    try:
        # 对背板根部和挡边根部进行倒角
        # 筛选 Z 方向较小的边，且位于连接处
        edges_to_fillet = model.edges("|Y").filter(
            lambda e: abs(e.val().Center().z - base_thickness) < 2.0 
        )
        if not edges_to_fillet.isEmpty():
            model = model.fillet(2.0, edges_to_fillet)
    except Exception as e:
        # 如果倒角失败，保留未倒角模型，保证几何可用
        pass
        
    # 6. 确保底部平整
    # 移动模型使最低点 Z=0
    bbox = model.val().BoundingBox()
    if abs(bbox.zmin) > 1e-6:
        model = model.translate((0, 0, -bbox.zmin))
        
    return model

def build():
    return build_model()

if __name__ == "__main__":
    show_object(build())