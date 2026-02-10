from typing import Dict, Any, Optional, List
import time
import json
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QCheckBox, QSlider, QTextEdit, QMessageBox, QSplitter,
    QFileDialog, QProgressBar, QFrame, QFormLayout, QComboBox,
    QLineEdit, QDialogButtonBox, QDialog, QListWidget, QListWidgetItem, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QObject
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor
from core import DeviceManager, RobotService, CameraService, LightService
from core.managers.log_manager import info, debug, warning, error
from core.managers.window_settings_manager import get_window_settings_manager
from ui_libs.hardware_widget.hardware_config.hardware_config_tab import HardwareConfigTab
from ui_libs.hardware_widget.camera.camera_info import CameraInfo
from ui_libs.hardware_widget.camera.camera_preview import CameraPreviewThread, PreviewLabel
from ui_libs.hardware_widget.camera.camera_control import CameraControlTab
from ui_libs.hardware_widget.camera.save_path_dialog import SavePathDialog
from ui_libs.hardware_widget.robotic_arm.robot_control import RobotControlTab
# from ui_libs.hardware_widget.robotic_arm.flexible_shooting_widget import FlexibleShootingWidget
from ui_libs.hardware_widget.light.light_control import LightControlTab

# 导入相机驱动
try:
    from drivers.camera import SimulationCamera
    CAMERA_DRIVERS_AVAILABLE = True
except ImportError:
    warning("相机驱动模块导入失败，将使用模拟预览", "CAMERA_UI")
    CAMERA_DRIVERS_AVAILABLE = False


class HardwareManagementMainWindow(QMainWindow):
    """硬件管理主控制窗口 - 最终版"""

    def __init__(self, device_manager: DeviceManager,
                 robot_service: RobotService,
                 camera_service: CameraService,
                 light_service: LightService):
        super().__init__()

        # 保存服务层实例
        self.device_manager = device_manager
        self.robot_service = robot_service
        self.camera_service = camera_service
        self.light_service = light_service

        # 初始化窗口设置管理器
        self.window_settings_manager = get_window_settings_manager()

        self.init_ui()

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle("🤖 机器人控制系统 v3.0")
        self.setGeometry(100, 100, 1600, 900)

        # 创建中央窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 创建Tab控件
        self.tab_widget = QTabWidget()

        # 机械臂控制标签页
        self.robot_tab = RobotControlTab(self.robot_service, self.camera_service, self)
        self.tab_widget.addTab(self.robot_tab, "🤖 机械臂控制")

        # 相机管理标签页
        self.camera_tab = CameraControlTab(self.camera_service, self)
        self.tab_widget.addTab(self.camera_tab, "📷 相机管理")

        # 光源控制标签页
        self.light_tab = LightControlTab(self.light_service, self)
        self.tab_widget.addTab(self.light_tab, "💡 光源控制")

        # 硬件配置标签页
        self.config_tab = HardwareConfigTab()
        self.tab_widget.addTab(self.config_tab, "⚙️ 硬件配置")

        # 柔性拍摄标签页
        # self.flexible_shooting_tab = FlexibleShootingWidget(self.robot_service, self.camera_service, self)
        # self.tab_widget.addTab(self.flexible_shooting_tab, "📷 柔性拍摄")

        main_layout.addWidget(self.tab_widget)

        # 状态栏
        self.statusBar().showMessage("系统就绪")

        # 连接相机标签页的信号以更新状态栏
        self.camera_tab.camera_connected.connect(self.on_camera_connected)
        self.camera_tab.camera_disconnected.connect(self.on_camera_disconnected)

        # 连接机械臂标签页的信号以更新状态栏
        if hasattr(self.robot_tab, 'robot_connected'):
            self.robot_tab.robot_connected.connect(self.on_robot_connected)
        if hasattr(self.robot_tab, 'robot_disconnected'):
            self.robot_tab.robot_disconnected.connect(self.on_robot_disconnected)

        # 加载窗口设置
        self._load_window_settings()

    def on_camera_connected(self, camera_id: str, config: dict):
        """相机连接时更新状态栏"""
        camera_name = config.get('name', f'Camera {camera_id}')
        self.statusBar().showMessage(f"📷 已连接: {camera_name}")

    def on_camera_disconnected(self, camera_id: str):
        """相机断开时更新状态栏"""
        self.statusBar().showMessage(f"📷 已断开: Camera {camera_id}")

    def on_robot_connected(self, robot_id: str, config: dict):
        """机械臂连接时更新状态栏"""
        robot_name = config.get('name', f'Robot {robot_id}')
        self.statusBar().showMessage(f"🤖 已连接: {robot_name}")

    def robot_disconnected(self, robot_id: str):
        """机械臂断开时更新状态栏"""
        self.statusBar().showMessage(f"🤖 已断开: Robot {robot_id}")

    def _load_window_settings(self):
        """加载窗口设置"""
        try:
            # 使用统一管理器加载窗口状态
            success = self.window_settings_manager.load_window_state(
                self,
                "hardware_management_main_window",
                default_geometry=(100, 100, 1600, 900)
            )
            if success:
                # 尝试恢复标签页状态
                window_settings = self.window_settings_manager.get_window_settings("hardware_management_main_window")
                if (window_settings and
                    'additional_data' in window_settings and
                    'current_tab_index' in window_settings['additional_data'] and
                    hasattr(self, 'tab_widget')):
                    try:
                        current_tab_index = window_settings['additional_data']['current_tab_index']
                        if 0 <= current_tab_index < self.tab_widget.count():
                            self.tab_widget.setCurrentIndex(current_tab_index)
                            info("硬件管理主窗口标签页状态恢复成功", "HardwareMainWindow")
                    except Exception as e:
                        debug(f"恢复标签页状态失败: {e}", "HardwareMainWindow")
            else:
                # 如果加载失败，使用默认状态
                if hasattr(self, 'tab_widget') and self.tab_widget.count() > 0:
                    self.tab_widget.setCurrentIndex(0)
        except Exception as e:
            error(f"加载窗口设置失败: {e}", "HardwareMainWindow")

    def _save_window_settings(self):
        """保存窗口设置"""
        try:
            # 准备额外数据
            additional_data = {}
            # 保存当前标签页索引
            if hasattr(self, 'tab_widget'):
                additional_data['current_tab_index'] = self.tab_widget.currentIndex()

            # 使用统一窗口设置管理器保存窗口状态
            success = self.window_settings_manager.save_window_state(
                self,
                "hardware_management_main_window",
                additional_data
            )
            if success:
                info("硬件管理主窗口设置保存完成", "HardwareMainWindow")
            else:
                warning("硬件管理主窗口设置保存失败", "HardwareMainWindow")
        except Exception as e:
            error(f"保存窗口设置失败: {e}", "HardwareMainWindow")

    def closeEvent(self, event):
        """关闭事件 - 保存窗口设置并清理资源"""
        try:
            # 保存窗口设置
            self._save_window_settings()
            
            # 清理资源
            info("正在关闭硬件管理系统，清理资源...", "HardwareMainWindow")
            
            # 1. 停止并断开所有相机
            if hasattr(self, 'camera_tab') and hasattr(self.camera_tab, 'disconnect_all'):
                self.camera_tab.disconnect_all()
            
            # 2. 断开机器人连接
            if hasattr(self, 'robot_service') and self.robot_service and self.robot_service.is_connected():
                self.robot_service.disconnect()
                
            # 3. 断开其他设备
            if hasattr(self, 'device_manager'):
                self.device_manager.disconnect_all()

            info("硬件管理系统已关闭", "HardwareMainWindow")
            event.accept()
        except Exception as e:
            error(f"关闭时出错: {e}", "HardwareMainWindow")
            event.accept()


if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 模拟服务实例
    class MockDeviceManager:
        def get_robot(self):
            return None
        def get_camera(self):
            return None
        def get_light(self):
            return None
        def disconnect_all(self):
            pass

    class MockService:
        def __init__(self):
            self.connected = False
        def connect(self, config):
            self.connected = True
            return {'success': True}
        def disconnect(self):
            self.connected = False
            return {'success': True}
        def is_connected(self):
            return self.connected
        def test_connection(self):
            return {'success': True}

    # 测试UI
    device_manager = MockDeviceManager()
    robot_service = MockService()
    camera_service = MockService()
    light_service = MockService()

    window = HardwareManagementMainWindow(device_manager, robot_service, camera_service, light_service)
    window.show()

    sys.exit(app.exec())