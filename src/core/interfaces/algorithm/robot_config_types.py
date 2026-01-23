#!/usr/bin/env python3
"""
机械臂配置类型系统
专门用于机械臂算法配置，包括标定、转换、引导等算法
"""

from typing import Dict, Any, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import numpy as np

from .base import ParameterType
from ..interfaces.algorithm.robot_data_types import RobotPose, CoordinateTransform, RobotJointAngles, RobotTrajectory


class RobotAlgorithmCategory(Enum):
    """机械臂算法分类"""
    CALIBRATION = "标定"
    TRANSFORM = "转换"
    GUIDANCE = "引导"
    KINEMATICS = "运动学"
    PLANNING = "路径规划"
    CONTROL = "控制"
    SAFETY = "安全"
    EXECUTION = "执行"


class RobotAlgorithmSubCategory(Enum):
    """机械臂算法子分类"""
    # 标定子类
    HAND_EYE_CALIBRATION = "手眼标定"
    BASE_CALIBRATION = "基座标定"
    TOOL_CALIBRATION = "工具标定"
    ACCURACY_CALIBRATION = "精度标定"

    # 转换子类
    COORDINATE_TRANSFORM = "坐标转换"
    VISION_TO_ROBOT = "视觉到机器人"
    ROBOT_TO_VISION = "机器人到视觉"
    WORLD_TO_ROBOT = "世界到机器人"

    # 引导子类
    VISUAL_GUIDANCE = "视觉引导"
    FORCE_GUIDANCE = "力引导"
    TELESCOPIC_GUIDANCE = "伸缩引导"
    PRECISION_GUIDANCE = "精度引导"

    # 运动学子类
    FORWARD_KINEMATICS = "正向运动学"
    INVERSE_KINEMATICS = "逆向运动学"
    JACOBIAN_ANALYSIS = "雅可比分析"
    SINGULARITY_AVOIDANCE = "奇点规避"

    # 路径规划子类
    CARTESIAN_PLANNING = "笛卡尔规划"
    JOINT_PLANNING = "关节规划"
    TRAJECTORY_OPTIMIZATION = "轨迹优化"
    COLLISION_AVOIDANCE = "碰撞避免"

    # 控制子类
    POSITION_CONTROL = "位置控制"
    FORCE_CONTROL = "力控制"
    IMPEDANCE_CONTROL = "阻抗控制"
    ADAPTIVE_CONTROL = "自适应控制"

    # 安全子类
    COLLISION_DETECTION = "碰撞检测"
    WORKSPACE_LIMITS = "工作空间限制"
    SPEED_LIMITS = "速度限制"
    EMERGENCY_STOP = "急停"

    # 执行子类
    TRAJECTORY_EXECUTION = "轨迹执行"
    PICK_AND_PLACE = "抓取放置"
    ASSEMBLY = "装配"
    WELDING = "焊接"


@dataclass
class RobotParameterConfig:
    """机械臂参数配置定义"""
    name: str                                    # 参数名称
    param_type: ParameterType                   # 参数类型
    value: Any                                  # 参数值
    description: str = ""                       # 参数描述

    # 数值类型相关
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    step: Optional[Union[int, float]] = None

    # 选择类型相关
    choices: Optional[List[str]] = None

    # 通用属性
    required: bool = True

    # 机械臂特定属性
    unit: Optional[str] = None                  # 单位 (mm, deg, m/s, N等)
    joint_index: Optional[int] = None           # 关节索引
    coordinate_frame: Optional[str] = None      # 坐标系
    safety_critical: bool = False               # 安全关键参数

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "name": self.name,
            "type": self.param_type.value,
            "value": self.value,
            "description": self.description,
            "required": self.required
        }

        # 根据类型添加特定字段
        if self.param_type in [ParameterType.INT, ParameterType.FLOAT, ParameterType.RANGE]:
            if self.min_value is not None:
                result["min_value"] = self.min_value
            if self.max_value is not None:
                result["max_value"] = self.max_value
            if self.step is not None:
                result["step"] = self.step

        elif self.param_type == ParameterType.CHOICE:
            if self.choices:
                result["choices"] = self.choices

        # 机械臂特定字段
        if self.unit:
            result["unit"] = self.unit
        if self.joint_index is not None:
            result["joint_index"] = self.joint_index
        if self.coordinate_frame:
            result["coordinate_frame"] = self.coordinate_frame
        if self.safety_critical:
            result["safety_critical"] = self.safety_critical

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RobotParameterConfig':
        """从字典创建参数配置"""
        # 解析参数类型
        param_type_str = data.get("type", "string")
        param_type = ParameterType(param_type_str)

        # 创建配置对象
        config = cls(
            name=data["name"],
            param_type=param_type,
            value=data["value"],
            description=data.get("description", ""),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            step=data.get("step"),
            choices=data.get("choices"),
            required=data.get("required", True),
            unit=data.get("unit"),
            joint_index=data.get("joint_index"),
            coordinate_frame=data.get("coordinate_frame"),
            safety_critical=data.get("safety_critical", False)
        )

        return config

    def validate_value(self, value: Any) -> bool:
        """验证参数值是否有效"""
        # 基础类型验证
        if not self._validate_basic_type(value):
            return False

        # 数值范围验证
        if self.param_type in [ParameterType.INT, ParameterType.FLOAT]:
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False

        # 选择项验证
        elif self.param_type == ParameterType.CHOICE:
            if self.choices and value not in self.choices:
                return False

        # 机械臂特定验证
        if self.safety_critical:
            # 安全关键参数需要更严格的验证
            if not self._validate_safety_critical(value):
                return False

        return True

    def _validate_basic_type(self, value: Any) -> bool:
        """基础类型验证"""
        if self.param_type == ParameterType.INT:
            return isinstance(value, int)
        elif self.param_type == ParameterType.FLOAT:
            return isinstance(value, (int, float))
        elif self.param_type == ParameterType.BOOL:
            return isinstance(value, bool)
        elif self.param_type == ParameterType.STRING:
            return isinstance(value, str)
        elif self.param_type == ParameterType.CHOICE:
            return isinstance(value, (str, int, float))
        elif self.param_type == ParameterType.RANGE:
            return isinstance(value, (list, tuple)) and len(value) == 2
        elif self.param_type == ParameterType.COLOR:
            return self._validate_color(value)
        elif self.param_type == ParameterType.FILE:
            return isinstance(value, str)
        elif self.param_type == ParameterType.ROI:
            return self._validate_roi(value)
        return True

    def _validate_color(self, value: Any) -> bool:
        """颜色格式验证"""
        if isinstance(value, str) and value.startswith('#'):
            return True
        elif isinstance(value, (list, tuple)) and len(value) in [3, 4]:
            return all(isinstance(v, int) and 0 <= v <= 255 for v in value)
        return False

    def _validate_roi(self, value: Any) -> bool:
        """ROI格式验证"""
        if isinstance(value, dict):
            required_keys = ["x", "y", "width", "height"]
            return all(key in value for key in required_keys)
        elif isinstance(value, str):
            try:
                coords = [int(x.strip()) for x in value.split(',')]
                return len(coords) == 4
            except:
                return False
        return False

    def _validate_safety_critical(self, value: Any) -> bool:
        """安全关键参数验证"""
        if self.param_type == ParameterType.FLOAT:
            # 速度限制等安全参数
            if self.max_value and abs(value) > self.max_value:
                return False
        elif self.param_type == ParameterType.INT:
            # 关节角度限制等安全参数
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
        return True


@dataclass
class RobotAlgorithmConfig:
    """机械臂算法配置定义"""
    algorithm_id: str                          # 算法ID
    display_name: str                         # 显示名称
    category: RobotAlgorithmCategory          # 分类
    sub_category: RobotAlgorithmSubCategory   # 子分类
    description: str = ""                     # 描述
    version: str = "1.0.0"                  # 版本
    author: str = ""                          # 作者

    # 参数配置列表
    parameters: List[RobotParameterConfig] = field(default_factory=list)

    # 机械臂特定配置
    robot_type: Optional[str] = None          # 适用机械臂类型
    dof: Optional[int] = None                 # 自由度
    workspace_requirements: Optional[Dict[str, Any]] = None  # 工作空间要求
    safety_level: str = "standard"            # 安全级别 (low, standard, high)

    # 布局信息（仅画布环境使用）
    layout: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "algorithm_id": self.algorithm_id,
            "display_name": self.display_name,
            "category": self.category.value,
            "sub_category": self.sub_category.value,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "parameters": [param.to_dict() for param in self.parameters],
            "safety_level": self.safety_level
        }

        # 机械臂特定字段
        if self.robot_type:
            result["robot_type"] = self.robot_type
        if self.dof is not None:
            result["dof"] = self.dof
        if self.workspace_requirements:
            result["workspace_requirements"] = self.workspace_requirements

        if self.layout:
            result["layout"] = self.layout

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RobotAlgorithmConfig':
        """从字典创建算法配置"""
        # 解析参数配置
        parameters = []
        if "parameters" in data:
            for param_data in data["parameters"]:
                param_config = RobotParameterConfig.from_dict(param_data)
                parameters.append(param_config)

        # 解析分类
        category = RobotAlgorithmCategory(data["category"])
        sub_category = RobotAlgorithmSubCategory(data["sub_category"])

        # 创建配置对象
        config = cls(
            algorithm_id=data["algorithm_id"],
            display_name=data["display_name"],
            category=category,
            sub_category=sub_category,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            parameters=parameters,
            robot_type=data.get("robot_type"),
            dof=data.get("dof"),
            workspace_requirements=data.get("workspace_requirements"),
            safety_level=data.get("safety_level", "standard"),
            layout=data.get("layout")
        )

        return config

    @classmethod
    def from_algorithm_base(cls, algorithm) -> 'RobotAlgorithmConfig':
        """从 AlgorithmBase 实例创建配置"""
        info = algorithm.get_info()
        algorithm_params = algorithm.get_parameters()
        current_values = algorithm.get_all_parameters()

        # 解析分类信息
        try:
            category = RobotAlgorithmCategory(info.category)
        except ValueError:
            category = RobotAlgorithmCategory(CONTROL)  # 默认分类

        try:
            sub_category = RobotAlgorithmSubCategory(info.secondary_category)
        except ValueError:
            sub_category = RobotAlgorithmSubCategory(POSITION_CONTROL)  # 默认子分类

        # 转换参数配置
        param_configs = []
        for param_def in algorithm_params:
            current_value = current_values.get(param_def.name, param_def.default_value)

            param_config = RobotParameterConfig(
                name=param_def.name,
                param_type=param_def.param_type,
                value=current_value,
                description=param_def.description,
                min_value=param_def.min_value,
                max_value=param_def.max_value,
                step=param_def.step,
                choices=param_def.choices,
                required=param_def.required
            )
            param_configs.append(param_config)

        return cls(
            algorithm_id=info.name,
            display_name=info.display_name,
            category=category,
            sub_category=sub_category,
            description=info.description,
            version=info.version,
            author=info.author,
            parameters=param_configs
        )

    def update_parameter(self, param_name: str, value: Any):
        """更新参数值"""
        for param_config in self.parameters:
            if param_config.name == param_name:
                param_config.value = value
                break

    def get_safety_critical_parameters(self) -> List[RobotParameterConfig]:
        """获取安全关键参数列表"""
        return [param for param in self.parameters if param.safety_critical]

    def get_parameters_by_unit(self, unit: str) -> List[RobotParameterConfig]:
        """根据单位获取参数列表"""
        return [param for param in self.parameters if param.unit == unit]

    def validate_safety_parameters(self) -> Tuple[bool, List[str]]:
        """验证安全关键参数"""
        errors = []
        for param in self.get_safety_critical_parameters():
            if not param.validate_value(param.value):
                errors.append(f"安全参数 {param.name} 值 {param.value} 无效")

        return len(errors) == 0, errors


@dataclass
class RobotChainConfig:
    """机械臂算法链配置"""
    algorithms: List[RobotAlgorithmConfig] = field(default_factory=list)
    connections: List[Dict[str, Any]] = field(default_factory=list)  # 简化连接配置

    # 元数据
    version: str = "1.0"
    created_at: Optional[str] = None
    algorithm_count: int = 0
    robot_type: Optional[str] = None          # 整体适用的机械臂类型
    safety_level: str = "standard"            # 整体安全级别
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.algorithm_count == 0:
            self.algorithm_count = len(self.algorithms)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 基本元数据
        base_metadata = {
            "version": self.version,
            "algorithm_count": self.algorithm_count,
            "safety_level": self.safety_level
        }

        if self.created_at:
            base_metadata["created_at"] = self.created_at

        if self.robot_type:
            base_metadata["robot_type"] = self.robot_type

        # 合并自定义metadata
        merged_metadata = {**base_metadata, **self.metadata}

        result = {
            "chain": [algo.to_dict() for algo in self.algorithms],
            "metadata": merged_metadata
        }

        if self.connections:
            result["connections"] = self.connections

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RobotChainConfig':
        """从字典创建链配置"""
        # 解析算法配置
        algorithms = []
        if "chain" in data:
            for algo_data in data["chain"]:
                algorithm = RobotAlgorithmConfig.from_dict(algo_data)
                algorithms.append(algorithm)

        # 解析连接配置
        connections = data.get("connections", [])

        # 解析元数据
        metadata = data.get("metadata", {})

        return cls(
            algorithms=algorithms,
            connections=connections,
            version=metadata.get("version", "1.0"),
            created_at=metadata.get("created_at"),
            algorithm_count=metadata.get("algorithm_count", len(algorithms)),
            robot_type=metadata.get("robot_type"),
            safety_level=metadata.get("safety_level", "standard"),
            metadata=metadata
        )

    def save_to_file(self, file_path: str):
        """保存到文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, file_path: str) -> 'RobotChainConfig':
        """从文件加载"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_algorithms_by_category(self, category: RobotAlgorithmCategory) -> List[RobotAlgorithmConfig]:
        """根据分类获取算法"""
        return [algo for algo in self.algorithms if algo.category == category]

    def get_algorithms_by_safety_level(self, safety_level: str) -> List[RobotAlgorithmConfig]:
        """根据安全级别获取算法"""
        return [algo for algo in self.algorithms if algo.safety_level == safety_level]

    def validate_chain_safety(self) -> Tuple[bool, List[str]]:
        """验证整个链的安全性"""
        errors = []

        # 检查每个算法的安全参数
        for i, algo in enumerate(self.algorithms):
            is_valid, algo_errors = algo.validate_safety_parameters()
            if not is_valid:
                for error in algo_errors:
                    errors.append(f"算法 {i} ({algo.display_name}): {error}")

        # 检查链级别的安全性
        if self.safety_level == "high" and not self.algorithms:
            errors.append("高安全级别链不能为空")

        return len(errors) == 0, errors


# 专用配置类型

@dataclass
class CalibrationConfig:
    """标定专用配置"""
    calibration_method: str                    # 标定方法
    reference_points: int = 5                  # 参考点数量
    tolerance: float = 0.001                   # 容差 (米)
    validation_ratio: float = 0.2              # 验证比例
    auto_validate: bool = True                 # 自动验证

    # 标定板配置
    calibration_board_size: Tuple[float, float] = (0.1, 0.1)  # 标定板尺寸
    pattern_type: str = "chessboard"          # 图案类型
    square_size: float = 0.01                  # 方格尺寸

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "calibration_method": self.calibration_method,
            "reference_points": self.reference_points,
            "tolerance": self.tolerance,
            "validation_ratio": self.validation_ratio,
            "auto_validate": self.auto_validate,
            "calibration_board_size": self.calibration_board_size,
            "pattern_type": self.pattern_type,
            "square_size": self.square_size
        }


@dataclass
class TransformConfig:
    """坐标转换专用配置"""
    source_frame: str                          # 源坐标系
    target_frame: str                          # 目标坐标系
    transform_matrix: Optional[List[List[float]]] = None  # 变换矩阵

    # 转换参数
    translation: Optional[List[float]] = None  # 平移 [x, y, z]
    rotation: Optional[List[float]] = None     # 旋转 [r, p, y] 或四元数
    rotation_format: str = "euler"             # "euler" 或 "quaternion"

    # 验证参数
    max_translation_error: float = 0.001       # 最大平移误差
    max_rotation_error: float = 0.01           # 最大旋转误差

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "source_frame": self.source_frame,
            "target_frame": self.target_frame,
            "transform_matrix": self.transform_matrix,
            "translation": self.translation,
            "rotation": self.rotation,
            "rotation_format": self.rotation_format,
            "max_translation_error": self.max_translation_error,
            "max_rotation_error": self.max_rotation_error
        }


@dataclass
class GuidanceConfig:
    """引导专用配置"""
    guidance_type: str                         # 引导类型
    guidance_mode: str = "auto"                # 引导模式 ("auto", "manual", "semi_auto")

    # 视觉引导参数
    vision_threshold: float = 0.8              # 视觉阈值
    detection_confidence: float = 0.9          # 检测置信度
    tracking_enabled: bool = True              # 跟踪启用

    # 力引导参数
    force_threshold: float = 5.0               # 力阈值 (N)
    torque_threshold: float = 0.5              # 力矩阈值 (Nm)
    compliance_enabled: bool = False           # 柔性启用

    # 精度参数
    position_accuracy: float = 0.001           # 位置精度 (m)
    orientation_accuracy: float = 0.01         # 姿态精度 (rad)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "guidance_type": self.guidance_type,
            "guidance_mode": self.guidance_mode,
            "vision_threshold": self.vision_threshold,
            "detection_confidence": self.detection_confidence,
            "tracking_enabled": self.tracking_enabled,
            "force_threshold": self.force_threshold,
            "torque_threshold": self.torque_threshold,
            "compliance_enabled": self.compliance_enabled,
            "position_accuracy": self.position_accuracy,
            "orientation_accuracy": self.orientation_accuracy
        }


# 机械臂UI控件类型映射
ROBOT_UI_WIDGET_MAPPING = {
    ParameterType.INT: "SpinBox",
    ParameterType.FLOAT: "DoubleSpinBox",
    ParameterType.BOOL: "CheckBox",
    ParameterType.STRING: "LineEdit",
    ParameterType.CHOICE: "ComboBox",
    ParameterType.RANGE: "Slider",
    ParameterType.COLOR: "ColorButton",
    ParameterType.FILE: "FileButton",
    ParameterType.ROI: "ROIButton",
    ParameterType.IMAGE: "ImageButton"
}


def get_robot_ui_widget_type(param_type: ParameterType) -> str:
    """获取机械臂参数类型对应的UI控件类型"""
    return ROBOT_UI_WIDGET_MAPPING.get(param_type, "LineEdit")


def validate_robot_parameter_config(param_config: RobotParameterConfig) -> bool:
    """验证机械臂参数配置的有效性"""
    return param_config.validate_value(param_config.value)


def create_default_calibration_config(method: str = "hand_eye") -> CalibrationConfig:
    """创建默认标定配置"""
    return CalibrationConfig(
        calibration_method=method,
        reference_points=8 if method == "hand_eye" else 5,
        tolerance=0.001,
        validation_ratio=0.2
    )


def create_default_transform_config(source_frame: str, target_frame: str) -> TransformConfig:
    """创建默认坐标转换配置"""
    return TransformConfig(
        source_frame=source_frame,
        target_frame=target_frame,
        translation=[0.0, 0.0, 0.0],
        rotation=[0.0, 0.0, 0.0],
        rotation_format="euler"
    )


def create_default_guidance_config(guidance_type: str = "vision") -> GuidanceConfig:
    """创建默认引导配置"""
    return GuidanceConfig(
        guidance_type=guidance_type,
        vision_threshold=0.8,
        detection_confidence=0.9
    )