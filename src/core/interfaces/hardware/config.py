from dataclasses import dataclass, field
import numpy as np
from typing import Dict, Any, Optional, List, Tuple, Union, Callable


@dataclass
class RobotConfig:
    """机械臂配置"""
    robot_type: str
    ip_address: str
    port: int = 30002
    workspace_limits: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    joint_limits: List[Dict[str, Tuple[float, float]]] = field(default_factory=list)
    max_velocity: float = 1.0
    max_acceleration: float = 2.0
    safety_radius: float = 0.1
    tool_offset: Optional[np.ndarray] = None
    reference_frame: str = "robot_base"
    connection_timeout: float = 10.0
    heartbeat_interval: float = 1.0

    def __post_init__(self):
        """设置默认工作空间限制"""
        if not self.workspace_limits:
            self.workspace_limits = {
                'x': (-0.8, 0.8),
                'y': (-0.8, 0.8),
                'z': (0.0, 1.2)
            }

    def is_position_in_workspace(self, position: np.ndarray) -> bool:
        """检查位置是否在工作空间内"""
        if len(position) >= 3:
            x, y, z = position[:3]
            return (self.workspace_limits['x'][0] <= x <= self.workspace_limits['x'][1] and
                    self.workspace_limits['y'][0] <= y <= self.workspace_limits['y'][1] and
                    self.workspace_limits['z'][0] <= z <= self.workspace_limits['z'][1])
        return False
    

@dataclass
class VisionConfig:
    """视觉系统配置"""
    camera_type: str
    camera_id: str
    resolution: Tuple[int, int] = (1920, 1080)
    frame_rate: float = 30.0
    exposure_time: Optional[float] = None
    gain: Optional[float] = None
    intrinsic_matrix: Optional[np.ndarray] = None
    distortion_coeffs: Optional[np.ndarray] = None
    auto_exposure: bool = True
    auto_gain: bool = True
    trigger_mode: str = "continuous"  # "continuous", "software", "hardware"

    def __post_init__(self):
        """设置默认相机内参"""
        if self.intrinsic_matrix is None:
            # 假设6mm镜头，1/2.3"传感器
            fx, fy = self.resolution[0] * 0.8, self.resolution[1] * 0.8
            cx, cy = self.resolution[0] / 2, self.resolution[1] / 2
            self.intrinsic_matrix = np.array([
                [fx, 0, cx],
                [0, fy, cy],
                [0, 0, 1]
            ], dtype=float)

        if self.distortion_coeffs is None:
            self.distortion_coeffs = np.zeros(5, dtype=float)