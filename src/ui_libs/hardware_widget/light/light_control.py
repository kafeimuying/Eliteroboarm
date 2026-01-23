from typing import Dict, Any, Optional, List
import os
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QCheckBox, QSlider, QTextEdit, QMessageBox, QSplitter,
    QFileDialog, QProgressBar, QFrame, QFormLayout, QComboBox,
    QLineEdit, QDialogButtonBox, QDialog, QListWidget, QListWidgetItem, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QObject
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor
from core.managers.log_manager import info, debug, warning, error
from core import LightService

class LightControlTab(QWidget):
    """光源控制标签页 - 最终版"""

    def __init__(self, light_service: LightService, parent=None):
        super().__init__(parent)
        self.light_service = light_service
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()

        # 主内容区域
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：通道控制和实时状态（垂直布局）
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_top = self.create_channel_control_panel()
        left_bottom = self.create_light_status_panel()

        left_splitter.addWidget(left_top)
        left_splitter.addWidget(left_bottom)
        left_splitter.setSizes([400, 150])  # 控制区域更大，状态区域较小

        main_splitter.addWidget(left_splitter)

        # 右侧：预设和快速设置
        right_panel = self.create_light_settings_panel()
        main_splitter.addWidget(right_panel)

        main_splitter.setSizes([400, 300])
        layout.addWidget(main_splitter)

        self.setLayout(layout)

        # 启动状态更新定时器
        self.status_update_timer = QTimer()
        self.status_update_timer.timeout.connect(self.update_realtime_status)
        self.status_update_timer.start(500)  # 500ms更新一次

    def create_channel_control_panel(self):
        """创建通道控制面板"""
        group = QGroupBox("8通道控制")
        layout = QVBoxLayout()

        # 通道控制网格
        channel_layout = QGridLayout()
        self.channel_controls = []

        for i in range(8):
            row = i // 4
            col = (i % 4) * 4

            # 通道组
            channel_group = QGroupBox(f"通道 {i+1}")
            channel_inner = QVBoxLayout()

            # 启用开关
            enable_cb = QCheckBox()
            enable_cb.stateChanged.connect(lambda state, ch=i: self.on_channel_enable_changed(ch, state))
            channel_inner.addWidget(enable_cb)

            # 亮度滑块
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.valueChanged.connect(lambda value, ch=i: self.on_channel_brightness_changed(ch, value))
            channel_inner.addWidget(slider)

            # 亮度显示
            brightness_label = QLabel("0%")
            channel_inner.addWidget(brightness_label)

            channel_group.setLayout(channel_inner)
            channel_layout.addWidget(channel_group, row, col)

            self.channel_controls.append({
                'enable': enable_cb,
                'slider': slider,
                'label': brightness_label
            })

        layout.addLayout(channel_layout)

        # 全局控制
        global_layout = QHBoxLayout()

        set_all_btn = QPushButton("✅ 启用所有")
        set_all_btn.clicked.connect(self.enable_all_channels)
        set_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        global_layout.addWidget(set_all_btn)

        disable_all_btn = QPushButton("❌ 关闭所有")
        disable_all_btn.clicked.connect(self.disable_all_channels)
        disable_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        global_layout.addWidget(disable_all_btn)

        emergency_btn = QPushButton("🛑 紧急关闭")
        emergency_btn.clicked.connect(self.emergency_off)
        emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        global_layout.addWidget(emergency_btn)

        layout.addLayout(global_layout)

        group.setLayout(layout)
        return group

    def create_light_settings_panel(self):
        """创建光源设置面板"""
        group = QWidget()
        layout = QVBoxLayout()

        # 快速预设
        preset_group = QGroupBox("快速预设")
        preset_layout = QGridLayout()

        presets = [
            ("🌙 低光", [20, 10, 15, 10, 5, 5, 10, 5], "#9C27B0"),
            ("💡 标准", [50, 40, 45, 40, 35, 30, 40, 35], "#2196F3"),
            ("☀️ 高光", [80, 70, 75, 70, 65, 60, 70, 65], "#FF9800"),
            ("⚡ 全亮", [100, 100, 100, 100, 100, 100, 100, 100], "#f44336")
        ]

        for i, (name, values, color) in enumerate(presets):
            row = i // 2
            col = (i % 2) * 2

            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, v=values: self.apply_preset_values(v))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {color}DD;
                }}
            """)
            preset_layout.addWidget(btn, row, col)

        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        # 快速亮度控制
        brightness_group = QGroupBox("亮度控制")
        brightness_layout = QHBoxLayout()

        brightness_levels = [
            ("💡 关闭", 0, "#666666"),
            ("🔅 25%", 25, "#2196F3"),
            ("🔆 50%", 50, "#FF9800"),
            ("☀️ 75%", 75, "#FF5722"),
            ("⚡ 100%", 100, "#f44336")
        ]

        for text, level, color in brightness_levels:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, l=level: self.set_all_brightness(l))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: none;
                    padding: 6px 10px;
                    border-radius: 3px;
                    font-weight: bold;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {color}DD;
                }}
            """)
            brightness_layout.addWidget(btn)

        brightness_group.setLayout(brightness_layout)
        layout.addWidget(brightness_group)

        # 操作按钮
        actions_layout = QHBoxLayout()

        # 存储当前配置
        save_btn = QPushButton("💾 保存配置")
        save_btn.clicked.connect(self.save_current_config)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        actions_layout.addWidget(save_btn)

        # 紧急关闭
        emergency_btn = QPushButton("🛑 紧急关闭")
        emergency_btn.clicked.connect(self.emergency_off)
        emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        actions_layout.addWidget(emergency_btn)

        layout.addLayout(actions_layout)
        layout.addStretch()
        group.setLayout(layout)
        return group

    def create_light_status_panel(self):
        """创建光源状态面板"""
        group = QGroupBox("实时状态")
        layout = QVBoxLayout()

        # 连接控制
        connection_layout = QHBoxLayout()

        # 连接状态指示
        self.light_connection_indicator = QLabel("🔴 未连接")
        self.light_connection_indicator.setStyleSheet("""
            QLabel {
                background-color: #444;
                color: white;
                padding: 5px 15px;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        connection_layout.addWidget(self.light_connection_indicator)

        connection_layout.addStretch()

        # 连接按钮
        self.connect_light_btn = QPushButton("🔌 连接光源")
        self.connect_light_btn.clicked.connect(self.toggle_light_connection)
        self.connect_light_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        connection_layout.addWidget(self.connect_light_btn)

        layout.addLayout(connection_layout)

        # 状态信息
        status_layout = QGridLayout()

        self.active_channels_label = QLabel("0/8")
        self.active_channels_label.setStyleSheet("font-weight: bold; color: #2196F3; font-size: 14px;")
        status_layout.addWidget(QLabel("活动通道:"), 0, 0)
        status_layout.addWidget(self.active_channels_label, 0, 1)

        self.total_power_label = QLabel("0W")
        self.total_power_label.setStyleSheet("font-weight: bold; color: #FF9800; font-size: 14px;")
        status_layout.addWidget(QLabel("总功率:"), 1, 0)
        status_layout.addWidget(self.total_power_label, 1, 1)

        self.avg_brightness_label = QLabel("0%")
        self.avg_brightness_label.setStyleSheet("font-weight: bold; color: #4CAF50; font-size: 14px;")
        status_layout.addWidget(QLabel("平均亮度:"), 2, 0)
        status_layout.addWidget(self.avg_brightness_label, 2, 1)

        self.temperature_label = QLabel("--°C")
        self.temperature_label.setStyleSheet("font-weight: bold; color: #f44336; font-size: 14px;")
        status_layout.addWidget(QLabel("温度:"), 3, 0)
        status_layout.addWidget(self.temperature_label, 3, 1)

        layout.addLayout(status_layout)
        group.setLayout(layout)
        return group

    def on_channel_enable_changed(self, channel, state):
        """通道启用状态改变"""
        enabled = state == 2  # Qt.Checked
        result = self.light_service.enable_channel(channel, enabled)
        if not result['success']:
            logger.warning(f"启用通道{channel}失败: {result.get('error')}")

        # 更新活动通道数
        self.update_channel_count()

    def on_channel_brightness_changed(self, channel, value):
        """通道亮度改变"""
        self.channel_controls[channel]['label'].setText(f"{value}%")

        # 启用通道并设置亮度
        self.light_service.enable_channel(channel, True)
        result = self.light_service.set_brightness(channel, value)
        if not result['success']:
            logger.warning(f"设置通道{channel}亮度失败: {result.get('error')}")

        # 更新总功率估算
        self.update_power_estimate()

    def enable_all_channels(self):
        """启用所有通道"""
        result = self.light_service.enable_all_channels(True)
        if result['success']:
            # 更新UI
            for i in range(8):
                self.channel_controls[i]['enable'].setChecked(True)
        else:
            logger.warning(f"启用所有通道失败: {result.get('error')}")

        self.update_channel_count()
        self.update_power_estimate()

    def disable_all_channels(self):
        """关闭所有通道"""
        result = self.light_service.enable_all_channels(False)
        if result['success']:
            # 更新UI
            for i in range(8):
                self.channel_controls[i]['enable'].setChecked(False)
                self.channel_controls[i]['slider'].setValue(0)
        else:
            logger.warning(f"关闭所有通道失败: {result.get('error')}")

        self.update_channel_count()
        self.update_power_estimate()

    def set_all_brightness(self, brightness):
        """设置所有通道亮度"""
        result = self.light_service.set_all_brightness(brightness)
        if result['success']:
            # 更新UI
            for i in range(8):
                self.channel_controls[i]['enable'].setChecked(True)
                self.channel_controls[i]['slider'].setValue(brightness)
        else:
            logger.warning(f"设置所有通道亮度失败: {result.get('error')}")

        self.update_channel_count()
        self.update_power_estimate()

    def emergency_off(self):
        """紧急关闭"""
        reply = QMessageBox.question(
            self, "确认紧急关闭",
            "确定要紧急关闭所有光源通道吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            result = self.light_service.emergency_off()
            if result['success']:
                # 更新UI
                for i in range(8):
                    self.channel_controls[i]['enable'].setChecked(False)
                    self.channel_controls[i]['slider'].setValue(0)
                QMessageBox.warning(self, "紧急关闭", "所有光源通道已紧急关闭")
            else:
                logger.warning(f"紧急关闭失败: {result.get('error')}")

    def apply_preset(self, preset_name):
        """应用预设"""
        preset_configs = {
            "低光模式": [10, 10, 10, 10, 10, 10, 10, 10, 10],
            "高光模式": [90, 90, 90, 90, 90, 90, 90, 90, 90],
            "环形光": [80, 30, 80, 30, 80, 80, 30, 80, 30],
            "对称光": [70, 70, 70, 70, 30, 30, 30, 30, 30]
        }

        if preset_name not in preset_configs:
            return

        brightness_values = preset_configs[preset_name]
        result = self.light_service.enable_all_channels(True)

        if result['success']:
            for i, brightness in enumerate(brightness_values):
                set_result = self.light_service.set_brightness(i, brightness)
                if set_result['success']:
                    self.channel_controls[i]['enable'].setChecked(True)
                    self.channel_controls[i]['slider'].setValue(brightness)
                else:
                    logger.warning(f"设置通道{i}预设失败")

            QMessageBox.information(self, "预设应用", f"已应用预设: {preset_name}")
        else:
            logger.warning(f"应用预设失败: {result.get('error')}")

    def show_advanced_settings(self):
        """显示高级设置"""
        QMessageBox.information(self, "高级设置", "高级光源设置功能正在开发中\n\n"
            "将包含:\n"
            "• 自定义预设编辑\n"
            "• 定时控制设置\n"
            "• 触发模式配置\n"
            "• 安全参数调整\n"
            "• 通讯参数配置")

    def update_channel_count(self):
        """更新通道数显示"""
        enabled_count = sum(1 for i in range(8) if self.channel_controls[i]['enable'].isChecked())
        self.active_channels_label.setText(f"{enabled_count}/8")

    def update_power_estimate(self):
        """更新功率估算"""
        try:
            # 估算总功率（假设每通道最大5W）
            total_power = sum(
                self.channel_controls[i]['slider'].value() * 0.05
                for i in range(8) if self.channel_controls[i]['enable'].isChecked()
            )
            self.total_power_label.setText(f"{total_power:.1f}W")
        except:
            self.total_power_label.setText("未知")

    def toggle_light_connection(self):
        """切换光源连接"""
        if self.light_service.is_connected():
            result = self.light_service.disconnect()
            if result['success']:
                self.light_status_label.setText("🔴 未连接")
                self.connect_btn.setText("连接")
        else:
            # 模拟连接
            self.light_status_label.setText("🟡 连接中(模拟)...")
            self.connect_btn.setText("断开")
            logger.info("模拟连接光源控制器")
            # 模拟连接成功
            self.light_status_label.setText("🟢 已连接")
            self.connect_btn.setText("断开")

    def show_light_config(self):
        """显示光源配置"""
        # 创建配置对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("光源配置")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout()

        # 配置信息
        config_text = QTextEdit()
        config_text.setPlainText(
            "光源控制器配置选项:\n\n"
            "连接配置:\n"
            "- IP地址: 控制器网络地址 (例: 192.168.0.3)\n"
            "- 端口: TCP/IP端口号 (例: 8080)\n"
            "- 超时时间: 连接超时秒数\n"
            "- 通道数量: 可用通道数 (1-8)\n\n"
            "通道配置:\n"
            "- 默认亮度: 启动时的亮度值\n"
            "- 最大亮度: 安全最大亮度限制\n"
            "- 触发模式: 硬件/软件触发\n"
            "- 触发延迟: 触发响应延迟\n"
            "- 触发极性: 上升沿/下降沿\n\n"
            "当前使用模拟模式，无需实际配置。"
        )
        config_text.setReadOnly(True)
        layout.addWidget(config_text)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.exec()

    def toggle_light_connection(self):
        """切换光源连接状态"""
        if not hasattr(self, 'light_connected'):
            self.light_connected = False

        if not self.light_connected:
            # 连接光源
            self.light_connected = True
            self.light_connection_indicator.setText("🟢 已连接")
            self.light_connection_indicator.setStyleSheet("""
                QLabel {
                    background-color: #4CAF50;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
            """)
            self.connect_light_btn.setText("🔌 断开光源")
            self.connect_light_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
            logger.info("光源已连接")
        else:
            # 断开光源
            self.light_connected = False
            self.light_connection_indicator.setText("🔴 未连接")
            self.light_connection_indicator.setStyleSheet("""
                QLabel {
                    background-color: #444;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
            """)
            self.connect_light_btn.setText("🔌 连接光源")
            self.connect_light_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
            # 关闭所有通道
            self.emergency_off()
            logger.info("光源已断开")

    def apply_preset_values(self, values):
        """应用预设值"""
        try:
            for i, brightness in enumerate(values):
                if i < len(self.channel_controls):
                    # 设置滑块值
                    self.channel_controls[i]['slider'].setValue(brightness)
                    # 更新显示
                    self.channel_controls[i]['label'].setText(f"{brightness}%")
                    # 启用通道
                    self.channel_controls[i]['enable'].setChecked(True)

            logger.info(f"应用光源预设: {values}")

        except Exception as e:
            logger.error(f"应用预设失败: {e}")

    def update_realtime_status(self):
        """更新实时状态"""
        try:
            if not hasattr(self, 'light_connected') or not self.light_connected:
                # 重置状态
                self.active_channels_label.setText("0/8")
                self.total_power_label.setText("0W")
                self.avg_brightness_label.setText("0%")
                self.temperature_label.setText("--°C")
                return

            # 计算活动通道数
            active_count = 0
            total_brightness = 0
            total_power = 0

            for i, control in enumerate(self.channel_controls):
                if control['enable'].isChecked():
                    active_count += 1
                    brightness = control['slider'].value()
                    total_brightness += brightness
                    # 估算功率 (假设每个通道最大10W)
                    total_power += (brightness / 100.0) * 10

            # 更新显示
            self.active_channels_label.setText(f"{active_count}/8")
            self.total_power_label.setText(f"{total_power:.1f}W")

            # 平均亮度
            avg_brightness = total_brightness / 8 if active_count > 0 else 0
            self.avg_brightness_label.setText(f"{avg_brightness:.0f}%")

            # 模拟温度 (基于功率的简单估算)
            if total_power > 0:
                import random
                base_temp = 25 + (total_power * 0.5)  # 基础温度 + 功率导致的温度升高
                temp_variation = random.uniform(-2, 2)  # 随机波动
                temperature = base_temp + temp_variation
                self.temperature_label.setText(f"{temperature:.1f}°C")

                # 温度颜色警告
                if temperature > 60:
                    self.temperature_label.setStyleSheet("font-weight: bold; color: #d32f2f; font-size: 16px;")
                elif temperature > 45:
                    self.temperature_label.setStyleSheet("font-weight: bold; color: #FF9800; font-size: 16px;")
                else:
                    self.temperature_label.setStyleSheet("font-weight: bold; color: #4CAF50; font-size: 16px;")
            else:
                self.temperature_label.setText("--°C")

        except Exception as e:
            logger.error(f"更新光源状态失败: {e}")

    def save_current_config(self):
        """保存当前配置"""
        try:
            config = {
                'timestamp': time.time(),
                'channels': []
            }

            for i, control in enumerate(self.channel_controls):
                config['channels'].append({
                    'id': i + 1,
                    'enabled': control['enable'].isChecked(),
                    'brightness': control['slider'].value()
                })

            # 保存到文件
            config_dir = "configs"
            os.makedirs(config_dir, exist_ok=True)

            filename = f"light_config_{int(time.time())}.json"
            filepath = os.path.join(config_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "保存成功", f"光源配置已保存到: {filepath}")
            logger.info(f"光源配置已保存: {filepath}")

        except Exception as e:
            logger.error(f"保存光源配置失败: {e}")
            QMessageBox.warning(self, "保存失败", f"保存配置失败: {str(e)}")


