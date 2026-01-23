#!/usr/bin/env python3
"""
统一配置类型系统
与 ParameterType 枚举完全对应的配置数据结构
"""

from typing import Dict, Any, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from .base import ParameterType
from core.managers.log_manager import debug, error, warning, LogCategory


@dataclass
class ParameterConfig:
    """参数配置定义，与 AlgorithmParameter 对应"""
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
    
    # ROI类型相关
    roi_mode: Optional[str] = None
    roi_constraint: Optional[str] = None
    
    # 通用属性
    required: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "name": self.name,
            "type": self.param_type.value,
            "value": self.value,
            "description": self.description
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
                
        elif self.param_type == ParameterType.ROI:
            if self.roi_mode:
                result["roi_mode"] = self.roi_mode
            if self.roi_constraint:
                result["roi_constraint"] = self.roi_constraint
        
        result["required"] = self.required
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParameterConfig':
        """从字典创建参数配置"""

        param_name = data.get("name", "unknown")
        param_type_str = data.get("type", "string")
        param_value = data.get("value", None)

        # debug(f"创建参数配置: {param_name}, 类型: {param_type_str}, 值: {param_value}", "PARAM_CONFIG", LogCategory.SOFTWARE)

        try:
            # 解析参数类型
            # debug(f"尝试解析参数类型: {param_type_str}", "PARAM_CONFIG", LogCategory.SOFTWARE)
            param_type = ParameterType(param_type_str)
            # debug(f"成功解析参数类型: {param_type}", "PARAM_CONFIG", LogCategory.SOFTWARE)
        except ValueError as e:
            error(f"参数类型无效: {param_type_str}, 错误: {str(e)}", "PARAM_CONFIG", LogCategory.SOFTWARE)
            error(f"完整的参数数据: {data}", "PARAM_CONFIG", LogCategory.SOFTWARE)
            raise

        try:
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
                roi_mode=data.get("roi_mode"),
                roi_constraint=data.get("roi_constraint"),
                required=data.get("required", True)
            )

            # 验证配置
            if not config.validate_value(config.value):
                warning(f"参数值验证失败: {param_name} = {config.value}", "PARAM_CONFIG", LogCategory.SOFTWARE)
            # else:
                # debug(f"参数配置创建成功并通过验证: {param_name}", "PARAM_CONFIG", LogCategory.SOFTWARE)

            return config

        except Exception as e:
            error(f"创建参数配置对象失败: {param_name}, 错误: {str(e)}", "PARAM_CONFIG", LogCategory.SOFTWARE)
            error(f"完整的参数数据: {data}", "PARAM_CONFIG", LogCategory.SOFTWARE)
            raise
    
    def validate_value(self, value: Any) -> bool:
        """验证参数值是否有效"""
        if self.param_type == ParameterType.INT:
            if not isinstance(value, int):
                return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
                
        elif self.param_type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                return False
            if self.min_value is not None and value < self.min_value:
                return False
            if self.max_value is not None and value > self.max_value:
                return False
                
        elif self.param_type == ParameterType.BOOL:
            if not isinstance(value, bool):
                return False
                
        elif self.param_type == ParameterType.STRING:
            if not isinstance(value, str):
                return False
                
        elif self.param_type == ParameterType.CHOICE:
            if self.choices and value not in self.choices:
                return False
                
        elif self.param_type == ParameterType.RANGE:
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                return False
            min_val, max_val = value
            if min_val >= max_val:
                return False
            if self.min_value is not None and min_val < self.min_value:
                return False
            if self.max_value is not None and max_val > self.max_value:
                return False
                
        elif self.param_type == ParameterType.COLOR:
            # 支持多种颜色格式
            if isinstance(value, str):
                # HEX格式: "#RRGGBB" 或 "#RGB"
                if not value.startswith('#'):
                    return False
                hex_part = value[1:]
                if len(hex_part) == 3:
                    # 短格式 #RGB
                    try:
                        int(hex_part, 16)
                    except ValueError:
                        return False
                elif len(hex_part) == 6:
                    # 长格式 #RRGGBB
                    try:
                        int(hex_part, 16)
                    except ValueError:
                        return False
                else:
                    return False
            elif isinstance(value, (list, tuple)):
                # RGB格式: (r, g, b) 或 RGBA格式: (r, g, b, a)
                if len(value) not in [3, 4]:
                    return False
                if not all(isinstance(v, int) and 0 <= v <= 255 for v in value):
                    return False
            else:
                return False
                
        elif self.param_type == ParameterType.FILE:
            if not isinstance(value, str):
                return False

        elif self.param_type == ParameterType.IMAGE:
            # IMAGE类型可以是字符串路径（用于配置存储）或实际图像数据（用于运行时）
            if not isinstance(value, (str, type(None))):
                debug(f"IMAGE类型参数值验证失败: 期望str或None，实际为{type(value)}，值={value}", "PARAM_VALIDATION", LogCategory.SOFTWARE)
                return False

        elif self.param_type == ParameterType.ROI:
            # ROI参数验证
            if isinstance(value, dict):
                required_keys = ["x", "y", "width", "height"]
                if not all(key in value for key in required_keys):
                    return False
                if not all(isinstance(value[key], (int, float)) for key in required_keys):
                    return False
                if value["width"] <= 0 or value["height"] <= 0:
                    return False
                if value["x"] < 0 or value["y"] < 0:
                    return False
            elif isinstance(value, str):
                # xyxy格式: "x1,y1,x2,y2"
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


@dataclass
class AlgorithmConfig:
    """算法配置定义"""
    algorithm_id: str                          # 算法ID
    display_name: str                         # 显示名称
    category: str                             # 分类
    description: str = ""                     # 描述
    version: str = "1.0.0"                  # 版本
    author: str = ""                          # 作者
    
    # 参数配置列表
    parameters: List[ParameterConfig] = field(default_factory=list)
    
    # 布局信息（仅画布环境使用）
    layout: Optional[Dict[str, Any]] = None
    
    # 嵌套的链配置（用于组合算法）
    nested_chain_config: Optional['ChainConfig'] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "algorithm_id": self.algorithm_id,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "parameters": [param.to_dict() for param in self.parameters]
        }
        
        if self.layout:
            result["layout"] = self.layout
        
        # 如果是组合算法，保存嵌套结构
        if self.nested_chain_config:
            result["nested_chain_config"] = self.nested_chain_config.to_dict()
            
        return result
    
    @classmethod
    def from_algorithm_base(cls, algorithm) -> 'AlgorithmConfig':
        """从 AlgorithmBase 实例创建配置"""
        info = algorithm.get_info()
        algorithm_params = algorithm.get_parameters()
        current_values = algorithm.get_all_parameters()
        
        # 检查是否是组合算法
        if hasattr(algorithm, 'get_chain_config') and hasattr(algorithm, 'get_inner_algorithms'):
            # 组合算法特殊处理 - 保持嵌套结构
            chain_config = algorithm.get_chain_config()
            if chain_config:
                # 对于组合算法，我们保存整个嵌套结构
                config = cls(
                    algorithm_id=info.name,
                    display_name=info.display_name,
                    category=info.category,
                    description=info.description,
                    version=info.version,
                    author=info.author,
                    parameters=[],  # 组合算法不在这里保存铺平的参数
                    layout=None
                )
                
                # 存储嵌套的chain_config
                config.nested_chain_config = chain_config
                
                return config
        
        # 普通算法的常规处理
        # 转换参数配置
        param_configs = []
        for param_def in algorithm_params:
            current_value = current_values.get(param_def.name, param_def.default_value)
            
            param_config = ParameterConfig(
                name=param_def.name,
                param_type=param_def.param_type,
                value=current_value,
                description=param_def.description,
                min_value=param_def.min_value,
                max_value=param_def.max_value,
                step=param_def.step,
                choices=param_def.choices,
                roi_mode=param_def.roi_mode,
                roi_constraint=param_def.roi_constraint,
                required=param_def.required
            )
            param_configs.append(param_config)
        
        return cls(
            algorithm_id=info.name,
            display_name=info.display_name,
            category=info.category,
            description=info.description,
            version=info.version,
            author=info.author,
            parameters=param_configs
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlgorithmConfig':
        """从字典创建算法配置"""

        algorithm_id = data.get("algorithm_id", "unknown")
        # debug(f"开始创建算法配置: {algorithm_id}", "ALGO_CONFIG", LogCategory.SOFTWARE)

        # 转换参数配置
        parameters = []
        if "parameters" in data:
            # debug(f"发现参数字段，包含{len(data['parameters'])}个参数", "ALGO_CONFIG", LogCategory.SOFTWARE)
            for i, param_data in enumerate(data["parameters"]):
                param_name = param_data.get("name", f"param_{i}")
                param_type = param_data.get("type", "unknown")
                # debug(f"处理参数 {i+1}/{len(data['parameters'])}: {param_name} (类型: {param_type})", "ALGO_CONFIG", LogCategory.SOFTWARE)
                try:
                    param_config = ParameterConfig.from_dict(param_data)
                    parameters.append(param_config)
                    # debug(f"成功创建参数配置: {param_name}", "ALGO_CONFIG", LogCategory.SOFTWARE)
                except Exception as e:
                    error(f"创建参数配置失败 ({param_name}): {str(e)}", "ALGO_CONFIG", LogCategory.SOFTWARE)
                    error(f"失败的参数数据: {param_data}", "ALGO_CONFIG", LogCategory.SOFTWARE)
                    raise
        else:
            debug(f"算法配置中没有parameters字段: {algorithm_id}", "ALGO_CONFIG", LogCategory.SOFTWARE)
        
        # 创建配置对象
        config = cls(
            algorithm_id=data["algorithm_id"],
            display_name=data["display_name"],
            category=data["category"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            parameters=parameters,
            layout=data.get("layout")
        )
        
        # 如果有嵌套结构，加载它
        if "nested_chain_config" in data:
            config.nested_chain_config = ChainConfig.from_dict(data["nested_chain_config"])
            
        return config
    
    def update_parameter(self, param_name: str, value: Any):
        """更新参数值"""
        for param_config in self.parameters:
            if param_config.name == param_name:
                param_config.value = value
                break
    
    def update_nested_parameter(self, algorithm_id: str, param_name: str, value: Any):
        """更新嵌套配置中指定算法的参数"""
        if not self.nested_chain_config:
            return False
        
        # 找到对应的算法配置
        for algo_config in self.nested_chain_config.algorithms:
            # 支持精确匹配和模糊匹配
            is_match = False
            
            # 精确匹配
            if algo_config.algorithm_id == algorithm_id:
                is_match = True
            # 模糊匹配：algorithm_id是实际ID的前缀或后缀
            elif algo_config.algorithm_id.startswith(algorithm_id) or algo_config.algorithm_id.endswith(algorithm_id):
                is_match = True
                debug(f"使用模糊匹配算法ID: '{algorithm_id}' -> '{algo_config.algorithm_id}'", "CONFIG")
            # 包含匹配
            elif algorithm_id in algo_config.algorithm_id or algo_config.algorithm_id in algorithm_id:
                is_match = True
                debug(f"使用包含匹配算法ID: '{algorithm_id}' -> '{algo_config.algorithm_id}'", "CONFIG")
            
            if is_match:
                # 更新参数值
                for param_config in algo_config.parameters:
                    if param_config.name == param_name:
                        param_config.value = value
                        debug(f"更新嵌套配置参数 {algo_config.algorithm_id}.{param_name} = {value}", "CONFIG")
                        return True

        debug(f"未找到匹配的算法ID: {algorithm_id}", "CONFIG")
        debug(f"可用的算法ID: {[algo.algorithm_id for algo in self.nested_chain_config.algorithms]}", "CONFIG")
        return False
    
    def apply_to_algorithm(self, algorithm):
        """将配置应用到算法实例"""
        import sys
        
        # 检查是否是组合算法，需要特殊处理
        if hasattr(algorithm, 'get_chain_config') and hasattr(algorithm, 'get_inner_algorithms'):
            # 组合算法特殊处理
            if hasattr(self, 'nested_chain_config') and self.nested_chain_config:
                debug(f"应用嵌套配置到组合算法: {algorithm.get_info().display_name}", "CONFIG")
                
                # 更新组合算法的chain_config
                algorithm.chain_config = self.nested_chain_config
                
                # 重新初始化内部算法
                if hasattr(algorithm, 'algorithm_manager') and algorithm.algorithm_manager:
                    algorithm.inner_algorithms.clear()
                    algorithm.initialize_algorithms(algorithm.algorithm_manager)
                    debug(f"组合算法内部算法重新初始化完成", "CONFIG")
                
                # 应用普通参数（如果有）
                for param_config in self.parameters:
                    try:
                        algorithm.set_parameter(param_config.name, param_config.value)
                        debug(f"设置组合算法参数 {param_config.name} = {param_config.value}", "CONFIG")
                    except Exception as e:
                        warning(f"Failed to set parameter {param_config.name}: {e}", "CONFIG")
                
                return
        
        # 普通算法的常规处理
        for param_config in self.parameters:
            try:
                algorithm.set_parameter(param_config.name, param_config.value)
            except Exception as e:
                print(f"Warning: Failed to set parameter {param_config.name}: {e}")


@dataclass
class ConnectionConfig:
    """连接配置定义（画布环境使用）"""
    from_algorithm: str                        # 源算法ID
    to_algorithm: str                          # 目标算法ID
    from_port: str = "right"                   # 源端口
    to_port: str = "left"                      # 目标端口
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "from": self.from_algorithm,
            "to": self.to_algorithm,
            "from_port": self.from_port,
            "to_port": self.to_port
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConnectionConfig':
        """从字典创建连接配置"""
        return cls(
            from_algorithm=data["from"],
            to_algorithm=data["to"],
            from_port=data.get("from_port", "right"),
            to_port=data.get("to_port", "left")
        )


@dataclass
class ChainConfig:
    """算法链配置"""
    algorithms: List[AlgorithmConfig] = field(default_factory=list)
    connections: List[ConnectionConfig] = field(default_factory=list)
    
    # 元数据
    version: str = "1.0"
    created_at: Optional[str] = None
    algorithm_count: int = 0
    canvas_layout: bool = False                # 是否包含画布布局信息
    metadata: Dict[str, Any] = field(default_factory=dict)  # 添加metadata字段
    
    def __post_init__(self):
        if self.algorithm_count == 0:
            self.algorithm_count = len(self.algorithms)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 基本元数据
        base_metadata = {
            "version": self.version,
            "algorithm_count": self.algorithm_count,
            "canvas_layout": self.canvas_layout
        }
        
        if self.created_at:
            base_metadata["created_at"] = self.created_at
        
        # 合并自定义metadata，让自定义metadata覆盖基本metadata
        merged_metadata = {**base_metadata, **self.metadata}
        
        result = {
            "chain": [algo.to_dict() for algo in self.algorithms],
            "metadata": merged_metadata
        }
        
        if self.connections:
            result["connections"] = [conn.to_dict() for conn in self.connections]
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChainConfig':
        """从字典创建链配置"""

        # debug(f"开始从字典创建链配置", "CHAIN_CONFIG", LogCategory.SOFTWARE)
        # debug(f"配置数据结构: {list(data.keys())}", "CHAIN_CONFIG", LogCategory.SOFTWARE)

        # 解析算法配置
        algorithms = []
        if "chain" in data:
            # debug(f"发现chain字段，包含{len(data['chain'])}个算法配置", "CHAIN_CONFIG", LogCategory.SOFTWARE)
            for i, algo_data in enumerate(data["chain"]):
                # debug(f"处理第{i+1}个算法配置: {algo_data.get('algorithm_id', 'unknown')}", "CHAIN_CONFIG", LogCategory.SOFTWARE)
                try:
                    algorithm = AlgorithmConfig.from_dict(algo_data)
                    algorithms.append(algorithm)
                    # debug(f"成功创建算法配置: {algorithm.algorithm_id}", "CHAIN_CONFIG", LogCategory.SOFTWARE)
                except Exception as e:
                    error(f"创建算法配置失败 (第{i+1}个): {str(e)}", "CHAIN_CONFIG", LogCategory.SOFTWARE)
                    error(f"失败的算法数据: {algo_data}", "CHAIN_CONFIG", LogCategory.SOFTWARE)
                    raise
        else:
            error(f"配置数据中缺少'chain'字段", "CHAIN_CONFIG", LogCategory.SOFTWARE)
        
        # 解析连接配置
        connections = []
        if "connections" in data:
            for conn_data in data["connections"]:
                connection = ConnectionConfig.from_dict(conn_data)
                connections.append(connection)
        
        # 解析元数据
        metadata = data.get("metadata", {})
        
        return cls(
            algorithms=algorithms,
            connections=connections,
            version=metadata.get("version", "1.0"),
            created_at=metadata.get("created_at"),
            algorithm_count=metadata.get("algorithm_count", len(algorithms)),
            canvas_layout=metadata.get("canvas_layout", False),
            metadata=metadata
        )
    
    def save_to_file(self, file_path: str):
        """保存到文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_from_file(cls, file_path: str) -> 'ChainConfig':
        """从文件加载"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


# UI控件类型映射
UI_WIDGET_MAPPING = {
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


def get_ui_widget_type(param_type: ParameterType) -> str:
    """获取参数类型对应的UI控件类型"""
    return UI_WIDGET_MAPPING.get(param_type, "LineEdit")


def validate_parameter_config(param_config: ParameterConfig) -> bool:
    """验证参数配置的有效性"""
    return param_config.validate_value(param_config.value)