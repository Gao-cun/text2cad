import cadquery as cq

def build_model():
    """
    构建一个简化的四门轿车模型，适用于3D打印。
    尺寸：长120mm, 宽50mm, 高35mm (相对于中心点)
    风格：极简，圆润，低多边形友好
    """
    
    # --- 参数定义 ---
    car_length = 120.0
    car_width = 50.0
    car_height = 35.0
    wheel_radius = 12.0
    wheel_thickness = 10.0
    ground_clearance = 5.0
    
    # --- 1. 车身主体 (Body) ---
    # 使用 loft 或 fillet 创建流线型车身
    # 底部轮廓 (Bottom Profile) - 略宽于顶部以提供稳定性
    bottom_sketch = (
        cq.Workplane("XZ")
        .moveTo(-car_length/2 + 5, -car_height/2 + ground_clearance)
        .lineTo(car_length/2 - 5, -car_height/2 + ground_clearance)
        .lineTo(car_length/2, -car_height/2 + ground_clearance + 5)
        .lineTo(-car_length/2, -car_height/2 + ground_clearance + 5)
        .close()
    )
    
    # 顶部轮廓 (Top Profile/Cabin) - 较窄，形成车顶
    top_sketch = (
        cq.Workplane("XZ")
        .workplane(offset=car_height * 0.6) # 抬高到车顶位置
        .moveTo(-car_length/4, -car_height/2 + ground_clearance + 5)
        .lineTo(car_length/4, -car_height/2 + ground_clearance + 5)
        .lineTo(car_length/4 - 5, car_height/2)
        .lineTo(-car_length/4 + 5, car_height/2)
        .close()
    )
    
    # 通过放样生成基本车身形状
    body_base = (
        cq.Workplane("YX")
        .loft([bottom_sketch, top_sketch], combine=True, clean=True)
    )
    
    # 对车身进行整体缩放和修整以匹配目标宽度
    # 由于loft在XZ平面，我们需要确保Y方向宽度正确
    # 上面的loft实际上生成的是沿Y轴延伸的实体吗？不，loft通常在两个工作平面之间。
    # 修正策略：使用 extrude 配合 fillet 更稳健地生成“玩具车”风格
    
    # 重新采用更稳健的 Extrude + Fillet 方法
    # 侧视图轮廓 (Side Profile in XZ plane)
    side_profile = (
        cq.Workplane("XZ")
        .moveTo(-car_length/2, 0)
        .lineTo(-car_length/2 + 10, 0) # 后保险杠底部
        .lineTo(-car_length/2 + 15, 8) # 后轮拱前
        .lineTo(-car_length/2 + 25, 8) # 后轮拱后
        .lineTo(-car_length/4, 8)      # 车门下沿
        .lineTo(-car_length/4 + 5, 22) # C柱底部
        .lineTo(-car_length/4 + 15, 28) # 车顶后部
        .lineTo(car_length/4 - 15, 28)  # 车顶前部
        .lineTo(car_length/4 - 5, 22)   # A柱顶部
        .lineTo(car_length/4, 8)        # 引擎盖前端
        .lineTo(car_length/2 - 25, 8)   # 前轮拱后
        .lineTo(car_length/2 - 15, 8)   # 前轮拱前
        .lineTo(car_length/2 - 10, 0)   # 前保险杠底部
        .lineTo(car_length/2, 0)        # 车头最前端
        .lineTo(car_length/2, 5)        # 车头高度
        .lineTo(-car_length/2, 5)       # 车尾高度 (简化为矩形截面基础)
        .close()
    )
    
    # 挤压出宽度
    body_raw = side_profile.extrude(car_width, both=False)
    
    # 移动到底部中心对齐
    body_raw = body_raw.translate((0, -car_width/2, 0))
    
    # 添加圆角使表面光滑 (Fillet edges)
    # 选择垂直边缘和顶部边缘进行倒角，模拟流线型
    body_filleted = (
        body_raw
        .edges("|Z")
        .fillet(2.0) # 垂直棱边倒角
        .edges("<Y")
        .fillet(1.5) # 侧面水平棱边
    )
    
    # --- 2. 车窗细节 (Windows) ---
    # 通过在侧面切割凹槽来模拟车窗
    window_cut = (
        cq.Workplane("YZ")
        .workplane(offset=-car_length/4 + 5) # 定位到A柱附近
        .rect(35, 12) # 侧窗大致尺寸
        .extrude(10, both=True) # 切穿车身
    )
    
    # 更精确的车窗切割：分别切割前后窗
    # 前侧窗
    front_window = (
        cq.Workplane("XY")
        .workplane(offset=10) # 高度
        .transformed(rotate=(0, 90, 0)) # 旋转到侧面
        .moveTo(-car_length/4 + 2, 0)
        .lineTo(car_length/4 - 2, 0)
        .lineTo(car_length/4 - 6, 12)
        .lineTo(-car_length/4 + 6, 12)
        .close()
        .extrude(car_width + 2, both=True) # 稍微切宽一点确保穿透
    )
    
    body_with_windows = body_filleted.cut(front_window)
    
    # --- 3. 车轮 (Wheels) ---
    # 创建单个车轮，然后阵列
    def make_wheel():
        # 轮胎
        tire = cq.Workplane("XY").circle(wheel_radius).extrude(wheel_thickness)
        # 轮毂
        hub = cq.Workplane("XY").circle(wheel_radius * 0.6).extrude(wheel_thickness + 1)
        # 合并
        wheel = tire.union(hub)
        # 添加简单的胎纹（环形凹槽）
        tread = (
            cq.Workplane("XY")
            .circle(wheel_radius - 1)
            .circle(wheel_radius - 3)
            .extrude(wheel_thickness + 2, both=True)
        )
        wheel = wheel.cut(tread)
        return wheel

    wheel_model = make_wheel()
    
    # 车轮位置
    wheel_offset_x = car_length / 2 - 20
    wheel_offset_y = car_width / 2 + wheel_thickness / 2 - 2 # 稍微突出车身
    wheel_z = -car_height / 2 + ground_clearance + wheel_radius
    
    # 放置四个车轮
    wheels = (
        wheel_model
        .translate((wheel_offset_x, wheel_offset_y, wheel_z))
        .union(wheel_model.translate((-wheel_offset_x, wheel_offset_y, wheel_z)))
        .union(wheel_model.translate((wheel_offset_x, -wheel_offset_y, wheel_z)))
        .union(wheel_model.translate((-wheel_offset_x, -wheel_offset_y, wheel_z)))
    )
    
    # --- 4. 组装与最终调整 ---
    # 合并车身和车轮
    car = body_with_windows.union(wheels)
    
    # 确保模型位于正确的坐标系中心
    # 当前中心可能在几何中心，根据需求调整到 [0,0,0] 附近或保持相对位置
    # 基线要求固定边界盒起始于 x=0? 不，基线给出的是绝对坐标范围
    # Fixed BBox: [0.0, -25.0, -17.5, 120.0, 25.0, 17.5]
    # 这意味着模型应该从 x=0 延伸到 x=120。目前模型是以 0 为中心的 (-60 到 60)。
    # 需要平移模型以匹配基线坐标系统。
    
    current_bb = car.val().BoundingBox()
    x_min = current_bb.xmin
    y_min = current_bb.ymin
    z_min = current_bb.zmin
    
    # 目标：xmin -> 0, ymin -> -25, zmin -> -17.5
    dx = 0 - x_min
    dy = -25 - y_min
    dz = -17.5 - z_min
    
    final_car = car.translate((dx, dy, dz))
    
    return final_car

# 入口点
MODEL = build_model()