#!/usr/bin/env python3
"""交互式电机控制程序 - 直接使用 ctypes 调用 libcontrolcan.so

位置单位：毫米（自动转换为编码器计数）

运行方式:
    cd /home/wuyuhao/SoftRobo_Control
    python3 motor_control.py
"""

import time
from ctypes import Structure, c_ubyte, c_uint, cdll, byref


# ============================================================================
# 结构体定义
# ============================================================================

class VCI_INIT_CONFIG(Structure):
    """CAN初始化配置结构体"""
    _fields_ = [
        ("AccCode", c_uint),
        ("AccMask", c_uint),
        ("Reserved", c_uint),
        ("Filter", c_ubyte),
        ("Timing0", c_ubyte),
        ("Timing1", c_ubyte),
        ("Mode", c_ubyte),
    ]


class VCI_CAN_OBJ(Structure):
    """CAN消息帧结构体"""
    _fields_ = [
        ("ID", c_uint),
        ("TimeStamp", c_uint),
        ("TimeFlag", c_ubyte),
        ("SendType", c_ubyte),
        ("RemoteFlag", c_ubyte),
        ("ExternFlag", c_ubyte),
        ("DataLen", c_ubyte),
        ("Data", c_ubyte * 8),
        ("Reserved", c_ubyte * 3),
    ]


# ============================================================================
# 常量定义
# ============================================================================

DEVICE_TYPE_USBCAN2 = 4
DEFAULT_DEVICE_INDEX = 0
DEFAULT_CAN_INDEX = 0

MOTOR_MODE_IDS = [0x011, 0x012, 0x013, 0x014, 0x015, 0x016]
MOTOR_COMMAND_IDS = [0x031, 0x032, 0x033, 0x034, 0x035, 0x036]

MODE_VELOCITY_POSITION = 0x07

# 位置换算常量
WHEEL_DIAMETER_MM = 17.0                        # 轮子直径（毫米）
WHEEL_CIRCUMFERENCE_MM = WHEEL_DIAMETER_MM * 3.14159265359  # 圆周长 ≈ 53.41mm
ENCODER_COUNTS_PER_REV = 8192                   # 编码器分辨率
MM_TO_ENCODER = ENCODER_COUNTS_PER_REV / WHEEL_CIRCUMFERENCE_MM  # ≈ 153.4


# ============================================================================
# 位置单位转换
# ============================================================================

def mm_to_encoder(mm):
    """毫米转编码器计数"""
    return int(mm * MM_TO_ENCODER)


def encoder_to_mm(encoder_count):
    """编码器计数转毫米"""
    return encoder_count / MM_TO_ENCODER


# ============================================================================
# 辅助函数（最小化封装，仅避免重复代码）
# ============================================================================

def rpm_to_bytes(rpm):
    """将RPM转换为CAN帧的2字节表示"""
    value = rpm if rpm >= 0 else (1 << 16) + rpm
    hex_str = format(value, "04X")
    return int(hex_str[:2], 16), int(hex_str[2:], 16)


def position_to_bytes(position):
    """将位置转换为CAN帧的4字节表示"""
    value = position if position >= 0 else (1 << 32) + position
    hex_str = format(value, "08X")
    return [int(hex_str[i:i+2], 16) for i in range(0, 8, 2)]


def build_mode_frame(motor_id):
    """构造模式设置帧"""
    mode_can_id = MOTOR_MODE_IDS[motor_id - 1]
    return VCI_CAN_OBJ(
        c_uint(mode_can_id), 0, 0, 0, 0, 0, 8,
        (c_ubyte * 8)(MODE_VELOCITY_POSITION, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA),
        (c_ubyte * 3)(0, 0, 0)
    )


def build_command_frame(motor_id, rpm, position):
    """构造速度+位置命令帧"""
    command_can_id = MOTOR_COMMAND_IDS[motor_id - 1]
    rpm_high, rpm_low = rpm_to_bytes(rpm)
    pos_bytes = position_to_bytes(position)

    return VCI_CAN_OBJ(
        c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
        (c_ubyte * 8)(0xAA, 0xAA, rpm_high, rpm_low, pos_bytes[0], pos_bytes[1], pos_bytes[2], pos_bytes[3]),
        (c_ubyte * 3)(0, 0, 0)
    )


def init_can_device(dll):
    """初始化CAN设备（返回是否成功）"""
    # 打开设备
    ret = dll.VCI_OpenDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, 0)
    if ret != 1:
        print("  [错误] 打开设备失败")
        return False

    # 初始化CAN
    init_config = VCI_INIT_CONFIG(0x80000000, 0xFFFFFFFF, 0, 2, 0x00, 0x14, 0)
    ret = dll.VCI_InitCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(init_config))
    if ret != 1:
        print("  [错误] 初始化CAN失败")
        dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
        return False

    # 启动CAN
    ret = dll.VCI_StartCAN(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX)
    if ret != 1:
        print("  [错误] 启动CAN失败")
        dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
        return False

    return True


def set_motor_mode(dll, motor_id):
    """设置电机工作模式"""
    mode_frame = build_mode_frame(motor_id)
    for _ in range(3):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(mode_frame), 1)
        time.sleep(0.02)


def stop_motor(dll, motor_id):
    """停止指定电机"""
    stop_frame = build_command_frame(motor_id, 0, 0)
    for _ in range(10):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(stop_frame), 1)
        time.sleep(0.01)


# ============================================================================
# 交互式控制函数
# ============================================================================

def control_velocity_interactive():
    """交互式恒速控制"""
    print("\n" + "="*60)
    print("[恒速控制]")
    print("="*60)

    try:
        motor_id = int(input("\n电机ID (1-6): "))
        if not 1 <= motor_id <= 6:
            print("[错误] 电机ID必须在1-6之间")
            return

        rpm = float(input("转速 RPM (正数顺时针，负数逆时针): "))
        duration = float(input("运行时间 (秒): "))

        if duration <= 0:
            print("[错误] 运行时间必须大于0")
            return

    except ValueError:
        print("[错误] 输入无效")
        return

    print(f"\n[启动] 电机{motor_id}, {rpm} RPM, {duration}秒")

    # 初始化设备
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    if not init_can_device(dll):
        return

    print("  [OK] CAN设备已初始化")

    # 设置模式
    set_motor_mode(dll, motor_id)
    print("  [OK] 电机模式已设置")

    # 发送速度命令
    velocity_frame = build_command_frame(motor_id, int(rpm), 0)

    print(f"  [运行中] 持续 {duration} 秒...")
    end_time = time.time() + duration

    try:
        while time.time() < end_time:
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(velocity_frame), 1)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n  [中断] 用户停止")

    # 停止电机
    print("  [停止] 发送停止命令...")
    stop_motor(dll, motor_id)

    # 关闭设备
    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("  [OK] 完成\n")


def control_position_interactive():
    """交互式位置控制（毫米）"""
    print("\n" + "="*60)
    print("[位置控制] - 位置单位：毫米")
    print("="*60)

    try:
        motor_id = int(input("\n电机ID (1-6): "))
        if not 1 <= motor_id <= 6:
            print("[错误] 电机ID必须在1-6之间")
            return

        position_mm = float(input("目标位置 (毫米): "))
        rpm = float(input("移动速度 RPM: "))
        hold_time = float(input("保持时间 (秒, 0表示不保持): "))

        # 转换为编码器计数
        position_encoder = mm_to_encoder(position_mm)
        print(f"\n[换算] {position_mm}mm = {position_encoder} 编码器计数")

    except ValueError:
        print("[错误] 输入无效")
        return

    print(f"\n[启动] 电机{motor_id}, 位置={position_mm}mm, 速度={rpm} RPM")

    # 初始化设备
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    if not init_can_device(dll):
        return

    print("  [OK] CAN设备已初始化")

    # 设置模式
    set_motor_mode(dll, motor_id)
    print("  [OK] 电机模式已设置")

    # 发送位置命令
    position_frame = build_command_frame(motor_id, int(rpm), position_encoder)

    for _ in range(3):
        dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(position_frame), 1)
        time.sleep(0.02)

    print("  [OK] 位置命令已发送")

    # 保持位置
    if hold_time > 0:
        print(f"  [保持] 持续 {hold_time} 秒... (按 Ctrl+C 提前退出)")
        end_time = time.time() + hold_time

        try:
            while time.time() < end_time:
                dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(position_frame), 1)
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n  [中断] 用户停止")

    # 停止电机
    print("  [停止] 发送停止命令...")
    stop_motor(dll, motor_id)

    # 关闭设备
    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("  [OK] 完成\n")


def control_multiple_interactive():
    """交互式多电机控制（毫米）"""
    print("\n" + "="*60)
    print("[多电机同步控制] - 位置单位：毫米")
    print("="*60)

    motors = []

    try:
        num_motors = int(input("\n控制几个电机 (1-6): "))
        if not 1 <= num_motors <= 6:
            print("[错误] 数量必须在1-6之间")
            return

        for i in range(num_motors):
            print(f"\n--- 电机 {i+1} ---")
            motor_id = int(input("  电机ID (1-6): "))
            if not 1 <= motor_id <= 6:
                print("[错误] 电机ID必须在1-6之间")
                return

            rpm = float(input("  速度 RPM: "))
            position_mm = float(input("  目标位置 (毫米): "))
            position_encoder = mm_to_encoder(position_mm)

            motors.append({
                'id': motor_id,
                'rpm': rpm,
                'position_mm': position_mm,
                'position_encoder': position_encoder
            })
            print(f"  [换算] {position_mm}mm = {position_encoder} 编码器计数")

        hold_time = float(input("\n保持时间 (秒, 0表示不保持): "))

    except ValueError:
        print("[错误] 输入无效")
        return

    print(f"\n[启动] 同步控制 {len(motors)} 个电机")

    # 初始化设备
    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    if not init_can_device(dll):
        return

    print("  [OK] CAN设备已初始化")

    # 设置所有电机模式
    for motor in motors:
        set_motor_mode(dll, motor['id'])
        print(f"  [OK] 电机 {motor['id']} 模式已设置")

    # 发送所有命令
    frames = []
    for motor in motors:
        frame = build_command_frame(motor['id'], int(motor['rpm']), motor['position_encoder'])
        frames.append(frame)

        for _ in range(3):
            dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(frame), 1)
            time.sleep(0.02)

        print(f"  [OK] 电机 {motor['id']} 命令已发送 ({motor['position_mm']}mm)")

    # 保持位置
    if hold_time > 0:
        print(f"\n  [保持] 持续 {hold_time} 秒... (按 Ctrl+C 提前退出)")
        end_time = time.time() + hold_time

        try:
            while time.time() < end_time:
                for frame in frames:
                    dll.VCI_Transmit(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, DEFAULT_CAN_INDEX, byref(frame), 1)
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n  [中断] 用户停止")

    # 停止所有电机
    print("\n  [停止] 停止所有电机...")
    for motor in motors:
        stop_motor(dll, motor['id'])

    # 关闭设备
    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("  [OK] 完成\n")


def emergency_stop_all():
    """紧急停止所有电机"""
    print("\n" + "="*60)
    print("[紧急停止]")
    print("="*60 + "\n")

    confirm = input("确认停止所有6个电机? (y/n): ")
    if confirm.lower() != 'y':
        print("已取消")
        return

    dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
    if not init_can_device(dll):
        return

    print("  [OK] CAN设备已初始化")
    print("  [停止] 发送停止命令到所有电机...")

    for motor_id in range(1, 7):
        stop_motor(dll, motor_id)
        print(f"  [OK] 电机 {motor_id} 已停止")

    dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
    print("\n  [OK] 所有电机已停止\n")


# ============================================================================
# 主菜单
# ============================================================================

def show_menu():
    """显示主菜单"""
    print("\n" + "╔" + "="*58 + "╗")
    print("║" + " "*15 + "DJI 电机控制程序（毫米模式）" + " "*15 + "║")
    print("╚" + "="*58 + "╝")
    print(f"\n位置换算：轮子直径{WHEEL_DIAMETER_MM}mm, 圆周长{WHEEL_CIRCUMFERENCE_MM:.2f}mm, 1mm≈{MM_TO_ENCODER:.1f}计数")
    print("\n可用操作：")
    print("  1. 恒速控制    - 指定转速和运行时间")
    print("  2. 位置控制    - 移动到目标位置（毫米）")
    print("  3. 多电机同步  - 同时控制多个电机（毫米）")
    print("  4. 紧急停止    - 立即停止所有电机")
    print("  5. 退出程序")
    print()


def main():
    """主程序"""
    while True:
        show_menu()

        try:
            choice = input("请选择操作 (1-5): ").strip()

            if choice == '1':
                control_velocity_interactive()
            elif choice == '2':
                control_position_interactive()
            elif choice == '3':
                control_multiple_interactive()
            elif choice == '4':
                emergency_stop_all()
            elif choice == '5':
                print("\n再见！\n")
                break
            else:
                print("\n[错误] 无效选择，请输入 1-5\n")

        except KeyboardInterrupt:
            print("\n\n[中断] 退出程序\n")
            break
        except Exception as e:
            print(f"\n[错误] {e}\n")


if __name__ == "__main__":
    main()
