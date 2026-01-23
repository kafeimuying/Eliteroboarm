from ..algorithm.robot_data_types import RobotPose
import numpy as np
import time
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum


class SystemState(Enum):
    """系统状态枚举"""
    INITIALIZING = "initializing"
    IDLE = "idle"
    CALIBRATING = "calibrating"
    VISION_PROCESSING = "vision_processing"
    ROBOT_MOVING = "robot_moving"
    COLLABORATIVE_WORKING = "collaborative_working"
    ERROR = "error"
    EMERGENCY_STOP = "emergency_stop"
    MAINTENANCE = "maintenance"
    SHUTTING_DOWN = "shutting_down"

    @classmethod
    def get_operational_states(cls) -> List['SystemState']:
        """获取可操作状态列表"""
        return [cls.IDLE, cls.CALIBRATING, cls.VISION_PROCESSING,
                cls.ROBOT_MOVING, cls.COLLABORATIVE_WORKING]

    @classmethod
    def get_safe_states(cls) -> List['SystemState']:
        """获取安全状态列表"""
        return [cls.IDLE, cls.ERROR, cls.EMERGENCY_STOP, cls.MAINTENANCE]

    def is_operational(self) -> bool:
        """检查是否为可操作状态"""
        return self in self.get_operational_states()

    def copy(self) -> 'RobotPose':
        """创建RobotPose副本"""
        pose_copy = RobotPose.from_matrix(
            self.to_matrix(),
            self.frame_id
        )
        pose_copy.timestamp = self.timestamp
        pose_copy.confidence = self.confidence
        pose_copy.covariance = self.covariance.copy() if self.covariance is not None else None
        return pose_copy

    def is_safe(self) -> bool:
        """检查是否为安全状态"""
        return self in self.get_safe_states()
    

@dataclass
class SystemStatus:
    """系统状态"""
    state: SystemState
    vision_ready: bool
    robot_ready: bool
    calibration_valid: bool
    safety_status: str
    current_task: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    sub_systems_status: Dict[str, bool] = field(default_factory=dict)
    performance_metrics: Dict[str, float] = field(default_factory=dict)

    def is_system_ready(self) -> bool:
        """检查系统是否就绪"""
        return (self.state == SystemState.IDLE and
                self.vision_ready and
                self.robot_ready and
                self.calibration_valid and
                self.safety_status == "SAFE")

    def get_health_score(self) -> float:
        """获取系统健康分数 (0-1)"""
        score = 0.0

        # 基础分数
        if self.vision_ready:
            score += 0.3
        if self.robot_ready:
            score += 0.3
        if self.calibration_valid:
            score += 0.2
        if self.safety_status == "SAFE":
            score += 0.2

        # 错误扣分
        if self.state == SystemState.ERROR:
            score *= 0.5
        elif self.state == SystemState.EMERGENCY_STOP:
            score = 0.0

        return score
    

@dataclass
class SystemMessage:
    """系统消息"""
    topic: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    priority: int = 0
    source: str = ""
    message_id: str = ""
    correlation_id: Optional[str] = None  # 用于消息关联
    expires_at: Optional[float] = None    # 消息过期时间
    retry_count: int = 0                  # 重试次数
    max_retries: int = 3                  # 最大重试次数

    def __post_init__(self):
        """生成消息ID"""
        if not self.message_id:
            import uuid
            self.message_id = str(uuid.uuid4())

    def __lt__(self, other):
        """支持优先级队列比较（用于负优先级实现最大堆）"""
        if not isinstance(other, SystemMessage):
            return NotImplemented
        return self.priority > other.priority  # 优先级高的排在前面

    def is_expired(self) -> bool:
        """检查消息是否过期"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.max_retries

    def create_response(self, response_data: Any) -> 'SystemMessage':
        """创建响应消息"""
        return SystemMessage(
            topic=f"{self.topic}.response",
            data=response_data,
            source=self.source,
            correlation_id=self.message_id,
            priority=self.priority
        )