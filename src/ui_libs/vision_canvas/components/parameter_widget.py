#!/usr/bin/env python3
"""
动态参数配置组件
"""

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from typing import Dict, Any, List, Optional, Callable

from core.interfaces.algorithm.base import AlgorithmParameter, ParameterType, AlgorithmBase


class ParameterWidget(QWidget):
    """参数控件基类"""
    
    value_changed = pyqtSignal(str, object)  # 参数名, 新值
    
    def __init__(self, parameter: AlgorithmParameter, parent=None):
        super().__init__(parent)
        self.parameter = parameter
        self.setup_ui()
    
    def setup_ui(self):
        """设置界面"""
        pass
    
    def get_value(self) -> Any:
        """获取当前值"""
        raise NotImplementedError
    
    def set_value(self, value: Any):
        """设置值"""
        raise NotImplementedError


class IntParameterWidget(ParameterWidget):
    """整数参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.spin_box = QSpinBox()
        self.spin_box.setMinimum(int(self.parameter.min_value) if self.parameter.min_value is not None else -2147483648)
        self.spin_box.setMaximum(int(self.parameter.max_value) if self.parameter.max_value is not None else 2147483647)
        self.spin_box.setValue(int(self.parameter.default_value))
        
        if self.parameter.step is not None:
            self.spin_box.setSingleStep(int(self.parameter.step))
        
        self.spin_box.valueChanged.connect(lambda v: self.value_changed.emit(self.parameter.name, v))
        layout.addWidget(self.spin_box)
        
        # 添加滑块（如果有范围）
        if (self.parameter.min_value is not None and 
            self.parameter.max_value is not None and 
            self.parameter.max_value - self.parameter.min_value <= 1000):
            
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setMinimum(int(self.parameter.min_value))
            self.slider.setMaximum(int(self.parameter.max_value))
            self.slider.setValue(int(self.parameter.default_value))
            
            # 连接滑块和数值框
            self.slider.valueChanged.connect(self.spin_box.setValue)
            self.spin_box.valueChanged.connect(self.slider.setValue)
            
            layout.addWidget(self.slider)
    
    def get_value(self) -> int:
        return self.spin_box.value()
    
    def set_value(self, value: int):
        self.spin_box.setValue(value)


class FloatParameterWidget(ParameterWidget):
    """浮点数参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.double_spin_box = QDoubleSpinBox()
        self.double_spin_box.setMinimum(self.parameter.min_value if self.parameter.min_value is not None else -1e10)
        self.double_spin_box.setMaximum(self.parameter.max_value if self.parameter.max_value is not None else 1e10)
        self.double_spin_box.setValue(self.parameter.default_value)
        self.double_spin_box.setDecimals(3)
        
        if self.parameter.step is not None:
            self.double_spin_box.setSingleStep(self.parameter.step)
        
        self.double_spin_box.valueChanged.connect(lambda v: self.value_changed.emit(self.parameter.name, v))
        layout.addWidget(self.double_spin_box)
    
    def get_value(self) -> float:
        return self.double_spin_box.value()
    
    def set_value(self, value: float):
        self.double_spin_box.setValue(value)


class BoolParameterWidget(ParameterWidget):
    """布尔参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.check_box = QCheckBox()
        self.check_box.setChecked(self.parameter.default_value)
        self.check_box.stateChanged.connect(lambda state: self.value_changed.emit(
            self.parameter.name, state == Qt.CheckState.Checked.value))
        layout.addWidget(self.check_box)
    
    def get_value(self) -> bool:
        return self.check_box.isChecked()
    
    def set_value(self, value: bool):
        self.check_box.setChecked(value)


class StringParameterWidget(ParameterWidget):
    """字符串参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.line_edit = QLineEdit()
        self.line_edit.setText(str(self.parameter.default_value))
        self.line_edit.textChanged.connect(lambda text: self.value_changed.emit(self.parameter.name, text))
        layout.addWidget(self.line_edit)
    
    def get_value(self) -> str:
        return self.line_edit.text()
    
    def set_value(self, value: str):
        self.line_edit.setText(value)


class ChoiceParameterWidget(ParameterWidget):
    """选择参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.combo_box = QComboBox()
        self.combo_box.addItems(self.parameter.choices)
        
        # 设置默认值
        if self.parameter.default_value in self.parameter.choices:
            self.combo_box.setCurrentText(self.parameter.default_value)
        
        self.combo_box.currentTextChanged.connect(lambda text: self.value_changed.emit(self.parameter.name, text))
        layout.addWidget(self.combo_box)
    
    def get_value(self) -> str:
        return self.combo_box.currentText()
    
    def set_value(self, value: str):
        if self.parameter.choices and value in self.parameter.choices:
            self.combo_box.setCurrentText(value)


class FileParameterWidget(ParameterWidget):
    """文件参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.line_edit = QLineEdit()
        self.line_edit.setText(str(self.parameter.default_value))
        self.line_edit.textChanged.connect(lambda text: self.value_changed.emit(self.parameter.name, text))
        layout.addWidget(self.line_edit)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_file)
        layout.addWidget(self.browse_btn)
    
    def browse_file(self):
        """浏览文件"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", self.line_edit.text())
        if file_path:
            self.line_edit.setText(file_path)
    
    def get_value(self) -> str:
        return self.line_edit.text()
    
    def set_value(self, value: str):
        self.line_edit.setText(value)


class ColorParameterWidget(ParameterWidget):
    """颜色参数控件"""
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(50, 25)
        self.current_color = QColor(self.parameter.default_value) if isinstance(self.parameter.default_value, str) else QColor(255, 255, 255)
        self.update_color_button()
        self.color_btn.clicked.connect(self.choose_color)
        layout.addWidget(self.color_btn)
        
        self.color_label = QLabel(self.current_color.name())
        layout.addWidget(self.color_label)
    
    def update_color_button(self):
        """更新颜色按钮显示"""
        self.color_btn.setStyleSheet(f"background-color: {self.current_color.name()}; border: 1px solid gray;")
    
    def choose_color(self):
        """选择颜色"""
        color = QColorDialog.getColor(self.current_color, self, "选择颜色")
        if color.isValid():
            self.current_color = color
            self.update_color_button()
            self.color_label.setText(color.name())
            self.value_changed.emit(self.parameter.name, color.name())
    
    def get_value(self) -> str:
        return self.current_color.name()
    
    def set_value(self, value: str):
        color = QColor(value)
        if color.isValid():
            self.current_color = color
            self.update_color_button()
            self.color_label.setText(color.name())


class ROIParameterWidget(ParameterWidget):
    """ROI参数控件"""
    
    roi_selected = pyqtSignal(dict)  # ROI选择信号，传递ROI数据
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 模式选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("模式:"))
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["手动选择", "坐标输入", "中心点+尺寸"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # 手动选择模式
        self.manual_widget = QWidget()
        manual_layout = QHBoxLayout(self.manual_widget)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        
        self.select_btn = QPushButton("手动选择ROI")
        self.select_btn.clicked.connect(self.select_roi_manually)
        manual_layout.addWidget(self.select_btn)
        
        self.roi_label = QLabel("未选择")
        manual_layout.addWidget(self.roi_label)
        manual_layout.addStretch()
        
        # 坐标输入模式
        self.coord_widget = QWidget()
        coord_layout = QGridLayout(self.coord_widget)
        coord_layout.setContentsMargins(0, 0, 0, 0)
        
        # xyxy格式输入
        coord_layout.addWidget(QLabel("X1:"), 0, 0)
        self.x1_spin = QSpinBox()
        self.x1_spin.setRange(0, 9999)
        self.x1_spin.valueChanged.connect(self.on_coord_changed)
        coord_layout.addWidget(self.x1_spin, 0, 1)
        
        coord_layout.addWidget(QLabel("Y1:"), 0, 2)
        self.y1_spin = QSpinBox()
        self.y1_spin.setRange(0, 9999)
        self.y1_spin.valueChanged.connect(self.on_coord_changed)
        coord_layout.addWidget(self.y1_spin, 0, 3)
        
        coord_layout.addWidget(QLabel("X2:"), 1, 0)
        self.x2_spin = QSpinBox()
        self.x2_spin.setRange(0, 9999)
        self.x2_spin.valueChanged.connect(self.on_coord_changed)
        coord_layout.addWidget(self.x2_spin, 1, 1)
        
        coord_layout.addWidget(QLabel("Y2:"), 1, 2)
        self.y2_spin = QSpinBox()
        self.y2_spin.setRange(0, 9999)
        self.y2_spin.valueChanged.connect(self.on_coord_changed)
        coord_layout.addWidget(self.y2_spin, 1, 3)
        
        # 中心点+尺寸模式
        self.center_widget = QWidget()
        center_layout = QGridLayout(self.center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        center_layout.addWidget(QLabel("中心X:"), 0, 0)
        self.center_x_spin = QSpinBox()
        self.center_x_spin.setRange(0, 9999)
        self.center_x_spin.valueChanged.connect(self.on_center_changed)
        center_layout.addWidget(self.center_x_spin, 0, 1)
        
        center_layout.addWidget(QLabel("中心Y:"), 0, 2)
        self.center_y_spin = QSpinBox()
        self.center_y_spin.setRange(0, 9999)
        self.center_y_spin.valueChanged.connect(self.on_center_changed)
        center_layout.addWidget(self.center_y_spin, 0, 3)
        
        center_layout.addWidget(QLabel("宽度:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 9999)
        self.width_spin.valueChanged.connect(self.on_center_changed)
        center_layout.addWidget(self.width_spin, 1, 1)
        
        center_layout.addWidget(QLabel("高度:"), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 9999)
        self.height_spin.valueChanged.connect(self.on_center_changed)
        center_layout.addWidget(self.height_spin, 1, 3)
        
        # 添加所有模式到主布局
        layout.addWidget(self.manual_widget)
        layout.addWidget(self.coord_widget)
        layout.addWidget(self.center_widget)
        
        # 初始化
        self.set_default_roi()
        self.on_mode_changed("手动选择")
        
        # 存储当前ROI数据
        self.current_roi = self.get_value()
    
    def set_default_roi(self):
        """设置默认ROI值"""
        default_value = self.parameter.default_value
        if isinstance(default_value, dict):
            x = default_value.get("x", 0)
            y = default_value.get("y", 0)
            width = default_value.get("width", 100)
            height = default_value.get("height", 100)
        else:
            x, y, width, height = 0, 0, 100, 100
        
        # 设置xyxy格式
        self.x1_spin.setValue(x)
        self.y1_spin.setValue(y)
        self.x2_spin.setValue(x + width)
        self.y2_spin.setValue(y + height)
        
        # 设置中心点格式
        self.center_x_spin.setValue(x + width // 2)
        self.center_y_spin.setValue(y + height // 2)
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
    
    def on_mode_changed(self, mode: str):
        """模式改变"""
        self.manual_widget.setVisible(mode == "手动选择")
        self.coord_widget.setVisible(mode == "坐标输入")
        self.center_widget.setVisible(mode == "中心点+尺寸")
    
    def select_roi_manually(self):
        """手动选择ROI"""
        # 发射信号，请求父组件进行ROI选择
        self.roi_selected.emit({
            "mode": "manual",
            "current_roi": self.current_roi
        })
    
    def on_coord_changed(self):
        """坐标改变"""
        x1, y1, x2, y2 = self.x1_spin.value(), self.y1_spin.value(), self.x2_spin.value(), self.y2_spin.value()
        
        # 确保坐标有效
        if x2 <= x1:
            self.x2_spin.setValue(x1 + 1)
            x2 = x1 + 1
        if y2 <= y1:
            self.y2_spin.setValue(y1 + 1)
            y2 = y1 + 1
        
        # 同步到中心点模式
        self.center_x_spin.setValue((x1 + x2) // 2)
        self.center_y_spin.setValue((y1 + y2) // 2)
        self.width_spin.setValue(x2 - x1)
        self.height_spin.setValue(y2 - y1)
        
        # 更新ROI标签
        self.roi_label.setText(f"({x1}, {y1}) - ({x2}, {y2})")
        
        # 发射值改变信号
        self.current_roi = self.get_value()
        self.value_changed.emit(self.parameter.name, self.current_roi)
    
    def on_center_changed(self):
        """中心点改变"""
        cx, cy, width, height = self.center_x_spin.value(), self.center_y_spin.value(), self.width_spin.value(), self.height_spin.value()
        
        # 计算左上角坐标
        x1 = cx - width // 2
        y1 = cy - height // 2
        x2 = x1 + width
        y2 = y1 + height
        
        # 确保坐标非负
        if x1 < 0:
            x1 = 0
            self.center_x_spin.setValue(width // 2)
        if y1 < 0:
            y1 = 0
            self.center_y_spin.setValue(height // 2)
        
        # 同步到坐标模式
        self.x1_spin.setValue(x1)
        self.y1_spin.setValue(y1)
        self.x2_spin.setValue(x1 + width)
        self.y2_spin.setValue(y1 + height)
        
        # 更新ROI标签
        self.roi_label.setText(f"({x1}, {y1}) - ({x1 + width}, {y1 + height})")
        
        # 发射值改变信号
        self.current_roi = self.get_value()
        self.value_changed.emit(self.parameter.name, self.current_roi)
    
    def get_value(self) -> dict:
        """获取当前ROI值"""
        x1 = self.x1_spin.value()
        y1 = self.y1_spin.value()
        width = self.x2_spin.value() - x1
        height = self.y2_spin.value() - y1
        
        return {
            "x": x1,
            "y": y1,
            "width": width,
            "height": height
        }
    
    def set_value(self, value):
        """设置ROI值"""
        if isinstance(value, dict):
            x = value.get("x", 0)
            y = value.get("y", 0)
            width = value.get("width", 100)
            height = value.get("height", 100)
        elif isinstance(value, str):
            # 解析xyxy格式字符串
            try:
                coords = [int(x.strip()) for x in value.split(',')]
                if len(coords) == 4:
                    x1, y1, x2, y2 = coords
                    x, y = x1, y1
                    width = x2 - x1
                    height = y2 - y1
                else:
                    x, y, width, height = 0, 0, 100, 100
            except (ValueError, TypeError):
                x, y, width, height = 0, 0, 100, 100
        else:
            x, y, width, height = 0, 0, 100, 100
        
        # 更新所有控件
        self.x1_spin.setValue(x)
        self.y1_spin.setValue(y)
        self.x2_spin.setValue(x + width)
        self.y2_spin.setValue(y + height)
        
        self.center_x_spin.setValue(x + width // 2)
        self.center_y_spin.setValue(y + height // 2)
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        
        self.roi_label.setText(f"({x}, {y}) - ({x + width}, {y + height})")
        
        self.current_roi = self.get_value()
    
    def set_roi_from_selection(self, x1: int, y1: int, x2: int, y2: int):
        """从手动选择设置ROI"""
        self.x1_spin.setValue(min(x1, x2))
        self.y1_spin.setValue(min(y1, y2))
        self.x2_spin.setValue(max(x1, x2))
        self.y2_spin.setValue(max(y1, y2))
        
        # 切换到手动选择模式
        self.mode_combo.setCurrentText("手动选择")


class DynamicParameterWidget(QWidget):
    """动态参数配置组件"""
    
    parameter_changed = pyqtSignal(str, object)  # 参数名, 新值
    parameters_reset = pyqtSignal()  # 参数重置信号
    roi_selection_requested = pyqtSignal(object)  # ROI选择请求信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.algorithm: Optional[AlgorithmBase] = None
        self.parameter_widgets: Dict[str, ParameterWidget] = {}
        self.setup_ui()
    
    def setup_ui(self):
        """设置界面"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QFormLayout(self.scroll_content)
        self.scroll_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.reset_btn = QPushButton("重置参数")
        self.reset_btn.clicked.connect(self.reset_parameters)
        button_layout.addWidget(self.reset_btn)
        
        self.apply_btn = QPushButton("应用")
        self.apply_btn.clicked.connect(self.apply_parameters)
        button_layout.addWidget(self.apply_btn)
        
        button_layout.addStretch()
        self.main_layout.addLayout(button_layout)
        
        # 初始显示空状态
        self.show_empty_state()
    
    def show_empty_state(self):
        """显示空状态"""
        self.clear_parameters()
        empty_label = QLabel("请选择算法以配置参数")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: gray; font-style: italic; padding: 20px;")
        self.scroll_layout.addRow(empty_label)
    
    def set_algorithm(self, algorithm: AlgorithmBase):
        """设置算法"""
        self.algorithm = algorithm
        self.load_parameters()
    
    def load_parameters(self):
        """加载参数"""
        self.clear_parameters()
        
        if not self.algorithm:
            self.show_empty_state()
            return
        
        parameters = self.algorithm.get_parameter_definitions()
        
        if not parameters:
            no_params_label = QLabel("该算法无可配置参数")
            no_params_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_params_label.setStyleSheet("color: gray; font-style: italic; padding: 20px;")
            self.scroll_layout.addRow(no_params_label)
            return
        
        # 为每个参数创建控件
        for param in parameters:
            param_widget = self.create_parameter_widget(param)
            if param_widget:
                param_widget.value_changed.connect(self.on_parameter_changed)
                
                # 连接ROI参数的特殊信号
                if param.param_type == ParameterType.ROI and hasattr(param_widget, 'roi_selected'):
                    param_widget.roi_selected.connect(self.on_roi_selected)
                
                self.parameter_widgets[param.name] = param_widget
                
                # 创建标签
                label = QLabel(param.description or param.name)
                label.setToolTip(f"类型: {param.param_type.value}\n默认值: {param.default_value}")
                if param.required:
                    label.setStyleSheet("font-weight: bold;")
                
                self.scroll_layout.addRow(label, param_widget)
    
    def create_parameter_widget(self, param: AlgorithmParameter) -> Optional[ParameterWidget]:
        """创建参数控件"""
        widget_map = {
            ParameterType.INT: IntParameterWidget,
            ParameterType.FLOAT: FloatParameterWidget,
            ParameterType.BOOL: BoolParameterWidget,
            ParameterType.STRING: StringParameterWidget,
            ParameterType.CHOICE: ChoiceParameterWidget,
            ParameterType.FILE: FileParameterWidget,
            ParameterType.COLOR: ColorParameterWidget,
            ParameterType.ROI: ROIParameterWidget,
        }
        
        widget_class = widget_map.get(param.param_type)
        if widget_class:
            return widget_class(param)
        return None
    
    def clear_parameters(self):
        """清空参数"""
        # 清空布局
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child and child.widget():
                widget = child.widget()
                if widget:
                    widget.deleteLater()
        
        self.parameter_widgets.clear()
    
    def on_parameter_changed(self, param_name: str, value: Any):
        """参数值改变"""
        if self.algorithm:
            try:
                self.algorithm.set_parameter(param_name, value)
                self.parameter_changed.emit(param_name, value)
            except ValueError as e:
                # 参数验证失败，恢复原值
                QMessageBox.warning(self, "参数错误", str(e))
                if param_name in self.parameter_widgets:
                    original_value = self.algorithm.get_parameter(param_name)
                    self.parameter_widgets[param_name].set_value(original_value)
    
    def reset_parameters(self):
        """重置参数"""
        if self.algorithm:
            self.algorithm.reset_parameters()
            
            # 更新界面
            for param_name, widget in self.parameter_widgets.items():
                default_value = self.algorithm.get_parameter(param_name)
                widget.set_value(default_value)
            
            self.parameters_reset.emit()
    
    def apply_parameters(self):
        """应用参数"""
        # 这里可以添加应用参数的逻辑
        # 比如触发算法重新执行等
        pass
    
    def get_current_parameters(self) -> Dict[str, Any]:
        """获取当前参数值"""
        if not self.algorithm:
            return {}
        return self.algorithm.get_all_parameters()
    
    def on_roi_selected(self, data):
        """处理ROI选择请求"""
        self.roi_selection_requested.emit(data)