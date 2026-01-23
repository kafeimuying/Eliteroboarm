"""
Yamaha机器人驱动实现
调用Yamaha SDK进行具体设备控制
"""

import time
import threading
import json
from typing import Optional, Tuple, Dict, Any, List
from core.interfaces.hardware.robot_interface import IRobot, RobotState, MotionMode, RobotPosition, PathPoint, RobotPath

try:
    # 尝试导入Yamaha官方SDK（如果存在）
    import yamaha_sdk as yamaha_sdk
    YAMAHA_SDK_AVAILABLE = True
except ImportError:
    # 如果没有官方SDK，无法连接真实设备
    YAMAHA_SDK_AVAILABLE = False

from core.managers.log_manager import warning, info, error, debug


class YamahaRobot(IRobot):
    """Yamaha机器人驱动实现"""

    def __init__(self):
        self.sdk = None
        self.connected = False
        self.current_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self.config = {}

        # 检查SDK可用性（在初始化时才显示警告）
        if not YAMAHA_SDK_AVAILABLE:
            warning("Yamaha SDK not available - real robot connection not possible", "ROBOT_DRIVER")

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

        # 路径存储（使用文件系统）
        self._path_storage_dir = "paths"
        import os
        os.makedirs(self._path_storage_dir, exist_ok=True)

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接Yamaha机器人"""
        try:
            self.config = config
            info(f"Connecting to Yamaha robot at {config.get('ip')}:{config.get('port')}", "ROBOT_DRIVER")

            if not YAMAHA_SDK_AVAILABLE:
                error("Yamaha SDK not available - cannot connect to real robot", "ROBOT_DRIVER")
                return False

            # 使用官方SDK连接
            self.sdk = yamaha_sdk.RobotController()
            success = self.sdk.connect(
                ip=config['ip'],
                port=config.get('port', 8080),
                timeout=config.get('timeout', 5.0)
            )

            if success:
                self.connected = True
                info(f"Yamaha robot connected successfully at {config.get('ip')}", "ROBOT_DRIVER")
            else:
                error(f"Failed to connect to Yamaha robot at {config.get('ip')}", "ROBOT_DRIVER")
                self.connected = False

            return self.connected

        except Exception as e:
            error(f"Failed to connect Yamaha robot: {e}", "ROBOT_DRIVER")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                self.sdk.disconnect()
                self.sdk = None

            self.connected = False
            info("Yamaha robot disconnected", "ROBOT_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to disconnect Yamaha robot: {e}", "ROBOT_DRIVER")
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        if self.sdk and YAMAHA_SDK_AVAILABLE:
            return self.sdk.is_connected()
        return self.connected

    def move_to(self, x: float, y: float, z: float,
                rx: float = 0, ry: float = 0, rz: float = 0) -> bool:
        """移动到指定位置"""
        if not self.is_connected():
            error("Robot not connected", "ROBOT_DRIVER")
            return False

        try:
            info(f"Moving to position ({x}, {y}, {z}, {rx}, {ry}, {rz})", "ROBOT_DRIVER")

            if self.sdk and YAMAHA_SDK_AVAILABLE:
                # 使用官方SDK移动
                success = self.sdk.move_to_position(x, y, z, rx, ry, rz)
                if success:
                    self.current_position = (x, y, z, rx, ry, rz)
                return success
            else:
                error("SDK not available - cannot move real robot", "ROBOT_DRIVER")
                return False

        except Exception as e:
            error(f"Failed to move robot: {e}", "ROBOT_DRIVER")
            return False

    def get_position(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """获取当前位置"""
        if not self.is_connected():
            logger.warning("Robot not connected")
            return None

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                # 使用官方SDK获取位置
                position = self.sdk.get_current_position()
                if position:
                    self.current_position = position
                    return position
            else:
                # 返回缓存位置
                return self.current_position

        except Exception as e:
            logger.error(f"Failed to get position: {e}")

        return self.current_position

    def home(self) -> bool:
        """回到原点"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            logger.info("Moving to home position")

            if self.sdk and YAMAHA_SDK_AVAILABLE:
                success = self.sdk.home()
                if success:
                    self.current_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                return success
            else:
                # 模拟回原点
                time.sleep(0.3)
                self.current_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                logger.info("Mock home completed successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to move home: {e}")
            return False

    def emergency_stop(self) -> bool:
        """紧急停止"""
        try:
            logger.warning("Emergency stop activated")

            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.emergency_stop()
            else:
                # 模拟紧急停止
                self.current_position = self.get_position()
                logger.warning("Mock emergency stop completed")
                return True

        except Exception as e:
            logger.error(f"Failed to emergency stop: {e}")
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

            logger.info(f"Setting speed to {speed}%")

            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.set_speed(speed)
            else:
                # 模拟设置速度
                logger.info(f"Mock speed set to {speed}%")
                return True

        except Exception as e:
            logger.error(f"Failed to set speed: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        info = {
            'brand': 'Yamaha',
            'type': 'Robot',
            'connected': self.is_connected(),
            'model': self.config.get('model', 'Unknown'),
            'ip': self.config.get('ip', 'Unknown'),
            'sdk_available': YAMAHA_SDK_AVAILABLE
        }

        if self.sdk and YAMAHA_SDK_AVAILABLE:
            try:
                sdk_info = self.sdk.get_robot_info()
                info.update(sdk_info)
            except Exception as e:
                logger.warning(f"Failed to get SDK info: {e}")

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

    # ========== 实时控制相关方法实现 ==========
    def start_jogging(self, axis: str) -> bool:
        """开始点动运动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.start_jogging(axis)
            else:
                # 模拟点动
                with self._motion_lock:
                    self._is_jogging = True
                    self._jogging_axis = axis
                    self._state = RobotState.JOGGING
                logger.info(f"Mock jogging started on axis {axis}")
                return True
        except Exception as e:
            logger.error(f"Failed to start jogging: {e}")
            return False

    def stop_jogging(self) -> bool:
        """停止点动运动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.stop_jogging()
            else:
                # 模拟停止点动
                with self._motion_lock:
                    self._is_jogging = False
                    self._jogging_axis = None
                    self._state = RobotState.IDLE
                logger.info("Mock jogging stopped")
                return True
        except Exception as e:
            logger.error(f"Failed to stop jogging: {e}")
            return False

    def jog_move(self, axis: str, speed: float, distance: float) -> bool:
        """点动移动指定轴"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.jog_move(axis, speed, distance)
            else:
                # 模拟点动移动
                with self._motion_lock:
                    if self._state != RobotState.JOGGING:
                        return False

                    # 模拟移动效果
                    time.sleep(0.1)
                    logger.info(f"Mock jog move: axis {axis}, speed {speed}, distance {distance}")
                return True
        except Exception as e:
            logger.error(f"Failed to jog move: {e}")
            return False

    def set_motion_mode(self, mode: MotionMode) -> bool:
        """设置运动模式"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.set_motion_mode(mode.value)
            else:
                # 模拟设置模式
                self._motion_mode = mode
                logger.info(f"Mock motion mode set to {mode.value}")
                return True
        except Exception as e:
            logger.error(f"Failed to set motion mode: {e}")
            return False

    def get_motion_mode(self) -> Optional[MotionMode]:
        """获取当前运动模式"""
        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                mode_str = self.sdk.get_motion_mode()
                return MotionMode(mode_str)
            else:
                return self._motion_mode
        except Exception as e:
            logger.error(f"Failed to get motion mode: {e}")
            return None

    def get_state(self) -> RobotState:
        """获取机器人当前状态"""
        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                state_str = self.sdk.get_state()
                return RobotState(state_str)
            else:
                return self._state
        except Exception as e:
            logger.error(f"Failed to get robot state: {e}")
            return RobotState.ERROR

    def is_moving(self) -> bool:
        """检查是否正在运动"""
        state = self.get_state()
        return state in [RobotState.MOVING, RobotState.JOGGING]

    # ========== 路径记录相关方法实现 ==========
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
                    description=f"Recorded on {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    id=f"path_{int(time.time())}"
                )
                logger.info(f"Started recording path: {path_name}")
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
                logger.info(f"Stopped recording path: {self._path_recording_name}")
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
                logger.info(f"Added path point: {point.position}")
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

            # 将路径数据转换为可序列化的格式
            path_data = {
                'id': path.id,
                'name': path.name,
                'description': path.description,
                'created_time': path.created_time,
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

            logger.info(f"Path saved: {file_path}")
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

            # 重建路径对象
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

            logger.info(f"Path loaded: {file_path}")
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
                logger.info(f"Path deleted: {file_path}")
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

                            # 移动到路径点
                            success = self.move_to(
                                point.position.x, point.position.y, point.position.z,
                                point.position.rx, point.position.ry, point.position.rz
                            )

                            if not success:
                                logger.error(f"Failed to move to path point: {point.position}")
                                break

                            # 设置速度
                            if point.speed != 50.0:  # 默认速度
                                self.set_speed(point.speed)

                            # 延迟
                            if point.delay > 0:
                                time.sleep(point.delay)

                except Exception as e:
                    logger.error(f"Path playback error: {e}")
                finally:
                    self._is_playing_path = False

            self._playback_thread = threading.Thread(target=playback_worker)
            self._playback_thread.daemon = True
            self._playback_thread.start()

            logger.info(f"Started path playback: {path.name}, loops: {loop_count}")
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
            logger.info("Path playback stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop path playback: {e}")
            return False

    def is_path_playing(self) -> bool:
        """检查是否正在播放路径"""
        return self._is_playing_path

    # ========== 高级控制功能实现 ==========
    def move_linear(self, start_pos: RobotPosition, end_pos: RobotPosition, speed: float) -> bool:
        """线性移动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.move_linear(
                    start_pos.x, start_pos.y, start_pos.z,
                    end_pos.x, end_pos.y, end_pos.z, speed
                )
            else:
                # 模拟线性移动
                self.set_speed(speed)
                success = self.move_to(end_pos.x, end_pos.y, end_pos.z,
                                     end_pos.rx, end_pos.ry, end_pos.rz)
                logger.info(f"Mock linear move from {start_pos} to {end_pos}")
                return success
        except Exception as e:
            logger.error(f"Failed to move linear: {e}")
            return False

    def move_circular(self, center: RobotPosition, radius: float, angle: float, speed: float) -> bool:
        """圆弧移动"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            import math
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.move_circular(center.x, center.y, center.z, radius, angle, speed)
            else:
                # 模拟圆弧移动（简化为直线移动到终点）
                self.set_speed(speed)
                # 计算圆弧终点
                end_x = center.x + radius * math.cos(math.radians(angle))
                end_y = center.y + radius * math.sin(math.radians(angle))
                success = self.move_to(end_x, end_y, center.z, center.rx, center.ry, center.rz)
                logger.info(f"Mock circular move: center {center}, radius {radius}, angle {angle}")
                return success
        except Exception as e:
            logger.error(f"Failed to move circular: {e}")
            return False

    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> bool:
        """设置工件坐标系"""
        if not self.is_connected():
            logger.error("Robot not connected")
            return False

        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.set_work_coordinate_system(wcs)
            else:
                # 模拟设置工件坐标系
                logger.info(f"Mock set work coordinate system: {wcs}")
                return True
        except Exception as e:
            logger.error(f"Failed to set work coordinate system: {e}")
            return False

    def get_work_coordinate_system(self) -> Optional[Dict[str, Any]]:
        """获取工件坐标系"""
        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.get_work_coordinate_system()
            else:
                # 返回默认工件坐标系
                return {
                    'origin': [0, 0, 0, 0, 0, 0],
                    'rotation': [0, 0, 0],
                    'name': 'WCS1'
                }
        except Exception as e:
            logger.error(f"Failed to get work coordinate system: {e}")
            return None

    def toggle_work_coordinate_system(self) -> bool:
        """切换工件坐标系"""
        try:
            if self.sdk and YAMAHA_SDK_AVAILABLE:
                return self.sdk.toggle_work_coordinate_system()
            else:
                # 模拟切换工件坐标系
                logger.info("Mock toggle work coordinate system")
                return True
        except Exception as e:
            logger.error(f"Failed to toggle work coordinate system: {e}")
            return False

    # ========== 信号和回调相关实现 ==========
    def register_position_callback(self, callback) -> bool:
        """注册位置变化回调函数"""
        try:
            if callback not in self._position_callbacks:
                self._position_callbacks.append(callback)
                logger.info(f"Registered position callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to register position callback: {e}")
            return False

    def register_state_callback(self, callback) -> bool:
        """注册状态变化回调函数"""
        try:
            if callback not in self._state_callbacks:
                self._state_callbacks.append(callback)
                logger.info(f"Registered state callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to register state callback: {e}")
            return False

    def unregister_position_callback(self, callback) -> bool:
        """取消注册位置变化回调函数"""
        try:
            if callback in self._position_callbacks:
                self._position_callbacks.remove(callback)
                logger.info(f"Unregistered position callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister position callback: {e}")
            return False

    def unregister_state_callback(self, callback) -> bool:
        """取消注册状态变化回调函数"""
        try:
            if callback in self._state_callbacks:
                self._state_callbacks.remove(callback)
                logger.info(f"Unregistered state callback: {callback}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister state callback: {e}")
            return False