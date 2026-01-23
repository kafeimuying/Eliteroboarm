#!/usr/bin/env python3
"""
算法注册和管理系统
"""

import json
import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Dict, List, Type, Optional, Any
from PyQt6.QtCore import QObject, pyqtSignal

from ..interfaces.algorithm.base import AlgorithmBase, AlgorithmInfo, CompositeAlgorithm
from .log_manager import LogManager, LogCategory, info, debug, warning, error


class AlgorithmRegistry(QObject):
    """算法注册表"""
    
    algorithm_registered = pyqtSignal(str)  # 算法注册信号
    algorithm_unregistered = pyqtSignal(str)  # 算法注销信号
    
    def __init__(self, log_manager: LogManager):
        super().__init__()
        self.log_manager = log_manager
        self._algorithms: Dict[str, Type[AlgorithmBase]] = {}
        self._algorithm_infos: Dict[str, AlgorithmInfo] = {}
        self._categories: Dict[str, List[str]] = {}
        
    def register_algorithm(self, algorithm_class: Type[AlgorithmBase]) -> bool:
        """注册算法"""
        try:
            # 创建临时实例获取信息
            temp_instance = algorithm_class()
            info = temp_instance.get_info()
            
            algorithm_id = info.name
            
            # 检查是否已注册
            if algorithm_id in self._algorithms:
                warning(f'算法 {algorithm_id} 已存在，将被覆盖', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            
            # 注册算法
            self._algorithms[algorithm_id] = algorithm_class
            self._algorithm_infos[algorithm_id] = info
            
            # 分类管理
            category = info.category
            if category not in self._categories:
                self._categories[category] = []
            
            if algorithm_id not in self._categories[category]:
                self._categories[category].append(algorithm_id)
            
            self.algorithm_registered.emit(algorithm_id)
            debug(f'算法 {algorithm_id} 注册成功', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return True

        except Exception as e:
            error(f'算法注册失败: {str(e)}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return False

    def register_algorithm_class(self, algorithm_id: str, factory_func, algorithm_info: AlgorithmInfo) -> bool:
        """注册算法类（使用工厂函数）"""
        try:
            # 检查是否已注册
            if algorithm_id in self._algorithms:
                warning(f'算法 {algorithm_id} 已存在，将被覆盖', "ALGO_REGISTRY", LogCategory.SOFTWARE)

            # 注册算法
            self._algorithms[algorithm_id] = factory_func
            self._algorithm_infos[algorithm_id] = algorithm_info

            # 分类管理
            category = algorithm_info.category
            if category not in self._categories:
                self._categories[category] = []
            if algorithm_id not in self._categories[category]:
                self._categories[category].append(algorithm_id)

            self.algorithm_registered.emit(algorithm_id)
            debug(f'已注册算法: {algorithm_id} ({algorithm_info.display_name})', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return True

        except Exception as e:
            error(f'注册算法失败 {algorithm_id}: {str(e)}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return False

    def unregister_algorithm(self, algorithm_id: str) -> bool:
        """注销算法"""
        if algorithm_id not in self._algorithms:
            warning(f'算法 {algorithm_id} 不存在', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return False
        
        try:
            info = self._algorithm_infos[algorithm_id]
            
            # 从分类中移除
            category = info.category
            if category in self._categories and algorithm_id in self._categories[category]:
                self._categories[category].remove(algorithm_id)
                
                # 如果分类为空，删除分类
                if not self._categories[category]:
                    del self._categories[category]
            
            # 删除算法
            del self._algorithms[algorithm_id]
            del self._algorithm_infos[algorithm_id]
            
            self.algorithm_unregistered.emit(algorithm_id)
            info(f'算法 {algorithm_id} 注销成功', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return True
            
        except Exception as e:
            error(f'算法注销失败: {str(e)}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return False
    
    def get_algorithm_class(self, algorithm_id: str) -> Optional[Type[AlgorithmBase]]:
        """获取算法类"""
        return self._algorithms.get(algorithm_id)
    
    def create_algorithm_instance(self, algorithm_id: str) -> Optional[AlgorithmBase]:
        """创建算法实例"""
        algorithm_factory = self.get_algorithm_class(algorithm_id)
        if algorithm_factory:
            try:
                # 如果是可调用对象（工厂函数或类），直接调用
                instance = algorithm_factory()
                # 如果返回的是自定义算法链，需要初始化内部算法
                if hasattr(instance, 'initialize_algorithms'):
                    instance.initialize_algorithms(self)
                return instance
            except Exception as e:
                error(f'创建算法实例失败 {algorithm_id}: {str(e)}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
        return None
    
    def get_algorithm_info(self, algorithm_id: str) -> Optional[AlgorithmInfo]:
        """获取算法信息"""
        return self._algorithm_infos.get(algorithm_id)
    
    def get_all_algorithms(self) -> Dict[str, AlgorithmInfo]:
        """获取所有算法信息"""
        return self._algorithm_infos.copy()
    
    def get_algorithms_by_category(self, category: str) -> List[str]:
        """根据分类获取算法列表"""
        return self._categories.get(category, []).copy()
    
    def get_all_categories(self) -> List[str]:
        """获取所有分类"""
        return list(self._categories.keys())
    
    def search_algorithms(self, keyword: str) -> List[str]:
        """搜索算法 - 支持模糊搜索"""
        results = []
        keyword = keyword.lower().strip()
        
        if not keyword:
            return []
        
        # 算法匹配分数
        algorithm_score = []
        
        for algorithm_id, info in self._algorithm_infos.items():
            score = 0.0
            
            # 完全匹配算法名称 - 最高权重
            if keyword == info.display_name.lower():
                score += 1.0
            # 算法名称包含搜索文本
            elif keyword in info.display_name.lower():
                score += 0.8
            
            # 完全匹配算法ID
            if keyword == algorithm_id.lower():
                score += 0.9
            # 算法ID包含搜索文本
            elif keyword in algorithm_id.lower():
                score += 0.7
            
            # 描述匹配
            if keyword in info.description.lower():
                score += 0.5
            
            # 标签匹配
            if info.tags:
                for tag in info.tags:
                    if keyword == tag.lower():
                        score += 0.9
                    elif keyword in tag.lower():
                        score += 0.6
                    # 模糊匹配标签
                    elif self._fuzzy_match(keyword, tag.lower()):
                        score += 0.3
            
            # 分类匹配
            if hasattr(info, 'category') and info.category:
                if keyword == info.category.lower():
                    score += 0.7
                elif keyword in info.category.lower():
                    score += 0.4
                elif self._fuzzy_match(keyword, info.category.lower()):
                    score += 0.2
            
            # 二级分类匹配
            if hasattr(info, 'secondary_category') and info.secondary_category:
                if keyword == info.secondary_category.lower():
                    score += 0.7
                elif keyword in info.secondary_category.lower():
                    score += 0.4
                elif self._fuzzy_match(keyword, info.secondary_category.lower()):
                    score += 0.2
            # 向后兼容：支持旧的custom_category属性
            elif hasattr(info, 'custom_category') and info.custom_category:
                if keyword == info.custom_category.lower():
                    score += 0.7
                elif keyword in info.custom_category.lower():
                    score += 0.4
                elif self._fuzzy_match(keyword, info.custom_category.lower()):
                    score += 0.2
            
            # 如果有匹配，添加到结果
            if score > 0:
                algorithm_score.append((algorithm_id, score))
        
        # 按分数排序
        algorithm_score.sort(key=lambda x: x[1], reverse=True)
        
        # 返回排序后的算法ID
        return [alg_id for alg_id, score in algorithm_score]
    
    def _fuzzy_match(self, query: str, text: str, threshold: float = 0.6) -> bool:
        """简单的模糊匹配算法"""
        if not query or not text:
            return False
        
        # 如果完全包含，直接返回True
        if query in text:
            return True
        
        # 字符集匹配
        query_chars = set(query)
        text_chars = set(text)
        common_chars = query_chars & text_chars
        
        if not common_chars:
            return False
        
        # 计算字符重叠率
        overlap_ratio = len(common_chars) / len(query_chars)
        
        # 如果重叠率超过阈值，认为匹配
        if overlap_ratio >= threshold:
            return True
        
        # 子序列匹配
        if len(query) > 2:
            # 检查查询词的子序列是否在目标文本中
            for i in range(len(query) - 1):
                subsequence = query[i:i+2]
                if subsequence in text:
                    return True
        
        return False
    
    def load_algorithms_from_directory(self, directory: str) -> int:
        """从目录加载算法"""
        loaded_count = 0
        directory_path = Path(directory)
        
        if not directory_path.exists():
            error(f'算法目录不存在: {directory}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            return 0
        
        # 遍历所有Python文件
        for py_file in directory_path.glob('**/*.py'):
            if py_file.name.startswith('__'):
                continue
            
            try:
                # 构建模块名
                relative_path = py_file.relative_to(directory_path)
                module_name = str(relative_path.with_suffix('')).replace('/', '.')
                
                # 动态导入模块
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 查找算法类
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, AlgorithmBase) and 
                        obj != AlgorithmBase and 
                        obj != CompositeAlgorithm):
                        
                        if self.register_algorithm(obj):
                            loaded_count += 1
                            
            except Exception as e:
                error(f'加载算法文件失败 {py_file}: {str(e)}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
        
        info(f'从目录 {directory} 加载了 {loaded_count} 个算法', "ALGO_REGISTRY", LogCategory.SOFTWARE)
        return loaded_count
    
    def export_algorithm_list(self, filename: str):
        """导出算法列表"""
        try:
            export_data = {
                'algorithms': {},
                'categories': self._categories
            }
            
            for algorithm_id, info in self._algorithm_infos.items():
                export_data['algorithms'][algorithm_id] = {
                    'name': info.name,
                    'display_name': info.display_name,
                    'description': info.description,
                    'category': info.category,
                    'version': info.version,
                    'author': info.author,
                    'tags': info.tags
                }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            info(f'算法列表已导出到 {filename}', "ALGO_REGISTRY", LogCategory.SOFTWARE)
            
        except Exception as e:
            error(f'导出算法列表失败: {str(e)}', "ALGO_REGISTRY", LogCategory.SOFTWARE)


class AlgorithmManager(QObject):
    """算法管理器"""
    
    algorithm_execution_started = pyqtSignal(str)  # 算法执行开始
    algorithm_execution_finished = pyqtSignal(str, dict)  # 算法执行结束
    
    def __init__(self, log_manager: LogManager):
        super().__init__()
        self.log_manager = log_manager
        self.registry = AlgorithmRegistry(log_manager)
        self._running_algorithms: Dict[str, AlgorithmBase] = {}
    
    def get_registry(self) -> AlgorithmRegistry:
        """获取算法注册表"""
        return self.registry
    
    def execute_algorithm(self, algorithm_id: str, input_image, **kwargs) -> Optional[Any]:
        """执行算法"""
        try:
            algorithm = self.registry.create_algorithm_instance(algorithm_id)
            if not algorithm:
                error(f'无法创建算法实例: {algorithm_id}', "ALGO_MANAGER", LogCategory.SOFTWARE)
                return None
            
            self.algorithm_execution_started.emit(algorithm_id)
            self._running_algorithms[algorithm_id] = algorithm
            
            # 执行算法
            result = algorithm.process(input_image, **kwargs)
            
            # 清理
            if algorithm_id in self._running_algorithms:
                del self._running_algorithms[algorithm_id]
            
            self.algorithm_execution_finished.emit(algorithm_id, result.__dict__)
            return result
            
        except Exception as e:
            error(f'算法执行失败 {algorithm_id}: {str(e)}', "ALGO_MANAGER", LogCategory.SOFTWARE)
            if algorithm_id in self._running_algorithms:
                del self._running_algorithms[algorithm_id]
            return None
    
    def create_composite_algorithm(self, algorithm_ids: List[str]) -> Optional[CompositeAlgorithm]:
        """创建复合算法"""
        try:
            composite = CompositeAlgorithm()
            
            for algorithm_id in algorithm_ids:
                algorithm = self.registry.create_algorithm_instance(algorithm_id)
                if algorithm:
                    composite.add_algorithm(algorithm)
                else:
                    error(f'无法创建算法实例: {algorithm_id}', "ALGO_MANAGER", LogCategory.SOFTWARE)
                    return None
            
            return composite
            
        except Exception as e:
            error(f'创建复合算法失败: {str(e)}', "ALGO_MANAGER", LogCategory.SOFTWARE)
            return None