# DJI 电机控制程序

基于 `libcontrolcan.so` 的 DJI 电机控制程序，支持6个电机的实时控制，位置单位使用毫米。

## 📁 项目结构

```
SoftRobo_Control/
├── CAN/
│   └── libcontrolcan.so          # ControlCAN驱动库
├── examples/
│   └── raw_api_example.py        # 裸API调用示例（学习用）
├── tests/                         # 测试和临时文档
│   ├── CAN_FIX.md
│   ├── POSITION_MODE_FIX.md
│   ├── USAGE_GUIDE.md
│   └── ...
├── motor_control.py               # 交互式菜单控制程序
├── realtime_control.py            # 实时控制系统 ⭐推荐
└── README.md                      # 本文件
```

## 🚀 快速开始

### 实时控制系统（推荐）

```bash
cd /home/wuyuhao/SoftRobo_Control
python3 realtime_control.py
```

然后使用交互命令：
```bash
>>> start              # 启动系统
>>> set 1 30 10        # 电机1以30RPM相对移动10mm
>>> enable 1           # 启用电机1
>>> status             # 查看状态
>>> disable 1          # 停止电机1
>>> stop               # 关闭系统
```

### 交互式菜单程序

```bash
python3 motor_control.py
# 按照菜单提示操作
```

## 🎯 核心功能

### 1. 相对移动（默认，推荐）
```bash
>>> set 1 30 10        # 从当前位置向前移动10mm
>>> set 1 30 -5        # 从当前位置向后移动5mm
```

### 2. 绝对位置
```bash
>>> moveto 1 30 100    # 移动到绝对位置100mm
```

### 3. 位置重置
```bash
>>> reset 1            # 重置电机1位置为0
```

### 4. 多电机控制
```bash
>>> enable_all         # 启用所有电机
>>> disable_all        # 停止所有电机
```

## 📐 位置换算

- **轮子直径**: 17mm
- **圆周长**: 53.41mm
- **编码器分辨率**: 8192 计数/圈
- **换算系数**: 1mm ≈ 153.4 编码器计数

## ⚙️ 硬件要求

- CANalyst-II (USBCAN-II) USB转CAN设备
- DJI电机（支持1-6号）
- Linux系统

## 📚 详细文档

- [使用指南](tests/USAGE_GUIDE.md) - 详细的命令说明和使用示例
- [CAN设备修复](tests/CAN_FIX.md) - VCI_OpenDevice返回失败的解决方案
- [位置模式说明](tests/POSITION_MODE_FIX.md) - 相对移动vs绝对位置

## ⚠️ 注意事项

1. 默认使用**相对移动模式**，更符合实际使用习惯
2. 首次测试建议使用低速（10-20 RPM）
3. 实时控制系统会在后台持续发送命令（10Hz），防止电机超时
4. 所有测试文件都在 `tests/` 目录

## 🎉 特性

✅ 位置单位使用毫米（自动转换为编码器计数）  
✅ 支持相对移动和绝对位置两种模式  
✅ 后台线程持续发送命令，防止超时  
✅ 线程安全的状态管理  
✅ 独立控制每个电机的启用/禁用  
✅ 实时状态监控和显示  

## 📝 开发记录

- 初始版本：封装的MotorController类
- v2.0：改为裸API调用，增强透明度
- v3.0：实时控制系统，后台线程持续发送
- v3.1：位置单位改为毫米
- v3.2：修复CAN设备打开失败问题
- v3.3：添加相对移动模式（当前版本）
