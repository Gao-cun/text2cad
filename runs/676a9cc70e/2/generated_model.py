import cadquery as cq
import math

def build_model():
    # 基础参数
    base_w, base_d, base_h = 90.0, 80.0, 5.0
    back_w, back_d, back_h = 70.0, 15.0, 75.0
    tilt_angle = 20.0  # 后倾角（度）
    lip_w, lip_d, lip_h = 60.0, 3.0, 5.0

    # 1. 底座
    base = cq.Workplane("XY").box(base_w, base_d, base_h)
    # 底座后上边缘预倒角（与背板交汇处应力缓解，半径3.0mm）
    base = base.edges(">Y and >Z").fillet(3.0)

    # 2. 背部支撑板（倾斜）
    backrest = cq.Workplane("XY").box(back_w, back_d, back_h)
    # 定位：使底部前缘与底座后缘顶部对齐
    backrest = backrest.translate((0, base_d/2 + back_d/2, base_h + back_h/2))
    # 背板底部前边缘预倒角
    backrest = backrest.edges("<Y and <Z").fillet(3.0)
    # 绕底部前缘中心 (0, 40, 5) 旋转，实现后倾
    backrest = backrest.rotate((0, base_d/2, base_h), (1, 0, 0), tilt_angle)

    # 3. 合并底座与背板
    model = base.union(backrest)

    # 4. 前挡边（手机限位）
    # 计算旋转后背板顶部前缘中心坐标
    pivot_y, pivot_z = base_d/2, base_h
    top_front_rel_y = back_d/2
    top_front_rel_z = back_h/2
    rad = math.radians(tilt_angle)
    lip_y = pivot_y + top_front_rel_y * math.cos(rad) - top_front_rel_z * math.sin(rad)
    lip_z = pivot_z + top_front_rel_y * math.sin(rad) + top_front_rel_z * math.cos(rad)
    # 挡边放置在顶部前缘，向前（-Y方向）突出
    lip = cq.Workplane("XY").box(lip_w, lip_d, lip_h)
    lip = lip.translate((0, lip_y - lip_d/2, lip_z + lip_h/2))
    model = model.union(lip)

    # 5. 全局倒角与圆角处理（打印优化 & 视觉要求）
    # 底部边缘保持平整以确保求解器识别固定面，仅做极小倒角防割手
    model = model.edges("<Z").fillet(1.0)
    # 顶部及外露边缘
    model = model.edges(">Z").fillet(2.0)
    # 侧边及背板过渡边
    model = model.edges("|Z").fillet(2.5)
    # 手机接触面（挡边顶部前沿）倒角防刮
    model = model.faces(">Z").edges("<Y").chamfer(1.0)

    return model