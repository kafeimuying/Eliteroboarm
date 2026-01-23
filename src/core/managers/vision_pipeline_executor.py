#!/usr/bin/env python3
"""
算法链执行器 - 统一的算法链执行引擎

从larminar_vision_algorithm_chain_dialog.py中整合的核心算法链执行逻辑，
供整个项目统一使用。
"""

import json
import numpy as np
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

# 导入核心模块
from ..interfaces.algorithm.base import AlgorithmBase, AlgorithmResult
from ..interfaces.algorithm.vision_config_types import ChainConfig, AlgorithmConfig, ParameterConfig, ConnectionConfig
from ..managers.log_manager import debug, error, LogCategory
from ..interfaces.algorithm.composite.combined_algorithm import CombinedAlgorithm



class PipelineExecutionResult:
    """算法链执行结果"""

    def __init__(self):
        self.success: bool = True
        self.final_image: Optional[np.ndarray] = None
        self.execution_time: float = 0.0
        self.algorithm_results: Dict[str, AlgorithmResult] = {}
        self.error_message: str = ""
        self.intermediate_images: Dict[str, np.ndarray] = {}

    def get_algorithm_result(self, algorithm_id: str) -> Optional[AlgorithmResult]:
        """获取特定算法的结果"""
        return self.algorithm_results.get(algorithm_id)

    def get_intermediate_images(self) -> Dict[str, np.ndarray]:
        """获取所有中间图像"""
        images = {}
        for algo_id, result in self.algorithm_results.items():
            if result.success and result.output_image is not None:
                images[algo_id] = result.output_image
        return images


class PipelineExecutor:
    """算法链执行器 - 统一的算法链执行引擎"""

    def __init__(self, algorithm_manager=None):
        """初始化执行器"""
        self.algorithm_manager = algorithm_manager
        self._execution_callbacks = {}

        # 如果没有提供算法管理器，初始化一个
        if not self.algorithm_manager:
            self._init_algorithm_manager()

        debug("PipelineExecutor: 初始化完成", "VISION_PIPELINE", LogCategory.SYSTEM)

    def _init_algorithm_manager(self):
        """初始化算法管理器"""
        try:
            from .algorithm_registry import AlgorithmManager
            from .log_manager import LogManager

            # 使用全局LogManager实例而不是创建新的
            log_manager = LogManager.instance()
            self.algorithm_manager = AlgorithmManager(log_manager)

            # 加载基础算法
            self._load_basic_algorithms()

            # 加载组合算法
            self._load_combined_algorithms()

            debug("PipelineExecutor: 算法管理器初始化完成", "VISION_PIPELINE", LogCategory.SYSTEM)

        except Exception as e:
            debug(f"PipelineExecutor: 算法管理器初始化失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)
            raise

    def _load_basic_algorithms(self):
        """加载基础算法"""
        try:
            from ..algorithms import basic, advanced, performance
            from ..interfaces.algorithm.base import AlgorithmBase
            import inspect

            loaded_count = 0
            registry = self.algorithm_manager.get_registry()

            for module in [basic, advanced, performance]:
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                        issubclass(obj, AlgorithmBase) and
                        obj != AlgorithmBase):
                        registry.register_algorithm(obj)
                        loaded_count += 1

            debug(f"PipelineExecutor: 成功加载 {loaded_count} 个基础算法", "VISION_PIPELINE", LogCategory.SYSTEM)

        except Exception as e:
            debug(f"PipelineExecutor: 加载基础算法失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)

    def _load_combined_algorithms(self):
        """加载组合算法"""
        try:
            from ..managers.combined_algorithm_manager import CombinedAlgorithmManager

            combined_manager = CombinedAlgorithmManager()
            registry = self.algorithm_manager.get_registry()

            # 获取所有组合算法并注册
            combined_algorithms = combined_manager.get_all_combined_algorithms()

            for algorithm_id, chain_config in combined_algorithms.items():
                algorithm_info = combined_manager.get_algorithm_info(algorithm_id)
                if algorithm_info:
                    factory = combined_manager.create_algorithm_factory(algorithm_id)
                    registry.register_algorithm_class(algorithm_id, factory, algorithm_info)

                    debug(f"PipelineExecutor: 已加载组合算法: {algorithm_info.display_name}", "VISION_PIPELINE", LogCategory.SYSTEM)

        except Exception as e:
            debug(f"PipelineExecutor: 加载组合算法失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)

    def add_execution_callback(self, event_type: str, callback: Callable):
        """添加执行回调函数"""
        if event_type not in self._execution_callbacks:
            self._execution_callbacks[event_type] = []
        self._execution_callbacks[event_type].append(callback)

    def _trigger_callback(self, event_type: str, *args, **kwargs):
        """触发回调函数"""
        if event_type in self._execution_callbacks:
            for callback in self._execution_callbacks[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    debug(f"PipelineExecutor: 回调函数执行失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)

    def load_config_from_file(self, config_path: str) -> ChainConfig:
        """从文件加载配置"""
        try:
            debug(f"PipelineExecutor: 尝试加载配置文件: {config_path}", "VISION_PIPELINE", LogCategory.SYSTEM)

            # 首先尝试加载为标准ChainConfig
            try:
                chain_config = ChainConfig.load_from_file(config_path)
                if chain_config:
                    debug(f"PipelineExecutor: 从标准配置文件加载成功: {config_path}", "VISION_PIPELINE", LogCategory.SYSTEM)
                    debug(f"PipelineExecutor: 标准配置包含 {len(chain_config.algorithms)} 个算法", "VISION_PIPELINE", LogCategory.SYSTEM)
                    return chain_config
            except Exception as e:
                debug(f"PipelineExecutor: 标准配置加载失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)

            # 如果标准格式加载失败，尝试从原始JSON创建ChainConfig
            debug(f"PipelineExecutor: 尝试从原始JSON创建配置", "VISION_PIPELINE", LogCategory.SYSTEM)
            with open(config_path, 'r', encoding='utf-8') as f:
                raw_config = json.load(f)

            if 'chain' not in raw_config:
                raise ValueError("配置文件格式错误：缺少'chain'字段")

            # 创建ChainConfig对象
            chain_config = ChainConfig(
                canvas_layout=raw_config.get('metadata', {}).get('canvas_layout', True),
                created_at=raw_config.get('metadata', {}).get('created_at', 'Unknown')
            )

            # 转换算法配置
            for algo_data in raw_config.get('chain', []):
                algo_config = AlgorithmConfig(
                    algorithm_id=algo_data['algorithm_id'],
                    display_name=algo_data.get('display_name', algo_data['algorithm_id']),
                    category=algo_data.get('category', '未分类'),
                    description=algo_data.get('description', ''),
                    version=algo_data.get('version', '1.0.0'),
                    author=algo_data.get('author', 'Unknown')
                )

                # 处理参数
                parameters = algo_data.get('parameters', {})
                if isinstance(parameters, dict):
                    # 字典格式：直接转换
                    for param_name, param_value in parameters.items():
                        param_config = ParameterConfig(
                            name=param_name,
                            param_type='mixed',
                            value=param_value,
                            description=f'参数 {param_name}',
                            required=True
                        )
                        algo_config.parameters.append(param_config)
                elif isinstance(parameters, list):
                    # 列表格式：从列表转换
                    for param in parameters:
                        if isinstance(param, dict) and 'name' in param and 'value' in param:
                            param_type = param.get('type', 'mixed')
                            param_config = ParameterConfig(
                                name=param['name'],
                                param_type=param_type,
                                value=param['value'],
                                description=param.get('description', f'参数 {param["name"]}'),
                                required=param.get('required', True)
                            )
                            algo_config.parameters.append(param_config)

                # 添加布局信息
                if 'layout' in algo_data:
                    algo_config.layout = algo_data['layout']

                chain_config.algorithms.append(algo_config)

            # 处理连接信息
            if 'connections' in raw_config:
                for conn_data in raw_config['connections']:
                    from_id = conn_data.get('from', '')
                    to_id = conn_data.get('to', '')

                    conn_config = ConnectionConfig(
                        from_algorithm=from_id,
                        to_algorithm=to_id,
                        from_port=conn_data.get('from_port', 'right'),
                        to_port=conn_data.get('to_port', 'left')
                    )
                    chain_config.connections.append(conn_config)
                    debug(f"PipelineExecutor: 添加连接: {from_id} -> {to_id}", "VISION_PIPELINE", LogCategory.SYSTEM)

            debug(f"PipelineExecutor: 从原始JSON配置文件加载成功: {config_path}", "VISION_PIPELINE", LogCategory.SYSTEM)
            return chain_config

        except Exception as e:
            error(f"PipelineExecutor: 从文件加载配置失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)
            raise

    def build_execution_order_from_config(self, chain_config: ChainConfig, algorithm_map: Optional[Dict[str, AlgorithmBase]] = None) -> List[AlgorithmBase]:
        """从配置构建算法执行顺序"""
        try:
            execution_order = []

            debug(f"PipelineExecutor: 开始构建执行顺序，算法数量: {len(chain_config.algorithms) if chain_config.algorithms else 0}", "VISION_PIPELINE", LogCategory.SYSTEM)

            if not chain_config.algorithms:
                debug("PipelineExecutor: 配置中没有算法", "VISION_PIPELINE", LogCategory.SYSTEM)
                return execution_order

            # 如果没有提供算法映射，创建一个
            if algorithm_map is None:
                algorithm_map = {}
                for algo_config in chain_config.algorithms:
                    debug(f"PipelineExecutor: 处理算法配置: {algo_config.algorithm_id}", "VISION_PIPELINE", LogCategory.SYSTEM)
                    algorithm = self.algorithm_manager.get_registry().create_algorithm_instance(algo_config.algorithm_id)
                    if algorithm:
                        # 应用配置到算法
                        algo_config.apply_to_algorithm(algorithm)

                        # 如果是组合算法，设置算法管理器引用
                        if isinstance(algorithm, CombinedAlgorithm):
                            algorithm.algorithm_manager = self.algorithm_manager
                            algorithm.initialize_algorithms(self.algorithm_manager)

                        algorithm_map[algo_config.algorithm_id] = algorithm
                        debug(f"PipelineExecutor: 创建算法实例: {algo_config.display_name}", "VISION_PIPELINE", LogCategory.SYSTEM)
                    else:
                        debug(f"PipelineExecutor: 无法创建算法实例: {algo_config.algorithm_id}", "VISION_PIPELINE", LogCategory.SYSTEM)

            debug(f"PipelineExecutor: 算法映射创建完成，包含 {len(algorithm_map)} 个算法", "VISION_PIPELINE", LogCategory.SYSTEM)

            # 根据连接关系构建执行顺序
            if chain_config.connections:
                # 构建连接图
                graph = {}
                for conn in chain_config.connections:
                    # 确保conn是ConnectionConfig对象
                    if isinstance(conn, ConnectionConfig):
                        from_id = conn.from_algorithm
                        to_id = conn.to_algorithm

                        if from_id not in graph:
                            graph[from_id] = []
                        graph[from_id].append(to_id)
                        debug(f"PipelineExecutor: 构建连接图: {from_id} -> {to_id}", "VISION_PIPELINE", LogCategory.SYSTEM)
                    else:
                        debug(f"PipelineExecutor: 跳过无效连接: {conn}", "VISION_PIPELINE", LogCategory.SYSTEM)

                # 拓扑排序找到执行顺序
                visited = set()
                temp_visited = set()

                def dfs(algo_id):
                    if algo_id in temp_visited:
                        raise ValueError(f"检测到循环依赖: {algo_id}")
                    if algo_id in visited:
                        return

                    temp_visited.add(algo_id)
                    if algo_id in graph:
                        for next_algo in graph[algo_id]:
                            dfs(next_algo)
                    temp_visited.remove(algo_id)
                    visited.add(algo_id)

                    if algo_id in algorithm_map:
                        execution_order.append(algorithm_map[algo_id])

                # 从没有前驱的节点开始
                all_algos = set(algorithm_map.keys())
                with_predecessor = set()
                for conn in chain_config.connections:
                    with_predecessor.add(conn.to_algorithm)

                start_algos = all_algos - with_predecessor

                for algo_id in start_algos:
                    dfs(algo_id)

                # 确保所有算法都被包含
                for algo_id in all_algos:
                    if algo_id not in visited:
                        if algo_id in algorithm_map:
                            execution_order.append(algorithm_map[algo_id])
            else:
                # 没有连接关系，按配置顺序执行
                for algo_config in chain_config.algorithms:
                    if algo_config.algorithm_id in algorithm_map:
                        execution_order.append(algorithm_map[algo_config.algorithm_id])

            debug(f"PipelineExecutor: 构建执行顺序完成，包含 {len(execution_order)} 个算法", "VISION_PIPELINE", LogCategory.SYSTEM)
            return execution_order

        except Exception as e:
            error(f"PipelineExecutor: 构建执行顺序失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)
            raise

    def execute_algorithm_chain(self, execution_order: List[AlgorithmBase], input_image: np.ndarray,
                              cache_config_path: Optional[str] = None, verbose: bool = False) -> PipelineExecutionResult:
        """
        执行算法序列 - 核心执行逻辑，整合自larminar_vision_algorithm_chain_dialog.py

        Args:
            execution_order: 算法执行顺序列表
            input_image: 输入图像
            cache_config_path: 缓存配置文件路径（用于刷新算法参数）
            verbose: 是否显示详细信息

        Returns:
            PipelineExecutionResult: 执行结果
        """
        import time
        start_time = time.time()

        result = PipelineExecutionResult()
        if isinstance(input_image, list):
            current_image = [img.copy() if isinstance(img, np.ndarray) else img for img in input_image]
        else:
            current_image = input_image.copy()

        try:
            debug(f"execute_algorithm_chain 开始执行", "VISION_PIPELINE", LogCategory.ALGO)
            debug(f"  执行顺序包含 {len(execution_order)} 个算法", "VISION_PIPELINE", LogCategory.ALGO)
            if isinstance(input_image, list):
                debug(f"  输入图片列表: {len(input_image)} 张图片", "VISION_PIPELINE", LogCategory.ALGO)
                for i, img in enumerate(input_image):
                    if isinstance(img, np.ndarray):
                        debug(f"    图片 {i}: {img.shape}", "VISION_PIPELINE", LogCategory.ALGO)
                    else:
                        debug(f"    图片 {i}: {type(img)} - {img}", "VISION_PIPELINE", LogCategory.ALGO)
            else:
                debug(f"  输入图像尺寸: {input_image.shape}", "VISION_PIPELINE", LogCategory.ALGO)

            self._trigger_callback('execution_started', len(execution_order))

            for i, algorithm in enumerate(execution_order):
                try:
                    # 更新状态回调
                    algo_info = algorithm.get_info()
                    self._trigger_callback('algorithm_started', i+1, len(execution_order), algo_info.display_name)

                    if verbose:
                        print(f"执行算法 {i+1}/{len(execution_order)}: {algo_info.display_name} ({algo_info.name})")

                    # 检查是否是组合算法，如果是则需要初始化
                    if isinstance(algorithm, CombinedAlgorithm):
                        if not algorithm.inner_algorithms and self.algorithm_manager:
                            algorithm.initialize_algorithms(self.algorithm_manager)

                        # 强制重新加载组合算法的配置
                        if cache_config_path:
                            debug(f"为组合算法 {algo_info.display_name} 强制重新加载配置", "VISION_PIPELINE", LogCategory.SYSTEM)
                            latest_chain_config = self.load_config_from_file(cache_config_path)
                            if latest_chain_config:
                                # 找到对应的组合算法配置
                                node_config = None
                                for algo_config in latest_chain_config.algorithms:
                                    if algo_config.algorithm_id == algo_info.name:
                                        node_config = algo_config
                                        debug(f"找到匹配的组合算法配置: {algo_config.display_name}", "VISION_PIPELINE", LogCategory.SYSTEM)
                                        break

                                if node_config and hasattr(node_config, 'nested_chain_config') and node_config.nested_chain_config:
                                    debug(f"更新组合算法的嵌套配置", "VISION_PIPELINE", LogCategory.SYSTEM)
                                    algorithm.chain_config = node_config.nested_chain_config
                                    algorithm.inner_algorithms.clear()
                                    algorithm.initialize_algorithms(self.algorithm_manager)
                                    debug(f"组合算法重新初始化完成，内部算法数量: {len(algorithm.inner_algorithms)}", "VISION_PIPELINE", LogCategory.SYSTEM)
                    else:
                        # 对于普通算法，也从最新配置中刷新参数
                        if cache_config_path:
                            debug(f"为普通算法 {algo_info.display_name} 刷新参数", "VISION_PIPELINE", LogCategory.SYSTEM)
                            latest_chain_config = self.load_config_from_file(cache_config_path)
                            if latest_chain_config:
                                for algo_config in latest_chain_config.algorithms:
                                    if algo_config.algorithm_id == algo_info.name:
                                        debug(f"找到匹配的算法配置: {algo_config.display_name}", "VISION_PIPELINE", LogCategory.SYSTEM)
                                        algo_config.apply_to_algorithm(algorithm)
                                        break

                    # 获取算法参数（在算法配置刷新之后）
                    all_params = algorithm.get_all_parameters()

                    # 执行算法
                    debug(f"开始执行算法 {algo_info.display_name}", "VISION_PIPELINE", LogCategory.ALGO)
                    if isinstance(current_image, list):
                        debug(f"  输入图片列表: {len(current_image)} 张图片", "VISION_PIPELINE", LogCategory.ALGO)
                    else:
                        debug(f"  输入图像尺寸: {current_image.shape}", "VISION_PIPELINE", LogCategory.ALGO)
                    debug(f"  算法参数: {all_params}", "VISION_PIPELINE", LogCategory.ALGO)

                    try:
                        algo_result = algorithm.process(current_image, **all_params)
                        debug(f"算法 {algo_info.display_name} 执行完成", "VISION_PIPELINE", LogCategory.ALGO)

                        if algo_result is None:
                            debug(f"❌ 算法返回了 None 结果", "VISION_PIPELINE", LogCategory.ALGO)
                            algo_result = AlgorithmResult(success=False, error_message="算法返回了None结果")

                        # 存储算法结果
                        result.algorithm_results[algo_info.name] = algo_result

                        # 触发算法完成回调
                        self._trigger_callback('algorithm_completed', i+1, len(execution_order), algo_info.display_name, algo_result)

                        if algo_result.success and algo_result.output_image is not None:
                            current_image = algo_result.output_image
                            if verbose:
                                print(f"  ✓ 算法 {i+1} 执行完成")
                        else:
                            error_msg = f"算法 {algo_info.display_name} 执行失败: {algo_result.error_message}"
                            debug(f"❌ {error_msg}", "VISION_PIPELINE", LogCategory.ALGO)
                            result.success = False
                            result.error_message = error_msg
                            break

                    except Exception as e:
                        error_msg = f"算法 {algo_info.display_name} 执行异常: {str(e)}"
                        debug(f"❌ {error_msg}", "VISION_PIPELINE", LogCategory.ALGO)

                        # 创建失败结果
                        algo_result = AlgorithmResult(success=False, error_message=error_msg)
                        result.algorithm_results[algo_info.name] = algo_result

                        result.success = False
                        result.error_message = error_msg
                        break

                except Exception as e:
                    algo_info = algorithm.get_info()
                    error_msg = f"算法 {algo_info.display_name} 处理出错: {e}"
                    debug(f"❌ {error_msg}", "VISION_PIPELINE", LogCategory.ALGO)
                    result.success = False
                    result.error_message = error_msg
                    break

            # 设置最终结果
            result.final_image = current_image
            result.execution_time = time.time() - start_time

            self._trigger_callback('execution_completed', result.success, result.execution_time)

            if result.success:
                debug(f"✓ 算法链执行完成", "VISION_PIPELINE", LogCategory.ALGO)
                if verbose:
                    print("算法链执行完成")
            else:
                debug(f"❌ 算法链执行失败: {result.error_message}", "VISION_PIPELINE", LogCategory.SYSTEM)

            return result

        except Exception as e:
            error_msg = f"算法链执行失败: {e}"
            error(f"❌ {error_msg}", "VISION_PIPELINE", LogCategory.ALGO)
            result.success = False
            result.error_message = error_msg
            result.execution_time = time.time() - start_time
            return result

    def execute_pipeline_from_config(self, config_path: str, input_image: np.ndarray,
                                   verbose: bool = False) -> PipelineExecutionResult:
        """
        从配置文件执行算法链 - 主要入口函数

        Args:
            config_path: 配置文件路径
            input_image: 输入图像
            verbose: 是否显示详细信息

        Returns:
            PipelineExecutionResult: 执行结果
        """
        try:
            if verbose:
                print(f"开始执行算法链...")
                print(f"配置文件: {config_path}")
                if isinstance(input_image, list):
                    print(f"输入图片列表: {len(input_image)} 张图片")
                else:
                    print(f"输入图像尺寸: {input_image.shape}")

            # 加载配置
            chain_config = self.load_config_from_file(config_path)

            # 构建执行顺序
            execution_order = self.build_execution_order_from_config(chain_config)

            if not execution_order:
                raise ValueError("没有找到可执行的算法")

            if verbose:
                print(f"算法数量: {len(execution_order)}")

            # 执行算法链
            return self.execute_algorithm_chain(execution_order, input_image, config_path, verbose)

        except Exception as e:
            error_msg = f"从配置文件执行算法链失败: {e}"
            error(f"❌ {error_msg}", "VISION_PIPELINE", LogCategory.ALGO)

            result = PipelineExecutionResult()
            result.success = False
            result.error_message = error_msg
            return result

    def get_algorithm_info(self) -> List[Dict[str, Any]]:
        """获取已注册的算法信息"""
        try:
            registry = self.algorithm_manager.get_registry()
            algorithms = registry.get_all_algorithms()

            algorithm_info = []
            for algorithm_id, algorithm_class in algorithms.items():
                # 创建临时实例获取信息
                try:
                    temp_instance = algorithm_class()
                    info = temp_instance.get_info()
                    algorithm_info.append({
                        'id': algorithm_id,
                        'name': info.display_name,
                        'category': info.category,
                        'description': info.description
                    })
                except Exception:
                    # 如果无法创建实例，跳过
                    continue

            return algorithm_info

        except Exception as e:
            error(f"PipelineExecutor: 获取算法信息失败: {e}", "VISION_PIPELINE", LogCategory.SYSTEM)
            return []


# 便捷函数，供外部直接调用
def execute_pipeline_from_config(config_path: str, input_image: np.ndarray,
                                verbose: bool = False, algorithm_manager=None) -> PipelineExecutionResult:
    """
    便捷函数：从配置文件执行算法链

    Args:
        config_path: 配置文件路径
        input_image: 输入图像
        verbose: 是否显示详细信息
        algorithm_manager: 算法管理器（可选）

    Returns:
        PipelineExecutionResult: 执行结果
    """
    executor = PipelineExecutor(algorithm_manager)
    return executor.execute_pipeline_from_config(config_path, input_image, verbose)


def validate_config_file(config_path: str, algorithm_manager=None) -> bool:
    """
    验证配置文件是否有效

    Args:
        config_path: 配置文件路径
        algorithm_manager: 算法管理器（可选）

    Returns:
        配置文件是否有效
    """
    try:
        executor = PipelineExecutor(algorithm_manager)
        chain_config = executor.load_config_from_file(config_path)
        return chain_config is not None and len(chain_config.algorithms) > 0
    except Exception:
        return False


def get_available_algorithms(algorithm_manager=None) -> List[Dict[str, Any]]:
    """
    获取所有可用的算法列表

    Args:
        algorithm_manager: 算法管理器（可选）

    Returns:
        算法信息列表
    """
    try:
        executor = PipelineExecutor(algorithm_manager)
        return executor.get_algorithm_info()
    except Exception:
        return []