from typing import Dict, Any, Optional, List
import time
import os
import json
import importlib
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QCheckBox, QSlider, QTextEdit, QMessageBox, QSplitter,
    QFileDialog, QProgressBar, QFrame, QFormLayout, QComboBox,
    QLineEdit, QDialogButtonBox, QDialog, QListWidget, QListWidgetItem, QApplication,
    QStackedWidget, QMenu, QInputDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QObject, QMetaObject
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor
from core.managers.log_manager import info, debug, warning, error, LogCategory
from core import RobotService, CameraService, CalibrationService
from core.interfaces.hardware import RobotState, MotionMode, RobotPosition, PathPoint, RobotPath
from ui_libs.hardware_widget.camera.save_path_dialog import SavePathDialog
from ui_libs.hardware_widget.camera.camera_preview import PreviewLabel
from ui_libs.hardware_widget.camera.camera_info import CameraInfo
from core.middleware.event_bus import get_hardware_event_bus
from core.middleware.types_dto import RobotConnectionInfo, RobotPositionInfo, HardwareErrorInfo

class RobotControlTab(QWidget):
    """机械臂控制标签页 - 最终版"""

    # 定义信号用于安全地处理右键菜单
    show_context_menu_signal = pyqtSignal(int, int)  # row, column
    # 定义信号用于跨线程日志记录
    log_signal = pyqtSignal(str, str)

    def __init__(self, robot_service: RobotService, camera_service: CameraService = None, parent=None, vmc_node=None, vmc_callback=None):
        super().__init__(parent)
        self.robot_service = robot_service
        self.camera_service = camera_service
        
        # 初始化标定服务
        self.calibration_service = None
        if self.camera_service:
            self.calibration_service = CalibrationService(self.robot_service, self.camera_service)
            # 使用emit_log确保跨线程日志安全
            self.calibration_service.set_log_callback(self.emit_log)

        # 连接日志信号
        self.log_signal.connect(self.add_robot_log)
        
        self.current_position = (0, 0, 0, 0, 0, 0)
        self.is_recording_path = False
        self.recorded_path = None
        self.is_playing_path = False

        # 路径列表管理
        self.path_list = []  # 存储所有路径的列表
        self._empty_current_path = None  # 缓存空路径对象

        # 机械臂驱动
        self.robot_drivers = []
        self.current_driver_index = -1
        # UI不应该知道驱动类型（模拟/真实）
        self.command_count = 0  # 命令执行计数器

        # VMC节点同步功能
        self.vmc_node = vmc_node  # 引用VMC机械臂节点
        self.vmc_callback = vmc_callback  # 回调函数用于同步selected_hardware_id
        self.is_from_vmc_node = vmc_node is not None  # 标识是否来自VMC节点

        # 连接信号
        self.show_context_menu_signal.connect(self._handle_context_menu_safely)

        self.setup_drivers()
        self.setup_ui()
        self.setup_timer()

    def load_robot_configs(self):
        """从 hardware_config.json 加载机械臂配置"""
        try:
            config_file = 'config/hardware_config.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                # 清空当前列表
                self.driver_combo.clear()

                # 添加机械臂配置
                robots = config_data.get('robots', [])
                if robots:
                    for robot_config in robots:
                        name = robot_config.get('name', '未知机械臂')
                        brand = robot_config.get('brand', '未知品牌')
                        model = robot_config.get('model', '未知型号')
                        display_name = f"🤖 {name} ({brand} {model})"
                        self.driver_combo.addItem(display_name, robot_config)
                else:
                    # 如果没有配置，显示提示
                    self.driver_combo.addItem("🔧 请在硬件配置中添加机械臂", None)

                info(f"Loaded {len(robots)} robot configurations", "ROBOT_UI")
            else:
                # 配置文件不存在
                self.driver_combo.addItem("🔧 配置文件不存在", None)
                warning("hardware_config.json not found", "ROBOT_UI")

        except Exception as e:
            self.driver_combo.addItem("🔧 配置加载失败", None)
            error(f"Failed to load robot configs: {e}", "ROBOT_UI")

    def setup_drivers(self):
        """设置机械臂驱动"""
        # 扫描drivers目录
        drivers_path = "src/drivers/robots"
        if os.path.exists(drivers_path):
            for filename in os.listdir(drivers_path):
                if filename.endswith('.py') and not filename.startswith('_'):
                    module_name = filename[:-3]
                    try:
                        # 动态导入驱动模块
                        module = importlib.import_module(f"src.drivers.robots.{module_name}")

                        # 查找驱动类
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and
                                hasattr(attr, '__bases__') and
                                any('Robot' in str(base) for base in attr.__bases__) and
                                not attr.__module__.endswith('_base')):

                                driver = attr()
                                self.robot_drivers.append({
                                    'name': module_name.title(),
                                    'class_name': attr.__name__,
                                    'instance': driver,
                                    'driver_type': 'real'
                                })
                                info(f"Found robot driver: {module_name}", "ROBOT_UI")
                                break
                    except Exception as e:
                        error(f"Failed to import driver {module_name}: {e}", "ROBOT_UI")

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()

        # 顶部：连接控制面板 - 统一机械臂选择和连接状态
        connection_panel = self.create_connection_control_panel()
        layout.addWidget(connection_panel)

        # 主控制区域 - 重新布局
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：实时控制和实时信息（垂直布局）
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_top = self.create_enhanced_realtime_control()  # 修改为增强版实时控制
        left_bottom = self.create_real_time_info_panel()

        left_splitter.addWidget(left_top)
        left_splitter.addWidget(left_bottom)
        left_splitter.setSizes([400, 200])  # 增加实时控制区域大小

        main_splitter.addWidget(left_splitter)

        # 中间：路径管理
        middle_panel = self.create_enhanced_path_management()
        main_splitter.addWidget(middle_panel)

        # 右侧：机械臂日志单独一排
        right_panel = self.create_robot_log_panel()
        main_splitter.addWidget(right_panel)

        main_splitter.setSizes([350, 600, 300])  # 调整三栏比例，左侧缩小25%
        layout.addWidget(main_splitter)

        self.setLayout(layout)

    # status_bar functionality has been moved to create_real_time_info_panel()

    def create_connection_control_panel(self):
        """创建连接控制面板 - 统一机械臂选择和连接状态"""
        group = QGroupBox("机械臂连接控制")
        # group.setMaximumHeight(104)  # 移除固定高度限制，允许自适应
        layout = QVBoxLayout()

        # 第一行：机械臂选择
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("机械臂:"))
        self.driver_combo = QComboBox()

        # 添加硬件配置中的机械臂
        self.load_robot_configs()

        self.driver_combo.currentTextChanged.connect(self.on_driver_changed)
        selection_layout.addWidget(self.driver_combo)

        selection_layout.addStretch()
        layout.addLayout(selection_layout)

        # 第二行：连接状态和控制
        control_layout = QHBoxLayout()

        # 连接状态显示
        self.robot_status_label = QLabel("🔴 未选择机械臂")
        self.robot_status_label.setStyleSheet("color: #f44336; font-weight: bold; font-size: 14px;")
        self.robot_status_label.setMinimumWidth(180)
        control_layout.addWidget(self.robot_status_label)

        # 连接控制按钮
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setMinimumWidth(100)
        self.connect_btn.clicked.connect(self.toggle_robot_connection)
        control_layout.addWidget(self.connect_btn)

        self.test_btn = QPushButton("执行标定")
        self.test_btn.setMinimumWidth(100)
        self.test_btn.clicked.connect(self.test_robot_connection)
        control_layout.addWidget(self.test_btn)

        self.calib_3d_btn = QPushButton("执行3D标定")
        self.calib_3d_btn.setMinimumWidth(100)
        self.calib_3d_btn.clicked.connect(self.show_3d_calibration_dialog)
        self.calib_3d_btn.setStyleSheet("""
            QPushButton {
                background-color: #673AB7;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E35B1;
            }
        """)
        control_layout.addWidget(self.calib_3d_btn)

        # 标定确认按钮 (默认隐藏，仅在Elite标定时显示)
        self.confirm_btn = QPushButton("✅ 确认/下一步")
        self.confirm_btn.setMinimumWidth(120)
        self.confirm_btn.clicked.connect(self.confirm_calibration_step)
        self.confirm_btn.setVisible(False)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        control_layout.addWidget(self.confirm_btn)
        
        # VMC节点同步按钮（只有从VMC节点打开时才显示）
        if self.is_from_vmc_node:
            apply_to_node_btn = QPushButton("🔗 应用到节点")
            apply_to_node_btn.setMinimumWidth(120)
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
            self.apply_to_node_btn = apply_to_node_btn
            control_layout.addWidget(apply_to_node_btn)

        control_layout.addStretch()

        # 连接时间显示
        self.connection_time_label = QLabel("00:00:00")
        self.connection_time_label.setStyleSheet("color: #666666; font-size: 12px;")
        control_layout.addWidget(self.connection_time_label)

        # state_status 和 motion_mode_label 在 create_real_time_info_panel 中创建，这里不需要重复创建

        layout.addLayout(control_layout)

        group.setLayout(layout)
        return group

    def create_enhanced_realtime_control(self):
        """创建增强版实时控制面板 - 集成点动和位置控制"""
        group = QGroupBox("实时控制")
        layout = QVBoxLayout()

        # 控制模式选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("控制模式:"))
        self.control_mode_combo = QComboBox()
        self.control_mode_combo.addItems(["点动控制", "位置控制"])
        self.control_mode_combo.currentTextChanged.connect(self.on_control_mode_changed)
        mode_layout.addWidget(self.control_mode_combo)
        layout.addLayout(mode_layout)

        # 创建堆叠窗口来切换不同控制模式
        self.control_stack = QStackedWidget()

        # 点动控制页面
        jog_widget = self.create_jog_control_panel()
        self.control_stack.addWidget(jog_widget)

        # 位置控制页面
        position_widget = self.create_position_control_panel()
        self.control_stack.addWidget(position_widget)

        layout.addWidget(self.control_stack)

        # 通用控制按钮（底部）
        button_layout = QHBoxLayout()

        home_btn = QPushButton("🏠 回原点")
        home_btn.setMinimumSize(100, 40)
        home_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #2E7D32;
            }
        """)
        home_btn.clicked.connect(self.go_home)
        button_layout.addWidget(home_btn)

        emergency_btn = QPushButton("🛑 紧急停止")
        emergency_btn.setMinimumSize(100, 40)
        emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
        """)
        emergency_btn.clicked.connect(self.emergency_stop)
        button_layout.addWidget(emergency_btn)

        # 运动模式（用于后端）
        motion_mode_layout = QHBoxLayout()
        motion_mode_layout.addWidget(QLabel("运动模式:"))
        self.motion_mode_combo = QComboBox()
        self.motion_mode_combo.setMinimumWidth(100)
        self.motion_mode_combo.setMinimumHeight(35)
        self.motion_mode_combo.setStyleSheet("QComboBox { font-size: 14px; padding: 5px; }")
        self.motion_mode_combo.addItems(["手动", "自动"])
        self.motion_mode_combo.currentTextChanged.connect(self.on_motion_mode_changed)
        motion_mode_layout.addWidget(self.motion_mode_combo)
        motion_mode_layout.addStretch()
        layout.addLayout(motion_mode_layout)

        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def create_jog_control_panel(self):
        """创建点动控制面板"""
        widget = QWidget()
        layout = QVBoxLayout()

        # 点动控制 - 恢复原来的高度
        jog_group = QGroupBox("点动控制")
        jog_group.setMinimumHeight(280)  # 恢复原来的高度
        jog_layout = QGridLayout()

        # 标签
        jog_layout.addWidget(QLabel("轴向控制"), 0, 0, 1, 6)
        jog_layout.setRowMinimumHeight(0, 30)

        # 方向控制按钮 - 恢复原来的布局
        directions = [
            ("X-", 1, 1), ("X+", 3, 1),
            ("Y-", 2, 0), ("Y+", 2, 2),
            ("Z-", 1, 4), ("Z+", 3, 4)
        ]

        for text, row, col in directions:
            btn = QPushButton(text)
            btn.setMinimumSize(50, 35)
            btn.setMaximumSize(60, 45)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
                QPushButton:pressed {
                    background-color: #0D47A1;
                }
            """)
            btn.clicked.connect(lambda checked, t=text: self.jog_move(t))
            jog_layout.addWidget(btn, row, col)

        # 速度控制区域
        jog_layout.addWidget(QLabel("速度控制:"), 5, 0, 1, 2)
        jog_layout.setRowMinimumHeight(5, 30)

        self.jog_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.jog_speed_slider.setRange(1, 100)
        self.jog_speed_slider.setValue(50)
        self.jog_speed_slider.setMinimumHeight(25)
        self.jog_speed_label = QLabel("50%")
        self.jog_speed_slider.valueChanged.connect(
            lambda v: self.jog_speed_label.setText(f"{v}%")
        )
        # 释放滑块时同步设置机器人速度
        self.jog_speed_slider.sliderReleased.connect(self.on_speed_changed)
        
        jog_layout.addWidget(self.jog_speed_slider, 5, 2, 1, 3)
        jog_layout.addWidget(self.jog_speed_label, 5, 5)

        # 点动距离设置
        distance_layout = QHBoxLayout()
        distance_layout.addWidget(QLabel("点动距离:"))
        self.jog_distance_spinbox = QDoubleSpinBox()
        self.jog_distance_spinbox.setRange(0.1, 100.0)
        self.jog_distance_spinbox.setValue(10.0)
        self.jog_distance_spinbox.setSuffix(" mm")
        self.jog_distance_spinbox.setMinimumWidth(80)
        distance_layout.addWidget(self.jog_distance_spinbox)
        distance_layout.addStretch()
        jog_layout.addLayout(distance_layout, 7, 0, 1, 6)

        jog_group.setLayout(jog_layout)
        layout.addWidget(jog_group)

        widget.setLayout(layout)
        return widget

    def create_position_control_panel(self):
        """创建位置控制面板"""
        widget = QWidget()
        layout = QVBoxLayout()

        # 位置控制 - 使用原来中间的面板代码
        position_group = QGroupBox("位置控制")
        position_layout = QVBoxLayout()

        # XYZ坐标 - 线性位置和旋转位置上下堆叠
        xyz_layout = QVBoxLayout()

        # 线性位置组 (X, Y, Z)
        linear_group = QGroupBox("线性位置 (mm)")
        linear_inner_layout = QGridLayout()

        linear_controls = [
            ("X:", 0, 0), ("Y:", 0, 1), ("Z:", 0, 2)
        ]

        for label, row, col in linear_controls:
            # 添加标签
            label_widget = QLabel(label)
            label_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignCenter)
            linear_inner_layout.addWidget(label_widget, row, col)

            # 添加输入框
            spinbox = QDoubleSpinBox()
            spinbox.setRange(-2000, 2000)
            spinbox.setSuffix(" mm")
            spinbox.setValue(0.0)
            spinbox.setMinimumWidth(100)
            spinbox.setMaximumWidth(120)
            spinbox.setMinimumHeight(35)
            spinbox.setStyleSheet("QDoubleSpinBox { font-size: 14px; }")
            spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            linear_inner_layout.addWidget(spinbox, row + 1, col)
            if col == 0:
                self.x_spinbox = spinbox
            elif col == 1:
                self.y_spinbox = spinbox
            else:
                self.z_spinbox = spinbox

        linear_group.setLayout(linear_inner_layout)

        # 旋转位置组 (RX, RY, RZ)
        rotation_group = QGroupBox("旋转位置 (°)")
        rotation_inner_layout = QGridLayout()

        rotation_controls = [
            ("RX:", 0, 0), ("RY:", 0, 1), ("RZ:", 0, 2)
        ]

        for label, row, col in rotation_controls:
            # 添加标签
            label_widget = QLabel(label)
            label_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignCenter)
            rotation_inner_layout.addWidget(label_widget, row, col)

            # 添加输入框
            spinbox = QDoubleSpinBox()
            spinbox.setRange(-180, 180)
            spinbox.setSuffix(" °")
            spinbox.setDecimals(1)
            spinbox.setValue(0.0)
            spinbox.setMinimumWidth(100)
            spinbox.setMaximumWidth(120)
            spinbox.setMinimumHeight(35)
            spinbox.setStyleSheet("QDoubleSpinBox { font-size: 14px; }")
            spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            rotation_inner_layout.addWidget(spinbox, row + 1, col)
            if col == 0:
                self.rx_spinbox = spinbox
            elif col == 1:
                self.ry_spinbox = spinbox
            else:
                self.rz_spinbox = spinbox

        rotation_group.setLayout(rotation_inner_layout)

        # 上下堆叠
        xyz_layout.addWidget(linear_group)
        xyz_layout.addWidget(rotation_group)

        position_layout.addLayout(xyz_layout)

        # 速度控制
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("速度:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(50)
        self.speed_label = QLabel("50%")
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_label.setText(f"{v}%")
        )
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        position_layout.addLayout(speed_layout)

        # 移动按钮
        move_btn_layout = QHBoxLayout()

        move_btn = QPushButton("🎯 移动到位置")
        move_btn.clicked.connect(self.move_to_position)
        move_btn.setMinimumSize(120, 40)
        move_btn.setMaximumSize(200, 50)
        move_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        move_btn_layout.addWidget(move_btn)

        # 当前位置按钮
        current_pos_btn = QPushButton("📍 读取当前位置")
        current_pos_btn.clicked.connect(self.read_current_position)
        current_pos_btn.setMinimumSize(120, 40)
        current_pos_btn.setMaximumSize(200, 50)
        current_pos_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        move_btn_layout.addWidget(current_pos_btn)

        position_layout.addLayout(move_btn_layout)
        position_group.setLayout(position_layout)
        layout.addWidget(position_group)

        widget.setLayout(layout)
        return widget

    def create_robot_log_panel(self):
        """创建机械臂日志面板"""
        group = QGroupBox("机械臂日志")
        layout = QVBoxLayout()

        # 日志控制按钮
        control_layout = QHBoxLayout()

        clear_log_btn = QPushButton("🗑 清空日志")
        clear_log_btn.clicked.connect(self.clear_robot_log)
        control_layout.addWidget(clear_log_btn)

        save_log_btn = QPushButton("💾 保存日志")
        save_log_btn.clicked.connect(self.save_robot_log)
        control_layout.addWidget(save_log_btn)

        # 日志级别过滤
        control_layout.addWidget(QLabel("级别:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["全部", "信息", "警告", "错误", "运动", "碰撞", "急停"])
        self.log_level_combo.currentTextChanged.connect(self.filter_robot_log)
        control_layout.addWidget(self.log_level_combo)

        control_layout.addStretch()
        layout.addLayout(control_layout)

        # 日志显示区域
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                line-height: 1.4;
            }
        """)
        layout.addWidget(self.log_display)

        # 日志统计
        stats_layout = QHBoxLayout()
        self.log_count_label = QLabel("总计: 0 条")
        self.log_count_label.setStyleSheet("color: #666666; font-size: 11px;")
        stats_layout.addWidget(self.log_count_label)

        self.log_error_count_label = QLabel("错误: 0 条")
        self.log_error_count_label.setStyleSheet("color: #f44336; font-size: 11px;")
        stats_layout.addWidget(self.log_error_count_label)

        self.log_warning_count_label = QLabel("警告: 0 条")
        self.log_warning_count_label.setStyleSheet("color: #FF9800; font-size: 11px;")
        stats_layout.addWidget(self.log_warning_count_label)

        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # 初始化日志存储
        self.robot_logs = []
        self.log_display.setHtml("<div style='color: #999; font-style: italic;'>等待机械臂日志...</div>")

        group.setLayout(layout)
        return group

    # 新的槽函数
    def on_control_mode_changed(self, mode_text):
        """控制模式改变"""
        if mode_text == "点动控制":
            self.control_stack.setCurrentIndex(0)
            # 设置运动模式为点动
            result = self.robot_service.set_motion_mode(MotionMode.JOG)
            info(f"切换到点动控制模式", "ROBOT_UI", LogCategory.HARDWARE)
        elif mode_text == "位置控制":
            self.control_stack.setCurrentIndex(1)
            # 设置运动模式为手动
            result = self.robot_service.set_motion_mode(MotionMode.MANUAL)
            info(f"切换到位置控制模式", "ROBOT_UI", LogCategory.HARDWARE)
        else:
            warning(f"未知的控制模式: {mode_text}", "ROBOT_UI", LogCategory.HARDWARE)

    def on_motion_mode_changed(self, mode_text):
        """运动模式改变"""
        mode_map = {
            "手动": MotionMode.MANUAL,
            "自动": MotionMode.AUTOMATIC
        }
        mode = mode_map.get(mode_text, MotionMode.MANUAL)
        result = self.robot_service.set_motion_mode(mode)
        if not result['success']:
            warning(f"设置运动模式失败: {result.get('error')}", "ROBOT_UI", LogCategory.HARDWARE)

    def read_current_position(self):
        """读取当前位置"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            self.add_robot_log("警告", "读取当前位置失败: 机械臂未连接")
            return

        info("开始读取当前位置", "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("信息", "开始读取当前位置")

        try:
            # 从service层获取当前位置
            position = self.robot_service.get_position()
            if position and len(position) >= 6:
                x, y, z, rx, ry, rz = position[:6]

                # 更新输入框显示当前值
                self.x_spinbox.setValue(float(x))
                self.y_spinbox.setValue(float(y))
                self.z_spinbox.setValue(float(z))
                self.rx_spinbox.setValue(float(rx))
                self.ry_spinbox.setValue(float(ry))
                self.rz_spinbox.setValue(float(rz))

                position_info = f"当前位置: ({x:.1f}, {y:.1f}, {z:.1f}, {rx:.1f}, {ry:.1f}, {rz:.1f})"
                info(f"{position_info}", "ROBOT_UI")
                self.add_robot_log("信息", position_info)
                self.add_robot_log("运动", f"位置读取完成并更新到输入框: {position_info}")

                QMessageBox.information(self, "读取成功",
                    f"当前位置已读取并更新到输入框：\n"
                    f"X: {x:.1f}mm, Y: {y:.1f}mm, Z: {z:.1f}mm\n"
                    f"RX: {rx:.1f}°, RY: {ry:.1f}°, RZ: {rz:.1f}°")

            elif position and len(position) >= 3:
                x, y, z = position[:3]
                # 只有线性位置
                self.x_spinbox.setValue(float(x))
                self.y_spinbox.setValue(float(y))
                self.z_spinbox.setValue(float(z))

                position_info = f"当前位置(仅线性): ({x:.1f}, {y:.1f}, {z:.1f})"
                info(f"{position_info}", "ROBOT_UI")
                self.add_robot_log("信息", position_info)
                self.add_robot_log("运动", f"读取线性位置完成: {position_info}")

                QMessageBox.information(self, "读取成功",
                    f"当前位置已读取（仅线性位置）：\n"
                    f"X: {x:.1f}mm, Y: {y:.1f}mm, Z: {z:.1f}mm\n"
                    f"旋转位置不可用")
            else:
                warning("无法读取当前位置，返回空值", "ROBOT_UI", LogCategory.HARDWARE)
                self.add_robot_log("警告", "无法读取当前位置，返回空值")
                QMessageBox.warning(self, "读取失败", "无法读取当前位置，返回空值")

        except Exception as e:
            error(f"读取位置失败: {e}", "ROBOT_UI", LogCategory.HARDWARE)
            self.add_robot_log("错误", f"读取位置失败: {e}")
            QMessageBox.warning(self, "读取失败", f"读取当前位置失败：{str(e)}")

    def clear_robot_log(self):
        """清空机械臂日志"""
        self.robot_logs.clear()
        self.log_display.setHtml("<div style='color: #999; font-style: italic;'>日志已清空...</div>")
        self.update_log_stats()
        info("机械臂日志已清空", "ROBOT_UI")

    def save_robot_log(self):
        """保存机械臂日志"""
        if not self.robot_logs:
            QMessageBox.information(self, "无日志", "没有可保存的日志")
            return

        from core.managers.app_config import AppConfigManager
        app_config = AppConfigManager()
        logs_dir = app_config.get_log_directory()

        timestamp = int(time.time())
        filename = f"robot_log_{timestamp}.txt"
        filepath = logs_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"机械臂日志 - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")

                for log_entry in self.robot_logs:
                    f.write(f"[{log_entry['time']}] [{log_entry['level']}] {log_entry['message']}\n")

                # 添加统计信息
                error_count = sum(1 for log in self.robot_logs if log['level'] == '错误')
                warning_count = sum(1 for log in self.robot_logs if log['level'] == '警告')
                f.write(f"\n日志统计: 总计 {len(self.robot_logs)} 条，错误 {error_count} 条，警告 {warning_count} 条\n")

            info(f"机械臂日志已保存到: {filepath}", "ROBOT_UI")
            QMessageBox.information(self, "保存成功", f"日志已保存到: {filename}")
        except Exception as e:
            error(f"保存日志失败: {e}", "ROBOT_UI")
            QMessageBox.warning(self, "保存失败", f"无法保存日志: {str(e)}")

    def filter_robot_log(self, level_text):
        """过滤机械臂日志"""
        filtered_logs = []

        if level_text == "全部":
            filtered_logs = self.robot_logs
        else:
            filtered_logs = [log for log in self.robot_logs if log['level'] == level_text]

        self.update_log_display(filtered_logs)

    def add_robot_log(self, level, message):
        """添加机械臂日志"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        log_entry = {
            'time': timestamp,
            'level': level,
            'message': message
        }

        self.robot_logs.append(log_entry)

        # 保持日志数量在合理范围内（最多1000条）
        if len(self.robot_logs) > 1000:
            self.robot_logs = self.robot_logs[-1000:]

        # 应用当前过滤器
        current_filter = self.log_level_combo.currentText()
        if current_filter == "全部" or current_filter == level:
            self.update_log_display([log for log in self.robot_logs if current_filter == "全部" or log['level'] == current_filter])

        self.update_log_stats()

    def update_log_display(self, logs):
        """更新日志显示"""
        if not logs:
            self.log_display.setHtml("<div style='color: #999; font-style: italic;'>没有符合条件的日志...</div>")
            return

        html_content = ""
        color_map = {
            '信息': '#4CAF50',
            '警告': '#FF9800',
            '错误': '#f44336',
            '运动': '#2196F3',
            '碰撞': '#9C27B0',
            '急停': '#f44336',
            '连接': '#607D8B'
        }

        for log_entry in logs[-100:]:  # 只显示最新100条
            color = color_map.get(log_entry['level'], '#ffffff')
            html_content += f'<div style="color: #999; margin-bottom: 2px;">[{log_entry["time"]}]</div>'
            html_content += f'<div style="color: {color}; margin-bottom: 8px; margin-left: 10px;">[{log_entry["level"]}] {log_entry["message"]}</div>'

        self.log_display.setHtml(html_content)
        # 滚动到底部
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    def update_log_stats(self):
        """更新日志统计"""
        total_count = len(self.robot_logs)
        error_count = sum(1 for log in self.robot_logs if log['level'] == '错误')
        warning_count = sum(1 for log in self.robot_logs if log['level'] == '警告')

        self.log_count_label.setText(f"总计: {total_count} 条")
        self.log_error_count_label.setText(f"错误: {error_count} 条")
        self.log_warning_count_label.setText(f"警告: {warning_count} 条")

    def add_log_on_emergency_stop(self):
        """紧急停止时添加日志"""
        self.add_robot_log("急停", "紧急停止被触发！")

    def add_log_on_collision(self):
        """碰撞检测时添加日志"""
        self.add_robot_log("碰撞", "检测到机械臂碰撞！")

    def add_log_on_movement(self, from_pos, to_pos):
        """移动时添加日志"""
        self.add_robot_log("运动", f"位置移动: {from_pos} → {to_pos}")

    def create_enhanced_path_management(self):
        """创建增强版路径管理面板"""
        group = QGroupBox("路径管理")
        layout = QVBoxLayout()

        # 路径记录控制
        record_group = QGroupBox("路径记录")
        record_layout = QHBoxLayout()

        self.record_btn = QPushButton("⏺ 开始记录")
        self.record_btn.clicked.connect(self.toggle_path_recording)
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        record_layout.addWidget(self.record_btn)

        self.add_point_btn = QPushButton("➕ 添加当前点")
        self.add_point_btn.clicked.connect(self.add_path_point)
        self.add_point_btn.setEnabled(False)
        record_layout.addWidget(self.add_point_btn)

        self.clear_path_btn = QPushButton("🗑 清空路径")
        self.clear_path_btn.clicked.connect(self.clear_recorded_path)
        record_layout.addWidget(self.clear_path_btn)

        record_group.setLayout(record_layout)
        layout.addWidget(record_group)

        # 路径列表管理
        list_group = QGroupBox("路径列表")
        list_layout = QVBoxLayout()

        self.path_table = QTableWidget()
        self.path_table.setColumnCount(6)
        self.path_table.setHorizontalHeaderLabels(["名称", "点数", "创建时间", "描述", "状态", "操作"])
        self.path_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.path_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.path_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.path_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.path_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.path_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        
        self.path_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.path_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # 设置双击事件
        self.path_table.cellDoubleClicked.connect(self.on_path_double_clicked)
        # 设置选择变化事件
        self.path_table.itemSelectionChanged.connect(self.on_path_selection_changed)
        # 设置右键菜单
        self.setup_path_table_context_menu()

        list_layout.addWidget(self.path_table)

        # 工具栏 - 放在表格下方，贴底显示
        toolbar_layout = QHBoxLayout()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh_path_list)
        refresh_btn.setToolTip("刷新当前路径显示")
        toolbar_layout.addWidget(refresh_btn)

        load_btn = QPushButton("📂 加载已保存")
        load_btn.clicked.connect(self.load_saved_paths_dialog)
        load_btn.setToolTip("从workspace/paths/加载已保存的路径")
        toolbar_layout.addWidget(load_btn)

        clear_btn = QPushButton("🗑 清空当前")
        clear_btn.clicked.connect(self.clear_recorded_path)
        clear_btn.setToolTip("清空当前记录的路径")
        toolbar_layout.addWidget(clear_btn)

        # 显示路径文件位置
        path_location_label = QLabel("📁 workspace/paths/")
        path_location_label.setStyleSheet("color: #666666; font-size: 11px; font-style: italic;")
        path_location_label.setToolTip("已保存路径存储位置")
        toolbar_layout.addWidget(path_location_label)

        toolbar_layout.addStretch()

        list_layout.addLayout(toolbar_layout)

        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        # 路径播放控制
        playback_group = QGroupBox("路径播放")
        playback_layout = QGridLayout()

        playback_layout.addWidget(QLabel("循环:"), 0, 0)
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setRange(1, 100)
        self.loop_spinbox.setValue(1)
        self.loop_spinbox.setSuffix("次")
        playback_layout.addWidget(self.loop_spinbox, 0, 1)

        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self.play_path)
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        playback_layout.addWidget(self.play_btn, 1, 0)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self.stop_path_playback)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        playback_layout.addWidget(self.stop_btn, 1, 1)

        playback_group.setLayout(playback_layout)
        layout.addWidget(playback_group)

        # 当前路径信息
        self.current_path_label = QLabel("📄 无路径加载")
        self.current_path_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
                color: #666666;
            }
        """)
        layout.addWidget(self.current_path_label)

        group.setLayout(layout)
        return group

    def create_real_time_info_panel(self):
        """创建实时信息面板"""
        group = QGroupBox("实时信息")
        layout = QVBoxLayout()

        # 运动信息
        motion_info = QGroupBox("运动状态")
        motion_layout = QFormLayout()

        self.motion_state_label = QLabel("未知")
        motion_layout.addRow("当前状态:", self.motion_state_label)

        self.is_moving_label = QLabel("否")
        motion_layout.addRow("正在移动:", self.is_moving_label)

        self.motion_mode_label = QLabel("未知")
        motion_layout.addRow("运动模式:", self.motion_mode_label)

        motion_info.setLayout(motion_layout)
        layout.addWidget(motion_info)

        # 连接信息
        connection_info = QGroupBox("连接信息")
        connection_layout = QFormLayout()

        self.driver_label = QLabel("未选择")
        connection_layout.addRow("当前驱动:", self.driver_label)

        # connection_time_label 在 create_connection_control_panel 中已创建，直接使用
        connection_layout.addRow("连接时长:", self.connection_time_label)

        connection_info.setLayout(connection_layout)
        layout.addWidget(connection_info)

        # 位置和状态信息
        position_state_info = QGroupBox("位置状态")
        position_state_layout = QFormLayout()

        self.position_status = QLabel("位置: (-, -, -, -, -, -)")
        self.position_status.setToolTip("X, Y, Z, RX, RY, RZ")
        position_state_layout.addRow(self.position_status)

        self.state_status = QLabel("状态: 未知")
        position_state_layout.addRow(self.state_status)

        position_state_info.setLayout(position_state_layout)
        layout.addWidget(position_state_info)

        # 性能信息
        performance_info = QGroupBox("性能信息")
        performance_layout = QFormLayout()

        self.fps_label = QLabel("0.0")
        performance_layout.addRow("更新频率(Hz):", self.fps_label)

        self.command_count_label = QLabel("0")
        performance_layout.addRow("命令执行数:", self.command_count_label)

        performance_info.setLayout(performance_layout)
        layout.addWidget(performance_info)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def setup_timer(self):
        """设置定时器"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(500)  # 恢复到500ms更新，现在不会产生日志污染

        # 性能监控定时器
        self.performance_timer = QTimer()
        self.performance_timer.timeout.connect(self.update_performance)
        self.performance_timer.start(1000)

        # 连接时间计时器
        self.connection_time = 0
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.update_connection_time)
        if self.robot_service.is_connected():
            self.connection_timer.start(1000)

        # 初始化路径显示
        self.refresh_path_list()

    # 驱动相关槽函数
    def on_driver_changed(self, driver_text):
        """驱动选择改变"""
        # 获取选中的机械臂配置
        current_data = self.driver_combo.currentData()

        if current_data is None:
            warning("未选择有效的机械臂配置", "ROBOT_UI")
            self.robot_status_label.setText("🔴 未选择机械臂")
            self.robot_status_label.setStyleSheet("color: #f44336; font-weight: bold; font-size: 14px;")
            return

        # 记录当前机械臂配置
        self.current_robot_config = current_data
        robot_name = current_data.get('name', '未知机械臂')
        brand = current_data.get('brand', '未知品牌')

        info(f"选择机械臂: {robot_name} ({brand})", "ROBOT_UI")
        self.add_robot_log("信息", f"选择机械臂: {robot_name} ({brand})")

        # 不需要预先设置robot实例，让service层在连接时处理
        # 更新状态显示
        if not self.robot_service.is_connected():
            self.robot_status_label.setText(f"🟡 已选择: {robot_name}")
            self.robot_status_label.setStyleSheet("color: #FF9800; font-weight: bold; font-size: 14px;")
            self.add_robot_log("信息", f"机械臂已选择但未连接: {robot_name}")

    def toggle_robot_connection(self):
        """切换机械臂连接"""
        info("用户点击连接按钮", "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("信息", "用户点击连接按钮")

        if self.robot_service.is_connected():
            # 断开连接
            info("开始断开机械臂连接", "ROBOT_UI")
            self.add_robot_log("信息", "开始断开机械臂连接")

            result = self.robot_service.disconnect()
            debug(f"robot_service.disconnect结果: {result}", "ROBOT_UI")

            if result['success']:
                # 更新状态为已选择
                if hasattr(self, 'current_robot_config') and self.current_robot_config:
                    robot_name = self.current_robot_config.get('name', '未知机械臂')
                    self.robot_status_label.setText(f"🟡 已选择: {robot_name}")
                    info(f"状态更新为已选择: {robot_name}", "ROBOT_UI")
                    self.add_robot_log("信息", f"机械臂已断开连接: {robot_name}")
                else:
                    self.robot_status_label.setText("🔴 未选择机械臂")
                    warning("未选择机械臂配置", "ROBOT_UI")
                    self.add_robot_log("警告", "未选择机械臂配置")

                self.robot_status_label.setStyleSheet("color: #FF9800; font-weight: bold; font-size: 14px;")
                self.connect_btn.setText("连接")
                self.connection_timer.stop()
                self.connection_time = 0
                self.connection_time_label.setText("00:00:00")
                info("机械臂连接已断开", "ROBOT_UI")
            else:
                error(f"断开连接失败: {result.get('error')}", "ROBOT_UI")
                self.add_robot_log("错误", f"断开连接失败: {result.get('error')}")
        else:
            # 检查是否已选择机械臂配置
            if not hasattr(self, 'current_robot_config') or not self.current_robot_config:
                warning("未选择机械臂配置，显示警告对话框", "ROBOT_UI")
                QMessageBox.warning(self, "未选择机械臂", "请先从下拉列表中选择一个机械臂")
                return

            # 准备连接
            robot_name = self.current_robot_config.get('name', '未知机械臂')
            brand = self.current_robot_config.get('brand', '').lower()
            
            # 如果是Elite机械臂，弹出对话框输入IP
            if brand == 'elite':
                current_ip = self.current_robot_config.get('connection_params', {}).get('ip', '192.168.1.200')
                ip, ok = QInputDialog.getText(self, "输入IP", "请输入Elite机械臂IP地址:", QLineEdit.EchoMode.Normal, current_ip)
                if ok and ip:
                    # 更新配置中的IP
                    if 'connection_params' not in self.current_robot_config:
                        self.current_robot_config['connection_params'] = {}
                    self.current_robot_config['connection_params']['ip'] = ip
                    info(f"用户更新Elite机械臂IP为: {ip}", "ROBOT_UI")
                else:
                    # 用户取消或未输入，取消连接
                    return

            info(f"准备连接机械臂: {robot_name}", "ROBOT_UI")
            self.add_robot_log("信息", f"开始连接机械臂: {robot_name}")

            # 显示连接中状态
            self.robot_status_label.setText("🟡 连接中...")
            self.robot_status_label.setStyleSheet("color: #FF9800; font-weight: bold; font-size: 14px;")
            self.connect_btn.setEnabled(False)
            QApplication.processEvents()  # 强制UI更新
            self.add_robot_log("信息", "正在连接中...")

            # 使用机械臂配置进行连接
            result = self.robot_service.connect(self.current_robot_config)
            debug(f"robot_service.connect结果: {result}", "ROBOT_UI")

            # 注册日志回调 - 使用emit_log方法发射信号，确保线程安全
            if hasattr(self.robot_service, 'register_log_callback'):
                self.robot_service.register_log_callback(self.emit_log)

            if result['success']:
                info(f"机械臂连接成功: {robot_name}", "ROBOT_UI")
                self.robot_status_label.setText(f"🟢 已连接: {robot_name}")
                self.robot_status_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 14px;")
                self.connect_btn.setText("断开")
                self.connect_btn.setEnabled(True)
                self.connection_timer.start(1000)
                self.add_robot_log("信息", f"机械臂连接成功: {robot_name}")

                # 发布机械臂连接事件到事件总线
                connection_info = RobotConnectionInfo(
                    robot_id=robot_name,
                    name=robot_name,
                    robot_type=self.current_robot_config.get('type', 'unknown'),
                    config=self.current_robot_config,
                    timestamp=time.time()
                )
                get_hardware_event_bus().publish_robot_connected("robot_control", connection_info)
            else:
                # 连接失败
                error(f"机械臂连接失败: {result.get('error')}", "ROBOT_UI")
                self.robot_status_label.setText(f"🔴 连接失败: {result.get('error', '未知错误')}")
                self.robot_status_label.setStyleSheet("color: #f44336; font-weight: bold; font-size: 14px;")
                self.connect_btn.setEnabled(True)
                self.add_robot_log("错误", f"机械臂连接失败: {result.get('error', '未知错误')}")

    def emit_log(self, level, message):
        """发射日志信号，用于跨线程调用"""
        self.log_signal.emit(level, message)

    def test_robot_connection(self):
        """测试机械臂连接 (执行标定流程)"""
        info("用户点击标定测试按钮", "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("信息", "用户点击标定测试按钮")

        if not self.robot_service.is_connected():
            warning("设备未连接，无法执行标定", "ROBOT_UI")
            self.add_robot_log("警告", "设备未连接，无法执行标定")
            QMessageBox.warning(self, "操作失败", "请先连接机械臂后再进行标定")
            return

        # 懒加载标定服务 (确保CameraService就绪)
        if not self.calibration_service and self.camera_service:
            self.calibration_service = CalibrationService(self.robot_service, self.camera_service)
            # 使用emit_log确保跨线程日志安全
            self.calibration_service.set_log_callback(self.emit_log)

        if self.calibration_service:
            # 使用标定服务启动流程
            self.add_robot_log("信息", "调用标定服务启动流程...")
            result = self.calibration_service.start_calibration()
        else:
            # 如果没有相机服务，回退到原始的测试连接
            self.add_robot_log("警告", "相机服务未就绪，仅执行机械臂运动测试")

    def show_3d_calibration_dialog(self):
        """显示3D标定配置对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("3D标定设置")
        layout = QVBoxLayout()

        # 层数选择
        layer_group = QGroupBox("层数选择")
        layer_layout = QHBoxLayout()
        layer_layout.addWidget(QLabel("四棱台层数:"))
        layer_spin = QSpinBox()
        layer_spin.setRange(2, 6)
        layer_spin.setValue(3)
        layer_layout.addWidget(layer_spin)
        layer_group.setLayout(layer_layout)
        layout.addWidget(layer_group)

        # 尺寸参数
        size_group = QGroupBox("棱台尺寸参数 (mm)")
        size_layout = QGridLayout()

        # 底面边长
        size_layout.addWidget(QLabel("底面边长:"), 0, 0)
        base_width_spin = QDoubleSpinBox()
        base_width_spin.setRange(0.0, 5000.0)
        base_width_spin.setMinimum(0.0)
        base_width_spin.setSingleStep(1.0)
        base_width_spin.setValue(100.0)
        base_width_spin.setSuffix(" mm")
        size_layout.addWidget(base_width_spin, 0, 1)

        # 顶面边长
        size_layout.addWidget(QLabel("顶面边长:"), 1, 0)
        top_width_spin = QDoubleSpinBox()
        top_width_spin.setRange(0.0, 5000.0)
        top_width_spin.setMinimum(0.0)
        top_width_spin.setSingleStep(1.0)
        top_width_spin.setValue(50.0)
        top_width_spin.setSuffix(" mm")
        size_layout.addWidget(top_width_spin, 1, 1)

        # 高度
        size_layout.addWidget(QLabel("总高度:"), 2, 0)
        height_spin = QDoubleSpinBox()
        height_spin.setRange(0.0, 5000.0)
        height_spin.setMinimum(0.0)
        height_spin.setSingleStep(1.0)
        height_spin.setValue(50.0)
        height_spin.setSuffix(" mm")
        size_layout.addWidget(height_spin, 2, 1)
        
        # 标定方向
        size_layout.addWidget(QLabel("Generate Direction:"), 4, 0)
        direction_combo = QComboBox()
        direction_combo.addItems(["Z+", "Z-", "X+", "X-", "Y+", "Y-"])
        # Default to Z+ (Standard)
        direction_combo.setCurrentText("Z+")
        size_layout.addWidget(direction_combo, 4, 1)

        size_group.setLayout(size_layout)
        layout.addWidget(size_group)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            params = {
                "base_width": base_width_spin.value(),
                "top_width": top_width_spin.value(),
                "height": height_spin.value(),
                # Tilt angle removed from UI
                "direction": direction_combo.currentText()
            }
            self.execute_3d_calibration(layer_spin.value(), params)

    def execute_3d_calibration(self, layers: int, params: dict = None):
        """执行3D标定轨迹"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "错误", "请先连接机械臂")
            return

        # 懒加载标定服务
        if not self.calibration_service:
            if not self.camera_service:
                 # 尝试获取全局唯一的camera_service，或者直接创建临时的
                # 这里假设上层已经初始化了camera_service，如果没有则警告
                pass 
            
            self.calibration_service = CalibrationService(self.robot_service, self.camera_service)
            self.calibration_service.set_log_callback(self.emit_log)

        # 使用自定义参数或默认参数
        if params is None:
            params = {
                "base_width": 100.0,
                "top_width": 50.0,
                "height": 50.0,
                "direction": "Z+"
            }

        msg = f"即将执行3D自动标定 (C++加速)\n\n" \
              f"层数: {layers}\n" \
              f"底面: {params['base_width']}mm, 顶面: {params['top_width']}mm\n" \
              f"高度: {params['height']}mm\n" \
              f"方向: {params.get('direction', 'Z+')}\n\n" \
              f"请确认周围无障碍物，机械臂将自动运行！"

        reply = QMessageBox.question(self, "确认执行", msg,
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                   
        if reply == QMessageBox.StandardButton.Yes:
            self.add_robot_log("信息", "启动C++ 3D标定流程...")
            # 调用Service层的3D标定接口
            result = self.calibration_service.start_3d_calibration(layers, params)
            
            if result['success']:
                QMessageBox.information(self, "已启动", "3D标定程序已在后台启动，请关注日志输出。")
            else:
                QMessageBox.warning(self, "启动失败", f"无法启动3D标定: {result.get('error')}")

    def confirm_calibration_step(self):
        """确认标定步骤"""
        info("用户点击标定确认按钮", "ROBOT_UI")
        result = self.robot_service.confirm_calibration()
        if result['success']:
            self.add_robot_log("信息", "已发送确认信号 (ENTER)")
        else:
            self.add_robot_log("错误", f"发送确认信号失败: {result.get('error')}")
            QMessageBox.warning(self, "操作失败", f"发送确认信号失败: {result.get('error')}")

    def on_speed_changed(self):
        """速度滑块释放时调用"""
        speed = self.jog_speed_slider.value()
        result = self.robot_service.set_speed(speed)
        if result['success']:
            self.add_robot_log("信息", f"设置全局速度: {speed}%")
        else:
            self.add_robot_log("错误", f"设置速度失败: {result.get('error')}")

    def on_mode_changed(self, mode_text):
        """运动模式改变"""
        mode_map = {
            "手动": MotionMode.MANUAL,
            "自动": MotionMode.AUTOMATIC,
            "点动": MotionMode.JOG
        }
        mode = mode_map.get(mode_text, MotionMode.MANUAL)
        result = self.robot_service.set_motion_mode(mode)
        if not result['success']:
            warning(f"设置运动模式失败: {result.get('error')}", "ROBOT_UI", LogCategory.HARDWARE)

    def jog_move(self, direction: str):
        """点动移动"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            self.add_robot_log("警告", "点动操作失败: 机械臂未连接")
            return

        speed = self.jog_speed_slider.value()
        distance = self.jog_distance_spinbox.value()  # 使用可配置的点动距离

        axis = direction[0]  # 取第一个字母作为轴
        direction_value = 1 if '+' in direction else -1

        # 获取当前位置用于日志对比
        try:
            current_pos = self.robot_service.get_position()
            if current_pos and len(current_pos) >= 6:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f}, {current_pos[3]:.1f}, {current_pos[4]:.1f}, {current_pos[5]:.1f})"
            elif current_pos and len(current_pos) >= 3:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f})"
            else:
                current_pos_str = "未知"
        except:
            current_pos_str = "获取失败"

        # 从service层执行点动移动
        movement_info = f"执行点动移动: 轴{axis}, 方向:{'+' if direction_value > 0 else '-'}, 速度:{speed}%, 距离:{distance}mm"
        info(f"开始{movement_info}", "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("运动", movement_info)
        self.add_robot_log("运动", f"点动移动起始位置: {current_pos_str}")

        # 实际调用service层的jog_move方法
        result = self.robot_service.jog_move(axis, speed, distance * direction_value)

        if result['success']:
            self.add_robot_log("运动", f"点动移动命令发送成功: {axis}轴{direction_value:+d} {distance}mm")
            # 延迟1.5秒检查结果，给予足够时间让机器人移动
            QTimer.singleShot(1500, lambda: self._handle_jog_completion(current_pos_str, axis, direction_value, distance, speed))
        else:
            error_msg = result.get('error', '未知错误')
            error(f"点动移动失败: {error_msg}", "ROBOT_UI", LogCategory.HARDWARE)
            self.add_robot_log("错误", f"点动移动失败: {axis}轴{direction_value:+d} - {error_msg}")

    def _handle_jog_completion(self, current_pos_str, axis, direction_value, distance, speed):
        """处理点动完成后的状态更新"""
        try:
            new_position = self.robot_service.get_position()
            if new_position and len(new_position) >= 6:
                new_pos_str = f"({new_position[0]:.1f}, {new_position[1]:.1f}, {new_position[2]:.1f}, {new_position[3]:.1f}, {new_position[4]:.1f}, {new_position[5]:.1f})"
            elif new_position and len(new_position) >= 3:
                new_pos_str = f"({new_position[0]:.1f}, {new_position[1]:.1f}, {new_position[2]:.1f})"
            else:
                new_pos_str = "未知"

            if new_position:
                self.add_robot_log("运动", f"点动移动后位置更新: {new_pos_str}")
                info(f"点动移动完成: {current_pos_str} → {new_pos_str}", "ROBOT_UI")

                # 发布位置变化事件到事件总线
                robot_id = getattr(self, 'current_robot_config', {}).get('name', 'unknown_robot')
                position_info = RobotPositionInfo(
                    robot_id=robot_id,
                    position=new_position,
                    movement_type="jog",
                    speed=speed,
                    axis=axis,
                    direction=direction_value,
                    distance=distance,
                    timestamp=time.time()
                )
                get_hardware_event_bus().publish_robot_position("robot_control", position_info)

                # 立即更新UI状态
                self.update_status()
            else:
                self.add_robot_log("警告", "无法获取点动移动后位置")
        except Exception as pos_error:
            self.add_robot_log("警告", f"获取点动移动后位置失败: {pos_error}")

    def move_to_position(self):
        """移动到指定位置"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            self.add_robot_log("警告", "位置移动失败: 机械臂未连接")
            return

        x = self.x_spinbox.value()
        y = self.y_spinbox.value()
        z = self.z_spinbox.value()
        rx = self.rx_spinbox.value()
        ry = self.ry_spinbox.value()
        rz = self.rz_spinbox.value()
        speed = self.speed_slider.value()

        # 构建位置移动命令
        position_command = {
            'position': [x, y, z, rx, ry, rz],
            'speed_percent': speed
        }

        # 记录当前位置（从service层获取）
        try:
            current_pos = self.robot_service.get_position()
            if current_pos and len(current_pos) >= 6:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f}, {current_pos[3]:.1f}, {current_pos[4]:.1f}, {current_pos[5]:.1f})"
            elif current_pos and len(current_pos) >= 3:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f}, -, -, -)"
            else:
                current_pos_str = "未知"
        except Exception as pos_error:
            warning(f"获取当前位置失败: {pos_error}", "ROBOT_UI")
            current_pos_str = "获取失败"

        target_pos_str = f"({x:.1f}, {y:.1f}, {z:.1f}, {rx:.1f}, {ry:.1f}, {rz:.1f})"

        # 记录移动日志
        movement_info = f"开始位置移动: {current_pos_str} → {target_pos_str}, 速度: {speed}%"
        info(movement_info, "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("运动", movement_info)

        # 实际调用service层的move_to方法
        result = self.robot_service.move_to(x, y, z, rx, ry, rz)

        if result['success']:
            self.add_robot_log("运动", f"位置移动命令发送成功: 目标位置{target_pos_str}，速度{speed}%")
            info(f"位置移动命令已发送到service层", "ROBOT_UI", LogCategory.HARDWARE)

            # 短暂延迟后检查位置更新
            import time
            time.sleep(0.3)  # 等待移动完成

            # 添加移动后的位置日志
            try:
                final_position = self.robot_service.get_position()
                if final_position and len(final_position) >= 6:
                    final_pos_str = f"({final_position[0]:.1f}, {final_position[1]:.1f}, {final_position[2]:.1f}, {final_position[3]:.1f}, {final_position[4]:.1f}, {final_position[5]:.1f})"
                elif final_position and len(final_position) >= 3:
                    final_pos_str = f"({final_position[0]:.1f}, {final_position[1]:.1f}, {final_position[2]:.1f}, -, -, -)"
                else:
                    final_pos_str = "获取失败"

                self.add_robot_log("运动", f"位置移动完成，最终位置: {final_pos_str}")
                info(f"位置移动完成: {target_pos_str}", "ROBOT_UI")

                # 发布位置变化事件到事件总线
                robot_id = getattr(self, 'current_robot_config', {}).get('name', 'unknown_robot')
                position_info = RobotPositionInfo(
                    robot_id=robot_id,
                    position=final_position,
                    movement_type="position",
                    speed=speed,
                    target_position=[x, y, z, rx, ry, rz],
                    timestamp=time.time()
                )
                get_hardware_event_bus().publish_robot_position("robot_control", position_info)

                # 立即更新UI状态
                self.update_status()
            except Exception as pos_error:
                self.add_robot_log("警告", f"获取位置移动后位置失败: {pos_error}")
        else:
            error_msg = result.get('error', '未知错误')
            error(f"位置移动失败: {error_msg}", "ROBOT_UI", LogCategory.HARDWARE)
            self.add_robot_log("错误", f"位置移动失败: {target_pos_str} - {error_msg}")

    def go_home(self):
        """回原点"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            self.add_robot_log("警告", "回原点操作失败: 机械臂未连接")
            return

        info("开始执行回原点操作", "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("信息", "开始执行回原点操作")

        # 获取当前位置用于日志
        try:
            current_pos = self.robot_service.get_position()
            if current_pos and len(current_pos) >= 6:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f}, {current_pos[3]:.1f}, {current_pos[4]:.1f}, {current_pos[5]:.1f})"
            elif current_pos and len(current_pos) >= 3:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f})"
            else:
                 current_pos_str = "未知"
        except:
            current_pos_str = "获取失败"

        # 实际调用service层的home方法
        result = self.robot_service.home()

        if result['success']:
            self.add_robot_log("信息", f"回原点操作开始，起始位置: {current_pos_str}")
            info("回原点操作开始", "ROBOT_UI", LogCategory.HARDWARE)

            # 短暂延迟后检查位置更新
            import time
            time.sleep(0.5)  # 等待回原点完成

            # 添加回原点后的位置日志
            try:
                home_position = self.robot_service.get_position()
                if home_position and len(home_position) >= 6:
                    home_pos_str = f"({home_position[0]:.1f}, {home_position[1]:.1f}, {home_position[2]:.1f}, {home_position[3]:.1f}, {home_position[4]:.1f}, {home_position[5]:.1f})"
                elif home_position and len(home_position) >= 3:
                    home_pos_str = f"({home_position[0]:.1f}, {home_position[1]:.1f}, {home_position[2]:.1f})"
                else:
                    home_pos_str = "获取失败"

                self.add_robot_log("信息", f"回原点操作完成，当前位置: {home_pos_str}")
                info("回原点操作已完成", "ROBOT_UI", LogCategory.HARDWARE)

                # 立即更新UI状态
                self.update_status()
            except Exception as pos_error:
                self.add_robot_log("警告", f"获取回原点后位置失败: {pos_error}")
        else:
            error_msg = result.get('error', '未知错误')
            error(f"回原点操作失败: {error_msg}", "ROBOT_UI", LogCategory.HARDWARE)
            self.add_robot_log("错误", f"回原点操作失败: {error_msg}")

    def emergency_stop(self):
        """紧急停止"""
        info("用户触发紧急停止", "ROBOT_UI", LogCategory.HARDWARE)
        self.add_robot_log("信息", "用户触发紧急停止")

        # 获取当前位置用于日志
        try:
            current_pos = self.robot_service.get_position()
            if current_pos and len(current_pos) >= 6:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f}, {current_pos[3]:.1f}, {current_pos[4]:.1f}, {current_pos[5]:.1f})"
            elif current_pos and len(current_pos) >= 3:
                current_pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f})"
            else:
                 current_pos_str = "未知"
        except:
            current_pos_str = "获取失败"

        result = self.robot_service.emergency_stop()
        if result['success']:
            # 添加紧急停止日志
            self.add_log_on_emergency_stop()
            self.add_robot_log("急停", f"紧急停止执行成功，停止位置: {current_pos_str}")
            QMessageBox.warning(self, "紧急停止", "机械臂已紧急停止！")
        else:
            error_msg = result.get('error', '未知错误')
            warning(f"紧急停止失败: {error_msg}", "ROBOT_UI", LogCategory.HARDWARE)
            self.add_robot_log("错误", f"紧急停止失败: {error_msg}")
            QMessageBox.warning(self, "紧急停止失败", f"紧急停止失败: {error_msg}")

    def toggle_path_recording(self):
        """切换路径记录状态"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            return

        if not self.is_recording_path:
            # 开始记录
            path_name = f"路径_{int(time.time())}"
            result = self.robot_service.start_path_recording(path_name)
            if result['success']:
                self.is_recording_path = True
                self.record_btn.setText("⏹ 停止记录")
                self.record_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """)
                self.add_point_btn.setEnabled(True)

                # 路径对象将由具体的驱动管理（模拟或真实）
                self.recorded_path = self.robot_service.get_recorded_path()
                self.refresh_path_list()

                QMessageBox.information(self, "记录开始", f"开始记录路径: {path_name}")
            else:
                warning(f"开始记录失败: {result.get('error')}", "PATH_UI")
        else:
            # 停止记录
            result = self.robot_service.stop_path_recording()
            if result['success']:
                self.is_recording_path = False
                self.record_btn.setText("⏺ 开始记录")
                self.record_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF9800;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """)
                self.add_point_btn.setEnabled(False)

                # 获取记录的路径
                self.recorded_path = self.robot_service.get_recorded_path()
                self.refresh_path_list()

                if self.recorded_path and len(self.recorded_path.points) > 0:
                    # 自动弹出保存对话框
                    self.save_recorded_path()
            else:
                warning(f"停止记录失败: {result.get('error')}", "PATH_UI")

    def save_recorded_path(self):
        """保存记录的路径"""
        if not self.recorded_path:
            return

        try:
            dialog = SavePathDialog(f"路径_{len(self.recorded_path.points)}点", self)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                path_info = dialog.get_path_info()
                self.recorded_path.name = path_info['name']
                self.recorded_path.description = path_info['description']

                result = self.robot_service.save_path(self.recorded_path)
                if result['success']:
                    try:
                        self.refresh_path_list()
                        QMessageBox.information(self, "保存成功", f"路径 '{self.recorded_path.name}' 已保存到 workspace/paths/")
                    except RuntimeError:
                        # 窗口已被删除，跳过UI更新
                        info(f"路径已保存: {self.recorded_path.name} (窗口已关闭)", "ROBOT_UI")
                else:
                    try:
                        warning(f"保存路径失败: {result.get('error')}", "PATH_UI")
                    except RuntimeError:
                        # 窗口已被删除，跳过UI更新
                        error(f"保存路径失败: {result.get('error')} (窗口已关闭)", "ROBOT_UI")
        except Exception as e:
            # 保存路径过程中的异常
            error(f"保存路径失败: {e}", "ROBOT_UI")
            QMessageBox.critical(self, "错误", f"保存路径失败: {e}")

    def save_current_path(self):
        """保存当前路径"""
        if not self.recorded_path or len(self.recorded_path.points) == 0:
            QMessageBox.warning(self, "保存失败", "没有可保存的路径数据")
            return

        try:
            dialog = SavePathDialog(f"路径_{len(self.recorded_path.points)}点", self)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                path_info = dialog.get_path_info()
                self.recorded_path.name = path_info['name']
                self.recorded_path.description = path_info['description']

                # 通过服务保存路径
                result = self.robot_service.save_path(self.recorded_path)
                if result['success']:
                    try:
                        self.add_robot_log("信息", f"路径已保存: {path_info['name']}")
                        info(f"路径已保存: {path_info['name']}", "ROBOT_UI")
                        self.refresh_path_list()
                        QMessageBox.information(self, "保存成功", f"路径 '{path_info['name']}' 已保存到 workspace/paths/")
                    except RuntimeError:
                        # 窗口已被删除，跳过UI更新
                        info(f"路径已保存: {path_info['name']}", "ROBOT_UI")
                else:
                    try:
                        error_msg = result.get('error', '未知错误')
                        self.add_robot_log("错误", f"保存路径失败: {error_msg}")
                        QMessageBox.warning(self, "保存失败", f"保存路径失败: {error_msg}")
                    except RuntimeError:
                        # 窗口已被删除，跳过UI更新
                        error(f"保存路径失败: {result.get('error')}", "ROBOT_UI")
        except RuntimeError as e:
            # 对话框创建失败
            error(f"创建保存对话框失败: {e}", "ROBOT_UI")
            QMessageBox.critical(self, "错误", "无法创建保存对话框，请重试")

    def add_path_point(self):
        """添加当前路径点"""
        if not self.is_recording_path:
            QMessageBox.warning(self, "未在记录", "请先开始路径记录")
            return

        result = self.robot_service.add_path_point()
        if result['success']:
            info("路径点已添加", "PATH_UI")

            # 更新当前路径显示
            self.recorded_path = self.robot_service.get_recorded_path()
            self.refresh_path_list()

            # 获取当前路径以显示点数
            current_path = self.robot_service.get_recorded_path()
            point_count = len(current_path.points) if current_path else 0

            # 更新当前路径标签
            self.current_path_label.setText(f"📄 当前路径: {current_path.name if current_path else '未命名'} ({point_count}点)")

            # 获取当前位置信息
            try:
                current_pos = self.robot_service.get_position()
                if current_pos and len(current_pos) >= 6:
                    pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f}, {current_pos[3]:.1f}, {current_pos[4]:.1f}, {current_pos[5]:.1f})"
                    self.add_robot_log("路径", f"路径点已添加，当前位置: {pos_str}")
                elif current_pos and len(current_pos) >= 3:
                    pos_str = f"({current_pos[0]:.1f}, {current_pos[1]:.1f}, {current_pos[2]:.1f})"
                    self.add_robot_log("路径", f"路径点已添加，当前位置: {pos_str}")
                else:
                    self.add_robot_log("路径", f"路径点已添加（当前共{point_count}个点）")
            except Exception:
                self.add_robot_log("路径", f"路径点已添加（当前共{point_count}个点）")
        else:
            warning(f"添加路径点失败: {result.get('error')}", "PATH_UI")

    def clear_recorded_path(self):
        """清空记录的路径"""
        if self.recorded_path and len(self.recorded_path.points) > 0:
            reply = QMessageBox.question(
                self, "确认清空",
                f"确定要清空当前记录的路径吗？\n包含{len(self.recorded_path.points)}个路径点。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                result = self.robot_service.clear_recorded_path()
                if result['success']:
                    self.recorded_path = None
                    self.current_path_label.setText("📄 无路径加载")
                    self.refresh_path_list()
                    self.add_robot_log("信息", "当前记录的路径已清空")
                    QMessageBox.information(self, "清空成功", "记录的路径已清空")

    def refresh_path_list(self):
        """刷新路径列表显示"""
        try:
            # 构建路径列表
            display_paths = []

            # 1. 当前路径始终显示在首行（即使为空）
            if self.recorded_path:
                status = "🔴 记录中" if self.is_recording_path else "⏸ 已停止"
                display_paths.append({
                    'path': self.recorded_path,
                    'status': status,
                    'is_recording': self.is_recording_path,
                    'is_current': True
                })
            else:
                # 使用缓存的空路径占位符或创建一个新的
                if self._empty_current_path is None:
                    from core.interfaces.hardware import RobotPath
                    self._empty_current_path = RobotPath(
                        name="无当前路径",
                        points=[],
                        created_time=time.time(),
                        description="点击'⏺ 开始记录'或'📂 加载已保存'来创建路径"
                    )

                display_paths.append({
                    'path': self._empty_current_path,
                    'status': "📝 无路径",
                    'is_recording': False,
                    'is_current': True,
                    'is_empty': True
                })

            # 2. 添加其他已加载的路径
            for path_data in self.path_list:
                try:
                    if hasattr(path_data, 'get') and 'path' in path_data:
                        path = path_data['path']
                        # 确保不重复添加当前路径
                        if path != self.recorded_path:
                            display_paths.append({
                                'path': path,
                                'status': "✅ 已加载",
                                'is_recording': False,
                                'is_current': False,
                                'is_empty': False
                            })
                except Exception as e:
                    # 跳过无效的路径数据
                    continue

            # 设置表格行数
            if display_paths:
                self.path_table.setRowCount(len(display_paths))
                # 清除所有现有的合并
                self.path_table.clearSpans()
            else:
                # 没有路径时显示提示
                self.path_table.setRowCount(1)
                self.path_table.clearSpans()  # 清除所有现有的合并
                no_path_item = QTableWidgetItem("暂无记录的路径")
                no_path_item.setToolTip("点击'⏺ 开始记录'按钮开始记录新路径")
                self.path_table.setItem(0, 0, no_path_item)
                # 只有在没有其他内容时才合并单元格
                self.path_table.setSpan(0, 0, 1, 6)
                return

            # 填充表格数据
            for row, path_data in enumerate(display_paths):
                path = path_data['path']

                # 路径名称
                name_text = path.name or "未命名路径"
                if path_data['is_current']:
                    name_text = "🎯 " + name_text  # 当前路径添加标记
                name_item = QTableWidgetItem(name_text)
                name_item.setToolTip("当前正在记录/已记录的路径" if path_data['is_current'] else "已加载的路径")
                self.path_table.setItem(row, 0, name_item)

                # 点数
                points_item = QTableWidgetItem(str(len(path.points)))
                points_item.setToolTip(f"路径包含 {len(path.points)} 个路径点")
                self.path_table.setItem(row, 1, points_item)

                # 创建时间
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.created_time))
                time_item = QTableWidgetItem(time_str)
                time_item.setToolTip(f"路径创建于 {time_str}")
                self.path_table.setItem(row, 2, time_item)

                # 描述
                desc_item = QTableWidgetItem(path.description or "")
                desc_item.setToolTip(path.description or "无描述")
                self.path_table.setItem(row, 3, desc_item)

                # 状态
                status_item = QTableWidgetItem(path_data['status'])
                if path_data['is_recording']:
                    status_item.setStyleSheet("color: red; font-weight: bold;")
                self.path_table.setItem(row, 4, status_item)

                # 操作按钮
                if path_data.get('is_empty', False):
                    # 空路径占位符，不显示操作按钮
                    action_btn = QPushButton("➕ 新建路径")
                    action_btn.clicked.connect(self.start_new_path_recording)
                    action_btn.setStyleSheet("background-color: #2196F3; color: white;")
                elif path_data['is_current'] and path_data['is_recording']:
                    # 正在记录的路径显示停止按钮
                    action_btn = QPushButton("⏹ 停止记录")
                    action_btn.clicked.connect(self.toggle_path_recording)
                    action_btn.setStyleSheet("background-color: #f44336; color: white;")
                elif path_data['is_current'] and not path_data['is_recording'] and len(path.points) > 0:
                    # 已停止的当前路径显示保存按钮
                    action_btn = QPushButton("💾 保存路径")
                    action_btn.clicked.connect(self.save_current_path)
                    action_btn.setStyleSheet("background-color: #4CAF50; color: white;")
                elif not path_data['is_current']:
                    # 已加载的其他路径显示移除按钮
                    action_btn = QPushButton("❌ 移除")
                    action_btn.clicked.connect(lambda checked, idx=row: self.remove_path_from_list(idx))
                    action_btn.setStyleSheet("background-color: #FF9800; color: white;")
                else:
                    # 无数据路径
                    action_btn = QPushButton("📝 无数据")
                    action_btn.setEnabled(False)
                    action_btn.setStyleSheet("background-color: #ccc; color: #666666;")

                action_btn.setMaximumWidth(80)
                self.path_table.setCellWidget(row, 5, action_btn)

        except Exception as e:
            error(f"刷新路径列表显示失败: {e}", "ROBOT_UI")

    def start_new_path_recording(self):
        """开始新的路径记录"""
        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            return

        # 生成路径名称
        path_name = f"路径_{int(time.time())}"

        # 开始记录
        result = self.robot_service.start_path_recording(path_name)
        if result['success']:
            self.is_recording_path = True
            self.recorded_path = self.robot_service.get_recorded_path()

            # 更新UI
            self.record_btn.setText("⏹ 停止记录")
            self.record_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
            self.add_point_btn.setEnabled(True)

            # 刷新路径列表
            self.refresh_path_list()

            QMessageBox.information(self, "记录开始", f"开始记录新路径: {path_name}")
        else:
            warning(f"开始记录失败: {result.get('error')}", "PATH_UI")

    def on_path_selection_changed(self):
        """处理路径表格选择变化事件"""
        try:
            selected_items = self.path_table.selectedItems()
            if not selected_items:
                # 没有选中任何项
                self.current_path_label.setText("📄 无路径加载")
                return

            # 获取选中的行
            selected_rows = set()
            for item in selected_items:
                selected_rows.add(item.row())

            if len(selected_rows) == 1:
                # 单选，显示选中的路径信息
                row = list(selected_rows)[0]

                # 获取显示的路径列表
                display_paths = []
                if self.recorded_path:
                    status = "🔴 记录中" if self.is_recording_path else "⏸ 已停止"
                    display_paths.append({
                        'path': self.recorded_path,
                        'status': status,
                        'is_recording': self.is_recording_path,
                        'is_current': True
                    })
                else:
                    from core.interfaces.hardware import RobotPath
                    empty_current_path = RobotPath(
                        name="无当前路径",
                        points=[],
                        created_time=time.time(),
                        description="点击'⏺ 开始记录'或'📂 加载已保存'来创建路径"
                    )
                    display_paths.append({
                        'path': empty_current_path,
                        'status': "📝 无路径",
                        'is_recording': False,
                        'is_current': True,
                        'is_empty': True
                    })

                # 安全地添加已加载路径
                for path_data in self.path_list:
                    try:
                        if hasattr(path_data, 'get') and 'path' in path_data:
                            if path_data['path'] != self.recorded_path:
                                display_paths.append({
                                    'path': path_data['path'],
                                    'status': "✅ 已加载",
                                    'is_recording': False,
                                    'is_current': False,
                                    'is_empty': False
                                })
                    except Exception as e:
                        continue

                # 检查行索引是否有效
                if row < len(display_paths):
                    path_data = display_paths[row]
                    path = path_data['path']

                    if not path_data.get('is_empty', False):
                        # 更新路径信息显示
                        status_text = "当前" if path_data['is_current'] else "已加载"
                        self.current_path_label.setText(
                            f"📄 {status_text}路径: {path.name} ({len(path.points)}点) {path_data['status']}"
                        )
                    else:
                        self.current_path_label.setText("📄 无路径加载")
            else:
                # 多选
                self.current_path_label.setText(f"📄 已选中 {len(selected_rows)} 个路径")

        except Exception as e:
            error(f"处理路径选择变化失败: {e}", "ROBOT_UI")

    def on_path_double_clicked(self, row, column):
        """处理路径表格双击事件"""
        try:
            # 获取显示的路径列表
            display_paths = []
            if self.recorded_path:
                status = "🔴 记录中" if self.is_recording_path else "⏸ 已停止"
                display_paths.append({
                    'path': self.recorded_path,
                    'status': status,
                    'is_recording': self.is_recording_path,
                    'is_current': True
                })
            else:
                from core.interfaces.hardware import RobotPath
                empty_current_path = RobotPath(
                    name="无当前路径",
                    points=[],
                    created_time=time.time(),
                    description="点击'⏺ 开始记录'或'📂 加载已保存'来创建路径"
                )
                display_paths.append({
                    'path': empty_current_path,
                    'status': "📝 无路径",
                    'is_recording': False,
                    'is_current': True,
                    'is_empty': True
                })

            for path_data in self.path_list:
                if path_data['path'] != self.recorded_path:
                    display_paths.append({
                        'path': path_data['path'],
                        'status': "✅ 已加载",
                        'is_recording': False,
                        'is_current': False,
                        'is_empty': False
                    })

            # 检查行索引是否有效
            if row >= len(display_paths):
                return

            path_data = display_paths[row]
            path = path_data['path']

            # 如果是空路径，不处理双击
            if path_data.get('is_empty', False):
                return

            # 如果不是当前路径，设置为当前路径并开始播放
            if not path_data['is_current']:
                self.set_path_as_current(path)

                # 开始播放路径
                self.play_selected_path()
            else:
                # 当前路径，直接播放
                self.play_selected_path()

        except Exception as e:
            error(f"双击路径处理失败: {e}", "ROBOT_UI")
            QMessageBox.warning(self, "错误", f"双击路径处理失败: {e}")

    def play_selected_path(self):
        """播放选中的路径"""
        try:
            if not self.recorded_path or not self.recorded_path.points:
                QMessageBox.warning(self, "警告", "当前路径为空，无法播放")
                return

            if not self.robot_service.is_connected():
                QMessageBox.warning(self, "警告", "请先连接机械臂")
                return

            # 禁用播放按钮，防止重复点击
            self.play_btn.setEnabled(False)
            self.play_btn.setText("🔄 播放中...")
            QApplication.processEvents()

            # 开始播放路径
            self.add_robot_log("信息", f"开始播放路径: {self.recorded_path.name} ({len(self.recorded_path.points)}个点)")

            result = self.robot_service.play_path(self.recorded_path)

            if result['success']:
                self.add_robot_log("信息", f"路径播放完成: {self.recorded_path.name}")
                QMessageBox.information(self, "播放完成", f"路径 '{self.recorded_path.name}' 播放完成")
            else:
                self.add_robot_log("错误", f"路径播放失败: {result.get('error', '未知错误')}")
                QMessageBox.warning(self, "播放失败", f"路径播放失败: {result.get('error', '未知错误')}")

        except Exception as e:
            error(f"播放路径失败: {e}", "ROBOT_UI")
            QMessageBox.warning(self, "错误", f"播放路径失败: {e}")
        finally:
            # 恢复播放按钮状态
            self.play_btn.setEnabled(True)
            self.play_btn.setText("▶️ 播放路径")

    def setup_path_table_context_menu(self):
        """设置路径表格的右键菜单"""
        self.path_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.path_table.customContextMenuRequested.connect(self.show_path_context_menu)

    def show_path_context_menu(self, position):
        """显示路径右键菜单 - 安全版本，使用信号避免段错误"""
        try:
            item = self.path_table.itemAt(position)
            if not item:
                return

            row = item.row()
            if row < 0:
                return

            # 使用信号延迟处理，避免在事件处理器中创建菜单
            self.show_context_menu_signal.emit(row, 0)

        except Exception as e:
            error(f"右键菜单触发异常: {e}", "ROBOT_UI")

    def _handle_context_menu_safely(self, row, column):
        """安全处理右键菜单 - 在主线程中延迟执行"""
        try:
            # 获取路径名称
            name_item = self.path_table.item(row, 0)
            if not name_item:
                return

            path_name = name_item.text()
            self.add_robot_log("信息", f"右键点击路径: {path_name}")

            # 获取对应的路径对象
            path = self._get_path_from_table_row(row)
            if path:
                # 创建简单的菜单选择对话框
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(f"路径操作: {path_name}")
                msg_box.setText(f"路径名称: {path_name}\n路径点数: {len(path.points)}\n\n请选择操作:")

                details_btn = msg_box.addButton("📋 查看详情", QMessageBox.ButtonRole.ActionRole)
                cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)

                msg_box.exec()

                if msg_box.clickedButton() == details_btn:
                    self._show_path_details_safe(path)
            else:
                # 空路径或无法获取路径时显示基本信息
                QMessageBox.information(
                    self,
                    "路径信息",
                    f"路径名称: {path_name}\n行号: {row}\n\n提示：双击行可以直接播放路径"
                )

        except Exception as e:
            error(f"安全处理右键菜单异常: {e}", "ROBOT_UI")
            # 最小化处理，避免二次异常

    def _get_path_from_table_row(self, row):
        """安全地从表格行获取路径对象"""
        try:
            # 获取显示的路径列表逻辑（简化版）
            display_paths = []

            # 当前路径
            if self.recorded_path:
                display_paths.append(self.recorded_path)
            else:
                from core.interfaces.hardware import RobotPath
                empty_current_path = RobotPath(
                    name="无当前路径",
                    points=[],
                    created_time=time.time(),
                    description="点击'⏺ 开始记录'或'📂 加载已保存'来创建路径"
                )
                display_paths.append(empty_current_path)

            # 已加载路径
            for path_data in self.path_list:
                try:
                    if hasattr(path_data, 'get') and 'path' in path_data:
                        if path_data['path'] != self.recorded_path:
                            display_paths.append(path_data['path'])
                except Exception:
                    continue

            # 检查行索引是否有效
            if 0 <= row < len(display_paths):
                return display_paths[row]

            return None

        except Exception as e:
            error(f"获取路径对象失败: {e}", "ROBOT_UI")
            return None

    def _show_path_details_safe(self, path):
        """安全显示路径详情"""
        try:
            if not path:
                QMessageBox.information(self, "路径详情", "路径为空")
                return

            # 创建详情对话框
            dialog = QDialog(self)
            dialog.setWindowTitle(f"路径详情: {path.name}")
            dialog.setMinimumSize(500, 400)
            layout = QVBoxLayout()

            # 基本信息
            info_text = f"路径名称: {path.name}\n"
            info_text += f"路径点数: {len(path.points)}\n"
            info_text += f"创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(path.created_time))}\n"
            info_text += f"描述: {path.description or '无描述'}"

            info_label = QLabel(info_text)
            info_label.setStyleSheet("QLabel { padding: 10px; background-color: #f5f5f5; border-radius: 5px; }")
            layout.addWidget(info_label)

            # 路径点简要信息
            if path.points:
                points_label = QLabel("路径点信息:")
                points_label.setStyleSheet("QLabel { font-weight: bold; margin-top: 10px; }")
                layout.addWidget(points_label)

                points_text = QTextEdit()
                points_text.setReadOnly(True)
                points_text.setMaximumHeight(200)

                for i, point in enumerate(path.points[:10]):  # 只显示前10个点
                    pos = point.position
                    points_text.append(f"点 {i+1}: X={pos.x:.2f}, Y={pos.y:.2f}, Z={pos.z:.2f}, 速度={point.speed:.1f}%")

                if len(path.points) > 10:
                    points_text.append(f"... 还有 {len(path.points) - 10} 个点")

                layout.addWidget(points_text)

            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.setLayout(layout)
            dialog.exec()

        except Exception as e:
            error(f"显示路径详情失败: {e}", "ROBOT_UI")
            QMessageBox.warning(self, "错误", f"显示路径详情失败: {e}")

    def show_path_details_dialog(self, path):
        """显示路径详情对话框"""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle(f"路径详情: {path.name}")
            dialog.setMinimumSize(600, 500)
            layout = QVBoxLayout()

            # 路径基本信息
            info_group = QGroupBox("基本信息")
            info_layout = QFormLayout()
            info_layout.addRow("路径名称:", QLabel(path.name))
            info_layout.addRow("路径点数:", QLabel(f"{len(path.points)} 个"))
            info_layout.addRow("创建时间:", QLabel(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.created_time))))
            info_layout.addRow("描述:", QLabel(path.description or "无描述"))
            info_group.setLayout(info_layout)
            layout.addWidget(info_group)

            # 路径点详情表格
            points_group = QGroupBox("路径点详情")
            points_layout = QVBoxLayout()

            points_table = QTableWidget()
            points_table.setColumnCount(7)
            points_table.setHorizontalHeaderLabels(["序号", "X", "Y", "Z", "RX", "RY", "RZ"])
            points_table.setRowCount(len(path.points))

            for i, point in enumerate(path.points):
                points_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                points_table.setItem(i, 1, QTableWidgetItem(f"{point.position.x:.2f}"))
                points_table.setItem(i, 2, QTableWidgetItem(f"{point.position.y:.2f}"))
                points_table.setItem(i, 3, QTableWidgetItem(f"{point.position.z:.2f}"))
                points_table.setItem(i, 4, QTableWidgetItem(f"{point.position.rx:.2f}"))
                points_table.setItem(i, 5, QTableWidgetItem(f"{point.position.ry:.2f}"))
                points_table.setItem(i, 6, QTableWidgetItem(f"{point.position.rz:.2f}"))

                # 添加工具提示（安全处理）
                try:
                    pos_tooltip = f"时间: {time.strftime('%H:%M:%S', time.localtime(point.position.timestamp))}\n"
                    pos_tooltip += f"速度: {point.speed:.1f}%\n"
                    pos_tooltip += f"延迟: {point.delay:.1f}ms\n"
                    pos_tooltip += f"动作: {point.action or '无'}"
                    for col in range(7):
                        item = points_table.item(i, col)
                        if item:
                            item.setToolTip(pos_tooltip)
                except Exception as e:
                    # 如果工具提示创建失败，跳过但不影响主要功能
                    pass

            points_layout.addWidget(points_table)
            points_group.setLayout(points_layout)
            layout.addWidget(points_group)

            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.setLayout(layout)
            dialog.exec()

        except Exception as e:
            error(f"显示路径详情失败: {e}", "ROBOT_UI")
            QMessageBox.critical(self, "错误", f"显示路径详情失败: {e}")

    def set_path_as_current(self, path):
        """设置路径为当前路径"""
        try:
            # 检查路径是否已在path_list中，如果没有则添加
            path_exists = False
            for existing_data in self.path_list:
                if (existing_data['path'].name == path.name and
                    existing_data['path'].created_time == path.created_time):
                    path_exists = True
                    break

            if not path_exists:
                # 只有当路径不在列表中时才添加
                self.add_path_to_list(path)

            # 设置为当前路径
            self.recorded_path = path
            self.current_path_label.setText(f"📄 已加载: {path.name} ({len(path.points)}点)")
            self.play_btn.setEnabled(True)

            # 如果没有在记录，确保状态正确
            if self.is_recording_path:
                self.is_recording_path = False
                self.record_btn.setText("⏺ 开始记录")
                self.record_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF9800;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """)
                self.add_point_btn.setEnabled(False)

            # 刷新显示
            self.refresh_path_list()

            self.add_robot_log("信息", f"已设置当前路径: {path.name} ({len(path.points)}个路径点)")

        except Exception as e:
            error(f"设置当前路径失败: {e}", "ROBOT_UI")
            QMessageBox.warning(self, "错误", f"设置当前路径失败: {e}")

    def load_specific_path(self, path_id: str):
        """加载指定路径到列表中（不替换当前路径）"""
        loaded_path = self.robot_service.load_path(path_id)
        if loaded_path:
            # 只添加到路径列表，不替换当前路径
            self.add_path_to_list(loaded_path)

            # 刷新显示
            self.refresh_path_list()

            QMessageBox.information(self, "加载成功", f"路径 '{loaded_path.name}' 已添加到路径列表")
        else:
            QMessageBox.warning(self, "加载失败", f"无法加载路径: {path_id}")

    def load_saved_paths_dialog(self):
        """加载已保存路径对话框"""
        try:
            # 获取所有已保存的路径
            saved_paths = self.robot_service.list_saved_paths()
            if not saved_paths:
                QMessageBox.information(self, "无已保存路径", "workspace/paths/ 目录中没有找到已保存的路径文件")
                return

            # 创建路径选择对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("加载已保存路径")
            dialog.setMinimumSize(600, 400)
            layout = QVBoxLayout()

            # 说明标签
            info_label = QLabel("选择要加载的已保存路径（支持多选）：")
            layout.addWidget(info_label)

            # 路径表格
            path_table = QTableWidget()
            path_table.setColumnCount(5)
            path_table.setHorizontalHeaderLabels(["路径名称", "点数", "创建时间", "描述", "文件大小"])
            path_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            path_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)  # 多选模式
            path_table.setAlternatingRowColors(True)  # 交替行颜色，便于区分

            # 填充路径数据
            path_table.setRowCount(len(saved_paths))
            for row, path_id in enumerate(saved_paths):
                # 加载路径详情
                path = self.robot_service.load_path(path_id)
                if path:
                    # 路径名称
                    name_item = QTableWidgetItem(path.name or f"路径_{path_id}")
                    path_table.setItem(row, 0, name_item)

                    # 点数
                    points_item = QTableWidgetItem(str(len(path.points)))
                    path_table.setItem(row, 1, points_item)

                    # 创建时间
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.created_time))
                    time_item = QTableWidgetItem(time_str)
                    path_table.setItem(row, 2, time_item)

                    # 描述
                    desc_item = QTableWidgetItem(path.description or "")
                    path_table.setItem(row, 3, desc_item)

                    # 文件大小（估算）
                    size_item = QTableWidgetItem(f"~{len(path.points) * 0.1:.1f}KB")
                    path_table.setItem(row, 4, size_item)

                    # 在隐藏列存储路径ID（始终使用第6列作为隐藏列）
                    hidden_col = 5  # 第6列（索引5）存储路径ID
                    path_table.setColumnCount(6)  # 确保有6列
                    id_item = QTableWidgetItem(path_id)
                    id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    path_table.setItem(row, hidden_col, id_item)
                    path_table.setColumnHidden(hidden_col, True)  # 隐藏第6列

            layout.addWidget(path_table)

            # 按钮
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)

            dialog.setLayout(layout)

            # 显示对话框
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_rows = path_table.selectionModel().selectedRows()
                if selected_rows:
                    loaded_count = 0
                    failed_paths = []

                    for selected_row in selected_rows:
                        row = selected_row.row()
                        hidden_col = 5  # 固定使用第6列（索引5）
                        path_id_item = path_table.item(row, hidden_col)
                        if path_id_item:
                            path_id = path_id_item.text()
                            debug(f"Selected path ID: {path_id} from row {row}", "ROBOT_UI")

                            # 加载路径到列表（不替换当前路径）
                            loaded_path = self.robot_service.load_path(path_id)
                            if loaded_path:
                                self.add_path_to_list(loaded_path)
                                loaded_count += 1
                                self.add_robot_log("信息", f"已加载路径: {loaded_path.name} ({len(loaded_path.points)}个路径点)")
                            else:
                                failed_paths.append(path_id)
                                error(f"无法加载路径 ID: {path_id}", "ROBOT_UI")
                        else:
                            error(f"无法获取路径ID，第{row}行第{hidden_col}列为空", "ROBOT_UI")

                    # 刷新显示
                    self.refresh_path_list()

                    # 显示结果
                    if loaded_count > 0:
                        QMessageBox.information(self, "加载完成", f"成功加载 {loaded_count} 个路径到路径列表")
                    if failed_paths:
                        QMessageBox.warning(self, "部分失败", f"以下路径加载失败: {', '.join(failed_paths)}")
                else:
                    QMessageBox.warning(self, "未选择", "请选择要加载的路径")

        except Exception as e:
            error(f"显示已保存路径对话框失败: {e}", "ROBOT_UI")
            QMessageBox.critical(self, "错误", f"加载已保存路径失败: {e}")

    def add_path_to_list(self, path):
        """添加路径到列表"""
        # 检查是否已存在
        for existing_data in self.path_list:
            if (existing_data['path'].name == path.name and
                existing_data['path'].created_time == path.created_time):
                return  # 已存在，不重复添加

        # 添加到列表
        self.path_list.append({
            'path': path,
            'added_time': time.time()
        })

    def remove_path_from_list(self, row_index):
        """从列表中移除路径"""
        try:
            # 简化逻辑：直接基于path_list处理
            if row_index <= 0:
                # 不能移除首行（当前路径或空路径占位符）
                QMessageBox.warning(self, "无法移除", "不能移除首行的当前路径")
                return

            # 计算在path_list中的实际索引（row_index-1，因为首行是当前路径）
            actual_index = row_index - 1

            if actual_index < 0 or actual_index >= len(self.path_list):
                error(f"移除路径失败: 行索引无效 {row_index}", "ROBOT_UI")
                return

            # 获取要移除的路径
            path_to_remove = self.path_list[actual_index]
            path_name = path_to_remove['path'].name

            # 从path_list中移除
            del self.path_list[actual_index]

            # 刷新显示
            self.refresh_path_list()

            self.add_robot_log("信息", f"已移除路径: {path_name}")

        except Exception as e:
            error(f"移除路径失败: {e}", "ROBOT_UI")
            QMessageBox.warning(self, "错误", f"移除路径失败: {e}")

    def load_path(self):
        """加载路径 - 简化版"""
        path_list = self.robot_service.list_saved_paths()
        if not path_list:
            QMessageBox.information(self, "无路径", "没有保存的路径")
            return

        # 加载第一个路径
        path_id = path_list[0]
        self.load_specific_path(path_id)

    def delete_selected_path(self):
        """删除选中的路径"""
        selected_rows = self.path_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "未选择路径", "请先选择要删除的路径")
            return

        row = selected_rows[0].row()
        path_name_item = self.path_table.item(row, 0)
        path_id = f"path_{row}"  # 简化ID生成

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除路径 '{path_name.text()}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            result = self.robot_service.delete_path(path_id)
            if result['success']:
                self.refresh_path_list()
                QMessageBox.information(self, "删除成功", "路径已删除")
            else:
                warning(f"删除路径失败: {result.get('error')}", "ROBOT_UI")

    def play_path(self):
        """播放路径"""
        if not self.recorded_path:
            QMessageBox.warning(self, "无路径", "请先加载路径")
            return

        if not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            return

        loop_count = self.loop_spinbox.value()
        result = self.robot_service.play_path(self.recorded_path, loop_count)
        if result['success']:
            self.is_playing_path = True
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.current_path_label.setText(f"🔄 正在播放: {self.recorded_path.name}")
            QMessageBox.information(self, "播放开始", f"开始播放路径 '{self.recorded_path.name}'")
        else:
            warning(f"路径播放失败: {result.get('error')}", "ROBOT_UI")

    def stop_path_playback(self):
        """停止路径播放"""
        result = self.robot_service.stop_path_playback()
        if result['success']:
            self.is_playing_path = False
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            if self.recorded_path:
                self.current_path_label.setText(f"📄 已加载: {self.recorded_path.name} ({len(self.recorded_path.points)}点)")
            else:
                self.current_path_label.setText("📄 无路径加载")
            QMessageBox.information(self, "播放停止", "路径播放已停止")
        else:
            warning(f"停止播放失败: {result.get('error')}", "ROBOT_UI")

    def update_status(self):
        """更新状态显示"""
        try:
            # 更新连接状态 - 保持当前选择状态显示
            if self.robot_service.is_connected():
                if hasattr(self, 'current_robot_config') and self.current_robot_config:
                    robot_name = self.current_robot_config.get('name', '未知机械臂')
                    current_text = self.robot_status_label.text()
                    if "🟢" not in current_text:
                        self.robot_status_label.setText(f"🟢 已连接: {robot_name}")
                else:
                    self.robot_status_label.setText("🟢 已连接")

                # 更新实时信息面板
                if hasattr(self, 'current_robot_config') and self.current_robot_config:
                    robot_name = self.current_robot_config.get('name', '未知机械臂')
                    self.driver_label.setText(robot_name)
            else:
                current_text = self.robot_status_label.text()
                if "🔴" not in current_text:
                    if hasattr(self, 'current_robot_config') and self.current_robot_config:
                        robot_name = self.current_robot_config.get('name', '未知机械臂')
                        self.robot_status_label.setText(f"🔴 未连接: {robot_name}")
                    else:
                        self.robot_status_label.setText("🔴 未连接")

                # 更新实时信息面板
                self.driver_label.setText("未选择")

            # 获取当前位置 - 从service层获取
            try:
                position = self.robot_service.get_position()
                if position and len(position) >= 6:
                    self.position_status.setText(f"位置: ({position[0]:.1f}, {position[1]:.1f}, {position[2]:.1f}, {position[3]:.1f}, {position[4]:.1f}, {position[5]:.1f})")
                elif position and len(position) >= 3:
                    self.position_status.setText(f"位置: ({position[0]:.1f}, {position[1]:.1f}, {position[2]:.1f}, -, -, -)")
                else:
                    self.position_status.setText("位置: 未知")
            except Exception as pos_error:
                warning(f"获取位置失败: {pos_error}", "ROBOT_UI")
                self.position_status.setText("位置: 获取失败")

            # 获取当前状态 - 从service层获取
            try:
                state = self.robot_service.get_state()
                self.state_status.setText(f"状态: {state.value if state else '未知'}")
            except Exception as state_error:
                warning(f"获取状态失败: {state_error}", "ROBOT_UI")
                self.state_status.setText("状态: 获取失败")

            # 获取运动模式 - 从service层获取
            try:
                mode = self.robot_service.get_motion_mode()
                self.motion_mode_label.setText(mode.value if mode else "未知")
            except Exception as mode_error:
                warning(f"获取运动模式失败: {mode_error}", "ROBOT_UI")
                self.motion_mode_label.setText("运动模式: 获取失败")

            # 检查是否正在移动 - 从service层获取
            try:
                is_moving = self.robot_service.is_moving()
                self.is_moving_label.setText("是" if is_moving else "否")
            except Exception as moving_error:
                warning(f"获取移动状态失败: {moving_error}", "ROBOT_UI")
                self.is_moving_label.setText("移动状态: 获取失败")

        except Exception as e:
            error(f"更新状态失败: {e}", "ROBOT_UI")
            self.add_robot_log("错误", f"状态更新失败: {e}")

    def update_performance(self):
        """更新性能信息"""
        try:
            # 更新FPS
            self.fps_label.setText(f"{self.update_timer.interval()}ms → {1000/self.update_timer.interval():.1f}")

            # 更新命令数
            self.command_count += 1
            self.command_count_label.setText(str(self.command_count))

        except Exception as e:
            error(f"更新性能信息失败: {e}")

    def update_connection_time(self):
        """更新连接时间和状态"""
        if self.robot_service.is_connected():
            self.connection_time += 1
            hours = self.connection_time // 3600
            minutes = (self.connection_time % 3600) // 60
            seconds = self.connection_time % 60
            self.connection_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

            # 确保状态显示为已连接
            current_text = self.robot_status_label.text()
            if "🟢" not in current_text:
                if self.current_driver_index >= 0:
                    driver_name = self.robot_drivers[self.current_driver_index]['name']
                    self.robot_status_label.setText(f"🟢 已连接: {driver_name}")
                else:
                    self.robot_status_label.setText("🟢 已连接")
                self.robot_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                self.connect_btn.setText("断开")
        else:
            # 连接断开，停止计时器并更新状态
            self.connection_timer.stop()
            if "🔴" not in self.robot_status_label.text():
                self.robot_status_label.setText("🔴 未连接")
                self.robot_status_label.setStyleSheet("color: #f44336; font-weight: bold;")
                self.connect_btn.setText("连接")
            self.connection_time = 0

    def apply_to_vmc_node(self):
        """将当前选择的机械臂应用到VMC节点"""
        try:
            if not self.is_from_vmc_node or not self.vmc_callback:
                warning("Not initialized with VMC node callback", "ROBOT_UI")
                return
            
            # 获取当前选择的机械臂
            if self.current_driver_index >= 0 and self.current_driver_index < len(self.robot_drivers):
                selected_driver = self.robot_drivers[self.current_driver_index]
                robot_id = selected_driver.get('id', selected_driver.get('name', 'unknown'))
                
                # 调用回调函数更新VMC节点的selected_hardware_id
                debug(f"RobotControlTab: Applying robot {robot_id} to VMC node", "ROBOT_UI")
                self.vmc_callback(robot_id)
                
                QMessageBox.information(self, "应用成功", f"机械臂 '{selected_driver.get('name', robot_id)}' 已应用到节点")
            else:
                QMessageBox.warning(self, "未选择机械臂", "请先选择一个机械臂")
            
        except Exception as e:
            error(f"Failed to apply robot to VMC node: {e}", "ROBOT_UI")
            QMessageBox.critical(self, "应用失败", f"应用机械臂到节点时出错: {e}")
    
    def get_selected_robot(self):
        """获取当前选择的机械臂信息"""
        try:
            if self.current_driver_index >= 0 and self.current_driver_index < len(self.robot_drivers):
                return self.robot_drivers[self.current_driver_index]
            return None
            
        except Exception as e:
            error(f"Failed to get selected robot: {e}", "ROBOT_UI")
            return None

    # ==================== 相机预览功能 ====================

    def refresh_preview_camera_list(self):
        """刷新相机列表"""
        self.camera_combo.clear()
        
        # 尝试从硬件配置文件加载相机
        try:
            from core.managers.app_config import AppConfigManager
            config_manager = AppConfigManager()
            hardware_config = config_manager.get_hardware_config()
            cameras = hardware_config.get('cameras', [])
            # Handle if cameras is a dict or list
            if isinstance(cameras, dict):
                cameras = list(cameras.values())
            
            if cameras:
                for idx, cam_config in enumerate(cameras):
                    name = cam_config.get('name', f'Camera {idx}')
                    # 将配置存入 userdata
                    self.camera_combo.addItem(f"📷 {name}", cam_config)
            else:
                self.camera_combo.addItem("没有检测到相机", None)
        except Exception as e:
            error(f"刷新相机列表失败: {e}", "ROBOT_UI")
            self.camera_combo.addItem("加载相机列表失败", None)

    def on_camera_selected(self, index):
        """相机选择变更"""
        if index < 0:
            return
        
        # 停止当前预览
        if hasattr(self, 'stop_preview_btn') and self.stop_preview_btn.isEnabled():
            self.stop_robot_tab_preview()

    def start_robot_tab_preview(self):
        """开始预览"""
        idx = self.camera_combo.currentIndex()
        if idx < 0:
            return
            
        cam_data = self.camera_combo.currentData()
        if not cam_data:
            QMessageBox.warning(self, "无效相机", "请选择有效的相机")
            return
            
        try:
            if not self.camera_service:
                QMessageBox.warning(self, "错误", "相机服务未初始化")
                return

            self.start_preview_btn.setEnabled(False)
            self.stop_preview_btn.setEnabled(True)
            self.camera_combo.setEnabled(False)
            
            cam_name = cam_data.get('name', 'Unknown')
            # 构造唯一ID
            cam_id = cam_data.get('id', f"camera_{cam_name}")
            
            self.preview_camera_info = CameraInfo(cam_id, cam_data)
            self.preview_camera_info.connected = True
            
            self.preview_label.setText("正在连接相机...")

            # 确保相机已连接
            if self.camera_service:
                connect_result = self.camera_service.connect(cam_data)
                if not connect_result['success']:
                     QMessageBox.warning(self, "连接失败", f"无法连接相机: {connect_result.get('error')}")
                     self.stop_robot_tab_preview()
                     return
            
            # 使用CameraService启动流
            result = self.camera_service.start_streaming(self._robot_tab_frame_callback)
            if not result['success']:
                QMessageBox.warning(self, "预览失败", f"启动预览失败: {result.get('error')}")
                self.stop_robot_tab_preview()
                return
                
            self.preview_label.setText("") 
            self.preview_label.set_camera_info(self.preview_camera_info)
            
            # 启动定时器 UI刷新
            if not hasattr(self, 'preview_timer'):
                self.preview_timer = QTimer()
                self.preview_timer.timeout.connect(self._update_preview_ui)
            self.preview_timer.start(50) # 20fps

        except Exception as e:
            error(f"启动预览异常: {e}", "ROBOT_UI")
            self.stop_robot_tab_preview()

    def stop_robot_tab_preview(self):
        """停止预览"""
        try:
            if self.camera_service:
                self.camera_service.stop_streaming()
                
            if hasattr(self, 'preview_timer'):
                self.preview_timer.stop()
                
            self.start_preview_btn.setEnabled(True)
            self.stop_preview_btn.setEnabled(False)
            self.camera_combo.setEnabled(True)
            self.preview_label.setText("预览已停止")
            self.preview_label.clear()
            self.preview_label.setText("预览已停止")
            
        except Exception as e:
            error(f"停止预览异常: {e}", "ROBOT_UI")

    def _robot_tab_frame_callback(self, frame):
        """相机帧回调 (后台线程)"""
        if hasattr(self, 'preview_camera_info'):
            self.preview_camera_info.current_frame = frame
            # 这里的日志太多会刷屏，但在调试阶段很有用，可以证明回调被触发
            # info(f"RobotTab frame received: {frame.shape if frame is not None else 'None'}", "ROBOT_UI")

    def _update_preview_ui(self):
        """定时更新预览画面 (主线程)"""
        if not hasattr(self, 'preview_label') or not self.preview_label:
            return
        if hasattr(self, 'preview_camera_info') and self.preview_camera_info.current_frame is not None:
             self.preview_label.update_frame(self.preview_camera_info)

