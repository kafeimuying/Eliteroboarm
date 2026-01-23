#!/usr/bin/env python3
"""
类型感知的参数控件组件
根据参数类型自动匹配合适的UI控件
"""

from typing import Dict, Any, List, Optional, Union
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit,
                             QComboBox, QSlider, QPushButton, QColorDialog,
                             QFileDialog, QGroupBox, QScrollArea, QFormLayout,
                             QDialog, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor
from core.interfaces.algorithm.base import ParameterType
from core.interfaces.algorithm.vision_config_types import ParameterConfig, get_ui_widget_type, validate_parameter_config
from core.managers.log_manager import info, debug, warning, error


class TypeAwareParameterWidget(QWidget):
    """类型感知的参数控件组件"""
    
    parameter_changed = pyqtSignal(str, object)  # 参数名, 新值
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parameter_widgets = {}  # 存储参数名到控件的映射
        self.parameter_configs = {}  # 存储参数配置
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 创建内容控件
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        
        self.scroll_area.setWidget(self.content_widget)
        self.main_layout.addWidget(self.scroll_area)
    
    def set_algorithm(self, algorithm):
        """设置算法并创建对应的参数控件"""
        self.clear_parameters()
        
        if algorithm is None:
            return
        
        # 获取算法参数定义
        parameter_definitions = algorithm.get_parameters()
        current_values = algorithm.get_all_parameters()
        
        # 为每个参数创建配置和控件
        for param_def in parameter_definitions:
            current_value = current_values.get(param_def.name, param_def.default_value)
            
            # 创建参数配置
            param_config = ParameterConfig(
                name=param_def.name,
                param_type=param_def.param_type,
                value=current_value,
                description=param_def.description,
                min_value=param_def.min_value,
                max_value=param_def.max_value,
                step=param_def.step,
                choices=param_def.choices,
                roi_mode=param_def.roi_mode,
                roi_constraint=param_def.roi_constraint,
                required=param_def.required
            )
            
            self.parameter_configs[param_def.name] = param_config
            
            # 创建对应的UI控件
            widget = self.create_parameter_widget(param_config)
            if widget:
                self.parameter_widgets[param_def.name] = widget
                self.content_layout.addWidget(widget)
        
        self.content_layout.addStretch()
    
    def create_parameter_widget(self, param_config: ParameterConfig) -> Optional[QWidget]:
        """根据参数配置创建对应的UI控件"""
        widget_type = get_ui_widget_type(param_config.param_type)
        
        # 创建参数组
        param_group = QGroupBox(param_config.description or param_config.name)
        param_layout = QFormLayout(param_group)
        
        # 根据类型创建具体控件
        if param_config.param_type == ParameterType.INT:
            control = self.create_int_control(param_config)
        elif param_config.param_type == ParameterType.FLOAT:
            control = self.create_float_control(param_config)
        elif param_config.param_type == ParameterType.BOOL:
            control = self.create_bool_control(param_config)
        elif param_config.param_type == ParameterType.STRING:
            control = self.create_string_control(param_config)
        elif param_config.param_type == ParameterType.CHOICE:
            control = self.create_choice_control(param_config)
        elif param_config.param_type == ParameterType.RANGE:
            control = self.create_range_control(param_config)
        elif param_config.param_type == ParameterType.COLOR:
            control = self.create_color_control(param_config)
        elif param_config.param_type == ParameterType.FILE:
            control = self.create_file_control(param_config)
        elif param_config.param_type == ParameterType.IMAGE:
            control = self.create_image_control(param_config)
        elif param_config.param_type == ParameterType.ROI:
            control = self.create_roi_control(param_config)
        else:
            # 默认使用文本框
            control = self.create_string_control(param_config)
        
        if control:
            param_layout.addRow("", control)
            
            # 连接信号
            if hasattr(control, 'valueChanged'):
                if param_config.param_type in [ParameterType.INT, ParameterType.FLOAT]:
                    control.valueChanged.connect(
                        lambda value, name=param_config.name: self.on_parameter_changed(name, value)
                    )
                elif param_config.param_type == ParameterType.RANGE:
                    control.valueChanged.connect(
                        lambda value, name=param_config.name: self.on_parameter_changed(name, value)
                    )
            
            elif hasattr(control, 'toggled'):
                control.toggled.connect(
                    lambda checked, name=param_config.name: self.on_parameter_changed(name, checked)
                )
            
            elif hasattr(control, 'currentTextChanged'):
                control.currentTextChanged.connect(
                    lambda text, name=param_config.name: self.on_parameter_changed(name, text)
                )
            
            elif hasattr(control, 'textChanged'):
                control.textChanged.connect(
                    lambda text, name=param_config.name: self.on_parameter_changed(name, text)
                )
            
            elif hasattr(control, 'clicked'):
                control.clicked.connect(
                    lambda name=param_config.name: self.on_button_clicked(name)
                )
        
        return param_group
    
    def create_int_control(self, param_config: ParameterConfig) -> QSpinBox:
        """创建整数控件"""
        control = QSpinBox()
        if param_config.min_value is not None:
            control.setMinimum(int(param_config.min_value))
        if param_config.max_value is not None:
            control.setMaximum(int(param_config.max_value))
        if param_config.step is not None:
            control.setSingleStep(int(param_config.step))
        
        control.setValue(int(param_config.value))
        control.setToolTip(f"类型: {param_config.param_type.value}")
        return control
    
    def create_float_control(self, param_config: ParameterConfig) -> QDoubleSpinBox:
        """创建浮点数控件"""
        control = QDoubleSpinBox()
        control.setDecimals(3)
        if param_config.min_value is not None:
            control.setMinimum(float(param_config.min_value))
        if param_config.max_value is not None:
            control.setMaximum(float(param_config.max_value))
        if param_config.step is not None:
            control.setSingleStep(float(param_config.step))
        
        control.setValue(float(param_config.value))
        control.setToolTip(f"类型: {param_config.param_type.value}")
        return control
    
    def create_bool_control(self, param_config: ParameterConfig) -> QCheckBox:
        """创建布尔值控件"""
        control = QCheckBox(param_config.description or param_config.name)
        control.setChecked(bool(param_config.value))
        control.setToolTip(f"类型: {param_config.param_type.value}")
        return control
    
    def create_string_control(self, param_config: ParameterConfig) -> QLineEdit:
        """创建字符串控件"""
        control = QLineEdit()
        control.setText(str(param_config.value))
        control.setToolTip(f"类型: {param_config.param_type.value}")
        return control
    
    def create_choice_control(self, param_config: ParameterConfig) -> QComboBox:
        """创建选择控件"""
        control = QComboBox()
        if param_config.choices:
            control.addItems(param_config.choices)
            if param_config.value in param_config.choices:
                control.setCurrentText(str(param_config.value))
        control.setToolTip(f"类型: {param_config.param_type.value}")
        return control
    
    def create_range_control(self, param_config: ParameterConfig) -> QWidget:
        """创建范围控件"""
        container = QWidget()
        layout = QHBoxLayout(container)
        
        # 创建滑块
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.valueChanged.connect(
            lambda value, name=param_config.name: self.on_parameter_changed(name, value)
        )
        
        # 创建显示标签
        value_label = QLabel(str(param_config.value))
        
        # 设置滑块范围
        if param_config.min_value is not None and param_config.max_value is not None:
            slider.setMinimum(int(param_config.min_value))
            slider.setMaximum(int(param_config.max_value))
            slider.setValue(int(param_config.value))
        
        if param_config.step is not None:
            slider.setSingleStep(int(param_config.step))
        
        # 连接滑块值变化到标签
        slider.valueChanged.connect(value_label.setText)
        
        layout.addWidget(slider)
        layout.addWidget(value_label)
        
        container.slider = slider  # 保存引用以便外部访问
        container.value_label = value_label
        container.setToolTip(f"类型: {param_config.param_type.value}")
        
        return container
    
    def create_color_control(self, param_config: ParameterConfig) -> QPushButton:
        """创建颜色控件"""
        control = QPushButton("选择颜色")
        
        # 设置当前颜色
        if isinstance(param_config.value, str) and param_config.value.startswith('#'):
            color = QColor(param_config.value)
            control.setStyleSheet(f"background-color: {param_config.value};")
        elif isinstance(param_config.value, (list, tuple)) and len(param_config.value) >= 3:
            r, g, b = param_config.value[:3]
            color = QColor(r, g, b)
            hex_color = color.name()
            control.setStyleSheet(f"background-color: {hex_color};")
        
        control.clicked.connect(lambda: self.on_color_clicked(param_config.name))
        control.setToolTip(f"类型: {param_config.param_type.value}")
        return control
    
    def create_file_control(self, param_config: ParameterConfig) -> QWidget:
        """创建文件选择控件"""
        container = QWidget()
        layout = QHBoxLayout(container)
        
        line_edit = QLineEdit(str(param_config.value))
        line_edit.setReadOnly(True)
        
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(lambda: self.on_file_browse_clicked(param_config.name, line_edit))
        
        layout.addWidget(line_edit)
        layout.addWidget(browse_btn)
        
        container.line_edit = line_edit
        container.setToolTip(f"类型: {param_config.param_type.value}")
        return container
    
    def create_image_control(self, param_config: ParameterConfig) -> QWidget:
        """创建图像选择控件"""
        container = QWidget()
        layout = QHBoxLayout(container)

        # 显示图像路径或状态的文本框
        line_edit = QLineEdit()
        line_edit.setReadOnly(True)
        line_edit.setPlaceholderText("请选择图像文件...")

        # 选择图像按钮
        browse_btn = QPushButton("选择图像...")
        browse_btn.clicked.connect(lambda: self.on_image_browse_clicked(param_config.name, line_edit))

        # 清除按钮
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(lambda: self.on_image_clear_clicked(param_config.name, line_edit))

        # 预览按钮 - 如果有图像的话
        preview_btn = QPushButton("预览")
        preview_btn.clicked.connect(lambda: self.on_image_preview_clicked(param_config.name))
        preview_btn.setEnabled(False)

        layout.addWidget(line_edit, 2)  # 给文本框更多空间
        layout.addWidget(browse_btn)
        layout.addWidget(preview_btn)
        layout.addWidget(clear_btn)

        # 保存控件引用
        container.line_edit = line_edit
        container.preview_btn = preview_btn
        container.setToolTip(f"类型: {param_config.param_type.value}")

        # 设置当前值
        if param_config.value:
            if isinstance(param_config.value, str):
                # 如果是文件路径
                line_edit.setText(param_config.value)
                preview_btn.setEnabled(True)
            elif isinstance(param_config.value, np.ndarray):
                # 如果是numpy数组
                line_edit.setText(f"已加载图像 ({param_config.value.shape[1]}x{param_config.value.shape[0]})")
                preview_btn.setEnabled(True)

        return container

    def create_roi_control(self, param_config: ParameterConfig) -> QPushButton:
        """创建ROI控件"""
        control = QPushButton("选择ROI区域")
        control.clicked.connect(lambda: self.on_roi_clicked(param_config.name))
        control.setToolTip(f"类型: {param_config.param_type.value}")

        # 显示当前ROI信息
        if isinstance(param_config.value, dict):
            roi_text = f"ROI: ({param_config.value.get('x', 0)}, {param_config.value.get('y', 0)}) "
            roi_text += f"{param_config.value.get('width', 0)}x{param_config.value.get('height', 0)}"
            control.setText(roi_text)

        return control
    
    def on_parameter_changed(self, param_name: str, value: Any):
        """参数值变化处理"""
        if param_name in self.parameter_configs:
            param_config = self.parameter_configs[param_name]
            
            # 验证新值
            if validate_parameter_config(param_config):
                param_config.value = value
                self.parameter_changed.emit(param_name, value)
            else:
                # 恢复为有效值
                self.reset_parameter_to_valid(param_name)
    
    def on_button_clicked(self, param_name: str):
        """按钮点击处理"""
        # 对于ROI和文件类型，通过其他方法处理
        pass
    
    def on_color_clicked(self, param_name: str):
        """颜色选择处理"""
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            # 更新按钮样式
            if param_name in self.parameter_widgets:
                control = self.parameter_widgets[param_name]
                if isinstance(control, QGroupBox):
                    # 获取实际的按钮控件
                    for child in control.children():
                        if isinstance(child, QPushButton):
                            child.setStyleSheet(f"background-color: {hex_color};")
                            break
            
            # 更新参数值
            self.on_parameter_changed(param_name, hex_color)
    
    def on_file_browse_clicked(self, param_name: str, line_edit: QLineEdit):
        """文件浏览处理"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if file_path:
            line_edit.setText(file_path)
            self.on_parameter_changed(param_name, file_path)
    
    def on_roi_clicked(self, param_name: str):
        """ROI选择处理"""
        try:
            # 导入ROI选择组件
            from ..dialogs.interactive_roi_selection import InteractiveROISelectionDialog, ROISelectionWidget
            
            # 获取输入图像
            input_image = self.get_input_image_for_roi_selection()
            
            # 如果没有输入图像，创建空白图像
            if input_image is None:
                input_image = self.create_blank_image()
            
            # 获取当前ROI值
            current_roi = None
            if param_name in self.parameter_configs:
                current_value = self.parameter_configs[param_name].value
                if isinstance(current_value, dict) and 'x' in current_value:
                    current_roi = (current_value['x'], current_value['y'], 
                                 current_value['width'], current_value['height'])
            
            # 创建ROI选择对话框
            roi_dialog = InteractiveROISelectionDialog(input_image, current_roi, self)
            
            if roi_dialog.exec() == QDialog.DialogCode.Accepted:
                selected_roi = roi_dialog.get_roi()
                if selected_roi and len(selected_roi) == 4:
                    # 验证ROI值的有效性
                    x, y, width, height = selected_roi
                    if width > 0 and height > 0:
                        roi_dict = {"x": x, "y": y, "width": width, "height": height}
                        from core.managers.log_manager import debug
                        debug(f"ROI参数控件验证通过: {roi_dict}", "UI")
                        self.on_parameter_changed(param_name, roi_dict)
                        
                        # 更新按钮文本
                        self.update_roi_button_text(param_name, selected_roi)
                        
                        # 显示成功消息
                        parent = self.parent()
                        while parent and not hasattr(parent, 'status_bar'):
                            parent = parent.parent()
                        if parent:
                            parent.status_bar.setText(f"ROI参数已更新: ({x}, {y}, {width}, {height})")
                    else:
                        from core.managers.log_manager import debug
                        debug(f"ROI值无效 - 跳过设置: ({x}, {y}, {width}, {height})", "UI")
                        parent = self.parent()
                        while parent and not hasattr(parent, 'status_bar'):
                            parent = parent.parent()
                        if parent:
                            parent.status_bar.setText("ROI选择无效：宽度和高度必须大于0")
                else:
                    from core.managers.log_manager import debug
                    debug(f"ROI选择取消或返回无效值: {selected_roi}", "UI")
                    parent = self.parent()
                    while parent and not hasattr(parent, 'status_bar'):
                        parent = parent.parent()
                    if parent:
                        parent.status_bar.setText("ROI选择已取消")
            else:
                # 回退到文本输入方式
                # self.fallback_roi_input(param_name)
                pass 
                
        except Exception as e:
            error(f"ROI选择出错: {e}", "TYPE_AWARE_WIDGET")
            # 回退到文本输入方式
            self.fallback_roi_input(param_name)
    
    def get_input_image_for_roi_selection(self):
        """获取用于ROI选择的输入图像"""
        try:
            # 查找父对话框
            parent = self.parent()
            canvas_dialog = None
            while parent:
                if hasattr(parent, 'canvas') and parent.canvas:
                    canvas_dialog = parent
                    break
                parent = parent.parent()
            
            if not canvas_dialog:
                return None
                
            # 优先从输入图像节点获取
            input_node = canvas_dialog.canvas.nodes.get("input_image")
            if input_node and input_node.image_data is not None:
                return input_node.image_data
            
            # 如果没有输入图像，尝试从算法链中获取第一个算法的输出
            for node in canvas_dialog.canvas.nodes.values():
                if hasattr(node, 'execution_result') and node.execution_result:
                    if node.execution_result.output_image is not None:
                        return node.execution_result.output_image
            
            return None
        except Exception:
            return None
    
    def create_blank_image(self):
        """创建空白图像用于ROI选择"""
        import numpy as np
        # 创建2000x3000的灰色图像
        height, width = 2000, 3000
        image = np.full((height, width, 3), [200, 200, 200], dtype=np.uint8)  # 浅灰色背景
        
        # 添加一些网格线作为参考
        import cv2
        grid_size = 100
        line_color = [150, 150, 150]  # 深灰色
        
        # 绘制垂直线
        for x in range(0, width, grid_size):
            cv2.line(image, (x, 0), (x, height), line_color, 1)
        
        # 绘制水平线
        for y in range(0, height, grid_size):
            cv2.line(image, (0, y), (width, y), line_color, 1)
        
        # 添加中心线
        center_x, center_y = width // 2, height // 2
        cv2.line(image, (center_x, 0), (center_x, height), [100, 100, 100], 2)  # 更深的中心垂直线
        cv2.line(image, (0, center_y), (width, center_y), [100, 100, 100], 2)  # 更深的中心水平线
        
        # 添加文字提示
        cv2.putText(image, "ROI Selection - Blank Canvas (2000x3000)", 
                   (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (50, 50, 50), 2)
        cv2.putText(image, "Drag to select ROI area", 
                   (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (70, 70, 70), 2)
        
        return image
    
    def fallback_roi_input(self, param_name: str):
        """回退到ROI文本输入方式"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "ROI设置", 
                                        "请输入ROI (格式: x,y,width,height):")
        if ok:
            try:
                parts = [int(x.strip()) for x in text.split(',')]
                if len(parts) == 4:
                    roi_dict = {"x": parts[0], "y": parts[1], 
                              "width": parts[2], "height": parts[3]}
                    self.on_parameter_changed(param_name, roi_dict)
                    self.update_roi_button_text(param_name, parts)
            except ValueError:
                pass  # 忽略无效输入
    
    def update_roi_button_text(self, param_name: str, roi_values):
        """更新ROI按钮文本"""
        if param_name in self.parameter_widgets:
            control = self.parameter_widgets[param_name]
            # control 可能直接是 QPushButton 或者包装在 QGroupBox 中
            if isinstance(control, QPushButton):
                if len(roi_values) == 4:
                    roi_text = f"ROI: ({roi_values[0]}, {roi_values[1]}) {roi_values[2]}x{roi_values[3]}"
                else:
                    roi_text = f"ROI: ({roi_values[0]}, {roi_values[1]}) {roi_values[2]}x{roi_values[3]}"
                control.setText(roi_text)
                from core.managers.log_manager import debug
                debug(f"更新ROI按钮文本: {param_name} -> {roi_text}", "UI")
            elif isinstance(control, QGroupBox):
                for child in control.children():
                    if isinstance(child, QPushButton):
                        if len(roi_values) == 4:
                            roi_text = f"ROI: ({roi_values[0]}, {roi_values[1]}) {roi_values[2]}x{roi_values[3]}"
                        else:
                            roi_text = f"ROI: ({roi_values[0]}, {roi_values[1]}) {roi_values[2]}x{roi_values[3]}"
                        child.setText(roi_text)
                        from core.managers.log_manager import debug
                        debug(f"更新ROI按钮文本(GroupBox内): {param_name} -> {roi_text}", "UI")
                        break
    
    def reset_parameter_to_valid(self, param_name: str):
        """重置参数为有效值"""
        if param_name in self.parameter_configs:
            param_config = self.parameter_configs[param_name]
            widget = self.parameter_widgets.get(param_name)
            
            if widget and isinstance(widget, QGroupBox):
                # 获取实际的控件
                for child in widget.children():
                    if hasattr(child, 'setValue'):
                        child.setValue(param_config.value)
                        break
    
    def clear_parameters(self):
        """清空所有参数控件"""
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        
        self.parameter_widgets.clear()
        self.parameter_configs.clear()
    
    def get_parameter_values(self) -> Dict[str, Any]:
        """获取所有参数值"""
        values = {}
        for param_name, config in self.parameter_configs.items():
            values[param_name] = config.value
        return values
    
    def validate_all_parameters(self) -> bool:
        """验证所有参数"""
        for param_config in self.parameter_configs.values():
            if not validate_parameter_config(param_config):
                return False
        return True

    def on_image_browse_clicked(self, param_name: str, line_edit: QLineEdit):
        """图像浏览处理"""
        try:
            import cv2
            import numpy as np

            # 支持多种图像格式
            image_filters = "图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif);;所有文件 (*)"
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择图像文件",
                "",
                image_filters
            )

            if file_path:
                # 验证图像文件是否可以加载
                try:
                    image = cv2.imread(file_path)
                    if image is None:
                        QMessageBox.warning(self, "错误", f"无法加载图像文件: {file_path}")
                        return

                    # 更新界面显示
                    line_edit.setText(file_path)

                    # 启用预览按钮
                    if param_name in self.parameter_widgets:
                        container = self.parameter_widgets[param_name]
                        if hasattr(container, 'preview_btn'):
                            container.preview_btn.setEnabled(True)

                    # 更新参数值
                    self.on_parameter_changed(param_name, file_path)

                    # 显示状态信息
                    parent = self.parent()
                    while parent and not hasattr(parent, 'status_bar'):
                        parent = parent.parent()
                    if parent:
                        height, width = image.shape[:2]
                        parent.status_bar.setText(f"已加载图像: {file_path.split('/')[-1]} ({width}x{height})")

                except Exception as e:
                    QMessageBox.critical(self, "错误", f"加载图像时出错: {str(e)}")

        except ImportError:
            QMessageBox.critical(self, "错误", "缺少必要的库: opencv-python")

    def on_image_clear_clicked(self, param_name: str, line_edit: QLineEdit):
        """清除图像选择"""
        line_edit.setText("")
        line_edit.setPlaceholderText("请选择图像文件...")

        # 禁用预览按钮
        if param_name in self.parameter_widgets:
            container = self.parameter_widgets[param_name]
            if hasattr(container, 'preview_btn'):
                container.preview_btn.setEnabled(False)

        # 更新参数值为None
        self.on_parameter_changed(param_name, None)

    def on_image_preview_clicked(self, param_name: str):
        """预览图像"""
        try:
            import cv2
            import numpy as np

            param_config = self.parameter_configs.get(param_name)
            if not param_config:
                return

            image_value = param_config.value
            if not image_value:
                return

            # 加载图像
            if isinstance(image_value, str):
                # 从文件路径加载
                image = cv2.imread(image_value)
                if image is None:
                    QMessageBox.warning(self, "错误", "无法加载图像文件")
                    return
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # 转换为RGB
            elif isinstance(image_value, np.ndarray):
                # 直接使用numpy数组
                image = image_value
                if len(image.shape) == 3 and image.shape[2] == 3:
                    # 假设是BGR格式，转换为RGB
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                QMessageBox.warning(self, "错误", "不支持的图像数据格式")
                return

            # 创建预览对话框
            from ..canvas.image_dialog import ImageDisplayDialog
            preview_dialog = ImageDisplayDialog(image, f"图像预览 - {param_config.description or param_name}", self)
            preview_dialog.exec()

        except ImportError:
            QMessageBox.critical(self, "错误", "缺少必要的库: opencv-python 或 numpy")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"预览图像时出错: {str(e)}")