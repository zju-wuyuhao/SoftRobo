#!/usr/bin/env python3
"""六电机实时控制系统 - 基于裸API的持续控制

特点：
- 后台线程持续发送命令（防止超时）
- 实时修改每个电机的速度和位置
- 状态监控和显示
- 安全的启动/停止机制

运行方式:
    cd /home/wuyuhao/SoftRobo_Control
    python3 realtime_control.py
"""

import time
import threading
from ctypes import Structure, c_ubyte, c_uint, cdll, byref
from collections import deque


# ============================================================================
# 结构体定义
# ============================================================================

class VCI_INIT_CONFIG(Structure):
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
# 位置单位转换函数
# ============================================================================

def mm_to_encoder(mm):
    """毫米转编码器计数"""
    return int(mm * MM_TO_ENCODER)


def encoder_to_mm(encoder_count):
    """编码器计数转毫米"""
    return encoder_count / MM_TO_ENCODER


# ============================================================================
# 实时控制器类
# ============================================================================

class RealtimeMotorController:
    """六电机实时控制器

    特点：
    - 后台线程持续发送命令
    - 线程安全的状态更新
    - 自动处理超时问题
    """

    def __init__(self, update_interval=0.1):
        """初始化控制器

        Args:
            update_interval: 命令发送间隔（秒），默认0.1秒（100ms）
        """
        self.update_interval = update_interval

        # 设备连接
        self.dll = None
        self.device_opened = False

        # 电机状态（线程安全）
        # 注意：position 存储的是编码器计数值，对外接口使用毫米
        self.motor_states = {
            i: {'rpm': 0, 'position': 0, 'enabled': False}
            for i in range(1, 7)
        }
        self.state_lock = threading.Lock()

        # 控制线程
        self.control_thread = None
        self.running = False

        # 统计信息
        self.command_count = 0
        self.error_count = 0
        self.start_time = None

    def _rpm_to_bytes(self, rpm):
        """RPM转字节"""
        value = rpm if rpm >= 0 else (1 << 16) + rpm
        hex_str = format(value, "04X")
        return int(hex_str[:2], 16), int(hex_str[2:], 16)

    def _position_to_bytes(self, position):
        """位置转字节"""
        value = position if position >= 0 else (1 << 32) + position
        hex_str = format(value, "08X")
        return [int(hex_str[i:i+2], 16) for i in range(0, 8, 2)]

    def _build_command_frame(self, motor_id, rpm, position):
        """构造命令帧"""
        command_can_id = MOTOR_COMMAND_IDS[motor_id - 1]
        rpm_high, rpm_low = self._rpm_to_bytes(int(rpm))
        pos_bytes = self._position_to_bytes(int(position))

        return VCI_CAN_OBJ(
            c_uint(command_can_id), 0, 0, 0, 0, 0, 8,
            (c_ubyte * 8)(0xAA, 0xAA, rpm_high, rpm_low, pos_bytes[0], pos_bytes[1], pos_bytes[2], pos_bytes[3]),
            (c_ubyte * 3)(0, 0, 0)
        )

    def _control_loop(self):
        """后台控制循环 - 持续发送命令"""
        print("[控制线程] 已启动")

        while self.running:
            # 获取当前状态快照
            with self.state_lock:
                states = {k: v.copy() for k, v in self.motor_states.items()}

            # 发送所有启用电机的命令
            for motor_id, state in states.items():
                if state['enabled']:
                    try:
                        frame = self._build_command_frame(
                            motor_id,
                            state['rpm'],
                            state['position']
                        )
                        ret = self.dll.VCI_Transmit(
                            DEVICE_TYPE_USBCAN2,
                            DEFAULT_DEVICE_INDEX,
                            DEFAULT_CAN_INDEX,
                            byref(frame),
                            1
                        )

                        if ret == 1:
                            self.command_count += 1
                        else:
                            self.error_count += 1

                    except Exception as e:
                        self.error_count += 1
                        print(f"[警告] 电机{motor_id}发送失败: {e}")

            # 等待下一个周期
            time.sleep(self.update_interval)

        print("[控制线程] 已停止")

    def start(self):
        """启动实时控制系统"""
        if self.running:
            print("[错误] 系统已在运行")
            return False

        print("\n" + "="*60)
        print("[启动] 初始化实时控制系统")
        print("="*60)

        # 加载库
        print("[步骤1] 加载 libcontrolcan.so...")
        try:
            self.dll = cdll.LoadLibrary("CAN/libcontrolcan.so")
            print("  [OK] 库已加载")
        except Exception as e:
            print(f"  [错误] 加载失败: {e}")
            return False

        # 打开设备
        print("[步骤2] 打开CAN设备...")
        ret = self.dll.VCI_OpenDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX, 0)
        if ret != 1:
            print(f"  [错误] 打开设备失败，返回值: {ret}")
            return False
        self.device_opened = True
        print("  [OK] 设备已打开")

        # 初始化CAN
        print("[步骤3] 初始化CAN (500kbps)...")
        init_config = VCI_INIT_CONFIG(0x80000000, 0xFFFFFFFF, 0, 2, 0x00, 0x14, 0)
        ret = self.dll.VCI_InitCAN(
            DEVICE_TYPE_USBCAN2,
            DEFAULT_DEVICE_INDEX,
            DEFAULT_CAN_INDEX,
            byref(init_config)
        )
        if ret != 1:
            print(f"  [错误] 初始化失败，返回值: {ret}")
            self.stop()
            return False
        print("  [OK] CAN已初始化")

        # 启动CAN
        print("[步骤4] 启动CAN...")
        ret = self.dll.VCI_StartCAN(
            DEVICE_TYPE_USBCAN2,
            DEFAULT_DEVICE_INDEX,
            DEFAULT_CAN_INDEX
        )
        if ret != 1:
            print(f"  [错误] 启动失败，返回值: {ret}")
            self.stop()
            return False
        print("  [OK] CAN已启动")

        # 设置所有电机模式
        print("[步骤5] 设置电机工作模式...")
        for motor_id in range(1, 7):
            mode_can_id = MOTOR_MODE_IDS[motor_id - 1]
            mode_frame = VCI_CAN_OBJ(
                c_uint(mode_can_id), 0, 0, 0, 0, 0, 8,
                (c_ubyte * 8)(MODE_VELOCITY_POSITION, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA),
                (c_ubyte * 3)(0, 0, 0)
            )
            for _ in range(3):
                self.dll.VCI_Transmit(
                    DEVICE_TYPE_USBCAN2,
                    DEFAULT_DEVICE_INDEX,
                    DEFAULT_CAN_INDEX,
                    byref(mode_frame),
                    1
                )
                time.sleep(0.02)
        print("  [OK] 所有电机模式已设置")

        # 启动控制线程
        print("[步骤6] 启动控制线程...")
        self.running = True
        self.start_time = time.time()
        self.command_count = 0
        self.error_count = 0

        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()

        print("  [OK] 控制线程已启动")
        print("\n" + "="*60)
        print("[成功] 实时控制系统已就绪")
        print(f"        更新频率: {1/self.update_interval:.1f} Hz")
        print("="*60 + "\n")

        return True

    def stop(self):
        """停止实时控制系统"""
        print("\n" + "="*60)
        print("[停止] 关闭实时控制系统")
        print("="*60)

        # 停止控制线程
        if self.running:
            print("[步骤1] 停止控制线程...")
            self.running = False
            if self.control_thread:
                self.control_thread.join(timeout=2.0)
            print("  [OK] 控制线程已停止")

        # 停止所有电机
        if self.dll and self.device_opened:
            print("[步骤2] 发送停止命令...")
            for motor_id in range(1, 7):
                stop_frame = self._build_command_frame(motor_id, 0, 0)
                for _ in range(10):
                    self.dll.VCI_Transmit(
                        DEVICE_TYPE_USBCAN2,
                        DEFAULT_DEVICE_INDEX,
                        DEFAULT_CAN_INDEX,
                        byref(stop_frame),
                        1
                    )
                    time.sleep(0.01)
            print("  [OK] 停止命令已发送")

            # 关闭设备
            print("[步骤3] 关闭设备...")
            self.dll.VCI_CloseDevice(DEVICE_TYPE_USBCAN2, DEFAULT_DEVICE_INDEX)
            self.device_opened = False
            print("  [OK] 设备已关闭")

        # 显示统计
        if self.start_time:
            runtime = time.time() - self.start_time
            print(f"\n[统计] 运行时间: {runtime:.1f}秒")
            print(f"        发送命令: {self.command_count} 次")
            print(f"        发送错误: {self.error_count} 次")
            if runtime > 0:
                print(f"        平均频率: {self.command_count/runtime:.1f} Hz")

        print("\n" + "="*60)
        print("[完成] 系统已安全关闭")
        print("="*60 + "\n")

    def set_motor(self, motor_id, rpm=None, position_mm=None, enabled=None):
        """设置单个电机参数

        Args:
            motor_id: 电机ID (1-6)
            rpm: 速度（None表示不修改）
            position_mm: 位置（毫米，None表示不修改）
            enabled: 是否启用（None表示不修改）
        """
        if not 1 <= motor_id <= 6:
            print(f"[错误] 电机ID必须在1-6之间")
            return False

        with self.state_lock:
            if rpm is not None:
                self.motor_states[motor_id]['rpm'] = rpm
            if position_mm is not None:
                # 将毫米转换为编码器计数存储
                self.motor_states[motor_id]['position'] = mm_to_encoder(position_mm)
            if enabled is not None:
                self.motor_states[motor_id]['enabled'] = enabled

        return True

    def get_motor_state(self, motor_id):
        """获取电机状态"""
        if not 1 <= motor_id <= 6:
            return None

        with self.state_lock:
            return self.motor_states[motor_id].copy()

    def get_all_states(self):
        """获取所有电机状态"""
        with self.state_lock:
            return {k: v.copy() for k, v in self.motor_states.items()}

    def enable_motor(self, motor_id):
        """启用电机"""
        return self.set_motor(motor_id, enabled=True)

    def disable_motor(self, motor_id):
        """禁用电机（停止）"""
        self.set_motor(motor_id, rpm=0, position_mm=0, enabled=False)
        return True

    def enable_all(self):
        """启用所有电机"""
        for motor_id in range(1, 7):
            self.enable_motor(motor_id)

    def disable_all(self):
        """禁用所有电机"""
        for motor_id in range(1, 7):
            self.disable_motor(motor_id)

    def print_status(self):
        """打印当前状态"""
        states = self.get_all_states()

        print("\n" + "="*75)
        print("  ID  |  状态  |   RPM   |  位置(mm)  | 编码器值  | 命令数 | 错误数")
        print("-"*75)

        for motor_id in range(1, 7):
            state = states[motor_id]
            status = "[运行]" if state['enabled'] else "[停止]"
            position_mm = encoder_to_mm(state['position'])
            encoder_count = state['position']

            if motor_id < 6:
                print(f"  {motor_id}   | {status} | {state['rpm']:>7.0f} | {position_mm:>9.2f} | {encoder_count:>9} |")
            else:
                # 最后一行显示统计信息
                runtime = time.time() - self.start_time if self.start_time else 0
                freq = self.command_count / runtime if runtime > 0 else 0
                print(f"  {motor_id}   | {status} | {state['rpm']:>7.0f} | {position_mm:>9.2f} | {encoder_count:>9} | {self.command_count:>6} | {self.error_count:>6}")
                print("-"*75)
                print(f"运行时间: {runtime:.1f}秒 | 频率: {freq:.1f} Hz | 换算: 1圈={WHEEL_CIRCUMFERENCE_MM:.2f}mm")

        print("="*75 + "\n")


# ============================================================================
# 交互式控制界面
# ============================================================================

def show_help():
    """显示帮助信息"""
    print("""
可用命令：
  start              - 启动实时控制系统
  stop               - 停止实时控制系统

  set <id> <rpm> <pos_mm>    - 设置电机参数（位置单位：毫米）
  enable <id>             - 启用电机
  disable <id>            - 禁用电机
  enable_all              - 启用所有电机
  disable_all             - 禁用所有电机

  status                  - 显示当前状态
  help                    - 显示此帮助
  quit / exit             - 退出程序

示例：
  set 1 30 50000          - 设置电机1: 30RPM, 30RPM, 位置100mm
  enable 1                - 启用电机1（开始运动）
  disable 1               - 禁用电机1（停止）
  status                  - 查看所有电机状态
""")


def main():
    """主程序 - 交互式实时控制"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           六电机实时控制系统 v1.0                             ║
╚══════════════════════════════════════════════════════════════╝

特点：
  • 后台线程持续发送命令（防止超时）
  • 实时修改速度和位置（位置单位：毫米）
  • 独立控制每个电机的启用/禁用
  • 线程安全的状态管理

位置换算：轮子直径{WHEEL_DIAMETER_MM}mm, 圆周长{WHEEL_CIRCUMFERENCE_MM:.2f}mm
输入 'help' 查看可用命令
""")

    controller = RealtimeMotorController(update_interval=0.1)

    try:
        while True:
            cmd = input(">>> ").strip().split()

            if not cmd:
                continue

            command = cmd[0].lower()

            # 系统控制命令
            if command == 'start':
                controller.start()

            elif command == 'stop':
                controller.stop()

            elif command in ['quit', 'exit']:
                if controller.running:
                    controller.stop()
                print("再见！")
                break

            # 电机控制命令
            elif command == 'set' and len(cmd) == 4:
                try:
                    motor_id = int(cmd[1])
                    rpm = float(cmd[2])
                    position = int(cmd[3])

                    if controller.set_motor(motor_id, rpm=rpm, position=position):
                        print(f"[OK] 电机{motor_id}: RPM={rpm}, 位置={position}")

                except ValueError:
                    print("[错误] 参数格式错误。用法: set <id> <rpm> <position_mm>")

            elif command == 'enable' and len(cmd) == 2:
                try:
                    motor_id = int(cmd[1])
                    if controller.enable_motor(motor_id):
                        print(f"[OK] 电机{motor_id}已启用")
                except ValueError:
                    print("[错误] 电机ID必须是数字")

            elif command == 'disable' and len(cmd) == 2:
                try:
                    motor_id = int(cmd[1])
                    controller.disable_motor(motor_id)
                    print(f"[OK] 电机{motor_id}已禁用")
                except ValueError:
                    print("[错误] 电机ID必须是数字")

            elif command == 'enable_all':
                controller.enable_all()
                print("[OK] 所有电机已启用")

            elif command == 'disable_all':
                controller.disable_all()
                print("[OK] 所有电机已禁用")

            elif command == 'status':
                controller.print_status()

            elif command == 'help':
                show_help()

            else:
                print("[错误] 未知命令。输入 'help' 查看帮助")

    except KeyboardInterrupt:
        print("\n\n[中断] 退出程序...")
        if controller.running:
            controller.stop()

    except Exception as e:
        print(f"\n[错误] {e}")
        if controller.running:
            controller.stop()


if __name__ == "__main__":
    main()
