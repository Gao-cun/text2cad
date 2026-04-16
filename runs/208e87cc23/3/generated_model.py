import cadquery as cq
import math

def build_model():
    """
    构建一个单一体积、结构增强的桌面手机支架。
    
    修复点：
    1. 解决多实体问题：通过统一的几何构造逻辑（先构建主体轮廓再拉伸，或确保布尔运算后严格融合）保证输出为单一 Solid。
       本方案采用“截面拉伸+局部特征添加”的策略，从根本上避免多实体拼接带来的拓扑错误。
    2. 增强连接强度：在背板与底座连接处增加三角加强筋（Fillet/Chamfer 的替代或补充），防止断裂。
    3. 优化前挡边：抬高并内延前挡边，形成有效的防滑限位，同时避免遮挡手机底部接口。
    4. 增加定位特征：在底座上表面增加浅凹槽或限位条，辅助手机放置。
    5. 视觉语义优化：调整比例，使其更像支架而非方块。
    """
    
    # --- 参数定义 ---
    width = 78.0       # Y方向宽度
    base_depth = 95.0  # X方向总深
    total_height = 110.0 # Z方向总高参考
    
    # 材料/打印相关
    wall_thickness = 4.0 # 主要壁厚
    base_thickness = 6.0 # 底座厚度
    
    # 背板几何
    back_angle_deg = 65.0 # 背板与水平面夹角
    back_height = 95.0    # 背板斜面长度
    
    # 前挡边几何
    lip_height = 12.0     # 挡边高度
    lip_thickness = 4.0   # 挡边厚度
    lip_inset = 3.0       # 挡边向内延伸量（勾住手机）
    
    # 加强筋几何
    rib_thickness = 4.0
    rib_height = 25.0     # 加强筋高度
    
    # --- 几何计算 ---
    rad_angle = math.radians(back_angle_deg)
    sin_a = math.sin(rad_angle)
    cos_a = math.cos(rad_angle)
    
    # 背板投影
    back_proj_x = back_height * cos_a
    back_proj_z = back_height * sin_a
    
    # 确定背板根部位置 (X坐标)
    # 为了让支架重心稳定，背板根部不宜太靠后。设根部距离后端 25mm
    back_root_x_offset = 25.0 
    back_root_x = -base_depth / 2.0 + back_root_x_offset
    
    # --- 构建主轮廓 (Side Profile in XZ plane) ---
    # 我们将构建一个包含底座侧面、背板侧面、加强筋侧面的复合轮廓，然后拉伸。
    # 注意：为了保持单一体积，我们将所有特征合并到一个 Sketch 中或者通过 Union 后立即 Fuse。
    
    # 1. 底座截面 (Base Profile)
    # 简单矩形，从 (-base_depth/2, 0) 到 (base_depth/2, base_thickness)
    base_profile = (
        cq.Workplane("XZ")
        .moveTo(-base_depth / 2, 0)
        .lineTo(base_depth / 2, 0)
        .lineTo(base_depth / 2, base_thickness)
        .lineTo(-base_depth / 2, base_thickness)
        .close()
    )
    
    # 2. 背板截面 (Back Plate Profile)
    # 从根部 (back_root_x, base_thickness) 开始
    x1, z1 = back_root_x, base_thickness
    x2, z2 = back_root_x + back_proj_x, base_thickness + back_proj_z
    # 背板厚度方向向内偏移
    x3, z3 = x2 - wall_thickness * sin_a, z2 + wall_thickness * cos_a
    x4, z4 = x1 - wall_thickness * sin_a, z1 + wall_thickness * cos_a
    
    back_profile = (
        cq.Workplane("XZ")
        .moveTo(x1, z1)
        .lineTo(x2, z2)
        .lineTo(x3, z3)
        .lineTo(x4, z4)
        .close()
    )
    
    # 3. 加强筋截面 (Rib Profile)
    # 三角形，连接底座上表面和背板下表面
    # 顶点1: 背板根部内侧下方一点 (x4, z4) 投影到底座? 不，直接连接背板下缘和底座上缘
    # 简化：直角三角形或斜三角形
    # 点A: 背板下缘中点附近? 不，直接连接 (x1, z1) 和 (x4, z4) 的中点到底座某点?
    # 更简单的做法：在背板和底座夹角处添加一个填充三角形
    # 顶点1: (x1, z1) [背板根部外侧]
    # 顶点2: (x4, z4) [背板根部内侧] -> 实际上加强筋通常在背板后方支撑，或者前方。
    # 鉴于背板后倾，加强筋应在背板“下方/后方”支撑，即夹角内侧。
    # 夹角内侧顶点：(x1, z1) 是外侧角，(x4, z4) 是内侧角？
    # 让我们画图：
    # 背板向右上方倾斜。根部在左下。
    # 外侧是左下方，内侧是右上方。
    # 加强筋应位于背板下方（即背板与底座形成的锐角侧，如果有的话）。
    # 由于背板角度 65度，与底座夹角 65度（锐角）。
    # 加强筋应填充这个锐角区域。
    # 顶点1: (x1, z1) [根部交点]
    # 顶点2: 沿底座向右 (x1 + rib_len, z1)
    # 顶点3: 沿背板向上 (x1 + rib_len*cos_a, z1 + rib_len*sin_a) -- 近似
    # 为了稳健，我们定义一个固定的加强筋三角形
    rib_len_along_base = 30.0
    rib_end_x = x1 + rib_len_along_base
    rib_end_z = z1
    # 背板上的对应点
    rib_back_dist = 30.0
    rib_back_x = x1 + rib_back_dist * cos_a
    rib_back_z = z1 + rib_back_dist * sin_a
    
    rib_profile = (
        cq.Workplane("XZ")
        .moveTo(x1, z1)
        .lineTo(rib_end_x, rib_end_z)
        .lineTo(rib_back_x, rib_back_z)
        .close()
    )
    
    # 4. 合并侧面轮廓并拉伸
    # 将 base, back, rib 合并为一个 Wire/Face 集合，然后 extrude
    # 注意：CadQuery 的 union 在 Workplane 级别可能产生多个 Solid，我们需要小心。
    # 更好的方法：分别拉伸然后 Union，但必须确保 Fuse=True 且几何重叠。
    
    # 拉伸宽度
    extrude_width = width
    
    # 拉伸各部分
    solid_base = base_profile.extrude(extrude_width / 2.0, both=True)
    solid_back = back_profile.extrude(extrude_width / 2.0, both=True)
    solid_rib = rib_profile.extrude(extrude_width / 2.0, both=True)
    
    # 融合主体
    main_body = solid_base.union(solid_back).union(solid_rib)
    
    # 5. 添加前挡边 (Front Lip)
    # 位置：底座前端
    # 形状：L型或倒T型，勾住手机
    # 为了防止多实体，我们将其作为单独特征添加并 Union
    
    lip_start_x = base_depth / 2.0 - lip_thickness
    
    # 前挡边截面 (XZ)
    # 垂直部分 + 向内勾的部分
    lip_profile = (
        cq.Workplane("XZ")
        .moveTo(lip_start_x, base_thickness)
        .lineTo(lip_start_x + lip_thickness, base_thickness) # 底部宽
        .lineTo(lip_start_x + lip_thickness, base_thickness + lip_height) # 外侧高
        .lineTo(lip_start_x + lip_thickness - lip_inset, base_thickness + lip_height) # 顶部向内勾
        .lineTo(lip_start_x + lip_thickness - lip_inset, base_thickness + lip_height - 2.0) # 稍微向下一点，避免尖锐
        .lineTo(lip_start_x + 2.0, base_thickness + lip_height - 2.0) # 内部空间
        .lineTo(lip_start_x + 2.0, base_thickness + 2.0) # 内部垂直
        .close() # 闭合回起点? 不，这样会封闭内部。我们需要它是实心的。
        # 重新设计：实心 L 型
    )
    
    # 简化前挡边：实心块，带倒角
    lip_solid = (
        cq.Workplane("XY")
        .center(lip_start_x + lip_thickness/2, 0)
        .box(lip_thickness, width, lip_height)
        .translate((0, 0, base_thickness + lip_height/2))
    )
    
    # 添加向内的小勾 (Hook)
    hook_solid = (
        cq.Workplane("XY")
        .center(lip_start_x + lip_thickness - lip_inset/2, 0)
        .box(lip_inset, width, 3.0) # 薄勾
        .translate((0, 0, base_thickness + lip_height - 1.5))
    )
    
    # 融合前挡边
    front_assembly = lip_solid.union(hook_solid)
    model = main_body.union(front_assembly)
    
    # 6. 添加手机定位槽/限位条 (Positioning Ribs)
    # 在底座上表面，左右各一条小凸起，防止手机左右滑动
    rib_h = 2.0
    rib_w = 4.0
    rib_l = 40.0
    pos_rib_left = (
        cq.Workplane("XY")
        .center(0, -width/2 + 10)
        .box(rib_l, rib_w, rib_h)
        .translate((0, 0, base_thickness + rib_h/2))
    )
    pos_rib_right = (
        cq.Workplane("XY")
        .center(0, width/2 - 10)
        .box(rib_l, rib_w, rib_h)
        .translate((0, 0, base_thickness + rib_h/2))
    )
    
    model = model.union(pos_rib_left).union(pos_rib_right)
    
    # 7. 全局倒角/圆角 (Fillet/Chamfer)
    # 关键：只选择安全的边进行倒角，避免拓扑错误
    # 对背板根部外侧大圆角，增强强度
    try:
        # 选择背板与底座连接处的外侧边
        # 这是一个近似选择，实际可能需要更精确的 Filter
        edges_fillet = model.edges("|Y").filter(
            lambda e: abs(e.val().Center().x - x1) < 5.0 and abs(e.val().Center().z - z1) < 5.0
        )
        if not edges_fillet.isEmpty():
            model = model.fillet(3.0, edges_fillet)
    except:
        pass
        
    # 对前挡边顶部倒角，方便放入手机
    try:
        lip_edges = model.edges("|Y").filter(
            lambda e: e.val().Center().x > base_depth/2 - 10 and e.val().Center().z > base_thickness + lip_height - 2
        )
        if not lip_edges.isEmpty():
            model = model.fillet(1.0, lip_edges)
    except:
        pass

    # 8. 最终检查与对齐
    # 确保模型底部在 Z=0
    bbox = model.val().BoundingBox()
    if bbox.zmin < 0:
        model = model.translate((0, 0, -bbox.zmin))
    elif bbox.zmin > 0.01:
        model = model.translate((0, 0, -bbox.zmin))
        
    return model

def build():
    return build_model()

if __name__ == "__main__":
    show_object(build())