#!/usr/bin/env python3
"""
算法基础类和接口定义
"""

import numpy as np
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ParameterType(Enum):
    """参数类型枚举"""
    INT = "integer"
    FLOAT = "float"
    BOOL = "boolean"
    STRING = "string"
    CHOICE = "choice"
    RANGE = "range"
    COLOR = "color"
    FILE = "file"
    ROI = "roi"
    IMAGE = "image"


@dataclass
class AlgorithmParameter:
    """算法参数定义"""
    name: str                                    # 参数名称
    param_type: ParameterType                   # 参数类型
    default_value: Any                          # 默认值
    description: str = ""                       # 参数描述
    min_value: Optional[Union[int, float]] = None  # 最小值
    max_value: Optional[Union[int, float]] = None  # 最大值
    choices: Optional[List[str]] = None         # 选择项（用于CHOICE类型）
    step: Optional[Union[int, float]] = None    # 步长
    required: bool = True                       # 是否必需
    # ROI特定属性
    roi_mode: Optional[str] = None              # ROI模式: "manual", "xyxy", "center_size"
    roi_constraint: Optional[str] = None         # ROI约束: "square", "fixed_aspect", "free"
    # IMAGE特定属性
    image_format: Optional[str] = None          # 支持的图像格式: "RGB", "GRAY", "BGR", "ANY"
    image_size_hint: Optional[Tuple[int, int]] = None  # 建议的图像尺寸 (width, height)

    def __post_init__(self):
        if self.param_type == ParameterType.CHOICE and self.choices is None:
            raise ValueError("CHOICE type parameter must have choices")
        if self.param_type == ParameterType.ROI and self.default_value is None:
            self.default_value = {"x": 0, "y": 0, "width": 100, "height": 100}
        if self.param_type == ParameterType.IMAGE and self.default_value is None:
            self.default_value = None  # IMAGE类型默认为None，需要用户选择


@dataclass
class AlgorithmInfo:
    """算法信息"""
    name: str                                   # 算法名称
    display_name: str                          # 显示名称
    description: str                           # 算法描述
    category: str                              # 算法分类 (一级目录)
    version: str = "1.0.0"                    # 版本号
    author: str = ""                           # 作者
    tags: List[str] = field(default_factory=list)  # 标签
    icon: Optional[str] = None                 # 图标路径
    secondary_category: str = "未分类"         # 二级分类


@dataclass
class AlgorithmResult:
    """算法执行结果"""
    success: bool                              # 是否成功
    output_image: Optional[np.ndarray] = None  # 输出图像
    intermediate_results: Dict[str, np.ndarray] = field(default_factory=dict)  # 中间结果
    data: Dict[str, Any] = field(default_factory=dict)  # 其他数据
    error_message: str = ""                    # 错误信息
    processing_time: float = 0.0               # 处理时间
    timestamp: float = field(default_factory=time.time)  # 执行时间戳
    
    def add_intermediate_result(self, name: str, image: np.ndarray):
        """添加中间结果"""
        self.intermediate_results[name] = image


class AlgorithmBase(ABC):
    """算法基础类"""
    
    def __init__(self):
        self._info = self.get_algorithm_info()
        self._parameters = self.get_parameters()
        self._current_params = {p.name: p.default_value for p in self._parameters}
    
    @abstractmethod
    def get_algorithm_info(self) -> AlgorithmInfo:
        """获取算法信息"""
        pass
    
    @abstractmethod
    def get_parameters(self) -> List[AlgorithmParameter]:
        """获取算法参数"""
        pass
    
    @abstractmethod
    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        """处理图像"""
        pass
    
    def get_info(self) -> AlgorithmInfo:
        """获取算法信息"""
        return self._info
    
    def get_parameter_definitions(self) -> List[AlgorithmParameter]:
        """获取参数定义"""
        return self._parameters
    
    def set_parameter(self, name: str, value: Any):
        """设置参数值"""
        param = next((p for p in self._parameters if p.name == name), None)
        if param is None:
            raise ValueError(f"Parameter '{name}' not found")
        
        # 验证参数值
        if not self._validate_parameter(param, value):
            raise ValueError(f"Invalid value for parameter '{name}': {value}")
        
        self._current_params[name] = value
    
    def get_parameter(self, name: str) -> Any:
        """获取参数值"""
        return self._current_params.get(name)
    
    def get_all_parameters(self) -> Dict[str, Any]:
        """获取所有参数值"""
        return self._current_params.copy()
    
    def reset_parameters(self):
        """重置参数为默认值"""
        self._current_params = {p.name: p.default_value for p in self._parameters}
    
    def _validate_parameter(self, param: AlgorithmParameter, value: Any) -> bool:
        """验证参数值"""
        if param.param_type == ParameterType.INT:
            if not isinstance(value, int):
                return False
            if param.min_value is not None and value < param.min_value:
                return False
            if param.max_value is not None and value > param.max_value:
                return False
        elif param.param_type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                return False
            if param.min_value is not None and value < param.min_value:
                return False
            if param.max_value is not None and value > param.max_value:
                return False
        elif param.param_type == ParameterType.BOOL:
            if not isinstance(value, bool):
                return False
        elif param.param_type == ParameterType.STRING:
            if not isinstance(value, str):
                return False
        elif param.param_type == ParameterType.CHOICE:
            if value not in param.choices:
                return False
        elif param.param_type == ParameterType.ROI:
            # ROI参数可以是字典格式或字符串格式
            if isinstance(value, dict):
                required_keys = ["x", "y", "width", "height"]
                if not all(key in value for key in required_keys):
                    return False
                # 验证值类型
                if not all(isinstance(value[key], (int, float)) for key in required_keys):
                    return False
                # 验证宽高为正数
                if value["width"] <= 0 or value["height"] <= 0:
                    return False
                # 验证坐标为非负数
                if value["x"] < 0 or value["y"] < 0:
                    return False
            elif isinstance(value, str):
                # 支持xyxy格式: "x1,y1,x2,y2"
                try:
                    coords = [int(x.strip()) for x in value.split(',')]
                    if len(coords) != 4:
                        return False
                    x1, y1, x2, y2 = coords
                    if x2 <= x1 or y2 <= y1:
                        return False
                    if x1 < 0 or y1 < 0:
                        return False
                except (ValueError, TypeError):
                    return False
            else:
                return False
        
        return True


class CompositeAlgorithm(AlgorithmBase):
    """复合算法基类"""
    
    def __init__(self):
        self._algorithms: List[AlgorithmBase] = []
        super().__init__()
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        """获取复合算法信息"""
        return AlgorithmInfo(
            name="composite_algorithm",
            display_name="复合算法",
            description="由多个算法组成的复合算法",
            category="复合",  # 二级目录
            secondary_category="高级算子",  # 一级目录
            version="1.0.0",
            author="System",
            tags=["复合", "多算法"]
        )
    
    def get_parameters(self) -> List[AlgorithmParameter]:
        """获取复合算法参数（汇总所有子算法参数）"""
        all_params = []
        for i, algorithm in enumerate(self._algorithms):
            algo_params = algorithm.get_parameters()
            # 为每个子算法的参数添加前缀以避免冲突
            for param in algo_params:
                new_param = AlgorithmParameter(
                    name=f"{algorithm.get_info().name}_{param.name}",
                    param_type=param.param_type,
                    default_value=param.default_value,
                    description=f"[{algorithm.get_info().display_name}] {param.description}",
                    min_value=param.min_value,
                    max_value=param.max_value,
                    choices=param.choices,
                    step=param.step,
                    required=param.required
                )
                all_params.append(new_param)
        return all_params
    
    def add_algorithm(self, algorithm: AlgorithmBase):
        """添加子算法"""
        self._algorithms.append(algorithm)
    
    def remove_algorithm(self, index: int):
        """移除子算法"""
        if 0 <= index < len(self._algorithms):
            self._algorithms.pop(index)
    
    def get_algorithms(self) -> List[AlgorithmBase]:
        """获取所有子算法"""
        return self._algorithms.copy()
    
    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        """依次执行所有子算法"""
        result = AlgorithmResult(success=True)
        current_image = input_image
        
        for i, algorithm in enumerate(self._algorithms):
            algo_result = algorithm.process(current_image, **kwargs)
            
            if not algo_result.success:
                result.success = False
                result.error_message = f"Algorithm {i+1} failed: {algo_result.error_message}"
                return result
            
            # 将中间结果添加到总结果中
            for name, img in algo_result.intermediate_results.items():
                result.add_intermediate_result(f"{algorithm.get_info().name}_{name}", img)
            
            # 更新当前图像为算法输出
            if algo_result.output_image is not None:
                current_image = algo_result.output_image
                result.add_intermediate_result(f"{algorithm.get_info().name}_output", current_image)
        
        result.output_image = current_image
        return result