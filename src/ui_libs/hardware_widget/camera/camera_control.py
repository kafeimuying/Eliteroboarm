from typing import Dict, Any, Optional, List
import time
import json
import os
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QCheckBox, QSlider, QTextEdit, QMessageBox, QSplitter,
    QFileDialog, QProgressBar, QFrame, QFormLayout, QComboBox,
    QLineEdit, QDialogButtonBox, QDialog, QListWidget, QListWidgetItem, QApplication,
    QSizePolicy, QMenu, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QObject
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QBrush
from core.managers.log_manager import info, debug, warning, error
from core import CameraService, RobotService
from core.interfaces.hardware import RobotPath
from .camera_info import CameraInfo
from .camera_preview import PreviewLabel
from .save_path_dialog import SavePathDialog
import sys
import os
try:
    sys.path.append(os.getcwd())
    from manual_correction_tool import calculate_correction, load_json_matrix
    from src.algorithms.vision.apriltag_detector import AprilTagDetector
    VISION_ALGO_AVAILABLE = True
except ImportError as e:
    warning(f"视觉算法模块导入失败: {e}", "CAMERA_UI")
    VISION_ALGO_AVAILABLE = False

# 导入相机驱动
CAMERA_DRIVERS_AVAILABLE = False

def check_camera_drivers():
    """检查相机驱动是否可用（基于配置）"""
    try:
        # 尝试从配置管理器获取设置
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

        from core.managers.app_config import AppConfigManager
        config_manager = AppConfigManager()

        # 如果配置禁用了驱动检查，直接返回False
        if not config_manager.is_camera_driver_check_enabled():
            return False

        # 否则尝试导入驱动
        from core.drivers.camera import SimulationCamera
        return True
    except ImportError:
        # 仅在启用检查时才显示警告
        try:
            config_manager = AppConfigManager()
            if config_manager.is_camera_driver_check_enabled():
                warning("相机驱动模块导入失败，将使用模拟预览", "CAMERA_UI")
        except:
            pass  # 静默忽略配置加载失败
        return False
    except Exception:
        return False

CAMERA_DRIVERS_AVAILABLE = check_camera_drivers()

class CameraControlTab(QWidget):
    """相机控制标签页 - 最终版"""

    # 定义信号
    camera_connected = pyqtSignal(str, dict)  # camera_id, config
    camera_disconnected = pyqtSignal(str)      # camera_id
    camera_status_changed = pyqtSignal(str, bool, dict)  # camera_id, connected, status_info
    
    # 路径管理相关信号
    show_context_menu_signal = pyqtSignal(int, int)  # row, column

    def __init__(self, camera_service: CameraService, parent=None, vmc_node=None, vmc_callback=None, robot_service: RobotService = None):
        super().__init__(parent)
        self.camera_service = camera_service  # 用于默认连接
        self.robot_service = robot_service    # 机械臂服务
        self.camera_list = []
        self.current_camera = None

        # 为每个相机创建独立的CameraService实例
        self.camera_services = {}  # camera_id -> CameraService
        self.preview_services = {}  # camera_id -> CameraService (用于预览)
        self.streaming_services = {}  # camera_id -> CameraService (用于流式传输)

        self.main_window = parent  # 获取主窗口引用以访问配置
        
        # 路径管理相关初始化
        self.is_recording_path = False
        self.recorded_path = None
        self.is_playing_path = False
        self.path_list = []  # 存储所有路径的列表
        self._empty_current_path = None  # 缓存空路径对象
        
        # VMC节点同步功能
        self.vmc_node = vmc_node  # 引用VMC相机节点
        self.vmc_callback = vmc_callback  # 回调函数用于同步selected_hardware_id
        self.is_from_vmc_node = vmc_node is not None  # 标识是否来自VMC节点
        
        # 连接信号
        self.show_context_menu_signal.connect(self._handle_context_menu_safely)
        
        self.setup_ui()
        # 相机管理页面从默认加载配置
        self.load_camera_configs()
        
        # 如果有机械臂服务，加载路径列表
        if self.robot_service:
            self.refresh_path_list()

        # 启动状态更新定时器
        self.status_update_timer = QTimer()
        self.status_update_timer.timeout.connect(self.update_camera_status_realtime)
        self.status_update_timer.start(1000)  # 每秒更新一次状态
        
        # 添加自动保存定时器（防抖机制）
        self._auto_save_timer = QTimer()
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._trigger_auto_save)
    
    def _trigger_parameter_change_auto_save(self):
        """触发参数变更自动保存（防抖机制）"""
        if hasattr(self, '_auto_save_timer'):
            self._auto_save_timer.stop()
            self._auto_save_timer.start(500)  # 500ms后保存
    
    def _trigger_auto_save(self):
        """执行自动保存到VMC缓存"""
        try:
            if self.is_from_vmc_node and self.vmc_node:
                if hasattr(self.vmc_node, 'canvas') and hasattr(self.vmc_node.canvas, 'parent_dialog') and hasattr(self.vmc_node.canvas.parent_dialog, '_save_vmc_config_to_cache'):
                    # 生成VMC配置
                    vmc_config = self.vmc_node.canvas.parent_dialog._generate_vmc_config()
                    self.vmc_node.canvas.parent_dialog._save_vmc_config_to_cache(vmc_config)
                    debug("CameraControlTab: Auto-saved configuration to VMC cache after parameter change", "CAMERA_UI")
        except Exception as e:
            debug(f"CameraControlTab: Failed to auto-save configuration: {e}", "CAMERA_UI")

    def load_camera_configs(self):
        """从 hardware_config.json 加载相机配置"""
        try:
            config_file = 'config/hardware_config.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                # 清空当前相机列表
                self.camera_list.clear()

                # 加载相机配置
                cameras = config_data.get('cameras', [])
                for camera_config in cameras:
                    # 创建 CameraInfo 对象
                    camera_info = CameraInfo(
                        camera_id=camera_config.get('id', 'unknown'),
                        config=camera_config
                    )
                    camera_info.name = camera_config.get('name', '未知相机')
                    camera_info.camera_type = camera_config.get('brand', 'unknown')
                    camera_info.connected = False  # 初始状态为未连接
                    camera_info.frame_count = 0

                    self.camera_list.append(camera_info)

                # 更新下拉列表显示
                if hasattr(self, 'update_camera_combo'):
                    self.update_camera_combo()
                elif hasattr(self, 'update_camera_table'):
                    self.update_camera_table()

                info(f"Loaded {len(cameras)} camera configurations", "CAMERA_UI")
            else:
                warning("hardware_config.json not found", "CAMERA_UI")

        except Exception as e:
            error(f"Failed to load camera configs: {e}", "CAMERA_UI")

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()

        # 主内容区域
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：相机管理和路径管理（垂直布局）
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_top = self.create_camera_management_panel()
        # 将原有的实时状态面板替换为路径管理
        left_bottom = self.create_enhanced_path_management()

        left_splitter.addWidget(left_top)
        left_splitter.addWidget(left_bottom)
        left_splitter.setSizes([150, 400])  # 管理区域较小，路径管理区域较大

        main_splitter.addWidget(left_splitter)

        # 右侧：预览
        right_panel = self.create_preview_panel()
        main_splitter.addWidget(right_panel)

        main_splitter.setSizes([450, 450])
        layout.addWidget(main_splitter)

        self.setLayout(layout)

    def create_camera_management_panel(self):
        """创建相机管理面板 - 下拉列表版"""
        group = QGroupBox("相机连接")
        group.setMaximumHeight(150)
        layout = QVBoxLayout()

        # 第一行：相机选择
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("相机:"))
        
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(200)
        self.camera_combo.currentIndexChanged.connect(self.on_camera_combo_changed)
        selection_layout.addWidget(self.camera_combo)
        
        # 刷新列表按钮
        refresh_list_btn = QPushButton("🔄")
        refresh_list_btn.setMaximumWidth(40)
        refresh_list_btn.setToolTip("重新加载配置文件")
        refresh_list_btn.clicked.connect(self.load_camera_configs)
        selection_layout.addWidget(refresh_list_btn)
        
        layout.addLayout(selection_layout)

        # 第二行：连接控制
        control_layout = QHBoxLayout()

        # 连接状态显示
        self.camera_status_label = QLabel("🔴 未连接")
        self.camera_status_label.setStyleSheet("color: #f44336; font-weight: bold; font-size: 14px;")
        control_layout.addWidget(self.camera_status_label)

        # 连接按钮
        self.connect_btn = QPushButton("连接")
        self.connect_btn.setMinimumWidth(80)
        self.connect_btn.clicked.connect(self.toggle_camera_connection)
        control_layout.addWidget(self.connect_btn)
        
        layout.addLayout(control_layout)
        
        # VMC节点同步 (保留)
        if self.is_from_vmc_node:
            apply_to_node_btn = QPushButton("🔗 应用到节点")
            apply_to_node_btn.clicked.connect(self.apply_to_vmc_node)
            apply_to_node_btn.setStyleSheet("background-color: #FF9800; color: white;")
            layout.addWidget(apply_to_node_btn)

        group.setLayout(layout)
        return group

    def update_camera_combo(self):
        """更新相机下拉列表"""
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        
        for cam_info in self.camera_list:
            display_text = f"{cam_info.name} ({cam_info.camera_type})"
            self.camera_combo.addItem(display_text, cam_info)
            
        self.camera_combo.blockSignals(False)
        
        # 触发一次变更以更新状态显示
        if self.camera_combo.count() > 0:
            self.on_camera_combo_changed(0)
            
    def on_camera_combo_changed(self, index):
        """相机选择变更"""
        if index < 0 or index >= len(self.camera_list):
            return
            
        cam_info = self.camera_combo.itemData(index)
        self.current_camera = cam_info
        
        # 更新按钮状态
        if cam_info.connected:
            self.camera_status_label.setText(f"🟢 已连接: {cam_info.name}")
            self.connect_btn.setText("断开")
            self.connect_btn.setStyleSheet("background-color: #f44336; color: white;")
        else:
            self.camera_status_label.setText("🔴 未连接")
            self.connect_btn.setText("连接")
            self.connect_btn.setStyleSheet("")

    def toggle_camera_connection(self):
        """切换相机连接状态"""
        if not self.current_camera:
            return
            
        if self.current_camera.connected:
            # 断开连接
            self.disconnect_current_camera()
        else:
            # 连接
            # 这里复用原有的 connect_selected_camera 逻辑，但 adapting first
            self.connect_current_selected_camera()

    def connect_current_selected_camera(self):
        """连接当前下拉框选中的相机"""
        if not self.current_camera:
            return
            
        camera_id = self.current_camera.camera_id
        config = self.current_camera.config
        
        info(f"Connecting to camera: {self.current_camera.name}", "CAMERA_UI")
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("连接中...")
        QApplication.processEvents()
        
        try:
            # 确保服务实例存在
            if camera_id not in self.camera_services:
                 # 创建新服务实例
                 self.camera_services[camera_id] = CameraService()
            
            service = self.camera_services[camera_id]
            result = service.connect(config)
            
            if result['success']:
                self.current_camera.connected = True
                self.current_camera.frame_count = 0
                self.camera_connected.emit(camera_id, config)
                
                info(f"Camera connected: {self.current_camera.name}", "CAMERA_UI")
                self.start_preview() # Auto start preview
            else:
                self.current_camera.connected = False
                error(f"Failed to connect camera: {result.get('error')}", "CAMERA_UI")
                QMessageBox.warning(self, "连接失败", f"无法连接相机: {result.get('error')}")

        except Exception as e:
            error(f"Connection exception: {e}", "CAMERA_UI")
            QMessageBox.critical(self, "连接异常", f"连接过程发生错误: {str(e)}")
        finally:
            self.connect_btn.setEnabled(True)
            # Update UI
            self.on_camera_combo_changed(self.camera_combo.currentIndex())
            
    def disconnect_current_camera(self):
        """断开当前相机"""
        if not self.current_camera:
            return
            
        camera_id = self.current_camera.camera_id
        if camera_id in self.camera_services:
            service = self.camera_services[camera_id]
            service.disconnect()
            
        self.current_camera.connected = False
        self.camera_disconnected.emit(camera_id)
        
        # Update UI
        self.on_camera_combo_changed(self.camera_combo.currentIndex())
        self.stop_preview()

    def create_enhanced_path_management(self):
        """创建增强版路径管理面板 (从 RobotControlTab 复制)"""
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

        # 视觉伺服控制 (AprilTag)
        if VISION_ALGO_AVAILABLE:
            servo_group = QGroupBox("视觉伺服 (AprilTag 0.1m)")
            servo_layout = QGridLayout()

            self.btn_record_std = QPushButton("🚩 记录标准点")
            self.btn_record_std.clicked.connect(self.on_record_standard_point)
            self.btn_record_std.setStyleSheet("background-color: #9C27B0; color: white;")
            
            self.btn_follow = QPushButton("🎯 跟随纠偏")
            self.btn_follow.clicked.connect(self.on_follow_and_correct)
            self.btn_follow.setStyleSheet("background-color: #2196F3; color: white;")

            servo_layout.addWidget(self.btn_record_std, 0, 0)
            servo_layout.addWidget(self.btn_follow, 0, 1)
            servo_group.setLayout(servo_layout)
            layout.addWidget(servo_group)
        
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

    def start_new_path_recording(self):
        """开始新的路径记录"""
        if not self.robot_service or not self.robot_service.is_connected():
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

    def toggle_path_recording(self):
        """切换路径记录状态"""
        if not self.robot_service or not self.robot_service.is_connected():
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

            # 更新当前路径标签
            current_path = self.robot_service.get_recorded_path()
            point_count = len(current_path.points) if current_path else 0
            self.current_path_label.setText(f"📄 当前路径: {current_path.name if current_path else '未命名'} ({point_count}点)")
            
            self.add_robot_log("路径", f"路径点已添加（当前共{point_count}个点）")
        else:
            warning(f"添加路径点失败: {result.get('error')}", "PATH_UI")

    def clear_recorded_path(self):
        """清空记录的路径"""
        if self.recorded_path and len(self.recorded_path.points) > 0:
            reply = QMessageBox.question(
                self, "确认清空",
                f"确定要清空当前记录的路径吗？\\n包含{len(self.recorded_path.points)}个路径点。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                result = self.robot_service.clear_recorded_path()
                if result['success']:
                    self.recorded_path = self.robot_service.get_recorded_path()
                    self.refresh_path_list()
                    self.current_path_label.setText("📄 无路径加载")
                    self.add_robot_log("路径", "路径已清空")
                else:
                    warning(f"清空路径失败: {result.get('error')}", "PATH_UI")

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
                    self.refresh_path_list()
                    QMessageBox.information(self, "保存成功", f"路径 '{self.recorded_path.name}' 已保存到 workspace/paths/")
                    self.add_robot_log("信息", f"路径已保存: {self.recorded_path.name}")
                else:
                    warning(f"保存路径失败: {result.get('error')}", "ROBOT_UI")
        except Exception as e:
            error(f"保存路径失败: {e}", "ROBOT_UI")
            QMessageBox.critical(self, "错误", f"保存路径失败: {e}")

    def save_current_path(self):
        """保存当前路径"""
        if not self.recorded_path or len(self.recorded_path.points) == 0:
            QMessageBox.warning(self, "保存失败", "没有可保存的路径数据")
            return
        self.save_recorded_path()

    def refresh_path_list(self):
        """刷新路径列表显示"""
        try:
            display_paths = []
            # 1. 当前路径
            if self.recorded_path:
                status = "🔴 记录中" if self.is_recording_path else "⏸ 已停止"
                display_paths.append({
                    'path': self.recorded_path,
                    'status': status,
                    'is_recording': self.is_recording_path,
                    'is_current': True
                })
            else:
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

            # 2. 其他路径
            for path_data in self.path_list:
                try:
                    if hasattr(path_data, 'get') and 'path' in path_data:
                        path = path_data['path']
                        if path != self.recorded_path:
                            display_paths.append({
                                'path': path,
                                'status': "✅ 已加载",
                                'is_recording': False,
                                'is_current': False,
                                'is_empty': False
                            })
                except Exception:
                    continue

            self.path_table.setRowCount(len(display_paths))
            self.path_table.clearSpans()

            for row, path_data in enumerate(display_paths):
                path = path_data['path']
                
                # Name
                name_text = path.name or "未命名路径"
                if path_data['is_current']: name_text = "🎯 " + name_text
                name_item = QTableWidgetItem(name_text)
                name_item.setData(Qt.ItemDataRole.UserRole, path)
                self.path_table.setItem(row, 0, name_item)
                
                # Points
                points_item = QTableWidgetItem(str(len(path.points)))
                self.path_table.setItem(row, 1, points_item)
                
                # Time
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.created_time))
                self.path_table.setItem(row, 2, QTableWidgetItem(time_str))
                
                # Description
                self.path_table.setItem(row, 3, QTableWidgetItem(path.description or ""))
                
                # Status
                status_item = QTableWidgetItem(path_data['status'])
                if path_data['is_recording']:
                    status_item.setForeground(QBrush(QColor("red")))
                self.path_table.setItem(row, 4, status_item)
                
                # Op Button
                if path_data.get('is_empty', False):
                    action_btn = QPushButton("➕ 新建路径")
                    action_btn.clicked.connect(self.start_new_path_recording)
                elif path_data['is_current'] and path_data['is_recording']:
                    action_btn = QPushButton("⏹ 停止记录")
                    action_btn.clicked.connect(self.toggle_path_recording)
                elif path_data['is_current'] and not path_data['is_recording'] and len(path.points) > 0:
                    action_btn = QPushButton("💾 保存路径")
                    action_btn.clicked.connect(self.save_current_path)
                elif not path_data['is_current']:
                    action_btn = QPushButton("❌ 移除")
                    action_btn.clicked.connect(lambda checked, idx=row: self.remove_path_from_list(idx))
                else:
                    action_btn = QPushButton("📝 无数据")
                    action_btn.setEnabled(False)
                
                self.path_table.setCellWidget(row, 5, action_btn)

        except Exception as e:
            error(f"刷新路径列表显示失败: {e}", "ROBOT_UI")

    def load_saved_paths_dialog(self):
        """加载已保存路径对话框"""
        if not self.robot_service: return
        
        try:
            saved_paths = self.robot_service.list_saved_paths()
            if not saved_paths:
                QMessageBox.information(self, "无已保存路径", "workspace/paths/ 中没有找到已保存的路径")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("加载已保存路径")
            dialog.setMinimumSize(600, 400)
            layout = QVBoxLayout()
            layout.addWidget(QLabel("选择要加载的已保存路径（支持多选）："))

            path_table = QTableWidget()
            path_table.setColumnCount(5)
            path_table.setHorizontalHeaderLabels(["路径名称", "点数", "创建时间", "描述", "ID"])
            path_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            path_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
            path_table.hideColumn(4) # Hide ID

            path_table.setRowCount(len(saved_paths))
            for row, path_id in enumerate(saved_paths):
                path = self.robot_service.load_path(path_id)
                if path:
                    path_table.setItem(row, 0, QTableWidgetItem(path.name or f"路径_{path_id}"))
                    path_table.setItem(row, 1, QTableWidgetItem(str(len(path.points))))
                    path_table.setItem(row, 2, QTableWidgetItem(time.strftime("%Y-%m-%d %H:%M", time.localtime(path.created_time))))
                    path_table.setItem(row, 3, QTableWidgetItem(path.description or ""))
                    path_table.setItem(row, 4, QTableWidgetItem(path_id))

            layout.addWidget(path_table)
            
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)

            dialog.setLayout(layout)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_rows = path_table.selectionModel().selectedRows()
                for selected_row in selected_rows:
                    row = selected_row.row()
                    path_id = path_table.item(row, 4).text()
                    path = self.robot_service.load_path(path_id)
                    if path:
                        self.add_path_to_list(path)
                self.refresh_path_list()

        except Exception as e:
            error(f"加载路径失败: {e}", "ROBOT_UI")

    def add_path_to_list(self, path):
        """添加路径到列表"""
        for existing_data in self.path_list:
            if existing_data['path'].created_time == path.created_time:
                return # Skip duplicate
        self.path_list.append({'path': path, 'added_time': time.time()})

    def remove_path_from_list(self, row_index):
        """移除路径"""
        try:
            if row_index <= 0: return # Skip current path
            actual_index = row_index - 1
            if 0 <= actual_index < len(self.path_list):
                del self.path_list[actual_index]
                self.refresh_path_list()
        except Exception:
            pass

    def on_path_selection_changed(self):
        """处理路径表格选择变化事件"""
        selected_items = self.path_table.selectedItems()
        if not selected_items:
            self.current_path_label.setText("📄 无路径加载")
            self.play_btn.setEnabled(False)
            return
            
        # Simplified selection logic
        row = selected_items[0].row()
        item = self.path_table.item(row, 0)
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.play_btn.setEnabled(True)
                self.current_path_label.setText(f"📄 选中: {path.name} ({len(path.points)}点)")

    def on_path_double_clicked(self, row, column):
        """处理路径表格双击事件"""
        self.play_path()

    def play_path(self):
        """播放路径"""
        if not self.robot_service or not self.robot_service.is_connected():
            QMessageBox.warning(self, "未连接", "请先连接机械臂")
            return

        target_path = None
        selected_rows = self.path_table.selectionModel().selectedRows()
        if selected_rows:
            item = self.path_table.item(selected_rows[0].row(), 0)
            if item: target_path = item.data(Qt.ItemDataRole.UserRole)
        
        if not target_path: target_path = self.recorded_path
        if not target_path: return

        loop_count = self.loop_spinbox.value()
        self.add_robot_log("信息", f"开始播放: {target_path.name}")
        
        result = self.robot_service.play_path(target_path, loop_count)
        if result['success']:
            self.is_playing_path = True
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.current_path_label.setText(f"🔄 正在播放: {target_path.name}")
            QMessageBox.information(self, "播放开始", f"开始播放路径 '{target_path.name}'")
        else:
            warning(f"路径播放失败: {result.get('error')}", "ROBOT_UI")

    def stop_path_playback(self):
        """停止播放"""
        if not self.robot_service: return
        result = self.robot_service.stop_path_playback()
        if result['success']:
            self.is_playing_path = False
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.add_robot_log("信息", "路径播放已停止")
            QMessageBox.information(self, "播放停止", "路径播放已停止")

    def setup_path_table_context_menu(self):
        self.path_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.path_table.customContextMenuRequested.connect(self.show_path_context_menu)

    def show_path_context_menu(self, position):
        item = self.path_table.itemAt(position)
        if item and item.row() >= 0:
            self.show_context_menu_signal.emit(item.row(), 0)

    def _handle_context_menu_safely(self, row, column):
        """Handle context menu safely"""
        item = self.path_table.item(row, 0)
        if not item: return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path: return
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(f"路径: {path.name}")
        msg_box.setText(f"名称: {path.name}\n点数: {len(path.points)}")
        details_btn = msg_box.addButton("查看详情", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg_box.exec()
        
        if msg_box.clickedButton() == details_btn:
            self._show_path_details_safe(path)

    def _show_path_details_safe(self, path):
        if not path: return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"路径详情: {path.name}")
        layout = QVBoxLayout()
        text = f"ID: {path.id}\n名称: {path.name}\n点数: {len(path.points)}\n创建时间: {time.ctime(path.created_time)}"
        layout.addWidget(QLabel(text))
        dialog.setLayout(layout)
        dialog.exec()

    def add_robot_log(self, level, message):
        """添加日志"""
        info(f"[ROBOT] {message}", "CAMERA_UI_ROBOT")

    def create_preview_panel(self):
        """创建预览面板"""
        group = QGroupBox("实时预览")
        layout = QVBoxLayout()

        self.preview_label = PreviewLabel(self)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setText("📹 选择相机开始预览")

        # 连接鼠标hover信号到坐标显示
        self.preview_label.mouse_hover.connect(self.update_coordinate_display)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 2px solid #555;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                min-height: 400px;
            }
        """)
        layout.addWidget(self.preview_label)

        # 预览控制 - 恢复原来的布局
        control_layout = QHBoxLayout()

        self.start_preview_btn = QPushButton("▶ 开始预览")
        self.start_preview_btn.clicked.connect(self.start_preview)
        self.start_preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
                border: 1px solid #45a049;
            }
            QPushButton:pressed {
                background-color: #388E3C;
                border: 1px solid #388E3C;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #cccccc;
            }
        """)
        control_layout.addWidget(self.start_preview_btn)

        self.stop_preview_btn = QPushButton("⏹ 停止预览")
        self.stop_preview_btn.clicked.connect(self.stop_preview)
        self.stop_preview_btn.setEnabled(False)
        self.stop_preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
                border: 1px solid #D32F2F;
            }
            QPushButton:pressed {
                background-color: #c62828;
                border: 1px solid #D32F2F;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #cccccc;
            }
        """)
        control_layout.addWidget(self.stop_preview_btn)

        capture_btn = QPushButton("📸 拍照")
        capture_btn.clicked.connect(self.capture_image)
        capture_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
                border: 1px solid #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
                border: 1px solid #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #cccccc;
            }
        """)
        control_layout.addWidget(capture_btn)

        # 自动对焦
        self.auto_focus_btn = QPushButton("🎯 自动对焦")
        self.auto_focus_btn.clicked.connect(self.trigger_auto_focus)
        self.auto_focus_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 8px 16px;
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
        self.auto_focus_btn.setEnabled(False)
        control_layout.addWidget(self.auto_focus_btn)

        # 相机切换
        camera_switch_btn = QPushButton("🔄 切换相机")
        camera_switch_btn.clicked.connect(self.switch_camera)
        camera_switch_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
                border: 1px solid #7B1FA2;
            }
            QPushButton:pressed {
                background-color: #6A1B9A;
                border: 1px solid #7B1FA2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
                border: 1px solid #cccccc;
            }
        """)
        control_layout.addWidget(camera_switch_btn)

        layout.addLayout(control_layout)

        group.setLayout(layout)
        return group

    def create_camera_status_panel(self):
        """创建相机状态面板"""
        group = QGroupBox("实时状态")
        layout = QVBoxLayout()

        self.camera_status_label = QLabel("🔴 未选择相机")
        layout.addWidget(self.camera_status_label)

        self.resolution_label = QLabel("分辨率: -")
        layout.addWidget(self.resolution_label)

        self.fps_label = QLabel("帧率: -")
        layout.addWidget(self.fps_label)

        self.bitrate_label = QLabel("码率: -")
        layout.addWidget(self.bitrate_label)

        self.last_frame_time_label = QLabel("最后帧: -")
        layout.addWidget(self.last_frame_time_label)

        # 添加坐标显示
        self.coordinate_label = QLabel("坐标: -")
        layout.addWidget(self.coordinate_label)

        group.setLayout(layout)
        return group

    def add_sample_cameras(self):
        """添加示例相机 - 改进版"""
        # 清空现有列表
        self.camera_list = []
        if hasattr(self, 'camera_combo'):
            self.camera_combo.clear()

        sample_cameras = [
            ("主相机", "rtsp://192.168.0.2:554/Streaming/Channels/101", "1920x1080", "30fps"),
            ("辅助相机", "rtsp://192.168.0.12:554/Streaming/Channels/101", "1280x720", "25fps"),
            ("侧视相机", "rtsp://192.168.0.13:554/Streaming/Channels/101", "800x600", "20fps")
        ]

        for i, (name, rtsp_url, resolution, fps) in enumerate(sample_cameras):
            # 创建相机信息对象
            camera_info = CameraInfo(f"camera_{i}", {
                'name': name,
                'rtsp_url': rtsp_url,
                'resolution': resolution,
                'fps': fps,
                'username': 'admin',
                'password': 'admin123'
            })
            self.camera_list.append(camera_info)
            
            # 添加到下拉框
            if hasattr(self, 'camera_combo'):
                self.camera_combo.addItem(f"{name} ({resolution})", camera_info)

        # 默认选中第一项
        if self.camera_list and hasattr(self, 'camera_combo'):
            self.camera_combo.setCurrentIndex(0)
            self.current_camera = self.camera_list[0]
            if hasattr(self, 'update_camera_info_display'):
                self.update_camera_info_display()

    def add_camera(self):
        """添加相机"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加相机")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        form_layout = QFormLayout()

        name_edit = QLineEdit()
        form_layout.addRow("相机名称:", name_edit)

        rtsp_edit = QLineEdit("rtsp://192.168.1.100:554/stream")
        form_layout.addRow("RTSP URL:", rtsp_edit)

        username_edit = QLineEdit("admin")
        form_layout.addRow("用户名:", username_edit)

        password_edit = QLineEdit("admin123")
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("密码:", password_edit)

        resolution_edit = QLineEdit("1920x1080")
        form_layout.addRow("分辨率:", resolution_edit)

        layout.addLayout(form_layout)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButton.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted and name_edit.text():
            # 创建新相机
            fps_value = "30fps"  # 默认帧率
            camera_info = CameraInfo(name_edit.text(), {
                'name': name_edit.text(),
                'rtsp_url': rtsp_edit.text(),
                'username': username_edit.text(),
                'password': password_edit.text(),
                'resolution': resolution_edit.text(),
                'fps': fps_value
            })

            self.camera_list.append(camera_info)
            
            # 添加到下拉框
            if hasattr(self, 'camera_combo'):
                self.camera_combo.addItem(f"{camera_info.name} ({camera_info.resolution})", camera_info)
                # 选中新添加的相机
                image_idx = self.camera_combo.count() - 1
                self.camera_combo.setCurrentIndex(image_idx)

            info(f"添加相机: {camera_info.name}", "CAMERA_UI")

    def connect_camera(self, row: int):
        """连接指定相机 (兼容性保留，实际逻辑已迁移到 connect_current_selected_camera)"""
        if row >= len(self.camera_list):
            return

        # 切换到指定相机并尝试连接
        if hasattr(self, 'camera_combo'):
            self.camera_combo.setCurrentIndex(row)
            self.connect_current_selected_camera()

        
    def trigger_auto_focus(self):
        """触发自动对焦"""
        if not self.current_camera or not self.current_camera.connected:
            QMessageBox.warning(self, "未连接", "请先连接相机")
            return

        camera_id = self.current_camera.camera_id
        info(f"Triggering auto focus for camera: {camera_id}", "CAMERA_UI")
        
        try:
            # 禁用按钮防止重复点击
            if hasattr(self, 'auto_focus_btn'):
                self.auto_focus_btn.setEnabled(False)
                self.auto_focus_btn.setText("🎯 对焦中...")
            QApplication.processEvents()

            # 确定使用哪个 Service实例
            # 优先检查streaming_services中的实例 (通常是当前活跃的连接)
            service_to_use = None
            if camera_id in self.streaming_services:
                service_to_use = self.streaming_services[camera_id]
            # 其次检查camera_services
            elif camera_id in self.camera_services:
                service_to_use = self.camera_services[camera_id]
            # 最后使用默认service
            if not service_to_use:
                service_to_use = self.camera_service
            
            # 调用服务层对焦接口
            if service_to_use:
                result = service_to_use.auto_focus()
                success = result.get('success', False)
                message = result.get('message') or result.get('error', 'Unknown error')
                
                if success:
                    info(f"Auto focus successful: {message}", "CAMERA_UI")
                    self.preview_label.setText(f"✅ 自动对焦成功")
                    QTimer.singleShot(2000, lambda: self.preview_label.setText(""))
                else:
                    warning(f"Auto focus failed: {message}", "CAMERA_UI")
                    QMessageBox.warning(self, "对焦失败", f"自动对焦失败:\n{message}")
            else:
                warning("No camera service available for auto focus", "CAMERA_UI")
                QMessageBox.warning(self, "错误", "无法获取相机服务")

        except Exception as e:
            error(f"Auto focus exception: {e}", "CAMERA_UI")
            QMessageBox.warning(self, "错误", f"触发自动对焦时发生错误:\n{str(e)}")
        finally:
            # 恢复按钮状态
            if hasattr(self, 'auto_focus_btn'):
                self.auto_focus_btn.setEnabled(True)
                self.auto_focus_btn.setText("🎯 自动对焦")

    def start_preview(self):
        """开始预览"""
        if not self.current_camera or not self.current_camera.connected:
            QMessageBox.warning(self, "未选择相机", "请先选择并连接相机")
            return

        try:
            self.preview_label.setText("⌛ 启动预览中...")
            QApplication.processEvents()

            # 使用统一的预览方法，确保FPS一致性
            success = self.start_camera_preview(self.current_camera)

            if success:
                # 更新按钮状态
                self.start_preview_btn.setEnabled(False)
                self.stop_preview_btn.setEnabled(True)
                self.preview_label.setText("📹 预览中...")

                info(f"相机预览已启动: {self.current_camera.name} (FPS: {self.current_camera.config.get('fps', 30)})", "CAMERA_UI")
            else:
                self.preview_label.setText("❌ 预览失败")
                QMessageBox.warning(self, "预览失败", "无法启动相机预览，请检查日志")

        except Exception as e:
            error(f"启动预览失败: {e}", "CAMERA_UI")
            QMessageBox.warning(self, "预览失败", f"启动预览失败: {str(e)}")
            self.start_preview_btn.setEnabled(True)

    def stop_all_previews(self):
        """停止所有相机的预览"""
        try:
            info("停止所有相机预览", "CAMERA_UI")

            # 停止所有CameraService的流式传输，但保留服务实例
            for camera_id, camera_service in list(self.streaming_services.items()):
                try:
                    if camera_service and camera_service.is_streaming():
                        result = camera_service.stop_streaming()
                        if result['success']:
                            info(f"已停止相机 {camera_id} 的流式传输", "CAMERA_UI")
                        else:
                            warning(f"停止相机 {camera_id} 流式传输失败: {result.get('error')}", "CAMERA_UI")
                except Exception as e:
                    warning(f"停止相机 {camera_id} 流式传输异常: {e}", "CAMERA_UI")

            # 注意：不清空 self.streaming_services 字典，保留服务实例以便重用

        except Exception as e:
            error(f"停止所有预览失败: {e}", "CAMERA_UI")

    def stop_preview(self):
        """停止预览（只停止推流，保持连接）"""
        try:
            info(f"停止当前相机预览: {self.current_camera.name if self.current_camera else 'None'}", "CAMERA_UI")

            # 停止当前相机的流式传输
            if self.current_camera and self.current_camera.camera_id in self.streaming_services:
                camera_service = self.streaming_services[self.current_camera.camera_id]
                if camera_service.is_streaming():
                    result = camera_service.stop_streaming()
                    if result['success']:
                        info(f"相机 {self.current_camera.name} 流式传输已停止", "CAMERA_UI")
                    else:
                        warning(f"停止相机 {self.current_camera.name} 流式传输失败: {result.get('error')}", "CAMERA_UI")

            # 清空预览显示
            self.preview_label.clear_preview()

            # 重置UI状态（保持连接状态，只更新预览相关按钮）
            self.start_preview_btn.setEnabled(self.current_camera and self.current_camera.connected)
            self.stop_preview_btn.setEnabled(False)

            # 清除坐标显示
            self.clear_coordinate_display()

        except Exception as e:
            error(f"停止预览失败: {e}", "CAMERA_UI")

    def switch_camera(self):
        """切换相机"""
        if not self.camera_list:
            QMessageBox.information(self, "无相机", "没有可切换的相机")
            return

        try:
            # 获取当前选中的相机
            current_row = self.camera_table.currentRow()
            if current_row < 0:
                current_row = 0

            # 切换到下一个相机
            next_row = (current_row + 1) % len(self.camera_list)
            next_camera = self.camera_list[next_row]

            info(f"切换相机: 从 {self.current_camera.name if self.current_camera else '无'} 到 {next_camera.name}", "CAMERA_UI")

            # 选择下一个相机
            self.camera_table.selectRow(next_row)

            # 连接新相机（会自动断开当前相机）
            self.connect_camera(next_row)

        except Exception as e:
            error(f"切换相机失败: {e}", "CAMERA_UI")
            QMessageBox.warning(self, "切换失败", f"切换相机失败: {str(e)}")

    def on_frame_captured(self, camera_info: CameraInfo):
        """接收到相机帧"""
        try:
            # 检查预览标签是否还存在且未被销毁
            if (not hasattr(self, 'preview_label') or
                self.preview_label is None or
                not hasattr(self.preview_label, '_is_destroyed') or
                self.preview_label._is_destroyed):
                return

            if camera_info.current_frame is not None:
                # 添加调试信息，确保是正确的相机
                # debug(f"处理来自相机 {camera_info.name} (ID: {camera_info.camera_id}) 的帧，帧大小: {camera_info.current_frame.shape}", "CAMERA_UI")
                # 更新帧数计数
                if not hasattr(camera_info, 'frame_count'):
                    camera_info.frame_count = 0
                camera_info.frame_count += 1

                # 将numpy数组转换为QImage
                import numpy as np
                import cv2

                height, width, channel = camera_info.current_frame.shape
                bytes_per_line = 3 * width
                q_image = QImage(
                    camera_info.current_frame.data, width, height,
                    bytes_per_line, QImage.Format.Format_RGB888
                ).rgbSwapped()

                # 获取预览区域的固定大小（不使用动态size）
                if hasattr(self.preview_label, 'preview_size'):
                    preview_size = self.preview_label.preview_size
                else:
                    # 第一次设置时保存预览大小
                    preview_size = self.preview_label.size()
                    self.preview_label.preview_size = preview_size

                # 缩放以适应预览区域（使用固定大小）
                pixmap = QPixmap.fromImage(q_image).scaled(
                    preview_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

                # 显示图像并设置相机信息
                self.preview_label.setFixedSize(preview_size)  # 确保标签大小固定
                self.preview_label.setPixmap(pixmap)
                self.preview_label.set_camera_info(camera_info)

                # 更新预览标签文本，显示当前相机信息
                self.preview_label.setToolTip(f"正在显示: {camera_info.name}\n分辨率: {width}x{height}\n相机ID: {camera_info.camera_id}")

                # 更新状态信息
                if self.current_camera and camera_info.camera_id == self.current_camera.camera_id:
                    if hasattr(self, 'resolution_label'):
                        self.resolution_label.setText(f"分辨率: {width}x{height}")
                    if hasattr(self, 'last_frame_time_label'):
                        current_time = time.strftime("%H:%M:%S")
                        self.last_frame_time_label.setText(f"最后帧: {current_time}")
                    if hasattr(self, 'fps_label'):
                        self.fps_label.setText(f"{camera_info.config.get('fps', 30)}fps")

                # 更新表格中的帧数显示
                self.update_frame_count_in_table(camera_info)

        except Exception as e:
            error(f"处理相机帧失败: {e}", "CAMERA_UI")

    def _get_detector(self):
        """延迟加载或获取检测器"""
        if hasattr(self, 'at_detector') and self.at_detector:
            return self.at_detector
        
        # 尝试加载标定文件
        calib_file = os.path.join(os.getcwd(), "AprilTagInterface", "calibration", "realsense_calib.npz")
        mtx = None
        dist = None
        
        if os.path.exists(calib_file):
            try:
                data = np.load(calib_file)
                mtx = data['mtx']
                dist = data.get('dist', np.zeros(4))
                info(f"已加载相机标定: {calib_file}", "CAMERA_UI")
            except Exception as e:
                warning(f"加载标定文件失败: {e}，将使用默认内参", "CAMERA_UI")
        
        if mtx is None:
            # 默认内参 (640x480)
            mtx = np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]], dtype=np.float32)
            dist = np.zeros(4)
            
        try:
            self.at_detector = AprilTagDetector(tag_size_m=0.1, camera_matrix=mtx, dist_coeffs=dist)
            return self.at_detector
        except Exception as e:
            error(f"初始化AprilTagDetector失败: {e}", "CAMERA_UI")
            return None

    def on_record_standard_point(self):
        """记录标准拍照点"""
        if not self.current_camera or not self.current_camera.current_frame is not None:
            QMessageBox.warning(self, "错误", "请先连接相机并开启预览")
            return
            
        # 1. 检测Tag
        detector = self._get_detector()
        if not detector:
            QMessageBox.critical(self, "错误", "无法初始化视觉检测器")
            return
            
        results = detector.detect(self.current_camera.current_frame)
        if not results:
            QMessageBox.warning(self, "未检测到Tag", "在当前视野中未找到AprilTag")
            return
            
        # 假设只关注第一个检测到的Tag
        tag_res = results[0]
        
        # 2. 记录信息
        self.std_tag_pose = {
            'id': tag_res['id'],
            'tvec': tag_res['tvec'],  # Camera系
            'rvec': tag_res['rvec'],
            'euler': tag_res['euler']
        }
        
        # 3. 记录当前机械臂位姿 (如果有RobotService)
        robot_pose = None
        if self.robot_service:
           robot_pose = self.robot_service.get_position()
           
        msg = (f"标准点已记录!\nTag ID: {tag_res['id']}\n"
               f"距离: {tag_res['distance']:.3f}m\n"
               f"Pos (Cam): {np.round(tag_res['tvec'], 3)}\n"
               f"Euler: {np.round(tag_res['euler'], 1)}")
               
        if robot_pose:
            self.std_robot_pose = robot_pose
            msg += f"\nRobot Pose: {np.round(robot_pose, 3)}"
            
        info(f"标准点记录: {msg}", "CAMERA_UI")
        QMessageBox.information(self, "成功", msg)
        
        # 拍照留底
        self.save_snapshot(prefix="std_point_")

    def on_follow_and_correct(self):
        """跟随纠偏逻辑"""
        if not self.std_tag_pose:
            QMessageBox.warning(self, "错误", "请先记录标准点")
            return
            
        if not self.current_camera or not self.current_camera.current_frame is not None:
            QMessageBox.warning(self, "错误", "无图像数据")
            return

        # 0. 保存当前(纠偏前)的现场照片
        self.save_snapshot(prefix="deviation_point_")
            
        # 1. 当前图像检测
        detector = self._get_detector()
        results = detector.detect(self.current_camera.current_frame)
        if not results:
            QMessageBox.warning(self, "失败", "未检测到Tag")
            return
            
        # 找对应ID
        target_id = self.std_tag_pose['id']
        curr_res = next((r for r in results if r['id'] == target_id), None)
        
        if not curr_res:
            QMessageBox.warning(self, "失败", f"未找到ID为 {target_id} 的Tag")
            return
            
        # 2. 计算偏差 (Cam系)
        # 这里的偏差是指：物体相对于标准位置移动了多少
        # Tag在Cam系下坐标：T_c_t
        # std: T_c_t_std
        # curr: T_c_t_cur
        # 移动量 D = T_c_t_cur - T_c_t_std
        
        tvec_std = self.std_tag_pose['tvec']
        tvec_cur = curr_res['tvec']
        
        # 单位: 米 -> 转毫米
        dx_mm = (tvec_cur[0] - tvec_std[0]) * 1000.0 
        dy_mm = (tvec_cur[1] - tvec_std[1]) * 1000.0
        
        # 角度偏差 (Yaw)
        # euler是 (roll, pitch, yaw) 还是其他？detector.py中是 ZYX顺序 -> x, y, z
        # euler[2] 是 z轴旋转 (yaw)
        yaw_std = self.std_tag_pose['euler'][2]
        yaw_cur = curr_res['euler'][2]
        dtheta_deg = yaw_cur - yaw_std
        
        # 打印偏差
        info(f"视觉偏差计算: dx={dx_mm:.2f}mm, dy={dy_mm:.2f}mm, dr={dtheta_deg:.2f}deg", "CAMERA_UI")
        
        # 3. 计算机械臂新位姿
        if not self.robot_service:
            QMessageBox.warning(self, "错误", "未连接机械臂服务，无法跟随")
            return
            
        current_robot_pose = self.robot_service.get_position()
        if not current_robot_pose:
            QMessageBox.warning(self, "错误", "无法获取机械臂当前位姿")
            return

        try:
            # 加载手眼标定
            hand_eye_file = os.path.join(os.getcwd(), "T_eye_in_hand_chessboard.json")
            if not os.path.exists(hand_eye_file):
                 QMessageBox.warning(self, "错误", f"找不到手眼标定文件: {hand_eye_file}")
                 return
                 
            T_hand_eye = load_json_matrix(hand_eye_file, "T")
            
            # 使用 manual_correction_tool 计算 (注意：偏差输入是物体移动量)
            # 如果物体向右移动(+x), 机械臂应该向右移动(+x)去追它?
            # 视觉伺服通常是：我们要消除偏差。
            # 偏差 = Cur - Std. 
            # 如果物体X变大(右移)，我们也希望相机X变大(右移)去重新对准它。
            # 所以 deviation = (dx, dy, dr) 正确。
            
            # robot_pose单位确认：roboarm通常使用 rad。is_degree参数需要确认
            # manual_correction_tool默认接受度数/弧度混合？
            # 我们的 elite_pose_to_matrix 函数，如果 input pose rx,ry,rz 是 rad，则 is_degree=False
            
            # log显示 robot_service.get_position() 返回的是 [x, y, z, rx, ry, rz] 且 rx,ry,rz 为度数
            # 必须传给 calculate_correction 的 is_degree=True
            
            new_pose = calculate_correction(
                current_robot_pose, 
                [dx_mm, dy_mm, dtheta_deg], 
                T_hand_eye, 
                is_degree=True
            )
            
            confirm_msg = (f"计算完成。\n"
                           f"偏差: dx={dx_mm:.1f}, dy={dy_mm:.1f}, dr={dtheta_deg:.1f}\n"
                           f"当前位姿: {np.round(current_robot_pose, 3)}\n"
                           f"目标位姿: {np.round(new_pose, 3)}\n\n"
                           f"是否移动机械臂？")
                           
            reply = QMessageBox.question(self, "跟随确认", confirm_msg, 
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                        
            if reply == QMessageBox.StandardButton.Yes:
                # 标准移动 (move_to)
                # 使用 robot_service 的统一接口，它最终调用 elite.py 的 move_to
                # elite.py 的 move_to 内部会处理 C++控制器调用或脚本发送
                # manual_correction_tool 返回 (mm, deg)，与 move_to 兼容
                self.robot_service.move_to(*new_pose) 
                
                info("机械臂移动指令已发送", "CAMERA_UI")
                
                # 移动完成后拍照
                # 由于这是异步移动，实际上我们应该等待移动完成。
                # 简单起见，暂不阻塞等待
                QTimer.singleShot(5000, lambda: self.save_snapshot(prefix="follow_result_"))
                
        except Exception as e:
            error(f"计算或移动失败: {e}", "CAMERA_UI")
            QMessageBox.critical(self, "异常", f"执行失败: {str(e)}")

    def update_frame_count_in_table(self, camera_info: CameraInfo):
        """更新帧数显示 (已废弃表格，仅打印日志或更新其他UI)"""
        pass
        # try:
        #     # 表格已移除，此处暂时禁用
        #     pass
        # except Exception as e:
        #     warning(f"更新帧数显示失败: {e}", "CAMERA_UI")

    def save_snapshot(self, prefix="snapshot_"):
        """保存当前画面快照"""
        if not self.current_camera or not self.current_camera.current_frame is not None:
             warning("无法保存快照：无相机或无图像", "CAMERA_UI")
             return
             
        try:
            import cv2
            import time
            frame = self.current_camera.current_frame
            
            # 使用配置中的媒体保存路径
            from core.managers.app_config import AppConfigManager
            config_manager = AppConfigManager()
            save_dir = os.path.join(config_manager.paths_dir, "captures")
            
            os.makedirs(save_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}{timestamp}.jpg"
            filepath = os.path.join(save_dir, filename)
            
            # 颜色转换 RGB -> BGR (OpenCV使用BGR)
            # 假设 current_frame 是 RGB
            save_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite(filepath, save_img)
            
            info(f"已保存快照: {filepath}", "CAMERA_UI")
            return filepath
        except Exception as e:
            error(f"保存快照失败: {e}", "CAMERA_UI")
            return None

    def capture_image(self):
        """拍照"""
        if not self.current_camera or not self.current_camera.connected:
            QMessageBox.warning(self, "未连接", "请先连接相机")
            return

        try:
            import numpy as np
            import cv2
            import time

            frame_array = None

            # 优先使用相机驱动的拍照功能
            if self.current_camera.camera_driver:
                try:
                    # 确保相机驱动使用配置的分辨率
                    if hasattr(self.current_camera.camera_driver, 'set_resolution'):
                        # 解析分辨率字符串 (例如 "1920x1080")
                        resolution_str = self.current_camera.resolution
                        if 'x' in resolution_str:
                            try:
                                width, height = map(int, resolution_str.split('x'))
                                self.current_camera.camera_driver.set_resolution(width, height)
                                info(f"设置相机分辨率为: {width}x{height}", "CAMERA_UI")
                            except ValueError as e:
                                warning(f"分辨率格式错误: {resolution_str}, 使用默认分辨率", "CAMERA_UI")

                    frame_array = self.current_camera.camera_driver.capture_image()
                    if frame_array is not None:
                        info(f"使用相机驱动拍照: {self.current_camera.name}", "CAMERA_UI")
                    else:
                        warning(f"相机驱动拍照返回空帧: {self.current_camera.name}", "CAMERA_UI")
                except Exception as e:
                    warning(f"相机驱动拍照失败: {e}", "CAMERA_UI")

            # 如果驱动拍照失败，回退到当前预览帧
            if frame_array is None and self.current_camera.current_frame is not None:
                frame_array = self.current_camera.current_frame
                info(f"使用预览帧拍照: {self.current_camera.name}", "CAMERA_UI")

            if frame_array is not None:
                # 使用AppConfigManager获取 captures 目录
                from core.managers.app_config import AppConfigManager
                app_config = AppConfigManager()
                captures_dir = app_config.get_captures_directory()

                # 生成文件名（不包含中文）
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                camera_id = self.current_camera.camera_id.replace(" ", "_").replace("/", "_")
                filename = f"camera_{camera_id}_{timestamp}.jpg"
                filepath = captures_dir / filename

                # 保存图像 (转换为字符串路径给cv2.imwrite)
                filepath_str = str(filepath)
                success = cv2.imwrite(filepath_str, frame_array)
                
                # 如果是RealSense相机，同时保存深度图
                depth_saved = False
                depth_filepath_str = ""
                if success and hasattr(self.current_camera.camera_driver, 'get_depth_frame'):
                    try:
                        from drivers.camera.realsense import RealSenseCamera
                        if isinstance(self.current_camera.camera_driver, RealSenseCamera):
                            depth_frame = self.current_camera.camera_driver.get_depth_frame()
                            if depth_frame is not None:
                                # 保存深度图（16位PNG格式）
                                depth_filename = f"camera_{camera_id}_{timestamp}_depth.png"
                                depth_filepath = captures_dir / depth_filename
                                depth_filepath_str = str(depth_filepath)
                                
                                # 保存原始深度数据（16位）
                                cv2.imwrite(depth_filepath_str, depth_frame)
                                
                                # 同时保存深度图可视化版本（伪彩色）
                                depth_colormap = cv2.applyColorMap(
                                    cv2.convertScaleAbs(depth_frame, alpha=0.03), 
                                    cv2.COLORMAP_JET
                                )
                                depth_vis_filename = f"camera_{camera_id}_{timestamp}_depth_vis.jpg"
                                depth_vis_filepath = captures_dir / depth_vis_filename
                                cv2.imwrite(str(depth_vis_filepath), depth_colormap)
                                
                                depth_saved = True
                                info(f"深度图已保存: {depth_filename}", "CAMERA_UI")
                    except Exception as e:
                        warning(f"保存深度图失败: {e}", "CAMERA_UI")
                
                if success:
                    # 获取图像信息
                    height, width = frame_array.shape[:2]
                    file_size = filepath.stat().st_size

                    info(f"拍照成功: {filename} ({width}x{height}, {file_size} bytes)", "CAMERA_UI")
                    
                    # 构建消息
                    msg = f"彩色图像已保存到: {filepath_str}\n分辨率: {width}x{height}\n文件大小: {file_size} bytes"
                    if depth_saved:
                        msg += f"\n\n深度图已保存:\n- 原始数据: {depth_filepath_str}\n- 可视化图: {depth_filepath_str.replace('_depth.png', '_depth_vis.jpg')}"
                    
                    QMessageBox.information(self, "拍照成功", msg)
                else:
                    error(f"保存图像失败: {filepath_str}", "CAMERA_UI")
                    QMessageBox.warning(self, "保存失败", f"无法保存图像到: {filepath_str}")
            else:
                warning("无可用图像数据，拍照失败", "CAMERA_UI")
                QMessageBox.warning(self, "拍照失败", "无可用图像数据，请确保预览正常")

        except Exception as e:
            error(f"拍照时发生异常: {str(e)}", "CAMERA_UI")
            QMessageBox.warning(self, "拍照异常", f"拍照时发生异常: {str(e)}")

    def start_camera_preview(self, camera_info: CameraInfo):
        """启动相机预览 - 使用统一的CameraService流式传输"""
        try:
            info(f"启动相机预览: {camera_info.name}", "CAMERA_UI")

            # 关键修复: 优先使用 camera_services 中已连接的服务实例
            if camera_info.camera_id in self.camera_services:
                self.streaming_services[camera_info.camera_id] = self.camera_services[camera_info.camera_id]

            # 确保相机有独立的CameraService实例
            if camera_info.camera_id not in self.streaming_services:
                from core.services.camera_service import CameraService
                self.streaming_services[camera_info.camera_id] = CameraService()

            # 获取或创建这个相机的CameraService
            camera_service = self.streaming_services[camera_info.camera_id]

            info(f"为相机 {camera_info.name} 使用Service层连接", "CAMERA_UI")

            # 停止其他所有相机的预览
            self.stop_all_previews()

            # 启动这个相机的流式传输
            # 保存相机ID和引用，避免闭包问题
            camera_id = camera_info.camera_id
            camera_name = camera_info.name

            info(f"为相机 {camera_name} (ID: {camera_id}) 创建预览回调", "CAMERA_UI")

            def frame_callback(frame_array):
                try:
                    # 检查预览标签是否还存在且未被销毁
                    if (not hasattr(self, 'preview_label') or
                        self.preview_label is None or
                        hasattr(self.preview_label, '_is_destroyed') and self.preview_label._is_destroyed):
                        return

                    # 通过相机ID查找对应的camera_info，避免闭包引用问题
                    target_camera_info = None
                    for ci in self.camera_list:
                        if ci.camera_id == camera_id:
                            target_camera_info = ci
                            break

                    if target_camera_info is None:
                        error(f"无法找到相机ID {camera_id} 对应的camera_info", "CAMERA_UI")
                        return

                    # 更新相机的帧信息 - 添加详细调试
                    target_camera_info.current_frame = frame_array
                    target_camera_info.last_frame_time = time.time()
                    target_camera_info.frame_count = target_camera_info.frame_count + 1 if hasattr(target_camera_info, 'frame_count') else 1

                    # 调试信息：确认回调来自正确的相机
                    # debug(f"回调更新 - 相机: {target_camera_info.name} (ID: {camera_id}), 帧数: {target_camera_info.frame_count}, 帧大小: {frame_array.shape if frame_array is not None else 'None'}", "CAMERA_UI")

                    # 发送帧信号进行UI更新
                    self.on_frame_captured(target_camera_info)
                except Exception as callback_error:
                    error(f"预览回调错误 for {camera_name} (ID: {camera_id}): {callback_error}", "CAMERA_UI")

            # 使用CameraService的start_streaming
            result = camera_service.start_streaming(frame_callback)

            if result['success']:
                info(f"相机预览已启动: {camera_info.name}", "CAMERA_UI")

                # 启动UI更新定时器
                if not hasattr(self, 'preview_update_timer'):
                    self.preview_update_timer = QTimer()
                    self.preview_update_timer.timeout.connect(self.update_preview_info)
                    self.preview_update_timer.start(100)  # 100ms更新一次
                return True
            else:
                error(f"相机预览启动失败: {camera_info.name} - {result.get('error')}", "CAMERA_UI")
                return False

        except Exception as e:
            error(f"启动相机预览失败: {e}", "CAMERA_UI")
            return False

    def update_camera_status_realtime(self):
        """实时更新相机状态 (Stubbed)"""
        pass

    def _unused_update_camera_status_realtime(self):
        """实时更新相机状态"""
        try:
            if not hasattr(self, 'camera_table'):
                return

            for row, camera_info in enumerate(self.camera_list):
                if row >= self.camera_table.rowCount():
                    continue

                status_item = self.camera_table.item(row, 1)
                if not status_item:
                    continue

                if camera_info.connected:
                    # 检查是否正在预览（使用新的streaming_services）
                    is_previewing = False
                    if camera_info.camera_id in self.streaming_services:
                        camera_service = self.streaming_services[camera_info.camera_id]
                        is_previewing = camera_service.is_streaming()

                    if is_previewing:
                        # 检查流式传输是否健康
                        if camera_info.camera_id in self.streaming_services:
                            camera_service = self.streaming_services[camera_info.camera_id]
                            if camera_service.is_streaming():
                                status_text = "🟡 预览中"
                                status_color = "#FF9800"
                            else:
                                status_text = "🟠 预览异常"
                                status_color = "#FF5722"
                        else:
                            status_text = "🟠 预览异常"
                            status_color = "#FF5722"
                    else:
                        status_text = "🟢 已连接"
                        status_color = "#4CAF50"
                else:
                    status_text = "🔴 未连接"
                    status_color = "#f44336"

                # 更新状态显示
                if status_item.text() != status_text:  # 只在状态变化时更新
                    status_item.setText(status_text)
                    status_item.setForeground(QColor(status_color))
                    status_item.setFont(QFont('', 8, QFont.Weight.Bold))

                # 更新帧数显示
                frame_item = self.camera_table.item(row, 2)
                if frame_item and camera_info.connected and hasattr(camera_info, 'frame_count'):
                    frame_text = f"{camera_info.frame_count}"
                    if frame_item.text() != frame_text:
                        frame_item.setText(frame_text)

        except Exception as e:
            error(f"更新相机状态失败: {e}", "CAMERA_UI")

    def connect_selected_camera(self):
        """连接选中的相机"""
        self.connect_current_selected_camera()

    def _unused_connect_selected_camera(self):
        """连接选中的相机"""
        selected_rows = self.camera_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "未选择相机", "请先选择要连接的相机")
            return

        row = selected_rows[0].row()
        self.connect_camera(row)

    def disconnect_current_camera(self):
        """断开当前相机"""
        if not self.current_camera:
            QMessageBox.warning(self, "未连接", "当前没有连接的相机")
            return

        camera_id = self.current_camera.camera_id

        # 1. 停止预览
        self.stop_preview()

        # 2. 真正断开硬件连接
        if camera_id in self.camera_services:
            camera_service = self.camera_services[camera_id]
            camera_service.disconnect()
            info(f"已断开相机硬件连接: {self.current_camera.name}", "CAMERA_UI")

        # 重置连接状态
        self.current_camera.connected = False

        # 更新UI
        self.on_camera_combo_changed(self.camera_combo.currentIndex())

                
    def disconnect_all(self):
        """断开所有相机连接（用于程序关闭时清理）"""
        try:
            info("正在断开所有相机...", "CAMERA_UI")
            self.stop_all_previews()
            
            # 使用列表副本进行遍历，因为可能会修改字典
            for camera_id, service in list(self.streaming_services.items()):
                try:
                    if service and hasattr(service, 'is_connected') and service.is_connected():
                        info(f"断开相机: {camera_id}", "CAMERA_UI")
                        service.disconnect()
                except Exception as e:
                    error(f"断开相机 {camera_id} 失败: {e}", "CAMERA_UI")
            
            self.streaming_services.clear()
            info("所有相机已断开", "CAMERA_UI")
        except Exception as e:
            error(f"批量断开相机失败: {e}", "CAMERA_UI")

        # 更新状态指示器
        if hasattr(self, 'camera_status_indicator'):
            self.camera_status_indicator.setText("🔴 无连接")
            self.camera_status_indicator.setStyleSheet("""
                QLabel {
                    background-color: #444;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 15px;
                    font-weight: bold;
                }
            """)

        self.current_camera = None
        QMessageBox.information(self, "断开连接", "相机已断开连接")

    def update_preview_info(self):
        """更新预览信息"""
        if self.current_camera and self.current_camera.connected:
            try:
                # 更新时间戳
                current_time = time.strftime("%H:%M:%S")
                # if hasattr(self, 'last_frame_time_label'):
                #     self.last_frame_time_label.setText(f"最后帧: {current_time}")

                # 模拟FPS更新 (已不需要更新表格)
                pass

            except Exception as e:
                error(f"更新预览信息失败: {e}", "CAMERA_UI")

    def add_camera_dialog(self):
        """添加相机对话框"""
        info("用户点击添加相机", "CAMERA_UI")

        dialog = QDialog(self)
        dialog.setWindowTitle("添加相机")
        dialog.setModal(True)
        layout = QVBoxLayout()

        # 相机名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("相机名称:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("例如: 主相机、辅助相机")
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # 相机类型
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("相机类型:"))
        type_combo = QComboBox()
        type_combo.addItems(["模拟相机", "海康威视相机", "USB相机"])
        type_layout.addWidget(type_combo)
        layout.addLayout(type_layout)

        # 连接参数
        params_group = QGroupBox("连接参数")
        params_layout = QVBoxLayout()

        # RTSP地址（用于网络相机）
        rtsp_layout = QHBoxLayout()
        rtsp_layout.addWidget(QLabel("RTSP地址:"))
        rtsp_input = QLineEdit()
        rtsp_input.setPlaceholderText("rtsp://192.168.0.100:554/Streaming/Channels/101")
        rtsp_layout.addWidget(rtsp_input)
        params_layout.addLayout(rtsp_layout)

        # 模拟相机媒体设置
        media_layout = QHBoxLayout()
        media_layout.addWidget(QLabel("媒体源:"))
        media_type_combo = QComboBox()
        media_type_combo.addItems(["程序生成", "图片文件夹", "视频文件"])
        media_layout.addWidget(media_type_combo)
        params_layout.addLayout(media_layout)

        media_path_layout = QHBoxLayout()
        media_path_layout.addWidget(QLabel("媒体路径:"))
        media_path_input = QLineEdit()
        media_path_input.setPlaceholderText("选择图片或视频文件夹")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(lambda: self.browse_media_folder(media_path_input))
        media_path_layout.addWidget(media_path_input)
        media_path_layout.addWidget(browse_btn)
        params_layout.addLayout(media_path_layout)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # 分辨率和帧率
        settings_layout = QFormLayout()
        resolution_combo = QComboBox()
        resolution_combo.addItems(["1920x1080", "1280x720", "800x600", "640x480"])
        fps_spin = QSpinBox()
        fps_spin.setRange(1, 60)
        fps_spin.setValue(30)
        settings_layout.addRow("分辨率:", resolution_combo)
        settings_layout.addRow("帧率(FPS):", fps_spin)
        layout.addLayout(settings_layout)

        # 按钮
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("添加")
        cancel_btn = QPushButton("取消")
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        # 连接事件
        def on_type_changed(text):
            # 根据相机类型显示/隐藏相关设置
            is_simulation = (text == "模拟相机")
            rtsp_input.setEnabled(not is_simulation)
            media_type_combo.setEnabled(is_simulation)
            media_path_input.setEnabled(is_simulation)
            browse_btn.setEnabled(is_simulation)

        type_combo.currentTextChanged.connect(on_type_changed)
        on_type_changed(type_combo.currentText())  # 初始状态

        def add_camera():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(dialog, "输入错误", "请输入相机名称")
                return

            # 创建相机信息
            camera_type = type_combo.currentText()
            camera_id = f"cam_{len(self.camera_list) + 1:03d}"

            # 添加到相机列表
            camera_info = CameraInfo(camera_id)
            camera_info.name = name
            camera_info.camera_type = camera_type
            camera_info.resolution = resolution_combo.currentText()
            camera_info.config = {
                'fps': fps_spin.value(),
                'rtsp_url': rtsp_input.text().strip() if rtsp_input.isEnabled() else '',
                'simulation': camera_type == "模拟相机",
                'media_type': media_type_combo.currentText() if camera_type == "模拟相机" else "程序生成",
                'media_path': media_path_input.text().strip() if camera_type == "模拟相机" else ""
            }

            self.camera_list.append(camera_info)
            self.update_camera_table()

            info(f"添加相机: {name} ({camera_type})", "CAMERA_UI")
            QMessageBox.information(dialog, "添加成功", f"相机 '{name}' 已添加")
            dialog.accept()

        ok_btn.clicked.connect(add_camera)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def browse_media_folder(self, line_edit):
        """浏览媒体文件夹"""
        from PyQt6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择媒体文件夹")
        if folder:
            line_edit.setText(folder)

    def update_camera_table(self):
        pass

    def _unused_update_camera_table(self):
        """更新相机表格"""
        if not hasattr(self, 'camera_table'):
            return

        self.camera_table.setRowCount(len(self.camera_list))

        for row, camera_info in enumerate(self.camera_list):
            # 相机名称
            name_item = QTableWidgetItem(camera_info.name)
            name_item.setToolTip(f"类型: {camera_info.camera_type}\nID: {camera_info.camera_id}")
            self.camera_table.setItem(row, 0, name_item)

            # 连接状态
            if camera_info.connected:
                # 检查是否正在预览（使用新的streaming_services）
                is_previewing = False
                if camera_info.camera_id in self.streaming_services:
                    camera_service = self.streaming_services[camera_info.camera_id]
                    is_previewing = camera_service.is_streaming()

                if is_previewing:
                    status_text = "🟡 预览中"
                    status_color = "#FF9800"
                else:
                    status_text = "🟢 已连接"
                    status_color = "#4CAF50"
            else:
                status_text = "🔴 未连接"
                status_color = "#f44336"

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            status_item.setFont(QFont('', 8, QFont.Weight.Bold))
            self.camera_table.setItem(row, 1, status_item)

            # 帧数（显示当前帧数或配置的FPS）
            if camera_info.connected and hasattr(camera_info, 'frame_count'):
                frame_text = f"{camera_info.frame_count}"
            else:
                fps = camera_info.config.get('fps', 30)
                frame_text = f"{fps}fps"

            frame_item = QTableWidgetItem(frame_text)
            frame_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.camera_table.setItem(row, 2, frame_item)

            # 预览按钮
            if camera_info.connected:
                # 预览按钮
                preview_btn = QPushButton("👁 预览")
                preview_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        border: none;
                        padding: 5px 10px;
                        border-radius: 4px;
                        font-size: 11px;
                        font-weight: bold;
                                            }
                    QPushButton:hover {
                        background-color: #1976D2;
                        border: 1px solid #1976D2;
                    }
                    QPushButton:pressed {
                        background-color: #1565C0;
                        border: 1px solid #1976D2;
                    }
                    QPushButton:disabled {
                        background-color: #cccccc;
                        color: #666666;
                        border: 1px solid #cccccc;
                    }
                """)
                preview_btn.clicked.connect(lambda checked, idx=row: self.start_camera_preview_by_index(idx))
                self.camera_table.setCellWidget(row, 3, preview_btn)
            else:
                # 未连接时显示提示
                no_preview_label = QLabel("—")
                no_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                no_preview_label.setStyleSheet("color: #999; font-style: italic;")
                self.camera_table.setCellWidget(row, 3, no_preview_label)

    def disconnect_camera(self, row: int):
        self.disconnect_current_camera()

    def _unused_disconnect_camera(self, row: int):
        """断开指定相机"""
        if row >= len(self.camera_list):
            return

        camera_info = self.camera_list[row]

        try:
            # 停止预览
            if camera_info.camera_id in self.streaming_services:
                camera_service = self.streaming_services[camera_info.camera_id]
                result = camera_service.stop_streaming()
                if not result.get('success'):
                    warning(f"停止相机 {camera_info.camera_id} 流式传输失败: {result.get('error')}", "CAMERA_UI")

            # 如果是当前相机，停止预览
            if self.current_camera and self.current_camera.camera_id == camera_info.camera_id:
                # 停止流式传输服务
                if camera_info.camera_id in self.streaming_services:
                    camera_service = self.streaming_services[camera_info.camera_id]
                    result = camera_service.stop_streaming()
                    if not result.get('success'):
                        warning(f"停止相机 {camera_info.camera_id} 流式传输失败: {result.get('error')}", "CAMERA_UI")

                self.current_camera = None

                # 同步更新右侧预览控制按钮状态
                self.start_preview_btn.setEnabled(False)
                self.stop_preview_btn.setEnabled(False)
                if hasattr(self, 'auto_focus_btn'):
                    self.auto_focus_btn.setEnabled(False)
                self.preview_label.setText("📹 选择相机开始预览")
                self.preview_label.clear_preview()

            # 使用该相机的CameraService断开相机连接
            if camera_info.camera_driver and camera_info.camera_id in self.streaming_services:
                camera_service = self.streaming_services[camera_info.camera_id]
                try:
                    result = camera_service.disconnect()
                    if result.get('success'):
                        info(f"相机已断开: {camera_info.name}", "CAMERA_UI")
                    else:
                        warning(f"断开相机失败: {camera_info.name} - {result.get('error')}", "CAMERA_UI")
                except Exception as e:
                    warning(f"断开相机异常: {camera_info.name} - {e}", "CAMERA_UI")
                finally:
                    camera_info.camera_driver = None
            elif camera_info.camera_driver:
                # 如果有camera_driver但没有对应的CameraService，直接断开
                try:
                    camera_info.camera_driver.disconnect()
                    info(f"相机已断开: {camera_info.name}", "CAMERA_UI")
                except Exception as e:
                    warning(f"断开相机失败: {camera_info.name} - {e}", "CAMERA_UI")
                finally:
                    camera_info.camera_driver = None

            # 更新状态
            camera_info.connected = False
            camera_info.current_frame = None
            camera_info.last_frame_time = None

            # 发送断开信号
            self.camera_disconnected.emit(camera_info.camera_id)

            # 更新整个表格以确保状态同步
            self.update_camera_table()

            # 更新状态指示器
            if hasattr(self, 'camera_status_indicator'):
                self.camera_status_indicator.setText("🔴 未选择相机")
                self.camera_status_indicator.setStyleSheet("""
                    QLabel {
                        background-color: #444;
                        color: white;
                        padding: 5px 15px;
                        border-radius: 15px;
                        font-weight: bold;
                    }
                """)

            if hasattr(self, 'camera_status_label'):
                self.camera_status_label.setText("🔴 未选择相机")

            # 更新表格按钮
            self.update_camera_table()

            info(f"断开相机: {camera_info.name}", "CAMERA_UI")

        except Exception as e:
            error(f"断开相机时发生异常: {camera_info.name} - {str(e)}", "CAMERA_UI")

    def delete_camera(self, row: int):
        """删除相机"""
        if row >= len(self.camera_list):
            return

        camera_info = self.camera_list[row]

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除相机 '{camera_info.name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 先断开连接
            if camera_info.connected:
                self.disconnect_camera(row)

            # 从列表中删除
            self.camera_list.pop(row)

            # 更新表格
            self.update_camera_table()

            info(f"删除相机: {camera_info.name}", "CAMERA_UI")

    def start_camera_preview_by_index(self, row: int):
        """根据索引启动相机预览"""
        if row >= len(self.camera_list):
            return

        camera_info = self.camera_list[row]

        # 如果不是当前相机，先切换
        if not self.current_camera or self.current_camera.camera_id != camera_info.camera_id:
            self.current_camera = camera_info

        # 启动预览
        self.start_preview()

    def on_camera_selection_changed(self):
        """相机选择改变事件"""
        selected_rows = self.camera_table.selectionModel().selectedRows()

        if selected_rows:
            row = selected_rows[0].row()
            if row < len(self.camera_list):
                camera_info = self.camera_list[row]
                info(f"选择相机: {camera_info.name}", "CAMERA_UI")

                # 设置当前选中的相机
                self.current_camera = camera_info

                # 同步更新预览按钮状态
                if camera_info.connected:
                    # 检查是否正在预览（使用新的streaming_services）
                    is_previewing = False
                    if camera_info.camera_id in self.streaming_services:
                        camera_service = self.streaming_services[camera_info.camera_id]
                        is_previewing = camera_service.is_streaming()

                    self.start_preview_btn.setEnabled(not is_previewing)
                    self.stop_preview_btn.setEnabled(is_previewing)

                    if is_previewing:
                        self.preview_label.setText("📹 预览中...")
                    else:
                        self.preview_label.setText("📹 已连接，点击开始预览")
                else:
                    # 未连接的相机
                    self.start_preview_btn.setEnabled(False)
                    self.stop_preview_btn.setEnabled(False)
                    self.preview_label.setText("📹 请先连接相机")
        else:
            # 没有选中任何相机
            info("取消相机选择", "CAMERA_UI")
            self.current_camera = None
            self.start_preview_btn.setEnabled(False)
            self.stop_preview_btn.setEnabled(False)
            self.preview_label.setText("📹 请选择相机")
    
    def on_camera_selection_changed_with_auto_save(self):
        """相机选择改变事件（带自动保存）"""
        # 先调用原有的选择变更逻辑
        self.on_camera_selection_changed()
        
        # 触发自动保存（防抖）
        if self.is_from_vmc_node:
            self._trigger_parameter_change_auto_save()
            debug("CameraControlTab: Camera selection changed, triggering auto-save", "CAMERA_UI")

    def on_camera_double_clicked(self, item):
        """相机双击事件"""
        row = item.row()
        if row < len(self.camera_list):
            camera_info = self.camera_list[row]
            if camera_info.connected:
                # 如果已连接，显示预览
                self.start_camera_preview_by_index(row)
            else:
                # 如果未连接，尝试连接
                self.connect_camera(row)

    def update_coordinate_display(self, x: int, y: int, rgb_info: str = ""):
        """更新坐标显示"""
        if hasattr(self, 'coordinate_label'):
            if x >= 0 and y >= 0:
                if rgb_info:
                    self.coordinate_label.setText(f"坐标: ({x}, {y}) | {rgb_info}")
                else:
                    self.coordinate_label.setText(f"坐标: ({x}, {y})")
            else:
                self.coordinate_label.setText("坐标: -")

    def clear_coordinate_display(self):
        """清除坐标显示"""
        if hasattr(self, 'coordinate_label'):
            self.coordinate_label.setText("坐标: -")

    def select_camera_from_config(self):
        """从硬件配置选择相机"""
        try:
            # 直接从硬件配置文件读取
            config_file = 'config/hardware_config.json'
            if not os.path.exists(config_file):
                QMessageBox.warning(self, "无配置文件", "硬件配置文件不存在，请先在硬件配置中添加相机")
                return

            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            camera_configs = config_data.get('cameras', [])
            if not camera_configs:
                QMessageBox.warning(self, "无配置", "硬件配置中没有可用相机，请先在硬件配置中添加相机")
                return

            # 刷新当前相机列表状态，确保信息完整
            for i, camera_info in enumerate(self.camera_list):
                # 查找对应的配置更新信息
                for config in camera_configs:
                    if camera_info.camera_id == config.get('id'):
                        # 更新相机信息
                        camera_info.name = config.get('name', camera_info.name)
                        camera_info.config = config
                        # 更新表格显示
                        self.update_camera_table()
                        break

            # 检查哪些相机已经添加
            added_camera_ids = {camera.camera_id for camera in self.camera_list}

        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法读取硬件配置: {str(e)}")
            return

        # 创建选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("选择相机")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        layout = QVBoxLayout()

        # 标题
        title_label = QLabel("从硬件配置中选择相机:")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(title_label)

        # 可用相机列表
        available_list = QListWidget()
        available_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        # 添加可用相机
        for config in camera_configs:
            # 检查是否已经添加
            already_added = any(cam.name == config['name'] for cam in self.camera_list)

            item_text = f"📷 {config['name']}"
            # 通过connection_type判断是否为模拟相机
            if config.get('connection_type') == 'simulation':
                item_text += " (模拟)"
            else:
                item_text += " (真实)"

            item_text += f" - {config.get('resolution', '未知分辨率')} - {config.get('fps', 30)}fps"

            item = QListWidgetItem(item_text)
            item.setData(1, config)  # 存储配置数据

            if already_added:
                item.setForeground(QColor('#999'))  # 灰色显示已添加的
                item.setToolTip("该相机已添加到当前列表")

            available_list.addItem(item)

        layout.addWidget(available_list)

        # 已添加相机提示
        added_label = QLabel("已添加的相机显示为灰色")
        added_label.setStyleSheet("color: #666666; font-style: italic; padding: 5px;")
        layout.addWidget(added_label)

        # 按钮
        button_layout = QHBoxLayout()

        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")

        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        def add_selected_camera():
            selected_items = available_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(dialog, "未选择", "请选择要添加的相机")
                return

            selected_config = selected_items[0].data(1)

            # 安全地从配置中获取相机信息
            def get_camera_info_safe(config):
                """安全地从配置中获取相机信息，提供默认值"""
                return {
                    'name': config.get('name', 'Unknown Camera'),
                    'resolution': config.get('resolution', '1920x1080'),
                    'fps': config.get('fps', 30),
                    'timeout': config.get('timeout', 5),
                    'brand': config.get('brand', 'unknown'),
                    'model': config.get('model', ''),
                    'connection_type': config.get('connection_type', 'unknown')
                }

            camera_data = get_camera_info_safe(selected_config)

            # 检查是否已添加
            if any(cam.name == camera_data['name'] for cam in self.camera_list):
                QMessageBox.warning(dialog, "已存在", f"相机 '{camera_data['name']}' 已经添加")
                return

            # 创建CameraInfo对象
            camera_info = CameraInfo(camera_data['name'])
            camera_info.name = camera_data['name']
            # 通过connection_type判断是否为模拟相机，UI层不直接访问is_simulation
            camera_info.camera_type = "模拟相机" if camera_data['connection_type'] == 'simulation' else "真实相机"
            camera_info.resolution = camera_data['resolution']
            camera_info.fps = camera_data['fps']
            camera_info.config = selected_config.copy()

            # 添加到相机列表
            self.camera_list.append(camera_info)
            self.update_camera_table()

            info(f"已添加相机: {camera_data['name']}", "CAMERA_UI")
            QMessageBox.information(dialog, "添加成功", f"相机 '{camera_data['name']}' 已添加到当前列表")
            dialog.accept()

        ok_btn.clicked.connect(add_selected_camera)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def apply_to_vmc_node(self):
        """将当前选择的相机应用到VMC节点"""
        try:
            if not self.is_from_vmc_node or not self.vmc_callback:
                warning("Not initialized with VMC node callback", "CAMERA_UI")
                return
            
            # 获取当前选择的相机
            selected_camera_info = self.get_selected_camera()
            if not selected_camera_info:
                QMessageBox.warning(self, "未选择相机", "请先在表格中选择一个相机")
                return
            
            # 获取相机ID（从config中获取）
            camera_id = None
            if hasattr(selected_camera_info, 'config') and selected_camera_info.config:
                camera_id = selected_camera_info.config.get('id')
            
            if not camera_id:
                QMessageBox.warning(self, "相机ID缺失", "选择的相机配置中缺少ID信息")
                return
            
            # 调用回调函数更新VMC节点的selected_hardware_id
            debug(f"CameraControlTab: Applying camera {camera_id} to VMC node", "CAMERA_UI")
            self.vmc_callback(camera_id)
            
            QMessageBox.information(self, "应用成功", f"相机 '{selected_camera_info.name}' 已应用到节点")
            
        except Exception as e:
            error(f"Failed to apply camera to VMC node: {e}", "CAMERA_UI")
            QMessageBox.critical(self, "应用失败", f"应用相机到节点时出错: {e}")
    
    def get_selected_camera(self):
        """获取当前选择的相机信息"""
        try:
            selected_rows = self.camera_table.selectedItems()
            if not selected_rows:
                return None
            
            # 获取选中行的索引
            selected_row = selected_rows[0].row()
            
            # 确保索引在有效范围内
            if 0 <= selected_row < len(self.camera_list):
                return self.camera_list[selected_row]
            
            return None
            
        except Exception as e:
            error(f"Failed to get selected camera: {e}", "CAMERA_UI")
            return None


