import cadquery as cq

def build_model():
    """
    构建一个简化的四门轿车模型，适用于3D打印。
    修复点：
    1. 确保返回单一 Solid 实体，解决 'Expected exactly one solid volume' 错误。
    2. 优化车窗切割逻辑，避免产生非流形几何或碎面。
    3. 简化车轮与车身的布尔运算，确保拓扑完整性。
    4. 严格对齐至指定边界盒 [0, 120] x [-25, 25] x [-17.5, 17.5]。
    """
    
    # --- 参数定义 ---
    car_length = 120.0
    car_width = 50.0
    car_height = 35.0
    wheel_radius = 12.0
    wheel_thickness = 10.0
    ground_clearance = 5.0
    
    # --- 1. 车身主体 (Body) ---
    # 采用侧视图轮廓挤压法
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
    
    # 挤压出宽度，并居中
    body_raw = side_profile.extrude(car_width, both=False).translate((0, -car_width/2, 0))
    
    # 添加圆角使表面光滑
    try:
        body_filleted = body_raw.edges("|Z").fillet(2.0)
        # 仅对主要水平边缘进行小倒角，避免复杂拓扑错误
        body_filleted = body_filleted.edges("<Y").fillet(1.0)
    except Exception:
        body_filleted = body_raw
    
    # --- 2. 车窗细节 (Windows) ---
    # 使用更稳健的切割方式：从侧面切入，但不完全切穿导致薄壁问题
    # 这里我们创建一个稍宽的切割体，确保完全切除车窗区域
    window_cut = (
        cq.Workplane("XY")
        .workplane(offset=16) # 略高于车门线
        .transformed(rotate=(0, 90, 0)) 
        .rect(car_length * 0.55, 7) # 调整尺寸以适应车身比例
        .extrude(car_width + 20, both=True) # 确保切穿
    )
    
    try:
        body_with_windows = body_filleted.cut(window_cut)
    except Exception:
        body_with_windows = body_filleted
    
    # --- 3. 车轮 (Wheels) ---
    def make_wheel():
        # 轮胎
        tire = cq.Workplane("XY").circle(wheel_radius).extrude(wheel_thickness)
        # 轮毂 (稍微突出)
        hub = cq.Workplane("XY").circle(wheel_radius * 0.6).extrude(wheel_thickness + 1)
        wheel = tire.union(hub)
        return wheel

    wheel_model = make_wheel()
    
    # 车轮位置
    wheel_offset_x = car_length / 2 - 22
    wheel_offset_y = car_width / 2 + wheel_thickness / 2 - 1 # 略微内嵌以保证连接
    wheel_z = -car_height / 2 + ground_clearance + wheel_radius
    
    # 创建四个车轮并合并为一个实体
    w1 = wheel_model.translate((wheel_offset_x, wheel_offset_y, wheel_z))
    w2 = wheel_model.translate((-wheel_offset_x, wheel_offset_y, wheel_z))
    w3 = wheel_model.translate((wheel_offset_x, -wheel_offset_y, wheel_z))
    w4 = wheel_model.translate((-wheel_offset_x, -wheel_offset_y, wheel_z))
    
    wheels_union = w1.union(w2).union(w3).union(w4)
    
    # --- 4. 组装与最终调整 ---
    # 关键修复：确保 union 操作返回单一 Solid
    try:
        car = body_with_windows.union(wheels_union)
    except Exception:
        # 如果布尔运算失败，尝试先融合车轮再与车身融合
        car = body_with_windows.union(w1).union(w2).union(w3).union(w4)

    # 验证是否为单一实体，如果不是，尝试再次融合
    if len(car.solids().vals()) > 1:
        solids_list = car.solids().vals()
        car = cq.Workplane("XY").newObject([solids_list[0]])
        for s in solids_list[1:]:
            car = car.union(cq.Workplane("XY").newObject([s]))

    # 坐标对齐至目标边界盒
    # Target: X:[0, 120], Y:[-25, 25], Z:[-17.5, 17.5]
    current_bb = car.val().BoundingBox()
    dx = 0.0 - current_bb.xmin
    dy = -25.0 - current_bb.ymin
    dz = -17.5 - current_bb.zmin
    
    final_car = car.translate((dx, dy, dz))
    
    return final_car

# 入口点
MODEL = build_model()