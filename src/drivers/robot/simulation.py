#!/usr/bin/env python3
"""
模拟机器人驱动
用于测试和演示完整的机器人功能
"""

import time
import threading
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from core.interfaces.hardware.robot_interface import IRobot, RobotState, MotionMode, RobotPosition, PathPoint, RobotPath
from core.managers.log_manager import info, debug, warning, error


class SimulationRobot(IRobot):
    """模拟机器人实现"""

    def __init__(self):
        """初始化模拟机器人"""
        self._connected = False
        self._state = RobotState.IDLE
        self._motion_mode = MotionMode.MANUAL
        self._current_position = RobotPosition(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, time.time())
        self._emergency_stopped = False
        self._is_moving = False

        # 路径记录相关
        self._recording_path = False
        self._current_path: Optional[RobotPath] = None
        self._saved_paths: Dict[str, RobotPath] = {}

        # 模拟运动
        self._move_thread: Optional[threading.Thread] = None
        self._stop_move = threading.Event()

        # 状态监听器
        self._position_callbacks = []
        self._state_callbacks = []

        info("Simulation robot initialized")

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接机器人"""
        if self._connected:
            warning("Robot already connected")
            return True

        info(f"Connecting simulation robot with config: {config}")
        # 模拟连接延迟
        time.sleep(0.1)
        self._connected = True
        self._state = RobotState.IDLE
        self._emergency_stopped = False

        info("Simulation robot connected successfully")
        return True

    def disconnect(self) -> bool:
        """断开连接"""
        if not self._connected:
            return True

        info("Disconnecting simulation robot")

        # 停止所有运动
        self.emergency_stop()

        self._connected = False
        self._state = RobotState.IDLE

        info("Simulation robot disconnected")
        return True

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    def move_to(self, x: float, y: float, z: float,
                rx: float = 0, ry: float = 0, rz: float = 0) -> bool:
        """移动到指定位置"""
        if not self._connected or self._emergency_stopped:
            return False

        info(f"Moving to position: ({x}, {y}, {z}, {rx}, {ry}, {rz})")

        # 创建运动线程
        if self._move_thread and self._move_thread.is_alive():
            self._stop_move.set()
            self._move_thread.join()

        self._stop_move.clear()
        target_position = RobotPosition(x, y, z, rx, ry, rz, time.time())

        self._move_thread = threading.Thread(
            target=self._simulate_movement,
            args=(target_position,),
            daemon=True
        )
        self._move_thread.start()

        return True

    def get_position(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """获取当前位置"""
        if not self._connected:
            return None
        return (
            self._current_position.x, self._current_position.y, self._current_position.z,
            self._current_position.rx, self._current_position.ry, self._current_position.rz
        )

    def home(self) -> bool:
        """回到原点"""
        if not self._connected:
            return False

        info("Moving to home position")
        return self.move_to(0, 0, 0, 0, 0, 0)

    def emergency_stop(self) -> bool:
        """紧急停止"""
        warning("Emergency stop activated")
        self._emergency_stopped = True
        self._state = RobotState.EMERGENCY_STOP

        # 停止运动
        if self._move_thread and self._move_thread.is_alive():
            self._stop_move.set()
            self._move_thread.join()

        self._is_moving = False
        return True

    def set_speed(self, speed: float) -> bool:
        """设置速度 (0-100%)"""
        if not self._connected:
            return False

        speed = max(0, min(100, speed))
        info(f"Speed set to {speed}%")
        return True

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        return {
            'type': 'Simulation Robot',
            'model': 'SIM-001',
            'firmware': '1.0.0',
            'serial_number': 'SIM-12345',
            'max_payload': '10kg',
            'reach_radius': '2000mm',
            'degrees_of_freedom': 6
        }

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self._connected:
            return {'success': False, 'error': 'Not connected'}

        return {
            'success': True,
            'device_info': self.get_info(),
            'response_time_ms': 5,
            'status': 'healthy'
        }

    # ========== 实时控制相关方法 ==========
    def start_jogging(self, axis: str) -> bool:
        """开始点动运动"""
        if not self._connected:
            return False

        info(f"Start jogging axis: {axis}")
        self._is_moving = True
        return True

    def stop_jogging(self) -> bool:
        """停止点动运动"""
        if not self._connected:
            return False

        info("Stop jogging")
        self._is_moving = False
        return True

    def jog_move(self, axis: str, speed: float, distance: float) -> bool:
        """点动移动指定轴"""
        if not self._connected:
            return False

        info(f"Jog move: axis={axis}, speed={speed}, distance={distance}")

        # 简单的位置更新
        current_pos = list(self.get_position())
        axis_map = {'x': 0, 'y': 1, 'z': 2, 'rx': 3, 'ry': 4, 'rz': 5}
        if axis.lower() in axis_map:
            idx = axis_map[axis.lower()]
            current_pos[idx] += distance

            return self.move_to(*current_pos)

        return False

    def set_motion_mode(self, mode: MotionMode) -> bool:
        """设置运动模式"""
        if not self._connected:
            return False

        self._motion_mode = mode
        info(f"Motion mode set to: {mode.value}")
        return True

    def get_motion_mode(self) -> Optional[MotionMode]:
        """获取当前运动模式"""
        return self._motion_mode

    def get_state(self) -> RobotState:
        """获取机器人当前状态"""
        return self._state

    def is_moving(self) -> bool:
        """检查是否正在运动"""
        return self._is_moving

    # ========== 路径记录相关方法 ==========
    def start_path_recording(self, path_name: str) -> bool:
        """开始记录路径"""
        if not self._connected or self._recording_path:
            return False

        info(f"Start recording path: {path_name}")
        self._recording_path = True
        self._current_path = RobotPath(
            name=path_name,
            points=[],
            created_time=time.time(),
            description=f"Path recorded on {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # 添加当前位置作为第一个点
        self.add_path_point()
        return True

    def stop_path_recording(self) -> bool:
        """停止记录路径"""
        if not self._recording_path:
            return False

        info("Stop recording path")
        self._recording_path = False
        return True

    def add_path_point(self, point: Optional[PathPoint] = None) -> bool:
        """添加路径点"""
        if not self._recording_path or not self._current_path:
            return False

        if point is None:
            # 使用当前位置
            current_pos = self.get_position()
            if current_pos:
                point = PathPoint(
                    position=RobotPosition(*current_pos, time.time()),
                    speed=50.0
                )

        if point:
            self._current_path.points.append(point)
            debug(f"Added path point {len(self._current_path.points)}: {point.position}")
            return True

        return False

    def get_recorded_path(self) -> Optional[RobotPath]:
        """获取当前记录的路径"""
        return self._current_path

    def clear_recorded_path(self) -> bool:
        """清空当前记录的路径"""
        self._current_path = None
        self._recording_path = False
        return True

#    def save_path_REMOVED(self, path: RobotPath) -> bool:
        """保存路径到存储"""
        if not path or not path.points:
            return False

        import json
        from pathlib import Path

        # 确保paths目录存在
        paths_dir = Path("workspace/paths")
        paths_dir.mkdir(parents=True, exist_ok=True)

        # 生成路径ID
        path_id = f"path_{int(time.time())}"
        path.id = path_id

        # 转换路径为JSON可序列化格式
        path_data = {
            'id': path.id,
            'name': path.name,
            'created_time': path.created_time,
            'description': path.description,
            'points': []
        }

        # 添加路径点
        for i, point in enumerate(path.points):
            point_data = {
                'index': i,
                'position': {
                    'x': point.position.x,
                    'y': point.position.y,
                    'z': point.position.z,
                    'rx': point.position.rx,
                    'ry': point.position.ry,
                    'rz': point.position.rz,
                    'timestamp': point.position.timestamp
                },
                'speed': point.speed,
                'delay': point.delay,
                'action': point.action
            }
            path_data['points'].append(point_data)

        # 保存到JSON文件
        try:
            with open(paths_dir / f"{path_id}.json", 'w', encoding='utf-8') as f:
                json.dump(path_data, f, indent=2, ensure_ascii=False)

            info(f"Path saved to file: {paths_dir}/{path_id}.json")
            info(f"Path saved: {path.name} (ID: {path_id}) with {len(path.points)} points")

            # 同时保存在内存中用于快速访问
            self._saved_paths[path_id] = path
            return True

        except Exception as e:
            error(f"Failed to save path to file: {e}")
            return False

#    def load_path_REMOVED(self, path_id: str) -> Optional[RobotPath]:
        """从存储加载路径"""
        import json
        from pathlib import Path

        # 首先尝试从内存中获取
        if path_id in self._saved_paths:
            return self._saved_paths[path_id]

        # 尝试从文件加载
        paths_dir = Path("workspace/paths")
        path_file = paths_dir / f"{path_id}.json"

        if path_file.exists():
            try:
                with open(path_file, 'r', encoding='utf-8') as f:
                    path_data = json.load(f)

                # 重构RobotPath对象
                points = []
                for point_data in path_data.get('points', []):
                    position_data = point_data['position']
                    position = RobotPosition(
                        x=position_data['x'],
                        y=position_data['y'],
                        z=position_data['z'],
                        rx=position_data['rx'],
                        ry=position_data['ry'],
                        rz=position_data['rz'],
                        timestamp=position_data.get('timestamp', time.time())
                    )

                    point = PathPoint(
                        position=position,
                        speed=point_data.get('speed', 50.0),
                        delay=point_data.get('delay', 0.0),
                        action=point_data.get('action', '')
                    )
                    points.append(point)

                path = RobotPath(
                    name=path_data.get('name', ''),
                    points=points,
                    created_time=path_data.get('created_time', time.time()),
                    description=path_data.get('description', ''),
                    id=path_data.get('id', path_id)
                )

                # 缓存到内存中
                self._saved_paths[path_id] = path

                info(f"Path loaded from file: {path_id}")
                return path

            except Exception as e:
                error(f"Failed to load path from file {path_file}: {e}")
                return None
        else:
            warning(f"Path file not found: {path_file}")
            return None

#    def delete_path_REMOVED(self, path_id: str) -> bool:
        """删除路径"""
        import json
        from pathlib import Path

        # 删除内存中的路径
        if path_id in self._saved_paths:
            del self._saved_paths[path_id]

        # 删除文件
        paths_dir = Path("workspace/paths")
        path_file = paths_dir / f"{path_id}.json"

        if path_file.exists():
            try:
                path_file.unlink()
                info(f"Path file deleted: {path_file}")
                return True
            except Exception as e:
                error(f"Failed to delete path file {path_file}: {e}")
                return False
        else:
            warning(f"Path file not found: {path_file}")
            return True  # 如果文件不存在，认为删除成功

#    def list_saved_paths_REMOVED(self) -> List[str]:
        """列出所有保存的路径"""
        import json
        from pathlib import Path

        paths_dir = Path("workspace/paths")
        if not paths_dir.exists():
            return []

        path_files = list(paths_dir.glob("*.json"))
        path_ids = []

        for path_file in path_files:
            path_id = path_file.stem  # 移除.json后缀
            try:
                with open(path_file, 'r', encoding='utf-8') as f:
                    path_data = json.load(f)
                    if isinstance(path_data, dict) and 'id' in path_data:
                        # 确保内存中也有这个路径
                        if path_id not in self._saved_paths:
                            # 尝试加载到内存
                            loaded_path = self.load_path(path_id)
                    path_ids.append(path_id)
            except Exception as e:
                error(f"Failed to read path file {path_file}: {e}")

        return list(set(path_ids))  # 去重

    def play_path(self, path: RobotPath, loop_count: int = 1) -> bool:
        """播放路径"""
        if not self._connected or not path or not path.points:
            return False

        info(f"Playing path: {path.name}, {loop_count} loops")

        # 创建播放线程
        def play_thread():
            for loop in range(loop_count):
                if self._emergency_stopped:
                    break

                info(f"Playing loop {loop + 1}/{loop_count}")
                for i, point in enumerate(path.points):
                    if self._emergency_stopped:
                        break

                    debug(f"Moving to point {i+1}/{len(path.points)}: {point.position}")
                    self.move_to(
                        point.position.x, point.position.y, point.position.z,
                        point.position.rx, point.position.ry, point.position.rz
                    )

                    # 等待运动完成
                    while self._is_moving and not self._emergency_stopped:
                        time.sleep(0.1)

                    time.sleep(point.delay / 1000.0 if point.delay else 0.1)

        threading.Thread(target=play_thread, daemon=True).start()
        return True

    def stop_path_playback(self) -> bool:
        """停止路径播放"""
        self.emergency_stop()
        return True

    def is_path_playing(self) -> bool:
        """检查是否正在播放路径"""
        return self._is_moving

    # ========== 高级控制功能 ==========
    def move_linear(self, start_pos: RobotPosition, end_pos: RobotPosition, speed: float) -> bool:
        """线性移动"""
        info(f"Linear move from {start_pos} to {end_pos}")
        return self.move_to(end_pos.x, end_pos.y, end_pos.z, end_pos.rx, end_pos.ry, end_pos.rz)

    def move_circular(self, center: RobotPosition, radius: float, angle: float, speed: float) -> bool:
        """圆弧移动"""
        info(f"Circular move: center={center}, radius={radius}, angle={angle}")
        # 简化实现：移动到圆弧终点
        return True

    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> bool:
        """设置工件坐标系"""
        info(f"Work coordinate system set: {wcs}")
        return True

    def get_work_coordinate_system(self) -> Optional[Dict[str, Any]]:
        """获取工件坐标系"""
        return {'type': 'cartesian', 'units': 'mm'}

    def toggle_work_coordinate_system(self) -> bool:
        """切换工件坐标系"""
        info("Toggle work coordinate system")
        return True

    # ========== 私有方法 ==========
    def _simulate_movement(self, target_position: RobotPosition):
        """模拟运动过程"""
        self._is_moving = True
        self._state = RobotState.MOVING

        # 计算运动参数
        start_pos = self._current_position
        distance = ((target_position.x - start_pos.x) ** 2 +
                   (target_position.y - start_pos.y) ** 2 +
                   (target_position.z - start_pos.z) ** 2) ** 0.5

        # 模拟运动时间（基于距离）
        move_time = max(0.1, distance / 100.0)  # 100mm/s
        steps = int(move_time * 20)  # 20 steps per second

        debug(f"Simulating movement: {distance:.1f}mm in {move_time:.2f}s")

        for i in range(steps):
            if self._stop_move.is_set():
                break

            # 线性插值
            t = (i + 1) / steps
            self._current_position = RobotPosition(
                start_pos.x + (target_position.x - start_pos.x) * t,
                start_pos.y + (target_position.y - start_pos.y) * t,
                start_pos.z + (target_position.z - start_pos.z) * t,
                start_pos.rx + (target_position.rx - start_pos.rx) * t,
                start_pos.ry + (target_position.ry - start_pos.ry) * t,
                start_pos.rz + (target_position.rz - start_pos.rz) * t,
                time.time()
            )

            # 通知位置监听器
            for callback in self._position_callbacks:
                try:
                    callback(self._current_position)
                except:
                    pass

            time.sleep(move_time / steps)

        if not self._stop_move.is_set():
            self._current_position = target_position
            # 最终通知
            for callback in self._position_callbacks:
                try:
                    callback(self._current_position)
                except:
                    pass

        self._is_moving = False
        if not self._emergency_stopped:
            self._state = RobotState.IDLE

        debug(f"Movement completed, final position: {self._current_position}")

    def register_position_callback(self, callback) -> bool:
        """注册位置变化回调函数"""
        self._position_callbacks.append(callback)
        return True

    def register_state_callback(self, callback) -> bool:
        """注册状态变化回调函数"""
        self._state_callbacks.append(callback)
        return True

    def unregister_position_callback(self, callback) -> bool:
        """取消注册位置变化回调函数"""
        if callback in self._position_callbacks:
            self._position_callbacks.remove(callback)
        return True

    def unregister_state_callback(self, callback) -> bool:
        """取消注册状态变化回调函数"""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
        return True