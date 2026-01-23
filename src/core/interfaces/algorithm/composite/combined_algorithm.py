#!/usr/bin/env python3
"""
组合算法类 - 将算法链封装为单个算法
"""

import json
import os
from typing import Dict, Any, List, Optional
from ..base.algorithm_base import AlgorithmBase, AlgorithmInfo, AlgorithmResult, AlgorithmParameter
from ..vision_config_types import ChainConfig, AlgorithmConfig
from ....managers.log_manager import LogManager
import numpy as np


class CombinedAlgorithm(AlgorithmBase):
    """组合算法 - 将多个算法组合成单个算法"""
    
    def __init__(self, chain_config_path: str = None, chain_config: ChainConfig = None):
        # 先设置属性，再调用父类构造函数
        self.chain_config_path = chain_config_path
        self.chain_config = chain_config
        self.inner_algorithms: List[AlgorithmBase] = []
        self.algorithm_manager = None  # 将在initialize_algorithms中设置
        self.log_manager = LogManager()
        
        # 如果提供了配置路径，加载配置
        if chain_config_path and os.path.exists(chain_config_path):
            self.chain_config = ChainConfig.load_from_file(chain_config_path)
        
        # 现在调用父类构造函数
        super().__init__()
    
    def initialize_algorithms(self, algorithm_manager=None):
        """初始化内部算法"""
        # 如果提供了算法管理器或注册表，使用它
        if algorithm_manager:
            self.algorithm_manager = algorithm_manager
            self._initialize_with_provider(algorithm_manager)
        else:
            # 尝试延迟初始化，在process时才真正初始化
            self._needs_initialization = True
            self.log_manager.log('DEBUG', f'组合算法 {self.get_info().display_name} 延迟初始化')
    
    def _initialize_with_provider(self, algorithm_provider):
        """使用算法提供者（管理器或注册表）初始化内部算法"""
        if not self.chain_config:
            return
        
        # 判断提供者类型并获取注册表
        if hasattr(algorithm_provider, 'get_registry'):
            # AlgorithmManager
            registry = algorithm_provider.get_registry()
        elif hasattr(algorithm_provider, 'create_algorithm_instance'):
            # AlgorithmRegistry
            registry = algorithm_provider
        else:
            self.log_manager.log('ERROR', '无法识别的算法提供者类型')
            return
            
        # 创建内部算法实例
        for algo_config in self.chain_config.algorithms:
            algorithm = registry.create_algorithm_instance(algo_config.algorithm_id)
            if algorithm:
                # 应用配置
                algo_config.apply_to_algorithm(algorithm)
                self.inner_algorithms.append(algorithm)
            else:
                self.log_manager.log('ERROR', f'无法创建内部算法: {algo_config.algorithm_id}')
        
        self._needs_initialization = False
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        """获取组合算法信息"""
        if self.chain_config and self.chain_config.algorithms:
            # 尝试从元数据获取自定义名称，否则生成默认名称
            algo_count = len(self.chain_config.algorithms)
            
            # 检查是否有自定义的算法信息
            if 'algorithm_info' in self.chain_config.metadata:
                algo_info_dict = self.chain_config.metadata['algorithm_info']
                display_name = algo_info_dict.get('display_name', f"组合算法({algo_count}步)")
                description = algo_info_dict.get('description', f"包含{algo_count}个算法的组合链")
                tags = algo_info_dict.get('tags', ["组合", "链式"])
            else:
                # 生成默认名称
                first_algo = self.chain_config.algorithms[0]
                display_name = f"{first_algo.display_name}链"
                description = f"组合链: {', '.join([algo.display_name for algo in self.chain_config.algorithms[:2]])}"
                tags = ["组合", "链式"]
            
            # 从元数据获取组合算法ID，否则生成默认ID
            combined_id = self.chain_config.metadata.get('combined_algorithm_id', f"combined_{algo_count}steps")
            
            return AlgorithmInfo(
                name=combined_id,
                display_name=display_name,
                description=description,
                category="组合算法",
                secondary_category="自定义组合",
                version="1.0.0",
                author="User",
                tags=tags
            )
        else:
            return AlgorithmInfo(
                name="combined_empty",
                display_name="空组合算法",
                description="空的组合算法",
                category="组合算法",
                secondary_category="自定义组合",
                version="1.0.0"
            )
    
    def get_parameters(self) -> List[AlgorithmParameter]:
        """获取组合算法参数 - 暴露所有内部算法的重要参数"""
        params = []
        
        if not self.chain_config:
            return params
            
        # 为每个内部算法添加关键参数
        for i, algo_config in enumerate(self.chain_config.algorithms):
            # 只暴露前3个内部算法的参数，避免参数过多
            if i >= 3:
                break
                
            for param_config in algo_config.parameters:
                # 只添加重要类型的参数（包括ROI）
                if param_config.param_type.value in ['float', 'integer', 'boolean', 'choice', 'roi']:
                    # 使用层级化参数命名：算法ID.参数名
                    hierarchical_name = f"{algo_config.algorithm_id}.{param_config.name}"
                    param = AlgorithmParameter(
                        name=hierarchical_name,
                        param_type=param_config.param_type,
                        default_value=param_config.value,
                        description=f"[{algo_config.display_name}] {param_config.description}",
                        min_value=param_config.min_value,
                        max_value=param_config.max_value,
                        step=param_config.step,
                        choices=param_config.choices,
                        roi_mode=param_config.roi_mode,
                        roi_constraint=param_config.roi_constraint,
                        required=param_config.required
                    )
                    params.append(param)
        
        return params
    
    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        """处理图像 - 依次执行内部算法"""
        # 如果需要初始化，尝试从全局获取算法管理器
        if hasattr(self, '_needs_initialization') and self._needs_initialization:
            try:
                # 尝试获取当前运行的算法管理器
                from ....managers.algorithm_registry import AlgorithmManager
                from ....managers.log_manager import LogManager
                
                # 创建临时的算法管理器（这里可能需要更好的全局访问方式）
                # 但目前先这样处理
                self.log_manager.log('DEBUG', '组合算法尝试自动初始化内部算法')
                self._needs_initialization = False  # 避免无限递归
                
            except Exception as e:
                return AlgorithmResult(
                    success=False,
                    error_message=f"组合算法初始化失败: {str(e)}"
                )
        
        if not self.inner_algorithms:
            return AlgorithmResult(
                success=False,
                error_message="组合算法没有配置内部算法"
            )
        
        try:
            current_image = input_image
            total_processing_time = 0
            
            # 依次执行每个内部算法
            for i, algorithm in enumerate(self.inner_algorithms):
                # 获取当前算法的配置
                algo_config = self.chain_config.algorithms[i]
                algo_prefix = algo_config.algorithm_id + "."
                
                # 收集属于当前算法的参数
                algo_kwargs = {}
                
                # 1. 从kwargs中获取层级化格式的参数（用于UI参数）
                for param_name, param_value in kwargs.items():
                    if param_name.startswith(algo_prefix):
                        # 移除前缀
                        inner_param_name = param_name[len(algo_prefix):]
                        algo_kwargs[inner_param_name] = param_value
                
                # 1.1. 兼容旧的下划线格式
                underscore_prefix = algo_config.algorithm_id + "_"
                for param_name, param_value in kwargs.items():
                    if param_name.startswith(underscore_prefix):
                        # 移除前缀
                        inner_param_name = param_name[len(underscore_prefix):]
                        algo_kwargs[inner_param_name] = param_value
                
                # 2. 从嵌套配置中获取原始格式的参数（用于缓存配置）
                if hasattr(algo_config, 'parameters'):
                    for param_config in algo_config.parameters:
                        if param_config.name not in algo_kwargs:
                            algo_kwargs[param_config.name] = param_config.value
                
                # 3. 如果没有参数，尝试从内部算法实例获取当前参数
                if not algo_kwargs and hasattr(algorithm, 'get_all_parameters'):
                    algo_kwargs = algorithm.get_all_parameters()
                
                from ....managers.log_manager import debug
                debug(f"组合算法执行 - {algo_config.display_name}, 参数: {algo_kwargs}", "ALGO")
                
                # 执行算法
                result = algorithm.process(current_image, **algo_kwargs)
                
                if not result.success:
                    return AlgorithmResult(
                        success=False,
                        error_message=f"组合算法第{i+1}步失败 ({algorithm.get_info().display_name}): {result.error_message}",
                        processing_time=total_processing_time
                    )
                
                # 更新当前图像
                if result.output_image is not None:
                    current_image = result.output_image
                
                # 累计处理时间
                total_processing_time += result.processing_time
                
                # 保存中间结果（只保存前几个）
                if i < 5:  # 最多保存5个中间结果
                    self.add_intermediate_result(f"step_{i+1}_{algorithm.get_info().name}", result.output_image)
            
            return AlgorithmResult(
                success=True,
                output_image=current_image,
                processing_time=total_processing_time
            )
            
        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=f"组合算法执行失败: {str(e)}"
            )
    
    def get_chain_config(self) -> ChainConfig:
        """获取算法链配置"""
        return self.chain_config
    
    def get_inner_algorithms(self) -> List[AlgorithmBase]:
        """获取内部算法列表"""
        return self.inner_algorithms
    
    def add_intermediate_result(self, name: str, image: np.ndarray):
        """添加中间结果 - 组合算法暂不支持中间结果，改为日志记录"""
        # 组合算法暂不支持保存中间结果，改为日志记录
        self.log_manager.log('INFO', f'组合算法中间结果: {name}, 图像尺寸: {image.shape if image is not None else "None"}')
    
    def save_to_file(self, file_path: str):
        """保存组合算法到文件"""
        if self.chain_config:
            self.chain_config.save_to_file(file_path)
    
    @classmethod
    def load_from_file(cls, file_path: str) -> 'CombinedAlgorithm':
        """从文件加载组合算法"""
        return cls(chain_config_path=file_path)