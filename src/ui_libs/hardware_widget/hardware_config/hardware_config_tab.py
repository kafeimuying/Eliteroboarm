"""
硬件配置Tab页
统一的硬件配置管理界面
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFormLayout, QComboBox, QLineEdit, QSpinBox,
    QCheckBox, QTextEdit, QMessageBox, QSplitter, QProgressBar,
    QDialogButtonBox, QTabWidget, QDialog, QFrame, QDoubleSpinBox,
    QMenu, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QColor

from core.managers.device_registry import get_device_registry
from core.services.robot_service import RobotService
from core.services.camera_service import CameraService
from core.services.light_service import LightService
from core.managers.app_config import AppConfigManager
from core.managers.log_manager import info, debug, warning, error
from .hardware_config_dialog import HardwareConfigDialog, show_hardware_config_dialog


class ConnectionTestThread(QThread):
    """连接测试线程"""
    test_completed = pyqtSignal(str, object, object)  # hardware_type, config_id, result

    def __init__(self, service: Any, hardware_type: str, config_id: str, config):
        super().__init__()
        self.service = service
        self.hardware_type = hardware_type
        self.config_id = config_id
        self.config = config

    def run(self):
        try:
            # 连接设备
            connect_result = self.service.connect(self.config)

            if connect_result.get('success', False):
                # 测试连接是否正常
                time.sleep(1)  # 等待连接稳定
                self.test_completed.emit(self.hardware_type, self.config_id, {'success': True})
            else:
                self.test_completed.emit(self.hardware_type, self.config_id, {'success': False, 'error': connect_result.get('error', 'Unknown error')})

        except Exception as e:
            error(f"Connection test failed: {e}", "HARDWARE_CONFIG_TAB")
            self.test_completed.emit(self.hardware_type, self.config_id, {'success': False, 'error': str(e)})


class HardwareConfigTab(QWidget):
    """硬件配置Tab页"""

    # 信号定义
    config_changed = pyqtSignal()
    device_connected = pyqtSignal(str, dict)  # hardware_type, config
    device_disconnected = pyqtSignal(str, str)  # hardware_type, device_id

    def __init__(self, parent=None):
        super().__init__(parent)

        # 初始化服务和管理器
        self.device_registry = get_device_registry()
        self.robot_service = RobotService()
        self.camera_service = CameraService()
        self.light_service = LightService()
        self.config_manager = AppConfigManager()
        # self.form_builder = DynamicFormBuilder()  # 已移除，使用统一配置对话框

        # 配置数据
        self.config_data = {}
        self.selected_config = None
        self.connection_threads = {}

        # 加载配置
        self.load_config()

        # 创建UI
        self.setup_ui()

        # 启动自动保存定时器
        self.setup_auto_save()

        # 初始化硬件列表
        self.refresh_hardware_list()

    def setup_ui(self):
        """设置UI"""
        main_layout = QHBoxLayout(self)

        # 左侧面板 - 硬件列表
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, 1)

        # 右侧面板 - 详细信息和操作
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, 1)

    def create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 硬件类型筛选
        type_group = QGroupBox("筛选")
        type_layout = QHBoxLayout(type_group)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["全部", "机械臂", "相机", "光源"])
        self.type_combo.currentTextChanged.connect(self.filter_hardware_list)
        type_layout.addWidget(self.type_combo)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索硬件名称...")
        self.search_input.textChanged.connect(self.filter_hardware_list)
        type_layout.addWidget(self.search_input)

        left_layout.addWidget(type_group)

        # 硬件列表
        self.hardware_table = QTableWidget()
        self.hardware_table.setColumnCount(6)
        self.hardware_table.setHorizontalHeaderLabels([
            "设备名称", "类型", "制造商", "型号", "连接方式", "状态"
        ])
        self.hardware_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.hardware_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # 设置为不可编辑
        self.hardware_table.itemSelectionChanged.connect(self.on_selection_changed)

        # 设置右击菜单
        self.hardware_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.hardware_table.customContextMenuRequested.connect(self.show_context_menu)

        # 设置列宽
        header = self.hardware_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        left_layout.addWidget(self.hardware_table)

        # 操作按钮
        button_layout = QHBoxLayout()

        self.add_btn = QPushButton("添加硬件")
        self.add_btn.clicked.connect(self.add_hardware)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        self.edit_btn = QPushButton("编辑硬件")
        self.edit_btn.clicked.connect(self.edit_hardware)
        self.edit_btn.setEnabled(False)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        self.delete_btn = QPushButton("删除硬件")
        self.delete_btn.clicked.connect(self.delete_hardware)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)

        left_layout.addLayout(button_layout)

        return left_widget

    def create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 硬件详情
        detail_group = QGroupBox("硬件详情")
        detail_layout = QFormLayout(detail_group)

        self.detail_name = QLabel("-")
        self.detail_type = QLabel("-")
        self.detail_manufacturer = QLabel("-")
        self.detail_model = QLabel("-")
        self.detail_connection = QLabel("-")
        self.detail_status = QLabel("-")
        self.detail_description = QLabel("-")

        detail_layout.addRow("设备名称:", self.detail_name)
        detail_layout.addRow("类型:", self.detail_type)
        detail_layout.addRow("制造商:", self.detail_manufacturer)
        detail_layout.addRow("型号:", self.detail_model)
        detail_layout.addRow("连接方式:", self.detail_connection)
        detail_layout.addRow("状态:", self.detail_status)
        detail_layout.addRow("描述:", self.detail_description)

        right_layout.addWidget(detail_group)

        # 连接参数
        params_group = QGroupBox("连接参数")
        params_layout = QVBoxLayout(params_group)

        self.params_text = QTextEdit()
        self.params_text.setReadOnly(True)
        self.params_text.setMaximumHeight(150)
        params_layout.addWidget(self.params_text)

        right_layout.addWidget(params_group)

        # 操作按钮
        action_group = QGroupBox("操作")
        action_layout = QHBoxLayout(action_group)

        self.connect_btn = QPushButton("连接设备")
        self.connect_btn.clicked.connect(self.connect_selected)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        self.disconnect_btn = QPushButton("断开连接")
        self.disconnect_btn.clicked.connect(self.disconnect_selected)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self.test_selected)
        self.test_btn.setEnabled(False)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        action_layout.addWidget(self.connect_btn)
        action_layout.addWidget(self.disconnect_btn)
        action_layout.addWidget(self.test_btn)

        right_layout.addWidget(action_group)

        # 状态指示器
        status_group = QGroupBox("连接状态")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("未选择设备")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #666666;
                padding: 20px;
                border: 2px dashed #cccccc;
                border-radius: 8px;
            }
        """)

        status_layout.addWidget(self.status_label)
        right_layout.addWidget(status_group)

        right_layout.addStretch()

        return right_widget

    def add_hardware(self):
        """添加硬件"""
        try:
            # 使用统一的硬件配置对话框
            config = show_hardware_config_dialog(parent=self)
            if config:
                self.add_hardware_config(config)
        except Exception as e:
            error(f"添加硬件失败: {e}")
            QMessageBox.critical(self, "错误", f"打开添加硬件对话框失败：{str(e)}")

    def edit_hardware(self):
        """编辑硬件"""
        try:
            if not self.selected_config:
                QMessageBox.warning(self, "警告", "请先选择要编辑的硬件配置")
                return

            # 使用统一的硬件配置对话框（编辑模式）
            config = show_hardware_config_dialog(
                config_data=self.selected_config,
                parent=self
            )
            if config:
                self.update_hardware_config(config)

        except Exception as e:
            error(f"编辑硬件失败: {e}")
            QMessageBox.critical(self, "错误", f"打开编辑硬件对话框失败：{str(e)}")

    def delete_hardware(self):
        """删除硬件"""
        if not self.selected_config:
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除硬件配置 '{self.selected_config.get('name', 'Unknown')}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_hardware_config(self.selected_config)

    def add_hardware_config(self, config):
        """添加硬件配置"""
        try:
            # 根据硬件类型添加到对应的配置数组
            hardware_type = config.get('type', '').lower()

            if hardware_type == 'camera':
                if 'cameras' not in self.config_data:
                    self.config_data['cameras'] = []
                self.config_data['cameras'].append(config)
            elif hardware_type == 'robot':
                if 'robots' not in self.config_data:
                    self.config_data['robots'] = []
                self.config_data['robots'].append(config)
            elif hardware_type == 'light':
                if 'lights' not in self.config_data:
                    self.config_data['lights'] = []
                self.config_data['lights'].append(config)

            # 保存配置文件
            self.save_config()

            # 刷新硬件列表
            self.refresh_hardware_list()

            info(f"Added {hardware_type} config: {config.get('name', 'Unknown')}")
            self.config_changed.emit()

        except Exception as e:
            error(f"Failed to add hardware config: {e}", "HARDWARE_CONFIG_TAB")
            QMessageBox.warning(self, "错误", f"添加硬件配置失败: {str(e)}")

    def update_hardware_config(self, new_config):
        """更新硬件配置"""
        try:
            hardware_type = new_config.get('type', '').lower()
            config_id = new_config.get('id', '')

            # 找到并更新对应的配置
            if hardware_type == 'camera' and 'cameras' in self.config_data:
                for i, config in enumerate(self.config_data['cameras']):
                    if config.get('id') == config_id:
                        self.config_data['cameras'][i] = new_config
                        break
            elif hardware_type == 'robot' and 'robots' in self.config_data:
                for i, config in enumerate(self.config_data['robots']):
                    if config.get('id') == config_id:
                        self.config_data['robots'][i] = new_config
                        break
            elif hardware_type == 'light' and 'lights' in self.config_data:
                for i, config in enumerate(self.config_data['lights']):
                    if config.get('id') == config_id:
                        self.config_data['lights'][i] = new_config
                        break

            # 保存配置文件
            self.save_config()

            # 刷新硬件列表
            self.refresh_hardware_list()

            # 更新选中的配置
            self.selected_config = new_config

            info(f"Updated {hardware_type} config: {new_config.get('name', 'Unknown')}")
            self.config_changed.emit()

        except Exception as e:
            error(f"Failed to update hardware config: {e}", "HARDWARE_CONFIG_TAB")
            QMessageBox.warning(self, "错误", f"更新硬件配置失败: {str(e)}")

    def delete_hardware_config(self, config):
        """删除硬件配置"""
        try:
            hardware_type = config.get('type', '').lower()
            config_id = config.get('id', '')

            # 找到并删除对应的配置
            if hardware_type == 'camera' and 'cameras' in self.config_data:
                self.config_data['cameras'] = [
                    c for c in self.config_data['cameras'] if c.get('id') != config_id
                ]
            elif hardware_type == 'robot' and 'robots' in self.config_data:
                self.config_data['robots'] = [
                    c for c in self.config_data['robots'] if c.get('id') != config_id
                ]
            elif hardware_type == 'light' and 'lights' in self.config_data:
                self.config_data['lights'] = [
                    c for c in self.config_data['lights'] if c.get('id') != config_id
                ]

            # 保存配置文件
            self.save_config()

            # 刷新硬件列表
            self.refresh_hardware_list()

            # 清除选择
            self.selected_config = None
            self.clear_detail_info()

            info(f"Deleted {hardware_type} config: {config.get('name', 'Unknown')}")
            self.config_changed.emit()

        except Exception as e:
            error(f"Failed to delete hardware config: {e}", "HARDWARE_CONFIG_TAB")
            QMessageBox.warning(self, "错误", f"删除硬件配置失败: {str(e)}")

    def load_config(self):
        """加载配置"""
        try:
            config_file = os.path.join("config", "hardware_config.json")
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
            else:
                # 创建默认配置
                self.config_data = {
                    "cameras": [],
                    "robots": [],
                    "lights": []
                }
                self.save_config()

        except Exception as e:
            error(f"Failed to load config: {e}", "HARDWARE_CONFIG_TAB")
            self.config_data = {"cameras": [], "robots": [], "lights": []}

    def save_config(self):
        """保存配置"""
        try:
            config_file = os.path.join("config", "hardware_config.json")
            os.makedirs(os.path.dirname(config_file), exist_ok=True)

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            error(f"Failed to save config: {e}")
            raise

    def setup_auto_save(self):
        """设置自动保存"""
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save)
        self.auto_save_timer.start(30000)  # 30秒自动保存一次

    def auto_save(self):
        """自动保存配置"""
        try:
            self.save_config()
        except Exception as e:
            error(f"Auto save failed: {e}")

    def refresh_hardware_list(self):
        """刷新硬件列表"""
        try:
            self.hardware_table.setRowCount(0)

            # 合并所有硬件配置
            all_configs = []

            if 'cameras' in self.config_data:
                all_configs.extend(self.config_data['cameras'])
            if 'robots' in self.config_data:
                all_configs.extend(self.config_data['robots'])
            if 'lights' in self.config_data:
                all_configs.extend(self.config_data['lights'])

            # 根据筛选条件过滤
            filter_text = self.type_combo.currentText()
            search_text = self.search_input.text().lower()

            for config in all_configs:
                # 类型筛选
                if filter_text != "全部":
                    type_map = {
                        "相机": "camera",
                        "机械臂": "robot",
                        "光源": "light"
                    }
                    if config.get('type', '').lower() != type_map.get(filter_text, ''):
                        continue

                # 搜索筛选
                if search_text and search_text not in config.get('name', '').lower():
                    continue

                # 添加到表格
                row = self.hardware_table.rowCount()
                self.hardware_table.insertRow(row)

                self.hardware_table.setItem(row, 0, QTableWidgetItem(config.get('name', '-')))
                self.hardware_table.setItem(row, 1, QTableWidgetItem(config.get('type', '-')))
                self.hardware_table.setItem(row, 2, QTableWidgetItem(config.get('manufacturer', '-')))
                self.hardware_table.setItem(row, 3, QTableWidgetItem(config.get('model', '-')))
                self.hardware_table.setItem(row, 4, QTableWidgetItem(config.get('connection_type', '-')))
                self.hardware_table.setItem(row, 5, QTableWidgetItem("已连接" if config.get('connected', False) else "未连接"))

        except Exception as e:
            error(f"Failed to refresh hardware list: {e}")

    def filter_hardware_list(self):
        """筛选硬件列表"""
        self.refresh_hardware_list()

    def on_selection_changed(self):
        """选择改变时的处理"""
        selected_items = self.hardware_table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            config = self.get_config_at_row(row)
            if config:
                self.selected_config = config
                self.update_detail_info(config)
                self.update_action_buttons(True)
        else:
            self.selected_config = None
            self.clear_detail_info()
            self.update_action_buttons(False)

    def update_detail_info(self, config):
        """更新详细信息"""
        try:
            self.detail_name.setText(config.get('name', '-'))
            self.detail_type.setText(config.get('type', '-'))
            self.detail_manufacturer.setText(config.get('manufacturer', '-'))
            self.detail_model.setText(config.get('model', '-'))
            self.detail_connection.setText(config.get('connection_type', '-'))
            self.detail_status.setText("已连接" if config.get('connected', False) else "未连接")
            self.detail_description.setText(config.get('description', '-'))

            # 显示连接参数
            connection_params = config.get('connection_params', {})
            if connection_params:
                params_text = json.dumps(connection_params, indent=2, ensure_ascii=False)
                self.params_text.setPlainText(params_text)
            else:
                self.params_text.clear()

            # 更新状态标签
            if config.get('connected', False):
                self.status_label.setText("设备已连接")
                self.status_label.setStyleSheet("""
                    QLabel {
                        font-size: 16px;
                        font-weight: bold;
                        color: #4CAF50;
                        padding: 20px;
                        border: 2px solid #4CAF50;
                        border-radius: 8px;
                        background-color: #f1f8e9;
                    }
                """)
            else:
                self.status_label.setText("设备未连接")
                self.status_label.setStyleSheet("""
                    QLabel {
                        font-size: 16px;
                        font-weight: bold;
                        color: #f44336;
                        padding: 20px;
                        border: 2px solid #f44336;
                        border-radius: 8px;
                        background-color: #ffebee;
                    }
                """)

        except Exception as e:
            error(f"Failed to update detail info: {e}")

    def clear_detail_info(self):
        """清除详细信息"""
        self.detail_name.setText("-")
        self.detail_type.setText("-")
        self.detail_manufacturer.setText("-")
        self.detail_model.setText("-")
        self.detail_connection.setText("-")
        self.detail_status.setText("-")
        self.detail_description.setText("-")
        self.params_text.clear()

        self.status_label.setText("未选择设备")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #666666;
                padding: 20px;
                border: 2px dashed #cccccc;
                border-radius: 8px;
            }
        """)

    def update_action_buttons(self, has_selection):
        """更新操作按钮状态"""
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

        if has_selection and self.selected_config:
            is_connected = self.selected_config.get('connected', False)
            self.connect_btn.setEnabled(not is_connected)
            self.disconnect_btn.setEnabled(is_connected)
            self.test_btn.setEnabled(True)
        else:
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
            self.test_btn.setEnabled(False)

    def get_config_at_row(self, row):
        """获取指定行的配置"""
        try:
            # 获取所有配置并找到对应的
            all_configs = []
            if 'cameras' in self.config_data:
                all_configs.extend(self.config_data['cameras'])
            if 'robots' in self.config_data:
                all_configs.extend(self.config_data['robots'])
            if 'lights' in self.config_data:
                all_configs.extend(self.config_data['lights'])

            if 0 <= row < len(all_configs):
                return all_configs[row]
        except Exception as e:
            error(f"Failed to get config at row {row}: {e}")

        return None

    def get_row_for_config(self, config):
        """获取配置对应的行号"""
        if not config:
            return -1

        target_name = config.get('name')
        if not target_name:
            return -1

        # 遍历表格查找匹配的行
        for row in range(self.hardware_table.rowCount()):
            item = self.hardware_table.item(row, 0)
            if item and item.text() == target_name:
                return row

        return -1

    def show_context_menu(self, position):
        """显示右击菜单"""
        if not self.selected_config:
            return

        menu = QMenu(self)

        edit_action = menu.addAction("编辑")
        edit_action.triggered.connect(lambda: self.edit_hardware())

        delete_action = menu.addAction("删除")
        delete_action.triggered.connect(lambda: self.delete_hardware())

        copy_action = menu.addAction("复制配置")
        copy_action.triggered.connect(lambda: self.copy_config())

        menu.exec(self.hardware_table.mapToGlobal(position))

    def copy_config(self):
        """复制配置"""
        if not self.selected_config:
            return

        try:
            config_copy = self.selected_config.copy()
            # 清除ID和连接状态
            config_copy.pop('id', None)
            config_copy.pop('connected', None)
            # 修改名称
            config_copy['name'] = config_copy.get('name', '') + "_副本"

            dialog = HardwareConfigDialog(
                hardware_type=config_copy.get('type'),
                config_data=config_copy,
                parent=self
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                config = dialog.get_result_config()
                if config:
                    self.add_hardware_config(config)

        except Exception as e:
            error(f"Failed to copy config: {e}")
            QMessageBox.warning(self, "错误", f"复制配置失败: {str(e)}")

    def connect_selected(self):
        """连接选中的设备"""
        if not self.selected_config:
            return

        try:
            hardware_type = self.selected_config.get('type', '').lower()
            service = self.get_service_for_hardware_type(hardware_type)

            if not service:
                QMessageBox.warning(self, "错误", "不支持的硬件类型")
                return

            self.connect_btn.setEnabled(False)
            self.connect_btn.setText("连接中...")

            # 启动连接线程
            thread = QThread()

            def connect_worker():
                try:
                    result = service.connect(self.selected_config)
                    return result
                except Exception as e:
                    error(f"Connection failed: {e}")
                    return {'success': False, 'error': str(e)}

            def on_connect_finished():
                try:
                    # 更新按钮状态
                    self.connect_btn.setEnabled(True)
                    self.connect_btn.setText("连接设备")

                    # 这里应该有实际的连接结果处理
                    # 暂时显示成功消息
                    QMessageBox.information(self, "连接", "设备连接成功（模拟）")

                except Exception as e:
                    error(f"Connection finish error: {e}")

            worker_thread = QThread()
            worker_thread.finished.connect(on_connect_finished)
            worker_thread.start()

        except Exception as e:
            error(f"Failed to connect device: {e}")
            QMessageBox.warning(self, "错误", f"连接设备失败: {str(e)}")

    def disconnect_selected(self):
        """断开选中的设备"""
        if not self.selected_config:
            return

        try:
            hardware_type = self.selected_config.get('type', '').lower()
            service = self.get_service_for_hardware_type(hardware_type)

            if not service:
                QMessageBox.warning(self, "错误", "不支持的硬件类型")
                return

            result = service.disconnect(self.selected_config.get('id'))
            if result.get('success', True):
                QMessageBox.information(self, "断开连接", "设备已断开连接")
            else:
                QMessageBox.warning(self, "错误", f"断开连接失败: {result.get('error', 'Unknown error')}")

        except Exception as e:
            error(f"Failed to disconnect device: {e}")
            QMessageBox.warning(self, "错误", f"断开连接失败: {str(e)}")

    def test_selected(self):
        """测试选中的设备连接"""
        if not self.selected_config:
            return

        try:
            hardware_type = self.selected_config.get('type', '').lower()
            service = self.get_service_for_hardware_type(hardware_type)

            if not service:
                QMessageBox.warning(self, "错误", "不支持的硬件类型")
                return

            # 显示测试中状态
            self.test_btn.setEnabled(False)
            self.test_btn.setText("测试中...")

            # 启动测试线程
            test_thread = ConnectionTestThread(
                service, hardware_type,
                self.selected_config.get('id'), self.selected_config
            )
            test_thread.test_completed.connect(self.on_test_completed)
            test_thread.start()

            # 保存线程引用
            self.connection_threads[self.selected_config.get('id')] = test_thread

        except Exception as e:
            error(f"Failed to start connection test: {e}")
            QMessageBox.warning(self, "错误", f"启动连接测试失败: {str(e)}")

    def on_test_completed(self, hardware_type: str, config_id: str, result):
        """连接测试完成回调"""
        try:
            # 恢复按钮状态
            self.test_btn.setEnabled(True)
            self.test_btn.setText("测试连接")

            # 移除线程引用
            if config_id in self.connection_threads:
                del self.connection_threads[config_id]

            # 显示测试结果
            if result.get('success', False):
                QMessageBox.information(
                    self, "连接测试",
                    f"设备连接成功！\n类型: {hardware_type}\nID: {config_id}"
                )
            else:
                error_msg = result.get('error', '未知错误')
                QMessageBox.warning(
                    self, "连接测试失败",
                    f"设备连接失败！\n类型: {hardware_type}\nID: {config_id}\n错误: {error_msg}"
                )

        except Exception as e:
            error(f"Test completion error: {e}")

    def get_service_for_hardware_type(self, hardware_type):
        """根据硬件类型获取服务实例"""
        try:
            if hardware_type == 'camera':
                return self.camera_service
            elif hardware_type == 'robot':
                return self.robot_service
            elif hardware_type == 'light':
                return self.light_service
            return None
        except Exception as e:
            error(f"Failed to get service instance for {hardware_type}: {e}")
            return None


