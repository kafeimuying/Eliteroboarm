"""
机器人抽象接口
定义机器人设备的抽象基类
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class RobotState(Enum):
    """机器人状态枚举"""
    IDLE = "idle"
    MOVING = "moving"
    JOGGING = "jogging"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"


class MotionMode(Enum):
    """运动模式枚举"""
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    JOG = "jog"


@dataclass
class RobotPosition:
    """机器人位置数据结构"""
    x: float
    y: float
    z: float
    rx: float = 0.0
    ry: float = 0.0
    rz: float = 0.0
    timestamp: float = 0.0


@dataclass
class PathPoint:
    """路径点数据结构"""
    position: RobotPosition
    speed: float = 50.0
    delay: float = 0.0
    action: str = ""  # 可选的动作描述


@dataclass
class RobotPath:
    """机器人路径数据结构"""
    name: str
    points: List[PathPoint]
    created_time: float
    description: str = ""
    id: str = ""


class IRobot(ABC):
    """机器人设备抽象接口"""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> bool:
        """连接机器人"""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """断开连接"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        pass

    @abstractmethod
    def move_to(self, x: float, y: float, z: float,
                rx: float = 0, ry: float = 0, rz: float = 0) -> bool:
        """移动到指定位置"""
        pass

    @abstractmethod
    def get_position(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """获取当前位置"""
        pass

    @abstractmethod
    def home(self) -> bool:
        """回到原点"""
        pass

    @abstractmethod
    def emergency_stop(self) -> bool:
        """紧急停止"""
        pass

    @abstractmethod
    def set_speed(self, speed: float) -> bool:
        """设置速度 (0-100%)"""
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        pass

    # ========== 实时控制相关方法 ==========
    @abstractmethod
    def start_jogging(self, axis: str) -> bool:
        """开始点动运动"""
        pass

    @abstractmethod
    def stop_jogging(self) -> bool:
        """停止点动运动"""
        pass

    @abstractmethod
    def jog_move(self, axis: str, speed: float, distance: float) -> bool:
        """点动移动指定轴"""
        pass

    @abstractmethod
    def set_motion_mode(self, mode: MotionMode) -> bool:
        """设置运动模式"""
        pass

    @abstractmethod
    def get_motion_mode(self) -> Optional[MotionMode]:
        """获取当前运动模式"""
        pass

    @abstractmethod
    def get_state(self) -> RobotState:
        """获取机器人当前状态"""
        pass

    @abstractmethod
    def is_moving(self) -> bool:
        """检查是否正在运动"""
        pass

    # ========== 路径记录相关方法 ==========
    @abstractmethod
    def start_path_recording(self, path_name: str) -> bool:
        """开始记录路径"""
        pass

    @abstractmethod
    def stop_path_recording(self) -> bool:
        """停止记录路径"""
        pass

    @abstractmethod
    def add_path_point(self, point: Optional[PathPoint] = None) -> bool:
        """添加路径点"""
        pass

    @abstractmethod
    def get_recorded_path(self) -> Optional[RobotPath]:
        """获取当前记录的路径"""
        pass

    @abstractmethod
    def clear_recorded_path(self) -> bool:
        """清空当前记录的路径"""
        pass

    # 路径存储相关方法已移至Service层
    # Robot层只处理机器人行为，不涉及文件存储

    @abstractmethod
    def play_path(self, path: RobotPath, loop_count: int = 1) -> bool:
        """播放路径"""
        pass

    @abstractmethod
    def stop_path_playback(self) -> bool:
        """停止路径播放"""
        pass

    @abstractmethod
    def is_path_playing(self) -> bool:
        """检查是否正在播放路径"""
        pass

    # ========== 高级控制功能 ==========
    @abstractmethod
    def move_linear(self, start_pos: RobotPosition, end_pos: RobotPosition, speed: float) -> bool:
        """线性移动"""
        pass

    @abstractmethod
    def move_circular(self, center: RobotPosition, radius: float, angle: float, speed: float) -> bool:
        """圆弧移动"""
        pass

    @abstractmethod
    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> bool:
        """设置工件坐标系"""
        pass

    @abstractmethod
    def get_work_coordinate_system(self) -> Optional[Dict[str, Any]]:
        """获取工件坐标系"""
        pass

    @abstractmethod
    def toggle_work_coordinate_system(self) -> bool:
        """切换工件坐标系"""
        pass

    # ========== 信号和回调相关 ==========
    def register_position_callback(self, callback) -> bool:
        """注册位置变化回调函数"""
        pass

    def register_state_callback(self, callback) -> bool:
        """注册状态变化回调函数"""
        pass

    def unregister_position_callback(self, callback) -> bool:
        """取消注册位置变化回调函数"""
        pass

    def unregister_state_callback(self, callback) -> bool:
        """取消注册状态变化回调函数"""
        pass

    def register_log_callback(self, callback) -> bool:
        """注册日志回调函数 callback(level: str, message: str)"""
        pass

    def unregister_log_callback(self, callback) -> bool:
        """取消注册日志回调函数"""
        pass

    # ========== 标定相关方法 ==========
    def set_capture_callback(self, callback) -> bool:
        """设置自动拍照回调函数 callback(point_index)"""
        pass

    def confirm_calibration(self) -> Dict[str, Any]:
        """确认标定步骤 (用于交互式标定流程)"""
        pass
