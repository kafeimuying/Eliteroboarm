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


# ==================== ArUco 检测器类 ====================
class ArUcoDetector:
    """ArUco标记检测器 - 用于检测OpenCV ArUco标记（6x6等）"""
    def __init__(self, camera_matrix, dist_coeffs, marker_size=0.1, dictionary_name="DICT_6X6_250"):
        """
        Args:
            camera_matrix: 相机内参矩阵 3x3
            dist_coeffs: 畸变系数
            marker_size: 标记尺寸 (米)
            dictionary_name: ArUco字典名称 (如 "DICT_6X6_250")
        """
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.marker_size = marker_size
        
        # 获取ArUco字典
        aruco_dict_map = {
            "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
            "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
            "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
            "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
            "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
            "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
            "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
            "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
            "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
            "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
            "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
            "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
            "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
            "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
            "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
            "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
        }
        
        dict_id = aruco_dict_map.get(dictionary_name, cv2.aruco.DICT_6X6_250)
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        self.dict_name = dictionary_name
    
    def detect(self, img):
        """检测ArUco标记并返回与AprilTag检测器相同格式的结果"""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        corners, ids, rejected = self.detector.detectMarkers(gray)
        
        results = []
        if ids is not None:
            for i, marker_id in enumerate(ids.flatten()):
                # 估计位姿
                rvec, tvec, _ = cv2.aruco.estimatePoseSingleMarkers(
                    [corners[i]], self.marker_size, self.camera_matrix, self.dist_coeffs
                )
                
                # 转换为欧拉角
                R, _ = cv2.Rodrigues(rvec[0][0])
                euler = self._rotation_matrix_to_euler(R)
                
                # 计算距离
                distance = np.linalg.norm(tvec[0][0])
                
                # 计算中心点 (从corners计算)
                marker_corners = corners[i].reshape(4, 2)
                center = marker_corners.mean(axis=0)
                
                results.append({
                    'id': int(marker_id),
                    'tvec': tvec[0][0],
                    'rvec': rvec[0][0],
                    'euler': euler,
                    'corners': corners[i],
                    'center': center,  # 像素中心坐标
                    'distance': distance,
                    'marker_type': 'aruco',
                    'dict_name': self.dict_name
                })
        
        return results
    
    def _rotation_matrix_to_euler(self, R):
        """旋转矩阵转欧拉角 (XYZ顺序, 单位: 度)"""
        sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)
        singular = sy < 1e-6
        
        if not singular:
            x = np.arctan2(R[2, 1], R[2, 2])
            y = np.arctan2(-R[2, 0], sy)
            z = np.arctan2(R[1, 0], R[0, 0])
        else:
            x = np.arctan2(-R[1, 2], R[1, 1])
            y = np.arctan2(-R[2, 0], sy)
            z = 0
        
        return np.degrees([x, y, z])


# 延迟导入视觉算法模块以避免初始化时的循环依赖
VISION_ALGO_AVAILABLE = False
_vision_import_error = None

# 检查环境变量，允许用户禁用视觉伺服功能进行调试
if os.environ.get('DISABLE_VISION_SERVO', '').lower() in ('1', 'true', 'yes'):
    _vision_import_error = "用户通过环境变量禁用"
else:
    try:
        # 添加项目根目录到路径
        _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        if _project_root not in sys.path:
            sys.path.insert(0, _project_root)
        
        from manual_correction_tool import calculate_correction, load_json_matrix
        # 直接导入 apriltag_detector，避免经过 src.algorithms 包
        import importlib.util
        _detector_path = os.path.join(_project_root, "src", "algorithms", "vision", "apriltag_detector.py")
        _spec = importlib.util.spec_from_file_location("apriltag_detector", _detector_path)
        _detector_module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_detector_module)
        AprilTagDetector = _detector_module.AprilTagDetector
        
        from multi_point_servo import MultiPointServo, ServoRecipe, save_recipe, load_recipe, list_recipes, RECIPE_DIR
        VISION_ALGO_AVAILABLE = True
    except ImportError as e:
        _vision_import_error = str(e)
        VISION_ALGO_AVAILABLE = False
    except Exception as e:
        _vision_import_error = str(e)
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


class FloatingJogDialog(QDialog):
    """可拖动的浮动机械臂轴向控制窗口（长按持续运动）"""

    def __init__(self, robot_service, parent=None):
        super().__init__(parent)
        self.robot_service = robot_service
        self.setWindowTitle("机械臂控制")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(400, 560)
        self._jog_timer = QTimer(self)
        self._jog_timer.setInterval(200)  # 每200ms发送一次移动指令
        self._jog_timer.timeout.connect(self._do_jog_step)
        self._jog_axis = None
        self._jog_direction = 0
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("轴向控制 (长按移动)")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setContentsMargins(5, 5, 5, 5)

        # 线性轴控制 (X/Y/Z) - 3列3行布局
        linear_label = QLabel("线性轴 (X/Y/Z)")
        linear_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linear_label.setStyleSheet("font-size:12px; color:#666; font-weight:bold;")
        grid.addWidget(linear_label, 0, 0, 1, 3)
        
        # 线性轴按钮布局：3列3行，每行一个轴的+/-
        linear_directions = [
            ("X-", 1, 0), ("X+", 1, 2),
            ("Y-", 2, 0), ("Y+", 2, 2),
            ("Z-", 3, 0), ("Z+", 3, 2),
        ]
        
        linear_axis_labels = [("X:", 1, 1), ("Y:", 2, 1), ("Z:", 3, 1)]
        for label_text, row, col in linear_axis_labels:
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size:12px; color:#666; font-weight:bold;")
            grid.addWidget(lbl, row, col)

        for text, row, col in linear_directions:
            btn = QPushButton(text)
            btn.setFixedSize(85, 45)
            btn.setStyleSheet(
                "QPushButton{background-color:#2196F3;color:white;border:none;"
                "border-radius:6px;font-weight:bold;font-size:14px;}"
                "QPushButton:hover{background-color:#1976D2;}"
                "QPushButton:pressed{background-color:#0D47A1;}"
            )
            btn.setAutoRepeat(False)
            btn.pressed.connect(lambda t=text: self._on_btn_pressed(t))
            btn.released.connect(self._on_btn_released)
            grid.addWidget(btn, row, col)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #ccc;")
        separator.setFixedHeight(2)
        grid.addWidget(separator, 4, 0, 1, 3)
        
        # 旋转轴控制 (RX/RY/RZ) - 3列3行布局
        rotation_label = QLabel("旋转轴 (RX/RY/RZ)")
        rotation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rotation_label.setStyleSheet("font-size:12px; color:#666; font-weight:bold;")
        grid.addWidget(rotation_label, 5, 0, 1, 3)
        
        # 旋转轴按钮布局：3列3行，每行一个轴的+/-
        rotation_directions = [
            ("RX-", 6, 0), ("RX+", 6, 2),
            ("RY-", 7, 0), ("RY+", 7, 2),
            ("RZ-", 8, 0), ("RZ+", 8, 2),
        ]
        
        rotation_axis_labels = [("RX:", 6, 1), ("RY:", 7, 1), ("RZ:", 8, 1)]
        for label_text, row, col in rotation_axis_labels:
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size:11px; color:#666; font-weight:bold;")
            grid.addWidget(lbl, row, col)

        for text, row, col in rotation_directions:
            btn = QPushButton(text)
            btn.setFixedSize(85, 45)
            btn.setStyleSheet(
                "QPushButton{background-color:#9C27B0;color:white;border:none;"
                "border-radius:6px;font-weight:bold;font-size:14px;}"
                "QPushButton:hover{background-color:#7B1FA2;}"
                "QPushButton:pressed{background-color:#6A1B9A;}"
            )
            btn.setAutoRepeat(False)
            btn.pressed.connect(lambda t=text: self._on_btn_pressed(t))
            btn.released.connect(self._on_btn_released)
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

        # 速度显示
        self._speed_label = QLabel("速度: --")
        self._speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._speed_label.setStyleSheet("color:#666; font-size:12px; margin-top:6px;")
        layout.addWidget(self._speed_label)

        hint = QLabel("速度取自机械臂控制面板设定")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color:#999; font-size:11px;")
        layout.addWidget(hint)

    # ---------- 长按逻辑 ----------
    def _on_btn_pressed(self, text: str):
        """按下按钮开始连续点动"""
        if not self.robot_service:
            return
            
        try:
            # 停止之前的定时器如果有
            if hasattr(self, '_jog_timer') and self._jog_timer.isActive():
                self._jog_timer.stop()
            
            # 直接使用按钮文本作为指令 (e.g. "X+", "RX-")
            jog_cmd = text  # 完整的指令，包括轴名和方向
            
            # 获取速度
            speed = self._get_speed()
            self._speed_label.setText(f"速度: {speed}%")
            
            # 设置速度
            self.robot_service.set_speed(speed)
            
            # 开始连续运动
            self.robot_service.start_jogging(jog_cmd)
            
        except Exception as e:
            warning(f"开始点动失败: {e}", "CAMERA_UI")

    def _on_btn_released(self):
        """释放按钮停止运动"""
        if not self.robot_service:
            return
            
        try:
            # 停止连续运动
            self.robot_service.stop_jogging()
            
            # 确保定时器停止
            if hasattr(self, '_jog_timer'):
                self._jog_timer.stop()
                
        except Exception as e:
            warning(f"停止点动失败: {e}", "CAMERA_UI")

    def _get_speed(self) -> int:
        """从机械臂控制界面获取当前速度"""
        try:
            # 尝试从主窗口找到 robot_tab 的 jog_speed_slider
            main_win = self.parent()
            for _ in range(10):  # 最多向上查找10层
                if main_win is None:
                    break
                if hasattr(main_win, 'robot_tab') and hasattr(main_win.robot_tab, 'jog_speed_slider'):
                    return main_win.robot_tab.jog_speed_slider.value()
                main_win = main_win.parent()
        except Exception:
            pass
        return 30  # 默认30%

    def _do_jog_step(self):
        """执行一步点动移动"""
        if not self._jog_axis or not self.robot_service:
            return
        try:
            speed = self._get_speed()
            self._speed_label.setText(f"速度: {speed}%")
            step_mm = max(1.0, speed / 10.0)  # 速度越大步长越大, 范围 1~10mm
            distance = step_mm * self._jog_direction
            self.robot_service.jog_move(self._jog_axis, speed, distance)
        except RuntimeError:
            # 对象已被删除
            self._jog_timer.stop()
        except Exception as e:
            # 任何其他异常也停止定时器
            warning(f"点动移动失败: {e}", "CAMERA_UI")
            self._jog_timer.stop()


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
        
        # ======= 多点位视觉伺服状态 =======
        self._servo_controller: Optional['MultiPointServo'] = None
        self._servo_teaching = False       # 是否处于示教模式
        self._servo_recipe: Optional['ServoRecipe'] = None  # 当前配方
        self._servo_std_recorded = False   # 标准点是否已记录
        self._servo_running = False        # 生产流程是否正在运行
        
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
        
        # 报告视觉算法模块导入状态
        if not VISION_ALGO_AVAILABLE and _vision_import_error:
            warning(f"视觉算法模块导入失败: {_vision_import_error}", "CAMERA_UI")
        
        # 初始化完成标志
        debug("CameraControlTab 初始化完成", "CAMERA_UI")
    
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

        # 机械臂控制浮窗按钮
        self.btn_floating_jog = QPushButton("🤖 机械臂控制")
        self.btn_floating_jog.setStyleSheet("background-color: #607D8B; color: white;")
        self.btn_floating_jog.setMinimumWidth(100)
        self.btn_floating_jog.clicked.connect(self._open_floating_jog)
        control_layout.addWidget(self.btn_floating_jog)
        
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

        # ===================== 多点位视觉伺服 =====================
        # 环境变量控制：DISABLE_VISION_SERVO=1 才禁用（默认启用）
        disable_servo_ui = os.environ.get('DISABLE_VISION_SERVO', '0').lower() in ('1', 'true', 'yes')
        enable_servo_ui = not disable_servo_ui
        
        if VISION_ALGO_AVAILABLE and enable_servo_ui:
            try:
                servo_group = QGroupBox("多点位视觉伺服 (AprilTag)")
                servo_main_layout = QVBoxLayout()

                # ---- 示教区 ----
                teach_label = QLabel("--- 示教 ---")
                teach_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                teach_label.setStyleSheet("font-weight:bold; color:#9C27B0;")
                servo_main_layout.addWidget(teach_label)

                teach_row1 = QHBoxLayout()
                self.btn_servo_start_teach = QPushButton("开始示教")
                self.btn_servo_start_teach.setStyleSheet("background-color: #9C27B0; color: white;")
                self.btn_servo_start_teach.clicked.connect(self.on_servo_start_teaching)
                teach_row1.addWidget(self.btn_servo_start_teach)

                self.btn_servo_record_std = QPushButton("记录标准点")
                self.btn_servo_record_std.setEnabled(False)
                self.btn_servo_record_std.clicked.connect(self.on_servo_record_std)
                teach_row1.addWidget(self.btn_servo_record_std)
                servo_main_layout.addLayout(teach_row1)

                teach_row2 = QHBoxLayout()
                self.btn_servo_add_point = QPushButton("添加拍照点")
                self.btn_servo_add_point.setEnabled(False)
                self.btn_servo_add_point.clicked.connect(self.on_servo_add_point)
                teach_row2.addWidget(self.btn_servo_add_point)

                self.btn_servo_finish_teach = QPushButton("完成示教")
                self.btn_servo_finish_teach.setEnabled(False)
                self.btn_servo_finish_teach.setStyleSheet("background-color: #4CAF50; color: white;")
                self.btn_servo_finish_teach.clicked.connect(self.on_servo_finish_teaching)
                teach_row2.addWidget(self.btn_servo_finish_teach)
                servo_main_layout.addLayout(teach_row2)

                # ---- 生产区 ----
                prod_label = QLabel("--- 生产 ---")
                prod_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                prod_label.setStyleSheet("font-weight:bold; color:#2196F3;")
                servo_main_layout.addWidget(prod_label)

                prod_row1 = QHBoxLayout()
                self.servo_recipe_combo = QComboBox()
                self.servo_recipe_combo.setMinimumWidth(120)
                prod_row1.addWidget(self.servo_recipe_combo)

                self.btn_servo_refresh_recipes = QPushButton("刷新")
                self.btn_servo_refresh_recipes.setMaximumWidth(50)
                self.btn_servo_refresh_recipes.clicked.connect(self._refresh_recipe_list)
                prod_row1.addWidget(self.btn_servo_refresh_recipes)
                servo_main_layout.addLayout(prod_row1)

                prod_row2 = QHBoxLayout()
                self.btn_servo_detect = QPushButton("检测偏差")
                self.btn_servo_detect.setStyleSheet("background-color: #2196F3; color: white;")
                self.btn_servo_detect.clicked.connect(self.on_servo_detect_deviation)
                prod_row2.addWidget(self.btn_servo_detect)

                self.btn_servo_execute = QPushButton("执行拍照")
                self.btn_servo_execute.setEnabled(False)
                self.btn_servo_execute.setStyleSheet("background-color: #FF9800; color: white;")
                self.btn_servo_execute.clicked.connect(self.on_servo_execute_production)
                prod_row2.addWidget(self.btn_servo_execute)
                servo_main_layout.addLayout(prod_row2)

                # ---- 状态 ----
                self.servo_status_label = QLabel("就绪")
                self.servo_status_label.setStyleSheet("color: #666; font-size: 11px;")
                servo_main_layout.addWidget(self.servo_status_label)

                servo_group.setLayout(servo_main_layout)
                layout.addWidget(servo_group)

                # 延迟加载配方列表，避免初始化时目录不存在导致错误
                # 使用弱引用确保对象销毁时不会调用
                def safe_refresh():
                    try:
                        if self and hasattr(self, 'servo_recipe_combo'):
                            self._refresh_recipe_list()
                    except RuntimeError:
                        # 对象已被删除，忽略
                        pass
                    except Exception as e:
                        warning(f"延迟加载配方列表失败: {e}", "CAMERA_UI")
                
                QTimer.singleShot(100, safe_refresh)
            except Exception as e:
                error(f"创建视觉伺服UI失败: {e}", "CAMERA_UI")
                err_label = QLabel(f"视觉伺服UI加载失败: {e}")
                err_label.setStyleSheet("color: red;")
                layout.addWidget(err_label)
        
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
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
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

    def _get_vision_config(self):
        """从配置文件读取视觉检测参数"""
        config = {
            'apriltag_size_m': 0.1,
            'aruco_size_m': 0.1,
            'depth_scale_factor': 1.0,
        }
        try:
            import yaml
            config_file = os.path.join(os.getcwd(), "config", "system.yaml")
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    vision = data.get('vision', {})
                    config['apriltag_size_m'] = vision.get('apriltag_size_m', vision.get('tag_size_m', 0.1))
                    config['aruco_size_m'] = vision.get('aruco_size_m', vision.get('tag_size_m', 0.1))
                    config['depth_scale_factor'] = vision.get('depth_scale_factor', 1.0)
                    info(f"Vision配置: AprilTag={config['apriltag_size_m']*1000:.1f}mm, ArUco={config['aruco_size_m']*1000:.1f}mm", "CAMERA_UI")
        except Exception as e:
            warning(f"加载vision配置失败: {e}，使用默认值", "CAMERA_UI")
        return config

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
        
        # 从配置读取tag_size
        vision_config = self._get_vision_config()
        tag_size = vision_config['apriltag_size_m']
            
        try:
            self.at_detector = AprilTagDetector(tag_size_m=tag_size, camera_matrix=mtx, dist_coeffs=dist)
            return self.at_detector
        except Exception as e:
            error(f"初始化AprilTagDetector失败: {e}", "CAMERA_UI")
            return None

    def _get_aruco_detector(self, dict_name: str = "DICT_6X6_50"):
        """延迟加载或获取ArUco检测器"""
        detector_key = f'aruco_detector_{dict_name}'
        if hasattr(self, detector_key) and getattr(self, detector_key):
            return getattr(self, detector_key)
        
        # 尝试加载相机内参
        mtx, dist = self._load_camera_calibration()
        
        # 从配置读取marker_size
        vision_config = self._get_vision_config()
        marker_size = vision_config['aruco_size_m']
        
        try:
            detector = ArUcoDetector(
                camera_matrix=mtx, 
                dist_coeffs=dist, 
                marker_size=marker_size, 
                dictionary_name=dict_name
            )
            setattr(self, detector_key, detector)
            info(f"已创建ArUco检测器: {dict_name}, marker_size={marker_size*1000:.1f}mm", "CAMERA_UI")
            return detector
        except Exception as e:
            error(f"初始化ArUcoDetector失败: {e}", "CAMERA_UI")
            return None
    
    def _load_camera_calibration(self):
        """加载相机标定参数"""
        calib_file = os.path.join(os.getcwd(), "AprilTagInterface", "calibration", "realsense_calib.npz")
        mtx = None
        dist = None
        
        if os.path.exists(calib_file):
            try:
                data = np.load(calib_file)
                mtx = data['mtx']
                dist = data.get('dist', np.zeros(4))
            except Exception as e:
                warning(f"加载标定文件失败: {e}", "CAMERA_UI")
        
        if mtx is None:
            # 默认内参 (640x480)
            mtx = np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]], dtype=np.float32)
            dist = np.zeros(4)
        
        return mtx, dist
    
    def _detect_marker(self, frame, marker_type: str = "apriltag", aruco_dict: str = "DICT_6X6_50"):
        """
        通用标记检测方法 - 支持 AprilTag 和 ArUco
        
        Args:
            frame: 图像帧
            marker_type: 标记类型 ("apriltag" 或 "aruco")
            aruco_dict: ArUco字典名称 (仅当marker_type为aruco时有效)
        Returns:
            检测结果列表，格式与 AprilTagDetector.detect() 相同
        """
        if marker_type == "apriltag":
            detector = self._get_detector()
            if detector:
                return detector.detect(frame)
        elif marker_type == "aruco":
            detector = self._get_aruco_detector(aruco_dict)
            if detector:
                return detector.detect(frame)
        else:
            # 自动检测：先尝试AprilTag，再尝试ArUco (6x6系列)
            detector = self._get_detector()
            if detector:
                results = detector.detect(frame)
                if results:
                    return results
            
            # AprilTag未检测到，尝试ArUco 6x6系列
            for dict_name in ["DICT_6X6_50", "DICT_6X6_100", "DICT_6X6_250", "DICT_6X6_1000"]:
                aruco_det = self._get_aruco_detector(dict_name)
                if aruco_det:
                    results = aruco_det.detect(frame)
                    if results:
                        info(f"使用ArUco {dict_name} 检测到标记", "CAMERA_UI")
                        return results
        
        return []

    def _detect_marker_averaged(self, num_frames: int = 5, interval_ms: int = 100, 
                                  marker_type: str = "auto", aruco_dict: str = "DICT_6X6_50"):
        """
        多帧检测平均 - 用于降低位姿估计噪声
        
        Args:
            num_frames: 采集帧数 (默认5)
            interval_ms: 帧间隔毫秒数 (默认100ms)
            marker_type: 标记类型
            aruco_dict: ArUco字典名
            
        Returns:
            平均后的检测结果列表，与 _detect_marker 格式相同
        """
        import time
        
        if not self.current_camera:
            return []
        
        all_detections = []  # 每帧检测到的所有标记: [{id: [det1, det2, ...]}, ...]
        
        for i in range(num_frames):
            frame = None
            
            # 尝试获取新帧
            if hasattr(self.current_camera, 'camera_driver') and self.current_camera.camera_driver:
                try:
                    frame = self.current_camera.camera_driver.capture_image()
                except Exception:
                    pass
            
            if frame is None and self.current_camera.current_frame is not None:
                frame = self.current_camera.current_frame.copy()
            
            if frame is not None:
                results = self._detect_marker(frame, marker_type, aruco_dict)
                if results:
                    # 按ID分组存储
                    frame_dets = {}
                    for det in results:
                        det_id = det.get('id', 0)
                        if det_id not in frame_dets:
                            frame_dets[det_id] = []
                        frame_dets[det_id].append(det)
                    all_detections.append(frame_dets)
            
            # 等待下一帧（除了最后一帧）
            if i < num_frames - 1:
                time.sleep(interval_ms / 1000.0)
        
        if not all_detections:
            return []
        
        # 计算每个ID的平均检测结果
        avg_results = []
        
        # 找出所有检测到的ID
        all_ids = set()
        for frame_dets in all_detections:
            all_ids.update(frame_dets.keys())
        
        for tag_id in all_ids:
            # 收集该ID在所有帧中的检测
            id_dets = []
            for frame_dets in all_detections:
                if tag_id in frame_dets:
                    id_dets.extend(frame_dets[tag_id])
            
            if not id_dets:
                continue
            
            # 计算平均值
            avg_tvec = np.mean([np.array(d['tvec']) for d in id_dets], axis=0)
            avg_rvec = np.mean([np.array(d['rvec']) for d in id_dets], axis=0)
            avg_euler = np.mean([np.array(d['euler']) for d in id_dets], axis=0)
            
            # 计算平均中心点
            centers = [d.get('center') for d in id_dets if d.get('center') is not None]
            avg_center = np.mean(centers, axis=0) if centers else None
            
            # 计算平均距离
            distances = [d.get('distance', 0) for d in id_dets]
            avg_distance = np.mean(distances) if distances else 0
            
            # 取第一个检测的marker_type和corners（这些不需要平均）
            marker_type_result = id_dets[0].get('marker_type', 'apriltag')
            corners = id_dets[0].get('corners', None)
            
            avg_results.append({
                'id': tag_id,
                'tvec': avg_tvec,
                'rvec': avg_rvec,
                'euler': avg_euler,
                'center': avg_center,
                'distance': avg_distance,
                'marker_type': marker_type_result,
                'corners': corners,
                'averaged_frames': len(id_dets)  # 记录平均了多少帧
            })
        
        if avg_results:
            info(f"多帧检测: {num_frames}帧，检测到{len(avg_results)}个标记", "CAMERA_UI")
        
        return avg_results

    def _normalize_angle(self, angle_deg: float) -> float:
        """
        将角度归一化到 [-180, 180] 范围内
        
        这用于处理角度环绕问题，例如：
        - 359.7° 实际应为 -0.3°
        - -359.7° 实际应为 0.3°
        
        Args:
            angle_deg: 输入角度 (度)
        Returns:
            归一化后的角度 [-180, 180]
        """
        while angle_deg > 180:
            angle_deg -= 360
        while angle_deg < -180:
            angle_deg += 360
        return angle_deg

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
            
        # 2. 计算偏差 (Cam系) - 完整6DOF
        # 这里的偏差是指：物体相对于标准位置移动了多少
        # Tag在Cam系下坐标：T_c_t
        # std: T_c_t_std
        # curr: T_c_t_cur
        # 移动量 D = T_c_t_cur - T_c_t_std
        
        tvec_std = self.std_tag_pose['tvec']
        tvec_cur = curr_res['tvec']
        
        # 单位: 米 -> 转毫米 (完整XYZ)
        dx_mm = (tvec_cur[0] - tvec_std[0]) * 1000.0 
        dy_mm = (tvec_cur[1] - tvec_std[1]) * 1000.0
        dz_mm = (tvec_cur[2] - tvec_std[2]) * 1000.0  # Z方向偏差
        
        # 角度偏差 (完整RX/RY/RZ)
        # euler 顺序是 [rx, ry, rz] (XYZ欧拉角)
        euler_std = self.std_tag_pose['euler']
        euler_cur = curr_res['euler']
        drx_deg = self._normalize_angle(euler_cur[0] - euler_std[0])
        dry_deg = self._normalize_angle(euler_cur[1] - euler_std[1])
        drz_deg = self._normalize_angle(euler_cur[2] - euler_std[2])
        
        # 打印偏差 (完整6DOF)
        info(f"视觉偏差计算 (6DOF): dx={dx_mm:.2f}mm, dy={dy_mm:.2f}mm, dz={dz_mm:.2f}mm, drx={drx_deg:.2f}°, dry={dry_deg:.2f}°, drz={drz_deg:.2f}°", "CAMERA_UI")
        
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
            # 6DOF偏差: [dx, dy, dz, drx, dry, drz] - 支持完整空间纠偏
            
            # robot_pose单位确认：roboarm通常使用 rad。is_degree参数需要确认
            # manual_correction_tool默认接受度数/弧度混合？
            # 我们的 elite_pose_to_matrix 函数，如果 input pose rx,ry,rz 是 rad，则 is_degree=False
            
            # log显示 robot_service.get_position() 返回的是 [x, y, z, rx, ry, rz] 且 rx,ry,rz 为度数
            # 必须传给 calculate_correction 的 is_degree=True
            
            new_pose = calculate_correction(
                current_robot_pose, 
                [dx_mm, dy_mm, dz_mm, drx_deg, dry_deg, drz_deg],  # 完整6DOF偏差
                T_hand_eye, 
                is_degree=True
            )
            
            confirm_msg = (f"计算完成。\n"
                           f"偏差: dx={dx_mm:.1f}, dy={dy_mm:.1f}, dz={dz_mm:.1f}\n"
                           f"      drx={drx_deg:.2f}°, dry={dry_deg:.2f}°, drz={drz_deg:.2f}°\n"
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

    # ===================== 浮动机械臂控制窗口 =====================

    def _open_floating_jog(self):
        """打开/激活浮动机械臂控制窗口"""
        try:
            if not self.robot_service:
                QMessageBox.warning(self, "错误", "未连接机械臂服务")
                return
            if hasattr(self, '_floating_jog_dlg') and self._floating_jog_dlg and self._floating_jog_dlg.isVisible():
                self._floating_jog_dlg.activateWindow()
                return
            self._floating_jog_dlg = FloatingJogDialog(self.robot_service, parent=self)
            self._floating_jog_dlg.show()
        except Exception as e:
            error(f"打开机械臂控制窗口失败: {e}", "CAMERA_UI")
            QMessageBox.critical(self, "错误", f"无法打开机械臂控制窗口: {e}")

    # ===================== 多点位视觉伺服 — 辅助 =====================

    def _refresh_recipe_list(self):
        """刷新配方下拉列表"""
        if not VISION_ALGO_AVAILABLE:
            return
        try:
            if not hasattr(self, 'servo_recipe_combo'):
                return
            self.servo_recipe_combo.clear()
            # 确保目录存在
            os.makedirs(RECIPE_DIR, exist_ok=True)
            recipes = list_recipes()
            for fname in recipes:
                self.servo_recipe_combo.addItem(fname.replace('.json', ''), fname)
            if not recipes:
                self.servo_recipe_combo.addItem("(无配方)", "")
        except Exception as e:
            warning(f"刷新配方列表失败: {e}", "CAMERA_UI")

    def _set_servo_status(self, text: str, color: str = "#666"):
        """更新伺服状态标签"""
        if hasattr(self, 'servo_status_label'):
            self.servo_status_label.setText(text)
            self.servo_status_label.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _set_teach_buttons(self, start=True, record_std=False, add_point=False, finish=False):
        """批量设置示教阶段按钮状态"""
        if hasattr(self, 'btn_servo_start_teach'):
            self.btn_servo_start_teach.setEnabled(start)
        if hasattr(self, 'btn_servo_record_std'):
            self.btn_servo_record_std.setEnabled(record_std)
        if hasattr(self, 'btn_servo_add_point'):
            self.btn_servo_add_point.setEnabled(add_point)
        if hasattr(self, 'btn_servo_finish_teach'):
            self.btn_servo_finish_teach.setEnabled(finish)

    # ===================== 多点位视觉伺服 — 示教流程 =====================

    def on_servo_start_teaching(self):
        """开始示教：创建控制器和空配方"""
        name, ok = QInputDialog.getText(self, "新配方", "请输入配方名称:",
                                        text=f"配方_{time.strftime('%m%d_%H%M')}")
        if not ok or not name.strip():
            return

        try:
            self._servo_controller = MultiPointServo()
            self._servo_recipe = self._servo_controller.start_teaching(name.strip())
            self._servo_teaching = True
            self._servo_std_recorded = False

            self._set_teach_buttons(start=False, record_std=True, add_point=False, finish=False)
            self._set_servo_status(f"示教中：请移动到标准位置后点击「记录标准点」", "#9C27B0")
            info(f"开始示教配方: {name}", "CAMERA_UI")
        except Exception as e:
            error(f"开始示教失败: {e}", "CAMERA_UI")
            QMessageBox.critical(self, "错误", f"初始化失败: {e}")

    def on_servo_record_std(self):
        """示教阶段 — 记录标准点"""
        if not self._servo_teaching or not self._servo_controller:
            return

        # 检查相机
        if not self.current_camera or self.current_camera.current_frame is None:
            QMessageBox.warning(self, "错误", "请先连接相机并开启预览")
            return

        # 检测 AprilTag
        detector = self._get_detector()
        if not detector:
            QMessageBox.critical(self, "错误", "无法初始化视觉检测器")
            return

        results = detector.detect(self.current_camera.current_frame)
        if not results:
            QMessageBox.warning(self, "未检测到", "当前画面未找到 AprilTag")
            return

        tag_res = results[0]

        # 获取机械臂位姿
        if not self.robot_service:
            QMessageBox.warning(self, "错误", "未连接机械臂")
            return
        robot_pose = self.robot_service.get_position()
        if robot_pose is None:
            QMessageBox.warning(self, "错误", "获取机械臂位姿失败")
            return

        # 记录
        ok = self._servo_controller.record_standard_point(robot_pose, tag_res)
        if not ok:
            QMessageBox.warning(self, "错误", "记录标准点失败")
            return

        self._servo_std_recorded = True
        
        # 保存标准点照片到配方目录
        recipe_name = self._servo_recipe.name if self._servo_recipe else "unknown"
        snap = self._save_recipe_standard_photo(recipe_name)

        self._set_teach_buttons(start=False, record_std=False, add_point=True, finish=True)
        self._set_servo_status(
            f"标准点已记录 (Tag#{tag_res['id']}, d={tag_res['distance']:.3f}m)。请移动到第一个拍照点位。",
            "#4CAF50"
        )
        # 详细日志：标准点位姿
        info(f"========== 标准点记录 ==========", "CAMERA_UI")
        info(f"  Tag ID: {tag_res['id']}, 距离: {tag_res['distance']:.3f}m", "CAMERA_UI")
        info(f"  标准点机械臂位姿 (位姿1):", "CAMERA_UI")
        info(f"    X={robot_pose[0]:.3f} Y={robot_pose[1]:.3f} Z={robot_pose[2]:.3f} mm", "CAMERA_UI")
        info(f"    RX={robot_pose[3]:.3f} RY={robot_pose[4]:.3f} RZ={robot_pose[5]:.3f} deg", "CAMERA_UI")
        info(f"=================================", "CAMERA_UI")

    def on_servo_add_point(self):
        """示教阶段 — 添加普通拍照点位"""
        if not self._servo_teaching or not self._servo_controller or not self._servo_std_recorded:
            return

        if not self.robot_service:
            QMessageBox.warning(self, "错误", "未连接机械臂")
            return

        robot_pose = self.robot_service.get_position()
        if robot_pose is None:
            QMessageBox.warning(self, "错误", "获取机械臂位姿失败")
            return

        n = len(self._servo_recipe.photo_points) + 1
        default_name = f"拍照点{n}"
        name, ok = QInputDialog.getText(self, "点位名称", "请输入拍照点名称:", text=default_name)
        if not ok or not name.strip():
            return

        # 保存示教照片到配方的teaching目录（使用数字编号避免中文）
        recipe_name = self._servo_recipe.name if self._servo_recipe else "unknown"
        snap = self._save_recipe_teaching_photo(recipe_name, name.strip(), point_index=n)

        # 检测当前帧中的标记 (使用多帧平均降低噪声)，保存示教阶段的tag_data
        tag_data = None
        if self.current_camera:
            try:
                # 使用多帧平均检测 (5帧，间隔100ms) - 大幅降低位姿估计噪声
                self._set_servo_status(f"正在采集多帧数据...", "#FF9800")
                QApplication.processEvents()  # 更新UI
                
                results = self._detect_marker_averaged(num_frames=5, interval_ms=100, marker_type="auto")
                if results:
                    # 取第一个检测到的标签
                    det = results[0]
                    marker_type = det.get('marker_type', 'apriltag')
                    avg_frames = det.get('averaged_frames', 1)
                    tag_data = {
                        'id': int(det['id']),
                        'tvec': det['tvec'].tolist() if hasattr(det['tvec'], 'tolist') else list(det['tvec']),
                        'rvec': det['rvec'].tolist() if hasattr(det['rvec'], 'tolist') else list(det['rvec']),
                        'euler': [float(x) for x in det['euler']],
                        'center': [float(x) for x in det.get('center', [0, 0])] if det.get('center') is not None else [0.0, 0.0],
                        'distance': float(det.get('distance', 0)),
                        'marker_type': str(marker_type)
                    }
                    info(f"  示教点 [{name}] 标记检测 ({marker_type}, {avg_frames}帧平均): ID={det['id']}, X={det['tvec'][0]:.3f}m, Y={det['tvec'][1]:.3f}m, Z={det['tvec'][2]:.3f}m", "CAMERA_UI")
                else:
                    info(f"  示教点 [{name}] 未检测到AprilTag/ArUco标记（可能不在视野内）", "CAMERA_UI")
            except Exception as e:
                warning(f"示教点标记检测失败: {e}", "CAMERA_UI")

        count = self._servo_controller.add_photo_point(name.strip(), robot_pose, snap, tag_data)

        self._set_servo_status(f"已添加 {count} 个拍照点位。继续添加或点击「完成示教」。", "#9C27B0")
        # 详细日志：拍照点位姿
        info(f"========== 添加拍照点 [{name}] ==========", "CAMERA_UI")
        info(f"  示教时机械臂位姿:", "CAMERA_UI")
        info(f"    X={robot_pose[0]:.3f} Y={robot_pose[1]:.3f} Z={robot_pose[2]:.3f} mm", "CAMERA_UI")
        info(f"    RX={robot_pose[3]:.3f} RY={robot_pose[4]:.3f} RZ={robot_pose[5]:.3f} deg", "CAMERA_UI")
        info(f"  当前总点位数: {count}", "CAMERA_UI")
        info(f"=========================================", "CAMERA_UI")

    def on_servo_finish_teaching(self):
        """示教阶段 — 完成示教"""
        if not self._servo_teaching or not self._servo_controller:
            return

        if not self._servo_std_recorded:
            QMessageBox.warning(self, "错误", "标准点未记录")
            return

        if not self._servo_recipe.photo_points:
            QMessageBox.warning(self, "错误", "至少添加一个拍照点位")
            return

        try:
            recipe = self._servo_controller.finish_teaching()
            self._servo_teaching = False

            # 恢复按钮
            self._set_teach_buttons(start=True, record_std=False, add_point=False, finish=False)
            self._refresh_recipe_list()

            # 自动选中新配方
            idx = self.servo_recipe_combo.findData(f"{recipe.id}.json")
            if idx >= 0:
                self.servo_recipe_combo.setCurrentIndex(idx)

            self._set_servo_status(
                f"示教完成: {recipe.name} ({len(recipe.photo_points)}个点位)", "#4CAF50"
            )
            
            # 机械臂回到标准点位姿（位姿1）
            std_pose = recipe.std_robot_pose
            if std_pose and self.robot_service:
                info(f"示教完成，机械臂回到标准点位姿: {np.round(std_pose, 2)}", "CAMERA_UI")
                self._set_servo_status("正在回到标准点...", "#FF9800")
                try:
                    self.robot_service.move_to(*std_pose)
                    # 延迟后更新状态
                    QTimer.singleShot(3000, lambda: self._set_servo_status(
                        f"示教完成: {recipe.name} ({len(recipe.photo_points)}个点位)，已回到标准点", "#4CAF50"
                    ))
                except Exception as move_err:
                    warning(f"回到标准点失败: {move_err}", "CAMERA_UI")

            QMessageBox.information(
                self, "示教完成",
                f"配方「{recipe.name}」已保存。\n"
                f"包含 {len(recipe.photo_points)} 个拍照点位。\n"
                f"机械臂将回到标准点位姿。\n"
                f"请切换到「生产」模式使用。"
            )
        except Exception as e:
            error(f"完成示教失败: {e}", "CAMERA_UI")
            QMessageBox.critical(self, "错误", f"完成示教失败: {e}")

    # ===================== 多点位视觉伺服 — 生产流程 =====================

    def on_servo_detect_deviation(self):
        """生产阶段 — 加载配方并在标准位置检测偏差"""
        # 加载选中的配方
        fname = self.servo_recipe_combo.currentData()
        if not fname:
            QMessageBox.warning(self, "错误", "请先选择一个配方")
            return

        filepath = os.path.join(RECIPE_DIR, fname)
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "错误", f"配方文件不存在: {fname}")
            return

        try:
            if self._servo_controller is None:
                self._servo_controller = MultiPointServo()
            self._servo_controller.load(filepath)
            recipe = self._servo_controller.current_recipe
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载配方失败: {e}")
            return

        # 提示用户：机械臂应在标准位置附近
        reply = QMessageBox.question(
            self, "检测偏差",
            f"配方: {recipe.name}\n"
            f"包含 {len(recipe.photo_points)} 个拍照点位\n\n"
            f"请确认机械臂已在标准位置附近，然后点击「是」开始检测。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 检测 AprilTag
        if not self.current_camera or self.current_camera.current_frame is None:
            QMessageBox.warning(self, "错误", "请先连接相机并开启预览")
            return

        detector = self._get_detector()
        if not detector:
            QMessageBox.critical(self, "错误", "无法初始化视觉检测器")
            return

        results = detector.detect(self.current_camera.current_frame)
        if not results:
            QMessageBox.warning(self, "未检测到", "当前画面未找到 AprilTag")
            return

        # 尝试匹配标准点 tag id
        std_tag_id = recipe.std_tag_data.get('id', 0) if recipe.std_tag_data else 0
        tag_res = next((r for r in results if r['id'] == std_tag_id), None)
        if tag_res is None:
            tag_res = results[0]
            warning(f"未找到 ID={std_tag_id} 的 Tag，使用第一个检测结果 (ID={tag_res['id']})", "CAMERA_UI")

        # 获取机械臂当前位姿
        if not self.robot_service:
            QMessageBox.warning(self, "错误", "未连接机械臂")
            return
        robot_pose = self.robot_service.get_position()
        if robot_pose is None:
            QMessageBox.warning(self, "错误", "获取机械臂位姿失败")
            return

        # 计算新位姿
        try:
            new_poses = self._servo_controller.compute_new_poses(robot_pose, tag_res)
        except Exception as e:
            QMessageBox.critical(self, "计算错误", f"偏差传播失败: {e}")
            return

        # 计算偏差数据（必须先计算才能保存）
        std_T_old = np.array(recipe.T_base_tag_std)
        from multi_point_servo import compute_T_base_tag
        from scipy.spatial.transform import Rotation as R
        T_new = compute_T_base_tag(
            robot_pose, np.array(tag_res['tvec']),
            np.array(tag_res['rvec']), self._servo_controller.T_flange_cam, True
        )
        delta_t = T_new[:3, 3] - std_T_old[:3, 3]
        
        # 计算旋转偏差 (从旋转矩阵提取欧拉角)
        R_old = std_T_old[:3, :3]
        R_new = T_new[:3, :3]
        R_delta = R_new @ R_old.T  # 相对旋转
        try:
            delta_euler = R.from_matrix(R_delta).as_euler('xyz', degrees=True)
        except:
            delta_euler = [0, 0, 0]

        # 保存计算结果到临时属性供执行使用
        self._servo_new_poses = new_poses
        self._servo_recipe = recipe
        
        # 保存偏差数据供生产拍照时使用 (完整6维度)
        self._servo_tag_deviation = {
            'tag_delta': [delta_t[0], delta_t[1], delta_t[2]],       # Tag位置偏差 XYZ (mm)
            'tag_rot_delta': list(delta_euler),                       # Tag旋转偏差 RX,RY,RZ (deg)
        }
        
        # 保存生产阶段标准点照片 (保存到 production/standard/)
        self._save_recipe_standard_photo(recipe.name, is_production=True)
        
        # 构建原始示教位姿的映射 (用于偏差报告)
        self._servo_teaching_poses = {}
        for pp in recipe.photo_points:
            self._servo_teaching_poses[pp.name] = list(pp.pose)

        # 详细日志
        info(f"========== 偏差计算结果 ==========", "CAMERA_UI")
        info(f"  当前机械臂位姿 (标准位置):", "CAMERA_UI")
        info(f"    X={robot_pose[0]:.3f} Y={robot_pose[1]:.3f} Z={robot_pose[2]:.3f} mm", "CAMERA_UI")
        info(f"    RX={robot_pose[3]:.3f} RY={robot_pose[4]:.3f} RZ={robot_pose[5]:.3f} deg", "CAMERA_UI")
        info(f"  原标准点位姿:", "CAMERA_UI")
        std_pose = recipe.std_robot_pose
        info(f"    X={std_pose[0]:.3f} Y={std_pose[1]:.3f} Z={std_pose[2]:.3f} mm", "CAMERA_UI")
        info(f"    RX={std_pose[3]:.3f} RY={std_pose[4]:.3f} RZ={std_pose[5]:.3f} deg", "CAMERA_UI")
        info(f"  Tag位置偏差 (新-旧):", "CAMERA_UI")
        info(f"    dX={delta_t[0]:.3f} dY={delta_t[1]:.3f} dZ={delta_t[2]:.3f} mm", "CAMERA_UI")
        info(f"  Tag旋转偏差 (欧拉角):", "CAMERA_UI")
        info(f"    dRX={delta_euler[0]:.3f} dRY={delta_euler[1]:.3f} dRZ={delta_euler[2]:.3f} deg", "CAMERA_UI")
        info(f"  --------- 新计算的拍照点位姿 ---------", "CAMERA_UI")
        for pp in recipe.photo_points:
            info(f"  [{pp.name}] 原示教位姿:", "CAMERA_UI")
            info(f"    X={pp.pose[0]:.3f} Y={pp.pose[1]:.3f} Z={pp.pose[2]:.3f} mm", "CAMERA_UI")
            info(f"    RX={pp.pose[3]:.3f} RY={pp.pose[4]:.3f} RZ={pp.pose[5]:.3f} deg", "CAMERA_UI")
        for name, pose in new_poses:
            info(f"  [{name}] 新计算位姿:", "CAMERA_UI")
            info(f"    X={pose[0]:.3f} Y={pose[1]:.3f} Z={pose[2]:.3f} mm", "CAMERA_UI")
            info(f"    RX={pose[3]:.3f} RY={pose[4]:.3f} RZ={pose[5]:.3f} deg", "CAMERA_UI")
        info(f"=========================================", "CAMERA_UI")
        
        summary = (f"检测完成 (Tag#{tag_res['id']})\n"
                   f"位置偏差: dX={delta_t[0]:.2f} dY={delta_t[1]:.2f} dZ={delta_t[2]:.2f} mm\n"
                   f"旋转偏差: dRX={delta_euler[0]:.2f} dRY={delta_euler[1]:.2f} dRZ={delta_euler[2]:.2f} deg\n\n")
        for name, pose in new_poses:
            summary += f"  {name}: [{', '.join(f'{v:.2f}' for v in pose)}]\n"

        self.btn_servo_execute.setEnabled(True)
        self._set_servo_status(f"偏差已计算，就绪执行 ({len(new_poses)} 点位)", "#FF9800")
        info(f"偏差计算完成: {len(new_poses)} 个新位姿", "CAMERA_UI")

        QMessageBox.information(self, "偏差计算结果", summary)

    def on_servo_execute_production(self):
        """生产阶段 — 依次移动到新位姿并拍照"""
        if not hasattr(self, '_servo_new_poses') or not self._servo_new_poses:
            QMessageBox.warning(self, "错误", "请先检测偏差")
            return

        if not self.robot_service:
            QMessageBox.warning(self, "错误", "未连接机械臂")
            return

        reply = QMessageBox.question(
            self, "执行确认",
            f"将依次移动到 {len(self._servo_new_poses)} 个拍照点位并拍照。\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._servo_running = True
        self.btn_servo_execute.setEnabled(False)
        self.btn_servo_detect.setEnabled(False)

        # 使用 QTimer 逐步执行以保持 UI 响应
        self._servo_exec_index = 0
        self._servo_exec_poses = list(self._servo_new_poses)
        self._servo_exec_timer = QTimer()
        self._servo_exec_timer.setSingleShot(True)
        self._servo_exec_timer.timeout.connect(self._servo_exec_next_point)
        self._servo_exec_next_point()

    def _servo_exec_next_point(self):
        """执行下一个拍照点位（定时器回调）"""
        idx = self._servo_exec_index
        poses = self._servo_exec_poses

        if idx >= len(poses):
            # 全部完成 — 回到标准点位姿（位姿1）
            self._servo_running = False
            self.btn_servo_detect.setEnabled(True)
            self.btn_servo_execute.setEnabled(False)
            
            # 获取标准点位姿并回去
            std_pose = None
            if self._servo_recipe and self._servo_recipe.std_robot_pose:
                std_pose = self._servo_recipe.std_robot_pose
            
            if std_pose and self.robot_service:
                self._set_servo_status("拍照完成，正在回到标准点...", "#FF9800")
                info(f"生产拍照完成，机械臂回到标准点: {np.round(std_pose, 2)}", "CAMERA_UI")
                try:
                    self.robot_service.move_to(*std_pose)
                    # 延迟后更新状态
                    QTimer.singleShot(3000, lambda: self._set_servo_status(
                        f"生产拍照完成 ({len(poses)} 个点位)，已回到标准点", "#4CAF50"
                    ))
                except Exception as move_err:
                    warning(f"回到标准点失败: {move_err}", "CAMERA_UI")
                    self._set_servo_status(f"生产拍照完成 ({len(poses)} 个点位)，回到标准点失败", "#f44336")
            else:
                self._set_servo_status(f"生产拍照完成 ({len(poses)} 个点位)", "#4CAF50")
            
            info(f"生产拍照全部完成: {len(poses)} 个点位", "CAMERA_UI")
            QMessageBox.information(self, "完成", f"已完成 {len(poses)} 个点位拍照\n机械臂已回到标准点位姿。")
            self._servo_new_poses = None
            return

        name, pose = poses[idx]
        self._set_servo_status(f"移动中: {name} ({idx+1}/{len(poses)})", "#FF9800")
        info(f"移动到 {name}: {np.round(pose, 2)}", "CAMERA_UI")

        try:
            self.robot_service.move_to(*pose)
            # 保存目标位姿用于位置检测
            self._servo_target_pose = pose
            self._servo_current_name = name
            self._servo_exec_index = idx + 1
            self._servo_move_start_time = time.time()
            
            # 启动位置检测定时器（每300ms检查一次）
            if not hasattr(self, '_servo_reach_timer'):
                self._servo_reach_timer = QTimer()
                self._servo_reach_timer.timeout.connect(self._servo_check_reached)
            self._servo_reach_timer.start(300)
        except Exception as e:
            error(f"移动到 {name} 失败: {e}", "CAMERA_UI")
            self._servo_running = False
            self.btn_servo_detect.setEnabled(True)
            QMessageBox.critical(self, "移动失败", f"移动到 {name} 失败: {e}")

    def _servo_check_reached(self):
        """轮询检查机械臂是否到达目标位置"""
        import time
        import math
        
        if not hasattr(self, '_servo_target_pose') or self._servo_target_pose is None:
            self._servo_reach_timer.stop()
            return
        
        target = self._servo_target_pose
        name = getattr(self, '_servo_current_name', '')
        start_time = getattr(self, '_servo_move_start_time', time.time())
        
        # 获取当前位置
        curr_pos = self.robot_service.get_position() if self.robot_service else None
        
        if curr_pos:
            # 计算位置误差 (仅xyz)
            dx = curr_pos[0] - target[0]
            dy = curr_pos[1] - target[1]
            dz = curr_pos[2] - target[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            
            # 到达判定: 距离 < 2mm
            if dist < 2.0:
                self._servo_reach_timer.stop()
                self._set_servo_status(f"已到达 {name}，等待稳定后拍照...", "#2196F3")
                info(f"已到达 {name}，距离误差={dist:.2f}mm，等待1秒后拍照", "CAMERA_UI")
                # 等待 1 秒后拍照
                QTimer.singleShot(1000, self._servo_take_photo_and_continue)
                return
        
        # 超时检测 (15秒)
        elapsed = time.time() - start_time
        if elapsed > 15.0:
            self._servo_reach_timer.stop()
            warning(f"等待到达 {name} 超时 ({elapsed:.1f}s)，强制拍照", "CAMERA_UI")
            self._set_servo_status(f"等待 {name} 超时，强制拍照...", "#f44336")
            QTimer.singleShot(500, self._servo_take_photo_and_continue)
    
    def _servo_take_photo_and_continue(self):
        """拍照并继续下一个点位"""
        idx = self._servo_exec_index - 1  # 当前已完成移动的点位
        if idx < len(self._servo_exec_poses):
            name = self._servo_exec_poses[idx][0]
            pose = self._servo_exec_poses[idx][1]
            
            # 使用配方目录结构保存生产照片（使用数字编号避免中文）
            recipe_name = self._servo_recipe.name if self._servo_recipe else "unknown"
            snap = self._save_recipe_production_photo(recipe_name, name, point_index=idx+1)
            
            # 获取示教位姿以计算纠偏后偏差
            teaching_pose = self._servo_teaching_poses.get(name, [0]*6) if hasattr(self, '_servo_teaching_poses') else [0]*6
            
            # 获取纠偏前偏差 (标准点Tag偏差 - 在检测标准点时计算) - 完整6维
            tag_deviation = getattr(self, '_servo_tag_deviation', {})
            tag_delta = tag_deviation.get('tag_delta', [0, 0, 0])
            tag_rot_delta = tag_deviation.get('tag_rot_delta', [0, 0, 0])
            pre_delta_x = tag_delta[0]   # 纠偏前X偏差
            pre_delta_y = tag_delta[1]   # 纠偏前Y偏差
            pre_delta_z = tag_delta[2]   # 纠偏前Z偏差
            pre_delta_rx = tag_rot_delta[0]  # 纠偏前RX偏差
            pre_delta_ry = tag_rot_delta[1]  # 纠偏前RY偏差
            pre_delta_rz = tag_rot_delta[2]  # 纠偏前RZ偏差
            
            # 检测当前帧标记，计算纠偏后偏差 (与示教点的tag_data比较) - 完整6维
            post_delta_x, post_delta_y, post_delta_z = 0.0, 0.0, 0.0
            post_delta_rx, post_delta_ry, post_delta_rz = 0.0, 0.0, 0.0
            current_tag_data = None
            teaching_tag_data = None
            
            # 从配方中获取此点位的示教tag_data
            if self._servo_recipe:
                for pp in self._servo_recipe.photo_points:
                    if pp.name == name and pp.tag_data:
                        teaching_tag_data = pp.tag_data
                        break
            
            # 检测当前帧中的标记 (使用多帧平均降低噪声)
            if self.current_camera:
                try:
                    # 使用多帧平均检测 (5帧，间隔100ms) - 与示教阶段保持一致
                    results = self._detect_marker_averaged(num_frames=5, interval_ms=100, marker_type="auto")
                    if results:
                        det = results[0]
                        avg_frames = det.get('averaged_frames', 1)
                        current_tag_data = {
                            'tvec': det['tvec'].tolist() if hasattr(det['tvec'], 'tolist') else list(det['tvec']),
                            'euler': [float(x) for x in det['euler']],
                            'marker_type': det.get('marker_type', 'apriltag'),
                            'id': det.get('id', 0),
                            'center': [float(x) for x in det.get('center', [0, 0])] if det.get('center') is not None else None,
                            'corners': det.get('corners', None),
                            'averaged_frames': avg_frames
                        }
                        
                        marker_info = f"{current_tag_data['marker_type']} ID={current_tag_data['id']} ({avg_frames}帧平均)"
                        
                        # 如果有示教点的tag_data，计算纠偏后偏差 (完整6维)
                        if teaching_tag_data:
                            teach_tvec = teaching_tag_data.get('tvec', [0, 0, 0])
                            teach_euler = teaching_tag_data.get('euler', [0, 0, 0])
                            curr_tvec = current_tag_data['tvec']
                            curr_euler = current_tag_data['euler']
                            
                            # 纠偏后偏差 = 生产Tag位置 - 示教Tag位置
                            # 位置偏差 (单位: mm)
                            post_delta_x = (curr_tvec[0] - teach_tvec[0]) * 1000  # m -> mm
                            post_delta_y = (curr_tvec[1] - teach_tvec[1]) * 1000
                            post_delta_z = (curr_tvec[2] - teach_tvec[2]) * 1000
                            # 旋转偏差 (单位: deg) - 带角度归一化
                            post_delta_rx = self._normalize_angle(curr_euler[0] - teach_euler[0])
                            post_delta_ry = self._normalize_angle(curr_euler[1] - teach_euler[1])
                            post_delta_rz = self._normalize_angle(curr_euler[2] - teach_euler[2])
                            
                            info(f"  标记检测成功 ({marker_info}): 生产 vs 示教", "CAMERA_UI")
                        else:
                            info(f"  标记检测成功 ({marker_info})，但无示教tag_data用于比较", "CAMERA_UI")
                    else:
                        info(f"  生产点未检测到AprilTag/ArUco标记", "CAMERA_UI")
                except Exception as e:
                    warning(f"生产点标记检测失败: {e}", "CAMERA_UI")
            
            # 计算纠偏评估比值 (纠偏后/纠偏前) - 完整6维
            def calc_ratio(post, pre):
                return abs(post / pre) if abs(pre) > 0.001 else 0.0
            
            ratio_x = calc_ratio(post_delta_x, pre_delta_x)
            ratio_y = calc_ratio(post_delta_y, pre_delta_y)
            ratio_z = calc_ratio(post_delta_z, pre_delta_z)
            ratio_rx = calc_ratio(post_delta_rx, pre_delta_rx)
            ratio_ry = calc_ratio(post_delta_ry, pre_delta_ry)
            ratio_rz = calc_ratio(post_delta_rz, pre_delta_rz)
            
            # 详细日志 (完整6维)
            info(f"========== 生产拍照 [{name}] ==========", "CAMERA_UI")
            info(f"  示教位姿:", "CAMERA_UI")
            info(f"    X={teaching_pose[0]:.3f} Y={teaching_pose[1]:.3f} Z={teaching_pose[2]:.3f} mm", "CAMERA_UI")
            info(f"    RX={teaching_pose[3]:.3f} RY={teaching_pose[4]:.3f} RZ={teaching_pose[5]:.3f} deg", "CAMERA_UI")
            info(f"  生产位姿 (纠偏后):", "CAMERA_UI")
            info(f"    X={pose[0]:.3f} Y={pose[1]:.3f} Z={pose[2]:.3f} mm", "CAMERA_UI")
            info(f"    RX={pose[3]:.3f} RY={pose[4]:.3f} RZ={pose[5]:.3f} deg", "CAMERA_UI")
            info(f"  -------- 偏差数据 (6维) --------", "CAMERA_UI")
            info(f"  纠偏前偏差 (标准点Tag):", "CAMERA_UI")
            info(f"    dX={pre_delta_x:.3f}mm  dY={pre_delta_y:.3f}mm  dZ={pre_delta_z:.3f}mm", "CAMERA_UI")
            info(f"    dRX={pre_delta_rx:.3f}°  dRY={pre_delta_ry:.3f}°  dRZ={pre_delta_rz:.3f}°", "CAMERA_UI")
            info(f"  纠偏后偏差 (此点Tag vs 示教):", "CAMERA_UI")
            info(f"    dX={post_delta_x:.3f}mm  dY={post_delta_y:.3f}mm  dZ={post_delta_z:.3f}mm", "CAMERA_UI")
            info(f"    dRX={post_delta_rx:.3f}°  dRY={post_delta_ry:.3f}°  dRZ={post_delta_rz:.3f}°", "CAMERA_UI")
            info(f"  -------- 纠偏评估 (后/前) --------", "CAMERA_UI")
            info(f"    X: {ratio_x:.2%}  Y: {ratio_y:.2%}  Z: {ratio_z:.2%}", "CAMERA_UI")
            info(f"    RX: {ratio_rx:.2%}  RY: {ratio_ry:.2%}  RZ: {ratio_rz:.2%}", "CAMERA_UI")
            info(f"  照片保存: {snap}", "CAMERA_UI")
            info(f"=========================================", "CAMERA_UI")
            
            # 追加偏差报告到文件 (完整6维) - 使用Tag相机坐标系数据
            deviation_info = {
                'pre_delta_x': pre_delta_x,
                'pre_delta_y': pre_delta_y,
                'pre_delta_z': pre_delta_z,
                'pre_delta_rx': pre_delta_rx,
                'pre_delta_ry': pre_delta_ry,
                'pre_delta_rz': pre_delta_rz,
                'post_delta_x': post_delta_x,
                'post_delta_y': post_delta_y,
                'post_delta_z': post_delta_z,
                'post_delta_rx': post_delta_rx,
                'post_delta_ry': post_delta_ry,
                'post_delta_rz': post_delta_rz,
                'ratio_x': ratio_x,
                'ratio_y': ratio_y,
                'ratio_z': ratio_z,
                'ratio_rx': ratio_rx,
                'ratio_ry': ratio_ry,
                'ratio_rz': ratio_rz,
                # Tag原始数据 (相机坐标系)
                'teaching_tag': teaching_tag_data,
                'current_tag': current_tag_data,
            }
            self._append_deviation_report(recipe_name, name, teaching_pose, pose, deviation_info)

        # 继续下一个
        self._servo_exec_timer.start(500)

    def update_frame_count_in_table(self, camera_info: CameraInfo):
        """更新帧数显示 (已废弃表格，仅打印日志或更新其他UI)"""
        pass
        # try:
        #     # 表格已移除，此处暂时禁用
        #     pass
        # except Exception as e:
        #     warning(f"更新帧数显示失败: {e}", "CAMERA_UI")

    def save_snapshot(self, prefix="snapshot_", save_dir=None, filepath_override=None):
        """保存当前画面快照
        
        Args:
            prefix: 文件名前缀
            save_dir: 指定保存目录（可选，默认使用配置的captures目录）
            filepath_override: 直接指定完整文件路径（可选，优先于prefix和save_dir）
        """
        # 检查相机是否可用
        if not self.current_camera:
            warning("无法保存快照：无相机", "CAMERA_UI")
            return None
        
        # 获取当前帧 - 优先从相机驱动获取最新帧
        frame = None
        if hasattr(self.current_camera, 'camera_driver') and self.current_camera.camera_driver:
            try:
                frame = self.current_camera.camera_driver.capture_image()
                if frame is not None:
                    debug(f"从相机驱动获取帧: shape={frame.shape}", "CAMERA_UI")
            except Exception as e:
                warning(f"从相机驱动获取帧失败: {e}", "CAMERA_UI")
        
        # 回退到current_frame
        if frame is None:
            frame = self.current_camera.current_frame
            if frame is not None:
                debug(f"使用current_frame: shape={frame.shape}", "CAMERA_UI")
        
        if frame is None:
            warning("无法保存快照：无图像帧", "CAMERA_UI")
            return None
             
        try:
            import cv2
            import time
            
            # 如果直接指定了完整文件路径
            if filepath_override:
                filepath = filepath_override
                # 确保目录存在
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            else:
                # 如果指定了保存目录，使用指定目录；否则使用默认目录
                if save_dir is None:
                    from core.managers.app_config import AppConfigManager
                    config_manager = AppConfigManager()
                    save_dir = os.path.join(config_manager.paths_dir, "captures")
                
                os.makedirs(save_dir, exist_ok=True)
                
                # 文件名中去除空格，避免文件系统问题
                safe_prefix = prefix.replace(" ", "_").replace("　", "_")
                
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{safe_prefix}{timestamp}.jpg"
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

    def _get_recipe_capture_dirs(self, recipe_name: str):
        """获取配方的照片存储目录结构
        
        返回目录结构:
        workspace/paths/captures/{recipe_name}/
            ├── standard.jpg           # 标准点位照片
            ├── teaching/              # 示教照片目录
            │   ├── point1.jpg
            │   └── point2.jpg
            ├── production/            # 生产照片目录
            │   ├── point1/            # 点位1的生产照片
            │   │   └── {timestamp}.jpg
            │   └── point2/            # 点位2的生产照片
            │       └── {timestamp}.jpg
            └── deviation_report.txt   # 偏差报告
        
        Returns:
            dict: {
                'base': 配方根目录,
                'standard': 标准点照片路径,
                'teaching': 示教照片目录,
                'production': 生产照片目录,
                'report': 偏差报告文件路径
            }
        """
        from core.managers.app_config import AppConfigManager
        config_manager = AppConfigManager()
        
        # 规范化配方名（去除非法字符）
        safe_name = recipe_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        safe_name = safe_name.replace(":", "_").replace("*", "_").replace("?", "_")
        safe_name = safe_name.replace("\"", "_").replace("<", "_").replace(">", "_")
        safe_name = safe_name.replace("|", "_")
        
        base_dir = os.path.join(config_manager.paths_dir, "captures", safe_name)
        teaching_dir = os.path.join(base_dir, "teaching")
        production_dir = os.path.join(base_dir, "production")
        
        # 创建目录
        os.makedirs(base_dir, exist_ok=True)
        os.makedirs(teaching_dir, exist_ok=True)
        os.makedirs(production_dir, exist_ok=True)
        
        return {
            'base': base_dir,
            'teaching': teaching_dir,
            'production': production_dir,
            'report': os.path.join(base_dir, "deviation_report.txt")
        }
    
    def _save_recipe_standard_photo(self, recipe_name: str, is_production: bool = False):
        """保存配方的标准点照片
        
        Args:
            recipe_name: 配方名称
            is_production: 是否为生产阶段（否则为示教阶段）
        """
        dirs = self._get_recipe_capture_dirs(recipe_name)
        if is_production:
            # 生产阶段：保存到 production/standard/
            std_dir = os.path.join(dirs['production'], 'standard')
            os.makedirs(std_dir, exist_ok=True)
            return self.save_snapshot(prefix="prod_std_", save_dir=std_dir)
        else:
            # 示教阶段：保存到 teaching/standard.jpg
            filepath = os.path.join(dirs['teaching'], 'standard.jpg')
            return self.save_snapshot(prefix="", save_dir=None, filepath_override=filepath)

    def _save_recipe_teaching_photo(self, recipe_name: str, point_name: str, point_index: int = None):
        """保存配方的示教点照片"""
        dirs = self._get_recipe_capture_dirs(recipe_name)
        # 使用英文编号命名，避免中文
        if point_index is not None:
            safe_name = f"point_{point_index}"
        else:
            safe_name = point_name.replace(" ", "_").replace("拍照点", "point_")
        return self.save_snapshot(prefix=f"teaching_{safe_name}_", save_dir=dirs['teaching'])

    def _save_recipe_production_photo(self, recipe_name: str, point_name: str, point_index: int = None):
        """保存配方的生产点照片"""
        dirs = self._get_recipe_capture_dirs(recipe_name)
        # 使用英文编号命名，避免中文
        if point_index is not None:
            safe_name = f"point_{point_index}"
        else:
            safe_name = point_name.replace(" ", "_").replace("拍照点", "point_").replace("标准点", "standard")
        
        # 生产照片按点位分目录
        point_dir = os.path.join(dirs['production'], safe_name)
        os.makedirs(point_dir, exist_ok=True)
        
        return self.save_snapshot(prefix="prod_", save_dir=point_dir)

    def _append_deviation_report(self, recipe_name: str, point_name: str, 
                                  teaching_pose, production_pose, deviation_info: dict):
        """追加偏差报告到文件 - 使用Tag相机坐标系数据"""
        import time
        dirs = self._get_recipe_capture_dirs(recipe_name)
        report_path = dirs['report']
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # 提取Tag数据
        teaching_tag = deviation_info.get('teaching_tag', {}) or {}
        current_tag = deviation_info.get('current_tag', {}) or {}
        
        with open(report_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*75}\n")
            f.write(f"时间: {timestamp}\n")
            f.write(f"点位: {point_name}\n")
            f.write(f"-" * 60 + "\n")
            
            # ========== Tag位姿数据 (相机坐标系) ==========
            f.write(f"【Tag位姿数据 - 相机坐标系】\n")
            
            # 示教时的Tag数据
            if teaching_tag:
                teach_tvec = teaching_tag.get('tvec', [0, 0, 0])
                teach_euler = teaching_tag.get('euler', [0, 0, 0])
                teach_center = teaching_tag.get('center', None)
                f.write(f"  示教Tag (ID={teaching_tag.get('id', '?')}):\n")
                f.write(f"    位置: X={teach_tvec[0]*1000:.2f}mm  Y={teach_tvec[1]*1000:.2f}mm  Z={teach_tvec[2]*1000:.2f}mm\n")
                f.write(f"    姿态: RX={teach_euler[0]:.2f}°  RY={teach_euler[1]:.2f}°  RZ={teach_euler[2]:.2f}°\n")
                if teach_center:
                    f.write(f"    像素中心: ({teach_center[0]:.1f}, {teach_center[1]:.1f}) px\n")
            else:
                f.write(f"  示教Tag: 无数据\n")
            
            # 生产时的Tag数据
            if current_tag:
                curr_tvec = current_tag.get('tvec', [0, 0, 0])
                curr_euler = current_tag.get('euler', [0, 0, 0])
                curr_center = current_tag.get('center', None)
                marker_type = current_tag.get('marker_type', 'unknown')
                f.write(f"  生产Tag (ID={current_tag.get('id', '?')}, {marker_type}):\n")
                f.write(f"    位置: X={curr_tvec[0]*1000:.2f}mm  Y={curr_tvec[1]*1000:.2f}mm  Z={curr_tvec[2]*1000:.2f}mm\n")
                f.write(f"    姿态: RX={curr_euler[0]:.2f}°  RY={curr_euler[1]:.2f}°  RZ={curr_euler[2]:.2f}°\n")
                if curr_center:
                    f.write(f"    像素中心: ({curr_center[0]:.1f}, {curr_center[1]:.1f}) px\n")
                
                # 计算像素偏差
                if teaching_tag and teaching_tag.get('center') and curr_center:
                    teach_center = teaching_tag.get('center')
                    px_dx = curr_center[0] - teach_center[0]
                    px_dy = curr_center[1] - teach_center[1]
                    f.write(f"    像素偏差: dX={px_dx:.1f}px  dY={px_dy:.1f}px\n")
            else:
                f.write(f"  生产Tag: 未检测到\n")
            
            f.write(f"-" * 60 + "\n")
            
            # ========== 纠偏偏差分析 ==========
            f.write(f"【纠偏偏差分析 - 相机坐标系下Tag位姿差】\n")
            
            # 纠偏前偏差 (标准点)
            f.write(f"  纠偏前偏差 (标准点Tag检测):\n")
            f.write(f"    位置: dX={deviation_info.get('pre_delta_x', 0):.3f}mm  ")
            f.write(f"dY={deviation_info.get('pre_delta_y', 0):.3f}mm  ")
            f.write(f"dZ={deviation_info.get('pre_delta_z', 0):.3f}mm\n")
            f.write(f"    姿态: dRX={deviation_info.get('pre_delta_rx', 0):.3f}°  ")
            f.write(f"dRY={deviation_info.get('pre_delta_ry', 0):.3f}°  ")
            f.write(f"dRZ={deviation_info.get('pre_delta_rz', 0):.3f}°\n")
            
            # 纠偏后偏差 (当前点)
            f.write(f"  纠偏后偏差 (生产Tag vs 示教Tag):\n")
            f.write(f"    位置: dX={deviation_info.get('post_delta_x', 0):.3f}mm  ")
            f.write(f"dY={deviation_info.get('post_delta_y', 0):.3f}mm  ")
            f.write(f"dZ={deviation_info.get('post_delta_z', 0):.3f}mm\n")
            f.write(f"    姿态: dRX={deviation_info.get('post_delta_rx', 0):.3f}°  ")
            f.write(f"dRY={deviation_info.get('post_delta_ry', 0):.3f}°  ")
            f.write(f"dRZ={deviation_info.get('post_delta_rz', 0):.3f}°\n")
            
            f.write(f"-" * 60 + "\n")
            
            # ========== 纠偏效果评估（改进版） ==========
            # 获取数据
            post_x = abs(deviation_info.get('post_delta_x', 0))
            post_y = abs(deviation_info.get('post_delta_y', 0))
            post_z = abs(deviation_info.get('post_delta_z', 0))
            post_rx = abs(deviation_info.get('post_delta_rx', 0))
            post_ry = abs(deviation_info.get('post_delta_ry', 0))
            post_rz = abs(deviation_info.get('post_delta_rz', 0))
            
            pre_x = abs(deviation_info.get('pre_delta_x', 0))
            pre_y = abs(deviation_info.get('pre_delta_y', 0))
            pre_z = abs(deviation_info.get('pre_delta_z', 0))
            pre_rx = abs(deviation_info.get('pre_delta_rx', 0))
            pre_ry = abs(deviation_info.get('pre_delta_ry', 0))
            pre_rz = abs(deviation_info.get('pre_delta_rz', 0))
            
            # 基于绝对误差的评级函数
            def grade_position_abs(err_mm):
                """位置误差评级 (mm)"""
                if err_mm < 0.5:
                    return "优秀 ★★★", 1.0
                elif err_mm < 1.0:
                    return "良好 ★★☆", 0.8
                elif err_mm < 2.0:
                    return "一般 ★☆☆", 0.5
                else:
                    return "需改进 ☆☆☆", 0.2
            
            def grade_angle_abs(err_deg):
                """姿态误差评级 (deg)"""
                if err_deg < 0.3:
                    return "优秀 ★★★", 1.0
                elif err_deg < 0.5:
                    return "良好 ★★☆", 0.8
                elif err_deg < 1.0:
                    return "一般 ★☆☆", 0.5
                else:
                    return "需改进 ☆☆☆", 0.2
            
            # 比例改善评估（仅当原始偏差足够大时有意义）
            def calc_improvement(post, pre, threshold):
                """计算改善比例，原始偏差小于阈值时返回 N/A"""
                if pre < threshold:
                    return "N/A(原始已很小)"
                ratio = post / pre
                if ratio < 0.1:
                    return f"{ratio:.0%} ↓↓↓"
                elif ratio < 0.3:
                    return f"{ratio:.0%} ↓↓"
                elif ratio < 0.5:
                    return f"{ratio:.0%} ↓"
                elif ratio < 1.0:
                    return f"{ratio:.0%}"
                else:
                    return f"{ratio:.0%} ↑"
            
            f.write(f"【纠偏效果评估】\n")
            f.write(f"  ┌─────────────────────────────────────────────────────────┐\n")
            f.write(f"  │ 指标     │ 纠偏后绝对误差    │ 评级     │ 改善比      │\n")
            f.write(f"  ├─────────────────────────────────────────────────────────┤\n")
            
            # 位置评估
            gx, _ = grade_position_abs(post_x)
            gy, _ = grade_position_abs(post_y)
            gz, _ = grade_position_abs(post_z)
            f.write(f"  │ 位置 X   │ {post_x:>8.3f}mm      │ {gx:<8} │ {calc_improvement(post_x, pre_x, 1.0):<11} │\n")
            f.write(f"  │ 位置 Y   │ {post_y:>8.3f}mm      │ {gy:<8} │ {calc_improvement(post_y, pre_y, 1.0):<11} │\n")
            f.write(f"  │ 位置 Z   │ {post_z:>8.3f}mm      │ {gz:<8} │ {calc_improvement(post_z, pre_z, 1.0):<11} │\n")
            
            # 姿态评估
            grx, _ = grade_angle_abs(post_rx)
            gry, _ = grade_angle_abs(post_ry)
            grz, _ = grade_angle_abs(post_rz)
            f.write(f"  │ 姿态 RX  │ {post_rx:>8.3f}°       │ {grx:<8} │ {calc_improvement(post_rx, pre_rx, 0.5):<11} │\n")
            f.write(f"  │ 姿态 RY  │ {post_ry:>8.3f}°       │ {gry:<8} │ {calc_improvement(post_ry, pre_ry, 0.5):<11} │\n")
            f.write(f"  │ 姿态 RZ  │ {post_rz:>8.3f}°       │ {grz:<8} │ {calc_improvement(post_rz, pre_rz, 0.5):<11} │\n")
            f.write(f"  └─────────────────────────────────────────────────────────┘\n")
            
            # 综合评分 (基于绝对误差)
            pos_scores = [grade_position_abs(post_x)[1], grade_position_abs(post_y)[1], grade_position_abs(post_z)[1]]
            rot_scores = [grade_angle_abs(post_rx)[1], grade_angle_abs(post_ry)[1], grade_angle_abs(post_rz)[1]]
            
            avg_pos_score = sum(pos_scores) / 3
            avg_rot_score = sum(rot_scores) / 3
            
            def overall_grade(score):
                if score >= 0.9:
                    return "优秀 ★★★"
                elif score >= 0.7:
                    return "良好 ★★☆"
                elif score >= 0.4:
                    return "一般 ★☆☆"
                else:
                    return "需改进 ☆☆☆"
            
            f.write(f"\n  【综合评估】\n")
            f.write(f"    位置精度: {overall_grade(avg_pos_score)} (XYZ均方根: {(post_x**2+post_y**2+post_z**2)**0.5:.2f}mm)\n")
            f.write(f"    姿态精度: {overall_grade(avg_rot_score)} (RxRyRz均方根: {(post_rx**2+post_ry**2+post_rz**2)**0.5:.2f}°)\n")
            
            # 参考：机械臂位姿（不再作为主要指标）
            f.write(f"\n  [参考] 机械臂位姿:\n")
            f.write(f"    示教: X={teaching_pose[0]:.1f} Y={teaching_pose[1]:.1f} Z={teaching_pose[2]:.1f}mm\n")
            f.write(f"    生产: X={production_pose[0]:.1f} Y={production_pose[1]:.1f} Z={production_pose[2]:.1f}mm\n")
            
            f.write(f"{'='*75}\n")
        
        info(f"偏差报告已更新: {report_path}", "CAMERA_UI")

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


