import cadquery as cq
import math

def build_model():
    # 核心参数 (mm)
    base_L, base_W, base_H = 115.0, 95.0, 10.0
    wall_H = 55.0
    wall_D = 10.0
    tray_len = 42.0
    angle = 12.0
    lip_front_h = 8.0
    lip_back_h = 14.0
    lip_thick = 4.0
    side_lip_h = 10.0
    side_lip_thick = 4.0

    rad = math.radians(angle)
    dx = tray_len * math.cos(rad)
    dz = tray_len * math.sin(rad)

    # 1. 底座
    base = cq.Workplane('XY').box(base_L, base_W, base_H)

    # 2. 垂直背墙
    back_wall = cq.Workplane('XY').box(wall_D, base_W, wall_H)
    back_wall = back_wall.translate((base_L/2 - wall_D/2, 0, base_H + wall_H/2))

    # 3. 倾斜托盘
    tray = cq.Workplane('XY').box(tray_len, base_W - 10, 4.0)
    tray = tray.rotate((0, 0, 0), (0, 1, 0), -angle)
    tray_back_x = base_L/2 - wall_D/2
    tray_back_z = base_H + wall_H
    local_back_x = -tray_len/2 * math.cos(rad)
    local_back_z = tray_len/2 * math.sin(rad)
    tray = tray.translate((tray_back_x - local_back_x, 0, tray_back_z - local_back_z))

    # 4. 前挡边
    front_lip = cq.Workplane('XY').box(lip_thick, base_W - 10, lip_front_h)
    tray_front_x = tray_back_x + dx
    tray_front_z = tray_back_z + dz
    front_lip = front_lip.translate((tray_front_x - lip_thick/2, 0, tray_front_z - lip_front_h/2))

    # 5. 后挡边
    back_lip = cq.Workplane('XY').box(lip_thick, base_W - 10, lip_back_h)
    back_lip = back_lip.translate((tray_back_x - lip_thick/2, 0, tray_back_z + lip_back_h/2))

    # 6. 侧挡边
    side_lip = cq.Workplane('XY').box(tray_len, side_lip_thick, side_lip_h)
    tray_cx = (tray_back_x + tray_front_x) / 2
    tray_cz = (tray_back_z + tray_front_z) / 2
    left_lip = side_lip.translate((tray_cx, -base_W/2 - side_lip_thick/2, tray_cz))
    right_lip = side_lip.translate((tray_cx, base_W/2 + side_lip_thick/2, tray_cz))

    # 7. 布尔合并 (修复: 将 .fuse() 替换为 Workplane 标准的 .union())
    model = base.union(back_wall).clean()
    model = model.union(tray).clean()
    model = model.union(front_lip).clean()
    model = model.union(back_lip).clean()
    model = model.union(left_lip).union(right_lip).clean()

    # 8. 倒角处理 (防割手 & 缓解应力集中)
    model = model.edges('>Z').fillet(2.0)
    model = model.edges('<Z').fillet(1.5)
    model = model.edges('|Z').fillet(2.0)

    return model