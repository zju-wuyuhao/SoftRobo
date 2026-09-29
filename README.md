# DJI 电机控制程序

基于 `libcontrolcan.so` 的 DJI 电机控制程序，提供裸API调用和交互式界面两种使用方式。

## 项目结构

```
SoftRobo_Control/
├── CAN/
│   └── libcontrolcan.so       # ControlCAN 驱动库
├── motor_control.py            # 交互式控制程序（推荐）
├── examples/
│   └── raw_api_example.py     # 裸API调用示例（学习用）
├── docs/
│   └── motor_runaway_diagnosis.md  # 安全诊断文档
└── README.md
```

## 快速开始

### 方式1：交互式程序（推荐日常使用）

```bash
cd /home/wuyuhao/SoftRobo_Control
python3 motor_control.py
```

特点：
- 菜单式界面，无需编辑代码
- 运行时输入参数
- 支持单电机/多电机控制
- 自动错误处理和安全停止

### 方式2：裸API示例（学习底层原理）

```bash
cd /home/wuyuhao/SoftRobo_Control
python3 examples/raw_api_example.py
```

特点：
- 完整展示每个VCI函数调用
- 手动构造CAN帧
- 适合学习底层机制

## 功能说明

### 1. 恒速控制
- 指定电机ID、转速RPM和运行时间
- 正数顺时针，负数逆时针
- 自动发送防超时命令

### 2. 位置控制
- 移动电机到目标编码器位置
- 可选的位置保持功能
- 防止超时漂移

### 3. 多电机同步
- 同时控制多个电机
- 统一的启动和停止时序
- 支持不同速度和位置

### 4. 紧急停止
- 一键停止所有6个电机
- 多次发送确保可靠性

## 硬件要求

- CANalyst-II (USBCAN-II) USB转CAN设备
- DJI电机（支持1-6号，CAN ID: 0x011-0x016, 0x031-0x036）
- Linux系统

## 安全注意事项

⚠️ **重要安全提示**

1. **首次测试**
   - 使用低速（10-20 RPM）
   - 空载运行
   - 准备紧急断电

2. **超时风险**
   - DJI电机需要持续接收命令（3-5秒间隔）
   - 本程序自动处理超时，但断电仍需手动准备

3. **限制建议**
   - 默认最大速度：50 RPM
   - 测试时建议更低速度
   - 观察终端所有警告信息

## API说明

### 核心VCI函数调用流程

```python
# 1. 加载库
dll = cdll.LoadLibrary("CAN/libcontrolcan.so")

# 2. 打开设备
dll.VCI_OpenDevice(4, 0, 0)  # 设备类型4=USBCAN2

# 3. 初始化CAN (500kbps)
init_config = VCI_INIT_CONFIG(0x80000000, 0xFFFFFFFF, 0, 2, 0x00, 0x14, 0)
dll.VCI_InitCAN(4, 0, 0, byref(init_config))

# 4. 启动CAN
dll.VCI_StartCAN(4, 0, 0)

# 5. 发送命令
dll.VCI_Transmit(4, 0, 0, byref(frame), 1)

# 6. 关闭设备
dll.VCI_CloseDevice(4, 0)
```

### CAN帧格式

**速度+位置命令**（8字节数据）：
```
[0xAA, 0xAA, rpm_high, rpm_low, pos_byte0, pos_byte1, pos_byte2, pos_byte3]
```

- `rpm`: 16位有符号整数（-32768 到 32767）
- `position`: 32位有符号整数

## 常见问题

### Q: 电机不转动？
A: 检查：
1. CANalyst-II是否正确连接
2. 电机电源是否打开
3. CAN总线终端电阻是否正确
4. 检查终端输出的错误信息

### Q: 电机突然高速旋转？
A: 这是超时失控现象，立即：
1. 按 Ctrl+C 停止程序
2. 或运行紧急停止：`python3 motor_control.py` 选择菜单4
3. 最后手段：切断电源

### Q: 如何学习底层API？
A: 
1. 阅读 `examples/raw_api_example.py`
2. 对比两个版本的实现差异
3. 每个示例都有详细注释

## 技术细节

### 辅助函数设计

程序提供最小化的辅助函数，仅避免重复代码：

- `rpm_to_bytes()` - RPM转字节
- `position_to_bytes()` - 位置转字节
- `build_command_frame()` - 构造命令帧
- `init_can_device()` - 设备初始化
- `stop_motor()` - 停止电机

这些函数保持了裸API的透明性，同时提高代码可读性。

### 错误处理

- 所有VCI函数返回值都会检查（1=成功）
- 设备打开失败时自动清理
- Ctrl+C中断时正确发送停止命令

## 开发历史

- 最初版本：完全封装的MotorController类
- 优化版本：裸API调用示例
- 当前版本：交互式程序 + 学习示例

## 许可

本项目使用的 `libcontrolcan.so` 库属于其原厂商所有。

## 参考资料

- [DJI电机CAN协议](docs/motor_runaway_diagnosis.md)
- CANalyst-II 用户手册
- ControlCAN API 文档
