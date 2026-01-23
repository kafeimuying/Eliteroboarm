#!/usr/bin/env python3
"""
交互式ROI选择对话框
"""

import cv2
import numpy as np
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QGraphicsView, QGraphicsScene,
                             QGraphicsRectItem, QGraphicsItem, QWidget,
                             QFormLayout, QSpinBox, QGroupBox, QTabWidget)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import QPen, QBrush, QColor, QImage, QPixmap, QPainter
from core.managers.log_manager import info, debug, warning, error

# 导入图像转换工具
from utils.image_utils import numpy_to_qpixmap


class ROISelectionWidget(QGraphicsView):
    """ROI选择控件"""
    
    roi_selected = pyqtSignal(int, int, int, int)  # ROI选择信号
    
    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.image = image
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # ROI选择状态
        self.selecting = False
        self.start_point = None
        self.current_rect = None
        self.final_rect = None
        
        # 图像缩放
        self.scale_factor = 1.0
        
        self.setup_ui()
        self.load_image()
    
    def setup_ui(self):
        """设置界面"""
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 设置背景
        self.setBackgroundBrush(QBrush(QColor(240, 240, 240)))
        
        # 启用鼠标追踪
        self.setMouseTracking(True)
    
    def load_image(self):
        """加载图像"""
        try:
            # 使用统一的图像转换工具
            pixmap = numpy_to_qpixmap(self.image)
            
            # 获取图像尺寸
            if len(self.image.shape) == 3:
                height, width = self.image.shape[:2]
            else:
                height, width = self.image.shape
            
            # 先设置场景大小为图像大小
            self.scene.setSceneRect(0, 0, width, height)
            
            # 添加原始图像到场景
            self.scene.addPixmap(pixmap)
            
            # 设置默认缩放比例（1:1显示）
            self.scale_factor = 1.0
            
            # 延迟调整视图以适应窗口
            QTimer.singleShot(100, self.fit_image_to_view)
            
        except Exception as e:
            # 如果图像加载失败，显示错误信息
            error_text = self.scene.addText(f"图像加载失败: {e}")
            error_text.setDefaultTextColor(QColor(255, 0, 0))
    
    def fit_image_to_view(self):
        """调整图像以适应视图"""
        try:
            # 获取视图大小
            view_size = self.size()
            if view_size.width() <= 0 or view_size.height() <= 0:
                return
            
            # 获取图像大小
            if not self.scene.items():
                return
            
            pixmap_item = self.scene.items()[0]
            if hasattr(pixmap_item, 'pixmap'):
                image_size = pixmap_item.pixmap().size()
                width, height = image_size.width(), image_size.height()
            else:
                return
            
            # 计算适合的缩放比例
            scale_x = view_size.width() / width
            scale_y = view_size.height() / height
            self.scale_factor = min(scale_x, scale_y) * 0.9  # 留一些边距
            
            # 应用缩放
            self.resetTransform()
            self.scale(self.scale_factor, self.scale_factor)
            
            debug(f"图像缩放比例: {self.scale_factor:.3f}, 原始尺寸: {width}x{height}", "ROI_SELECTION")

        except Exception as e:
            error(f"调整图像视图失败: {e}", "ROI_SELECTION")
    
    def resizeEvent(self, event):
        """窗口大小改变事件"""
        super().resizeEvent(event)
        # 重新调整图像以适应新的视图大小
        QTimer.singleShot(50, self.fit_image_to_view)
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.selecting = True
            self.start_point = self.mapToScene(event.position().toPoint())
            
            # 创建新的选择矩形
            if self.current_rect:
                self.scene.removeItem(self.current_rect)
            
            self.current_rect = QGraphicsRectItem(QRectF(self.start_point, self.start_point))
            self.current_rect.setPen(QPen(QColor(255, 0, 0), 2))
            self.current_rect.setBrush(QBrush(QColor(255, 0, 0, 50), Qt.BrushStyle.SolidPattern))
            self.scene.addItem(self.current_rect)
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.selecting and self.current_rect and self.start_point:
            current_point = self.mapToScene(event.position().toPoint())
            
            # 更新矩形大小
            rect = QRectF(self.start_point, current_point).normalized()
            self.current_rect.setRect(rect)
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton and self.selecting:
            self.selecting = False
            
            if self.current_rect:
                # 获取最终选择的矩形（场景坐标）
                rect = self.current_rect.rect()
                
                # 场景坐标对应原始图像坐标，不受视图缩放影响
                scene_x = rect.x()
                scene_y = rect.y()
                scene_width = rect.width()
                scene_height = rect.height()
                
                # 确保ROI在图像范围内
                img_height, img_width = self.image.shape[:2]
                x = max(0, min(int(scene_x), img_width - 1))
                y = max(0, min(int(scene_y), img_height - 1))
                width = max(1, min(int(scene_width), img_width - x))
                height = max(1, min(int(scene_height), img_height - y))
                
                # 更新矩形样式
                self.current_rect.setPen(QPen(QColor(0, 255, 0), 2))
                self.current_rect.setBrush(QBrush(QColor(0, 255, 0, 50), Qt.BrushStyle.SolidPattern))
                
                self.final_rect = (x, y, width, height)
                
                # 详细的调试信息
                info(f"ROI选择完成:", "ROI_SELECTION")
                info(f"  原始图像尺寸: {img_width} x {img_height}", "ROI_SELECTION")
                info(f"  视图缩放比例: {self.scale_factor:.3f}", "ROI_SELECTION")
                info(f"  场景坐标: ({scene_x:.1f}, {scene_y:.1f}, {scene_width:.1f}, {scene_height:.1f})", "ROI_SELECTION")
                info(f"  最终图像坐标: ({x}, {y}, {width}, {height})", "ROI_SELECTION")
                info(f"  坐标验证: 场景坐标 == 图像坐标 (场景未缩放)", "ROI_SELECTION")
                
                # 发送ROI选择信号
                self.roi_selected.emit(x, y, width, height)
        
        super().mouseReleaseEvent(event)
    
    def get_selected_roi(self):
        """获取选择的ROI"""
        return self.final_rect
    
    def clear_selection(self):
        """清除选择"""
        if self.current_rect:
            self.scene.removeItem(self.current_rect)
            self.current_rect = None
        self.final_rect = None
        self.selecting = False
        self.start_point = None
    
    def wheelEvent(self, event):
        """滚轮事件 - 支持缩放"""
        try:
            # 获取滚轮滚动的角度
            angle_delta = event.angleDelta().y()
            if angle_delta == 0:
                return
            
            # 计算缩放因子
            scale_factor = 1.15
            if angle_delta > 0:
                # 放大
                new_scale = self.scale_factor * scale_factor
                if new_scale <= 5.0:  # 最大5倍放大
                    self.scale(scale_factor, scale_factor)
                    self.scale_factor = new_scale
            else:
                # 缩小
                new_scale = self.scale_factor / scale_factor
                if new_scale >= 0.1:  # 最小0.1倍缩放
                    self.scale(1/scale_factor, 1/scale_factor)
                    self.scale_factor = new_scale
            
            debug(f"ROI选择 - 缩放比例: {self.scale_factor:.3f}", "ROI_SELECTION")

        except Exception as e:
            error(f"ROI选择缩放失败: {e}", "ROI_SELECTION")
    
    def set_existing_roi(self, roi):
        """设置并显示现有的ROI"""
        if not roi or len(roi) != 4:
            return
            
        x, y, width, height = roi
        img_height, img_width = self.image.shape[:2]
        
        # 确保ROI在图像范围内
        x = max(0, min(x, img_width - 1))
        y = max(0, min(y, img_height - 1))
        width = max(1, min(width, img_width - x))
        height = max(1, min(height, img_height - y))
        
        # 清除当前选择
        if self.current_rect:
            self.scene.removeItem(self.current_rect)
        
        # 创建ROI矩形
        self.current_rect = QGraphicsRectItem(x, y, width, height)
        self.current_rect.setPen(QPen(QColor(0, 255, 0), 2))
        self.current_rect.setBrush(QBrush(QColor(0, 255, 0, 50), Qt.BrushStyle.SolidPattern))
        self.scene.addItem(self.current_rect)
        
        self.final_rect = (x, y, width, height)
        info(f"显示现有ROI: 原始坐标({x}, {y}, {width}, {height})", "ROI_SELECTION")
        info(f"图像尺寸: {img_width}x{img_height}, 缩放比例: {self.scale_factor:.3f}", "ROI_SELECTION")


class InteractiveROISelectionDialog(QDialog):
    """增强的ROI选择对话框 - 支持交互式选择和手动输入"""
    
    roi_selected = pyqtSignal(int, int, int, int)  # ROI选择信号
    
    def __init__(self, image, current_roi=None, parent=None):
        super().__init__(parent)
        self.image = image
        self.current_roi = current_roi  # 当前ROI值
        self.selected_roi = None
        self.init_ui()
        
        # 如果有当前ROI，显示在手动输入区域和图像上
        if current_roi:
            self.set_manual_roi(current_roi)
            # 在图像上显示现有ROI
            if hasattr(self, 'roi_widget'):
                self.roi_widget.set_existing_roi(current_roi)
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle('ROI区域选择')
        self.setGeometry(100, 100, 1000, 700)
        
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 选项卡
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 交互式选择选项卡
        self.create_interactive_tab()
        
        # 手动输入选项卡
        self.create_manual_tab()
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 清除按钮
        clear_btn = QPushButton('清除选择')
        clear_btn.clicked.connect(self.clear_selection)
        button_layout.addWidget(clear_btn)
        
        button_layout.addStretch()
        
        # 确定按钮
        ok_btn = QPushButton('确定')
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        # 取消按钮
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
    
    def create_interactive_tab(self):
        """创建交互式选择选项卡"""
        interactive_widget = QWidget()
        layout = QVBoxLayout(interactive_widget)
        
        # 说明标签
        info_label = QLabel('交互式选择：请按住鼠标左键并拖拽来选择ROI区域，支持滚轮缩放')
        info_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info_label)
        
        # 缩放工具栏
        zoom_toolbar = QHBoxLayout()
        
        # 放大按钮
        zoom_in_btn = QPushButton('🔍+ 放大')
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_toolbar.addWidget(zoom_in_btn)
        
        # 缩小按钮
        zoom_out_btn = QPushButton('🔍- 缩小')
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_toolbar.addWidget(zoom_out_btn)
        
        # 适应窗口按钮
        fit_btn = QPushButton('📐 适应窗口')
        fit_btn.clicked.connect(self.fit_to_window)
        zoom_toolbar.addWidget(fit_btn)
        
        # 1:1按钮
        original_btn = QPushButton('1:1 原始大小')
        original_btn.clicked.connect(self.original_size)
        zoom_toolbar.addWidget(original_btn)
        
        # 缩放比例显示
        self.zoom_label = QLabel('100%')
        self.zoom_label.setStyleSheet("background-color: #f0f0f0; padding: 2px 8px; border: 1px solid #ccc;")
        zoom_toolbar.addWidget(self.zoom_label)
        
        zoom_toolbar.addStretch()
        
        # 提示标签
        hint_label = QLabel('💡 提示：可以使用鼠标滚轮缩放')
        hint_label.setStyleSheet("color: #999; font-size: 10px;")
        zoom_toolbar.addWidget(hint_label)
        
        layout.addLayout(zoom_toolbar)
        
        # ROI选择控件
        self.roi_widget = ROISelectionWidget(self.image, self)
        self.roi_widget.roi_selected.connect(self.on_roi_selected)
        layout.addWidget(self.roi_widget)
        
        # 当前选择显示
        self.selection_label = QLabel('当前选择：未选择')
        self.selection_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc;")
        layout.addWidget(self.selection_label)
        
        self.tab_widget.addTab(interactive_widget, "交互式选择")
    
    def create_manual_tab(self):
        """创建手动输入选项卡"""
        manual_widget = QWidget()
        layout = QVBoxLayout(manual_widget)
        
        # 说明标签
        info_label = QLabel('手动输入：请输入ROI区域的坐标和尺寸')
        info_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(info_label)
        
        # 输入表单
        form_group = QGroupBox("ROI参数")
        form_layout = QFormLayout(form_group)
        
        # X坐标
        self.x_spinbox = QSpinBox()
        self.x_spinbox.setRange(0, 5000)
        self.x_spinbox.setValue(0)
        form_layout.addRow("X坐标:", self.x_spinbox)
        
        # Y坐标
        self.y_spinbox = QSpinBox()
        self.y_spinbox.setRange(0, 5000)
        self.y_spinbox.setValue(0)
        form_layout.addRow("Y坐标:", self.y_spinbox)
        
        # 宽度
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 5000)
        self.width_spinbox.setValue(100)
        form_layout.addRow("宽度:", self.width_spinbox)
        
        # 高度
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(1, 5000)
        self.height_spinbox.setValue(100)
        form_layout.addRow("高度:", self.height_spinbox)
        
        layout.addWidget(form_group)
        
        # 图像尺寸信息
        img_height, img_width = self.image.shape[:2]
        size_label = QLabel(f"图像尺寸：{img_width} × {img_height} 像素")
        size_label.setStyleSheet("background-color: #e3f2fd; padding: 10px; border-radius: 5px;")
        layout.addWidget(size_label)
        
        # 应用按钮
        apply_btn = QPushButton('应用手动输入的ROI')
        apply_btn.clicked.connect(self.apply_manual_roi)
        apply_btn.setStyleSheet("QPushButton { padding: 10px; background-color: #2196f3; color: white; border-radius: 5px; }")
        layout.addWidget(apply_btn)
        
        layout.addStretch()
        
        self.tab_widget.addTab(manual_widget, "手动输入")
    
    def on_roi_selected(self, x, y, width, height):
        """ROI选择事件"""
        self.selected_roi = (x, y, width, height)
        # 更新显示标签
        self.selection_label.setText(f'当前选择：({x}, {y}) 尺寸：{width}×{height}')
        # 同时更新手动输入框
        self.set_manual_roi((x, y, width, height))
        # 切换到手动输入选项卡显示结果
        self.tab_widget.setCurrentIndex(1)
    
    def apply_manual_roi(self):
        """应用手动输入的ROI"""
        x = self.x_spinbox.value()
        y = self.y_spinbox.value()
        width = self.width_spinbox.value()
        height = self.height_spinbox.value()
        
        self.selected_roi = (x, y, width, height)
        self.selection_label.setText(f'当前选择：({x}, {y}) 尺寸：{width}×{height}')
        
        # 如果ROI选择控件存在，清除交互式选择
        if hasattr(self, 'roi_widget'):
            self.roi_widget.clear_selection()
    
    def set_manual_roi(self, roi):
        """设置手动输入的ROI值"""
        if len(roi) == 4:
            x, y, width, height = roi
            self.x_spinbox.setValue(x)
            self.y_spinbox.setValue(y)
            self.width_spinbox.setValue(width)
            self.height_spinbox.setValue(height)
    
    def clear_selection(self):
        """清除选择"""
        self.selected_roi = None
        self.selection_label.setText('当前选择：未选择')
        
        # 清除交互式选择
        if hasattr(self, 'roi_widget'):
            self.roi_widget.clear_selection()
        
        # 重置手动输入
        self.x_spinbox.setValue(0)
        self.y_spinbox.setValue(0)
        self.width_spinbox.setValue(100)
        self.height_spinbox.setValue(100)
    
    def get_roi(self):
        """获取ROI"""
        return self.selected_roi
    
    def zoom_in(self):
        """放大"""
        if hasattr(self, 'roi_widget'):
            self.roi_widget.scale(1.15, 1.15)
            self.roi_widget.scale_factor *= 1.15
            self.update_zoom_label()
    
    def zoom_out(self):
        """缩小"""
        if hasattr(self, 'roi_widget'):
            self.roi_widget.scale(1/1.15, 1/1.15)
            self.roi_widget.scale_factor /= 1.15
            self.update_zoom_label()
    
    def fit_to_window(self):
        """适应窗口"""
        if hasattr(self, 'roi_widget'):
            self.roi_widget.fit_image_to_view()
            self.update_zoom_label()
    
    def original_size(self):
        """原始大小"""
        if hasattr(self, 'roi_widget'):
            # 重置变换
            self.roi_widget.resetTransform()
            self.roi_widget.scale_factor = 1.0
            self.update_zoom_label()
    
    def update_zoom_label(self):
        """更新缩放比例标签"""
        if hasattr(self, 'roi_widget'):
            zoom_percent = int(self.roi_widget.scale_factor * 100)
            self.zoom_label.setText(f'{zoom_percent}%')
            debug(f"ROI选择 - 缩放比例更新: {zoom_percent}%", "ROI_SELECTION")