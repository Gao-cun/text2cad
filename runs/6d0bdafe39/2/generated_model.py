import cadquery as cq

def build_model():
    """
    构建一个简化的四门轿车模型，适用于3D打印。
    尺寸：长120mm, 宽50mm, 高35mm
    风格：极简，圆润，低多边形友好
    修复：移除了导致 'Nothing to loft' 错误的无效 loft 代码，
    采用稳健的 Side Profile Extrude + Fillet 方法生成车身。
    """
    
    # --- 参数定义 ---
    car_length = 120.0
    car_width = 50.0
    car_height = 35.0
    wheel_radius = 12.0
    wheel_thickness = 10.0
    ground_clearance = 5.0
    
    # --- 1. 车身主体 (Body) ---
    # 采用侧视图轮廓挤压法，这是生成汽车侧面最稳健的方法
    
    # 侧视图轮廓 (Side Profile in XZ plane)
    # 注意：Z轴向上，X轴向右。Y轴将是挤压方向（宽度）。
    side_profile = (
        cq.Workplane("XZ")
        .moveTo(-car_length/2, 0)          # 车尾底部
        .lineTo(-car_length/2 + 10, 0)     # 后保险杠底
        .lineTo(-car_length/2 + 15, 8)     # 后轮拱前起
        .lineTo(-car_length/2 + 25, 8)     # 后轮拱后落
        .lineTo(-car_length/4, 8)          # 车门下沿
        .lineTo(-car_length/4 + 5, 22)     # C柱底部
        .lineTo(-car_length/4 + 15, 28)    # 车顶后部
        .lineTo(car_length/4 - 15, 28)     # 车顶前部
        .lineTo(car_length/4 - 5, 22)      # A柱顶部
        .lineTo(car_length/4, 8)           # 引擎盖前端
        .lineTo(car_length/2 - 25, 8)      # 前轮拱后落
        .lineTo(car_length/2 - 15, 8)      # 前轮拱前起
        .lineTo(car_length/2 - 10, 0)      # 前保险杠底
        .lineTo(car_length/2, 0)           # 车头最前端
        .lineTo(car_length/2, 5)           # 车头高度
        .lineTo(-car_length/2, 5)          # 车尾高度 (封闭底部)
        .close()
    )
    
    # 挤压出宽度
    # extrude 沿 Y 轴方向
    body_raw = side_profile.extrude(car_width, both=False)
    
    # 移动到底部中心对齐 (Y方向居中)
    body_raw = body_raw.translate((0, -car_width/2, 0))
    
    # 添加圆角使表面光滑 (Fillet edges)
    # 使用 try-except 保护 fillet，防止因几何拓扑复杂导致失败
    try:
        body_filleted = (
            body_raw
            .edges("|Z")
            .fillet(2.0) # 垂直棱边倒角
        )
        # 进一步处理水平边缘，模拟车身曲面过渡
        body_filleted = (
            body_filleted
            .edges("<Y")
            .fillet(1.5) # 侧面水平棱边
        )
    except Exception:
        # 如果 fillet 失败，保留原始挤压体，确保模型可生成
        body_filleted = body_raw
    
    # --- 2. 车窗细节 (Windows) ---
    # 通过在侧面切割凹槽来模拟车窗
    # 使用一个简单的矩形切割整个侧面，形成“带状”车窗效果，简化几何以保证鲁棒性
    window_cut = (
        cq.Workplane("XY")
        .workplane(offset=15) # 高度位置，大约在车门上方
        .transformed(rotate=(0, 90, 0)) # 旋转到侧面视角
        .rect(car_length * 0.6, 8) # 车窗长度和高度
        .extrude(car_width + 10, both=True) # 切穿车身
    )
    
    try:
        body_with_windows = body_filleted.cut(window_cut)
    except Exception:
        body_with_windows = body_filleted
    
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
        try:
            tread = (
                cq.Workplane("XY")
                .circle(wheel_radius - 1)
                .circle(wheel_radius - 3)
                .extrude(wheel_thickness + 2, both=True)
            )
            wheel = wheel.cut(tread)
        except Exception:
            pass
        return wheel

    wheel_model = make_wheel()
    
    # 车轮位置计算
    wheel_offset_x = car_length / 2 - 20
    # 车轮稍微突出车身，但不要太远
    wheel_offset_y = car_width / 2 + wheel_thickness / 2 - 2 
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
    
    # 坐标对齐
    # 基线要求固定边界盒: [0.0, -25.0, -17.5, 120.0, 25.0, 17.5]
    # 即: X:[0, 120], Y:[-25, 25], Z:[-17.5, 17.5]
    
    current_bb = car.val().BoundingBox()
    x_min = current_bb.xmin
    y_min = current_bb.ymin
    z_min = current_bb.zmin
    
    # 计算平移量
    dx = 0.0 - x_min
    dy = -25.0 - y_min
    dz = -17.5 - z_min
    
    final_car = car.translate((dx, dy, dz))
    
    return final_car

# 入口点
MODEL = build_model()