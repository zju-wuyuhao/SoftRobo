"""裸API调用示例 - 直接使用 ctypes 调用 libcontrolcan.so

这个文件展示如何完全不使用封装类，直接调用 VCI_* 函数来控制 DJI 电机。

运行方式:
    cd /home/wuyuhao/SoftRobo_Control
    python3 examples/raw_api_example.py

注意：取消注释底部的示例函数来运行
"""

import time
from ctypes import Structure, c_ubyte, c_uint, cdll, byref


# ============================================================================
# 结构体定义（保留以避免手写复杂的 ctypes.Structure）
# ============================================================================

class VCI_INIT_CONFIG(Structure):
    """CAN初始化配置结构体"""
    _fields_ = [
        ("AccCode", c_uint),      # 验收码
        ("AccMask", c_uint),      # 屏蔽码
        ("Reserved", c_uint),     # 保留
        ("Filter", c_ubyte),      # 滤波方式
        ("Timing0", c_ubyte),     # 定时器0
        ("Timing1", c_ubyte),     # 定时器1
        ("Mode", c_ubyte),        # 工作模式
    ]


class VCI_CAN_OBJ(Structure):
    """CAN消息帧结构体"""
    _fields_ = [
        ("ID", c_uint),           # CAN ID
        ("TimeStamp", c_uint),    # 时间戳
        ("TimeFlag", c_ubyte),    # 时间标志
        ("SendType", c_ubyte),    # 发送类型
        ("RemoteFlag", c_ubyte),  # 远程帧标志
        ("ExternFlag", c_ubyte),  # 扩展帧标志
        ("DataLen", c_ubyte),     # 数据长度 (0-8)
        ("Data", c_ubyte * 8),    # 8字节数据
        ("Reserved", c_ubyte * 3),# 保留字节
    ]


# ============================================================================
# 常量定义
# ============================================================================

# 设备类型
DEVICE_TYPE_USBCAN2 = 4  # USBCAN-II (CANalyst-II)
DEFAULT_DEVICE_INDEX = 0
DEFAULT_CAN_INDEX = 0

# DJI电机ID映射
MOTOR_MODE_IDS = [0x011, 0x012, 0x013, 0x014, 0x015, 0x016]      # 模式设置ID
MOTOR_COMMAND_IDS = [0x031, 0x032, 0x033, 0x034, 0x035, 0x036]  # 命令ID

# 工作模式
MODE_VELOCITY_POSITION = 0x07  # 速度+位置模式


# ============================================================================
# 示例 1: 单电机恒速转动
# ============================================================================

def example_1_raw_velocity():
    """裸API调用 - 电机1恒速转动5秒"""

    print("\n" + "="*60)
    print("[示例1] 裸API调用 - 恒速转动")
    print("="*60 + "\n")

    # 步骤1: 加载动态链接库
    print("[步骤1] 加载 libcontrolcan.so...")
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    print("  [OK] 库已加载\n")

    # 步骤2: 打开CAN设备
    print("[步骤2] 打开CAN设备...")
    ret = dll.VCI_OpenDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, 0)
    if ret != 1:
        print("  [错误] 打开设备失败，返回值:", ret)
        return
    print("  [OK] 设备已打开\n")

    # 步骤3: 初始化CAN参数
    print("[步骤3] 初始化CAN参数 (500kbps)...")
    init_config = VCI_INIT_CONFIG(
        0x80000000,  # AccCode
        0xFFFFFFFF,  # AccMask
        0,           # Reserved
        2,           # Filter
        0x00,        # Timing0 (500kbps 的配置)
        0x14,        # Timing1
        0            # Mode (正常模式)
    )
    ret = dll.VCI_InitCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(init_config))
    if ret != 1:
        print("  [错误] 初始化CAN失败，返回值:", ret)
        dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
        return
    print("  [OK] CAN已初始化\n")

    # 步骤4: 启动CAN
    print("[步骤4] 启动CAN通道...")
    ret = dll.VCI_StartCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX)
    if ret != 1:
        print("  [错误] 启动CAN失败，返回值:", ret)
        dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
        return
    print("  [OK] CAN已启动\n")

    # 步骤5: 设置电机工作模式
    print("[步骤5] 设置电机1工作模式为 VELOCITY_POSITION...")
    motor_id = 1
    mode_can_id = MOTOR_MODE_IDS[motor_id - 1]

    # 手动构造模式设置帧：[mode, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA]
    mode_frame = VCI_CAN_OBJ(
        c_uint(mode_can_id),
        0, 0, 0, 0, 0,
        8,  # 数据长度
        (c_ubyte * 8)(MODE_VELOCITY_POSITION, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA),
        (c_ubyte * 3)(0, 0, 0)
    )

    # 发送3次确保收到
    for _ in range(3):
        ret = dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(mode_frame), 1)
        if ret != 1:
            print("  [警告] 发送模式设置失败")
        time.sleep(0.02)
    print("  [OK] 模式设置完成\n")

    # 步骤6: 发送速度命令
    print("[步骤6] 发送速度命令 (30 RPM, 持续5秒)...")
    command_can_id = MOTOR_COMMAND_IDS[motor_id - 1]
    rpm = 30

    # 手动计算RPM的16位有符号整数表示
    rpm_value = rpm if rpm >= 0 else (1 << 16) + rpm
    rpm_hex = format(rpm_value, "04X")
    rpm_high = int(rpm_hex[:2], 16)
    rpm_low = int(rpm_hex[2:], 16)

    # 手动构造速度命令帧：[0xAA, 0xAA, rpm_high, rpm_low, 0, 0, 0, 0]
    velocity_frame = VCI_CAN_OBJ(
        c_uint(command_can_id),
        0, 0, 0, 0, 0,
        8,
        (c_ubyte * 8)(0xAA, 0xAA, rpm_high, rpm_low, 0, 0, 0, 0),
        (c_ubyte * 3)(0, 0, 0)
    )

    # 持续发送5秒（每0.1秒发送一次，防止超时）
    end_time = time.time() + 5
    while time.time() < end_time:
        ret = dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(velocity_frame), 1)
        if ret != 1:
            print("  [警告] 发送命令失败")
        time.sleep(0.1)
    print("  [OK] 运行完成\n")

    # 步骤7: 停止电机
    print("[步骤7] 停止电机...")
    stop_frame = VCI_CAN_OBJ(
        c_uint(command_can_id),
        0, 0, 0, 0, 0,
        8,
        (c_ubyte * 8)(0xAA, 0xAA, 0, 0, 0, 0, 0, 0),  # 速度=0
        (c_ubyte * 3)(0, 0, 0)
    )

    # 多次发送停止命令确保收到
    for _ in range(10):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(stop_frame), 1)
        time.sleep(0.01)
    print("  [OK] 电机已停止\n")

    # 步骤8: 关闭设备
    print("[步骤8] 关闭设备...")
    ret = dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    if ret != 1:
        print("  [警告] 关闭设备失败")
    print("  [OK] 设备已关闭\n")

    print("="*60)
    print("示例1完成")
    print("="*60 + "\n")


# ============================================================================
# 示例 2: 单电机位置控制
# ============================================================================

def example_2_raw_position():
    """裸API调用 - 电机1移动到目标位置"""

    print("\n" + "="*60)
    print("[示例2] 裸API调用 - 位置控制")
    print("="*60 + "\n")

    # 步骤1-4: 加载库、打开设备、初始化、启动（同示例1）
    print("[步骤1-4] 初始化CAN设备...")
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")

    ret = dll.VCI_OpenDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, 0)
    if ret != 1:
        print("  [错误] 打开设备失败")
        return

    init_config = VCI_INIT_CONFIG(0x80000000, 0xFFFFFFFF, 0, 2, 0x00, 0x14, 0)
    ret = dll.VCI_InitCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(init_config))
    if ret != 1:
        print("  [错误] 初始化失败")
        dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
        return

    ret = dll.VCI_StartCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX)
    if ret != 1:
        print("  [错误] 启动失败")
        dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
        return
    print("  [OK] CAN设备就绪\n")

    # 步骤5: 设置工作模式
    print("[步骤5] 设置电机1工作模式...")
    motor_id = 1
    mode_can_id = MOTOR_MODE_IDS[motor_id - 1]
    mode_frame = VCI_CAN_OBJ(
        c_uint(mode_can_id), 0, 0, 0, 0, 0, 8,
        (c_ubyte * 8)(MODE_VELOCITY_POSITION, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA),
        (c_ubyte * 3)(0, 0, 0)
    )
    for _ in range(3):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(mode_frame), 1)
        time.sleep(0.02)
    print("  [OK] 模式设置完成\n")

    # 步骤6: 发送位置命令
    print("[步骤6] 发送位置命令 (目标位置=50000, 速度=20 RPM)...")
    command_can_id = MOTOR_COMMAND_IDS[motor_id - 1]
    rpm = 20
    target_position = 50000

    # 手动计算RPM (16位有符号)
    rpm_value = rpm if rpm >= 0 else (1 << 16) + rpm
    rpm_hex = format(rpm_value, "04X")
    rpm_high = int(rpm_hex[:2], 16)
    rpm_low = int(rpm_hex[2:], 16)

    # 手动计算位置 (32位有符号)
    pos_value = target_position if target_position >= 0 else (1 << 32) + target_position
    pos_hex = format(pos_value, "08X")
    pos_bytes = [int(pos_hex[i:i+2], 16) for i in range(0, 8, 2)]

    # 手动构造位置命令帧：[0xAA, 0xAA, rpm_high, rpm_low, pos[0], pos[1], pos[2], pos[3]]
    position_frame = VCI_CAN_OBJ(
        c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
        (c_ubyte * 8)(0xAA, 0xAA, rpm_high, rpm_low, pos_bytes[0], pos_bytes[1], pos_bytes[2], pos_bytes[3]),
        (c_ubyte * 3)(0, 0, 0)
    )

    # 发送3次初始命令
    for _ in range(3):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(position_frame), 1)
        time.sleep(0.02)
    print("  [OK] 位置命令已发送\n")

    # 步骤7: 持续发送保持命令（10秒）
    print("[步骤7] 持续发送保持命令 (10秒，防止超时)...")
    print("  按 Ctrl+C 可提前退出\n")

    try:
        end_time = time.time() + 10
        while time.time() < end_time:
            # 每0.5秒重发一次位置保持命令
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(position_frame), 1)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  [OK] 用户中断\n")

    # 步骤8: 停止电机
    print("[步骤8] 停止电机...")
    stop_frame = VCI_CAN_OBJ(
        c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
        (c_ubyte * 8)(0xAA, 0xAA, 0, 0, 0, 0, 0, 0),
        (c_ubyte * 3)(0, 0, 0)
    )
    for _ in range(10):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(stop_frame), 1)
        time.sleep(0.01)
    print("  [OK] 电机已停止\n")

    # 步骤9: 关闭设备
    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("[步骤9] 设备已关闭\n")

    print("="*60)
    print("示例2完成")
    print("="*60 + "\n")


# ============================================================================
# 示例 3: 多电机同步控制
# ============================================================================

def example_3_raw_multiple():
    """裸API调用 - 3个电机同步控制"""

    print("\n" + "="*60)
    print("[示例3] 裸API调用 - 多电机同步")
    print("="*60 + "\n")

    # 电机配置
    motors = [
        {'id': 1, 'rpm': 30, 'position': 50000},
        {'id': 2, 'rpm': 25, 'position': 45000},
        {'id': 3, 'rpm': 35, 'position': 55000},
    ]

    # 步骤1-4: 初始化设备
    print("[步骤1-4] 初始化CAN设备...")
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    dll.VCI_OpenDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, 0)
    init_config = VCI_INIT_CONFIG(0x80000000, 0xFFFFFFFF, 0, 2, 0x00, 0x14, 0)
    dll.VCI_InitCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(init_config))
    dll.VCI_StartCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX)
    print("  [OK] 设备就绪\n")

    # 步骤5: 设置所有电机模式
    print("[步骤5] 设置所有电机工作模式...")
    for motor in motors:
        mode_can_id = MOTOR_MODE_IDS[motor['id'] - 1]
        mode_frame = VCI_CAN_OBJ(
            c_uint(mode_can_id), 0, 0, 0, 0, 0, 8,
            (c_ubyte * 8)(MODE_VELOCITY_POSITION, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA),
            (c_ubyte * 3)(0, 0, 0)
        )
        for _ in range(3):
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(mode_frame), 1)
            time.sleep(0.02)
        print(f"  [OK] 电机 {motor['id']} 模式设置完成")
    print()

    # 步骤6: 发送所有电机的运动命令
    print("[步骤6] 发送运动命令到所有电机...")
    frames = []

    for motor in motors:
        motor_id = motor['id']
        rpm = motor['rpm']
        position = motor['position']
        command_can_id = MOTOR_COMMAND_IDS[motor_id - 1]

        # 计算RPM
        rpm_value = rpm if rpm >= 0 else (1 << 16) + rpm
        rpm_hex = format(rpm_value, "04X")
        rpm_high = int(rpm_hex[:2], 16)
        rpm_low = int(rpm_hex[2:], 16)

        # 计算位置
        pos_value = position if position >= 0 else (1 << 32) + position
        pos_hex = format(pos_value, "08X")
        pos_bytes = [int(pos_hex[i:i+2], 16) for i in range(0, 8, 2)]

        # 构造帧
        frame = VCI_CAN_OBJ(
            c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
            (c_ubyte * 8)(0xAA, 0xAA, rpm_high, rpm_low, pos_bytes[0], pos_bytes[1], pos_bytes[2], pos_bytes[3]),
            (c_ubyte * 3)(0, 0, 0)
        )
        frames.append(frame)

        # 发送初始命令
        for _ in range(3):
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(frame), 1)
            time.sleep(0.02)
        print(f"  [OK] 电机 {motor_id} 命令已发送")
    print()

    # 步骤7: 持续发送保持命令
    print("[步骤7] 持续发送保持命令 (10秒)...")
    print("  按 Ctrl+C 可提前退出\n")

    try:
        end_time = time.time() + 10
        while time.time() < end_time:
            # 对每个电机重发保持命令
            for frame in frames:
                dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(frame), 1)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  [OK] 用户中断\n")

    # 步骤8: 停止所有电机
    print("[步骤8] 停止所有电机...")
    for motor in motors:
        command_can_id = MOTOR_COMMAND_IDS[motor['id'] - 1]
        stop_frame = VCI_CAN_OBJ(
            c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
            (c_ubyte * 8)(0xAA, 0xAA, 0, 0, 0, 0, 0, 0),
            (c_ubyte * 3)(0, 0, 0)
        )
        for _ in range(10):
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(stop_frame), 1)
            time.sleep(0.01)
    print("  [OK] 所有电机已停止\n")

    # 步骤9: 关闭设备
    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("[步骤9] 设备已关闭\n")

    print("="*60)
    print("示例3完成")
    print("="*60 + "\n")


# ============================================================================
# 示例 4: 紧急停止所有电机
# ============================================================================

def example_4_raw_stop_all():
    """裸API调用 - 紧急停止所有电机"""

    print("\n" + "="*60)
    print("[示例4] 裸API调用 - 紧急停止所有电机")
    print("="*60 + "\n")

    # 初始化设备
    print("[步骤1] 初始化CAN设备...")
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    dll.VCI_OpenDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, 0)
    init_config = VCI_INIT_CONFIG(0x80000000, 0xFFFFFFFF, 0, 2, 0x00, 0x14, 0)
    dll.VCI_InitCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(init_config))
    dll.VCI_StartCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX)
    print("  [OK] 设备就绪\n")

    # 发送停止命令到所有6个电机
    print("[步骤2] 发送停止命令到所有电机 (1-6)...")
    for motor_id in range(1, 7):
        command_can_id = MOTOR_COMMAND_IDS[motor_id - 1]
        stop_frame = VCI_CAN_OBJ(
            c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
            (c_ubyte * 8)(0xAA, 0xAA, 0, 0, 0, 0, 0, 0),  # 速度=0, 位置=0
            (c_ubyte * 3)(0, 0, 0)
        )

        # 多次发送确保收到
        for _ in range(10):
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(stop_frame), 1)
            time.sleep(0.01)

        print(f"  [OK] 电机 {motor_id} 已停止")
    print()

    # 关闭设备
    print("[步骤3] 关闭设备...")
    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("  [OK] 设备已关闭\n")

    print("="*60)
    print("示例4完成 - 所有电机已停止")
    print("="*60 + "\n")


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════╗
║      裸API调用示例 - 直接使用 ctypes 控制电机                 ║
╚═══════════════════════════════════════════════════════════════╝

这个文件展示了如何完全不使用封装类，直接调用 VCI_* 函数。

每个示例函数都是完整的从头到尾的调用流程：
  • 加载库 (cdll.LoadLibrary)
  • 打开设备 (VCI_OpenDevice)
  • 初始化CAN (VCI_InitCAN)
  • 启动CAN (VCI_StartCAN)
  • 手动构造CAN帧
  • 发送命令 (VCI_Transmit)
  • 关闭设备 (VCI_CloseDevice)

可用示例：
  1. example_1_raw_velocity()   - 恒速转动5秒
  2. example_2_raw_position()   - 移动到目标位置（毫米）
  3. example_3_raw_multiple()   - 多电机同步（毫米）
  4. example_4_raw_stop_all()   - 紧急停止所有电机

位置换算：
  轮子直径: {WHEEL_DIAMETER_MM}mm
  圆周长:   {WHEEL_CIRCUMFERENCE_MM:.2f}mm
  1mm ≈ {MM_TO_ENCODER:.1f} 编码器计数

取消注释下面的一个示例来运行：
    """)

    # ========== 选择一个示例运行 ==========

    # 示例1: 恒速转动5秒
    # example_1_raw_velocity()

    # 示例2: 移动到目标位置
    # example_2_raw_position()

    # 示例3: 多电机同步
    # example_3_raw_multiple()

    # 示例4: 紧急停止所有电机
    # example_4_raw_stop_all()

    print("""
对比高层封装版本：
  封装版本：examples/motor_control.py
  裸API版本：examples/raw_api_example.py (当前文件)

建议：
  • 学习底层机制：使用裸API版本
  • 快速开发项目：使用封装版本
  • 调试底层问题：对比两个版本的差异
    """)
