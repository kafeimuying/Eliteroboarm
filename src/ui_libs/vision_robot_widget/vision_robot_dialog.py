#!/usr/bin/env python3
"""
视觉-机器人协作主界面对话框
基于 ui/canvas/canvas_dialog.py 设计模式
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import QDateTime
from core.managers.app_config import AppConfigManager
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QStatusBar, QMenuBar, QToolBar, QMessageBox, QFileDialog,
    QProgressBar, QTextEdit, QTabWidget, QScrollArea, QDialog,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QPointF, QTimer, QThread, QMimeData, QPoint
from PyQt6.QtGui import QAction, QIcon, QFont, QDrag

from core.managers.log_manager import info, debug, warning, error, LogCategory
from core.managers.window_settings_manager import get_window_settings_manager
from .canvas import VRAlgorithmCanvas as VisionRobotCanvas
from .nodes import NodeType, NodeState
from .connections import VRConnectionManager

# 硬件管理模块导入
from ui_libs.hardware_widget.camera.camera_control import CameraControlTab
from ui_libs.hardware_widget.light.light_control import LightControlTab
from ui_libs.hardware_widget.robotic_arm.robot_control import RobotControlTab
from ui_libs.hardware_widget.hardware_config.hardware_config_tab import HardwareConfigTab


class DraggableNodeList(QListWidget):
    """支持拖拽的节点列表"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)

    def startDrag(self, supported_actions):
        """开始拖拽"""
        current_item = self.currentItem()
        if current_item:
            node_type = current_item.data(Qt.ItemDataRole.UserRole)
            if node_type:
                # 创建Mime数据
                mime_data = QMimeData()
                mime_data.setData("application/x-vr-node-type",
                                node_type.value.encode())

                # 创建拖拽对象
                drag = QDrag(self)
                drag.setMimeData(mime_data)
                drag.setPixmap(current_item.icon().pixmap(32, 32) if current_item.icon() else
                              self.style().standardPixmap(self.style().StandardPixmap.SP_FileIcon))
                drag.setHotSpot(QPoint(16, 16))

                # 执行拖拽
                drag.exec()


class VisionRobotDialog(QMainWindow):
    """视觉-机器人协作主界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("视觉-机器人协作系统")
        self.setGeometry(100, 100, 1600, 1000)

        # 初始化窗口设置管理器
        self.window_settings_manager = get_window_settings_manager()

        # 核心组件
        self.canvas = VisionRobotCanvas(self)
        self.connection_manager = VRConnectionManager(self.canvas)
        #self.vr_system = VisionGuidedGraspingSystem() # remove now

        # UI组件
        self.node_palette = None
        self.properties_panel = None
        self.status_panel = None
        self.workflow_panel = None

        # 状态变量
        self.current_workflow_file = None
        self.is_project_modified = False

        # 配置缓存相关
        self.cache_file_path = None  # 缓存配置文件路径
        self.first_drag_operation = True  # 标记是否为第一次拖拽操作

        # 自动保存定时器
        self._global_save_timer = QTimer()
        self._global_save_timer.setSingleShot(True)
        self._global_save_timer.timeout.connect(self.save_config_to_cache)

        # 初始化UI
        self.init_ui()
        self.init_menu_bar()
        self.init_toolbar()
        self.init_status_bar()

        # 连接信号
        self._connect_signals()

        # 初始化配置缓存（在设置初始状态之前）
        self.init_config_cache()

        # 设置初始状态
        self._setup_initial_state()

        # 检查画布中是否已有节点，如果有则自动保存初始状态
        self._auto_save_initial_state()

        # 加载窗口设置
        self._load_window_settings()

    def init_ui(self):
        """初始化用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)

        # 创建分割器
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # 左侧：节点面板和工作流面板
        left_panel = self._create_left_panel()
        self.main_splitter.addWidget(left_panel)

        # 中间：画布
        self.main_splitter.addWidget(self.canvas)
        self.main_splitter.setStretchFactor(1, 3)  # 画布占主要空间

        # 右侧：属性面板和状态面板
        right_panel = self._create_right_panel()
        self.main_splitter.addWidget(right_panel)

        # 设置分割器比例
        self.main_splitter.setSizes([300, 1000, 300])

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 设置布局策略：顶部对齐，不拉伸
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        left_layout.setSpacing(10)  # 设置面板间距

        # 节点调色板
        self.node_palette = self._create_node_palette()
        self.node_palette.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left_layout.addWidget(self.node_palette)

        # 硬件管理面板
        self.hardware_panel = self._create_hardware_panel()
        self.hardware_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left_layout.addWidget(self.hardware_panel)

        # 添加弹簧，让面板不被拉伸到底部
        left_layout.addStretch()

        # 工作流管理面板
        self.workflow_panel = self._create_workflow_panel()
        self.workflow_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left_layout.addWidget(self.workflow_panel)

        return left_widget

    def _create_node_palette(self) -> QGroupBox:
        """创建节点调色板"""
        group = QGroupBox("节点库")
        layout = QVBoxLayout(group)

        # 创建节点列表 - 使用支持拖拽的自定义列表
        node_list = DraggableNodeList()
        node_list.setMaximumHeight(200)

        # 添加节点类型 - 包含执行器节点（删除硬件配置节点）
        node_types = [
            ("📥 输入节点（相机取图）", NodeType.INPUT),
            ("👁️ 视觉处理节点", NodeType.VISION),
            ("🦾 机械臂执行节点", NodeType.MOTION),
            ("⚡ 执行器节点", NodeType.EXECUTOR),
            ("📷 相机节点", NodeType.CAMERA),
            ("💡 光源节点", NodeType.LIGHT)
        ]

        for display_name, node_type in node_types:
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, node_type)
            node_list.addItem(item)

        # 双击添加节点
        node_list.itemDoubleClicked.connect(self._on_node_palette_double_clicked)

        # 添加提示文字 - 只占一行
        hint_label = QLabel("双击或拖拽添加节点到画布")
        hint_label.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")
        layout.addWidget(hint_label)
        layout.addWidget(node_list)

        # 添加预设工作流按钮
        preset_btn = QPushButton("加载预设工作流")
        preset_btn.clicked.connect(self._load_preset_workflow)
        layout.addWidget(preset_btn)
        
        # VMC配置按钮
        vmc_layout = QHBoxLayout()
        
        self.save_vmc_btn = QPushButton("🤖 保存VMC配置")
        self.save_vmc_btn.clicked.connect(self.save_vmc_config)
        self.save_vmc_btn.setStyleSheet("QPushButton { padding: 6px; background-color: #28a745; color: white; border-radius: 3px; font-size: 12px; }")
        vmc_layout.addWidget(self.save_vmc_btn)
        
        self.execute_vmc_btn = QPushButton("🚀 执行VMC工作流")
        self.execute_vmc_btn.clicked.connect(self.execute_vmc_workflow)
        self.execute_vmc_btn.setStyleSheet("QPushButton { padding: 6px; background-color: #dc3545; color: white; border-radius: 3px; font-size: 12px; }")
        vmc_layout.addWidget(self.execute_vmc_btn)
        
        layout.addLayout(vmc_layout)

        return group

    def _create_hardware_panel(self) -> QGroupBox:
        """创建硬件管理面板"""
        group = QGroupBox("硬件管理")
        layout = QVBoxLayout(group)

        # 硬件管理按钮布局 - 2x2网格
        button_grid = QGridLayout()

        # 相机管理按钮
        camera_btn = QPushButton("📷 相机管理")
        camera_btn.clicked.connect(self._open_camera_management)
        camera_btn.setMinimumHeight(40)
        button_grid.addWidget(camera_btn, 0, 0)

        # 光源管理按钮
        light_btn = QPushButton("💡 光源管理")
        light_btn.clicked.connect(self._open_light_management)
        light_btn.setMinimumHeight(40)
        button_grid.addWidget(light_btn, 0, 1)

        # 机械臂管理按钮
        robot_btn = QPushButton("🦾 机械臂管理")
        robot_btn.clicked.connect(self._open_robot_management)
        robot_btn.setMinimumHeight(40)
        button_grid.addWidget(robot_btn, 1, 0)

        # 硬件配置管理按钮
        config_btn = QPushButton("⚙️ 硬件配置")
        config_btn.clicked.connect(self._open_hardware_config)
        config_btn.setMinimumHeight(40)
        button_grid.addWidget(config_btn, 1, 1)

        layout.addLayout(button_grid)
        layout.addWidget(QLabel("单击按钮打开对应硬件管理界面"))

        return group

    def _create_workflow_panel(self) -> QGroupBox:
        """创建工作流管理面板"""
        group = QGroupBox("工作流管理")
        layout = QVBoxLayout(group)

        # 工作流信息
        self.workflow_info = QLabel("当前工作流: 无")
        layout.addWidget(self.workflow_info)

        # 执行控制
        control_layout = QHBoxLayout()

        self.execute_btn = QPushButton("▶️ 执行")
        self.execute_btn.clicked.connect(self.execute_workflow)
        control_layout.addWidget(self.execute_btn)

        self.step_btn = QPushButton("🔃 单步执行")
        self.step_btn.clicked.connect(self.step_execute_vmc_workflow)
        self.step_btn.setEnabled(False)
        control_layout.addWidget(self.step_btn)

        self.continue_btn = QPushButton("⏩ 继续执行")
        self.continue_btn.clicked.connect(self.continue_vmc_workflow)
        self.continue_btn.setEnabled(False)
        control_layout.addWidget(self.continue_btn)

        self.stop_btn = QPushButton("⏹️ 停止")
        self.stop_btn.clicked.connect(self.stop_workflow)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        layout.addLayout(control_layout)

        # 执行进度
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        # 步骤信息
        self.step_info = QLabel("步骤: 未开始")
        layout.addWidget(self.step_info)

        # 工作流状态
        self.workflow_status = QLabel("状态: 就绪")
        layout.addWidget(self.workflow_status)

        return group

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 属性面板
        self.properties_panel = self._create_properties_panel()
        right_layout.addWidget(self.properties_panel)

        # 状态面板
        self.status_panel = self._create_status_panel()
        right_layout.addWidget(self.status_panel)

        return right_widget

    def _create_properties_panel(self) -> QGroupBox:
        """创建属性面板"""
        group = QGroupBox("节点属性")
        layout = QVBoxLayout(group)

        # 节点信息
        self.node_info = QLabel("选择一个节点查看属性")
        self.node_info.setWordWrap(True)
        layout.addWidget(self.node_info)

        # 节点参数（可扩展）
        self.node_params = QWidget()
        self.node_params_layout = QVBoxLayout(self.node_params)
        layout.addWidget(self.node_params)

        return group

    def _create_status_panel(self) -> QGroupBox:
        """创建状态面板"""
        group = QGroupBox("系统状态")
        layout = QVBoxLayout(group)

        # VR系统状态
        self.vr_system_status = QLabel("VR系统: 未初始化")
        layout.addWidget(self.vr_system_status)

        # 连接状态
        self.connection_status = QLabel("连接数: 0")
        layout.addWidget(self.connection_status)

        # 执行日志
        layout.addWidget(QLabel("执行日志:"))
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        return group

    def init_menu_bar(self):
        """初始化菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        new_action = QAction("新建工作流", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_workflow)
        file_menu.addAction(new_action)

        open_action = QAction("打开工作流", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_workflow)
        file_menu.addAction(open_action)

        save_action = QAction("保存工作流", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_workflow)
        file_menu.addAction(save_action)

        save_as_action = QAction("另存为", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_workflow_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑")

        clear_action = QAction("清空画布", self)
        clear_action.triggered.connect(self.clear_canvas)
        edit_menu.addAction(clear_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图")

        fit_action = QAction("适应窗口", self)
        fit_action.triggered.connect(self.fit_in_window)
        view_menu.addAction(fit_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_toolbar(self):
        """初始化工具栏"""
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        # 常用操作
        new_action = QAction("新建", self)
        new_action.triggered.connect(self.new_workflow)
        toolbar.addAction(new_action)

        open_action = QAction("打开", self)
        open_action.triggered.connect(self.open_workflow)
        toolbar.addAction(open_action)

        save_action = QAction("保存", self)
        save_action.triggered.connect(self.save_workflow)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        # 执行控制
        # 单步调试
        single_step_action = QAction("🔃 单步调试", self)
        single_step_action.triggered.connect(self.single_step_execute)
        toolbar.addAction(single_step_action)

        # 继续执行
        continue_action = QAction("⏩ 继续执行", self)
        continue_action.triggered.connect(self.continue_execute)
        toolbar.addAction(continue_action)

        # 执行全部
        execute_all_action = QAction("▶️ 执行全部", self)
        execute_all_action.triggered.connect(self.execute_workflow)
        toolbar.addAction(execute_all_action)
        # 查看缓存数据
        buffer_view_action = QAction("🖼️ 查看缓存数据", self)
        buffer_view_action.triggered.connect(self.show_buffer_images)
        toolbar.addAction(buffer_view_action)

        toolbar.addSeparator()

        # 加载图像
        load_image_action = QAction("📁 加载图像", self)
        load_image_action.triggered.connect(self.load_image)
        toolbar.addAction(load_image_action)

        toolbar.addSeparator()

        # 停止
        stop_action = QAction("⏹️ 停止", self)
        stop_action.triggered.connect(self.stop_workflow)
        toolbar.addAction(stop_action)

    def init_status_bar(self):
        """初始化状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _connect_signals(self):
        """设置回调函数"""
        # 画布信号连接 - 使用正确的信号连接方式
        self.canvas.node_selected.connect(self.on_node_selected)

        # 画布状态更新回调
        self.canvas.status_update_callback = self.on_status_update

        # 设置画布的连接管理器引用
        self.canvas.connection_manager = self.connection_manager

        debug("VisionRobotDialog: Canvas signals connected successfully", "VisionRobotDialog")

    def _setup_initial_state(self):
        """设置初始状态"""
        # 添加默认的4个节点并连接
        self._add_default_nodes()

        # 更新状态显示
        self.update_status_display()

    def _add_default_nodes(self):
        """添加默认节点 - 使用相机节点作为输入"""
        # 添加相机节点
        debug(f"VisionRobotDialog: Adding default CAMERA node", "VisionRobotDialog")
        camera_node = self.canvas.add_node(NodeType.CAMERA, QPointF(50, 200))
        debug(f"VisionRobotDialog: Camera node created: {camera_node}", "VisionRobotDialog")

        # 添加视觉节点
        vision_node = self.canvas.add_node(NodeType.VISION, QPointF(300, 200))

        # 添加机械臂节点
        robot_node = self.canvas.add_node(NodeType.MOTION, QPointF(550, 200))

        # 添加执行器节点
        executor_node = self.canvas.add_node(NodeType.EXECUTOR, QPointF(800, 200))

        # 创建默认连接 - 包含执行器节点的完整流程
        # 相机 → 视觉处理
        if camera_node and vision_node:
            self.connection_manager.create_connection(camera_node, vision_node)

        # 视觉处理 → 机械臂执行
        if vision_node and robot_node:
            self.connection_manager.create_connection(vision_node, robot_node)

        # 机械臂执行 → 执行器
        if robot_node and executor_node:
            self.connection_manager.create_connection(robot_node, executor_node)

    # 事件处理
    def _on_node_palette_double_clicked(self, item: QListWidgetItem):
        """节点面板双击事件"""
        node_type = item.data(Qt.ItemDataRole.UserRole)
        if node_type:
            # 在画布中心添加节点
            canvas_center = self.canvas.mapToScene(
                self.canvas.width() // 2, self.canvas.height() // 2
            )
            self.canvas.add_node(node_type, canvas_center)

    def on_node_selected(self, node):
        """节点选择事件"""
        try:
            debug(f"VisionRobotDialog: on_node_selected called with node: {getattr(node, 'node_id', 'None')}", "VisionRobotDialog")
            debug(f"VisionRobotDialog: Node object type: {type(node)}", "VisionRobotDialog")

            if node:
                # 更新属性面板
                node_info = f"节点ID: {node.node_id}\n"
                node_type = getattr(node, 'node_type', None)
                if node_type:
                    node_info += f"节点类型: {node_type.value if hasattr(node_type, 'value') else str(node_type)}\n"
                else:
                    node_info += "节点类型: unknown\n"
                if hasattr(node, 'node_name'):
                    node_info += f"节点名称: {node.node_name}\n"
                if hasattr(node, 'state'):
                    node_info += f"节点状态: {node.state.value}"

                self.node_info.setText(node_info)
                debug(f"VisionRobotDialog: Updated node info for {node.node_id}", "VisionRobotDialog")

                # 高亮相关连接
                if hasattr(self.connection_manager, 'highlight_connections_for_node'):
                    self.connection_manager.highlight_connections_for_node(node, True)

                # Show parameter dialog if the node supports it
                if hasattr(node, 'show_param_dialog'):
                    debug(f"VisionRobotDialog: Node {node.node_id} has show_param_dialog method, calling it", "VisionRobotDialog")
                    try:
                        node.show_param_dialog()
                        debug(f"VisionRobotDialog: Successfully called show_param_dialog for node {node.node_id}", "VisionRobotDialog")
                    except Exception as e:
                        error(f"VisionRobotDialog: Failed to show parameter dialog for node {node.node_id}: {e}", "VisionRobotDialog")
                        import traceback
                        error(f"VisionRobotDialog: Traceback: {traceback.format_exc()}", "VisionRobotDialog")
                else:
                    debug(f"VisionRobotDialog: Node {node.node_id} does not have show_param_dialog method", "VisionRobotDialog")
            else:
                debug("VisionRobotDialog: Node is None, clearing selection", "VisionRobotDialog")
                self.node_info.setText("选择一个节点查看属性")
                # 清除所有高亮
                if hasattr(self.connection_manager, 'highlight_connections_for_node'):
                    self.connection_manager.highlight_connections_for_node(None, False)

        except Exception as e:
            error(f"VisionRobotDialog: Error in on_node_selected: {e}", "VisionRobotDialog")
            import traceback
            error(f"VisionRobotDialog: Traceback: {traceback.format_exc()}", "VisionRobotDialog")

    def on_execution_started(self):
        """执行开始事件"""
        self.execute_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, 0)  # 无限进度条
        self.workflow_status.setText("状态: 执行中...")
        self.add_log("工作流执行开始")

    def on_execution_finished(self):
        """执行完成事件"""
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.workflow_status.setText("状态: 执行完成")
        self.add_log("工作流执行完成")

    def on_status_update(self, message):
        """状态更新事件"""
        self.status_bar.showMessage(message, 3000)
        self.add_log(message)

    def on_vr_state_changed(self, state):
        """VR系统状态变化"""
        self.vr_system_status.setText(f"VR系统: {state.value}")

    def on_vr_phase_changed(self, phase):
        """VR系统阶段变化"""
        self.add_log(f"VR阶段: {phase.value}")

    # 工作流操作
    def execute_workflow(self):
        """执行工作流"""
        debug("开始执行工作流", "VisionRobotDialog")

        # 优先尝试从缓存加载配置
        cache_loaded = False
        if hasattr(self, 'cache_file_path') and self.cache_file_path and self.cache_file_path.exists():
            debug("尝试从缓存加载工作流配置", "VisionRobotDialog")
            cache_loaded = self.load_config_from_cache(safe_loading=True)
            if cache_loaded:
                self.add_log("已从缓存加载工作流配置")
            else:
                debug("缓存加载失败，使用当前画布配置", "VisionRobotDialog")
        else:
            debug("缓存文件不存在，使用当前画布配置", "VisionRobotDialog")

        # 执行工作流
        self.canvas.execute_workflow()

    def stop_workflow(self):
        """停止工作流"""
        self.canvas.stop_execution()

    def new_workflow(self):
        """新建工作流"""
        if self.is_project_modified:
            reply = QMessageBox.question(
                self, "新建工作流",
                "当前工作流未保存，是否保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_workflow()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.clear_canvas()
        self.current_workflow_file = None
        self.is_project_modified = False
        self.update_window_title()

    def open_workflow(self):
        """打开工作流"""
        if self.is_project_modified:
            reply = QMessageBox.question(
                self, "打开工作流",
                "当前工作流未保存，是否保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_workflow()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开工作流", "", "JSON文件 (*.json)"
        )
        if file_path:
            self.load_workflow_from_file(file_path)

    def save_workflow(self):
        """保存工作流"""
        if self.current_workflow_file:
            self.save_workflow_to_file(self.current_workflow_file)
        else:
            self.save_workflow_as()

    def save_workflow_as(self):
        """另存为工作流"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存工作流", "", "JSON文件 (*.json)"
        )
        if file_path:
            self.save_workflow_to_file(file_path)

    def clear_canvas(self):
        """清空画布"""
        reply = QMessageBox.question(
            self, "清空画布",
            "确定要清空画布吗？这将删除所有节点和连接。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.canvas.clear_canvas()
            self.is_project_modified = False
            self.update_window_title()

    def fit_in_window(self):
        """适应窗口"""
        self.canvas.fitInView(self.canvas.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def show_about(self):
        """显示关于信息"""
        QMessageBox.about(self, "关于", "视觉-机器人协作系统\n版本 1.0.0\n基于VMC框架")

    def update_status_display(self):
        """更新状态显示"""
        status = self.canvas.get_workflow_status()
        self.connection_status.setText(f"连接数: {status['connection_count']}")

    def build_execution_order(self):
        """构建节点执行顺序，用于右键参数配置对话框"""
        try:
            execution_order = []
            
            # 如果没有画布，返回空列表
            if not self.canvas:
                return execution_order
            
            # 获取所有节点
            all_nodes = list(self.canvas.nodes.values())
            if not all_nodes:
                return execution_order
            
            # 简单的拓扑排序，基于节点类型和连接关系
            # 1. 找到所有输入节点（没有输入连接的节点）
            input_nodes = []
            for node in all_nodes:
                has_input = False
                for connection in self.canvas.connections:
                    # 检查连接对象的有效性和连接关系
                    if not connection:
                        continue
                        
                    # 获取起始和结束节点，处理不同的连接对象结构
                    start_node = None
                    end_node = None
                    
                    # 方法1：通过start_item和end_item获取节点
                    if hasattr(connection, 'start_item') and hasattr(connection, 'end_item'):
                        start_node = connection.start_item
                        end_node = connection.end_item
                    # 方法2：通过start_port和end_port获取节点
                    elif hasattr(connection, 'start_port') and hasattr(connection, 'end_port'):
                        if (connection.start_port and hasattr(connection.start_port, 'parent_node') and
                            connection.end_port and hasattr(connection.end_port, 'parent_node')):
                            start_node = connection.start_port.parent_node
                            end_node = connection.end_port.parent_node
                    
                    # 如果找到有效连接且当前节点是目标节点，则标记为有输入
                    if end_node == node:
                        has_input = True
                        break
                        
                if not has_input:
                    input_nodes.append(node)
            
            # 2. 按照节点类型和Y坐标排序输入节点
            def node_type_priority(node):
                if not hasattr(node, 'node_type'):
                    return 10  # 未知类型放在最后
                    
                node_type = node.node_type
                if hasattr(node_type, 'value'):
                    node_type_value = node_type.value
                else:
                    node_type_value = str(node_type)
                    
                if node_type_value == "image_input":
                    return 1
                elif node_type_value == "input":
                    return 1
                elif node_type_value == "camera":
                    return 2
                elif node_type_value == "vision":
                    return 3
                elif node_type_value == "robot":
                    return 4
                else:
                    return 5
            
            # 安全排序，处理可能没有pos()方法的节点
            def get_node_position(node):
                try:
                    return node.pos().y()
                except:
                    return 0
            
            input_nodes.sort(key=lambda n: (node_type_priority(n), get_node_position(n)))
            execution_order.extend(input_nodes)
            
            # 3. 基于连接关系添加后续节点
            added_nodes = set(input_nodes)
            changed = True
            
            while changed:
                changed = False
                for connection in self.canvas.connections:
                    if not connection:
                        continue
                        
                    # 获取起始和结束节点
                    start_node = None
                    end_node = None
                    
                    # 同上，处理不同的连接对象结构
                    if hasattr(connection, 'start_item') and hasattr(connection, 'end_item'):
                        start_node = connection.start_item
                        end_node = connection.end_item
                    elif hasattr(connection, 'start_port') and hasattr(connection, 'end_port'):
                        if (connection.start_port and hasattr(connection.start_port, 'parent_node') and
                            connection.end_port and hasattr(connection.end_port, 'parent_node')):
                            start_node = connection.start_port.parent_node
                            end_node = connection.end_port.parent_node
                    
                    # 如果找到有效连接，执行拓扑排序逻辑
                    if start_node and end_node:
                        # 如果起始节点已添加，但目标节点未添加，则添加目标节点
                        if start_node in added_nodes and end_node not in added_nodes:
                            # 检查目标节点的所有输入源是否都已添加
                            can_add = True
                            for conn in self.canvas.connections:
                                if not conn:
                                    continue
                                    
                                # 获取连接的节点
                                conn_start = None
                                conn_end = None
                                
                                if hasattr(conn, 'start_item') and hasattr(conn, 'end_item'):
                                    conn_start = conn.start_item
                                    conn_end = conn.end_item
                                elif hasattr(conn, 'start_port') and hasattr(conn, 'end_port'):
                                    if (conn.start_port and hasattr(conn.start_port, 'parent_node') and
                                        conn.end_port and hasattr(conn.end_port, 'parent_node')):
                                        conn_start = conn.start_port.parent_node
                                        conn_end = conn.end_port.parent_node
                                
                                # 如果找到连接指向目标节点，检查源节点是否已添加
                                if conn_end == end_node and conn_start not in added_nodes:
                                    can_add = False
                                    break
                            
                            if can_add:
                                execution_order.append(end_node)
                                added_nodes.add(end_node)
                                changed = True
            
            # 4. 添加剩余未连接的节点
            for node in all_nodes:
                if node not in added_nodes:
                    execution_order.append(node)
            
            info(f"Built execution order with {len(execution_order)} nodes", "VisionRobotDialog")
            return execution_order
            
        except Exception as e:
            error(f"Failed to build execution order: {e}", "VisionRobotDialog")
            # 如果出错，返回所有节点的简单排序
            if self.canvas and hasattr(self.canvas, 'nodes'):
                return list(self.canvas.nodes.values())
            return []

    def update_window_title(self):
        """更新窗口标题"""
        title = "视觉-机器人协作系统"
        if self.current_workflow_file:
            title += f" - {Path(self.current_workflow_file).name}"
        if self.is_project_modified:
            title += " *"
        self.setWindowTitle(title)

    def add_log(self, message):
        """添加日志"""
        self.log_text.append(f"[{QTimer().remainingTime()}] {message}")
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _load_preset_workflow(self):
        """加载预设工作流"""
        self.clear_canvas()
        self._add_default_nodes()
        self.add_log("已加载预设工作流")

    # 文件操作
    def save_workflow_to_file(self, file_path):
        """保存工作流到文件"""
        try:
            workflow_data = {
                'nodes': [],
                'connections': []
            }

            # 保存节点
            for node_id, node in self.canvas.nodes.items():
                node_data = {
                    'id': node.node_id,
                    'type': node.node_type.value,
                    'position': {
                        'x': node.pos().x(),
                        'y': node.pos().y()
                    },
                    'properties': getattr(node, 'properties', {})
                }
                workflow_data['nodes'].append(node_data)

            # 保存连接
            for connection in self.canvas.connections:
                conn_data = {
                    'start_node': connection.start_port.parent_node.node_id,
                    'start_port': connection.start_port.port_id,
                    'end_node': connection.end_port.parent_node.node_id,
                    'end_port': connection.end_port.port_id
                }
                workflow_data['connections'].append(conn_data)

            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, indent=2, ensure_ascii=False)

            self.current_workflow_file = file_path
            self.is_project_modified = False
            self.update_window_title()
            self.add_log(f"工作流已保存到: {file_path}")

        except Exception as e:
            error(f"保存工作流失败: {e}", "VisionRobotDialog")
            QMessageBox.critical(self, "错误", f"保存工作流失败: {e}")

    def load_workflow_from_file(self, file_path):
        """从文件加载工作流"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)

            # 清空当前画布
            self.canvas.clear_canvas()

            # 加载节点
            node_map = {}
            for node_data in workflow_data.get('nodes', []):
                node_type = NodeType(node_data['type'])
                position = QPointF(
                    node_data['position']['x'],
                    node_data['position']['y']
                )
                node = self.canvas.add_node(node_type, position)
                if node:
                    # 设置节点属性
                    if hasattr(node, 'properties'):
                        node.properties.update(node_data.get('properties', {}))
                    node_map[node_data['id']] = node

            # 加载连接
            for conn_data in workflow_data.get('connections', []):
                start_node = node_map.get(conn_data['start_node'])
                end_node = node_map.get(conn_data['end_node'])

                if start_node and end_node:
                    # 查找对应端口
                    start_port = None
                    end_port = None

                    for port in start_node.get_output_ports():
                        if port.port_id == conn_data['start_port']:
                            start_port = port
                            break

                    for port in end_node.get_input_ports():
                        if port.port_id == conn_data['end_port']:
                            end_port = port
                            break

                    if start_port and end_port:
                        self.connection_manager.create_connection(start_port, end_port)

            self.current_workflow_file = file_path
            self.is_project_modified = False
            self.update_window_title()
            self.add_log(f"工作流已从文件加载: {file_path}")

        except Exception as e:
            error(f"加载工作流失败: {e}", "VisionRobotDialog")
            QMessageBox.critical(self, "错误", f"加载工作流失败: {e}")

    def init_config_cache(self):
        """初始化配置缓存机制"""
        import os
        import tempfile
        from datetime import datetime

        try:
            # 使用AppConfigManager获取vision_robot_temp目录
            from core.managers.app_config import AppConfigManager
            app_config = AppConfigManager()
            temp_dir = app_config.vision_robot_temp_subdir
        except Exception:
            # fallback到workspace/temp/vision_robot_temp
            temp_dir = Path("workspace") / "temp" / "vision_robot_temp"
        finally:
            temp_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一的缓存文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.cache_file_path = temp_dir / f"vr_workflow_config_{timestamp}.json"

        debug(f"初始化VR工作流配置缓存，缓存文件: {self.cache_file_path}", "VisionRobotDialog")

        # 注意：不自动加载缓存配置，确保使用默认的相机节点配置

    def trigger_save_to_cache(self):
        """触发延迟保存到缓存（防抖）"""
        if hasattr(self, '_global_save_timer'):
            self._global_save_timer.stop()
            self._global_save_timer.start(1000)  # 1秒后保存

    def save_config_to_cache(self):
        """实时保存配置到缓存文件 - 按节点实际顺序保存"""
        if not self.cache_file_path:
            return

        try:
            config = {
                'nodes': [],
                'connections': [],
                'workflow_settings': {
                    'execution_mode': getattr(self, 'execution_mode', 'continuous'),
                    'auto_save': getattr(self, 'auto_save', True)
                }
            }

            # 按节点实际顺序保存配置
            for item in self.canvas.scene.items():
                if hasattr(item, 'node_id'):
                    # Collect all important node properties
                    properties = getattr(item, 'properties', {})
                    
                    # Add hardware-specific properties for VMC nodes
                    if hasattr(item, 'selected_hardware_id') and item.selected_hardware_id:
                        properties['selected_hardware_id'] = item.selected_hardware_id
                        
                        # 获取硬件配置（使用hardware_config_dialog.py的格式）
                        hardware_config = self._get_hardware_config_from_node(item)
                        if hardware_config:
                            properties['hardware_config'] = hardware_config
                    
                    # Add algorithm configurations for vision nodes
                    if hasattr(item, 'algorithm_configs') and item.algorithm_configs:
                        properties['algorithm_configs'] = item.algorithm_configs
                        
                        # 获取视觉配置（使用canvas_dialog.py的格式）
                        vision_config = self._get_vision_config_from_node(item)
                        if vision_config:
                            properties['vision_config'] = vision_config
                    
                    # Add auto-trigger config for camera nodes
                    if hasattr(item, 'auto_trigger_config') and item.auto_trigger_config:
                        properties['auto_trigger_config'] = item.auto_trigger_config
                    
                    node_config = {
                        'node_id': item.node_id,
                        'node_type': item.node_type.value,
                        'position': {'x': item.pos().x(), 'y': item.pos().y()},
                        'state': item.state.value,
                        'properties': properties
                    }
                    config['nodes'].append(node_config)

            # 保存连接信息
            for connection in self.connection_manager.connections:
                conn_config = {
                    'start_node': connection.start_port.parent_node.node_id,
                    'start_port': connection.start_port.port_id,
                    'end_node': connection.end_port.parent_node.node_id,
                    'end_port': connection.end_port.port_id
                }
                config['connections'].append(conn_config)

            # 写入缓存文件
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            debug(f"VR工作流配置已保存到缓存文件: {self.cache_file_path}", "VisionRobotDialog")
            
            # 统计保存的节点类型
            camera_count = sum(1 for node in config['nodes'] if node['node_type'] == 'camera')
            robot_count = sum(1 for node in config['nodes'] if node['node_type'] == 'robot')
            vision_count = sum(1 for node in config['nodes'] if node['node_type'] == 'vision')
            debug(f"  保存统计: {camera_count} 相机节点, {robot_count} 机械臂节点, {vision_count} 视觉节点", "VisionRobotDialog")

        except Exception as e:
            error(f"保存配置到缓存失败: {e}", "VisionRobotDialog")
    
    def _get_hardware_config_from_node(self, node):
        """从硬件节点获取配置，使用hardware_config_dialog.py的格式"""
        try:
            hardware_id = getattr(node, 'selected_hardware_id', None)
            if not hardware_id:
                return None
                
            # 从硬件配置文件中获取基础配置
            if hasattr(node, 'hardware_config') and hardware_id in node.hardware_config:
                base_config = node.hardware_config[hardware_id].copy()
            else:
                # 创建基础配置结构
                node_type = node.node_type.value
                if node_type == 'camera':
                    base_config = {
                        'id': hardware_id,
                        'name': f'相机_{hardware_id}',
                        'type': 'camera',
                        'brand': 'unknown',
                        'model': 'unknown',
                        'connection_type': 'network',
                        'description': f'相机节点 {hardware_id}',
                        'connection_params': {},
                        'hardware_type': '相机',
                        'original_type': 'camera'
                    }
                elif node_type == 'robot':
                    base_config = {
                        'id': hardware_id,
                        'name': f'机械臂_{hardware_id}',
                        'type': 'robot',
                        'brand': 'unknown',
                        'model': 'unknown',
                        'connection_type': 'network',
                        'description': f'机械臂节点 {hardware_id}',
                        'connection_params': {},
                        'hardware_type': '机械臂',
                        'original_type': 'robot'
                    }
                elif node_type == 'light':
                    base_config = {
                        'id': hardware_id,
                        'name': f'光源_{hardware_id}',
                        'type': 'light',
                        'brand': 'unknown',
                        'model': 'unknown',
                        'connection_type': 'network',
                        'description': f'光源节点 {hardware_id}',
                        'connection_params': {},
                        'hardware_type': '光源',
                        'original_type': 'light'
                    }
                else:
                    return None
            
            # 添加节点特定配置
            # 相机自动触发配置
            if hasattr(node, 'auto_trigger_config') and node.auto_trigger_config:
                base_config['auto_trigger'] = node.auto_trigger_config
            
            return base_config
            
        except Exception as e:
            error(f"获取硬件节点配置失败: {e}", "VisionRobotDialog")
            return None
    
    def _get_vision_config_from_node(self, node):
        """从视觉节点获取配置，使用canvas_dialog.py的格式"""
        try:
            if not hasattr(node, 'algorithm_configs') or not node.algorithm_configs:
                return None
                
            # 这里应该调用canvas_dialog.py的保存机制
            # 由于我们无法直接访问canvas_dialog实例，这里简化处理
            vision_config = {
                'algorithm_configs': node.algorithm_configs,
                'node_id': node.node_id,
                'timestamp': QDateTime.currentDateTime().toString()
            }
            
            return vision_config
            
        except Exception as e:
            error(f"获取视觉节点配置失败: {e}", "VisionRobotDialog")
            return None
    
    def _restore_hardware_config_to_node(self, node, hardware_config):
        """将硬件配置恢复到节点"""
        try:
            if hasattr(node, 'selected_hardware_id'):
                node.selected_hardware_id = hardware_config.get('id')
                debug(f"恢复硬件ID到节点 {node.node_id}: {node.selected_hardware_id}", "VisionRobotDialog")
            
            if hasattr(node, 'hardware_config'):
                # 确保hardware_config是字典格式
                if not isinstance(node.hardware_config, dict):
                    node.hardware_config = {}
                node.hardware_config[hardware_config.get('id')] = hardware_config
                debug(f"恢复硬件配置到节点 {node.node_id}", "VisionRobotDialog")
            
            # 恢复自动触发配置
            if 'auto_trigger' in hardware_config and hasattr(node, 'auto_trigger_config'):
                node.auto_trigger_config = hardware_config['auto_trigger']
                debug(f"恢复自动触发配置到节点 {node.node_id}", "VisionRobotDialog")
                
        except Exception as e:
            error(f"恢复硬件配置到节点失败: {e}", "VisionRobotDialog")
    
    def _restore_vision_config_to_node(self, node, vision_config):
        """将视觉配置恢复到节点"""
        try:
            if hasattr(node, 'algorithm_configs'):
                node.algorithm_configs = vision_config.get('algorithm_configs', [])
                debug(f"恢复算法配置到视觉节点 {node.node_id}: {len(node.algorithm_configs)} 个配置", "VisionRobotDialog")
                
        except Exception as e:
            error(f"恢复视觉配置到节点失败: {e}", "VisionRobotDialog")
    
    def _auto_save_initial_state(self):
        """检查画布中是否已有节点，如果有则自动保存初始状态"""
        try:
            if hasattr(self.canvas, 'scene'):
                # 统计画布中的节点数量
                node_count = 0
                for item in self.canvas.scene.items():
                    if hasattr(item, 'node_id'):
                        node_count += 1
                
                if node_count > 0:
                    debug(f"画布中发现 {node_count} 个节点，自动保存初始状态到缓存", "VisionRobotDialog")
                    # 生成VMC配置并保存到缓存
                    vmc_config = self._generate_vmc_config()
                    self._save_vmc_config_to_cache(vmc_config)
                    debug(f"初始状态已自动保存到缓存文件", "VisionRobotDialog")
                else:
                    debug("画布中没有节点，跳过初始状态保存", "VisionRobotDialog")
            else:
                debug("画布场景未初始化，跳过初始状态保存", "VisionRobotDialog")
                
        except Exception as e:
            error(f"自动保存初始状态失败: {e}", "VisionRobotDialog")

    def load_config_from_cache(self, safe_loading=True) -> bool:
        """从缓存文件加载配置"""
        if not self.cache_file_path or not self.cache_file_path.exists():
            debug("缓存文件不存在，无法加载配置", "VisionRobotDialog")
            return False

        try:
            with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if not config:
                debug("缓存文件为空或无效", "VisionRobotDialog")
                return False

            debug(f"从缓存文件加载VR工作流配置: {self.cache_file_path}", "VisionRobotDialog")

            # 清空当前画布
            self.canvas.clear_canvas()

            # 恢复节点
            for node_config in config.get('nodes', []):
                node_type = NodeType(node_config['node_type'])
                position = QPointF(node_config['position']['x'], node_config['position']['y'])

                # 创建节点（这里需要根据节点类型创建相应的节点）
                node = self.canvas.create_node_by_type(node_type, position)
                if node:
                    node.node_id = node_config['node_id']
                    node.set_state(NodeState(node_config['state']))
                    
                    # 恢复节点属性
                    properties = node_config.get('properties', {})
                    node.properties = properties
                    
                    # 恢复硬件配置
                    if 'hardware_config' in properties:
                        hardware_config = properties['hardware_config']
                        self._restore_hardware_config_to_node(node, hardware_config)
                    
                    # 恢复视觉配置  
                    if 'vision_config' in properties:
                        vision_config = properties['vision_config']
                        self._restore_vision_config_to_node(node, vision_config)
                    
                    # 恢复自动触发配置
                    if 'auto_trigger_config' in properties:
                        node.auto_trigger_config = properties['auto_trigger_config']

            # 恢复连接
            for conn_config in config.get('connections', []):
                # 查找对应的节点和端口
                start_node = None
                end_node = None

                for item in self.canvas.scene.items():
                    if hasattr(item, 'node_id'):
                        if item.node_id == conn_config['start_node']:
                            start_node = item
                        elif item.node_id == conn_config['end_node']:
                            end_node = item

                if start_node and end_node:
                    # 使用端口系统创建连接
                    self.connection_manager.create_connection(start_node, end_node)

            # 恢复工作流设置
            workflow_settings = config.get('workflow_settings', {})
            if 'execution_mode' in workflow_settings:
                self.execution_mode = workflow_settings['execution_mode']
            if 'auto_save' in workflow_settings:
                self.auto_save = workflow_settings['auto_save']

            return True

        except Exception as e:
            error(f"从缓存加载配置失败: {e}", "VisionRobotDialog")
            return False

    def single_step_execute(self):
        """单步执行"""
        debug("开始单步执行", "VisionRobotDialog")

        # 优先尝试从缓存加载配置
        if hasattr(self, 'cache_file_path') and self.cache_file_path and self.cache_file_path.exists():
            debug("单步执行：尝试从缓存加载工作流配置", "VisionRobotDialog")
            cache_loaded = self.load_config_from_cache(safe_loading=True)
            if cache_loaded:
                self.add_log("单步执行：已从缓存加载配置")

        if hasattr(self.canvas, 'single_step_execute'):
            self.canvas.single_step_execute()
        else:
            self.add_log("画布不支持单步执行")

    def continue_execute(self):
        """继续执行"""
        debug("继续执行", "VisionRobotDialog")

        # 优先尝试从缓存加载配置
        if hasattr(self, 'cache_file_path') and self.cache_file_path and self.cache_file_path.exists():
            debug("继续执行：尝试从缓存加载工作流配置", "VisionRobotDialog")
            cache_loaded = self.load_config_from_cache(safe_loading=True)
            if cache_loaded:
                self.add_log("继续执行：已从缓存加载配置")

        if hasattr(self.canvas, 'continue_execute'):
            self.canvas.continue_execute()
        else:
            self.add_log("画布不支持继续执行")

    def load_image(self):
        """加载图像"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择图像文件", "",
                "图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff);;所有文件 (*)"
            )
            if file_path:
                # 这里应该将图像加载到输入节点
                self.add_log(f"已选择图像文件: {file_path}")
                debug(f"加载图像: {file_path}", "VisionRobotDialog")
                # TODO: 实现将图像设置到输入节点的逻辑
        except Exception as e:
            error(f"加载图像失败: {e}", "VisionRobotDialog")

    def show_buffer_images(self):
        """显示所有缓存数据"""
        try:
            debug("VisionRobotDialog: Showing buffer images", "VisionRobotDialog")
            if hasattr(self.canvas, 'show_all_buffer_images'):
                self.canvas.show_all_buffer_images()
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "缓存数据", "画布不支持缓存数据查看功能")
                warning("Canvas does not support buffer data viewing", "VisionRobotDialog")
        except Exception as e:
            error(f"显示缓存数据失败: {e}", "VisionRobotDialog")

    def _load_window_settings(self):
        """加载窗口设置"""
        try:
            # 使用统一管理器加载窗口状态
            success = self.window_settings_manager.load_window_state(
                self,
                "vision_robot_dialog",
                default_geometry=(100, 100, 1600, 1000)
            )

            if success:
                # 尝试恢复分割器状态
                window_settings = self.window_settings_manager.get_window_settings("vision_robot_dialog")
                if (window_settings and
                    'additional_data' in window_settings and
                    'main_splitter_state' in window_settings['additional_data'] and
                    hasattr(self, 'main_splitter')):
                    try:
                        import binascii
                        splitter_state = binascii.unhexlify(window_settings['additional_data']['main_splitter_state'])
                        self.main_splitter.restoreState(splitter_state)
                        info("视觉-机器人协作对话框分割器状态恢复成功", "VisionRobotDialog")
                    except Exception as e:
                        debug(f"恢复分割器状态失败: {e}", "VisionRobotDialog")
            else:
                # 如果加载失败，使用默认分割器比例
                if hasattr(self, 'main_splitter'):
                    self.main_splitter.setSizes([300, 1000, 300])

        except Exception as e:
            error(f"加载窗口设置失败: {e}", "VisionRobotDialog")

    def save_window_settings(self):
        """保存窗口设置"""
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
                "vision_robot_dialog",
                additional_data
            )

            if success:
                info("视觉-机器人协作对话框设置保存完成", "VisionRobotDialog")
            else:
                warning("视觉-机器人协作对话框设置保存失败", "VisionRobotDialog")

        except Exception as e:
            error(f"保存窗口设置失败: {e}", "VisionRobotDialog")

    def closeEvent(self, event):
        """关闭事件"""
        try:
            # 保存窗口设置
            self.save_window_settings()

            info("视觉-机器人协作系统已关闭", "VisionRobotDialog")
            event.accept()

        except Exception as e:
            error(f"关闭时出错: {e}", "VisionRobotDialog")
            event.accept()

    def _open_camera_management(self):
        """打开相机管理"""
        try:
            info("打开相机管理界面", "VisionRobotDialog", LogCategory.SOFTWARE)

            # 创建相机管理对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("相机管理")
            dialog.setMinimumSize(800, 600)

            # 使用相机管理的Tab组件 - 需要提供CameraService参数
            layout = QVBoxLayout(dialog)
            try:
                # 尝试导入和创建CameraService
                from core import CameraService
                camera_service = CameraService()
                camera_tab = CameraControlTab(camera_service)
                layout.addWidget(camera_tab)
            except Exception as camera_error:
                # 如果无法创建CameraService，显示错误信息
                error_label = QLabel(f"相机服务初始化失败: {camera_error}")
                layout.addWidget(error_label)

            dialog.exec()

        except Exception as e:
            error(f"打开相机管理失败: {e}", "VisionRobotDialog")
            QMessageBox.critical(self, "错误", f"无法打开相机管理: {e}")

    def _open_light_management(self):
        """打开光源管理"""
        try:
            info("打开光源管理界面", "VisionRobotDialog")

            # 创建光源管理对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("光源管理")
            dialog.setMinimumSize(600, 400)

            # 使用光源管理的Tab组件 - 需要提供LightService参数
            layout = QVBoxLayout(dialog)
            try:
                # 尝试导入和创建LightService
                from core.services.light_service import LightService
                light_service = LightService()
                light_tab = LightControlTab(light_service)
                layout.addWidget(light_tab)
            except Exception as light_error:
                # 如果无法创建LightService，显示错误信息
                error_label = QLabel(f"光源服务初始化失败: {light_error}")
                layout.addWidget(error_label)

            dialog.exec()

        except Exception as e:
            error(f"打开光源管理失败: {e}", "VisionRobotDialog")
            QMessageBox.critical(self, "错误", f"无法打开光源管理: {e}")

    def _open_robot_management(self):
        """打开机械臂管理"""
        try:
            info("打开机械臂管理界面", "VisionRobotDialog")

            # 创建机械臂管理对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("机械臂管理")
            dialog.setMinimumSize(800, 600)

            # 使用机械臂管理的Tab组件 - 需要提供RobotService参数
            layout = QVBoxLayout(dialog)
            try:
                # 尝试导入和创建RobotService
                from core.services.robot_service import RobotService
                robot_service = RobotService()
                robot_tab = RobotControlTab(robot_service)
                layout.addWidget(robot_tab)
            except Exception as robot_error:
                # 如果无法创建RobotService，显示错误信息
                error_label = QLabel(f"机械臂服务初始化失败: {robot_error}")
                layout.addWidget(error_label)

            dialog.exec()

        except Exception as e:
            error(f"打开机械臂管理失败: {e}", "VisionRobotDialog")
            QMessageBox.critical(self, "错误", f"无法打开机械臂管理: {e}")

    def _open_hardware_config(self):
        """打开硬件配置管理"""
        try:
            info("打开硬件配置管理界面", "VisionRobotDialog")

            # 创建硬件配置管理对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("硬件配置管理")
            dialog.setMinimumSize(1000, 700)

            # 使用硬件配置Tab组件
            layout = QVBoxLayout(dialog)
            try:
                # 硬件配置Tab不需要额外参数
                hardware_config_tab = HardwareConfigTab(parent=dialog)
                layout.addWidget(hardware_config_tab)
            except Exception as config_error:
                # 如果无法创建硬件配置Tab，显示错误信息
                error_label = QLabel(f"硬件配置初始化失败: {config_error}")
                layout.addWidget(error_label)

            dialog.exec()

        except Exception as e:
            error(f"打开硬件配置管理失败: {e}", "VisionRobotDialog")
            QMessageBox.critical(self, "错误", f"无法打开硬件配置管理: {e}")

    def save_vmc_config(self):
        """保存VMC工作流配置到文件"""
        try:
            # 检查画布上是否有节点
            if not hasattr(self.canvas, 'scene') or len(self.canvas.scene.items()) == 0:
                QMessageBox.warning(self, '警告', '当前画布上没有节点，无法保存VMC配置。\n请先添加相机、视觉处理或机械臂节点。')
                return
            
            # 生成VMC配置
            vmc_config = self._generate_vmc_config()
            
            # 让用户选择保存位置
            default_name = f"vmc_workflow_{int(time.time())}.json"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                '保存VMC工作流配置',
                default_name,
                'JSON文件 (*.json);;所有文件 (*)'
            )
            
            if not file_path:
                debug("用户取消了VMC配置保存", "VisionRobotDialog")
                return
            
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(vmc_config, f, indent=2, ensure_ascii=False)
            
            # 显示成功消息
            node_count = len(vmc_config.get('vmc_workflow', {}).get('nodes', []))
            connection_count = len(vmc_config.get('vmc_workflow', {}).get('connections', []))
            
            success_msg = f"""VMC工作流配置已成功保存！

文件位置: {file_path}
节点数量: {node_count} 个
连接数量: {connection_count} 个

配置包含:
- 相机节点配置和触发参数
- 视觉处理算法配置
- 机械臂连接和移动参数
- 节点间的数据流连接

该配置文件可用于VMC Pipeline Executor执行完整的工作流。"""
            
            QMessageBox.information(self, '保存成功', success_msg)
            self.add_log(f"VMC配置已保存: {Path(file_path).name}")
            
            # 同时保存到缓存目录
            self._save_vmc_config_to_cache(vmc_config)
            
        except Exception as e:
            error_msg = f"保存VMC配置失败: {str(e)}"
            debug(error_msg, "VisionRobotDialog")
            QMessageBox.critical(self, '错误', error_msg)

    def _generate_vmc_config(self) -> Dict[str, Any]:
        """生成VMC配置格式"""
        try:
            vmc_config = {
                "vmc_workflow": {
                    "name": "VMR Canvas Workflow",
                    "description": "从视觉-机器人画布生成的VMC工作流配置",
                    "version": "1.0.0",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "nodes": [],
                    "connections": []
                }
            }
            
            # 优先从canvas.nodes字典遍历（保持节点顺序）
            if hasattr(self.canvas, 'nodes') and self.canvas.nodes:
                debug(f"VMC: Generating config from canvas.nodes dictionary with {len(self.canvas.nodes)} nodes", "VisionRobotDialog")
                for node_id, node in self.canvas.nodes.items():
                    if hasattr(node, 'node_type') and hasattr(node, 'node_id'):
                        node_type = node.node_type
                        
                        # 只包含VMC相关的节点类型
                        vmc_type = self._map_node_type_to_vmc_type(node_type)
                        if vmc_type:
                            node_config = {
                                "id": node.node_id,
                                "type": vmc_type,
                                "name": getattr(node, 'node_name', f"{vmc_type}_{node.node_id}"),
                                "config": self._get_node_config(node)
                            }
                            
                            # 添加布局信息
                            node_pos = node.pos()
                            node_config["layout"] = {
                                "position": {
                                    "x": float(node_pos.x()),
                                    "y": float(node_pos.y())
                                }
                            }
                            
                            vmc_config["vmc_workflow"]["nodes"].append(node_config)
            else:
                # 备用方案：遍历画布场景中的所有项目
                debug(f"VMC: canvas.nodes not available, falling back to scene.items()", "VisionRobotDialog")
                for item in self.canvas.scene.items():
                    if hasattr(item, 'node_type') and hasattr(item, 'node_id'):
                        node_type = item.node_type
                        
                        # 只包含VMC相关的节点类型
                        vmc_type = self._map_node_type_to_vmc_type(node_type)
                        if vmc_type:
                            node_config = {
                                "id": item.node_id,
                                "type": vmc_type,
                                "name": getattr(item, 'node_name', f"{vmc_type}_{item.node_id}"),
                                "config": self._get_node_config(item)
                            }
                            
                            # 添加布局信息
                            node_pos = item.pos()
                            node_config["layout"] = {
                                "position": {
                                    "x": float(node_pos.x()),
                                    "y": float(node_pos.y())
                                }
                            }
                            
                            vmc_config["vmc_workflow"]["nodes"].append(node_config)
            
            # 生成连接配置
            if hasattr(self.canvas, 'connections'):
                for connection in self.canvas.connections:
                    # 使用start_item和end_item（而不是start_node和end_node）
                    start_node = connection.start_item if hasattr(connection, 'start_item') else None
                    end_node = connection.end_item if hasattr(connection, 'end_item') else None
                    
                    if start_node and end_node:
                        # 只包含VMC节点之间的连接
                        start_vmc_type = self._map_node_type_to_vmc_type(start_node.node_type)
                        end_vmc_type = self._map_node_type_to_vmc_type(end_node.node_type)
                        
                        if start_vmc_type and end_vmc_type:
                            connection_config = {
                                "from": start_node.node_id,
                                "to": end_node.node_id,
                                "data_type": self._map_connection_data_type(start_vmc_type, end_vmc_type)
                            }
                            
                            vmc_config["vmc_workflow"]["connections"].append(connection_config)
            
            return vmc_config
            
        except Exception as e:
            debug(f"生成VMC配置失败: {str(e)}", "VisionRobotDialog")
            # 返回空的VMC配置
            return {
                "vmc_workflow": {
                    "name": "Empty VMC Workflow",
                    "description": "生成VMC配置时出错",
                    "version": "1.0.0",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "nodes": [],
                    "connections": []
                }
            }

    def _map_node_type_to_vmc_type(self, node_type) -> Optional[str]:
        """将节点类型映射到VMC节点类型"""
        from .nodes import NodeType
        
        mapping = {
            NodeType.INPUT: "camera",  # 输入节点对应相机
            NodeType.CAMERA: "camera",
            NodeType.VISION: "vision",
            NodeType.MOTION: "robot",
            NodeType.EXECUTOR: "robot",  # 执行器节点也对应机器人
            NodeType.LIGHT: None  # 光源节点不在VMC工作流中
        }
        return mapping.get(node_type)

    def _map_connection_data_type(self, from_type: str, to_type: str) -> str:
        """映射连接的数据类型"""
        # 相机到视觉
        if from_type == "camera" and to_type == "vision":
            return "image"
        # 视觉到机械臂
        elif from_type == "vision" and to_type == "robot":
            return "position_data"
        else:
            return "data"

    def _get_node_config(self, node) -> Dict[str, Any]:
        """获取节点配置"""
        config = {}
        
        # 从节点的属性中获取配置
        if hasattr(node, 'properties'):
            config.update(node.properties)
        
        # 根据节点类型设置默认配置
        from .nodes import NodeType
        
        if node.node_type == NodeType.INPUT or node.node_type == NodeType.CAMERA:
            # 相机硬件ID
            if hasattr(node, 'selected_hardware_id') and node.selected_hardware_id:
                config['hardware_id'] = node.selected_hardware_id
            else:
                config['hardware_id'] = "camera_001"
            
            # 相机参数
            config.update({
                "trigger_mode": "software",
                "exposure_time": 1000.0,
                "gain": 1.0,
                "save_image": True
            })
            
            # 自动触发配置
            if hasattr(node, 'auto_trigger_config') and node.auto_trigger_config:
                config['auto_trigger'] = node.auto_trigger_config
                
        elif node.node_type == NodeType.VISION:
            # 视觉算法配置 - 优先从algorithm_configs获取
            if hasattr(node, 'algorithm_configs') and node.algorithm_configs:
                config['algorithm_configs'] = node.algorithm_configs
                debug(f"VMC Vision: Found {len(node.algorithm_configs)} algorithm configs in vision node {node.node_id}", "VisionRobotDialog")
            
            # 视觉配置文件
            if hasattr(node, 'vision_config_file') and node.vision_config_file:
                config['algorithm_config_file'] = node.vision_config_file
            else:
                config['algorithm_config_file'] = "workspace/pipeline/vmc_vision_config.json"
            
            config['output_mapping'] = {"target_position": "result.center", "confidence": "result.confidence"}
            
        elif node.node_type == NodeType.MOTION or node.node_type == NodeType.EXECUTOR:
            # 机械臂硬件ID
            if hasattr(node, 'selected_hardware_id') and node.selected_hardware_id:
                config['hardware_id'] = node.selected_hardware_id
            else:
                config['hardware_id'] = "robot_001"
            
            config.update({
                "connection_config": {"ip": "192.168.1.100", "port": 30003},
                "speed": 50.0,
                "approach_distance": 50.0,
                "safety_height": 200.0
            })
        
        return config

    def _save_vmc_config_to_cache(self, vmc_config: Dict[str, Any]):
        """保存VMC配置到缓存目录"""
        try:
            from core.managers.app_config import AppConfigManager
            
            # 获取配置管理器
            config_manager = AppConfigManager()
            
            # 获取临时目录路径
            temp_dir = config_manager.workspace_dir / "temp" / "vmc_tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成配置文件路径
            timestamp = int(time.time())
            config_file = temp_dir / f"vmc_canvas_{timestamp}.json"
            
            # 保存配置
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(vmc_config, f, indent=2, ensure_ascii=False)
            
            # 同时保存一个最新版本的文件
            latest_file = temp_dir / "vmc_canvas_latest.json"
            with open(latest_file, 'w', encoding='utf-8') as f:
                json.dump(vmc_config, f, indent=2, ensure_ascii=False)
            
            debug(f"VMC配置已缓存到: {config_file}", "VisionRobotDialog")
            info(f"VMC配置已保存，包含 {len(vmc_config.get('vmc_workflow', {}).get('nodes', []))} 个节点", "VisionRobotDialog")
            
        except Exception as e:
            debug(f"VMC配置缓存失败: {str(e)}", "VisionRobotDialog")

    def execute_vmc_workflow(self):
        """执行VMC工作流"""
        try:
            # 检查是否有节点
            if not hasattr(self.canvas, 'scene') or len(self.canvas.scene.items()) == 0:
                QMessageBox.warning(self, '警告', '当前画布上没有节点，无法执行VMC工作流。\n请先添加相机、视觉处理或机械臂节点。')
                return
            
            # 生成并保存配置到缓存
            vmc_config = self._generate_vmc_config()
            self._save_vmc_config_to_cache(vmc_config)
            
            # 创建执行进度对话框
            from PyQt6.QtWidgets import QProgressDialog, QVBoxLayout, QLabel, QTextEdit
            progress_dialog = QProgressDialog("正在执行VMC工作流...", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("VMC工作流执行")
            progress_dialog.setModal(True)
            progress_dialog.setMinimumDuration(0)
            
            # 添加详细日志显示
            log_widget = QTextEdit()
            log_widget.setReadOnly(True)
            log_widget.setMaximumHeight(200)
            
            layout = QVBoxLayout()
            layout.addWidget(QLabel("执行日志:"))
            layout.addWidget(log_widget)
            progress_dialog.setLayout(layout)
            
            progress_dialog.show()
            
            def log_message(message: str):
                """添加日志消息"""
                log_widget.append(f"[{time.strftime('%H:%M:%S')}] {message}")
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
            
            log_message("开始执行VMC工作流...")
            
            # 在后台线程执行VMC工作流
            from PyQt6.QtCore import QThread, pyqtSignal
            
            class VMCExecutionThread(QThread):
                progress_updated = pyqtSignal(int)
                log_updated = pyqtSignal(str)
                execution_completed = pyqtSignal(object)
                
                def __init__(self, config_path: str):
                    super().__init__()
                    self.config_path = config_path
                    self._cancelled = False
                
                def cancel(self):
                    self._cancelled = True
                
                def run(self):
                    try:
                        from core.managers.vmc_pipeline_executor import VMCPipelineExecutor
                        
                        self.log_updated.emit("初始化VMC执行器...")
                        self.progress_updated.emit(10)
                        
                        executor = VMCPipelineExecutor()
                        
                        # 添加进度回调
                        def on_workflow_started():
                            self.log_updated.emit("VMC工作流开始执行")
                            self.progress_updated.emit(20)
                        
                        def on_camera_started(node_id):
                            self.log_updated.emit(f"开始执行相机节点: {node_id}")
                            self.progress_updated.emit(30)
                        
                        def on_camera_completed(node_id, image):
                            self.log_updated.emit(f"相机节点执行完成，图像尺寸: {image.shape}")
                            self.progress_updated.emit(40)
                        
                        def on_vision_started(node_id):
                            self.log_updated.emit(f"开始执行视觉节点: {node_id}")
                            self.progress_updated.emit(50)
                        
                        def on_vision_completed(node_id, result):
                            self.log_updated.emit(f"视觉节点执行完成，处理时间: {result.get('processing_time', 0):.3f}s")
                            self.progress_updated.emit(60)
                        
                        def on_robot_started(node_id):
                            self.log_updated.emit(f"开始执行机械臂节点: {node_id}")
                            self.progress_updated.emit(70)
                        
                        def on_robot_completed(node_id, position):
                            self.log_updated.emit(f"机械臂节点执行完成，目标位置: {position}")
                            self.progress_updated.emit(85)
                        
                        def on_workflow_completed(result):
                            if result.success:
                                self.log_updated.emit(f"VMC工作流执行成功！总耗时: {result.execution_time:.3f}s")
                                self.progress_updated.emit(100)
                            else:
                                self.log_updated.emit(f"VMC工作流执行失败: {result.error_message}")
                        
                        # 注册回调
                        executor.add_execution_callback('workflow_started', on_workflow_started)
                        executor.add_execution_callback('camera_started', on_camera_started)
                        executor.add_execution_callback('camera_completed', on_camera_completed)
                        executor.add_execution_callback('vision_started', on_vision_started)
                        executor.add_execution_callback('vision_completed', on_vision_completed)
                        executor.add_execution_callback('robot_started', on_robot_started)
                        executor.add_execution_callback('robot_completed', on_robot_completed)
                        executor.add_execution_callback('workflow_completed', on_workflow_completed)
                        
                        self.log_updated.emit(f"加载配置文件: {self.config_path}")
                        self.progress_updated.emit(25)
                        
                        # 执行工作流
                        result = executor.execute_vmc_workflow(self.config_path)
                        
                        self.execution_completed.emit(result)
                        
                    except Exception as e:
                        self.log_updated.emit(f"执行线程异常: {str(e)}")
                        error_result = type('MockResult', (), {
                            'success': False,
                            'error_message': str(e),
                            'execution_time': 0.0
                        })()
                        self.execution_completed.emit(error_result)
            
            # 获取最新配置文件路径
            from core.managers.app_config import AppConfigManager
            config_manager = AppConfigManager()
            temp_dir = config_manager.workspace_dir / "temp" / "vmc_tmp"
            config_file = temp_dir / "vmc_canvas_latest.json"
            
            execution_thread = VMCExecutionThread(str(config_file))
            execution_thread.progress_updated.connect(progress_dialog.setValue)
            execution_thread.log_updated.connect(log_message)
            
            def on_execution_completed(result):
                progress_dialog.close()
                
                # 显示执行结果
                if result.success:
                    success_msg = f"""VMC工作流执行成功！

执行时间: {result.execution_time:.3f} 秒

执行结果:
- ✅ 相机节点: 已完成
- ✅ 视觉处理节点: 已完成
- ✅ 机械臂节点: 已完成

详细信息:
- 捕获图像尺寸: {result.camera_output.shape if result.camera_output is not None else 'N/A'}
- 视觉处理时间: {result.vision_output.get('processing_time', 0):.3f}s (如果有)
- 机械臂动作数量: {len(result.robot_actions)} 个"""
                    
                    QMessageBox.information(self, '执行成功', success_msg)
                    self.add_log("VMC工作流执行成功")
                    
                else:
                    error_msg = f"""VMC工作流执行失败！

错误信息: {result.error_message}
执行时间: {result.execution_time:.3f} 秒

请检查:
1. 硬件连接是否正常
2. 节点配置是否正确
3. 节点连接是否完整"""
                    
                    QMessageBox.critical(self, '执行失败', error_msg)
                    self.add_log(f"VMC工作流执行失败: {result.error_message}")
            
            execution_thread.execution_completed.connect(on_execution_completed)
            
            # 连接取消按钮
            progress_dialog.canceled.connect(execution_thread.cancel)
            
            # 启动执行
            execution_thread.start()
            
        except Exception as e:
            error_msg = f"启动VMC工作流执行失败: {str(e)}"
            debug(error_msg, "VisionRobotDialog", LogCategory.SOFTWARE)
            QMessageBox.critical(self, '错误', error_msg)

    def step_execute_vmc_workflow(self):
        """单步执行VMC工作流"""
        try:
            # 检查是否有节点
            if not hasattr(self.canvas, 'scene') or len(self.canvas.scene.items()) == 0:
                QMessageBox.warning(self, '警告', '当前画布上没有节点，无法执行VMC工作流。\n请先添加相机、视觉处理或机械臂节点。')
                return
            
            # 生成并保存配置到缓存
            vmc_config = self._generate_vmc_config()
            self._save_vmc_config_to_cache(vmc_config)
            
            # 获取配置文件路径
            from core.managers.app_config import AppConfigManager
            config_manager = AppConfigManager()
            temp_dir = config_manager.workspace_dir / "temp" / "vmc_tmp"
            config_file = temp_dir / "vmc_canvas_latest.json"
            
            # 初始化VMC执行器
            from core.managers.vmc_pipeline_executor import VMCPipelineExecutor
            self.vmc_executor = VMCPipelineExecutor()
            
            # 如果还没有准备执行计划，先准备
            if not hasattr(self.vmc_executor, 'execution_plan') or not self.vmc_executor.execution_plan:
                self.vmc_executor.prepare_execution_plan(str(config_file))
                self.step_btn.setEnabled(True)
                self.continue_btn.setEnabled(False)
                self.add_log("VMC单步执行计划已准备完成")
                self.update_step_info()
                return
            
            # 执行单步
            if self.vmc_executor.step_execute():
                self.update_step_info()
                node_info = self.vmc_executor.get_step_info()
                self.add_log(f"单步执行完成: 第 {node_info['current_step']} 步")
                
                # 检查是否执行完毕
                if node_info['current_step'] >= node_info['total_steps']:
                    self.step_btn.setEnabled(False)
                    self.continue_btn.setEnabled(False)
                    self.add_log("VMC工作流单步执行完成！")
                    QMessageBox.information(self, '执行完成', 'VMC工作流所有步骤已执行完毕')
            else:
                error(f"单步执行失败", "VisionRobotDialog", LogCategory.SOFTWARE)
                QMessageBox.warning(self, '执行失败', '单步执行失败，请检查节点配置')
            
        except Exception as e:
            error_msg = f"单步执行失败: {str(e)}"
            error(error_msg, "VisionRobotDialog", LogCategory.SOFTWARE)
            QMessageBox.critical(self, '错误', error_msg)

    def continue_vmc_workflow(self):
        """继续执行VMC工作流（从当前位置执行到完成）"""
        try:
            if not hasattr(self, 'vmmc_executor') or not self.vmc_executor:
                QMessageBox.warning(self, '警告', '请先进行单步执行来初始化工作流')
                return
            
            # 切换到连续执行模式
            self.vmc_executor.disable_step_mode()
            
            # 创建执行进度对话框
            from PyQt6.QtWidgets import QProgressDialog, QVBoxLayout, QLabel, QTextEdit
            progress_dialog = QProgressDialog("正在继续执行VMC工作流...", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("VMC工作流继续执行")
            progress_dialog.setModal(True)
            progress_dialog.setMinimumDuration(0)
            
            # 添加详细日志显示
            log_widget = QTextEdit()
            log_widget.setReadOnly(True)
            log_widget.setMaximumHeight(200)
            
            layout = QVBoxLayout()
            layout.addWidget(QLabel("执行日志:"))
            layout.addWidget(log_widget)
            progress_dialog.setLayout(layout)
            
            progress_dialog.show()
            
            def log_message(message: str):
                log_widget.append(f"[{time.strftime('%H:%M:%S')}] {message}")
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
            
            log_message("继续执行VMC工作流...")
            
            # 在后台线程执行
            from PyQt6.QtCore import QThread, pyqtSignal
            
            class VMCContinueThread(QThread):
                progress_updated = pyqtSignal(int)
                log_updated = pyqtSignal(str)
                execution_completed = pyqtSignal(object)
                
                def __init__(self, executor, config_path: str):
                    super().__init__()
                    self.executor = executor
                    self.config_path = config_path
                
                def run(self):
                    try:
                        self.log_updated.emit("继续执行剩余工作流步骤...")
                        self.progress_updated.emit(10)
                        
                        # 执行剩余步骤
                        while self.executor.get_step_info()['current_step'] < self.executor.get_step_info()['total_steps']:
                            if not self.executor.step_execute():
                                self.log_updated.emit("步骤执行失败，终止继续执行")
                                break
                            
                            step_info = self.executor.get_step_info()
                            self.progress_updated.emit(30 + int(60 * step_info['current_step'] / step_info['total_steps']))
                            self.log_updated.emit(f"执行完成: 第 {step_info['current_step']} 步")
                        
                        # 创建最终结果
                        result = type('VMCResult', (), {
                            'success': True,
                            'execution_time': 0.0,
                            'camera_output': None,
                            'vision_output': None,
                            'robot_actions': []
                        })()
                        
                        self.execution_completed.emit(result)
                        
                    except Exception as e:
                        self.log_updated.emit(f"继续执行异常: {str(e)}")
                        error_result = type('VMCResult', (), {
                            'success': False,
                            'error_message': str(e),
                            'execution_time': 0.0
                        })()
                        self.execution_completed.emit(error_result)
            
            config_manager = AppConfigManager()
            temp_dir = config_manager.workspace_dir / "temp" / "vmc_tmp"
            config_file = temp_dir / "vmc_canvas_latest.json"
            
            execution_thread = VMCContinueThread(self.vmc_executor, str(config_file))
            execution_thread.progress_updated.connect(progress_dialog.setValue)
            execution_thread.log_updated.connect(log_message)
            
            def on_execution_completed(result):
                progress_dialog.close()
                self.step_btn.setEnabled(False)
                self.continue_btn.setEnabled(False)
                
                if result.success:
                    QMessageBox.information(self, '执行成功', 'VMC工作流继续执行完成')
                    self.add_log("VMC工作流继续执行成功")
                    self.update_step_info()
                else:
                    QMessageBox.critical(self, '执行失败', f'继续执行失败: {result.error_message}')
                    self.add_log(f"VMC工作流继续执行失败: {result.error_message}")
            
            execution_thread.execution_completed.connect(on_execution_completed)
            progress_dialog.canceled.connect(execution_thread.terminate)
            execution_thread.start()
            
        except Exception as e:
            error_msg = f"继续执行失败: {str(e)}"
            error(error_msg, "VisionRobotDialog", LogCategory.SOFTWARE)
            QMessageBox.critical(self, '错误', error_msg)

    def update_step_info(self):
        """更新步骤信息显示"""
        if hasattr(self, 'vmc_executor') and self.vmc_executor:
            step_info = self.vmc_executor.get_step_info()
            self.step_info.setText(f"步骤: {step_info['current_step']}/{step_info['total_steps']}")
            
            if step_info['current_node']:
                node_type = step_info['current_node']['type']
                node_id = step_info['current_node'].get('config', {}).get('id', 'unknown')
                self.workflow_status.setText(f"状态: 执行 {node_type} 节点 ({node_id})")
            else:
                self.workflow_status.setText("状态: 就绪")
        else:
            self.step_info.setText("步骤: 未开始")
            self.workflow_status.setText("状态: 就绪")