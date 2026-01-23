"""
机器人服务层
提供机器人的高级业务逻辑和UI接口
"""

from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
from ..interfaces.hardware import IRobot, RobotState, MotionMode, RobotPosition, PathPoint, RobotPath
from .robot_factory import RobotFactory
from ..managers.log_manager import info, debug, warning, error
from ..managers.app_config import AppConfigManager


class RobotService:
    """机器人服务类，封装业务逻辑"""

    def __init__(self, robot: Optional[IRobot] = None):
        self.robot = robot

        # 获取统一的路径配置
        self.app_config = AppConfigManager()
        self.paths_dir = self.app_config.paths_dir

        # 业务状态
        self._emergency_stopped = False
        self._position_history: list = []

    @staticmethod
    def get_robot_service(hardware_id: str) -> Optional['RobotService']:
        """
        获取机器人服务实例的工厂方法
        
        Args:
            hardware_id: 硬件ID
            
        Returns:
            RobotService实例，失败返回None
        """
        try:
            # 从HardwareManager获取机器人实例
            from ..managers.hardware_manager import HardwareManager
            from ..container import Container
            from ..managers.app_config import AppConfigManager
            from ..managers.log_manager import LogManager
            
            container = Container()
            config_manager = AppConfigManager()
            log_manager = LogManager()
            hardware_manager = HardwareManager(container, config_manager, log_manager)
            
            # 初始化硬件管理器（如果尚未初始化）
            if not hardware_manager.hardware_config:
                hardware_manager.initialize_from_config()
            
            # 获取机器人实例
            robot = hardware_manager.get_robot(hardware_id)
            if robot is None:
                error(f"Robot '{hardware_id}' not found in hardware manager", "ROBOT_SERVICE")
                return None
                
            return RobotService(robot)
            
        except Exception as e:
            error(f"Failed to create robot service for '{hardware_id}': {e}", "ROBOT_SERVICE")
            return None

    def set_robot(self, robot: IRobot):
        """设置机器人实例（用于运行时切换）"""
        self.robot = robot
        self._emergency_stopped = False
        self._position_history.clear()
        info("Robot service updated with new robot instance", "ROBOT_SERVICE")

    def register_log_callback(self, callback):
        """注册日志回调"""
        if self.robot and hasattr(self.robot, 'register_log_callback'):
            self.robot.register_log_callback(callback)

    def unregister_log_callback(self, callback):
        """取消注册日志回调"""
        if self.robot and hasattr(self.robot, 'unregister_log_callback'):
            self.robot.unregister_log_callback(callback)

    def set_device(self, robot: IRobot):
        """设置设备实例（与set_robot功能相同，用于统一接口）"""
        self.set_robot(robot)

    def connect(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """连接机器人"""
        robot_name = config.get('name', 'Unknown Robot')
        info(f"Attempting to connect to robot: {robot_name}")

        try:
            # 如果没有机器人实例，尝试自动创建
            if not self.robot:
                debug(f"No robot instance available, creating from config for {robot_name}", "ROBOT_SERVICE")
                self.robot = RobotFactory.create_robot(config)
                if not self.robot:
                    error(f"Failed to create robot driver for {robot_name}", "ROBOT_SERVICE")
                    return {'success': False, 'error': 'Failed to create robot driver'}

            success = self.robot.connect(config)
            if success:
                self._emergency_stopped = False
                info(f"Robot '{robot_name}' connected successfully", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Robot connected'}
            else:
                error(f"Failed to connect robot: {robot_name}", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to connect robot'}
        except Exception as e:
            error(f"Robot connection error for '{robot_name}': {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def disconnect(self) -> Dict[str, Any]:
        """断开机器人连接"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        info("Disconnecting robot", "ROBOT_SERVICE")

        try:
            success = self.robot.disconnect()
            if success:
                self._emergency_stopped = False
                info("Robot disconnected successfully", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Robot disconnected'}
            else:
                error("Failed to disconnect robot", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to disconnect robot'}
        except Exception as e:
            error(f"Robot disconnection error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def is_connected(self) -> bool:
        """检查连接状态"""
        if not self.robot:
            return False
        return self.robot.is_connected()

    def move_to(self, x: float, y: float, z: float,
                rx: float = 0, ry: float = 0, rz: float = 0) -> Dict[str, Any]:
        """移动到指定位置"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.move_to(x, y, z, rx, ry, rz)
            if success:
                info(f"Robot moving to: ({x}, {y}, {z}, {rx}, {ry}, {rz})", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Movement started'}
            else:
                error("Failed to start movement", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start movement'}
        except Exception as e:
            error(f"Robot move error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def get_position(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """获取当前位置"""
        if not self.robot:
            return None

        try:
            return self.robot.get_position()
        except Exception as e:
            error(f"Failed to get position: {e}", "ROBOT_SERVICE")
            return None

    def home(self) -> Dict[str, Any]:
        """回到原点"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.home()
            if success:
                info("Robot moving to home position", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Homing started'}
            else:
                error("Failed to start homing", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start homing'}
        except Exception as e:
            error(f"Robot home error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def emergency_stop(self) -> Dict[str, Any]:
        """紧急停止"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.emergency_stop()
            if success:
                warning("Emergency stop activated", "ROBOT_SERVICE")
                self._emergency_stopped = True
                return {'success': True, 'message': 'Emergency stop activated'}
            else:
                error("Failed to activate emergency stop", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to activate emergency stop'}
        except Exception as e:
            error(f"Emergency stop error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def set_speed(self, speed: float) -> Dict[str, Any]:
        """设置速度 (0-100%)"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.set_speed(speed)
            if success:
                info(f"Robot speed set to {speed}%", "ROBOT_SERVICE")
                return {'success': True, 'message': f'Speed set to {speed}%'}
            else:
                error("Failed to set speed", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to set speed'}
        except Exception as e:
            error(f"Set speed error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def get_info(self) -> Optional[Dict[str, Any]]:
        """获取机器人信息"""
        if not self.robot:
            return None

        try:
            return self.robot.get_info()
        except Exception as e:
            error(f"Failed to get robot info: {e}", "ROBOT_SERVICE")
            return None

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            return self.robot.test_connection()
        except Exception as e:
            error(f"Connection test error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def confirm_calibration(self) -> Dict[str, Any]:
        """确认标定步骤 (发送回车)"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            if hasattr(self.robot, 'confirm_calibration'):
                if self.robot.confirm_calibration():
                    return {'success': True, 'message': 'Confirmation sent'}
                else:
                    return {'success': False, 'error': 'Failed to send confirmation'}
            else:
                return {'success': False, 'error': 'Operation not supported by this driver'}
        except Exception as e:
            error(f"Confirm calibration error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'connected': self.is_connected(),
            'emergency_stopped': self._emergency_stopped,
            'current_position': self.get_position(),
            'position_history_count': len(self._position_history)
        }

    def get_position_history(self) -> list:
        """获取位置历史"""
        return self._position_history.copy()

    def clear_position_history(self):
        """清空位置历史"""
        self._position_history.clear()

    # ========== 实时控制相关方法 ==========
    def start_jogging(self, axis: str) -> Dict[str, Any]:
        """开始点动运动"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.start_jogging(axis)
            if success:
                info(f"Jogging started on axis: {axis}", "ROBOT_SERVICE")
                return {'success': True, 'message': f'Jogging started on axis {axis}'}
            else:
                error("Failed to start jogging", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start jogging'}
        except Exception as e:
            error(f"Start jogging error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def stop_jogging(self) -> Dict[str, Any]:
        """停止点动运动"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.stop_jogging()
            if success:
                info("Jogging stopped", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Jogging stopped'}
            else:
                error("Failed to stop jogging", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to stop jogging'}
        except Exception as e:
            error(f"Stop jogging error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def jog_move(self, axis: str, speed: float, distance: float) -> Dict[str, Any]:
        """点动移动指定轴"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.jog_move(axis, speed, distance)
            if success:
                info(f"Jog move: axis={axis}, speed={speed}, distance={distance}", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Jog move executed'}
            else:
                error("Failed to execute jog move", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to execute jog move'}
        except Exception as e:
            error(f"Jog move error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def set_motion_mode(self, mode: MotionMode) -> Dict[str, Any]:
        """设置运动模式"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.set_motion_mode(mode)
            if success:
                info(f"Motion mode set to: {mode.value}", "ROBOT_SERVICE")
                return {'success': True, 'message': f'Motion mode set to {mode.value}'}
            else:
                error("Failed to set motion mode", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to set motion mode'}
        except Exception as e:
            error(f"Set motion mode error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def get_motion_mode(self) -> Optional[MotionMode]:
        """获取当前运动模式"""
        if not self.robot:
            return None

        try:
            return self.robot.get_motion_mode()
        except Exception as e:
            error(f"Get motion mode error: {e}", "ROBOT_SERVICE")
            return None

    def get_state(self) -> RobotState:
        """获取机器人当前状态"""
        if not self.robot:
            return RobotState.ERROR

        try:
            return self.robot.get_state()
        except Exception as e:
            error(f"Get robot state error: {e}", "ROBOT_SERVICE")
            return RobotState.ERROR

    def is_moving(self) -> bool:
        """检查是否正在运动"""
        if not self.robot:
            return False

        try:
            return self.robot.is_moving()
        except Exception as e:
            error(f"Check moving status error: {e}", "ROBOT_SERVICE")
            return False

    # ========== 路径记录相关方法 ==========
    def start_path_recording(self, path_name: str) -> Dict[str, Any]:
        """开始记录路径"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.start_path_recording(path_name)
            if success:
                info(f"Path recording started: {path_name}", "ROBOT_SERVICE")
                return {'success': True, 'message': f'Path recording started: {path_name}'}
            else:
                error("Failed to start path recording", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start path recording'}
        except Exception as e:
            error(f"Start path recording error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def stop_path_recording(self) -> Dict[str, Any]:
        """停止记录路径"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.stop_path_recording()
            if success:
                info("Path recording stopped", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Path recording stopped'}
            else:
                error("Failed to stop path recording", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to stop path recording'}
        except Exception as e:
            error(f"Stop path recording error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def add_path_point(self, point: Optional[PathPoint] = None) -> Dict[str, Any]:
        """添加路径点"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.add_path_point(point)
            if success:
                info("Path point added", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Path point added'}
            else:
                error("Failed to add path point", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to add path point'}
        except Exception as e:
            error(f"Add path point error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def get_recorded_path(self) -> Optional[RobotPath]:
        """获取当前记录的路径"""
        if not self.robot:
            return None

        try:
            return self.robot.get_recorded_path()
        except Exception as e:
            error(f"Get recorded path error: {e}", "ROBOT_SERVICE")
            return None

    def clear_recorded_path(self) -> Dict[str, Any]:
        """清空记录的路径"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.clear_recorded_path()
            if success:
                info("Recorded path cleared", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Recorded path cleared'}
            else:
                error("Failed to clear recorded path", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to clear recorded path'}
        except Exception as e:
            error(f"Clear recorded path error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def save_path(self, path: RobotPath) -> Dict[str, Any]:
        """保存路径到存储"""
        try:
            import json
            import time

            # 确保路径目录存在
            self.paths_dir.mkdir(parents=True, exist_ok=True)

            # 生成路径ID（如果没有的话）
            if not hasattr(path, 'id') or not path.id:
                path.id = f"path_{int(time.time())}"

            # 构建路径数据
            path_data = {
                'id': path.id,
                'name': path.name,
                'created_time': path.created_time,
                'description': path.description,
                'points': []
            }

            # 转换路径点
            for i, point in enumerate(path.points):
                path_data['points'].append({
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
                })

            # 保存到文件
            path_file = self.paths_dir / f"{path.id}.json"
            with open(path_file, 'w', encoding='utf-8') as f:
                json.dump(path_data, f, indent=2, ensure_ascii=False)

            info(f"Path saved to file: {path_file}", "ROBOT_SERVICE")
            return {'success': True, 'message': f'Path saved: {path.name}', 'path_id': path.id}

        except Exception as e:
            error(f"Save path error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def load_path(self, path_id: str) -> Optional[RobotPath]:
        """从存储加载路径"""
        try:
            import json

            path_file = self.paths_dir / f"{path_id}.json"
            if not path_file.exists():
                error(f"Path file not found: {path_file}", "ROBOT_SERVICE")
                return None

            with open(path_file, 'r', encoding='utf-8') as f:
                path_data = json.load(f)

            # 重构路径对象
            points = []
            for point_data in path_data.get('points', []):
                position_data = point_data.get('position', {})
                position = RobotPosition(
                    x=position_data.get('x', 0.0),
                    y=position_data.get('y', 0.0),
                    z=position_data.get('z', 0.0),
                    rx=position_data.get('rx', 0.0),
                    ry=position_data.get('ry', 0.0),
                    rz=position_data.get('rz', 0.0),
                    timestamp=position_data.get('timestamp', 0.0)
                )

                point = PathPoint(
                    position=position,
                    speed=point_data.get('speed', 50.0),
                    delay=point_data.get('delay', 0.0),
                    action=point_data.get('action', '')
                )
                points.append(point)

            path = RobotPath(
                name=path_data.get('name', 'Unnamed Path'),
                points=points,
                created_time=path_data.get('created_time', 0.0),
                description=path_data.get('description', ''),
                id=path_data.get('id', path_id)
            )

            info(f"Path loaded from file: {path_file}", "ROBOT_SERVICE")
            return path

        except Exception as e:
            error(f"Load path error: {e}", "ROBOT_SERVICE")
            return None

    def delete_path(self, path_id: str) -> Dict[str, Any]:
        """删除路径"""
        try:
            import os

            path_file = self.paths_dir / f"{path_id}.json"
            if path_file.exists():
                os.remove(path_file)
                info(f"Path deleted: {path_file}", "ROBOT_SERVICE")
                return {'success': True, 'message': f'Path deleted: {path_id}'}
            else:
                error(f"Path file not found: {path_file}", "ROBOT_SERVICE")
                return {'success': False, 'error': f'Path file not found: {path_id}'}
        except Exception as e:
            error(f"Delete path error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def list_saved_paths(self) -> List[str]:
        """列出所有保存的路径"""
        try:

            if not self.paths_dir.exists():
                return []

            path_files = list(self.paths_dir.glob("*.json"))
            path_ids = [f.stem for f in path_files]  # 移除.json扩展名
            return sorted(path_ids)

        except Exception as e:
            error(f"List saved paths error: {e}", "ROBOT_SERVICE")
            return []

    def play_path(self, path: RobotPath, loop_count: int = 1) -> Dict[str, Any]:
        """播放路径"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.play_path(path, loop_count)
            if success:
                info(f"Path playback started: {path.name}, loops: {loop_count}", "ROBOT_SERVICE")
                return {'success': True, 'message': f'Path playback started: {path.name}'}
            else:
                error("Failed to start path playback", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start path playback'}
        except Exception as e:
            error(f"Play path error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def stop_path_playback(self) -> Dict[str, Any]:
        """停止路径播放"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.stop_path_playback()
            if success:
                info("Path playback stopped", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Path playback stopped'}
            else:
                error("Failed to stop path playback", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to stop path playback'}
        except Exception as e:
            error(f"Stop path playback error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def is_path_playing(self) -> bool:
        """检查是否正在播放路径"""
        if not self.robot:
            return False

        try:
            return self.robot.is_path_playing()
        except Exception as e:
            error(f"Check path playing status error: {e}", "ROBOT_SERVICE")
            return False

    # ========== 高级控制功能 ==========
    def move_linear(self, start_pos: RobotPosition, end_pos: RobotPosition, speed: float) -> Dict[str, Any]:
        """线性移动"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.move_linear(start_pos, end_pos, speed)
            if success:
                info(f"Linear move started from {start_pos} to {end_pos}", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Linear move started'}
            else:
                error("Failed to start linear move", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start linear move'}
        except Exception as e:
            error(f"Linear move error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def move_circular(self, center: RobotPosition, radius: float, angle: float, speed: float) -> Dict[str, Any]:
        """圆弧移动"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.move_circular(center, radius, angle, speed)
            if success:
                info(f"Circular move started: center={center}, radius={radius}, angle={angle}", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Circular move started'}
            else:
                error("Failed to start circular move", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to start circular move'}
        except Exception as e:
            error(f"Circular move error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> Dict[str, Any]:
        """设置工件坐标系"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.set_work_coordinate_system(wcs)
            if success:
                info(f"Work coordinate system set: {wcs}", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Work coordinate system set'}
            else:
                error("Failed to set work coordinate system", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to set work coordinate system'}
        except Exception as e:
            error(f"Set work coordinate system error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    def get_work_coordinate_system(self) -> Optional[Dict[str, Any]]:
        """获取工件坐标系"""
        if not self.robot:
            return None

        try:
            return self.robot.get_work_coordinate_system()
        except Exception as e:
            error(f"Get work coordinate system error: {e}", "ROBOT_SERVICE")
            return None

    def toggle_work_coordinate_system(self) -> Dict[str, Any]:
        """切换工件坐标系"""
        if not self.robot:
            return {'success': False, 'error': 'No robot instance available'}

        try:
            success = self.robot.toggle_work_coordinate_system()
            if success:
                info("Work coordinate system toggled", "ROBOT_SERVICE")
                return {'success': True, 'message': 'Work coordinate system toggled'}
            else:
                error("Failed to toggle work coordinate system", "ROBOT_SERVICE")
                return {'success': False, 'error': 'Failed to toggle work coordinate system'}
        except Exception as e:
            error(f"Toggle work coordinate system error: {e}", "ROBOT_SERVICE")
            return {'success': False, 'error': str(e)}

    # ========== 信号和回调相关 ==========
    def register_position_callback(self, callback) -> bool:
        """注册位置变化回调函数"""
        if not self.robot:
            return False

        try:
            return self.robot.register_position_callback(callback)
        except Exception as e:
            error(f"Register position callback error: {e}", "ROBOT_SERVICE")
            return False

    def register_state_callback(self, callback) -> bool:
        """注册状态变化回调函数"""
        if not self.robot:
            return False

        try:
            return self.robot.register_state_callback(callback)
        except Exception as e:
            error(f"Register state callback error: {e}", "ROBOT_SERVICE")
            return False

    def unregister_position_callback(self, callback) -> bool:
        """取消注册位置变化回调函数"""
        if not self.robot:
            return False

        try:
            return self.robot.unregister_position_callback(callback)
        except Exception as e:
            error(f"Unregister position callback error: {e}", "ROBOT_SERVICE")
            return False

    def unregister_state_callback(self, callback) -> bool:
        """取消注册状态变化回调函数"""
        if not self.robot:
            return False

        try:
            return self.robot.unregister_state_callback(callback)
        except Exception as e:
            error(f"Unregister state callback error: {e}", "ROBOT_SERVICE")
            return False