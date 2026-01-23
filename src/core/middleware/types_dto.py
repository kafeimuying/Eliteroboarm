"""
数据传输对象（Data Transfer Objects）
定义系统内各个组件之间传输数据的标准化格式
使用强类型对象替代字典，提供IDE智能提示和类型安全
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


# ==================== 硬件事件类型枚举 ====================

class HardwareEventType(Enum):
    """硬件事件类型枚举 - 避免魔法字符串"""
    # 相机事件
    CAMERA_CONNECTED = "camera_connected"
    CAMERA_DISCONNECTED = "camera_disconnected"
    CAMERA_FRAME_CAPTURED = "camera_frame_capture"

    # 机械臂事件
    ROBOT_CONNECTED = "robot_connected"
    ROBOT_POSITION_CHANGED = "robot_position_changed"

    # 通用错误事件
    HARDWARE_ERROR = "hardware_error"


# ==================== 相机相关DTO ====================

@dataclass
class CameraConnectionInfo:
    """相机连接信息DTO"""
    camera_id: str
    name: str
    camera_type: str
    config: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.config:
            self.config = {}


@dataclass
class CameraFrameInfo:
    """相机帧信息DTO"""
    camera_id: str
    name: str
    frame_count: int
    width: int
    height: int
    channels: int
    timestamp: float
    is_simulation: bool = False
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


# ==================== 机械臂相关DTO ====================

@dataclass
class RobotConnectionInfo:
    """机械臂连接信息DTO"""
    robot_id: str
    name: str
    robot_type: str
    config: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.config:
            self.config = {}


@dataclass
class RobotPositionInfo:
    """机械臂位置信息DTO"""
    robot_id: str
    position: List[float]  # 6轴关节角度 [J1, J2, J3, J4, J5, J6]
    movement_type: str = "unknown"  # jog, position, home, emergency_stop
    speed: float = 100.0
    axis: Optional[str] = None  # 用于点动移动
    direction: Optional[int] = None  # 用于点动移动 +1/-1
    distance: Optional[float] = None  # 用于点动移动
    target_position: Optional[List[float]] = None  # 目标位置
    timestamp: float = field(default_factory=time.time)


# ==================== 通用硬件事件DTO ====================

@dataclass
class HardwareErrorInfo:
    """硬件错误信息DTO"""
    hardware_type: str  # camera, robot, light
    device_id: str
    error: str
    operation: str  # connect, disconnect, move, capture, etc.
    error_code: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


# ==================== 核心事件DTO ====================

@dataclass
class HardwareEvent:
    """标准硬件事件DTO - 统一所有硬件事件的入口"""
    event_type: HardwareEventType
    source: str  # 事件源组件名
    timestamp: float = field(default_factory=time.time)
    message: str = ""

    # 载荷数据 - 根据事件类型携带具体的数据对象
    camera_connection: Optional[CameraConnectionInfo] = None
    camera_frame: Optional[CameraFrameInfo] = None
    robot_connection: Optional[RobotConnectionInfo] = None
    robot_position: Optional[RobotPositionInfo] = None
    hardware_error: Optional[HardwareErrorInfo] = None

    def is_camera_event(self) -> bool:
        """判断是否为相机相关事件"""
        return self.event_type in [
            HardwareEventType.CAMERA_CONNECTED,
            HardwareEventType.CAMERA_DISCONNECTED,
            HardwareEventType.CAMERA_FRAME_CAPTURED
        ]

    def is_robot_event(self) -> bool:
        """判断是否为机械臂相关事件"""
        return self.event_type in [
            HardwareEventType.ROBOT_CONNECTED,
            HardwareEventType.ROBOT_POSITION_CHANGED
        ]

    def is_error_event(self) -> bool:
        """判断是否为错误事件"""
        return self.event_type in [
            HardwareEventType.HARDWARE_ERROR
        ]


# ==================== 工厂函数 ====================

def create_camera_connected_event(source: str, camera_connection: CameraConnectionInfo) -> HardwareEvent:
    """创建相机连接事件"""
    return HardwareEvent(
        event_type=HardwareEventType.CAMERA_CONNECTED,
        source=source,
        message=f"相机 {camera_connection.name} 已连接",
        camera_connection=camera_connection
    )


def create_camera_disconnected_event(source: str, camera_connection: CameraConnectionInfo) -> HardwareEvent:
    """创建相机断开事件"""
    return HardwareEvent(
        event_type=HardwareEventType.CAMERA_DISCONNECTED,
        source=source,
        message=f"相机 {camera_connection.name} 已断开",
        camera_connection=camera_connection
    )


def create_camera_frame_event(source: str, frame_info: CameraFrameInfo) -> HardwareEvent:
    """创建相机帧捕获事件"""
    return HardwareEvent(
        event_type=HardwareEventType.CAMERA_FRAME_CAPTURED,
        source=source,
        message=f"相机 {frame_info.name} 捕获帧 #{frame_info.frame_count}",
        camera_frame=frame_info
    )


def create_robot_connected_event(source: str, robot_connection: RobotConnectionInfo) -> HardwareEvent:
    """创建机械臂连接事件"""
    return HardwareEvent(
        event_type=HardwareEventType.ROBOT_CONNECTED,
        source=source,
        message=f"机械臂 {robot_connection.name} 已连接",
        robot_connection=robot_connection
    )


def create_robot_position_event(source: str, position_info: RobotPositionInfo) -> HardwareEvent:
    """创建机械臂位置变化事件"""
    return HardwareEvent(
        event_type=HardwareEventType.ROBOT_POSITION_CHANGED,
        source=source,
        message=f"机械臂 {position_info.robot_id} 位置更新",
        robot_position=position_info
    )


def create_hardware_error_event(source: str, error_info: HardwareErrorInfo) -> HardwareEvent:
    """创建硬件错误事件"""
    return HardwareEvent(
        event_type=HardwareEventType.HARDWARE_ERROR,
        source=source,
        message=f"硬件错误: {error_info.error}",
        hardware_error=error_info
    )


# ==================== 兼容性DTO类（为core_engine_service等使用） ====================

class DeviceType(Enum):
    """设备类型枚举"""
    CAMERA = "camera"
    ROBOT = "robot"
    LIGHT = "light"


class ConnectionStatus(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    """设备基础信息"""
    device_id: str
    name: str
    device_type: DeviceType
    brand: str
    model: str
    firmware_version: Optional[str] = None
    serial_number: Optional[str] = None


@dataclass
class FrameData:
    """图像帧数据"""
    camera_id: str
    frame_id: str
    width: int
    height: int
    channels: int
    data: bytes  # 原始图像数据
    timestamp: float
    format: str = "rgb24"
    quality: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AlgorithmResult:
    """算法结果"""
    algorithm_id: str
    algorithm_type: str
    status: str  # started, completed, error
    confidence: float = 0.0
    data: Optional[Any] = None
    processing_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class VisionResult:
    """视觉算法结果"""
    algorithm_id: str
    frame_id: str
    detections: List[Dict[str, Any]] = field(default_factory=list)
    classifications: List[Dict[str, Any]] = field(default_factory=list)
    keypoints: List[Dict[str, Any]] = field(default_factory=list)
    segmentation_mask: Optional[bytes] = None
    confidence: float = 0.0
    processing_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class PerformanceMetric:
    """性能指标"""
    metric_name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    device_id: Optional[str] = None
    category: str = "system"  # system, hardware, algorithm


@dataclass
class ErrorReport:
    """错误报告"""
    error_type: str
    message: str
    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_id: Optional[str] = None
    component: str = "unknown"
    stack_trace: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    severity: str = "error"  # warning, error, critical
    resolved: bool = False


@dataclass
class RobotInfo:
    """机械臂信息"""
    device_id: str
    name: str
    position: List[float]  # 6轴关节角度
    cartesian_position: Optional[List[float]] = None  # 笛卡尔坐标
    is_connected: bool = False
    is_moving: bool = False
    speed: float = 100.0
    acceleration: float = 100.0


@dataclass
class CameraInfo:
    """相机信息"""
    device_id: str
    name: str
    resolution: str
    fps: int
    is_preview_active: bool = False
    frame_count: int = 0
    last_frame_time: Optional[float] = None
    supports_capture: bool = True
    capture_path: Optional[str] = None


@dataclass
class LightChannelInfo:
    """光源通道信息"""
    device_id: str
    channel_id: int
    name: str
    current_brightness: int
    max_brightness: int = 255
    is_enabled: bool = True
    min_brightness: int = 0
    response_time_ms: float = 50.0


@dataclass
class ConnectionInfo:
    """连接信息"""
    device_id: str
    status: ConnectionStatus
    connection_type: str
    last_connected: Optional[float] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class UserAction:
    """用户操作记录"""
    action_type: str
    component: str
    parameters: Dict[str, Any]
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    session_id: str = "unknown"
    user_id: Optional[str] = None
    success: bool = True


@dataclass
class SystemStatus:
    """系统状态"""
    application_ready: bool
    total_devices: int
    connected_devices: int
    error_count: int
    last_update: float = field(default_factory=time.time)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0