#!/usr/bin/env python3
"""
LaminarVision风格算法链调试对话框 - 完整功能版本
基于画布的可视化算法编程界面

注意：这是一个完整功能版本的对话框，保持了所有原有功能，
但底层使用新的 ui/canvas 模块组件。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTabWidget, QWidget, QScrollArea, QGroupBox,
                             QLabel, QFileDialog, QMessageBox, QSplitter, 
                             QGraphicsView, QGraphicsScene, QGraphicsItem,
                             QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsLineItem,
                             QGraphicsPathItem, QGraphicsTextItem, QMenu, QDialogButtonBox, QComboBox,
                             QLineEdit, QTextEdit, QInputDialog, QApplication)
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF, QLineF, pyqtSignal, QMimeData, QDateTime, QThread, QThreadPool, QRunnable
from PyQt6.QtGui import QPen, QBrush, QColor, QDrag, QPainter, QFont, QPixmap, QImage, QPainterPath
import numpy as np
import subprocess
import sys

# 导入核心组件
from core.interfaces.algorithm.base import AlgorithmBase, AlgorithmResult, AlgorithmInfo
from core.interfaces.algorithm.vision_config_types import ChainConfig, AlgorithmConfig, ParameterConfig, ConnectionConfig, get_ui_widget_type
from core.interfaces.algorithm.composite.combined_algorithm import CombinedAlgorithm
from core.managers.window_settings_manager import get_window_settings_manager
from core.managers.vision_pipeline_executor import PipelineExecutor
from core.managers.log_manager import debug, info, error, warning, LogCategory
from core.managers.combined_algorithm_manager import CombinedAlgorithmManager

from ..components.parameter_widget import DynamicParameterWidget
from ..components.type_aware_parameter_widget import TypeAwareParameterWidget
from ..components.algorithm_panel import AlgorithmCategoryWidget
from ..dialogs.intermediate_result_dialog import IntermediateResultDialog, ROISelectionDialog
from ..dialogs.interactive_roi_selection import InteractiveROISelectionDialog


# 从同模块导入画布组件
from .canvas import AlgorithmCanvas
from .nodes import AlgorithmNode, ImageNode
from .connections import ConnectionLine
from .image_dialog import ImageDisplayDialog
from .recursive_combined_algorithm_dialogs import RecursiveCombinedAlgorithmDebugDialog


class LarminarVisionAlgorithmChainDialog(QDialog):
    """LarminarVision风格算法链配置对话框 - 完整功能版本"""
    
    def __init__(self, parent=None, algorithm_chain: List[AlgorithmBase] = None, vmc_node=None, vmc_callback=None):
        super().__init__(parent)
        self.main_window = parent
        self.algorithm_chain = algorithm_chain or []
        self.current_algorithm = None
        self.window_settings_manager = get_window_settings_manager()
        
        # VMC节点同步功能
        self.vmc_node = vmc_node  # 引用VMC视觉节点
        self.vmc_callback = vmc_callback  # 回调函数用于同步算法配置
        self.is_from_vmc_node = vmc_node is not None  # 标识是否来自VMC节点
        
        # 初始化组合算法管理器
        self.combined_algorithm_manager = CombinedAlgorithmManager()
        
        # 设置算法管理器引用
        if (self.main_window and 
            hasattr(self.main_window, 'algorithm_manager') and 
            self.main_window.algorithm_manager is not None):
            self.algorithm_manager = self.main_window.algorithm_manager
        else:
            # 创建默认的算法管理器
            from core.managers.algorithm_registry import AlgorithmManager
            from core.managers.log_manager import LogManager
            log_manager = LogManager()
            self.algorithm_manager = AlgorithmManager(log_manager)
            
            # 立即加载基础算法
            self._load_basic_algorithms()

        # 初始化统一的PipelineExecutor
        self.pipeline_executor = PipelineExecutor(self.algorithm_manager)

        # 递归调试相关
        self.recursive_debug_dialogs = []  # 存储递归打开的调试对话框
        
        # 性能优化相关
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)  # 限制线程数量
        self.current_output_image = None  # 存储最终输出图像
        self.current_execution_order = []  # 存储当前执行顺序
        self.current_input_image = None  # 存储当前输入图像
        
        # 配置缓存相关
        self.cache_file_path = None  # 缓存配置文件路径
        self.first_drag_operation = True  # 标记是否为第一次拖拽操作

        self.init_ui()

        # 初始化配置缓存
        self.init_config_cache()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('算法链调试')
        self.setGeometry(200, 200, 1200, 800)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建主分割器
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # 创建状态栏
        self.status_bar = QLabel()
        self.status_bar.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-top: 1px solid #ccc;")
        self.status_bar.setText("就绪")
        main_layout.addWidget(self.status_bar)
        
        # 左侧：算法库
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        library_label = QLabel("算法库:")
        left_layout.addWidget(library_label)
        
        # 算法库组件
        self.algorithm_category_widget = AlgorithmCategoryWidget()
        self.algorithm_category_widget.algorithm_dropped.connect(self.on_algorithm_dropped_from_library)
        left_layout.addWidget(self.algorithm_category_widget)
        
        self.main_splitter.addWidget(left_widget)
        
        # 中间：画布区域
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(5, 5, 5, 5)
        
        # 工具栏
        toolbar_layout = QHBoxLayout()
        
        self.load_image_btn = QPushButton('📁 加载图像')
        self.load_image_btn.clicked.connect(self.load_image_dialog)
        toolbar_layout.addWidget(self.load_image_btn)
        
        # 连接提示标签
        connection_help = QLabel('💡 提示: 直接拖拽节点边缘的引脚进行连接')
        connection_help.setStyleSheet("color: #666; font-size: 10px;")
        toolbar_layout.addWidget(connection_help)
        
        self.execute_btn = QPushButton('▶️ 执行 (F5)')
        self.execute_btn.clicked.connect(self.execute_algorithm_chain)
        toolbar_layout.addWidget(self.execute_btn)
        
        self.save_btn = QPushButton('💾 保存配置')
        self.save_btn.clicked.connect(self.save_chain_config)
        toolbar_layout.addWidget(self.save_btn)
        
        self.load_btn = QPushButton('📂 加载配置')
        self.load_btn.clicked.connect(self.load_chain_config)
        toolbar_layout.addWidget(self.load_btn)
        
        self.clear_btn = QPushButton('🗑️ 清空画布')
        self.clear_btn.clicked.connect(self.clear_canvas)
        toolbar_layout.addWidget(self.clear_btn)
        
        # 保存为组合算法按钮
        self.save_combined_btn = QPushButton('🔗 保存为组合算法')
        self.save_combined_btn.clicked.connect(self.save_as_combined_algorithm)
        toolbar_layout.addWidget(self.save_combined_btn)
        
        # VMC节点同步按钮（只有从VMC节点打开时才显示）
        if self.is_from_vmc_node:
            apply_to_node_btn = QPushButton('🔗 应用到节点')
            apply_to_node_btn.clicked.connect(self.apply_to_vmc_node)
            apply_to_node_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF9800;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #F57C00;
                    border: 1px solid #F57C00;
                }
                QPushButton:pressed {
                    background-color: #E65100;
                    border: 1px solid #E65100;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                    border: 1px solid #cccccc;
                }
            """)
            toolbar_layout.addWidget(apply_to_node_btn)
        
        toolbar_layout.addStretch()
        middle_layout.addLayout(toolbar_layout)
        
        # 算法画布 - 使用新的canvas模块
        self.canvas = AlgorithmCanvas(parent_dialog=self)
        self.canvas.algorithm_dropped.connect(self.on_algorithm_dropped_to_canvas)
        self.canvas.node_selected.connect(self.on_node_selected)
        self.canvas.connection_created.connect(self.on_connection_created)
        self.canvas.execution_requested.connect(self.execute_algorithm_chain)
        self.canvas.status_update_callback = self.status_bar.setText
        middle_layout.addWidget(self.canvas)
        
        self.main_splitter.addWidget(middle_widget)
        
        # 右侧：参数配置
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        param_label = QLabel("参数配置:")
        right_layout.addWidget(param_label)
        
        # 参数配置组件 - 使用类型感知的参数控件
        self.parameter_widget = TypeAwareParameterWidget()
        self.parameter_widget.parameter_changed.connect(self.on_parameter_changed)
        right_layout.addWidget(self.parameter_widget)
        
        # 中间结果显示区域
        result_group = QGroupBox("中间结果")
        result_layout = QVBoxLayout()
        
        self.result_combo = QComboBox()
        self.result_combo.currentTextChanged.connect(self.on_result_selected)
        result_layout.addWidget(self.result_combo)
        
        result_group.setLayout(result_layout)
        right_layout.addWidget(result_group)
        
        right_layout.addStretch()
        
        self.main_splitter.addWidget(right_widget)
        
        # 设置分割器比例
        self.main_splitter.setSizes([200, 700, 300])
        
        # 初始化画布
        self.init_canvas()
        
        # 加载算法库
        self.load_algorithm_library()

        # 加载窗口设置
        self.load_settings()
        
    def init_canvas(self):
        """初始化画布"""
        # 添加输入图像节点
        input_node = self.canvas.add_image_node("input", 50, 200)
        
        # 添加输出图像节点
        output_node = self.canvas.add_image_node("output", 50, 350)
        
        # 如果有现有算法链，添加到画布
        if self.algorithm_chain:
            x, y = 250, 200
            for algorithm in self.algorithm_chain:
                node = self.canvas.add_algorithm_node(algorithm, x, y)
                x += 200
                if x > 800:
                    x = 250
                    y += 150
    
    def init_config_cache(self):
        """初始化配置缓存机制"""
        import os
        import tempfile
        from datetime import datetime

        try:
            # 使用AppConfigManager获取canvas_temp目录
            from core.managers.app_config import AppConfigManager
            app_config = AppConfigManager()
            temp_dir = app_config.canvas_temp_dir
        except Exception:
            # fallback到workspace/canvas_temp
            temp_dir = Path("workspace") / "canvas_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一的缓存文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.cache_file_path = temp_dir / f"canvas_config_{timestamp}.json"
        
        debug(f"初始化配置缓存，缓存文件: {self.cache_file_path}", "CHAIN")
    
    def save_config_to_cache(self):
        """实时保存配置到缓存文件"""
        if not self.cache_file_path:
            return
        
        try:
            # 构建算法执行顺序
            execution_order = self.build_execution_order()
            if not execution_order:
                # 如果没有算法，保存空配置
                chain_config = ChainConfig(
                    canvas_layout=True,
                    created_at=QDateTime.currentDateTime().toString()
                )
            else:
                # 创建链配置对象
                chain_config = ChainConfig(
                    canvas_layout=True,
                    created_at=QDateTime.currentDateTime().toString()
                )
                
                # 为每个算法创建配置
                for algorithm_node in execution_order:
                    algorithm = algorithm_node.algorithm
                    
                    # 优先使用节点存储的配置（包含嵌套结构），如果没有则创建新配置
                    if hasattr(algorithm_node, 'config') and algorithm_node.config:
                        algorithm_config = algorithm_node.config
                        # 更新算法当前参数值到配置中（同步当前状态）
                        current_params = algorithm.get_all_parameters()
                        for param_config in algorithm_config.parameters:
                            if param_config.name in current_params:
                                param_config.value = current_params[param_config.name]
                    else:
                        # 从算法实例创建配置
                        algorithm_config = AlgorithmConfig.from_algorithm_base(algorithm)
                        algorithm_node.config = algorithm_config
                    
                    # 添加/更新布局信息
                    node_pos = algorithm_node.scenePos()
                    algorithm_config.layout = {
                        "position": {
                            "x": float(node_pos.x()),
                            "y": float(node_pos.y())
                        },
                        "node_id": algorithm_node.node_id
                    }
                    
                    chain_config.algorithms.append(algorithm_config)
                
                # 保存连接信息
                for connection in self.canvas.connections:
                    start_node = connection.start_item
                    end_node = connection.end_item
                    
                    if isinstance(start_node, AlgorithmNode) and isinstance(end_node, AlgorithmNode):
                        connection_config = ConnectionConfig(
                            from_algorithm=start_node.node_id,
                            to_algorithm=end_node.node_id,
                            from_port=getattr(connection, 'start_port', 'right'),
                            to_port=getattr(connection, 'end_port', 'left')
                        )
                        chain_config.connections.append(connection_config)
            
            # 保存到缓存文件
            chain_config.save_to_file(str(self.cache_file_path))
            debug(f"配置已保存到缓存文件: {self.cache_file_path}", "CHAIN")
            
        except Exception as e:
            debug(f"保存配置到缓存失败: {str(e)}", "CHAIN")
    
    def load_config_from_cache(self, safe_loading=True) -> bool:
        """从缓存文件加载配置

        Args:
            safe_loading: 如果为True，加载失败时不会清空画布
        """
        if not self.cache_file_path or not self.cache_file_path.exists():
            debug(f"缓存文件不存在: {self.cache_file_path}", "CANVAS_LOADING", LogCategory.SOFTWARE)
            return False

        try:
            debug(f"开始加载缓存配置: {self.cache_file_path}", "CANVAS_LOADING", LogCategory.SOFTWARE)

            # 从缓存文件加载配置
            chain_config = ChainConfig.load_from_file(str(self.cache_file_path))
            if not chain_config:
                error(f"ChainConfig.load_from_file返回None", "CANVAS_LOADING", LogCategory.SOFTWARE)
                return False

            if not chain_config.algorithms:
                error(f"链配置中没有算法: {chain_config}", "CANVAS_LOADING", LogCategory.SOFTWARE)
                return False

            info(f"成功加载配置，包含{len(chain_config.algorithms)}个算法", "CANVAS_LOADING", LogCategory.SOFTWARE)
            
            # 保存当前的输入图像数据（在清空前）
            saved_input_image = None
            current_input_node = self.canvas.nodes.get("input_image")
            if current_input_node and current_input_node.image_data is not None:
                saved_input_image = current_input_node.image_data.copy()
                debug(f"已保存当前输入图像数据，尺寸: {saved_input_image.shape}", "CANVAS_LOADING", LogCategory.SOFTWARE)
            
            # 如果不是安全模式，清空画布并重建所有节点
            if not safe_loading:
                # 清空当前画布
                self.canvas.clear_canvas()
                
                # 重新创建输入和输出图像节点
                input_node = self.canvas.add_image_node("input", 50, 200)
                output_node = self.canvas.add_image_node("output", 50, 350)
                
                # 恢复输入图像数据
                if saved_input_image is not None:
                    input_node.set_image(saved_input_image)
                    debug(f"已恢复输入图像数据到重建的输入节点", "CANVAS_LOADING", LogCategory.SOFTWARE)
            else:
                # 安全模式：只更新现有节点，不清空画布
                input_node = self.canvas.nodes.get("input_image")
                output_node = self.canvas.nodes.get("output_image")
                
                # 检查必要的节点是否存在
                if not input_node or not output_node:
                    error(f"安全模式：必要的输入/输出节点不存在", "CANVAS_LOADING", LogCategory.SOFTWARE)
                    return False
            
            # 如果是安全模式，只同步参数，不重建节点
            if safe_loading:
                # 安全模式：只更新现有算法节点的参数，不重建整个画布
                debug(f"进入安全模式，开始更新{len(chain_config.algorithms)}个算法节点的参数", "CANVAS_LOADING", LogCategory.SOFTWARE)
                for algo_config in chain_config.algorithms:
                    debug(f"处理算法配置: {algo_config.algorithm_id} - {algo_config.display_name}", "CANVAS_LOADING", LogCategory.SOFTWARE)
                    # 查找对应的现有节点
                    existing_node = self.canvas.nodes.get(algo_config.instance_id)
                    if existing_node and hasattr(existing_node, 'algorithm'):
                        try:
                            # 应用配置到现有算法
                            algo_config.apply_to_algorithm(existing_node.algorithm)
                            debug(f"安全模式：已更新节点 {algo_config.instance_id} 的参数", "CANVAS_LOADING", LogCategory.SOFTWARE)
                        except Exception as e:
                            error(f"安全模式：更新节点 {algo_config.instance_id} 参数失败: {str(e)}", "CANVAS_LOADING", LogCategory.SOFTWARE)
                    else:
                        warning(f"安全模式：未找到节点 {algo_config.instance_id}，跳过参数更新", "CANVAS_LOADING", LogCategory.SOFTWARE)
                return True
            
            # 非安全模式：重建算法节点
            for algo_config in chain_config.algorithms:
                # 创建算法实例
                registry = self.algorithm_manager.get_registry()
                algorithm = registry.create_algorithm_instance(algo_config.algorithm_id)
                if algorithm:
                    # 如果是组合算法，设置algorithm_manager引用
                    if hasattr(algorithm, 'algorithm_manager'):
                        algorithm.algorithm_manager = self.algorithm_manager
                        debug(f"为组合算法 {algo_config.display_name} 设置algorithm_manager", "CHAIN")
                    
                    # 应用配置到算法
                    algo_config.apply_to_algorithm(algorithm)
                    
                    # 获取布局信息
                    layout = algo_config.layout or {}
                    position = layout.get("position", {"x": 100, "y": 100})
                    node_id = layout.get("node_id", f"node_{algo_config.algorithm_id}")
                    
                    # 创建算法节点
                    algorithm_node = AlgorithmNode(
                        algorithm=algorithm,
                        x=position["x"],
                        y=position["y"],
                        node_id=node_id,
                        canvas=self.canvas
                    )
                    
                    # 存储算法配置到节点（包含嵌套结构）
                    algorithm_node.config = algo_config
                    
                    self.canvas.add_node(algorithm_node)
                    debug(f"从缓存恢复算法节点: {algo_config.display_name}", "CHAIN")
            
            # 只有在非安全模式下才重建连接
            if not safe_loading:
                # 重建连接
                for conn_config in chain_config.connections:
                    start_node = self.canvas.nodes.get(conn_config.from_algorithm)
                    end_node = self.canvas.nodes.get(conn_config.to_algorithm)
                    
                    if start_node and end_node:
                        connection = ConnectionLine(
                            start_item=start_node,
                            end_item=end_node,
                            start_port=conn_config.from_port,
                            end_port=conn_config.to_port
                        )
                        self.canvas.add_connection(connection)
                        debug(f"从缓存恢复连接: {conn_config.from_algorithm} -> {conn_config.to_algorithm}", "CHAIN")
            
            return True
            
        except Exception as e:
            debug(f"从缓存文件加载配置失败: {str(e)}", "CHAIN")
            return False
    
    def move_cache_to_saved_path(self, target_path: str):
        """将缓存配置移动到指定保存路径"""
        if not self.cache_file_path or not self.cache_file_path.exists():
            return False
        
        try:
            import shutil
            
            # 确保目标目录存在
            target_path = Path(target_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 移动文件
            shutil.move(str(self.cache_file_path), str(target_path))
            debug(f"缓存配置已移动到: {target_path}", "CHAIN")
            
            # 更新缓存文件路径为新的路径（以便后续继续缓存）
            self.cache_file_path = target_path
            
            return True
            
        except Exception as e:
            debug(f"移动缓存配置失败: {str(e)}", "CHAIN")
            return False
    
    def _load_basic_algorithms(self):
        """加载基础算法"""
        try:
            # 导入算法模块
            from algorithms import basic, advanced, performance
            from core.interfaces.algorithm.base import AlgorithmBase
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
                        
            info(f"对话框初始化: 成功加载 {loaded_count} 个算法", "CANVAS_DIALOG", LogCategory.SOFTWARE)
            
        except Exception as e:
            error(f"对话框初始化: 加载算法失败: {e}", "CANVAS_DIALOG", LogCategory.SOFTWARE)
    
    def load_algorithm_library(self):
        """加载算法库"""
        if not self.algorithm_manager:
            return
            
        # 获取算法注册表
        registry = self.algorithm_manager.get_registry()
        
        # 注册组合算法到注册表
        self.register_combined_algorithms(registry)
        
        self.algorithm_category_widget.set_registry(registry)
    
    def register_combined_algorithms(self, registry):
        """注册组合算法到算法注册表"""
        try:
            # 获取所有组合算法
            combined_algorithms = self.combined_algorithm_manager.get_all_combined_algorithms()
            
            for algorithm_id, chain_config in combined_algorithms.items():
                # 获取算法信息
                algorithm_info = self.combined_algorithm_manager.get_algorithm_info(algorithm_id)
                if algorithm_info:
                    # 创建工厂函数
                    factory = self.combined_algorithm_manager.create_algorithm_factory(algorithm_id)
                    
                    # 注册到算法注册表
                    registry.register_algorithm_class(
                        algorithm_id, 
                        factory, 
                        algorithm_info
                    )
                    
                    self.status_bar.setText(f"已加载组合算法: {algorithm_info.display_name}")
                    
        except Exception as e:
            self.status_bar.setText(f"加载组合算法失败: {str(e)}")
    
    def on_algorithm_dropped_from_library(self, algorithm_id: str, position):
        """处理从算法库拖拽的算法"""
        # 在画布中心添加算法节点
        scene_pos = self.canvas.mapToScene(position)
        self.on_algorithm_dropped_to_canvas(algorithm_id, scene_pos.x(), scene_pos.y())
    
    def on_algorithm_dropped_to_canvas(self, algorithm_id: str, x: float, y: float):
        """处理拖拽到画布的算法"""
        try:
            if not self.algorithm_manager:
                self.status_bar.setText("算法管理器未初始化")
                return
                
            registry = self.algorithm_manager.get_registry()
            algorithm = registry.create_algorithm_instance(algorithm_id)
            
            if algorithm:
                node = self.canvas.add_algorithm_node(algorithm, x, y)
                self.status_bar.setText(f"已添加算法: {algorithm.get_info().display_name}")
                
                # 提供连线提示
                self.provide_connection_hints(node)
                
                # 检查是否为第一次拖拽操作
                if self.first_drag_operation:
                    self.first_drag_operation = False
                    debug(f"检测到第一次拖拽操作，初始化配置缓存", "CHAIN")
                    # 保存初始配置到缓存
                    self.save_config_to_cache()
                
                # 注释掉这里的立即保存，因为位置变化会通过防抖机制自动保存
                # self.save_config_to_cache()
            else:
                self.status_bar.setText(f"无法创建算法实例: {algorithm_id}")
                
        except Exception as e:
            self.status_bar.setText(f"添加算法失败: {str(e)}")
            debug(f"添加算法失败: {str(e)}", "CHAIN")
            import traceback
            traceback.print_exc()
    
    def provide_connection_hints(self, new_node):
        """为新增的算法节点提供连线提示"""
        try:
            # 统计当前节点和连线数量
            algorithm_nodes = [node for node in self.canvas.nodes.values() if isinstance(node, AlgorithmNode)]
            total_connections = len(self.canvas.connections)
            
            # 如果这是第一个算法节点
            if len(algorithm_nodes) == 1:
                self.status_bar.setText("💡 提示：请从输入图像节点拖拽连线到此算法的左侧端口")
                debug(f"第一个算法节点添加，提示输入连线", "CHAIN")
                return
            
            # 如果有算法节点但没有连线
            if total_connections == 0 and len(algorithm_nodes) > 1:
                self.status_bar.setText("💡 提示：请创建连线来连接算法。从输入图像→算法1→算法2→...→输出图像")
                debug(f"有算法但无连线，提示创建连接", "CHAIN")
                return
            
            # 检查是否有输入连接
            has_input_connection = any(
                conn.end_item == new_node 
                for conn in self.canvas.connections
                if isinstance(conn.start_item, ImageNode) and conn.start_item.node_type == "input"
            )
            
            # 检查是否有输出连接
            has_output_connection = any(
                conn.start_item == new_node 
                for conn in self.canvas.connections
                if isinstance(conn.end_item, ImageNode) and conn.end_item.node_type == "output"
            )
            
            # 提供针对性的提示
            if not has_input_connection:
                self.status_bar.setText(f"💡 提示：请从输入节点或其他算法的输出端口连线到 {new_node.algorithm.get_info().display_name}")
            elif not has_output_connection:
                self.status_bar.setText(f"💡 提示：请从 {new_node.algorithm.get_info().display_name} 的输出端口连线到下一个算法或输出节点")
            else:
                self.status_bar.setText(f"✅ {new_node.algorithm.get_info().display_name} 连线完整")
                
        except Exception as e:
            debug(f"提供连线提示失败: {e}", "CHAIN")
    
    def on_node_selected(self, node):
        """节点选择事件"""
        if isinstance(node, AlgorithmNode):
            self.current_algorithm = node.algorithm
            self.parameter_widget.set_algorithm(node.algorithm)
            # 显示算法信息
            info = node.algorithm.get_info()
            self.setWindowTitle(f'算法链调试 - 当前选中: {info.display_name}')
        elif isinstance(node, ImageNode):
            self.current_algorithm = None
            self.parameter_widget.set_algorithm(None)
            # 显示图像节点信息
            if node.image_data is not None:
                self.show_image_info_in_params_for_node(node)
            # 恢复窗口标题
            self.setWindowTitle('算法链调试')
    
    def on_node_double_clicked(self, node):
        """处理节点双击事件 - 显示执行结果"""
        if isinstance(node, AlgorithmNode):
            if hasattr(node, 'execution_result') and node.execution_result:
                if node.execution_result.success and node.execution_result.output_image is not None:
                    # 显示执行结果
                    from .image_dialog import ImageDisplayDialog
                    dialog = ImageDisplayDialog(
                        node.execution_result.output_image, 
                        f"执行结果 - {node.algorithm.get_info().display_name}", 
                        self
                    )
                    dialog.exec()
                else:
                    self.status_bar.setText(f"算法 {node.algorithm.get_info().display_name} 执行失败: {node.execution_result.error_message}")
            else:
                self.status_bar.setText(f"算法 {node.algorithm.get_info().display_name} 尚未执行")
    
    def show_image_info_in_params_for_node(self, image_node):
        """在参数区域显示图像节点的信息 - 支持多张图片"""
        # 清空参数区域
        self.parameter_widget.clear_parameters()

        if image_node.image_data is not None:
            if isinstance(image_node.image_data, list):
                # 多张图片模式
                self._show_multiple_images_info(image_node)
            else:
                # 单张图片模式
                self._show_single_image_info(image_node)
        else:
            # 没有图像时显示图形生成选项
            self.show_image_generation_options(image_node)

    def _show_single_image_info(self, image_node):
        """显示单张图片信息"""
        # 获取图像信息
        height, width = image_node.image_data.shape[:2]
        channels = image_node.image_data.shape[2] if len(image_node.image_data.shape) == 3 else 1
        dtype = str(image_node.image_data.dtype)
        file_path = getattr(image_node, 'file_path', '未知路径')

        # 创建图像信息标签
        info_label = QLabel()
        info_text = f"""
        <h3>图像信息</h3>
        <p><b>文件路径:</b> {file_path}</p>
        <p><b>尺寸:</b> {width} × {height}</p>
        <p><b>通道数:</b> {channels}</p>
        <p><b>数据类型:</b> {dtype}</p>
        <p><b>文件大小:</b> {getattr(image_node, 'file_size', '未知')}</p>
        """
        info_label.setText(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("QLabel { padding: 10px; background-color: #f0f0f0; border-radius: 5px; }")

        # 创建查看图片按钮
        view_image_btn = QPushButton("🖼️ 查看图片")
        view_image_btn.clicked.connect(lambda: image_node.show_image())
        view_image_btn.setStyleSheet("QPushButton { padding: 8px; background-color: #0078d4; color: white; border-radius: 3px; }")
        view_image_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # 创建信息组
        info_group = QGroupBox("图像信息")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(info_label)
        info_layout.addWidget(view_image_btn)

        # 添加到参数区域的内容布局
        self.parameter_widget.content_layout.addWidget(info_group)

    def _show_multiple_images_info(self, image_node):
        """显示多张图片信息"""
        image_count = len(image_node.image_data)
        if image_count == 0:
            return

        # 获取文件路径信息
        file_paths = getattr(image_node, 'file_paths', [])
        if file_paths and len(file_paths) >= image_count:
            path_info = file_paths[0] if image_count == 1 else f"{len(file_paths)}个文件"
        else:
            path_info = "未知路径"

        # 计算总内存占用
        total_size = sum(img.nbytes for img in image_node.image_data)

        # 创建概览信息标签
        overview_label = QLabel()
        overview_text = f"""
        <h3>所有图片概览</h3>
        <p><b>图片数量:</b> {image_count} 张</p>
        <p><b>文件路径:</b> {path_info}</p>
        <p><b>总内存占用:</b> {total_size / 1024:.1f} KB ({total_size / 1024 / 1024:.1f} MB)</p>
        """
        overview_label.setText(overview_text)
        overview_label.setWordWrap(True)
        overview_label.setStyleSheet("QLabel { padding: 10px; background-color: #e8f4fd; border-radius: 5px; }")

        # 创建查看所有图片按钮
        view_all_btn = QPushButton("🖼️ 查看所有图片")
        view_all_btn.clicked.connect(lambda: image_node.show_image())
        view_all_btn.setStyleSheet("QPushButton { padding: 8px; background-color: #0078d4; color: white; border-radius: 3px; }")
        view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # 创建信息组
        overview_group = QGroupBox("多张图片信息")
        overview_layout = QVBoxLayout(overview_group)
        overview_layout.addWidget(overview_label)
        overview_layout.addWidget(view_all_btn)

        # 添加到参数区域的内容布局
        self.parameter_widget.content_layout.addWidget(overview_group)

        # 显示前3张图片的详细信息
        detail_group = QGroupBox("前3张图片详情")
        detail_layout = QVBoxLayout(detail_group)

        for i in range(min(3, image_count)):
            img = image_node.image_data[i]
            height, width = img.shape[:2]  # 只获取高度和宽度，不包含通道数
            channels = img.shape[2] if len(img.shape) == 3 else 1
            dtype = str(img.dtype)
            size_kb = img.nbytes / 1024

            # 获取单个文件路径
            single_file_path = file_paths[i] if file_paths and i < len(file_paths) else f"图片_{i+1}"

            # 创建单个图片信息
            img_info = QLabel()
            img_text = f"""
            <h4>图片 {i + 1}</h4>
            <p><b>文件路径:</b> {single_file_path}</p>
            <p><b>尺寸:</b> {width} × {height}</p>
            <p><b>通道数:</b> {channels}</p>
            <p><b>数据类型:</b> {dtype}</p>
            <p><b>文件大小:</b> {size_kb:.1f} KB</p>
            """
            img_info.setText(img_text)
            img_info.setWordWrap(True)
            img_info.setStyleSheet("QLabel { padding: 8px; background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 3px; margin: 2px; }")

            # 添加查看单张图片按钮
            view_single_btn = QPushButton(f"📷 查看图片 {i + 1}")
            view_single_btn.clicked.connect(lambda checked, idx=i: self._view_single_image(image_node, idx))
            view_single_btn.setStyleSheet("QPushButton { padding: 4px; background-color: #28a745; color: white; border-radius: 3px; font-size: 11px; }")
            view_single_btn.setCursor(Qt.CursorShape.PointingHandCursor)

            # 创建子布局
            img_layout = QVBoxLayout()
            img_layout.addWidget(img_info)
            img_layout.addWidget(view_single_btn)

            detail_layout.addLayout(img_layout)

        # 添加到参数区域的内容布局
        self.parameter_widget.content_layout.addWidget(detail_group)

        # 如果图片超过3张，添加更多图片提示
        if image_count > 3:
            more_label = QLabel(f"... 还有 {image_count - 3} 张图片，点击'查看所有图片'浏览完整列表")
            more_label.setStyleSheet("QLabel { padding: 8px; background-color: #fff3cd; border-radius: 3px; font-style: italic; }")
            self.parameter_widget.content_layout.addWidget(more_label)

    def _view_single_image(self, image_node, index: int):
        """查看单张图片"""
        try:
            from .image_dialog import ImageDisplayDialog

            if isinstance(image_node.image_data, list) and 0 <= index < len(image_node.image_data):
                # 创建标题，包含图片索引信息
                total_images = len(image_node.image_data)
                title = f"图片预览 - {index + 1}/{total_images}"

                # 使用统一的图片预览对话框，从指定索引开始
                dialog = ImageDisplayDialog(image_node.image_data, title, self)
                dialog.current_index = index
                dialog.load_current_image()
                dialog.exec()

        except Exception as e:
            error(f"查看单张图片时出错: {str(e)}", "CANVAS_DIALOG", LogCategory.SOFTWARE)
    
    def show_image_generation_options(self, image_node):
        """在参数区域显示图形生成选项"""
        # 创建说明标签
        desc_label = QLabel()
        desc_text = """
        <h3>🎨 图像生成选项</h3>
        <p>当前没有加载图像，您可以选择生成测试图像来调试算法：</p>
        """
        desc_label.setText(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("QLabel { padding: 10px; background-color: #e3f2fd; border-radius: 5px; }")

        # 创建生成选项组
        generation_group = QGroupBox("测试图像生成")
        generation_layout = QVBoxLayout()

        # 基础几何图形
        basic_group = QGroupBox("基础几何图形")
        basic_layout = QVBoxLayout()

        # 创建按钮样式
        button_style = """
            QPushButton {
                padding: 8px;
                background-color: #2196f3;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
        """

        # 几何图形按钮
        solid_color_btn = QPushButton("🎨 纯色图像")
        solid_color_btn.setStyleSheet(button_style)
        solid_color_btn.clicked.connect(lambda: self.generate_solid_color_image(image_node))

        checkerboard_btn = QPushButton("♟️ 棋盘格")
        checkerboard_btn.setStyleSheet(button_style)
        checkerboard_btn.clicked.connect(lambda: self.generate_checkerboard_image(image_node))

        circles_btn = QPushButton("⭕ 圆形图案")
        circles_btn.setStyleSheet(button_style)
        circles_btn.clicked.connect(lambda: self.generate_circles_image(image_node))

        rectangles_btn = QPushButton("⬜ 矩形图案")
        rectangles_btn.setStyleSheet(button_style)
        rectangles_btn.clicked.connect(lambda: self.generate_rectangles_image(image_node))

        lines_btn = QPushButton("📏 直线图案")
        lines_btn.setStyleSheet(button_style)
        lines_btn.clicked.connect(lambda: self.generate_lines_image(image_node))

        # 添加基础几何图形按钮
        basic_layout.addWidget(solid_color_btn)
        basic_layout.addWidget(checkerboard_btn)
        basic_layout.addWidget(circles_btn)
        basic_layout.addWidget(rectangles_btn)
        basic_layout.addWidget(lines_btn)
        basic_group.setLayout(basic_layout)

        # 视觉测试图形
        test_group = QGroupBox("视觉测试图形")
        test_layout = QVBoxLayout()

        gradient_btn = QPushButton("🌈 渐变图像")
        gradient_btn.setStyleSheet(button_style)
        gradient_btn.clicked.connect(lambda: self.generate_gradient_image(image_node))

        noise_btn = QPushButton("📺 噪声图像")
        noise_btn.setStyleSheet(button_style)
        noise_btn.clicked.connect(lambda: self.generate_noise_image(image_node))

        grid_btn = QPushButton("📊 网格图像")
        grid_btn.setStyleSheet(button_style)
        grid_btn.clicked.connect(lambda: self.generate_grid_image(image_node))

        text_btn = QPushButton("📝 文字图像")
        text_btn.setStyleSheet(button_style)
        text_btn.clicked.connect(lambda: self.generate_text_image(image_node))

        # 添加视觉测试图形按钮
        test_layout.addWidget(gradient_btn)
        test_layout.addWidget(noise_btn)
        test_layout.addWidget(grid_btn)
        test_layout.addWidget(text_btn)
        test_group.setLayout(test_layout)

        # 组合布局
        generation_layout.addWidget(desc_label)
        generation_layout.addWidget(basic_group)
        generation_layout.addWidget(test_group)

        # 添加文件加载选项
        file_group = QGroupBox("从文件加载")
        file_layout = QVBoxLayout()

        load_file_btn = QPushButton("📁 选择图像文件")
        load_file_btn.setStyleSheet("""
            QPushButton {
                padding: 10px;
                background-color: #4caf50;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        load_file_btn.clicked.connect(lambda: self.load_image_for_node(image_node))
        file_layout.addWidget(load_file_btn)
        file_group.setLayout(file_layout)

        generation_layout.addWidget(file_group)
        generation_group.setLayout(generation_layout)

        # 添加到参数区域
        self.parameter_widget.content_layout.addWidget(generation_group)

    # 图像生成方法
    def generate_solid_color_image(self, image_node):
        """生成纯色图像"""
        try:
            import numpy as np
            image = np.full((480, 640, 3), [128, 128, 128], dtype=np.uint8)  # 灰色
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成纯色测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成纯色图像失败: {str(e)}")

    def generate_checkerboard_image(self, image_node):
        """生成棋盘格图像"""
        try:
            import numpy as np
            height, width = 480, 640
            square_size = 40
            image = np.zeros((height, width, 3), dtype=np.uint8)
            for y in range(0, height, square_size):
                for x in range(0, width, square_size):
                    if ((x // square_size) + (y // square_size)) % 2 == 0:
                        image[y:y+square_size, x:x+square_size] = [255, 255, 255]
                    else:
                        image[y:y+square_size, x:x+square_size] = [0, 0, 0]
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成棋盘格测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成棋盘格图像失败: {str(e)}")

    def generate_circles_image(self, image_node):
        """生成圆形图案图像"""
        try:
            import numpy as np
            import cv2
            height, width = 480, 640
            image = np.full((height, width, 3), [240, 240, 240], dtype=np.uint8)
            center_x, center_y = width // 2, height // 2
            cv2.circle(image, (center_x, center_y), 100, (255, 0, 0), -1)
            cv2.circle(image, (center_x - 120, center_y), 60, (0, 255, 0), -1)
            cv2.circle(image, (center_x + 120, center_y), 60, (0, 0, 255), -1)
            cv2.circle(image, (center_x, center_y - 80), 30, (255, 255, 0), -1)
            cv2.circle(image, (center_x, center_y + 80), 30, (255, 0, 255), -1)
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成圆形图案测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成圆形图像失败: {str(e)}")

    def generate_rectangles_image(self, image_node):
        """生成矩形图案图像"""
        try:
            import numpy as np
            import cv2
            height, width = 480, 640
            image = np.full((height, width, 3), [220, 220, 220], dtype=np.uint8)
            cv2.rectangle(image, (50, 50), (200, 150), (255, 0, 0), -1)
            cv2.rectangle(image, (250, 80), (400, 180), (0, 255, 0), -1)
            cv2.rectangle(image, (450, 50), (590, 150), (0, 0, 255), -1)
            cv2.rectangle(image, (100, 250), (300, 380), (255, 255, 0), -1)
            cv2.rectangle(image, (350, 280), (550, 400), (255, 0, 255), -1)
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成矩形图案测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成矩形图像失败: {str(e)}")

    def generate_lines_image(self, image_node):
        """生成直线图案图像"""
        try:
            import numpy as np
            import cv2
            height, width = 480, 640
            image = np.full((height, width, 3), [250, 250, 250], dtype=np.uint8)
            cv2.line(image, (50, 100), (590, 100), (255, 0, 0), 3)
            cv2.line(image, (50, 200), (590, 200), (0, 255, 0), 3)
            cv2.line(image, (50, 300), (590, 300), (0, 0, 255), 3)
            cv2.line(image, (50, 400), (590, 400), (255, 255, 0), 3)
            cv2.line(image, (150, 50), (150, 430), (255, 0, 255), 3)
            cv2.line(image, (320, 50), (320, 430), (0, 255, 255), 3)
            cv2.line(image, (490, 50), (490, 430), (128, 128, 128), 3)
            cv2.line(image, (50, 50), (590, 430), (255, 165, 0), 2)
            cv2.line(image, (590, 50), (50, 430), (128, 0, 128), 2)
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成直线图案测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成直线图像失败: {str(e)}")

    def generate_gradient_image(self, image_node):
        """生成渐变图像"""
        try:
            import numpy as np
            height, width = 480, 640
            image = np.zeros((height, width, 3), dtype=np.uint8)
            for x in range(width):
                ratio = x / width
                image[:, x] = [int(255 * (1 - ratio)), int(255 * ratio), 128]
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成渐变测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成渐变图像失败: {str(e)}")

    def generate_noise_image(self, image_node):
        """生成噪声图像"""
        try:
            import numpy as np
            height, width = 480, 640
            image = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成随机噪声测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成噪声图像失败: {str(e)}")

    def generate_grid_image(self, image_node):
        """生成网格图像"""
        try:
            import numpy as np
            import cv2
            height, width = 480, 640
            image = np.full((height, width, 3), [255, 255, 255], dtype=np.uint8)
            grid_size = 40
            line_color = [0, 0, 0]
            for x in range(0, width, grid_size):
                cv2.line(image, (x, 0), (x, height), line_color, 1)
            for y in range(0, height, grid_size):
                cv2.line(image, (0, y), (width, y), line_color, 1)
            cv2.line(image, (320, 0), (320, height), [255, 0, 0], 2)
            cv2.line(image, (0, 240), (width, 240), [0, 255, 0], 2)
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成网格测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成网格图像失败: {str(e)}")

    def generate_text_image(self, image_node):
        """生成文字图像"""
        try:
            import numpy as np
            import cv2
            height, width = 480, 640
            image = np.full((height, width, 3), [240, 240, 240], dtype=np.uint8)
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(image, "VISION TEST", (120, 80), font, 2, (0, 0, 255), 3)
            cv2.putText(image, "ALGORITHM DEBUG", (100, 130), font, 1.5, (0, 128, 0), 2)
            cv2.putText(image, "Test Image for Algorithm", (140, 200), font, 0.8, (0, 0, 0), 2)
            cv2.putText(image, "Development and Testing", (150, 230), font, 0.8, (0, 0, 0), 2)
            cv2.putText(image, f"Size: {width}x{height}", (200, 300), font, 0.7, (255, 0, 0), 2)
            cv2.putText(image, "Format: BGR", (230, 330), font, 0.7, (0, 0, 255), 2)
            cv2.putText(image, "Type: UINT8", (230, 360), font, 0.7, (0, 128, 0), 2)
            cv2.putText(image, "Click to generate other patterns", (120, 420), font, 0.6, (128, 128, 128), 1)
            image_node.image_data = image
            image_node.setBrush(QBrush(QColor(150, 200, 255)))
            self.status_bar.setText("已生成文字测试图像 (640x480)")
            self.show_image_info_in_params_for_node(image_node)
        except Exception as e:
            self.status_bar.setText(f"生成文字图像失败: {str(e)}")

    def load_image_for_node(self, image_node):
        """为指定节点加载图像文件 - 使用统一的工具函数"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            from utils.image_utils import load_image as utils_load_image

            file_path, _ = QFileDialog.getOpenFileName(
                self,
                '选择输入图像',
                '',
                '图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff)'
            )
            if file_path:
                # 使用统一的图像加载函数
                image = utils_load_image(file_path)
                if image is not None:
                    image_node.image_data = image
                    image_node.setBrush(QBrush(QColor(150, 200, 255)))
                    self.status_bar.setText(f"输入图像已加载: {file_path}")
                    self.show_image_info_in_params_for_node(image_node)
                else:
                    self.status_bar.setText("图像加载失败")
        except Exception as e:
            self.status_bar.setText(f"加载图像时出错: {str(e)}")

    def on_connection_created(self, start_item, end_item):
        """连接创建事件"""
        # 验证连接是否有效
        if (hasattr(start_item, 'get_output_pos') and hasattr(end_item, 'get_input_pos')) or \
           (hasattr(start_item, 'get_port_pos') and hasattr(end_item, 'get_input_pos')) or \
           (hasattr(start_item, 'get_output_pos') and hasattr(end_item, 'get_port_pos')):
            self.canvas.add_connection(start_item, end_item)
    
    def on_parameter_changed(self, param_name, value):
        """参数改变事件"""
        if self.current_algorithm:
            self.current_algorithm.set_parameter(param_name, value)
            
            # 如果是组合算法，需要更新嵌套配置
            if hasattr(self.current_algorithm, 'get_chain_config') and hasattr(self.current_algorithm, 'get_inner_algorithms'):
                # 解析层级化参数名：algorithm_id.inner_param_name
                algorithm_id, inner_param_name = None, None
                
                # 优先使用 . 分割（新的层级化命名）
                if '.' in param_name:
                    parts = param_name.split('.', 1)
                    if len(parts) == 2:
                        algorithm_id, inner_param_name = parts[0], parts[1]
                        debug(f"解析层级化参数名: {param_name} -> {algorithm_id}.{inner_param_name}", "CHAIN")
                # 兼容 _ 分割（旧的命名方式）
                elif '_' in param_name:
                    parts = param_name.split('_', 1)
                    if len(parts) == 2:
                        algorithm_id, inner_param_name = parts[0], parts[1]
                        debug(f"解析兼容参数名: {param_name} -> {algorithm_id}.{inner_param_name}", "CHAIN")
                
                # 如果解析出了算法ID和参数名，继续处理
                if algorithm_id and inner_param_name:
                    # 获取当前算法节点
                    current_node = None
                    for node_id, node in self.canvas.nodes.items():
                        if isinstance(node, AlgorithmNode) and node.algorithm == self.current_algorithm:
                            current_node = node
                            break
                    
                    if current_node and hasattr(current_node, 'config'):
                        # 获取当前组合算法的配置
                        combined_algo_config = current_node.config
                        
                        # 如果已经有嵌套配置，直接更新
                        if combined_algo_config.nested_chain_config:
                            updated = combined_algo_config.update_nested_parameter(algorithm_id, inner_param_name, value)
                            if updated:
                                debug(f"成功更新嵌套配置参数: {algorithm_id}.{inner_param_name} = {value}", "CHAIN")
                            else:
                                debug(f"未能更新嵌套配置参数: {algorithm_id}.{inner_param_name} = {value}", "CHAIN")
                                debug(f"可能的原因 - 找不到算法ID或参数名", "CHAIN")
                        else:
                            # 如果没有嵌套配置，从算法实例创建
                            chain_config = self.current_algorithm.get_chain_config()
                            if chain_config:
                                combined_algo_config.nested_chain_config = chain_config
                                updated = combined_algo_config.update_nested_parameter(algorithm_id, inner_param_name, value)
                                if updated:
                                    debug(f"创建并更新嵌套配置参数: {algorithm_id}.{inner_param_name} = {value}", "CHAIN")
                                else:
                                    debug(f"创建嵌套配置后未能更新参数: {algorithm_id}.{inner_param_name} = {value}", "CHAIN")
                            else:
                                debug(f"无法获取算法的链配置来创建嵌套结构", "CHAIN")
                    else:
                        debug(f"找到当前节点但没有config属性", "CHAIN")
                else:
                    debug(f"未能解析参数名: {param_name}", "CHAIN")
            
            # 实时保存配置到缓存
            self.save_config_to_cache()
    
    def on_roi_selection_requested(self, data):
        """处理ROI选择请求 - 兼容性方法"""
        # 新的类型感知控件已经内置了ROI处理功能
        # 这个方法保留用于兼容性
        pass
    
    def get_input_image_for_current_algorithm(self):
        """获取当前算法的输入图像"""
        # 查找当前算法节点
        current_algorithm_node = None
        for node in self.canvas.nodes.values():
            if isinstance(node, AlgorithmNode) and node.algorithm == self.current_algorithm:
                current_algorithm_node = node
                break
        
        if not current_algorithm_node:
            return None
        
        # 查找连接到该算法节点的输入连接
        for connection in self.canvas.connections:
            if connection.end_item == current_algorithm_node:
                if isinstance(connection.start_item, ImageNode):
                    return connection.start_item.image_data
                elif isinstance(connection.start_item, AlgorithmNode):
                    if connection.start_item.execution_result and connection.start_item.execution_result.output_image is not None:
                        return connection.start_item.execution_result.output_image
        
        # 如果没有找到连接，尝试从输入图像节点获取
        input_node = self.canvas.nodes.get("input_image")
        if input_node and input_node.image_data is not None:
            return input_node.image_data
        
        return None
    
    def on_roi_selected(self, x, y, width, height):
        """ROI选择完成事件"""
        if self.current_algorithm:
            # 验证ROI值的有效性
            if width <= 0 or height <= 0:
                debug(f"ROI值无效 - 跳过设置: ({x}, {y}, {width}, {height})", "CHAIN")
                return
                
            roi_info = {"x": x, "y": y, "width": width, "height": height}
            debug(f"准备设置ROI参数: {roi_info}", "CHAIN")
            
            # 设置算法的ROI参数
            params = self.current_algorithm.get_parameters()
            for param in params:
                if param.param_type.name == "ROI":
                    try:
                        self.current_algorithm.set_parameter(param.name, roi_info)
                        # 更新参数界面显示
                        self.parameter_widget.set_algorithm(self.current_algorithm)
                        self.status_bar.setText(f"ROI已设置到算法 {self.current_algorithm.get_info().display_name}")
                        debug(f"ROI参数设置成功: {roi_info}", "CHAIN")
                    except Exception as e:
                        debug(f"ROI参数设置失败: {e}", "CHAIN")
                    break
                else:
                    debug(f"跳过非ROI参数: {param.name} (类型: {param.param_type.name})", "CHAIN")
        else:
            debug(f"没有当前算法，无法设置ROI", "CHAIN")
    
    def on_result_selected(self, result_name: str):
        """结果选择事件"""
        debug(f"选择了结果: {result_name}", "CHAIN")
        if result_name == "选择中间结果...":
            return
        
        # 解析选中的结果
        parts = result_name.split(". ", 1)
        if len(parts) == 2:
            index = int(parts[0]) - 1
            debug(f"解析索引: {index}", "CHAIN")
            
            # 优先使用保存的执行顺序，确保与下拉框一致
            execution_order = getattr(self, 'current_execution_order', None)
            if not execution_order:
                execution_order = self.build_execution_order()
            
            debug(f"执行顺序长度: {len(execution_order)}", "CHAIN")
            
            if 0 <= index < len(execution_order):
                node = execution_order[index]
                debug(f"找到节点: {node.algorithm.get_info().display_name}", "CHAIN")
                debug(f"节点执行结果状态: {node.execution_result is not None}", "CHAIN")
                if node.execution_result:
                    debug(f"节点有执行结果，调用显示方法", "CHAIN")
                    # 使用统一的结果查看接口
                    self.canvas.show_algorithm_result(node)
                else:
                    debug(f"节点没有执行结果", "CHAIN")
                    # 尝试从画布节点中查找最新状态
                    node_id = getattr(node, 'node_id', None)
                    if node_id and node_id in self.canvas.nodes:
                        canvas_node = self.canvas.nodes[node_id]
                        if canvas_node.execution_result:
                            debug(f"从画布节点找到执行结果", "CHAIN")
                            self.canvas.show_algorithm_result(canvas_node)
            else:
                debug(f"索引超出范围", "CHAIN")
        else:
            debug(f"无法解析结果名称", "CHAIN")
    
    def execute_algorithm_chain(self):
        """执行算法链"""
        debug(f"execute_algorithm_chain 开始执行", "CHAIN")
        
        # 检测执行启动时的错误，用于控制节点动画（存储为实例变量）
        self.execution_error_state = {'has_error': False}
        
        # 强制从缓存文件加载配置（确保执行的是缓存中的配置）
        if self.cache_file_path and self.cache_file_path.exists():
            debug(f"强制从缓存文件加载配置: {self.cache_file_path}", "CHAIN")
            if self.load_config_from_cache(safe_loading=True):
                self.status_bar.setText("已从缓存配置加载算法链并同步界面")
            else:
                self.status_bar.setText("⚠️ 缓存配置加载失败，使用当前画布配置")
                warning("缓存配置加载失败，执行结果可能与界面显示不一致", "CHAIN")
                self.execution_error_state['has_error'] = True  # 设置错误标志，防止节点动画
        else:
            debug(f"缓存文件不存在，使用当前画布配置: {self.cache_file_path}", "CHAIN")
            self.status_bar.setText("⚠️ 无缓存文件，使用当前画布配置")
        
        # 保存当前界面状态到缓存（确保缓存是最新的）
        self.save_config_to_cache()
        
        # 获取输入图像
        input_node = self.canvas.nodes.get("input_image")
        debug(f"  输入节点存在: {input_node is not None}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
        if input_node:
            debug(f"  输入图像存在: {input_node.image_data is not None}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            if input_node.image_data is not None:
                if isinstance(input_node.image_data, list):
                    debug(f"  输入图片列表: {len(input_node.image_data)} 张图片", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                    for i, img in enumerate(input_node.image_data):
                        if isinstance(img, np.ndarray):
                            debug(f"    图片 {i}: {img.shape}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                        else:
                            debug(f"    图片 {i}: {type(img)} - {img}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                else:
                    debug(f"  输入图像尺寸: {input_node.image_data.shape}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)

        if not input_node or input_node.image_data is None:
            debug(f"输入图像检查失败，返回", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            self.status_bar.setText("请先设置输入图像")
            return
        
        # 构建算法执行顺序（基于同步后的界面）
        execution_order = self.build_execution_order()
        debug(f"  执行顺序长度: {len(execution_order) if execution_order else 0}", "CHAIN")
        if not execution_order:
            debug(f"执行顺序为空，返回", "CHAIN")
            # 检查是否有算法节点但没有连线
            algorithm_nodes = [node for node in self.canvas.nodes.values() if isinstance(node, AlgorithmNode)]
            if algorithm_nodes:
                self.status_bar.setText("⚠️ 检测到算法节点但未创建连线。请从输入图像节点连线到算法，再连线到输出节点。")
                debug(f"发现 {len(algorithm_nodes)} 个算法节点，但没有有效的连线", "CHAIN")
            else:
                self.status_bar.setText("⚠️ 未找到可执行的算法链。请先添加算法节点并创建连线。")
                debug(f"画布上没有算法节点", "CHAIN")
            return
        
        # 禁用执行按钮，防止重复执行
        self.execute_btn.setEnabled(False)
        self.execute_btn.setText("⏳ 执行中...")
        
        # 保存执行顺序和输入图像
        self.current_execution_order = execution_order
        self.current_input_image = input_node.image_data
        debug(f"  已保存执行顺序和输入图像", "CHAIN")
        
        # 使用统一的PipelineExecutor执行算法链
        debug(f"  调用统一的PipelineExecutor", "CHAIN")
        self.execute_with_unified_executor(execution_order, input_node.image_data)
        debug(f"  统一PipelineExecutor 调用完成", "CHAIN")
    
    def execute_with_unified_executor(self, execution_order: List[AlgorithmNode], input_image: np.ndarray):
        """使用统一的PipelineExecutor执行算法链"""
        try:
            debug(f"execute_with_unified_executor 开始执行", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            debug(f"  执行顺序包含 {len(execution_order)} 个算法", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            if isinstance(input_image, list):
                debug(f"  输入图片列表: {len(input_image)} 张图片", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            else:
                debug(f"  输入图像尺寸: {input_image.shape}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)

            # 设置执行回调函数
            def on_execution_started(total_algorithms):
                self.status_bar.setText(f"开始执行算法链，共 {total_algorithms} 个算法")
                QApplication.processEvents()

            def on_algorithm_started(current, total, algorithm_name):
                self.status_bar.setText(f"正在执行步骤 {current}/{total}: {algorithm_name}")
                QApplication.processEvents()
                # 设置对应节点为执行状态
                for node in execution_order:
                    if node.algorithm.get_info().display_name == algorithm_name:
                        node.set_executing(True)
                        break

            def on_algorithm_completed(current, total, algorithm_name, result):
                # 查找对应的节点并更新状态
                for node in execution_order:
                    if node.algorithm.get_info().display_name == algorithm_name:
                        node.set_executing(False)
                        # 只有在没有执行错误时才设置节点颜色（防止出错时动画布节点）
                        if not self.execution_error_state['has_error']:
                            node.set_execution_result(result.success)
                        node.execution_result = result

                        # 同时更新画布中的节点
                        if hasattr(node, 'node_id') and node.node_id in self.canvas.nodes:
                            canvas_node = self.canvas.nodes[node.node_id]
                            if not self.execution_error_state['has_error']:
                                canvas_node.set_execution_result(result.success)
                            canvas_node.execution_result = result

                        break

                # 更新中间结果下拉框
                self.update_result_combo(execution_order[:current])

            def on_execution_completed(success, execution_time):
                # 恢复执行按钮
                self.execute_btn.setEnabled(True)
                self.execute_btn.setText('▶️ 执行 (F5)')

                if success:
                    self.status_bar.setText(f"算法链执行完成，耗时 {execution_time:.2f}秒")
                    # 更新最终输出图像
                    output_node = self.canvas.nodes.get("output_image")
                    debug(f"检查输出图像: output_node={output_node is not None}, has_current_output={hasattr(self, 'current_output_image')}, current_output_image={getattr(self, 'current_output_image', None) is not None}", "CHAIN")
                    if output_node and hasattr(self, 'current_output_image') and self.current_output_image is not None:
                        output_node.set_image(self.current_output_image)
                        # Force immediate visual update of the output node
                        output_node.update()
                        # Also force canvas update to ensure the node is redrawn
                        self.canvas.update()
                        debug(f"已设置输出图像数据并强制刷新视觉，尺寸: {self.current_output_image.shape}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                    else:
                        # 尝试从最后一个算法节点获取结果
                        if execution_order and len(execution_order) > 0:
                            last_node = execution_order[-1]
                            debug(f"尝试从最后一个算法节点获取输出: {last_node.algorithm.get_info().display_name}", "CHAIN")
                            if (hasattr(last_node, 'execution_result') and
                                last_node.execution_result and
                                last_node.execution_result.success and
                                last_node.execution_result.output_image is not None):
                                output_node.set_image(last_node.execution_result.output_image)
                                # Force immediate visual update of the output node
                                output_node.update()
                                # Also force canvas update to ensure the node is redrawn
                                self.canvas.update()
                                debug(f"从最后一个算法节点设置输出图像并强制刷新视觉，尺寸: {last_node.execution_result.output_image.shape}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                            else:
                                debug(f"最后一个算法节点也没有输出图像", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                        else:
                            debug(f"没有找到执行顺序或执行顺序为空", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
                else:
                    self.status_bar.setText("算法链执行失败")

                QApplication.processEvents()

  
            # 添加回调函数
            self.pipeline_executor.add_execution_callback('execution_started', on_execution_started)
            self.pipeline_executor.add_execution_callback('algorithm_started', on_algorithm_started)
            self.pipeline_executor.add_execution_callback('algorithm_completed', on_algorithm_completed)
            self.pipeline_executor.add_execution_callback('execution_completed', on_execution_completed)

            # 构建算法实例列表
            algorithm_list = []
            for node in execution_order:
                algorithm_list.append(node.algorithm)

            # 执行算法链
            execution_result = self.pipeline_executor.execute_algorithm_chain(
                algorithm_list,
                input_image,
                cache_config_path=str(self.cache_file_path) if self.cache_file_path else None
            )

            # 保存执行结果
            self.current_execution_order = execution_order
            self.current_output_image = execution_result.final_image

            debug(f"execute_with_unified_executor 执行完成", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            debug(f"  执行成功: {execution_result.success}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            debug(f"  执行时间: {execution_result.execution_time:.2f}秒", "CHAIN_EXECUTION", LogCategory.SOFTWARE)

        except Exception as e:
            debug(f"execute_with_unified_executor 执行失败: {e}", "CHAIN_EXECUTION", LogCategory.SOFTWARE)
            self.status_bar.setText(f"算法链执行失败: {str(e)}")

            # 恢复执行按钮
            self.execute_btn.setEnabled(True)
            self.execute_btn.setText('▶️ 执行 (F5)')

            error(f"统一执行器执行失败: {str(e)}", "CANVAS_DIALOG", LogCategory.SOFTWARE)
            import traceback
            traceback.print_exc()
        finally:
            # 确保所有节点都停止执行状态
            for node in execution_order:
                node.set_executing(False)

    def build_execution_order(self) -> List[AlgorithmNode]:
        """构建算法执行顺序"""
        execution_order = []
        visited = set()
        
        def find_execution_path(start_node):
            """递归查找执行路径"""
            for connection in self.canvas.connections:
                if connection.start_item == start_node and connection.end_item not in visited:
                    visited.add(connection.end_item)
                    
                    if isinstance(connection.end_item, AlgorithmNode):
                        execution_order.append(connection.end_item)
                        # 继续查找连接到该算法节点的后续节点
                        find_execution_path(connection.end_item)
                    elif isinstance(connection.end_item, ImageNode) and connection.end_item.node_type == "output":
                        # 到达输出节点，停止查找
                        pass
        
        # 从输入节点开始构建执行顺序
        input_node = self.canvas.nodes.get("input_image")
        if input_node:
            find_execution_path(input_node)
        
        return execution_order
    
    def update_result_combo(self, executed_nodes: List[AlgorithmNode]):
        """更新中间结果下拉框"""
        debug(f"更新中间结果下拉框，节点数量: {len(executed_nodes)}", "CHAIN")
        
        # 保存当前下拉框选择
        current_selection = self.result_combo.currentText()
        debug(f"当前选择: {current_selection}", "CHAIN")
        
        self.result_combo.clear()
        self.result_combo.addItem("选择中间结果...")
        
        added_count = 0
        for i, node in enumerate(executed_nodes):
            algorithm_info = node.algorithm.get_info()
            if node.execution_result:
                # 根据成功/失败状态添加不同的标识
                status_icon = "✅" if node.execution_result.success else "❌"
                item_text = f"{i+1}. {status_icon} {algorithm_info.display_name}"
                debug(f"添加中间结果: {item_text}", "CHAIN")
                self.result_combo.addItem(item_text)
                added_count += 1
            else:
                # 即使没有结果对象也显示，让用户知道算法被执行了
                item_text = f"{i+1}. ❓ {algorithm_info.display_name} (无结果)"
                debug(f"添加无结果节点: {item_text}", "CHAIN")
                self.result_combo.addItem(item_text)
                added_count += 1
        
        debug(f"下拉框项目总数: {self.result_combo.count()}，添加了 {added_count} 个结果", "CHAIN")
        
        # 尝试恢复之前的选择
        if current_selection != "选择中间结果...":
            index = self.result_combo.findText(current_selection)
            if index >= 0:
                self.result_combo.setCurrentIndex(index)
                debug(f"恢复选择: {current_selection}", "CHAIN")
        
        # 强制刷新UI
        self.result_combo.update()
        self.result_combo.repaint()
    
    def clear_canvas(self):
        """清空画布"""
        reply = QMessageBox.question(
            self, 
            '确认清空', 
            '确定要清空画布吗？此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.scene.clear()
            self.canvas.nodes.clear()
            self.canvas.connections.clear()
            self.canvas.draw_grid()
            self.init_canvas()
            
            # 保存空配置到缓存
            self.save_config_to_cache()
    
    def get_algorithm_chain(self) -> List[AlgorithmBase]:
        """获取当前算法链"""
        algorithms = []
        for node_id, node in self.canvas.nodes.items():
            if isinstance(node, AlgorithmNode):
                algorithms.append(node.algorithm)
        return algorithms
    
    def set_input_image(self, image: np.ndarray):
        """设置输入图像"""
        input_node = self.canvas.nodes.get("input_image")
        if input_node:
            input_node.set_image(image)
            self.status_bar.setText("输入图像已设置")
            # 保存配置到缓存
            self.save_config_to_cache()
    
    def load_image_file(self, file_path: str):
        """从文件加载图像 - 使用统一的工具函数"""
        try:
            from utils.image_utils import load_image as utils_load_image
            image = utils_load_image(file_path)
            if image is not None:
                self.set_input_image(image)
            else:
                self.status_bar.setText("无法加载图像文件")
        except Exception as e:
            self.status_bar.setText(f"加载图像失败: {str(e)}")
    
    def add_input_image_button(self):
        """添加输入图像按钮到工具栏"""
        # 在工具栏中添加输入图像按钮
        self.load_image_btn = QPushButton('📁 加载图像')
        self.load_image_btn.clicked.connect(self.load_image_dialog)
        
        # 找到工具栏布局并添加按钮
        toolbar = self.findChild(QHBoxLayout)  # 简单查找工具栏布局
        if toolbar:
            toolbar.insertWidget(2, self.load_image_btn)  # 插入到第三个位置
    
    def load_image_dialog(self):
        """显示图像加载对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            '选择输入图像', 
            '', 
            '图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff)'
        )
        
        if file_path:
            self.load_image_file(file_path)
    
    def save_chain_config(self):
        """保存算法链配置到文件"""
        # 首先确保缓存是最新的
        self.save_config_to_cache()
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            '保存算法链配置', 
            '', 
            'JSON Files (*.json)'
        )
        
        if not file_path:
            return
            
        try:
            # 尝试将缓存文件移动到指定路径
            if self.move_cache_to_saved_path(file_path):
                QMessageBox.information(self, '成功', f'算法链配置已保存到: {file_path}')
                self.status_bar.setText(f"配置已保存: {Path(file_path).name}")
                
                # 保存后创建新的缓存文件以供继续编辑
                self.init_config_cache()
                # 保存当前状态到新缓存文件
                self.save_config_to_cache()
            else:
                # 如果移动失败（比如缓存文件不存在），则创建新配置
                debug(f"缓存移动失败，创建新配置文件", "CHAIN")
                
                # 构建算法执行顺序
                execution_order = self.build_execution_order()
                if not execution_order:
                    QMessageBox.warning(self, '警告', '当前画布上没有可执行的算法链')
                    return
                    
                # 创建链配置对象
                chain_config = ChainConfig(
                    canvas_layout=True,
                    created_at=QDateTime.currentDateTime().toString()
                )
                
                # 为每个算法创建配置
                for algorithm_node in execution_order:
                    algorithm = algorithm_node.algorithm
                    
                    # 从算法实例创建配置
                    algorithm_config = AlgorithmConfig.from_algorithm_base(algorithm)
                    
                    # 添加布局信息
                    node_pos = algorithm_node.scenePos()
                    algorithm_config.layout = {
                        "position": {
                            "x": float(node_pos.x()),
                            "y": float(node_pos.y())
                        },
                        "node_id": algorithm_node.node_id
                    }
                    
                    chain_config.algorithms.append(algorithm_config)
                
                # 保存连接信息
                for connection in self.canvas.connections:
                    start_node = connection.start_item
                    end_node = connection.end_item
                    
                    if isinstance(start_node, AlgorithmNode) and isinstance(end_node, AlgorithmNode):
                        # 查找算法ID
                        start_algorithm_id = start_node.algorithm.get_info().name
                        end_algorithm_id = end_node.algorithm.get_info().name
                        
                        connection_config = ConnectionConfig(
                            from_algorithm=start_algorithm_id,
                            to_algorithm=end_algorithm_id,
                            from_port=connection.start_port or "right",
                            to_port=connection.end_port or "left"
                        )
                        
                        chain_config.connections.append(connection_config)
                
                # 保存到文件
                chain_config.save_to_file(file_path)
                    
                QMessageBox.information(self, '成功', f'配置已保存，包含 {len(execution_order)} 个算法')
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'保存配置失败: {str(e)}')
    
    def load_chain_config(self):
        """从文件加载算法链配置"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            '加载算法链配置', 
            '', 
            'JSON Files (*.json)'
        )
        
        if not file_path:
            return
            
        try:
            info(f"开始加载算法链配置文件: {file_path}", "CHAIN")
            # 加载配置文件
            chain_config = ChainConfig.load_from_file(file_path)
            debug(f"成功加载配置文件，包含 {len(chain_config.algorithms)} 个算法", "CHAIN")
            
            # 清空当前画布
            reply = QMessageBox.question(
                self, 
                '确认加载', 
                '加载配置将清空当前画布，是否继续？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
            
            self.clear_canvas_silent()
            
            # 加载算法链
            if not self.algorithm_manager:
                self.status_bar.setText("算法管理器未初始化，无法加载配置")
                return
                
            registry = self.algorithm_manager.get_registry()
            node_mapping = {}  # 用于建立算法ID到节点的映射
            algorithm_nodes = []  # 存储所有算法节点，用于自动连接
            
            for algorithm_config in chain_config.algorithms:
                # 检查是否是组合算法
                algorithm = None
                
                # 方法1：检查是否有nested_chain_config
                if hasattr(algorithm_config, 'nested_chain_config') and algorithm_config.nested_chain_config:
                    debug(f"检测到组合算法（通过nested_chain_config）: {algorithm_config.algorithm_id}", "CHAIN")
                    try:
                        # 创建组合算法实例
                        from core.interfaces.algorithm.composite.combined_algorithm import CombinedAlgorithm
                        debug(f"正在处理嵌套链配置: {algorithm_config.algorithm_id}", "CHAIN")
                        
                        # 检查nested_chain_config的类型
                        if isinstance(algorithm_config.nested_chain_config, ChainConfig):
                            # 已经是ChainConfig对象，直接使用
                            nested_chain = algorithm_config.nested_chain_config
                            debug(f"嵌套链配置已是ChainConfig对象: {algorithm_config.algorithm_id}", "CHAIN")
                        elif isinstance(algorithm_config.nested_chain_config, dict):
                            # 是字典，需要转换
                            debug(f"从字典创建嵌套链配置: {algorithm_config.algorithm_id}", "CHAIN")
                            nested_chain = ChainConfig.from_dict(algorithm_config.nested_chain_config)
                        else:
                            error(f"嵌套链配置类型错误: {type(algorithm_config.nested_chain_config)}", "CHAIN")
                            continue
                        
                        debug(f"正在创建组合算法实例: {algorithm_config.algorithm_id}", "CHAIN")
                        algorithm = CombinedAlgorithm(chain_config=nested_chain)
                        if self.algorithm_manager:
                            algorithm.initialize_algorithms(self.algorithm_manager)
                        debug(f"组合算法创建成功: {algorithm_config.algorithm_id}", "CHAIN")
                    except Exception as e:
                        error(f"创建组合算法失败 {algorithm_config.algorithm_id}: {str(e)}", "CHAIN")
                        import traceback
                        error(f"创建组合算法错误详情: {traceback.format_exc()}", "CHAIN")
                        continue
                
                # 方法2：检查category是否为"组合算法"
                elif (hasattr(algorithm_config, 'category') and algorithm_config.category == "组合算法") or \
                     (hasattr(algorithm_config, 'secondary_category') and algorithm_config.secondary_category == "自定义组合") or \
                     (hasattr(algorithm_config, 'custom_category') and algorithm_config.custom_category == "自定义组合"):
                    debug(f"检测到组合算法（通过category）: {algorithm_config.algorithm_id}", "CHAIN")
                    try:
                        # 尝试从已注册的组合算法创建实例
                        algorithm = registry.create_algorithm_instance(algorithm_config.algorithm_id)
                        debug(f"组合算法创建成功（通过注册表）: {algorithm_config.algorithm_id}", "CHAIN")
                    except Exception as e:
                        error(f"通过注册表创建组合算法失败 {algorithm_config.algorithm_id}: {str(e)}", "CHAIN")
                        algorithm = None
                
                # 方法3：如果不是组合算法，按普通算法处理
                if algorithm is None:
                    debug(f"尝试作为普通算法创建: {algorithm_config.algorithm_id}", "CHAIN")
                    try:
                        algorithm = registry.create_algorithm_instance(algorithm_config.algorithm_id)
                        debug(f"普通算法创建成功: {algorithm_config.algorithm_id}", "CHAIN")
                    except Exception as e:
                        error(f"创建算法失败 {algorithm_config.algorithm_id}: {str(e)}", "CHAIN")
                        continue
                
                if algorithm:
                    # 应用配置到算法实例
                    algorithm_config.apply_to_algorithm(algorithm)
                    
                    # 确定节点位置
                    x, y = 250, 200  # 默认位置
                    if algorithm_config.layout and "position" in algorithm_config.layout:
                        x = float(algorithm_config.layout["position"]["x"])
                        y = float(algorithm_config.layout["position"]["y"])
                    
                    # 添加到画布
                    node = self.canvas.add_algorithm_node(algorithm, x, y)
                    algorithm_nodes.append(node)
                    
                    # 建立映射关系 - 使用节点ID而不是算法ID
                    node_mapping[algorithm_config.algorithm_id] = node
                    # 也建立基于节点ID的映射
                    if hasattr(node, 'node_id'):
                        node_mapping[node.node_id] = node
            
            # 自动连接输入图像节点到第一个算法节点
            input_node = self.canvas.nodes.get("input_image")
            if input_node and algorithm_nodes:
                first_algorithm = algorithm_nodes[0]
                if self.canvas.validate_connection(input_node, 'port', first_algorithm, 'left'):
                    connection = ConnectionLine(input_node, first_algorithm, 'port', 'left')
                    self.canvas.scene.addItem(connection)
                    self.canvas.connections.append(connection)
                    self.canvas.update_port_states(input_node, first_algorithm)
            
            # 如果有连接信息，重建连接
            debug(f"开始重建连接，共有 {len(chain_config.connections)} 个连接配置", "CHAIN")
            connection_count = 0
            for connection_config in chain_config.connections:
                from_id = connection_config.from_algorithm
                to_id = connection_config.to_algorithm
                
                # 尝试多种方式查找节点
                from_node = None
                to_node = None
                
                # 方法1：直接通过ID映射查找
                if from_id in node_mapping:
                    from_node = node_mapping[from_id]
                if to_id in node_mapping:
                    to_node = node_mapping[to_id]
                
                # 方法2：如果在直接映射中没找到，尝试在所有节点中查找
                if not from_node or not to_node:
                    for node_id, node in self.canvas.nodes.items():
                        if not from_node and hasattr(node, 'algorithm') and node.algorithm.get_info().name == from_id:
                            from_node = node
                        if not to_node and hasattr(node, 'algorithm') and node.algorithm.get_info().name == to_id:
                            to_node = node
                
                # 方法3：如果还是没找到，尝试通过display_name查找
                if not from_node or not to_node:
                    for node_id, node in self.canvas.nodes.items():
                        if not from_node and hasattr(node, 'algorithm') and node.algorithm.get_info().display_name == from_id:
                            from_node = node
                        if not to_node and hasattr(node, 'algorithm') and node.algorithm.get_info().display_name == to_id:
                            to_node = node
                
                if from_node and to_node:
                    # 验证连接并创建
                    debug(f"创建连接: {from_id} -> {to_id}", "CHAIN")
                    if self.canvas.validate_connection(from_node, connection_config.from_port, to_node, connection_config.to_port):
                        connection = ConnectionLine(from_node, to_node, connection_config.from_port, connection_config.to_port)
                        self.canvas.scene.addItem(connection)
                        self.canvas.connections.append(connection)
                        
                        # 更新端口状态
                        self.canvas.update_port_states(from_node, to_node)
                        connection_count += 1
                    else:
                        warning(f"连接验证失败: {from_id} -> {to_id}", "CHAIN")
                else:
                    warning(f"无法找到连接节点: {from_id} -> {to_id} (from_node: {from_node is not None}, to_node: {to_node is not None})", "CHAIN")
            
            debug(f"连接重建完成，成功创建 {connection_count}/{len(chain_config.connections)} 个连接", "CHAIN")
            
            # 自动连接最后一个算法节点到输出图像节点
            output_node = self.canvas.nodes.get("output_image")
            if output_node and algorithm_nodes:
                last_algorithm = algorithm_nodes[-1]
                if self.canvas.validate_connection(last_algorithm, 'right', output_node, 'port'):
                    connection = ConnectionLine(last_algorithm, output_node, 'right', 'port')
                    self.canvas.scene.addItem(connection)
                    self.canvas.connections.append(connection)
                    self.canvas.update_port_states(last_algorithm, output_node)
            
            QMessageBox.information(self, '成功', f'配置已加载，包含 {len(chain_config.algorithms)} 个算法，已自动连接输入输出节点')
            
            # 加载完成后保存到缓存
            self.save_config_to_cache()
            
        except Exception as e:
            error_msg = f'加载配置失败: {str(e)}'
            error(error_msg, "CHAIN")
            import traceback
            traceback_str = traceback.format_exc()
            error(f"详细错误信息: {traceback_str}", "CHAIN")
            QMessageBox.critical(self, '错误', error_msg)
    
    def clear_canvas_silent(self):
        """静默清空画布（不显示确认对话框）"""
        self.canvas.scene.clear()
        self.canvas.nodes.clear()
        self.canvas.connections.clear()
        self.canvas.draw_grid()
        self.init_canvas()

    def load_settings(self):
        """加载对话框窗口设置"""
        try:
            # 使用统一窗口设置管理器加载对话框设置
            additional_data = {}

            # 保存分割器状态到额外数据中
            if hasattr(self, 'main_splitter'):
                splitter_state = self.main_splitter.saveState()
                import binascii
                additional_data['main_splitter_state'] = binascii.hexlify(splitter_state.data()).decode('ascii')

            # 使用统一管理器加载窗口状态
            success = self.window_settings_manager.load_window_state(
                self,
                "larminar_vision_algorithm_chain_dialog",
                default_geometry=(200, 200, 1200, 800)
            )

            if success:
                # 尝试恢复分割器状态
                window_settings = self.window_settings_manager.get_window_settings("larminar_vision_algorithm_chain_dialog")
                if (window_settings and
                    'additional_data' in window_settings and
                    'main_splitter_state' in window_settings['additional_data'] and
                    hasattr(self, 'main_splitter')):
                    try:
                        import binascii
                        splitter_bytes = binascii.unhexlify(window_settings['additional_data']['main_splitter_state'])
                        self.main_splitter.restoreState(splitter_bytes)
                        debug("算法链对话框分割器状态已恢复", "CANVAS_DIALOG", LogCategory.SOFTWARE)
                    except Exception as e:
                        error(f"恢复算法链对话框分割器状态失败: {str(e)}", "CANVAS_DIALOG", LogCategory.SOFTWARE)

                debug("算法链对话框设置加载完成", "CANVAS_DIALOG", LogCategory.SOFTWARE)
            else:
                debug("使用默认算法链对话框设置", "CANVAS_DIALOG", LogCategory.SOFTWARE)
                # 如果没有保存的设置，使用默认的分割器比例
                if hasattr(self, 'main_splitter'):
                    self.main_splitter.setSizes([200, 700, 300])

        except Exception as e:
            error(f"加载算法链对话框设置失败: {str(e)}", "CANVAS_DIALOG", LogCategory.SOFTWARE)
            # 使用默认设置
            self.setGeometry(200, 200, 1200, 800)
            if hasattr(self, 'main_splitter'):
                self.main_splitter.setSizes([200, 700, 300])

    def save_settings(self):
        """保存对话框窗口设置"""
        try:
            # 准备额外数据
            additional_data = {}

            # 保存分割器状态
            if hasattr(self, 'main_splitter'):
                splitter_state = self.main_splitter.saveState()
                import binascii
                additional_data['main_splitter_state'] = binascii.hexlify(splitter_state.data()).decode('ascii')

            # 使用统一窗口设置管理器保存窗口状态
            success = self.window_settings_manager.save_window_state(
                self,
                "larminar_vision_algorithm_chain_dialog",
                additional_data
            )

            if success:
                debug("算法链对话框设置保存完成", "CANVAS_DIALOG", LogCategory.SOFTWARE)
            else:
                error("算法链对话框设置保存失败", "CANVAS_DIALOG", LogCategory.SOFTWARE)

        except Exception as e:
            error(f"保存算法链对话框设置失败: {str(e)}", "CANVAS_DIALOG", LogCategory.SOFTWARE)

    def save_as_combined_algorithm(self):
        """保存当前算法链为组合算法"""
        try:
            # 构建算法执行顺序
            execution_order = self.build_execution_order()
            if not execution_order:
                QMessageBox.warning(self, '警告', '当前画布上没有可执行的算法链，无法保存为组合算法')
                return
            
            # 显示保存组合算法对话框
            from ..dialogs.save_combined_algorithm_dialog import SaveCombinedAlgorithmDialog
            
            # 获取现有算法ID列表用于去重
            existing_ids = []
            if self.algorithm_manager:
                registry = self.algorithm_manager.get_registry()
                existing_ids = list(registry.get_all_algorithms().keys())
            
            dialog = SaveCombinedAlgorithmDialog(self, execution_order, existing_ids)
            
            def on_save_requested(algorithm_id, metadata):
                """处理保存请求"""
                try:
                    # 创建链配置对象
                    chain_config = ChainConfig(
                        canvas_layout=True,
                        created_at=QDateTime.currentDateTime().toString()
                    )
                    
                    # 为每个算法创建配置
                    for algorithm_node in execution_order:
                        algorithm = algorithm_node.algorithm
                        
                        # 从算法实例创建配置
                        algorithm_config = AlgorithmConfig.from_algorithm_base(algorithm)
                        
                        # 添加布局信息
                        node_pos = algorithm_node.scenePos()
                        algorithm_config.layout = {
                            "position": {
                                "x": float(node_pos.x()),
                                "y": float(node_pos.y())
                            },
                            "node_id": algorithm_node.node_id
                        }
                        
                        chain_config.algorithms.append(algorithm_config)
                    
                    # 保存连接信息
                    for connection in self.canvas.connections:
                        start_node = connection.start_item
                        end_node = connection.end_item
                        
                        if isinstance(start_node, AlgorithmNode) and isinstance(end_node, AlgorithmNode):
                            # 查找算法ID
                            start_algorithm_id = start_node.algorithm.get_info().name
                            end_algorithm_id = end_node.algorithm.get_info().name
                            
                            connection_config = ConnectionConfig(
                                from_algorithm=start_algorithm_id,
                                to_algorithm=end_algorithm_id,
                                from_port=connection.start_port or "right",
                                to_port=connection.end_port or "left"
                            )
                            
                            chain_config.connections.append(connection_config)
                    
                    # 使用组合算法管理器创建组合算法
                    created_algorithm_id = self.combined_algorithm_manager.create_combined_algorithm(
                        chain_config=chain_config,
                        name=metadata["display_name"],
                        description=metadata["description"],
                        metadata=metadata
                    )
                    
                    if created_algorithm_id:
                        # 重新加载算法库以显示新的组合算法
                        self.load_algorithm_library()
                        
                        # 通知主窗口刷新算法面板
                        if (self.main_window and 
                            hasattr(self.main_window, 'algorithm_category_widget')):
                            self.main_window.algorithm_category_widget.refresh_algorithms()
                            debug(f"已通知主窗口刷新算法面板", "CHAIN_REFRESH", LogCategory.SOFTWARE)
                        
                        QMessageBox.information(self, '成功', 
                            f'组合算法已保存\n'
                            f'名称: {metadata["display_name"]}\n'
                            f'ID: {created_algorithm_id}\n'
                            f'分类: {metadata["category"]}\n'
                            f'版本: {metadata["version"]}\n'
                            f'作者: {metadata["author"]}\n'
                            f'包含 {len(execution_order)} 个算法')
                        self.status_bar.setText(f"组合算法已保存: {metadata['display_name']}")
                    else:
                        QMessageBox.critical(self, '错误', '保存组合算法失败')
                        
                except Exception as e:
                    QMessageBox.critical(self, '错误', f'保存组合算法失败: {str(e)}')
            
            dialog.save_requested.connect(on_save_requested)
            
            # 显示对话框
            result = dialog.exec()
            if result == QDialog.DialogCode.Rejected:
                debug(f"用户取消了组合算法保存", "CHAIN")
            
        except Exception as e:
            QMessageBox.critical(self, '错误', f'打开保存组合算法对话框失败: {str(e)}')
    
    def open_recursive_debug_dialog(self, combined_algorithm: CombinedAlgorithm):
        """打开递归调试对话框"""
        try:
            # 清理已关闭的对话框
            self.cleanup_closed_debug_dialogs()
            
            # 检查是否已经打开了该算法的调试对话框
            for dialog in self.recursive_debug_dialogs:
                if (hasattr(dialog, 'debugged_algorithm') and 
                    dialog.debugged_algorithm == combined_algorithm and
                    dialog.isVisible()):
                    dialog.raise_()
                    dialog.activateWindow()
                    debug(f"递归调试对话框已存在，重新激活: {combined_algorithm.get_info().display_name}", "CHAIN")
                    return
            
            # 创建新的调试对话框
            debug(f"正在创建递归调试对话框: {combined_algorithm.get_info().display_name}", "CHAIN")
            debug_dialog = RecursiveCombinedAlgorithmDebugDialog(self, combined_algorithm)
            debug_dialog.debugged_algorithm = combined_algorithm
            
            # 添加到递归调试对话框列表
            self.recursive_debug_dialogs.append(debug_dialog)
            
            # 当对话框关闭时，标记为已关闭但不立即删除
            debug_dialog.finished.connect(lambda: self.on_debug_dialog_closed(debug_dialog))
            
            # 显示对话框
            debug_dialog.show()
            
            self.status_bar.setText(f"已打开递归调试对话框: {combined_algorithm.get_info().display_name}")
            info(f"递归调试对话框已打开: {combined_algorithm.get_info().display_name}", "CHAIN")
            
        except Exception as e:
            error_msg = f'打开递归调试对话框失败: {str(e)}'
            error(error_msg, "CHAIN")
            QMessageBox.critical(self, '错误', error_msg)
    
    def cleanup_closed_debug_dialogs(self):
        """清理已关闭的调试对话框"""
        try:
            # 过滤出仍然存在的对话框
            active_dialogs = []
            closed_count = 0
            for dialog in self.recursive_debug_dialogs:
                try:
                    if dialog.isVisible():
                        active_dialogs.append(dialog)
                    else:
                        # 对话框已关闭，可以安全删除
                        dialog.deleteLater()
                        closed_count += 1
                except:
                    # 对话框对象已被销毁
                    closed_count += 1
                    pass
            
            self.recursive_debug_dialogs = active_dialogs
            if closed_count > 0:
                debug(f"已清理 {closed_count} 个已关闭的调试对话框", "CHAIN")
            
        except Exception as e:
            error(f"清理调试对话框失败: {str(e)}", "CHAIN")
    
    def on_debug_dialog_closed(self, debug_dialog):
        """处理调试对话框关闭事件"""
        try:
            # 从列表中移除已关闭的对话框
            if debug_dialog in self.recursive_debug_dialogs:
                self.recursive_debug_dialogs.remove(debug_dialog)
            
            # 延迟删除对话框对象
            debug_dialog.deleteLater()
            
            self.status_bar.setText("递归调试对话框已关闭")
            debug("递归调试对话框已关闭并清理", "CHAIN")
            
        except Exception as e:
            error(f"处理调试对话框关闭事件失败: {str(e)}", "CHAIN")

    def closeEvent(self, event):
        """关闭事件 - 保存窗口设置"""
        try:
            # 关闭所有递归调试对话框
            dialog_count = len(self.recursive_debug_dialogs)
            if dialog_count > 0:
                info(f"正在关闭 {dialog_count} 个递归调试对话框", "CHAIN")
                
            for dialog in self.recursive_debug_dialogs[:]:  # 创建副本以避免修改列表时的问题
                try:
                    if hasattr(dialog, 'close'):
                        dialog.close()
                        dialog.deleteLater()
                except Exception as e:
                    warning(f"关闭递归调试对话框时出错: {str(e)}", "CHAIN")
            
            self.recursive_debug_dialogs.clear()
            
            # 保存设置
            self.save_settings()

        except Exception as e:
            error(f"关闭事件处理失败: {str(e)}", "CHAIN")
            # 即使出错也接受关闭事件
            event.accept()
            return

        # 接受关闭事件
        info("算法链对话框已关闭", "CHAIN")
        event.accept()
    
    def apply_to_vmc_node(self):
        """将当前算法配置应用到VMC节点"""
        try:
            if not self.is_from_vmc_node or not self.vmc_callback:
                warning("Not initialized with VMC node callback", "VISION_DIALOG")
                return
            
            # Get current algorithm configuration from canvas
            algorithm_configs = []
            if hasattr(self.canvas, 'algorithm_nodes') and self.canvas.algorithm_nodes:
                from core.managers.combined_algorithm_manager import CombinedAlgorithmManager
                combined_manager = CombinedAlgorithmManager()
                
                # Collect all algorithms from canvas in execution order
                for node in self.canvas.algorithm_nodes:
                    if hasattr(node, 'algorithm') and node.algorithm:
                        try:
                            # Convert algorithm to configuration
                            algorithm_config = combined_manager.convert_algorithm_to_config(node.algorithm)
                            algorithm_configs.append(algorithm_config)
                        except Exception as e:
                            debug(f"Failed to convert algorithm {getattr(node.algorithm, '_algorithm_id', 'unknown')} to config: {e}", "VISION_DIALOG")
            
            # Call callback with algorithm configurations
            if algorithm_configs:
                debug(f"VisionDialog: Applying {len(algorithm_configs)} algorithm configs to VMC node", "VISION_DIALOG")
                self.vmc_callback(algorithm_configs)
                
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "应用成功", f"已将 {len(algorithm_configs)} 个算法配置应用到节点")
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "无算法配置", "画布中没有可应用的算法配置")
            
        except Exception as e:
            from core.managers.log_manager import error
            error(f"Failed to apply algorithm configs to VMC node: {e}", "VISION_DIALOG")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "应用失败", f"应用算法配置到节点时出错: {e}")