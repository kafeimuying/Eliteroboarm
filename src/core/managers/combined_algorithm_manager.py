#!/usr/bin/env python3
"""
组合算法管理器 - 管理自定义组合算法的创建、保存和加载
"""

import os
import json
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from datetime import datetime

from ..interfaces.algorithm.vision_config_types import ChainConfig
from ..interfaces.algorithm.base import AlgorithmInfo, AlgorithmParameter, ParameterType
from ..interfaces.algorithm.composite.combined_algorithm import CombinedAlgorithm
from ..managers.log_manager import LogManager


class CombinedAlgorithmManager(QObject):
    """组合算法管理器"""
    
    # 信号
    combined_algorithm_created = pyqtSignal(str)  # 组合算法创建信号
    combined_algorithm_deleted = pyqtSignal(str)  # 组合算法删除信号
    combined_algorithm_updated = pyqtSignal(str)  # 组合算法更新信号
    
    def __init__(self, combined_algorithms_dir: str = None, app_config_manager=None):
        super().__init__()

        # 优先使用AppConfigManager获取路径
        if app_config_manager is not None:
            self.combined_algorithms_dir = str(app_config_manager.algorithms_composite_dir)
        elif combined_algorithms_dir is not None:
            self.combined_algorithms_dir = combined_algorithms_dir
        else:
            # 默认使用AppConfigManager
            try:
                from .app_config import AppConfigManager
                app_config = AppConfigManager()
                self.combined_algorithms_dir = str(app_config.algorithms_composite_dir)
            except Exception:
                # fallback to default path
                self.combined_algorithms_dir = os.path.join(os.getcwd(), "algorithms", "composite")

        self.log_manager = LogManager()
        self._combined_algorithms: Dict[str, ChainConfig] = {}

        # 确保目录存在
        os.makedirs(self.combined_algorithms_dir, exist_ok=True)

        # 加载现有的组合算法
        self.load_combined_algorithms()
    
    def create_combined_algorithm(self, 
                                chain_config: ChainConfig, 
                                name: str = None,
                                description: str = None,
                                metadata: Dict[str, Any] = None) -> str:
        """创建组合算法"""
        try:
            # 如果提供了metadata，使用metadata中的信息，否则使用默认值
            if metadata:
                algorithm_id = metadata.get('algorithm_id') or name or f"combined_{uuid.uuid4().hex[:8]}"
                display_name = metadata.get('display_name') or name or f"组合算法 ({len(chain_config.algorithms)}步)"
                category = metadata.get('category') or "组合算法"  # 一级分类
                secondary_category = metadata.get('secondary_category') or "未分类"  # 二级分类
                description = metadata.get('description') or description or f"包含{len(chain_config.algorithms)}个算法的组合链"
                version = metadata.get('version') or "1.0.0"
                author = metadata.get('author') or "User"
                tags = metadata.get('tags') or ["组合", "链式"]
            else:
                # 生成唯一ID
                algorithm_id = name or f"combined_{uuid.uuid4().hex[:8]}"
                
                # 创建算法信息
                if chain_config.algorithms:
                    algo_count = len(chain_config.algorithms)
                    first_algo = chain_config.algorithms[0]

                    display_name = name or f"组合算法 ({algo_count}步)"
                    category = "组合算法"  # 一级分类
                    secondary_category = "未分类"  # 二级分类
                    description = description or f"包含{algo_count}个算法的组合链"
                    version = "1.0.0"
                    author = "User"
                    tags = ["组合", "链式", f"{algo_count}步"]
                else:
                    display_name = name or "空组合算法"
                    category = "组合算法"  # 一级分类
                    secondary_category = "未分类"  # 二级分类
                    description = description or "空的组合算法"
                    version = "1.0.0"
                    author = "User"
                    tags = ["组合"]
            
            # 创建算法信息对象
            algorithm_info = AlgorithmInfo(
                name=algorithm_id,
                display_name=display_name,
                description=description,
                category=category,  # 一级分类
                secondary_category=secondary_category,  # 二级分类
                version=version,
                author=author,
                tags=tags
            )
            
            # 添加完整的元数据到配置
            chain_config.metadata['combined_algorithm_id'] = algorithm_id
            chain_config.metadata['algorithm_info'] = {
                'algorithm_id': algorithm_id,
                'display_name': algorithm_info.display_name,
                'category': algorithm_info.category,  # 一级分类
                'secondary_category': algorithm_info.secondary_category,  # 二级分类
                'description': algorithm_info.description,
                'version': algorithm_info.version,
                'author': algorithm_info.author,
                'tags': algorithm_info.tags
            }
            chain_config.metadata['created_at'] = datetime.now().isoformat()
            
            # 如果提供了额外的metadata，合并到配置中
            if metadata:
                for key, value in metadata.items():
                    if key not in ['algorithm_id', 'display_name', 'category', 'description', 'version', 'author', 'tags']:
                        chain_config.metadata[key] = value
            
            # 保存配置
            file_path = os.path.join(self.combined_algorithms_dir, f"{algorithm_id}.json")
            chain_config.save_to_file(file_path)
            
            # 注册到内存
            self._combined_algorithms[algorithm_id] = chain_config
            
            self.combined_algorithm_created.emit(algorithm_id)
            self.log_manager.log('INFO', f'创建组合算法成功: {algorithm_id} ({display_name})')
            
            return algorithm_id
            
        except Exception as e:
            self.log_manager.log('ERROR', f'创建组合算法失败: {str(e)}')
            return None
    
    def delete_combined_algorithm(self, algorithm_id: str) -> bool:
        """删除组合算法"""
        try:
            if algorithm_id not in self._combined_algorithms:
                self.log_manager.log('WARNING', f'组合算法不存在: {algorithm_id}')
                return False
            
            # 删除文件
            file_path = os.path.join(self.combined_algorithms_dir, f"{algorithm_id}.json")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # 从内存中删除
            del self._combined_algorithms[algorithm_id]
            
            self.combined_algorithm_deleted.emit(algorithm_id)
            self.log_manager.log('INFO', f'删除组合算法成功: {algorithm_id}')
            
            return True
            
        except Exception as e:
            self.log_manager.log('ERROR', f'删除组合算法失败: {str(e)}')
            return False
    
    def update_combined_algorithm(self, algorithm_id: str, chain_config: ChainConfig) -> bool:
        """更新组合算法"""
        try:
            if algorithm_id not in self._combined_algorithms:
                self.log_manager.log('WARNING', f'组合算法不存在: {algorithm_id}')
                return False
            
            # 更新元数据
            chain_config.metadata['updated_at'] = datetime.now().isoformat()
            chain_config.metadata['combined_algorithm_id'] = algorithm_id
            
            # 保存配置
            file_path = os.path.join(self.combined_algorithms_dir, f"{algorithm_id}.json")
            chain_config.save_to_file(file_path)
            
            # 更新内存
            self._combined_algorithms[algorithm_id] = chain_config
            
            self.combined_algorithm_updated.emit(algorithm_id)
            self.log_manager.log('INFO', f'更新组合算法成功: {algorithm_id}')
            
            return True
            
        except Exception as e:
            self.log_manager.log('ERROR', f'更新组合算法失败: {str(e)}')
            return False
    
    def get_combined_algorithm(self, algorithm_id: str) -> Optional[ChainConfig]:
        """获取组合算法配置"""
        return self._combined_algorithms.get(algorithm_id)
    
    def get_all_combined_algorithms(self) -> Dict[str, ChainConfig]:
        """获取所有组合算法"""
        return self._combined_algorithms.copy()
    
    def create_algorithm_factory(self, algorithm_id: str):
        """创建算法工厂函数供注册表使用"""
        def factory():
            config = self.get_combined_algorithm(algorithm_id)
            if config:
                # 创建组合算法实例
                combined_algorithm = CombinedAlgorithm(chain_config=config)
                # 设置日志管理器和引用
                combined_algorithm.log_manager = self.log_manager
                combined_algorithm.combined_algorithm_manager = self
                return combined_algorithm
            return None
        
        # 设置工厂函数的属性
        factory.__name__ = f"combined_{algorithm_id}"
        factory.combined_algorithm_id = algorithm_id
        
        return factory
    
    def get_algorithm_info(self, algorithm_id: str) -> Optional[AlgorithmInfo]:
        """获取组合算法信息"""
        config = self._combined_algorithms.get(algorithm_id)
        if not config or not config.algorithms:
            return None
        
        # 从元数据中获取或重新创建算法信息
        if 'algorithm_info' in config.metadata:
            info_dict = config.metadata['algorithm_info']
            # 确保字段名正确
            info_dict['name'] = info_dict.pop('algorithm_id', info_dict.get('name', ''))
            # 兼容旧字段名
            if 'custom_category' in info_dict and 'secondary_category' not in info_dict:
                info_dict['secondary_category'] = info_dict.pop('custom_category')
            # 确保 secondary_category 字段存在
            if 'secondary_category' not in info_dict:
                info_dict['secondary_category'] = '未分类'
            return AlgorithmInfo(**info_dict)
        else:
            # 创建新的算法信息
            algo_count = len(config.algorithms)
            first_algo = config.algorithms[0]
            
            return AlgorithmInfo(
                name=algorithm_id,
                display_name=f"组合算法 ({algo_count}步)",
                description=f"包含{algo_count}个算法的组合链: {', '.join([algo.display_name for algo in config.algorithms[:3]])}{'...' if algo_count > 3 else ''}",
                category="组合算法",  # 一级分类
                secondary_category="未分类",  # 二级分类
                version="1.0.0",
                author="User",
                tags=["组合", "链式", f"{algo_count}步"]
            )
    
    def load_combined_algorithms(self):
        """加载所有组合算法"""
        loaded_count = 0
        directory_path = Path(self.combined_algorithms_dir)
        
        if not directory_path.exists():
            self.log_manager.log('WARNING', f'组合算法目录不存在: {self.combined_algorithms_dir}')
            return
        
        # 遍历所有JSON文件
        for json_file in directory_path.glob('*.json'):
            try:
                # 加载配置
                chain_config = ChainConfig.load_from_file(str(json_file))
                
                # 从文件名获取算法ID
                algorithm_id = json_file.stem
                
                # 检查是否是组合算法（有combined_algorithm_id元数据）
                if 'combined_algorithm_id' in chain_config.metadata:
                    algorithm_id = chain_config.metadata['combined_algorithm_id']
                
                self._combined_algorithms[algorithm_id] = chain_config
                loaded_count += 1
                
            except Exception as e:
                self.log_manager.log('ERROR', f'加载组合算法失败 {json_file}: {str(e)}')
        
        self.log_manager.log('INFO', f'加载了 {loaded_count} 个组合算法')
    
    def load_combined_algorithms_from_directory(self, directory: str) -> int:
        """从指定目录加载组合算法并注册到算法注册表
        
        Args:
            directory: 组合算法目录路径
            
        Returns:
            int: 加载的组合算法数量
        """
        loaded_count = 0
        
        try:
            directory_path = Path(directory)
            if not directory_path.exists():
                self.log_manager.log('WARNING', f'组合算法目录不存在: {directory}')
                return 0
            
            # 遍历所有JSON文件
            for json_file in directory_path.glob('*.json'):
                try:
                    # 加载配置
                    chain_config = ChainConfig.load_from_file(str(json_file))
                    
                    # 从文件名获取算法ID
                    algorithm_id = json_file.stem
                    
                    # 检查是否是组合算法（有combined_algorithm_id元数据）
                    if 'combined_algorithm_id' in chain_config.metadata:
                        algorithm_id = chain_config.metadata['combined_algorithm_id']
                    
                    self._combined_algorithms[algorithm_id] = chain_config
                    loaded_count += 1
                    
                except Exception as e:
                    self.log_manager.log('ERROR', f'加载组合算法失败 {json_file}: {str(e)}')
            
            self.log_manager.log('INFO', f'从目录加载了 {loaded_count} 个组合算法')
            
        except Exception as e:
            self.log_manager.log('ERROR', f'从目录加载组合算法失败: {str(e)}')
        
        return loaded_count
    
    def register_combined_algorithms_to_registry(self, registry) -> int:
        """将所有加载的组合算法注册到算法注册表
        
        Args:
            registry: 算法注册表
            
        Returns:
            int: 注册的算法数量
        """
        registered_count = 0
        
        for algorithm_id, chain_config in self._combined_algorithms.items():
            try:
                # 创建算法工厂函数
                factory = self.create_algorithm_factory(algorithm_id)
                algorithm_info = self.get_algorithm_info(algorithm_id)
                
                # 注册到算法注册表
                registry.register_algorithm_class(algorithm_id, factory, algorithm_info)
                registered_count += 1
                
                self.log_manager.log('DEBUG', f'注册组合算法: {algorithm_info.display_name}')
                
            except Exception as e:
                self.log_manager.log('ERROR', f'注册组合算法失败 {algorithm_id}: {str(e)}')
        
        if registered_count > 0:
            self.log_manager.log('INFO', f'成功注册了 {registered_count} 个组合算法')
        
        return registered_count
    
    def export_combined_algorithm(self, algorithm_id: str, export_path: str) -> bool:
        """导出组合算法到指定路径"""
        try:
            config = self._combined_algorithms.get(algorithm_id)
            if not config:
                self.log_manager.log('ERROR', f'组合算法不存在: {algorithm_id}')
                return False
            
            config.save_to_file(export_path)
            self.log_manager.log('INFO', f'导出组合算法成功: {algorithm_id} -> {export_path}')
            return True
            
        except Exception as e:
            self.log_manager.log('ERROR', f'导出组合算法失败: {str(e)}')
            return False
    
    def import_combined_algorithm(self, import_path: str, new_id: str = None) -> Optional[str]:
        """从文件导入组合算法"""
        try:
            config = ChainConfig.load_from_file(import_path)
            
            # 生成新的算法ID
            algorithm_id = new_id or f"combined_imported_{uuid.uuid4().hex[:8]}"
            
            # 保存到组合算法目录
            return self.create_combined_algorithm(config, algorithm_id)
            
        except Exception as e:
            self.log_manager.log('ERROR', f'导入组合算法失败: {str(e)}')
            return None
    
    def get_combined_algorithm_statistics(self) -> Dict[str, Any]:
        """获取组合算法统计信息"""
        total_count = len(self._combined_algorithms)
        total_algorithms = sum(len(config.algorithms) for config in self._combined_algorithms.values())
        
        # 统计不同步数的组合算法数量
        step_distribution = {}
        for config in self._combined_algorithms.values():
            step_count = len(config.algorithms)
            step_distribution[step_count] = step_distribution.get(step_count, 0) + 1
        
        return {
            'total_combined_algorithms': total_count,
            'total_internal_algorithms': total_algorithms,
            'average_steps': total_algorithms / total_count if total_count > 0 else 0,
            'step_distribution': step_distribution,
            'storage_directory': self.combined_algorithms_dir
        }