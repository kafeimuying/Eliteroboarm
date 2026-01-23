"""
硬件配置对话框 - 统一支持添加和编辑功能
"""

import logging
import time
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QPushButton, QLineEdit, QComboBox, QSpinBox, QTextEdit,
    QDialogButtonBox, QFileDialog
)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)


class HardwareConfigDialog(QDialog):
    """硬件配置对话框 - 统一支持添加和编辑功能"""

    def __init__(self, config_data: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)

        self.is_edit_mode = bool(config_data)
        self.config_data = config_data or {}
        self.result_config = {}

        # 设置窗口标题
        if self.is_edit_mode:
            self.setWindowTitle("编辑硬件配置")
        else:
            self.setWindowTitle("添加硬件配置")

        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self.setup_ui()

        # 如果是编辑模式，加载现有数据
        if self.is_edit_mode:
            self.load_existing_config()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()

        # 硬件类型
        type_group = QGroupBox("硬件类型")
        type_layout = QFormLayout()

        self.hardware_type_combo = QComboBox()
        self.hardware_type_combo.addItems([
            "机器人", "相机", "光源"
        ])

        # 如果是编辑模式，根据现有配置设置硬件类型
        if self.is_edit_mode:
            hardware_type = self.config_data.get('hardware_type', self.config_data.get('type', ''))
            if hardware_type == 'robot':
                self.hardware_type_combo.setCurrentText("机器人")
            elif hardware_type == 'camera':
                self.hardware_type_combo.setCurrentText("相机")
            elif hardware_type == 'light':
                self.hardware_type_combo.setCurrentText("光源")

        # 编辑模式下禁用硬件类型选择
        if self.is_edit_mode:
            self.hardware_type_combo.setEnabled(False)

        type_layout.addRow("硬件类型:", self.hardware_type_combo)

        # 设备ID
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("例如: camera_001")
        type_layout.addRow("设备ID:", self.id_input)

        # 硬件名称
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如: 新增相机")
        type_layout.addRow("硬件名称:", self.name_input)

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # 品牌和型号
        info_group = QGroupBox("硬件信息")
        info_layout = QFormLayout()

        self.brand_combo = QComboBox()
        self.brand_combo.setEditable(True)
        info_layout.addRow("品牌:", self.brand_combo)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        info_layout.addRow("型号:", self.model_combo)

        # 当硬件类型变化时更新品牌选项
        self.hardware_type_combo.currentTextChanged.connect(self.update_brand_options)

        # 当品牌变化时自动调整连接方式
        self.brand_combo.currentTextChanged.connect(self.on_brand_changed)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 连接方式
        connection_group = QGroupBox("连接方式")
        connection_layout = QFormLayout()

        self.connection_type_combo = QComboBox()
        self.connection_type_combo.addItems(["TCP/IP", "Serial", "USB", "Simulation"])
        connection_layout.addRow("连接方式:", self.connection_type_combo)

        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)

        # 连接参数
        params_group = QGroupBox("连接参数")
        params_layout = QVBoxLayout()

        self.params_form_layout = QFormLayout()
        self.params_form_layout.addRow("IP地址:", QLineEdit("192.168.1.100"))
        self.params_form_layout.addRow("端口:", QSpinBox().setRange(1, 65535))
        self.params_form_layout.addRow("超时(秒):", QSpinBox().setRange(1, 60))

        params_layout.addLayout(self.params_form_layout)
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # 描述
        desc_group = QGroupBox("描述")
        desc_layout = QVBoxLayout()

        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(100)
        desc_layout.addWidget(self.description_input)

        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # 当连接类型变化时更新参数表单
        self.connection_type_combo.currentTextChanged.connect(self.update_params_form)

        # 初始化品牌选项（仅在非编辑模式）
        if not self.is_edit_mode:
            self.update_brand_options(self.hardware_type_combo.currentText())

    def update_brand_options(self, hardware_type):
        """根据硬件类型更新品牌选项"""
        self.brand_combo.clear()

        if hardware_type == "机器人":
            # 从 device_registry 获取机器人品牌（延迟初始化）
            registry = self.get_device_registry()
            if registry:
                robot_info = registry.get_robot_brand_info()
                for brand_key in robot_info.keys():
                    brand_info = robot_info[brand_key]
                    brand_name = brand_info.get('name_cn', brand_info.get('name', brand_key))
                    self.brand_combo.addItem(brand_name)
            # 添加模拟选项
            self.brand_combo.addItems(["yamaha", "fanuc", "universal", "kuka", "abb", "simulation"])

        elif hardware_type == "相机":
            # 从 device_registry 获取相机制造商（延迟初始化）
            registry = self.get_device_registry()
            if registry:
                camera_info = registry.get_camera_brand_info()
                for brand_key in camera_info.keys():
                    brand_info = camera_info[brand_key]
                    brand_name = brand_info.get('name_cn', brand_info.get('name', brand_key))
                    self.brand_combo.addItem(brand_name)
            # 添加模拟选项
            self.brand_combo.addItems(["hikvision", "basler", "dahua", "sony", "flir", "simulation"])

        elif hardware_type == "光源":
            # 光源通常比较简单，使用基本选项
            self.brand_combo.addItems(["digital", "omron", "keyence", "banner", "simulation"])

    def on_brand_changed(self, brand_text):
        """当品牌选择变化时自动调整连接方式"""
        brand_lower = brand_text.lower()
        if 'simulation' in brand_lower or '模拟' in brand_text:
            # 自动选择 Simulation 连接方式
            self.connection_type_combo.setCurrentText("Simulation")

    def update_params_form(self, connection_type):
        """根据连接类型更新参数表单"""
        # 清除现有的参数表单项
        while self.params_form_layout.rowCount() > 0:
            self.params_form_layout.removeRow(0)

        if connection_type == "TCP/IP":
            ip_edit = QLineEdit("192.168.1.100")
            self.params_form_layout.addRow("IP地址:", ip_edit)

            port_spin = QSpinBox()
            port_spin.setRange(1, 65535)
            port_spin.setValue(8080)
            self.params_form_layout.addRow("端口:", port_spin)

            timeout_spin = QSpinBox()
            timeout_spin.setRange(1, 60)
            timeout_spin.setValue(5)
            self.params_form_layout.addRow("超时(秒):", timeout_spin)

        elif connection_type == "Serial":
            serial_edit = QLineEdit("COM1")
            self.params_form_layout.addRow("串口:", serial_edit)

            baudrate_combo = QComboBox()
            baudrate_combo.addItems(["9600", "19200", "38400", "115200"])
            self.params_form_layout.addRow("波特率:", baudrate_combo)

            databits_combo = QComboBox()
            databits_combo.addItems(["8", "7", "6", "5"])
            self.params_form_layout.addRow("数据位:", databits_combo)

        elif connection_type == "USB":
            device_id_edit = QLineEdit()
            self.params_form_layout.addRow("设备ID:", device_id_edit)

            vendor_id_edit = QLineEdit()
            self.params_form_layout.addRow("供应商ID:", vendor_id_edit)

            product_id_edit = QLineEdit()
            self.params_form_layout.addRow("产品ID:", product_id_edit)

        elif connection_type == "Simulation":
            # 获取硬件类型以确定参数
            hardware_type = self.hardware_type_combo.currentText()

            if hardware_type == "相机":
                media_type_combo = QComboBox()
                media_type_combo.addItems(["程序生成", "图片文件夹", "单个媒体文件", "视频文件"])
                self.params_form_layout.addRow("媒体类型:", media_type_combo)

                # 媒体路径选择
                path_layout = QHBoxLayout()
                self.media_path_edit = QLineEdit("/home/ashu001/Documents/code/robot-control/data/")
                browse_btn = QPushButton("浏览...")
                browse_btn.clicked.connect(lambda: self.browse_media_path(self.media_path_edit, media_type_combo))
                path_layout.addWidget(self.media_path_edit)
                path_layout.addWidget(browse_btn)
                self.params_form_layout.addRow("媒体路径:", path_layout)

                fps_spin = QSpinBox()
                fps_spin.setRange(1, 120)
                fps_spin.setValue(30)
                self.params_form_layout.addRow("帧率(FPS):", fps_spin)

                self.params_form_layout.addRow("分辨率:", QLineEdit("1920x1080"))
            elif hardware_type == "机械臂":
                self.params_form_layout.addRow("模拟模式:", QComboBox().addItems(["Basic", "Advanced"]))
                self.params_form_layout.addRow("响应延迟(ms):", QSpinBox().setRange(0, 1000))
            elif hardware_type == "光源":
                self.params_form_layout.addRow("通道数:", QSpinBox().setRange(1, 16))
                self.params_form_layout.addRow("响应延迟(ms):", QSpinBox().setRange(0, 1000))

    def get_config(self):
        """获取配置"""
        # 映射中文硬件类型到英文
        hardware_type_map = {
            '机械臂': 'robot',
            '相机': 'camera',
            '光源': 'light'
        }

        # 映射连接类型
        connection_type_map = {
            'TCP/IP': 'network',
            'Serial': 'serial',
            'USB': 'usb',
            'Simulation': 'simulation'
        }

        chinese_type = self.hardware_type_combo.currentText()
        chinese_connection = self.connection_type_combo.currentText()

        # 映射中文硬件类型到英文
        hardware_type_map = {
            '机械臂': 'robot',
            '相机': 'camera',
            '光源': 'light'
        }

        english_type = hardware_type_map.get(chinese_type, chinese_type.lower())

        # 如果是编辑模式，保留原有ID；如果是添加模式，生成新ID
        if self.is_edit_mode:
            device_id = self.id_input.text() or self.config_data.get('id', f"{english_type}_{int(time.time())}")
        else:
            device_id = self.id_input.text() or f"{english_type}_{int(time.time())}"

        config = {
            'id': device_id,
            'name': self.name_input.text(),
            'type': english_type,
            'brand': self.brand_combo.currentText().lower(),
            'model': self.model_combo.currentText(),
            'connection_type': connection_type_map.get(chinese_connection, chinese_connection.lower()),
            'description': self.description_input.toPlainText(),
            'connection_params': self._get_connection_params(),
            # 添加缺失的字段
            'hardware_type': chinese_type,  # 保持中文显示类型
            'original_type': english_type   # 保存英文原始类型
        }

        # 为相机添加特殊字段
        if english_type == 'camera':
            config.update(self._get_camera_specific_fields())

        # 为模拟设备添加特殊标记
        if config['connection_type'] == 'simulation':
            config['is_simulation'] = True

        return config

    def _get_camera_specific_fields(self):
        """获取相机特有字段"""
        fields = {}

        # 从参数表单中提取相机特有字段
        for i in range(self.params_form_layout.rowCount()):
            label_item = self.params_form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.params_form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)

            if label_item and field_item:
                label_widget = label_item.widget()
                field_widget = field_item.widget()

                if label_widget and field_widget:
                    label_text = label_widget.text().replace(":", "").strip()

                    # 处理相机特有字段
                    if label_text == "分辨率":
                        if isinstance(field_widget, QLineEdit):
                            fields['resolution'] = field_widget.text().strip()
                    elif label_text == "帧率(FPS)":
                        if isinstance(field_widget, QSpinBox):
                            fields['fps'] = field_widget.value()
                    elif label_text == "超时(秒)":
                        if isinstance(field_widget, QSpinBox):
                            fields['timeout'] = field_widget.value()

        return fields

    def browse_media_path(self, line_edit, media_type_combo):
        """浏览媒体路径"""
        media_type = media_type_combo.currentText()

        if media_type == "图片文件夹":
            folder_path = QFileDialog.getExistingDirectory(
                self, "选择图片文件夹",
                line_edit.text() or "/home/ashu001/Documents/code/robot-control/data/"
            )
            if folder_path:
                line_edit.setText(folder_path)
        elif media_type in ["单个媒体文件", "视频文件"]:
            file_filter = ""
            if media_type == "单个媒体文件":
                file_filter = "图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff);;所有文件 (*)"
            elif media_type == "视频文件":
                file_filter = "视频文件 (*.mp4 *.avi *.mov *.mkv);;所有文件 (*)"

            file_path, _ = QFileDialog.getOpenFileName(
                self, f"选择{media_type}",
                line_edit.text() or "/home/ashu001/Documents/code/robot-control/data/",
                file_filter
            )
            if file_path:
                line_edit.setText(file_path)

    def _get_connection_params(self):
        """获取连接参数"""
        params = {}
        for i in range(self.params_form_layout.rowCount()):
            # 使用 QFormLayout.ItemRole 枚举
            label_item = self.params_form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            field_item = self.params_form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)

            if label_item and field_item:
                label_widget = label_item.widget()
                field_widget = field_item.widget()

                if label_widget and field_widget:
                    label = label_widget.text().replace(":", "").strip()

                    if isinstance(field_widget, QLineEdit):
                        params[label] = field_widget.text().strip()
                    elif isinstance(field_widget, QSpinBox):
                        params[label] = field_widget.value()
                    elif isinstance(field_widget, QComboBox):
                        params[label] = field_widget.currentText()

        return params

    def load_existing_config(self):
        """加载现有配置数据到表单"""
        try:
            # 设置基本字段
            self.id_input.setText(self.config_data.get('id', ''))
            self.name_input.setText(self.config_data.get('name', ''))
            self.model_combo.addItem(self.config_data.get('model', ''))
            self.model_combo.setCurrentText(self.config_data.get('model', ''))

            # 设置品牌
            brand = self.config_data.get('brand', '')
            if brand:
                # 更新品牌选项
                hardware_type_text = self.hardware_type_combo.currentText()
                self.update_brand_options(hardware_type_text)

                # 尝试设置品牌
                brand_index = self.brand_combo.findText(brand)
                if brand_index >= 0:
                    self.brand_combo.setCurrentIndex(brand_index)
                else:
                    self.brand_combo.addItem(brand)
                    self.brand_combo.setCurrentText(brand)

            # 设置连接类型
            connection_type = self.config_data.get('connection_type', '')
            if connection_type:
                # 映射连接类型到中文显示
                connection_type_map = {
                    'network': 'TCP/IP',
                    'serial': 'Serial',
                    'usb': 'USB',
                    'simulation': 'Simulation'
                }
                chinese_connection = connection_type_map.get(connection_type, connection_type)
                self.connection_type_combo.setCurrentText(chinese_connection)

            # 更新参数表单
            self.update_params_form(self.connection_type_combo.currentText())

            # 填充连接参数
            connection_params = self.config_data.get('connection_params', {})
            self._fill_connection_params(connection_params)

            # 设置描述
            if 'description' in self.config_data:
                self.description_input.setPlainText(self.config_data['description'])

        except Exception as e:
            logger.error(f"加载配置失败: {e}")

    def _fill_connection_params(self, connection_params):
        """填充连接参数到表单"""
        try:
            for i in range(self.params_form_layout.rowCount()):
                label_item = self.params_form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                field_item = self.params_form_layout.itemAt(i, QFormLayout.ItemRole.FieldRole)

                if label_item and field_item:
                    label_widget = label_item.widget()
                    field_widget = field_item.widget()

                    if label_widget and field_widget:
                        label_text = label_widget.text().replace(":", "").strip()

                        # 填充对应的值
                        if label_text in connection_params:
                            value = connection_params[label_text]

                            if isinstance(field_widget, QLineEdit):
                                field_widget.setText(str(value))
                            elif isinstance(field_widget, QSpinBox):
                                try:
                                    field_widget.setValue(int(value))
                                except (ValueError, TypeError):
                                    pass
                            elif isinstance(field_widget, QComboBox):
                                index = field_widget.findText(str(value))
                                if index >= 0:
                                    field_widget.setCurrentIndex(index)

        except Exception as e:
            logger.error(f"填充连接参数失败: {e}")

    def get_device_registry(self):
        """获取设备注册表（延迟初始化）"""
        try:
            from core.managers.device_registry import get_device_registry
            return get_device_registry()
        except Exception as e:
            logger.error(f"Failed to initialize device registry: {e}")
            return None


def show_hardware_config_dialog(config_data: Optional[Dict[str, Any]] = None, parent=None) -> Optional[Dict[str, Any]]:
    """
    显示硬件配置对话框的便捷函数

    Args:
        config_data: 现有配置数据（编辑模式），None表示添加模式
        parent: 父窗口

    Returns:
        配置数据字典，取消则返回None
    """
    dialog = HardwareConfigDialog(config_data, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.get_config()
    return None