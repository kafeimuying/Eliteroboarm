#!/usr/bin/env python3
"""
VMC节点参数配置对话框模块

提供各种VMC节点的参数配置对话框功能
"""

import os
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QLineEdit,
    QSpinBox, QDoubleSpinBox, QMessageBox, QGroupBox, QScrollArea,
    QCheckBox, QColorDialog, QFileDialog, QWidget, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt
from core.interfaces.algorithm.base.algorithm_base import ParameterType, AlgorithmParameter, AlgorithmInfo
from core.managers.log_manager import debug, info, warning, error, LogCategory

# 测试导入是否成功
try:
    # 验证 ParameterType 导入
    test_param_type = ParameterType.INT
    debug(f"node_parameter_dialogs: ParameterType import successful - {test_param_type}", "NodeParameterDialogs")

    # 验证 AlgorithmParameter 导入
    test_param = AlgorithmParameter("test", ParameterType.INT, 0, description="Test parameter")
    debug(f"node_parameter_dialogs: AlgorithmParameter import successful - {test_param.name}", "NodeParameterDialogs")

    # 验证 AlgorithmInfo 导入 (如果需要的话)
    debug("node_parameter_dialogs: All core imports successful", "NodeParameterDialogs")

except Exception as e:
    error(f"node_parameter_dialogs: Import test failed: {e}", "NodeParameterDialogs")


class CameraParameterDialog(QDialog):
    """相机节点参数配置对话框"""
    
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"相机参数配置 - {node.node_id}")
        self.setMinimumSize(500, 400)
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout()
        
        # 相机选择组
        camera_group = QGroupBox("相机选择")
        camera_layout = QFormLayout()
        
        # 相机选择下拉框
        self.camera_combo = QComboBox()
        self.camera_combo.addItem("选择相机...")
        
        # 从硬件配置中填充相机选项
        for camera_id, camera_info in self.node.hardware_config.items():
            display_name = f"{camera_info.get('name', camera_id)} ({camera_info.get('brand', 'Unknown')} - {camera_info.get('model', 'Unknown')})"
            self.camera_combo.addItem(display_name, camera_id)
            
        # 如果已配置，设置当前选择
        if self.node.selected_hardware_id and self.node.selected_hardware_id in self.node.hardware_config:
            for i in range(self.camera_combo.count()):
                if self.camera_combo.itemData(i) == self.node.selected_hardware_id:
                    self.camera_combo.setCurrentIndex(i)
                    break
        
        camera_layout.addRow("相机设备:", self.camera_combo)
        camera_group.setLayout(camera_layout)
        layout.addWidget(camera_group)
        
        # 相机参数组
        params_group = QGroupBox("相机参数")
        params_layout = QFormLayout()
        
        # 通用相机参数
        self.exposure_spin = QDoubleSpinBox()
        self.exposure_spin.setRange(0.001, 1000)
        self.exposure_spin.setDecimals(3)
        self.exposure_spin.setSuffix(" ms")
        self.exposure_spin.setValue(10.0)
        
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(0.0, 100.0)
        self.gain_spin.setDecimals(2)
        self.gain_spin.setValue(1.0)
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(30)
        
        params_layout.addRow("曝光时间:", self.exposure_spin)
        params_layout.addRow("增益:", self.gain_spin)
        params_layout.addRow("帧率:", self.fps_spin)
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # 连接相机选择变化事件
        self.camera_combo.currentTextChanged.connect(self.on_camera_changed)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        test_btn = QPushButton("测试连接")
        capture_btn = QPushButton("拍照测试")
        
        test_btn.clicked.connect(self.test_connection)
        capture_btn.clicked.connect(self.test_capture)
        
        button_layout.addWidget(test_btn)
        button_layout.addWidget(capture_btn)
        button_layout.addStretch()
        
        # 确定/取消按钮
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        
        ok_btn.clicked.connect(self.save_config)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def on_camera_changed(self):
        """相机选择变化时更新参数"""
        selected_id = self.camera_combo.currentData()
        if selected_id and selected_id in self.node.hardware_config:
            camera_info = self.node.hardware_config[selected_id]
            # 从配置中更新参数值
            if 'fps' in camera_info:
                self.fps_spin.setValue(camera_info['fps'])
            if 'connection_params' in camera_info:
                params = camera_info['connection_params']
                if 'exposure' in params:
                    self.exposure_spin.setValue(params['exposure'])
                if 'gain' in params:
                    self.gain_spin.setValue(params['gain'])
    
    def test_connection(self):
        """测试相机连接"""
        selected_id = self.camera_combo.currentData()
        if not selected_id:
            QMessageBox.warning(self, "警告", "请先选择相机设备")
            return
            
        try:
            from core.services.camera_service import CameraService
            camera_service = CameraService.get_camera_service(selected_id)
            if camera_service and camera_service.is_connected():
                QMessageBox.information(self, "连接测试", "相机连接成功！")
            else:
                QMessageBox.warning(self, "连接测试", "相机连接失败")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接测试失败: {e}")
    
    def test_capture(self):
        """测试拍照"""
        selected_id = self.camera_combo.currentData()
        if not selected_id:
            QMessageBox.warning(self, "警告", "请先选择相机设备")
            return
            
        try:
            from core.services.camera_service import CameraService
            camera_service = CameraService.get_camera_service(selected_id)
            if camera_service:
                frame = camera_service.capture_frame()
                if frame is not None:
                    QMessageBox.information(self, "拍照测试", f"拍照成功！图像尺寸: {frame.shape}")
                else:
                    QMessageBox.warning(self, "拍照测试", "拍照失败")
            else:
                QMessageBox.warning(self, "拍照测试", "无法创建相机服务")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"拍照测试失败: {e}")
    
    def save_config(self):
        """保存配置"""
        selected_id = self.camera_combo.currentData()
        if selected_id:
            self.node.selected_hardware_id = selected_id
            # 存储相机参数
            self.node.camera_params = {
                'exposure': self.exposure_spin.value(),
                'gain': self.gain_spin.value(),
                'fps': self.fps_spin.value()
            }
            # 更新节点标题
            camera_info = self.node.hardware_config[selected_id]
            self.node.title_item.setPlainText(f"相机: {camera_info.get('name', selected_id)}")
            
            # 触发配置保存到VMC缓存
            try:
                if hasattr(self.node, 'canvas') and hasattr(self.node.canvas, 'parent_dialog') and hasattr(self.node.canvas.parent_dialog, '_save_vmc_config_to_cache'):
                    # 生成VMC配置
                    vmc_config = self.node.canvas.parent_dialog._generate_vmc_config()
                    self.node.canvas.parent_dialog._save_vmc_config_to_cache(vmc_config)
                    debug(f"CameraParameterDialog: Triggered VMC configuration save to cache", "NodeParameterDialogs")
            except Exception as e:
                debug(f"CameraParameterDialog: Failed to save VMC configuration to cache: {e}", "NodeParameterDialogs")
            
            QMessageBox.information(self, "成功", f"已配置相机: {camera_info.get('name', selected_id)}")
            self.accept()
        else:
            QMessageBox.warning(self, "警告", "请选择相机设备")


class VisionAlgorithmParameterDialog(QDialog):
    """视觉算法参数配置对话框"""
    
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.param_widgets = {}

        # Load available algorithms
        self.available_algorithms = self._load_available_algorithms()

        # Handle case where algorithm is None
        if node.algorithm is None:
            algorithm_name = "未配置算法"
            self.selected_algorithm_id = None
        else:
            try:
                algorithm_name = node.algorithm.get_info().display_name
                # Try to get algorithm ID from algorithm instance
                self.selected_algorithm_id = getattr(node.algorithm, '_algorithm_id', None)
            except Exception:
                algorithm_name = "算法信息获取失败"
                self.selected_algorithm_id = None

        self.setWindowTitle(f"视觉算法参数配置 - {algorithm_name}")
        self.setMinimumSize(600, 500)
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout()
        
        
        # 配置文件选择区域
        config_group = QGroupBox("配置文件选择")
        config_layout = QVBoxLayout()

        # 配置文件下拉选择
        self.config_combo = QComboBox()
        self.config_combo.addItem("请选择配置文件...", None)
        self._load_config_files()

        # 文件选择按钮
        file_button_layout = QHBoxLayout()
        self.browse_config_btn = QPushButton("浏览文件...")
        self.browse_config_btn.clicked.connect(self._browse_config_file)
        file_button_layout.addWidget(self.browse_config_btn)

        config_layout.addWidget(QLabel("选择配置文件:"))
        config_layout.addWidget(self.config_combo)
        config_layout.addLayout(file_button_layout)
        config_group.setLayout(config_layout)

        layout.addWidget(config_group)

        # 存储配置数据
        self.config_data = None
        self.selected_config_file = None

        # 算法信息组
        info_group = QGroupBox("当前算法信息")
        info_layout = QFormLayout()

        if self.node.algorithm is None:
            info_layout.addRow("算法名称:", QLabel("未配置"))
            info_layout.addRow("算法描述:", QLabel("此视觉节点尚未配置算法"))
            info_layout.addRow("算法版本:", QLabel("-"))
            info_layout.addRow("算法分类:", QLabel("-"))
        else:
            try:
                algo_info = self.node.algorithm.get_info()
                info_layout.addRow("算法名称:", QLabel(algo_info.display_name))
                info_layout.addRow("算法描述:", QLabel(algo_info.description))
                info_layout.addRow("算法版本:", QLabel(algo_info.version))
                info_layout.addRow("算法分类:", QLabel(f"{algo_info.category} - {algo_info.secondary_category}"))
            except Exception as e:
                info_layout.addRow("算法名称:", QLabel("信息获取失败"))
                info_layout.addRow("算法描述:", QLabel(f"错误: {str(e)}"))
                info_layout.addRow("算法版本:", QLabel("-"))
                info_layout.addRow("算法分类:", QLabel("-"))

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 参数组（带滚动区域）
        params_group = QGroupBox("算法参数")
        params_scroll = QScrollArea()
        params_scroll.setWidgetResizable(True)
        params_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        params_widget = QWidget()
        params_layout = QFormLayout(params_widget)
        
        # 获取算法参数
        if self.node.algorithm is not None and hasattr(self.node.algorithm, 'get_parameters'):
            try:
                parameters = self.node.algorithm.get_parameters()
                if parameters:
                    for param in parameters:
                        widget = self.create_parameter_widget(param)
                        if widget:
                            self.param_widgets[param.name] = widget
                            params_layout.addRow(f"{param.name}:", widget)

                            # 添加参数描述
                            if param.description:
                                desc_label = QLabel(f"说明: {param.description}")
                                desc_label.setWordWrap(True)
                                desc_label.setStyleSheet("color: gray; font-size: 10px; margin-left: 10px;")
                                params_layout.addRow("", desc_label)
                else:
                    params_layout.addRow("状态:", QLabel("此算法没有可配置的参数"))
            except Exception as e:
                params_layout.addRow("状态:", QLabel(f"获取参数失败: {str(e)}"))
        else:
            params_layout.addRow("状态:", QLabel("此节点未配置算法，无法显示参数"))
        
        params_widget.setLayout(params_layout)
        params_scroll.setWidget(params_widget)
        params_group.setLayout(QVBoxLayout())
        params_group.layout().addWidget(params_scroll)
        layout.addWidget(params_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        test_btn = QPushButton("测试算法")
        test_btn.clicked.connect(self.test_algorithm)
        
        # 确定/取消按钮
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")

        ok_btn.clicked.connect(self.save_parameters)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(test_btn)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def create_parameter_widget(self, param):
        """根据参数类型创建合适的控件"""
        if param.param_type == ParameterType.INT:
            widget = QSpinBox()
            widget.setMinimum(param.min_value if param.min_value is not None else -999999)
            widget.setMaximum(param.max_value if param.max_value is not None else 999999)
            widget.setValue(int(param.default_value))
            
        elif param.param_type == ParameterType.FLOAT:
            widget = QDoubleSpinBox()
            widget.setMinimum(float(param.min_value if param.min_value is not None else -999999.0))
            widget.setMaximum(float(param.max_value if param.max_value is not None else 999999.0))
            widget.setValue(float(param.default_value))
            widget.setDecimals(4)
            
        elif param.param_type == ParameterType.BOOL:
            widget = QCheckBox()
            widget.setChecked(bool(param.default_value))
            
        elif param.param_type == ParameterType.STRING:
            widget = QLineEdit()
            widget.setText(str(param.default_value))
            
        elif param.param_type == ParameterType.COLOR:
            widget = QPushButton()
            color_value = str(param.default_value)
            widget.setStyleSheet(f"background-color: {color_value};")
            widget.clicked.connect(lambda checked, w=widget: self.choose_color(w))
            
        elif param.param_type == ParameterType.FILE_PATH:
            widget = QPushButton()
            widget.setText("选择文件...")
            widget.clicked.connect(lambda checked, w=widget: self.choose_file(w))
            
        elif param.param_type == ParameterType.DIRECTORY_PATH:
            widget = QPushButton()
            widget.setText("选择目录...")
            widget.clicked.connect(lambda checked, w=widget: self.choose_directory(w))
            
        else:
            # 默认使用行编辑框
            widget = QLineEdit()
            widget.setText(str(param.default_value))
        
        return widget
    
    def choose_color(self, button):
        """选择颜色"""
        color = QColorDialog.getColor()
        if color.isValid():
            color_hex = color.name()
            button.setStyleSheet(f"background-color: {color_hex};")
            button._value = color_hex

    def choose_file(self, button):
        """选择文件"""
        file_path, _ = QFileDialog.getOpenFileName(button, "选择文件")
        if file_path:
            button.setText(file_path.split('/')[-1])  # 只显示文件名
            button._value = file_path

    def choose_directory(self, button):
        """选择目录"""
        dir_path = QFileDialog.getExistingDirectory(button, "选择目录")
        if dir_path:
            button.setText(dir_path.split('/')[-1])  # 只显示目录名
            button._value = dir_path
    
    def test_algorithm(self):
        """测试算法"""
        if self.node.algorithm is None:
            QMessageBox.warning(self, "测试警告", "此节点未配置算法，无法进行测试。")
            return

        try:
            # 从控件更新算法参数
            self.update_algorithm_parameters()

            # 使用测试图像测试
            import numpy as np
            test_image = np.zeros((100, 100, 3), dtype=np.uint8)
            result = self.node.execute_vision_task(test_image)

            if result and hasattr(result, 'success') and result.success:
                QMessageBox.information(self, "测试成功", "算法执行成功！")
            else:
                QMessageBox.warning(self, "测试警告", "算法执行未成功，请检查参数设置。")

        except Exception as e:
            QMessageBox.critical(self, "测试错误", f"算法测试失败: {e}")
    
    def update_algorithm_parameters(self):
        """从控件更新算法参数"""
        if self.node.algorithm is not None and hasattr(self.node.algorithm, 'get_parameters'):
            try:
                parameters = self.node.algorithm.get_parameters()
                if parameters:
                    for param in parameters:
                        widget = self.param_widgets.get(param.name)
                        if widget:
                            # 根据参数类型获取值
                            if param.param_type == ParameterType.INT:
                                value = widget.value()
                            elif param.param_type == ParameterType.FLOAT:
                                value = widget.value()
                            elif param.param_type == ParameterType.BOOL:
                                value = widget.isChecked()
                            elif param.param_type == ParameterType.STRING:
                                value = widget.text()
                            elif param.param_type in [ParameterType.COLOR, ParameterType.FILE_PATH, ParameterType.DIRECTORY_PATH]:
                                value = getattr(widget, '_value', str(param.default_value))
                            else:
                                value = widget.text()

                            # 设置算法参数
                            if hasattr(self.node.algorithm, 'set_parameter'):
                                self.node.algorithm.set_parameter(param.name, value)
            except Exception as e:
                QMessageBox.warning(self, "参数更新警告", f"更新参数时出错: {str(e)}")
    
    def _load_available_algorithms(self):
        """加载可用的视觉算法"""
        try:
            from core import AlgorithmManager
            from core.managers.app_config import AppConfigManager

            # 创建算法管理器
            log_manager = AppConfigManager().get_log_manager()
            algorithm_manager = AlgorithmManager(log_manager)
            registry = algorithm_manager.get_registry()

            # 获取所有算法信息
            all_algorithms = registry.get_all_algorithms()

            # 过滤出视觉算法 (基础算子、高级算子、组合算法中的视觉相关算法)
            vision_algorithms = {}
            for algo_id, algo_info in all_algorithms.items():
                # 包含视觉相关分类的算法
                if any(keyword in algo_info.category.lower() or
                       keyword in algo_info.secondary_category.lower() or
                       any(keyword in tag.lower() for tag in algo_info.tags)
                       for keyword in ['视觉', 'vision', '图像', 'image', '检测', 'detection', '分割', 'segmentation', '预处理', '边缘', 'edge']):
                    vision_algorithms[algo_id] = algo_info

            debug(f"Loaded {len(vision_algorithms)} vision algorithms", "NodeParameterDialogs")
            return vision_algorithms

        except Exception as e:
            error(f"Failed to load available algorithms: {e}", "NodeParameterDialogs")
            return {}

    def save_parameters(self):
        """保存参数"""
        try:
            # 加载选择的配置文件
            self._load_selected_config()

            # 保存配置数据到节点（不要求有算法）
            selected_config = self.get_selected_config()
            if selected_config is not None:
                self.node.vision_config = selected_config
                self.node.vision_config_file = getattr(self, 'selected_config_file', None)
                debug(f"Saved vision config to node {self.node.node_id}, items: {len(selected_config)}", "NodeParameterDialogs")

                # 触发配置保存到VMC缓存
                try:
                    if hasattr(self.node, 'canvas') and hasattr(self.node.canvas, 'parent_dialog') and hasattr(self.node.canvas.parent_dialog, '_save_vmc_config_to_cache'):
                        # 生成VMC配置
                        vmc_config = self.node.canvas.parent_dialog._generate_vmc_config()
                        self.node.canvas.parent_dialog._save_vmc_config_to_cache(vmc_config)
                        debug(f"VisionAlgorithmParameterDialog: Triggered VMC configuration save to cache", "NodeParameterDialogs")
                except Exception as e:
                    debug(f"VisionAlgorithmParameterDialog: Failed to save VMC configuration to cache: {e}", "NodeParameterDialogs")

                QMessageBox.information(self, "成功", f"配置已保存！\n配置文件: {os.path.basename(self.selected_config_file) if self.selected_config_file else '未知'}")
                self.accept()
            else:
                QMessageBox.warning(self, "警告", "请先选择一个配置文件。")
                return

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存参数失败: {e}")

    
    def _load_config_files(self):
        """加载配置文件到下拉框"""
        try:
            from core.managers.app_config import AppConfigManager
            app_config = AppConfigManager()
            pipeline_dir = app_config.pipeline_dir

            # 清空现有的配置文件（除了第一个占位项）
            self.config_combo.clear()
            self.config_combo.addItem("请选择配置文件...", None)

            # 添加pipeline目录下的所有JSON文件
            if pipeline_dir.exists():
                config_files = list(pipeline_dir.glob("*.json"))
                for config_file in sorted(config_files):
                    display_text = f"{config_file.stem} (默认)"
                    self.config_combo.addItem(display_text, str(config_file))
                    debug(f"Added config file to dropdown: {config_file.stem}", "NodeParameterDialogs")
            else:
                # 如果目录不存在，添加提示项
                self.config_combo.addItem("无配置文件目录", None)

            debug(f"Loaded {len(config_files) if 'config_files' in locals() else 0} config files to dropdown", "NodeParameterDialogs")

        except Exception as e:
            error(f"Failed to load config files: {e}", "NodeParameterDialogs")
            # 添加错误提示项
            self.config_combo.clear()
            self.config_combo.addItem("加载配置失败", None)

    def _browse_config_file(self):
        """浏览配置文件"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择配置文件",
                "",  # 默认目录
                "JSON 配置文件 (*.json);;所有文件 (*.*)"
            )
            if file_path:
                # 检查文件是否已在下拉框中
                for i in range(self.config_combo.count()):
                    if self.config_combo.itemData(i) == file_path:
                        self.config_combo.setCurrentIndex(i)
                        return

                # 添加到下拉框
                display_text = f"{os.path.basename(file_path)} (自定义)"
                self.config_combo.addItem(display_text, file_path)
                self.config_combo.setCurrentIndex(self.config_combo.count() - 1)

                debug(f"Selected config file: {file_path}", "NodeParameterDialogs")

        except Exception as e:
            error(f"Failed to browse config file: {e}", "NodeParameterDialogs")

    def _load_selected_config(self):
        """加载选择的配置文件"""
        try:
            config_path = self.config_combo.currentData()
            if not config_path:
                debug("No config file selected", "NodeParameterDialogs")
                return None

            debug(f"Loading config from: {config_path}", "NodeParameterDialogs")
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                self.config_data = loaded_data
                self.selected_config_file = config_path

            debug(f"Successfully loaded config from: {config_path}, items: {len(self.config_data) if isinstance(self.config_data, dict) else 'unknown'}", "NodeParameterDialogs")
            debug(f"Config data stored in self.config_data: {type(self.config_data)}", "NodeParameterDialogs")
            return self.config_data

        except json.JSONDecodeError as e:
            error(f"Config file format error: {e}", "NodeParameterDialogs")
            QMessageBox.critical(self, "错误", f"配置文件格式错误: {e}")
            return None
        except Exception as e:
            error(f"Failed to load config file: {e}", "NodeParameterDialogs")
            QMessageBox.critical(self, "错误", f"加载配置文件失败: {e}")
            return None

    def get_selected_config(self):
        """获取当前选择的配置"""
        if self.config_data is None:
            debug("get_selected_config called, self.config_data: None", "NodeParameterDialogs")
        else:
            debug(f"get_selected_config called, self.config_data: {type(self.config_data)}", "NodeParameterDialogs")
        return self.config_data

    def _preview_algorithm_parameters(self, algorithm_id):
        """预览算法参数（不应用到节点）"""
        try:
            from core import AlgorithmManager
            from core.managers.app_config import AppConfigManager

            # 创建算法管理器
            log_manager = AppConfigManager().get_log_manager()
            algorithm_manager = AlgorithmManager(log_manager)

            # 创建临时算法实例用于预览参数
            temp_algorithm = algorithm_manager.get_registry().create_algorithm_instance(algorithm_id)
            if temp_algorithm and hasattr(temp_algorithm, 'get_parameters'):
                parameters = temp_algorithm.get_parameters()
                # 这里可以显示参数预览，但暂时不实现
                debug(f"Algorithm {algorithm_id} has {len(parameters) if parameters else 0} parameters", "NodeParameterDialogs")

        except Exception as e:
            debug(f"Failed to preview algorithm parameters: {e}", "NodeParameterDialogs")

    def _apply_selected_algorithm(self, algorithm_id):
        """应用选择的算法到节点"""
        try:
            from core import AlgorithmManager
            from core.managers.app_config import AppConfigManager

            # 创建算法管理器
            log_manager = AppConfigManager().get_log_manager()
            algorithm_manager = AlgorithmManager(log_manager)

            # 创建算法实例
            algorithm = algorithm_manager.get_registry().create_algorithm_instance(algorithm_id)
            if algorithm:
                # 设置算法ID以便后续识别
                algorithm._algorithm_id = algorithm_id

                # 更新节点算法
                self.node.algorithm = algorithm
                self.selected_algorithm_id = algorithm_id

                # 更新节点显示名称
                algo_info = algorithm.get_info()
                self.node.set_content(algo_info.display_name)

                # 更新窗口标题
                self.setWindowTitle(f"视觉算法参数配置 - {algo_info.display_name}")

                # 重新加载参数界面
                self._reload_parameters_section()

                debug(f"Applied algorithm {algorithm_id} to node {self.node.node_id}", "NodeParameterDialogs")
            else:
                QMessageBox.warning(self, "警告", f"无法创建算法实例: {algorithm_id}")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"应用算法失败: {e}")

    def _reload_parameters_section(self):
        """重新加载参数部分"""
        try:
            # 重新设置参数区域
            # 这里需要重新构建参数界面，暂时简化处理
            # 在实际应用中，可以只更新参数部分而不重建整个界面
            debug("Parameters section needs to be reloaded", "NodeParameterDialogs")
        except Exception as e:
            debug(f"Failed to reload parameters section: {e}", "NodeParameterDialogs")


class RobotParameterDialog(QDialog):
    """机器人节点参数配置对话框"""
    
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"机器人参数配置 - {node.node_id}")
        self.setMinimumSize(500, 400)
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout()
        
        # 机器人选择组
        robot_group = QGroupBox("机器人选择")
        robot_layout = QFormLayout()
        
        # 机器人选择下拉框
        self.robot_combo = QComboBox()
        self.robot_combo.addItem("选择机器人...")
        
        # 从硬件配置中填充机器人选项
        for robot_id, robot_info in self.node.robot_config.items():
            display_name = f"{robot_info.get('name', robot_id)} ({robot_info.get('brand', 'Unknown')} - {robot_info.get('model', 'Unknown')})"
            self.robot_combo.addItem(display_name, robot_id)
            
        # 如果已配置，设置当前选择
        if self.node.selected_hardware_id and self.node.selected_hardware_id in self.node.robot_config:
            for i in range(self.robot_combo.count()):
                if self.robot_combo.itemData(i) == self.node.selected_hardware_id:
                    self.robot_combo.setCurrentIndex(i)
                    break
        
        robot_layout.addRow("机器人设备:", self.robot_combo)
        robot_group.setLayout(robot_layout)
        layout.addWidget(robot_group)
        
        # 机器人参数组
        params_group = QGroupBox("机器人参数")
        params_layout = QFormLayout()
        
        # 运动速度参数
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 100.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSuffix(" mm/s")
        self.speed_spin.setValue(50.0)
        
        # 加速度参数
        self.accel_spin = QDoubleSpinBox()
        self.accel_spin.setRange(1.0, 1000.0)
        self.accel_spin.setDecimals(2)
        self.accel_spin.setSuffix(" mm/s²")
        self.accel_spin.setValue(200.0)
        
        # 精度参数
        self.precision_spin = QDoubleSpinBox()
        self.precision_spin.setRange(0.01, 10.0)
        self.precision_spin.setDecimals(3)
        self.precision_spin.setSuffix(" mm")
        self.precision_spin.setValue(0.1)
        
        params_layout.addRow("运动速度:", self.speed_spin)
        params_layout.addRow("加速度:", self.accel_spin)
        params_layout.addRow("定位精度:", self.precision_spin)
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        test_btn = QPushButton("测试连接")
        move_btn = QPushButton("移动测试")
        
        test_btn.clicked.connect(self.test_connection)
        move_btn.clicked.connect(self.test_move)
        
        button_layout.addWidget(test_btn)
        button_layout.addWidget(move_btn)
        button_layout.addStretch()
        
        # 确定/取消按钮
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        
        ok_btn.clicked.connect(self.save_config)
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def test_connection(self):
        """测试机器人连接"""
        selected_id = self.robot_combo.currentData()
        if not selected_id:
            QMessageBox.warning(self, "警告", "请先选择机器人设备")
            return
            
        try:
            from core.services.robot_service import RobotService
            robot_service = RobotService.get_robot_service(selected_id)
            if robot_service and robot_service.is_connected():
                QMessageBox.information(self, "连接测试", "机器人连接成功！")
            else:
                QMessageBox.warning(self, "连接测试", "机器人连接失败")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"连接测试失败: {e}")
    
    def test_move(self):
        """测试机器人移动"""
        selected_id = self.robot_combo.currentData()
        if not selected_id:
            QMessageBox.warning(self, "警告", "请先选择机器人设备")
            return
            
        try:
            from core.services.robot_service import RobotService
            robot_service = RobotService.get_robot_service(selected_id)
            if robot_service:
                # 执行一个小的测试移动（例如，移动到零点附近）
                test_position = [0.0, 0.0, 100.0, 0.0, 90.0, 0.0]  # 安全的测试位置
                result = robot_service.move_joints(test_position)
                
                if result.get('success', False):
                    QMessageBox.information(self, "移动测试", "机器人移动测试成功！")
                else:
                    QMessageBox.warning(self, "移动测试", f"机器人移动失败: {result.get('error', 'Unknown error')}")
            else:
                QMessageBox.warning(self, "移动测试", "无法创建机器人服务")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"移动测试失败: {e}")
    
    def save_config(self):
        """保存配置"""
        selected_id = self.robot_combo.currentData()
        if selected_id:
            self.node.selected_hardware_id = selected_id
            # 存储机器人参数
            self.node.robot_params = {
                'speed': self.speed_spin.value(),
                'acceleration': self.accel_spin.value(),
                'precision': self.precision_spin.value()
            }
            # 更新节点标题
            robot_info = self.node.robot_config[selected_id]
            self.node.title_item.setPlainText(f"机器人: {robot_info.get('name', selected_id)}")
            
            # 触发配置保存到VMC缓存
            try:
                if hasattr(self.node, 'canvas') and hasattr(self.node.canvas, 'parent_dialog') and hasattr(self.node.canvas.parent_dialog, '_save_vmc_config_to_cache'):
                    # 生成VMC配置
                    vmc_config = self.node.canvas.parent_dialog._generate_vmc_config()
                    self.node.canvas.parent_dialog._save_vmc_config_to_cache(vmc_config)
                    debug(f"RobotParameterDialog: Triggered VMC configuration save to cache", "NodeParameterDialogs")
            except Exception as e:
                debug(f"RobotParameterDialog: Failed to save VMC configuration to cache: {e}", "NodeParameterDialogs")
            
            QMessageBox.information(self, "成功", f"已配置机器人: {robot_info.get('name', selected_id)}")
            self.accept()
        else:
            QMessageBox.warning(self, "警告", "请选择机器人设备")