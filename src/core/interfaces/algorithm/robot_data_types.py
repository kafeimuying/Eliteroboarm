from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import time


class RobotStatus(Enum):
    """机器人状态枚举"""
    DISCONNECTED = "未连接"
    CONNECTED = "已连接"
    RUNNING = "运行中"
    ERROR = "错误"
    EMERGENCY_STOP = "急停"


@dataclass
class RobotPose:
    """机械臂位姿"""
    position: np.ndarray        # [x, y, z] 位置坐标 (米)
    orientation: np.ndarray     # [qw, qx, qy, qz] 四元数 或 [r, p, y] 欧拉角
    timestamp: float = field(default_factory=time.time)
    frame_id: str = "robot_base"
    confidence: float = 1.0
    covariance: Optional[np.ndarray] = None  # 3x3 协方差矩阵

    def __post_init__(self):
        """数据验证"""
        if not isinstance(self.position, np.ndarray):
            self.position = np.array(self.position, dtype=float)
        if not isinstance(self.orientation, np.ndarray):
            self.orientation = np.array(self.orientation, dtype=float)

    def copy(self):
        """复制位姿"""
        return RobotPose(
            position=self.position.copy(),
            orientation=self.orientation.copy(),
            timestamp=self.timestamp,
            frame_id=self.frame_id,
            confidence=self.confidence,
            covariance=self.covariance.copy() if self.covariance is not None else None
        )

        assert self.position.shape == (3,), f"position shape must be (3,), got {self.position.shape}"
        assert self.orientation.shape in [(3,), (4,)], f"orientation shape must be (3,) or (4,), got {self.orientation.shape}"

    def to_matrix(self) -> np.ndarray:
        """转换为4x4齐次变换矩阵"""
        matrix = np.eye(4)
        matrix[:3, 3] = self.position

        # 四元数转旋转矩阵
        if len(self.orientation) == 4:
            q = self.orientation  # [w, x, y, z]
            w, x, y, z = q
            matrix[0, 0] = 1 - 2*(y*y + z*z)
            matrix[0, 1] = 2*(x*y - z*w)
            matrix[0, 2] = 2*(x*z + y*w)
            matrix[1, 0] = 2*(x*y + z*w)
            matrix[1, 1] = 1 - 2*(x*x + z*z)
            matrix[1, 2] = 2*(y*z - x*w)
            matrix[2, 0] = 2*(x*z - y*w)
            matrix[2, 1] = 2*(y*z + x*w)
            matrix[2, 2] = 1 - 2*(x*x + y*y)
        else:
            # 欧拉角转旋转矩阵 (roll, pitch, yaw)
            r, p, y = self.orientation
            matrix[0, 0] = np.cos(y)*np.cos(p)
            matrix[0, 1] = np.cos(y)*np.sin(p)*np.sin(r) - np.sin(y)*np.cos(r)
            matrix[0, 2] = np.cos(y)*np.sin(p)*np.cos(r) + np.sin(y)*np.sin(r)
            matrix[1, 0] = np.sin(y)*np.cos(p)
            matrix[1, 1] = np.sin(y)*np.sin(p)*np.sin(r) + np.cos(y)*np.cos(r)
            matrix[1, 2] = np.sin(y)*np.sin(p)*np.cos(r) - np.cos(y)*np.sin(r)
            matrix[2, 0] = -np.sin(p)
            matrix[2, 1] = np.cos(p)*np.sin(r)
            matrix[2, 2] = np.cos(p)*np.cos(r)

        return matrix

    @staticmethod
    def from_matrix(matrix: np.ndarray, frame_id: str = "robot_base") -> 'RobotPose':
        """从4x4齐次变换矩阵创建RobotPose"""
        assert matrix.shape == (4, 4), f"Matrix shape must be (4, 4), got {matrix.shape}"

        position = matrix[:3, 3]

        # 旋转矩阵转四元数
        R = matrix[:3, :3]
        trace = np.trace(R)

        if trace > 0:
            s = 0.5 / np.sqrt(trace + 1.0)
            w = 0.25 / s
            x = (R[2, 1] - R[1, 2]) * s
            y = (R[0, 2] - R[2, 0]) * s
            z = (R[1, 0] - R[0, 1]) * s
        else:
            if R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
                s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
                w = (R[2, 1] - R[1, 2]) / s
                x = 0.25 * s
                y = (R[0, 1] + R[1, 0]) / s
                z = (R[0, 2] + R[2, 0]) / s
            elif R[1, 1] > R[2, 2]:
                s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
                w = (R[0, 2] - R[2, 0]) / s
                x = (R[0, 1] + R[1, 0]) / s
                y = 0.25 * s
                z = (R[1, 2] + R[2, 1]) / s
            else:
                s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
                w = (R[1, 0] - R[0, 1]) / s
                x = (R[0, 2] + R[2, 0]) / s
                y = (R[1, 2] + R[2, 1]) / s
                z = 0.25 * s

        orientation = np.array([w, x, y, z])

        return RobotPose(
            position=position.copy() if hasattr(position, 'copy') else np.array(position),
            orientation=orientation.copy() if hasattr(orientation, 'copy') else np.array(orientation),
            frame_id=frame_id,
            timestamp=self.timestamp,
            confidence=self.confidence,
            covariance=self.covariance.copy() if self.covariance is not None else None
        )

@dataclass
class RobotJointAngles:
    """机械臂关节角度"""
    angles: List[float]         # 关节角度（弧度）
    timestamp: float = field(default_factory=time.time)
    joint_names: Optional[List[str]] = None
    frame_id: str = "robot_base"
    velocities: Optional[List[float]] = None
    accelerations: Optional[List[float]] = None

    def __post_init__(self):
        """数据验证"""
        if not isinstance(self.angles, list):
            self.angles = list(self.angles)

        # 验证角度范围（-π 到 π）
        for i, angle in enumerate(self.angles):
            if not -np.pi <= angle <= np.pi:
                # 角度标准化到 [-π, π]
                self.angles[i] = ((angle + np.pi) % (2 * np.pi)) - np.pi

    def to_dict(self) -> Dict[str, float]:
        """转换为字典"""
        result = {}
        if self.joint_names:
            for name, angle in zip(self.joint_names, self.angles):
                result[name] = angle
        else:
            for i, angle in enumerate(self.angles):
                result[f"joint_{i}"] = angle
        return result

@dataclass
class RobotTrajectory:
    """机械臂轨迹"""
    waypoints: List[RobotPose]
    timestamps: List[float]
    velocities: Optional[List[float]] = None
    accelerations: Optional[List[float]] = None
    joint_trajectory: Optional[List[RobotJointAngles]] = None
    trajectory_type: str = "joint"  # "joint" or "cartesian"
    interpolation_type: str = "linear"  # "linear", "cubic", "quintic"

    def __post_init__(self):
        """数据验证"""
        assert len(self.waypoints) == len(self.timestamps), "waypoints and timestamps must have same length"

        if self.velocities is not None:
            assert len(self.velocities) == len(self.waypoints), "velocities must match waypoints length"

        if self.accelerations is not None:
            assert len(self.accelerations) == len(self.waypoints), "accelerations must match waypoints length"

    def get_duration(self) -> float:
        """获取轨迹总时长"""
        if len(self.timestamps) < 2:
            return 0.0
        return self.timestamps[-1] - self.timestamps[0]
    

@dataclass
class CoordinateTransform:
    """坐标变换"""
    matrix: np.ndarray           # 4x4 齐次变换矩阵
    source_frame: str           # 源坐标系名称
    target_frame: str           # 目标坐标系名称
    timestamp: float = field(default_factory=time.time)
    valid: bool = True
    confidence: float = 1.0
    transform_type: str = "static"  # "static" or "dynamic"

    def __post_init__(self):
        """数据验证"""
        if not isinstance(self.matrix, np.ndarray):
            self.matrix = np.array(self.matrix, dtype=float)

        assert self.matrix.shape == (4, 4), f"Transform matrix must be 4x4, got {self.matrix.shape}"

        # 验证变换矩阵的有效性
        assert np.allclose(self.matrix[3, :], [0, 0, 0, 1]), "Invalid homogeneous transform matrix"

    def transform_point(self, point: np.ndarray) -> np.ndarray:
        """变换3D点"""
        if not isinstance(point, np.ndarray):
            point = np.array(point, dtype=float)

        assert point.shape == (3,), f"Point must be 3D, got shape {point.shape}"

        # 转换为齐次坐标
        homogeneous_point = np.append(point, 1)

        # 应用变换
        transformed = self.matrix @ homogeneous_point

        return transformed[:3]

    def transform_pose(self, pose: RobotPose) -> RobotPose:
        """变换位姿"""
        # 转换为矩阵
        pose_matrix = pose.to_matrix()

        # 应用变换
        transformed_matrix = self.matrix @ pose_matrix

        # 转换回RobotPose
        return RobotPose.from_matrix(transformed_matrix, self.target_frame)

    def inverse(self) -> 'CoordinateTransform':
        """获取逆变换"""
        inv_matrix = np.linalg.inv(self.matrix)
        return CoordinateTransform(
            matrix=inv_matrix,
            source_frame=self.target_frame,
            target_frame=self.source_frame,
            timestamp=self.timestamp,
            valid=self.valid,
            confidence=self.confidence,
            transform_type=self.transform_type
        )
    
# ================== 工具函数 ==================

def create_identity_transform(frame_id: str = "world") -> CoordinateTransform:
    """创建单位变换"""
    return CoordinateTransform(
        matrix=np.eye(4),
        source_frame=frame_id,
        target_frame=frame_id
    )

def create_translation_transform(translation: np.ndarray,
                                source_frame: str = "world",
                                target_frame: str = "new_frame") -> CoordinateTransform:
    """创建平移变换"""
    matrix = np.eye(4)
    matrix[:3, 3] = translation
    return CoordinateTransform(
        matrix=matrix,
        source_frame=source_frame,
        target_frame=target_frame
    )

def create_rotation_from_euler(roll: float, pitch: float, yaw: float,
                               source_frame: str = "world",
                               target_frame: str = "rotated_frame") -> CoordinateTransform:
    """创建欧拉角旋转变换"""
    # Roll (X-axis)
    Rx = np.array([
        [1, 0, 0, 0],
        [0, np.cos(roll), -np.sin(roll), 0],
        [0, np.sin(roll), np.cos(roll), 0],
        [0, 0, 0, 1]
    ])

    # Pitch (Y-axis)
    Ry = np.array([
        [np.cos(pitch), 0, np.sin(pitch), 0],
        [0, 1, 0, 0],
        [-np.sin(pitch), 0, np.cos(pitch), 0],
        [0, 0, 0, 1]
    ])

    # Yaw (Z-axis)
    Rz = np.array([
        [np.cos(yaw), -np.sin(yaw), 0, 0],
        [np.sin(yaw), np.cos(yaw), 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1]
    ])

    # 组合旋转 (ZYX顺序)
    matrix = Rz @ Ry @ Rx

    return CoordinateTransform(
        matrix=matrix,
        source_frame=source_frame,
        target_frame=target_frame
    )