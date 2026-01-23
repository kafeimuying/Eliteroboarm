#!/usr/bin/env python3
"""
中间结果查看对话框
用于显示算法节点的中间处理结果
"""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QWidget, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
import numpy as np
import cv2

# 导入图像转换工具
from utils.image_utils import numpy_to_qpixmap


class IntermediateResultDialog(QDialog):
    """中间结果查看对话框"""
    
    def __init__(self, algorithm_node, parent=None):
        super().__init__(parent)
        self.algorithm_node = algorithm_node
        self.algorithm = algorithm_node.algorithm
        self.execution_result = algorithm_node.execution_result
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        algorithm_info = self.algorithm.get_info()
        self.setWindowTitle(f'中间结果 - {algorithm_info.display_name}')
        self.setGeometry(200, 200, 800, 600)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 算法信息
        info_group = QWidget()
        info_layout = QHBoxLayout(info_group)
        
        info_text = f"""
        <b>算法:</b> {algorithm_info.display_name}<br>
        <b>类别:</b> {algorithm_info.category}<br>
        <b>描述:</b> {algorithm_info.description}<br>
        <b>执行状态:</b> {'成功' if self.execution_result and self.execution_result.success else '失败'}
        """
        
        info_label = QLabel(info_text)
        info_layout.addWidget(info_label)
        
        main_layout.addWidget(info_group)
        
        # 结果标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 添加结果标签页
        if self.execution_result:
            self.add_result_tabs()
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.close_btn = QPushButton('关闭')
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(button_layout)
    
    def add_result_tabs(self):
        """添加结果标签页"""
        # 添加最终结果
        if self.execution_result.output_image is not None:
            self.add_image_tab(self.execution_result.output_image, "最终结果")
        
        # 添加中间结果
        if hasattr(self.execution_result, 'intermediate_results'):
            for name, result in self.execution_result.intermediate_results.items():
                if isinstance(result, np.ndarray):
                    self.add_image_tab(result, name)
                else:
                    self.add_data_tab(result, name)
    
    def add_image_tab(self, image: np.ndarray, title: str):
        """添加图像标签页"""
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # 创建图像标签
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 转换图像格式
        try:
            # 使用统一的图像转换工具
            pixmap = numpy_to_qpixmap(image)
            image_label.setPixmap(pixmap)
            
        except Exception as e:
            image_label.setText(f"图像显示错误: {e}")
        
        scroll_area.setWidget(image_label)
        self.tab_widget.addTab(scroll_area, title)
    
    def add_data_tab(self, data, title: str):
        """添加数据标签页"""
        # 创建文本显示区域
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        
        text_label = QLabel(str(data))
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-family: monospace; font-size: 12px;")
        
        text_layout.addWidget(text_label)
        self.tab_widget.addTab(text_widget, title)


class ROISelectionDialog(QDialog):
    """ROI选择对话框"""
    
    roi_selected = pyqtSignal(int, int, int, int)  # ROI选择信号
    
    def __init__(self, image_data: np.ndarray, parent=None):
        super().__init__(parent)
        self.image_data = image_data
        self.is_selecting = False
        self.start_point = None
        self.end_point = None
        self.roi_rect = None
        self.selected_roi = None  # 存储选择的ROI
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('ROI选择')
        self.setGeometry(200, 200, 800, 600)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 说明文字
        info_label = QLabel('请在图像上拖拽鼠标选择ROI区域')
        main_layout.addWidget(info_label)
        
        # 图像显示区域（这里简化处理，实际应该集成到画布中）
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; border: 1px solid gray;")
        self.display_image()
        main_layout.addWidget(self.image_label)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.ok_btn = QPushButton('确定')
        self.ok_btn.clicked.connect(self.accept_roi)
        button_layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        main_layout.addLayout(button_layout)
    
    def display_image(self):
        """显示图像"""
        try:
            # 使用统一的图像转换工具
            pixmap = numpy_to_qpixmap(self.image_data)
            scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            
        except Exception as e:
            self.image_label.setText(f"图像显示错误: {e}")
    
    def accept_roi(self):
        """确认ROI选择"""
        if self.start_point and self.end_point:
            x1, y1 = self.start_point.x(), self.start_point.y()
            x2, y2 = self.end_point.x(), self.end_point.y()
            
            # 确保坐标顺序正确
            roi_x = min(x1, x2)
            roi_y = min(y1, y2)
            roi_width = abs(x2 - x1)
            roi_height = abs(y2 - y1)
            
            # 存储ROI值
            self.selected_roi = {"x": roi_x, "y": roi_y, "width": roi_width, "height": roi_height}
            
            self.roi_selected.emit(roi_x, roi_y, roi_width, roi_height)
        
        self.accept()