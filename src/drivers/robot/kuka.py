"""
KUKA机械臂驱动实现
支持KUKA KR系列、LBR系列等型号
"""

import time
import threading
import json
import socket
from typing import Optional, Tuple, Dict, Any, List
from core.interfaces.hardware.robot_interface import IRobot, RobotState, MotionMode, RobotPosition, PathPoint, RobotPath

try:
    # 尝试导入KUKA官方SDK
    import kuka_connect
    KUKA_SDK_AVAILABLE = True
except ImportError:
    KUKA_SDK_AVAILABLE = False

from core.managers.log_manager import warning, info, error, debug


class KukaRobot(IRobot):
    """KUKA机械臂驱动实现"""

    def __init__(self):
        # 在初始化时显示SDK可用性警告
        if not KUKA_SDK_AVAILABLE:
            warning("KUKA SDK not available - will try socket implementation", "ROBOT_DRIVER")

        self.krc_connection = None
        self.socket_connection = None
        self.connected = False
        self.current_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self.config = {}

        # 实时控制相关状态
        self._state = RobotState.IDLE
        self._motion_mode = MotionMode.MANUAL
        self._is_jogging = False
        self._jogging_axis = None

        # 路径记录相关状态
        self._is_recording_path = False
        self._recorded_path = None
        self._path_recording_name = ""
        self._is_playing_path = False
        self._playback_thread = None
        self._playback_stopped = threading.Event()

        # 回调函数列表
        self._position_callbacks = []
        self._state_callbacks = []

        # 线程锁
        self._motion_lock = threading.Lock()
        self._path_lock = threading.Lock()

        # 路径存储
        self._path_storage_dir = "paths"
        import os
        os.makedirs(self._path_storage_dir, exist_ok=True)

        # KUKA特定参数
        self.robot_ip = None
        self.robot_model = None
        self.krl_interface = None

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接KUKA机械臂"""
        try:
            self.config = config
            self.robot_ip = config.get('ip')
            self.robot_model = config.get('model', 'KR_AGILUS')

            info(f"Connecting to KUKA robot at {self.robot_ip}", "ROBOT_DRIVER")

            if KUKA_SDK_AVAILABLE:
                # 使用官方SDK连接
                try:
                    self.krc_connection = kuka_connect.KUKAConnection(
                        host=self.robot_ip,
                        port=config.get('port', 7000)
                    )
                    success = self.krc_connection.connect()
                    if success:
                        self.connected = True
                        info("KUKA robot connected via SDK", "ROBOT_DRIVER")
                        return True
                    else:
                        error("KUKA SDK connection failed", "ROBOT_DRIVER")
                except Exception as e:
                    warning(f"KUKA SDK connection failed: {e}, trying socket connection", "ROBOT_DRIVER")

            # 备用：使用Socket连接
            return self._connect_socket()

        except Exception as e:
            error(f"Failed to connect KUKA robot: {e}", "ROBOT_DRIVER")
            self.connected = False
            return False

    def _connect_socket(self) -> bool:
        """使用Socket连接KUKA机械臂"""
        try:
            # KUKA KRC控制器端口
            host = self.robot_ip
            port = 7000  # KUKA Ethernet KRL接口

            self.socket_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket_connection.settimeout(10.0)
            self.socket_connection.connect((host, port))

            self.connected = True
            info(f"KUKA robot connected via socket to {host}:{port}", "ROBOT_DRIVER")
            return True

        except Exception as e:
            error(f"KUKA socket connection failed: {e}", "ROBOT_DRIVER")
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.krc_connection:
                self.krc_connection.disconnect()
                self.krc_connection = None

            if self.socket_connection:
                self.socket_connection.close()
                self.socket_connection = None

            self.connected = False
            logger.info("KUKA robot disconnected")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect KUKA robot: {e}")
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        if KUKA_SDK_AVAILABLE and self.krc_connection:
            return self.krc_connection.is_connected()
        elif self.socket_connection:
            return self.connected
        return False

    def move_to(self, x: float, y: float, z: float,
                rx: float = 0, ry: float = 0, rz: float = 0) -> bool:
        """移动到指定位置"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            logger.info(f"Moving to position ({x}, {y}, {z}, {rx}, {ry}, {rz})")

            if KUKA_SDK_AVAILABLE and self.krc_connection:
                # 使用KUKA SDK移动
                success = self.krc_connection.move_to_position(
                    x, y, z, rx, ry, rz,
                    speed=config.get('speed', 100),
                    acceleration=config.get('acceleration', 50)
                )
                if success:
                    self.current_position = (x, y, z, rx, ry, rz)
                return success
            elif self.socket_connection:
                # 使用KRL命令移动
                krl_command = f"PTP {{X {x}, Y {y}, Z {z}, A {rx}, B {ry}, C {rz}}} C_PTP"
                self._send_krl_command(krl_command)
                time.sleep(0.5)  # 等待移动
                self.current_position = (x, y, z, rx, ry, rz)
                return True
            else:
                error("No connection available - cannot move real robot", "ROBOT_DRIVER")
                return False

        except Exception as e:
            logger.error(f"Failed to move KUKA robot: {e}")
            return False

    def get_position(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """获取当前位置"""
        if not self.is_connected():
            logger.warning("Robot not connected")
            return None

        try:
            if KUKA_SDK_AVAILABLE and self.krc_connection:
                # 使用SDK获取位置
                position = self.krc_connection.get_current_position()
                if position and len(position) >= 6:
                    self.current_position = tuple(position[:6])
                    return self.current_position
            elif self.socket_connection:
                # 使用KRL查询位置
                krl_command = "POS_ACT"  # 获取实际位置
                response = self._send_krl_command(krl_command)
                # 解析KUKA位置响应（简化）
                # 这里应该根据实际的KUKA KRL协议解析
                return self.current_position
            else:
                # 返回缓存位置
                return self.current_position

        except Exception as e:
            logger.error(f"Failed to get KUKA position: {e}")

        return self.current_position

    def home(self) -> bool:
        """回到原点"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            logger.info("Moving KUKA robot to home position")

            # KUKA机械臂的零位（$HOME）
            if KUKA_SDK_AVAILABLE and self.krc_connection:
                success = self.krc_connection.move_to_home()
                return success
            elif self.socket_connection:
                krl_command = "PTP $HOME"
                self._send_krl_command(krl_command)
                time.sleep(1.0)
                return True
            else:
                # 模拟回原点
                home_position = [0, 0, 0, 0, 0, 0]
                time.sleep(0.3)
                self.current_position = tuple(home_position)
                logger.info("Mock KUKA home completed successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to move KUKA home: {e}")
            return False

    def emergency_stop(self) -> bool:
        """紧急停止"""
        try:
            logger.warning("KUKA emergency stop activated")

            if KUKA_SDK_AVAILABLE and self.krc_connection:
                return self.krc_connection.emergency_stop()
            elif self.socket_connection:
                # 发送KUKA紧急停止命令
                krl_command = "HALT"
                self._send_krl_command(krl_command)
                return True
            else:
                logger.warning("Mock KUKA emergency stop completed")
                return True

        except Exception as e:
            logger.error(f"Failed to KUKA emergency stop: {e}")
            return False

    def set_speed(self, speed: float) -> bool:
        """设置速度"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if not (0 <= speed <= 100):
                logger.error("Speed must be between 0 and 100")
                return False

            # KUKA速度设置（1% = 1% of maximum velocity）
            kuka_speed = speed / 100.0

            logger.info(f"Setting KUKA speed to {speed}% ({kuka_speed:.2f})")

            if KUKA_SDK_AVAILABLE and self.krc_connection:
                return self.krc_connection.set_velocity_override(kuka_speed)
            elif self.socket_connection:
                krl_command = f"OV_PRO {kuka_speed}"
                self._send_krl_command(krl_command)
                return True
            else:
                logger.info(f"Mock KUKA speed set to {speed}%")
                return True

        except Exception as e:
            logger.error(f"Failed to set KUKA speed: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        info = {
            'brand': 'KUKA',
            'type': 'Robot',
            'connected': self.is_connected(),
            'model': self.robot_model,
            'ip': self.robot_ip,
            'sdk_available': KUKA_SDK_AVAILABLE
        }

        if KUKA_SDK_AVAILABLE and self.krc_connection:
            try:
                # 获取KUKA特定信息
                kuka_info = self.krc_connection.get_robot_info()
                info.update(kuka_info)
            except Exception as e:
                logger.warning(f"Failed to get KUKA info: {e}")

        return info

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        result = {
            'success': False,
            'error': None,
            'info': self.get_info()
        }

        try:
            if not self.is_connected():
                result['error'] = 'Robot not connected'
                return result

            # 测试基本功能
            position = self.get_position()
            if position is None:
                result['error'] = 'Failed to get position'
                return result

            # 测试设备信息获取
            info = self.get_info()
            if not info:
                result['error'] = 'Failed to get device info'
                return result

            result['success'] = True
            result['position'] = position

        except Exception as e:
            result['error'] = str(e)

        return result

    def _send_krl_command(self, command: str) -> str:
        """发送KRL命令并获取响应"""
        if not self.socket_connection:
            return ""

        try:
            # KUKA KRL命令格式
            full_command = f"{command}\n"
            self.socket_connection.send(full_command.encode())

            # 读取响应
            response = self.socket_connection.recv(1024).decode().strip()
            return response
        except Exception as e:
            logger.error(f"Failed to send KRL command: {e}")
            return ""

    # ========== 实现其他IRobot接口方法 ==========
    def start_jogging(self, axis: str) -> bool:
        """开始点动运动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            with self._motion_lock:
                self._is_jogging = True
                self._jogging_axis = axis
                self._state = RobotState.JOGGING

                # KUKA特定的点动实现
                if self.socket_connection:
                    axis_map = {'x': 'X', 'y': 'Y', 'z': 'Z', 'rx': 'A', 'ry': 'B', 'rz': 'C'}
                    krl_axis = axis_map.get(axis.lower(), 'X')
                    krl_command = f"$VEL.CORR[1] = 100"  # 设置点动速度
                    self._send_krl_command(krl_command)

                logger.info(f"KUKA jogging started on axis {axis}")
                return True
        except Exception as e:
            logger.error(f"Failed to start KUKA jogging: {e}")
            return False

    def stop_jogging(self) -> bool:
        """停止点动运动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            with self._motion_lock:
                self._is_jogging = False
                self._jogging_axis = None
                self._state = RobotState.IDLE

                if self.socket_connection:
                    krl_command = "$VEL.CORR[1] = 0"  # 停止运动
                    self._send_krl_command(krl_command)

                logger.info("KUKA jogging stopped")
                return True
        except Exception as e:
            logger.error(f"Failed to stop KUKA jogging: {e}")
            return False

    def jog_move(self, axis: str, speed: float, distance: float) -> bool:
        """点动移动指定轴"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            # KUKA实现：计算目标位置并移动
            current_pos = self.get_position()
            if not current_pos:
                return False

            axis_map = {'x': 0, 'y': 1, 'z': 2, 'rx': 3, 'ry': 4, 'rz': 5}
            if axis.lower() in axis_map:
                idx = axis_map[axis.lower()]
                new_pos = list(current_pos)
                new_pos[idx] += distance

                return self.move_to(*new_pos)
            else:
                logger.error(f"Invalid axis: {axis}")
                return False
        except Exception as e:
            logger.error(f"Failed to KUKA jog move: {e}")
            return False

    def set_motion_mode(self, mode: MotionMode) -> bool:
        """设置运动模式"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            self._motion_mode = mode
            logger.info(f"KUKA motion mode set to {mode.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to set KUKA motion mode: {e}")
            return False

    def get_motion_mode(self) -> Optional[MotionMode]:
        """获取当前运动模式"""
        return self._motion_mode

    def get_state(self) -> RobotState:
        """获取机器人当前状态"""
        try:
            if KUKA_SDK_AVAILABLE and self.krc_connection:
                # 获取KUKA运动状态
                kuka_state = self.krc_connection.get_robot_state()
                if kuka_state == 'ERROR':
                    return RobotState.ERROR
                elif kuka_state == 'MOVING':
                    return RobotState.MOVING
                else:
                    return RobotState.IDLE
            else:
                return self._state
        except Exception as e:
            logger.error(f"Failed to get KUKA robot state: {e}")
            return RobotState.ERROR

    def is_moving(self) -> bool:
        """检查是否正在运动"""
        state = self.get_state()
        return state in [RobotState.MOVING, RobotState.JOGGING]

    # ========== 路径记录方法（简化实现）==========
    def start_path_recording(self, path_name: str) -> bool:
        """开始记录路径"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            with self._path_lock:
                if self._is_recording_path:
                    logger.warning("Path recording already in progress")
                    return False

                self._is_recording_path = True
                self._path_recording_name = path_name
                self._recorded_path = RobotPath(
                    name=path_name,
                    points=[],
                    created_time=time.time(),
                    description=f"KUKA recorded on {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    id=f"kuka_path_{int(time.time())}"
                )
                logger.info(f"Started recording KUKA path: {path_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to start path recording: {e}")
            return False

    def stop_path_recording(self) -> bool:
        """停止记录路径"""
        try:
            with self._path_lock:
                if not self._is_recording_path:
                    logger.warning("No path recording in progress")
                    return False

                self._is_recording_path = False
                logger.info(f"Stopped recording KUKA path: {self._path_recording_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to stop path recording: {e}")
            return False

    def add_path_point(self, point: Optional[PathPoint] = None) -> bool:
        """添加路径点"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            with self._path_lock:
                if not self._is_recording_path:
                    logger.warning("No path recording in progress")
                    return False

                if point is None:
                    # 获取当前位置创建路径点
                    current_pos = self.get_position()
                    if current_pos:
                        position = RobotPosition(
                            x=current_pos[0], y=current_pos[1], z=current_pos[2],
                            rx=current_pos[3], ry=current_pos[4], rz=current_pos[5],
                            timestamp=time.time()
                        )
                        point = PathPoint(position=position)
                    else:
                        logger.error("Failed to get current position")
                        return False

                self._recorded_path.points.append(point)
                logger.info(f"Added KUKA path point: {point.position}")
                return True
        except Exception as e:
            logger.error(f"Failed to add path point: {e}")
            return False

    def get_recorded_path(self) -> Optional[RobotPath]:
        """获取当前记录的路径"""
        try:
            with self._path_lock:
                return self._recorded_path
        except Exception as e:
            logger.error(f"Failed to get recorded path: {e}")
            return None

    def clear_recorded_path(self) -> bool:
        """清空当前记录的路径"""
        try:
            with self._path_lock:
                self._recorded_path = None
                self._path_recording_name = ""
                logger.info("Cleared recorded path")
                return True
        except Exception as e:
            logger.error(f"Failed to clear recorded path: {e}")
            return False

    def save_path(self, path: RobotPath) -> bool:
        """保存路径到存储"""
        try:
            file_path = f"{self._path_storage_dir}/{path.id}.json"

            path_data = {
                'id': path.id,
                'name': path.name,
                'description': path.description,
                'created_time': path.created_time,
                'robot_type': 'KUKA',
                'model': self.robot_model,
                'points': [
                    {
                        'position': {
                            'x': p.position.x, 'y': p.position.y, 'z': p.position.z,
                            'rx': p.position.rx, 'ry': p.position.ry, 'rz': p.position.rz,
                            'timestamp': p.position.timestamp
                        },
                        'speed': p.speed,
                        'delay': p.delay,
                        'action': p.action
                    } for p in path.points
                ]
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(path_data, f, ensure_ascii=False, indent=2)

            logger.info(f"KUKA path saved: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save path: {e}")
            return False

    def load_path(self, path_id: str) -> Optional[RobotPath]:
        """从存储加载路径"""
        try:
            file_path = f"{self._path_storage_dir}/{path_id}.json"
            with open(file_path, 'r', encoding='utf-8') as f:
                path_data = json.load(f)

            points = []
            for point_data in path_data['points']:
                pos_data = point_data['position']
                position = RobotPosition(
                    x=pos_data['x'], y=pos_data['y'], z=pos_data['z'],
                    rx=pos_data['rx'], ry=pos_data['ry'], rz=pos_data['rz'],
                    timestamp=pos_data['timestamp']
                )
                points.append(PathPoint(
                    position=position,
                    speed=point_data['speed'],
                    delay=point_data['delay'],
                    action=point_data['action']
                ))

            path = RobotPath(
                name=path_data['name'],
                points=points,
                created_time=path_data['created_time'],
                description=path_data['description'],
                id=path_data['id']
            )

            logger.info(f"KUKA path loaded: {file_path}")
            return path
        except Exception as e:
            logger.error(f"Failed to load path: {e}")
            return None

    def delete_path(self, path_id: str) -> bool:
        """删除路径"""
        try:
            import os
            file_path = f"{self._path_storage_dir}/{path_id}.json"
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"KUKA path deleted: {file_path}")
                return True
            else:
                logger.warning(f"Path file not found: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete path: {e}")
            return False

    def list_saved_paths(self) -> List[str]:
        """列出所有保存的路径"""
        try:
            import os
            if not os.path.exists(self._path_storage_dir):
                return []

            path_files = [f for f in os.listdir(self._path_storage_dir) if f.endswith('.json')]
            path_ids = [f.replace('.json', '') for f in path_files]
            return path_ids
        except Exception as e:
            logger.error(f"Failed to list saved paths: {e}")
            return []

    def play_path(self, path: RobotPath, loop_count: int = 1) -> bool:
        """播放路径"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self._is_playing_path:
                logger.warning("Path already playing")
                return False

            self._is_playing_path = True
            self._playback_stopped.clear()

            def playback_worker():
                try:
                    for loop in range(loop_count):
                        if self._playback_stopped.is_set():
                            break

                        for point in path.points:
                            if self._playback_stopped.is_set():
                                break

                            # 使用KUKA的PTP指令
                            success = self.move_to(
                                point.position.x, point.position.y, point.position.z,
                                point.position.rx, point.position.ry, point.position.rz
                            )

                            if not success:
                                logger.error(f"Failed to move to path point: {point.position}")
                                break

                            # 设置速度
                            if point.speed != 50.0:
                                self.set_speed(point.speed)

                            # 延迟
                            if point.delay > 0:
                                time.sleep(point.delay)

                except Exception as e:
                    logger.error(f"KUKA path playback error: {e}")
                finally:
                    self._is_playing_path = False

            self._playback_thread = threading.Thread(target=playback_worker)
            self._playback_thread.daemon = True
            self._playback_thread.start()

            logger.info(f"Started KUKA path playback: {path.name}, loops: {loop_count}")
            return True
        except Exception as e:
            logger.error(f"Failed to play path: {e}")
            self._is_playing_path = False
            return False

    def stop_path_playback(self) -> bool:
        """停止路径播放"""
        try:
            if not self._is_playing_path:
                logger.warning("No path playing")
                return False

            self._playback_stopped.set()
            if self._playback_thread and self._playback_thread.is_alive():
                self._playback_thread.join(timeout=5.0)

            self._is_playing_path = False
            logger.info("KUKA path playback stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop path playback: {e}")
            return False

    def is_path_playing(self) -> bool:
        """检查是否正在播放路径"""
        return self._is_playing_path

    # ========== 高级控制功能 ==========
    def move_linear(self, start_pos: RobotPosition, end_pos: RobotPosition, speed: float) -> bool:
        """线性移动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if KUKA_SDK_AVAILABLE and self.krc_connection:
                # 使用KUKA SDK的线性移动
                return self.krc_connection.move_linear(
                    end_pos.x, end_pos.y, end_pos.z,
                    end_pos.rx, end_pos.ry, end_pos.rz, speed
                )
            else:
                # 使用KRL线性移动命令
                krl_command = f"LIN {{X {end_pos.x}, Y {end_pos.y}, Z {end_pos.z}, A {end_pos.rx}, B {end_pos.ry}, C {end_pos.rz}}} C_LIN"
                self._send_krl_command(krl_command)
                time.sleep(0.5)
                return True
        except Exception as e:
            logger.error(f"Failed to move linear: {e}")
            return False

    def move_circular(self, center: RobotPosition, radius: float, angle: float, speed: float) -> bool:
        """圆弧移动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            # KUKA圆弧移动需要辅助点和终点，这里简化实现
            import math
            end_x = center.x + radius * math.cos(math.radians(angle))
            end_y = center.y + radius * math.sin(math.radians(angle))

            # 使用KRL圆弧移动命令
            krl_command = f"CIRC {{X {end_x}, Y {end_y}, Z {center.z}, A {center.rx}, B {center.ry}, C {center.rz}}} C_CIRC"
            self._send_krl_command(krl_command)
            time.sleep(0.5)
            return True
        except Exception as e:
            logger.error(f"Failed to move circular: {e}")
            return False

    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> bool:
        """设置工件坐标系"""
        try:
            if self.socket_connection:
                # KUKA设置基础坐标
                krl_command = f"BASE_DATA[1] = {{X {wcs.get('x', 0)}, Y {wcs.get('y', 0)}, Z {wcs.get('z', 0)}, A {wcs.get('a', 0)}, B {wcs.get('b', 0)}, C {wcs.get('c', 0)}}}"
                self._send_krl_command(krl_command)
            logger.info(f"Setting KUKA work coordinate system: {wcs}")
            return True
        except Exception as e:
            logger.error(f"Failed to set work coordinate system: {e}")
            return False

    def get_work_coordinate_system(self) -> Optional[Dict[str, Any]]:
        """获取工件坐标系"""
        try:
            return {
                'origin': [0, 0, 0, 0, 0, 0],
                'rotation': [0, 0, 0],
                'name': 'KUKA_BASE1'
            }
        except Exception as e:
            logger.error(f"Failed to get work coordinate system: {e}")
            return None

    def toggle_work_coordinate_system(self) -> bool:
        """切换工件坐标系"""
        try:
            logger.info("Toggling KUKA work coordinate system")
            return True
        except Exception as e:
            logger.error(f"Failed to toggle work coordinate system: {e}")
            return False

    # ========== 回调函数方法 ==========
    def register_position_callback(self, callback) -> bool:
        """注册位置变化回调函数"""
        try:
            if callback not in self._position_callbacks:
                self._position_callbacks.append(callback)
                logger.info(f"Registered KUKA position callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to register position callback: {e}")
            return False

    def register_state_callback(self, callback) -> bool:
        """注册状态变化回调函数"""
        try:
            if callback not in self._state_callbacks:
                self._state_callbacks.append(callback)
                logger.info(f"Registered KUKA state callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to register state callback: {e}")
            return False

    def unregister_position_callback(self, callback) -> bool:
        """取消注册位置变化回调函数"""
        try:
            if callback in self._position_callbacks:
                self._position_callbacks.remove(callback)
                logger.info(f"Unregistered KUKA position callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister position callback: {e}")
            return False

    def unregister_state_callback(self, callback) -> bool:
        """取消注册状态变化回调函数"""
        try:
            if callback in self._state_callbacks:
                self._state_callbacks.remove(callback)
                logger.info(f"Unregistered KUKA state callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister state callback: {e}")
            return False