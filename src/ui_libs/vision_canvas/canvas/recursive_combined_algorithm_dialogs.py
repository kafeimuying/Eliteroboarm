from typing import List, Any
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QGroupBox, QTextEdit, QFileDialog, QMessageBox, 
                             QSplitter, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainterPath

import cv2
import os

from core.interfaces.algorithm.base import AlgorithmBase
from core.interfaces.algorithm.composite import CombinedAlgorithm
from core.managers.window_settings_manager import get_window_settings_manager
from core.managers.log_manager import debug, info, error, warning
from .canvas import AlgorithmCanvas
from .nodes import AlgorithmNode, ImageNode
from .connections import ConnectionLine
from ..components.type_aware_parameter_widget import TypeAwareParameterWidget


class RecursiveCombinedAlgorithmDebugDialog(QDialog):
    """递归组合算法调试对话框"""
    
    def __init__(self, parent_dialog, combined_algorithm: CombinedAlgorithm):
        super().__init__(parent_dialog)
        self.parent_dialog = parent_dialog
        self.combined_algorithm = combined_algorithm
        self.debugged_algorithm = combined_algorithm  # 用于标识
        self.window_settings_manager = get_window_settings_manager()
        
        self.init_ui()
        self.load_combined_algorithm_chain()
    
    def init_ui(self):
        """初始化界面"""
        algo_info = self.combined_algorithm.get_info()
        self.setWindowTitle(f'{algo_info.display_name}调试')
        self.setGeometry(300, 300, 1400, 900)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建信息栏
        info_layout = QHBoxLayout()
        info_label = QLabel(f"正在调试: {algo_info.display_name}")
        info_label.setStyleSheet("font-weight: bold; color: #0066cc; padding: 5px;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        
        # 返回父级按钮
        back_btn = QPushButton("⬅️ 返回上级")
        back_btn.clicked.connect(self.return_to_parent)
        info_layout.addWidget(back_btn)
        
        main_layout.addLayout(info_layout)
        
        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)
        
        # 创建状态栏
        self.status_bar = QLabel()
        self.status_bar.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-top: 1px solid #ccc;")
        self.status_bar.setText("调试模式 - 就绪")
        main_layout.addWidget(self.status_bar)
        
        # 左侧：内部算法库
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        library_label = QLabel("内部算法:")
        left_layout.addWidget(library_label)
        
        # 内部算法信息显示
        self.inner_algorithms_widget = QGroupBox("内部算法链")
        inner_layout = QVBoxLayout()
        
        # 显示内部算法列表
        self.inner_algorithms_list = QLabel()
        self.inner_algorithms_list.setWordWrap(True)
        inner_layout.addWidget(self.inner_algorithms_list)
        
        self.inner_algorithms_widget.setLayout(inner_layout)
        left_layout.addWidget(self.inner_algorithms_widget)
        
        main_splitter.addWidget(left_widget)
        
        # 中间：调试画布区域
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(5, 5, 5, 5)
        
        # 工具栏
        toolbar_layout = QHBoxLayout()
        
        # 输入图像控制
        self.load_input_btn = QPushButton('📁 加载测试图像')
        self.load_input_btn.clicked.connect(self.load_test_image)
        toolbar_layout.addWidget(self.load_input_btn)
        
        self.execute_btn = QPushButton('▶️ 执行内部链')
        self.execute_btn.clicked.connect(self.execute_internal_chain)
        toolbar_layout.addWidget(self.execute_btn)
        
        self.clear_btn = QPushButton('🗑️ 清空')
        self.clear_btn.clicked.connect(self.clear_debug_canvas)
        toolbar_layout.addWidget(self.clear_btn)
        
        toolbar_layout.addStretch()
        middle_layout.addLayout(toolbar_layout)
        
        # 创建调试画布
        self.debug_canvas = AlgorithmCanvas(parent_dialog=self)
        self.debug_canvas.algorithm_dropped.connect(self.on_algorithm_dropped_to_debug_canvas)
        self.debug_canvas.node_selected.connect(self.on_debug_node_selected)
        self.debug_canvas.connection_created.connect(self.on_debug_connection_created)
        self.debug_canvas.execution_requested.connect(self.execute_debug_chain)
        self.debug_canvas.status_update_callback = self.status_bar.setText
        middle_layout.addWidget(self.debug_canvas)
        
        main_splitter.addWidget(middle_widget)
        
        # 右侧：参数配置和结果
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        param_label = QLabel("参数配置:")
        right_layout.addWidget(param_label)
        
        # 参数配置组件
        self.debug_parameter_widget = TypeAwareParameterWidget()
        self.debug_parameter_widget.parameter_changed.connect(self.on_debug_parameter_changed)
        right_layout.addWidget(self.debug_parameter_widget)
        
        # 测试结果区域
        result_group = QGroupBox("执行结果")
        result_layout = QVBoxLayout()
        
        self.result_text = QTextEdit()
        self.result_text.setMaximumHeight(150)
        self.result_text.setReadOnly(True)
        result_layout.addWidget(self.result_text)
        
        result_group.setLayout(result_layout)
        right_layout.addWidget(result_group)
        
        right_layout.addStretch()
        
        main_splitter.addWidget(right_widget)
        
        # 设置分割器比例
        main_splitter.setSizes([200, 800, 300])
        
        # 加载窗口设置
        self.load_settings()
    
    def load_combined_algorithm_chain(self):
        """加载组合算法的内部链到画布"""
        try:
            debug(f"开始加载组合算法内部链: {self.combined_algorithm.get_info().display_name}", "CHAIN")
            chain_config = self.combined_algorithm.get_chain_config()
            if not chain_config:
                error("无法获取组合算法配置", "CHAIN")
                self.status_bar.setText("无法获取组合算法配置")
                return
            
            # 清空当前画布
            self.clear_debug_canvas()
            
            # 添加输入输出节点
            input_node = self.debug_canvas.add_image_node("input", 50, 200)
            output_node = self.debug_canvas.add_image_node("output", 50, 350)
            
            # 创建内部算法节点映射
            node_mapping = {}
            algorithm_nodes = []
            
            # 加载内部算法
            if self.parent_dialog and self.parent_dialog.algorithm_manager:
                registry = self.parent_dialog.algorithm_manager.get_registry()
                
                for i, algo_config in enumerate(chain_config.algorithms):
                    # 创建算法实例
                    algorithm = registry.create_algorithm_instance(algo_config.algorithm_id)
                    if algorithm:
                        # 应用配置
                        algo_config.apply_to_algorithm(algorithm)
                        
                        # 确定位置
                        x, y = 250, 200
                        if algo_config.layout and "position" in algo_config.layout:
                            x = float(algo_config.layout["position"]["x"])
                            y = float(algo_config.layout["position"]["y"])
                        else:
                            # 默认位置排列
                            x = 250 + (i % 3) * 200
                            y = 200 + (i // 3) * 150
                        
                        # 添加到画布
                        node = self.debug_canvas.add_algorithm_node(algorithm, x, y)
                        algorithm_nodes.append(node)
                        node_mapping[algo_config.algorithm_id] = node
            else:
                self.status_bar.setText("无法获取算法注册表，跳过内部算法加载")
                return
            
            # 自动连接输入到第一个算法
            if algorithm_nodes:
                first_algorithm = algorithm_nodes[0]
                connection = ConnectionLine(input_node, first_algorithm, 'port', 'left')
                self.debug_canvas.scene.addItem(connection)
                self.debug_canvas.connections.append(connection)
                first_algorithm.input_connected = True
                first_algorithm.update_port_colors()
                input_node.connected = True
                input_node.update_port_color()
            
            # 重建内部连接
            for connection_config in chain_config.connections:
                from_id = connection_config.from_algorithm
                to_id = connection_config.to_algorithm
                
                if from_id in node_mapping and to_id in node_mapping:
                    from_node = node_mapping[from_id]
                    to_node = node_mapping[to_id]
                    
                    # 验证连接并创建
                    if self.debug_canvas.validate_connection(from_node, connection_config.from_port, to_node, connection_config.to_port):
                        connection = ConnectionLine(from_node, to_node, connection_config.from_port, connection_config.to_port)
                        self.debug_canvas.scene.addItem(connection)
                        self.debug_canvas.connections.append(connection)
                        
                        # 更新端口状态
                        self.debug_canvas.update_port_states(from_node, to_node)
            
            # 自动连接最后一个算法到输出
            if algorithm_nodes:
                last_algorithm = algorithm_nodes[-1]
                connection = ConnectionLine(last_algorithm, output_node, 'right', 'port')
                self.debug_canvas.scene.addItem(connection)
                self.debug_canvas.connections.append(connection)
                last_algorithm.output_connected = True
                last_algorithm.update_port_colors()
                output_node.connected = True
                output_node.update_port_color()
            
            # 更新内部算法信息显示
            self.update_inner_algorithms_info(algorithm_nodes)
            
            success_msg = f"已加载内部链: {len(algorithm_nodes)} 个算法"
            self.status_bar.setText(success_msg)
            info(success_msg, "CHAIN")
            
        except Exception as e:
            error_msg = f"加载内部链失败: {str(e)}"
            self.status_bar.setText(error_msg)
            error(error_msg, "CHAIN")
    
    def update_inner_algorithms_info(self, algorithm_nodes):
        """更新内部算法信息显示"""
        try:
            info_text = f"内部算法数量: {len(algorithm_nodes)}\n\n"
            
            for i, node in enumerate(algorithm_nodes, 1):
                algo_info = node.algorithm.get_info()
                info_text += f"{i}. {algo_info.display_name}\n"
                info_text += f"   ID: {algo_info.name}\n"
                info_text += f"   描述: {algo_info.description}\n\n"
            
            self.inner_algorithms_list.setText(info_text)
            
        except Exception as e:
            self.inner_algorithms_list.setText(f"更新信息失败: {str(e)}")
    
    def load_test_image(self):
        """加载测试图像"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            '选择测试图像', 
            '', 
            '图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff)'
        )
        
        if file_path:
            try:
                import cv2
                image = cv2.imread(file_path)
                if image is not None:
                    input_node = self.debug_canvas.nodes.get("input_image")
                    if input_node:
                        input_node.set_image(image)
                        self.status_bar.setText(f"测试图像已加载: {os.path.basename(file_path)}")
                else:
                    self.status_bar.setText("图像加载失败")
            except Exception as e:
                self.status_bar.setText(f"加载图像失败: {str(e)}")
    
    def execute_internal_chain(self):
        """执行内部算法链"""
        self.execute_debug_chain()
    
    def execute_debug_chain(self):
        """执行调试画布上的算法链"""
        try:
            # 获取输入图像
            input_node = self.debug_canvas.nodes.get("input_image")
            
            # 优先使用统一输入，如果有的话
            input_image = self.get_unified_input_image()
            if input_image is not None:
                if input_node:
                    input_node.set_image(input_image)
            elif input_node and input_node.image_data is not None:
                input_image = input_node.image_data
            
            # 如果仍然没有输入图像，提示用户加载
            if input_image is None:
                QMessageBox.warning(self, '警告', '请先加载测试图像')
                return
            
            # 构建执行顺序
            execution_order = []
            visited = set()
            
            def find_execution_path(start_node):
                for connection in self.debug_canvas.connections:
                    if connection.start_item == start_node and connection.end_item not in visited:
                        visited.add(connection.end_item)
                        if isinstance(connection.end_item, AlgorithmNode):
                            execution_order.append(connection.end_item)
                            find_execution_path(connection.end_item)
            
            input_node_debug = self.debug_canvas.nodes.get("input_image")
            if input_node_debug:
                find_execution_path(input_node_debug)
            
            if not execution_order:
                self.status_bar.setText("未找到可执行的算法链")
                return
            
            # 执行算法链
            current_image = input_node.image_data
            results = []
            
            for i, node in enumerate(execution_order):
                try:
                    # 设置执行状态
                    node.set_executing(True)
                    
                    # 获取算法参数
                    algorithm = node.algorithm
                    all_params = algorithm.get_all_parameters()
                    
                    # 执行算法
                    result = algorithm.process(current_image, **all_params)
                    
                    # 存储执行结果
                    node.execution_result = result
                    
                    # 更新节点状态
                    node.set_execution_result(result.success)
                    
                    if result.success and result.output_image is not None:
                        current_image = result.output_image
                        results.append(f"步骤 {i+1}: {algorithm.get_info().display_name} - 成功")
                    else:
                        results.append(f"步骤 {i+1}: {algorithm.get_info().display_name} - 失败: {result.error_message}")
                        break
                    
                except Exception as e:
                    node.set_execution_result(False)
                    results.append(f"步骤 {i+1}: 执行异常 - {str(e)}")
                    break
                finally:
                    node.set_executing(False)
            
            # 设置输出图像
            output_node = self.debug_canvas.nodes.get("output_image")
            if output_node and current_image is not None:
                output_node.set_image(current_image)
            
            # 显示执行结果
            result_text = "执行结果:\n" + "\n".join(results)
            self.result_text.setText(result_text)
            self.status_bar.setText(f"内部链执行完成，共执行 {len(execution_order)} 个算法")
            
        except Exception as e:
            self.result_text.setText(f"执行失败: {str(e)}")
            self.status_bar.setText(f"执行失败: {str(e)}")
    
    def clear_debug_canvas(self):
        """清空调试画布"""
        self.debug_canvas.scene.clear()
        self.debug_canvas.nodes.clear()
        self.debug_canvas.connections.clear()
        self.debug_canvas.draw_grid()
    
    def on_algorithm_dropped_to_debug_canvas(self, algorithm_id: str, x: float, y: float):
        """处理拖拽到调试画布的算法"""
        pass  # 递归调试模式下不允许添加新算法
    
    def on_debug_node_selected(self, node):
        """调试节点选择事件"""
        if isinstance(node, AlgorithmNode):
            self.debug_parameter_widget.set_algorithm(node.algorithm)
        elif isinstance(node, ImageNode):
            self.debug_parameter_widget.set_algorithm(None)
    
    def on_debug_connection_created(self, start_item, end_item):
        """调试连接创建事件"""
        pass  # 递归调试模式下不允许创建新连接
    
    def on_debug_parameter_changed(self, param_name, value):
        """调试参数改变事件"""
        # 获取当前选中的算法节点
        selected_items = self.debug_canvas.scene.selectedItems()
        if selected_items:
            for item in selected_items:
                if isinstance(item, AlgorithmNode):
                    item.algorithm.set_parameter(param_name, value)
                    
                    # 实时同步参数到组合算法配置
                    self.sync_parameter_to_combined_algorithm(item.algorithm, param_name, value)
    
    def get_unified_input_image(self):
        """获取统一的输入图像（从父对话框继承）"""
        try:
            # 如果父对话框有输入图像，使用它
            if self.parent_dialog and hasattr(self.parent_dialog, 'canvas'):
                parent_input_node = self.parent_dialog.canvas.nodes.get("input_image")
                if parent_input_node and parent_input_node.image_data is not None:
                    return parent_input_node.image_data
            
            # 如果父级正在执行算法链，使用其当前的输入
            if self.parent_dialog and hasattr(self.parent_dialog, 'current_input_image'):
                return self.parent_dialog.current_input_image
            
            return None
        except Exception:
            return None
    
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
    
    def return_to_parent(self):
        """返回父级对话框"""
        self.close()
    
    def load_settings(self):
        """加载对话框窗口设置"""
        try:
            dialog_id = f"recursive_debug_{id(self.combined_algorithm)}"
            success = self.window_settings_manager.load_window_state(
                self,
                dialog_id,
                default_geometry=(300, 300, 1400, 900)
            )
            
            if success:
                print(f"递归调试对话框设置加载完成: {dialog_id}")
            else:
                print(f"使用默认递归调试对话框设置: {dialog_id}")
                
        except Exception as e:
            print(f"加载递归调试对话框设置失败: {str(e)}")
            self.setGeometry(300, 300, 1400, 900)
    
    def save_settings(self):
        """保存对话框窗口设置"""
        try:
            dialog_id = f"recursive_debug_{id(self.combined_algorithm)}"
            success = self.window_settings_manager.save_window_state(self, dialog_id)
            
            if success:
                print(f"递归调试对话框设置保存完成: {dialog_id}")
            else:
                print(f"递归调试对话框设置保存失败: {dialog_id}")
                
        except Exception as e:
            print(f"保存递归调试对话框设置失败: {str(e)}")
    
    def closeEvent(self, event):
        """关闭事件 - 保存窗口设置并同步参数"""
        # 同步参数变化回主对话框
        self.sync_parameters_to_parent()
        
        self.save_settings()
        event.accept()
    
    def sync_parameters_to_parent(self):
        """将内部算法的参数同步回主对话框中的组合算法"""
        try:
            # 获取组合算法的配置
            chain_config = self.combined_algorithm.get_chain_config()
            if not chain_config:
                return
            
            # 遍历调试画布中的所有算法节点
            algorithm_nodes = []
            for node_id, node in self.debug_canvas.nodes.items():
                if isinstance(node, AlgorithmNode):
                    algorithm_nodes.append(node)
            
            # 为每个算法节点同步参数
            for i, debug_node in enumerate(algorithm_nodes):
                if i < len(chain_config.algorithms):
                    algo_config = chain_config.algorithms[i]
                    
                    # 调试节点中的算法应该对应配置中的算法
                    if debug_node.algorithm.get_info().name == algo_config.algorithm_id:
                        # 获取调试节点中算法的所有参数
                        debug_params = debug_node.algorithm.get_all_parameters()
                        
                        # 更新配置中的参数
                        for param_name, param_value in debug_params.items():
                            algo_config.update_parameter(param_name, param_value)
                            debug(f"同步参数 {algo_config.algorithm_id}.{param_name} = {param_value}", "CHAIN")
            
            # 保存更新后的配置到文件
            if hasattr(self.combined_algorithm, 'chain_config_path') and self.combined_algorithm.chain_config_path:
                self.combined_algorithm.save_to_file(self.combined_algorithm.chain_config_path)
                debug(f"已保存组合算法配置到 {self.combined_algorithm.chain_config_path}", "CHAIN")
            
            # 如果主对话框中有对应的算法节点，也更新其参数
            if self.parent_dialog and hasattr(self.parent_dialog, 'canvas'):
                self.sync_parameters_to_main_dialog(algorithm_nodes, chain_config)
            
        except Exception as e:
            print(f"ERROR: 同步参数失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def sync_parameters_to_main_dialog(self, debug_nodes: List, chain_config):
        """将参数同步到主对话框中的对应算法节点"""
        try:
            # 遍历主对话框画布中的算法节点
            for main_node_id, main_node in self.parent_dialog.canvas.nodes.items():
                if isinstance(main_node, AlgorithmNode):
                    # 查找对应的调试节点
                    matching_debug_node = None
                    for debug_node in debug_nodes:
                        if (debug_node.algorithm.get_info().name == main_node.algorithm.get_info().name and
                            debug_node.algorithm.get_info().category == main_node.algorithm.get_info().category):
                            matching_debug_node = debug_node
                            break
                    
                    if matching_debug_node:
                        # 同步参数
                        debug_params = matching_debug_node.algorithm.get_all_parameters()
                        for param_name, param_value in debug_params.items():
                            main_node.algorithm.set_parameter(param_name, param_value)
                            debug(f"主对话框同步参数 {main_node.algorithm.get_info().name}.{param_name} = {param_value}", "CHAIN")
                        
        except Exception as e:
            print(f"ERROR: 同步参数到主对话框失败: {str(e)}")
    
    def sync_parameter_to_combined_algorithm(self, algorithm: AlgorithmBase, param_name: str, value: Any):
        """实时同步单个参数到组合算法配置"""
        try:
            # 获取组合算法的配置
            chain_config = self.combined_algorithm.get_chain_config()
            if not chain_config:
                return
            
            # 找到对应的算法配置
            for algo_config in chain_config.algorithms:
                if algo_config.algorithm_id == algorithm.get_info().name:
                    # 更新参数配置
                    algo_config.update_parameter(param_name, value)
                    debug(f"实时同步参数 {algo_config.algorithm_id}.{param_name} = {value}", "CHAIN")
                    
                    # 实时保存配置到文件
                    if (hasattr(self.combined_algorithm, 'chain_config_path') and 
                        self.combined_algorithm.chain_config_path):
                        self.combined_algorithm.save_to_file(self.combined_algorithm.chain_config_path)
                        debug(f"实时保存组合算法配置到 {self.combined_algorithm.chain_config_path}", "CHAIN")
                    break
                    
        except Exception as e:
            print(f"ERROR: 实时同步参数失败: {str(e)}")