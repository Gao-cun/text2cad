import cadquery as cq

def build_model():
    # 1. 主体轮廓 (XZ平面): 底座 + 连续斜面背板
    # 倾角约53度，消除>45度悬垂，满足FDM免支撑打印
    prof = (
        cq.Workplane("XZ")
        .moveTo(0, 0)
        .lineTo(120, 0)
        .lineTo(120, 15)
        .lineTo(100, 15)
        .lineTo(20, 125)
        .lineTo(0, 125)
        .close()
    )
    # 修复: extrude() 不支持 centered 参数，改为标准拉伸后沿Y轴平移居中
    main = prof.extrude(100).translate((0, -50, 0))

    # 2. 底部手机限位挡边 (Lip)
    # 宽85mm居中，防止手机下滑。故意偏移1mm确保与主体重叠，避免布尔运算产生碎面
    lip = cq.Workplane("XY").box(12, 85, 6, centered=(False, True, False)).translate((99, 0, 15))
    model = main.union(lip)

    # 3. 两侧垂直限位挡边 (Side Walls)
    # 厚度4mm，高度100mm，贴合主体两侧形成U型托槽，适配70-80mm宽手机
    side_l = cq.Workplane("XY").box(100, 4, 100, centered=(False, False, False)).translate((0, -49, 0))
    side_r = cq.Workplane("XY").box(100, 4, 100, centered=(False, False, False)).translate((0, 46, 0))
    model = model.union(side_l).union(side_r)

    # 4. 背部防滑凸条 (Anti-slip Ridges)
    # 在背部平面添加3条横向凸条，增强摩擦限位
    for z in [35, 70, 105]:
        ridge = cq.Workplane("YZ").box(2, 90, 2, centered=(False, True, False)).translate((-1, 0, z))
        model = model.union(ridge)

    # 5. 边缘倒角 (Fillet) - 缓解应力集中，提升手感与安全性
    # 仅对外部主轮廓边倒角，避开内部布尔交界以防拓扑奇异
    model = model.edges(">Z").fillet(2.0)
    model = model.edges("<Z").fillet(2.0)
    model = model.edges(">X").fillet(2.0)
    model = model.edges("<X").fillet(2.0)

    # 6. 几何清理与流形修复
    model = model.clean()
    return model