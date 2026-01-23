"""
Canvas Node Components

This module provides visual node components for the algorithm canvas,
including algorithm nodes and image nodes with full interaction support.
"""

import os
import sys
import subprocess
import cv2
from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsTextItem, QMenu, QMessageBox, QFileDialog,
                             QGroupBox, QVBoxLayout, QLabel, QPushButton)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal, QMimeData
from PyQt6.QtGui import QPen, QBrush, QColor, QFont, QDrag

import numpy as np

from core.managers.log_manager import debug
from core.interfaces.algorithm.composite.combined_algorithm import CombinedAlgorithm


class AlgorithmNode(QGraphicsRectItem):
    """Algorithm node"""
    
    # Position change signal
    scenePositionChanged = pyqtSignal()
    
    def __init__(self, algorithm, x: float, y: float, node_id: str, canvas):
        super().__init__(0, 0, 180, 80)
        self.algorithm = algorithm
        self.node_id = node_id
        self.canvas = canvas
        self.setPos(x, y)
        self.setZValue(1)
        
        # Node state
        self.is_selected = False
        self.is_executing = False
        self.execution_result = None
        self.execution_status = None  # 'success', 'failure', 'executing', None
        
        # Connection state
        self.input_connected = False
        self.output_connected = False
        
        # Store original colors for status feedback
        self.default_brush = None
        
        # Ports - changed to pins in the middle of four sides
        self.ports = {}  # Store all pins: {'left': pin, 'right': pin, 'top': pin, 'bottom': pin}
        self.port_hover = False
        
        # Configuration storage
        self.config = None  # Store AlgorithmConfig, used for saving nested structure
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up node UI"""
        # Set node style
        default_color = QColor(240, 240, 240)
        self.setBrush(QBrush(default_color))
        self.setPen(QPen(QColor(100, 100, 100), 2))
        
        # Store default brush for status restoration
        self.default_brush = self.brush()
        
        # Add algorithm name
        info = self.algorithm.get_info()
        name_text = QGraphicsTextItem(info.display_name, self)
        name_text.setPos(10, 10)
        name_text.setDefaultTextColor(QColor(0, 0, 0))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        name_text.setFont(font)
        
        # Add algorithm category
        category_text = QGraphicsTextItem(info.category, self)
        category_text.setPos(10, 30)
        category_text.setDefaultTextColor(QColor(100, 100, 100))
        small_font = QFont()
        small_font.setPointSize(8)
        category_text.setFont(small_font)
        
        # Add pins in the middle of four sides
        self.create_ports()
        
        # Set draggable and selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        
        # Add parameter button (top right corner)
        self.add_param_button()
    
    def create_ports(self):
        """Create pins on left and right sides"""
        node_rect = self.rect()
        width = node_rect.width()
        height = node_rect.height()
        
        # Left pin (input) - red when not connected
        left_pin = QGraphicsRectItem(-6, height//2 - 6, 12, 12, self)
        left_pin.setBrush(QBrush(QColor(255, 100, 100)))
        left_pin.setPen(QPen(QColor(200, 50, 50), 2))
        left_pin.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)  # Don't block mouse events
        self.ports['left'] = left_pin
        
        # Right pin (output) - red when not connected
        right_pin = QGraphicsRectItem(width - 6, height//2 - 6, 12, 12, self)
        right_pin.setBrush(QBrush(QColor(255, 100, 100)))
        right_pin.setPen(QPen(QColor(200, 50, 50), 2))
        right_pin.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)  # Don't block mouse events
        self.ports['right'] = right_pin
    
    def add_param_button(self):
        """Add parameter button"""
        self.param_button = QGraphicsRectItem(self.rect().width() - 25, 5, 20, 20, self)
        self.param_button.setBrush(QBrush(QColor(100, 150, 200)))
        self.param_button.setPen(QPen(QColor(50, 100, 150), 1))
        
        # Add parameter icon
        param_text = QGraphicsTextItem("⚙", self.param_button)
        param_text.setPos(2, 0)
        param_text.setDefaultTextColor(QColor(255, 255, 255))
        small_font = QFont()
        small_font.setPointSize(10)
        param_text.setFont(small_font)
    
    def update_port_colors(self):
        """Update all pin colors"""
        # Update left pin (input)
        if self.input_connected:
            self.ports['left'].setBrush(QBrush(QColor(0, 255, 0)))  # Green
            self.ports['left'].setPen(QPen(QColor(0, 200, 0), 2))
        else:
            self.ports['left'].setBrush(QBrush(QColor(255, 100, 100)))  # Red
            self.ports['left'].setPen(QPen(QColor(200, 50, 50), 2))
        
        # Update right pin (output)
        if self.output_connected:
            self.ports['right'].setBrush(QBrush(QColor(0, 255, 0)))  # Green
            self.ports['right'].setPen(QPen(QColor(0, 200, 0), 2))
        else:
            self.ports['right'].setBrush(QBrush(QColor(255, 100, 100)))  # Red
            self.ports['right'].setPen(QPen(QColor(200, 50, 50), 2))
    
    def update_port_colors_realtime(self):
        """Update port colors based on actual connection status in real-time"""
        if not self.canvas or not hasattr(self, 'ports'):
            debug(f"节点 {getattr(self, 'node_id', 'unknown')} 无法更新端口颜色: 缺少canvas或ports", "CHAIN")
            return
        
        # Check actual connection status for each port
        left_connected = self.canvas.is_port_connected(self, 'left')
        right_connected = self.canvas.is_port_connected(self, 'right')
        
        # debug(f"节点 {getattr(self, 'node_id', 'unknown')} 连接状态: left={left_connected}, right={right_connected}", "CHAIN")
        
        # Update left pin (input) based on actual connections
        if left_connected:
            self.ports['left'].setBrush(QBrush(QColor(0, 255, 0)))  # Green
            self.ports['left'].setPen(QPen(QColor(0, 200, 0), 2))
            # debug(f"节点 {getattr(self, 'node_id', 'unknown')} 左端口设为绿色", "CHAIN")
        else:
            self.ports['left'].setBrush(QBrush(QColor(255, 100, 100)))  # Red
            self.ports['left'].setPen(QPen(QColor(200, 50, 50), 2))
            # debug(f"节点 {getattr(self, 'node_id', 'unknown')} 左端口设为红色", "CHAIN")
        
        # Update right pin (output) based on actual connections
        if right_connected:
            self.ports['right'].setBrush(QBrush(QColor(0, 255, 0)))  # Green
            self.ports['right'].setPen(QPen(QColor(0, 200, 0), 2))
            # debug(f"节点 {getattr(self, 'node_id', 'unknown')} 右端口设为绿色", "CHAIN")
        else:
            self.ports['right'].setBrush(QBrush(QColor(255, 100, 100)))  # Red
            self.ports['right'].setPen(QPen(QColor(200, 50, 50), 2))
            # debug(f"节点 {getattr(self, 'node_id', 'unknown')} 右端口设为红色", "CHAIN")
        
        # Update internal states for compatibility
        self.input_connected = left_connected
        self.output_connected = right_connected
        
        # Force UI update
        if hasattr(self, 'scene') and self.scene():
            self.scene().update()
        if hasattr(self, 'update'):
            self.update()
        # debug(f"节点 {getattr(self, 'node_id', 'unknown')} UI 已强制刷新", "CHAIN")
    
    def hoverMoveEvent(self, event):
        """Mouse hover move event"""
        # Check if hovering on any pin
        was_hover = self.port_hover
        self.port_hover = False
        
        for port_name, port_item in self.ports.items():
            port_rect = port_item.sceneBoundingRect()
            if port_rect.contains(event.scenePos()):
                self.port_hover = True
                break
        
        if self.port_hover != was_hover:
            if self.port_hover:
                self.canvas.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
        
        super().hoverMoveEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Mouse leave event"""
        self.port_hover = False
        self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)
        
    def get_input_pos(self) -> QPointF:
        """Get input port position (left side)"""
        return self.mapToScene(self.ports['left'].rect().center() + self.ports['left'].pos())
    
    def get_output_pos(self) -> QPointF:
        """Get output port position (right side)"""
        return self.mapToScene(self.ports['right'].rect().center() + self.ports['right'].pos())
    
    def get_port_pos(self, port_name: str) -> QPointF:
        """Get specified pin position"""
        if port_name in self.ports:
            return self.mapToScene(self.ports[port_name].rect().center() + self.ports[port_name].pos())
        return self.sceneBoundingRect().center()
    
    def itemChange(self, change, value):
        """Item change event"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.is_selected = value
            if value:
                self.setPen(QPen(QColor(0, 120, 215), 3))
            else:
                self.setPen(QPen(QColor(100, 100, 100), 2))
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Position change triggers automatic connection line updates via timer
            # Use canvas's debounce save mechanism to avoid frequent saves during dragging
            if hasattr(self.canvas, 'debounce_save_config'):
                self.canvas.debounce_save_config(500)  # 500ms debounce delay
        
        return super().itemChange(change, value)
    
    def mousePressEvent(self, event):
        """Mouse press event"""
        # Call parent method first to ensure event propagation
        super().mousePressEvent(event)
        
        # Check right-click
        if event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event)
            return
        
        # Single-click on node shows parameter configuration
        if hasattr(self.canvas, 'node_selected'):
            self.canvas.node_selected.emit(self)
    
    def show_context_menu(self, event):
        """Show context menu"""
        menu = QMenu()
        
        # Basic operations
        delete_action = menu.addAction("🗑️ 删除节点")
        delete_action.triggered.connect(lambda: self.canvas.remove_node(self))
        
        menu.addSeparator()
        
        # Parameter configuration
        config_action = menu.addAction("⚙️ 参数配置")
        config_action.triggered.connect(lambda: self.canvas.node_selected.emit(self))
        
        # If combined algorithm, add recursive debug options
        if isinstance(self.algorithm, CombinedAlgorithm):
            menu.addSeparator()
            debug_action = menu.addAction("🔍 递归调试组合算法")
            debug_action.triggered.connect(lambda: self.debug_combined_algorithm())
            
            # View internal structure
            view_structure_action = menu.addAction("📋 查看内部结构")
            view_structure_action.triggered.connect(lambda: self.view_combined_structure())
        
        # Execution results - check multiple conditions
        has_result = (self.execution_result is not None or 
                     (hasattr(self.canvas, 'parent_dialog') and 
                      hasattr(self.canvas.parent_dialog, 'current_execution_order') and
                      self in self.canvas.parent_dialog.current_execution_order))
        
        if has_result:
            menu.addSeparator()
            result_action = menu.addAction("📊 查看执行结果")
            result_action.triggered.connect(lambda: self.canvas.on_node_double_clicked(self))
            debug(f"Right-click menu added view result option - Node: {self.algorithm.get_info().display_name}", "CHAIN")
        else:
            debug(f"Right-click menu skipped view result option - Node: {self.algorithm.get_info().display_name}, execution_result: {self.execution_result}", "CHAIN")
        
        # Show menu
        menu.exec(event.screenPos())
    
    def debug_combined_algorithm(self):
        """Recursively debug combined algorithm"""
        if hasattr(self.canvas, 'parent_dialog'):
            self.canvas.parent_dialog.open_recursive_debug_dialog(self.algorithm)
    
    def view_combined_structure(self):
        """View combined algorithm internal structure"""
        if not isinstance(self.algorithm, CombinedAlgorithm):
            return
            
        config = self.algorithm.get_chain_config()
        if not config:
            return
        
        # Create info dialog
        dialog = QMessageBox(self.canvas)
        dialog.setWindowTitle(f"组合算法结构 - {self.algorithm.get_info().display_name}")
        dialog.setIcon(QMessageBox.Icon.Information)
        
        # Build structure info
        structure_info = f"组合算法: {self.algorithm.get_info().display_name}\n"
        structure_info += f"包含算法数量: {len(config.algorithms)}\n"
        structure_info += f"创建时间: {config.metadata.get('created_at', '未知')}\n\n"
        
        structure_info += "内部算法列表:\n"
        structure_info += "=" * 50 + "\n"
        
        for i, algo_config in enumerate(config.algorithms, 1):
            structure_info += f"\n{i}. {algo_config.display_name} (ID: {algo_config.algorithm_id})\n"
            structure_info += f"   描述: {algo_config.description}\n"
            structure_info += f"   参数数量: {len(algo_config.parameters)}\n"
            
            # Show key parameters
            key_params = [p for p in algo_config.parameters[:3]]  # Only show first 3 parameters
            if key_params:
                structure_info += "   关键参数:\n"
                for param in key_params:
                    structure_info += f"     - {param.name}: {param.value} ({param.param_type.value})\n"
        
        # If there's connection info
        if config.connections:
            structure_info += "\n连接关系:\n"
            structure_info += "-" * 30 + "\n"
            for conn in config.connections:
                structure_info += f"{conn.from_algorithm} → {conn.to_algorithm}\n"
        
        dialog.setText(structure_info)
        dialog.exec()
    
    def mouseDoubleClickEvent(self, event):
        """Mouse double-click event"""
        super().mouseDoubleClickEvent(event)
        
        # Call canvas's node double-click handler (show execution results)
        if hasattr(self.canvas, 'on_node_double_clicked'):
            self.canvas.on_node_double_clicked(self)
    
    def set_executing(self, executing: bool):
        """Set execution state"""
        self.is_executing = executing
        if executing:
            self.setBrush(QBrush(QColor(255, 255, 200)))
        else:
            self.setBrush(QBrush(QColor(240, 240, 240)))
    
    def set_execution_result(self, success: bool):
        """Set execution result"""
        if success:
            self.setBrush(QBrush(QColor(200, 255, 200)))
        else:
            self.setBrush(QBrush(QColor(255, 200, 200)))


class ImageNode(QGraphicsRectItem):
    """Image node (input/output)"""
    
    def __init__(self, node_type: str, x: float, y: float, node_id: str, canvas):
        super().__init__(0, 0, 160, 80)
        self.node_type = node_type  # "input" or "output"
        self.node_id = node_id
        self.canvas = canvas
        self.setPos(x, y)
        self.setZValue(1)
        self.image_data = None
        self.is_selected = False

        # 文件路径信息
        self.file_paths = []  # 存储所有文件路径
        self.file_path = "未知路径"  # 当前文件路径

        # Port
        self.port = None
        # Connection state
        self.connected = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up node UI"""
        # Set node style
        if self.node_type == "input":
            self.setBrush(QBrush(QColor(200, 230, 255)))
            title = "输入图像"
            port_color = QColor(255, 0, 0)  # 红色表示未连接
        else:
            self.setBrush(QBrush(QColor(255, 230, 200)))
            title = "输出图像"
            port_color = QColor(255, 0, 0)  # 红色表示未连接
            
        self.setPen(QPen(QColor(100, 100, 100), 2))
        
        # Add title
        self.title_text = QGraphicsTextItem(title, self)
        self.title_text.setPos(10, 10)
        self.title_text.setDefaultTextColor(QColor(0, 0, 0))
        font = QFont()
        font.setBold(True)
        self.title_text.setFont(font)

        # Add subtitle (initially hidden)
        self.subtitle_text = QGraphicsTextItem("", self)
        self.subtitle_text.setPos(10, 30)
        self.subtitle_text.setDefaultTextColor(QColor(100, 100, 100))
        small_font = QFont()
        small_font.setPointSize(8)
        self.subtitle_text.setFont(small_font)
        
        # Add port
        if self.node_type == "input":
            self.port = QGraphicsEllipseItem(155, 35, 10, 10, self)
        else:
            self.port = QGraphicsEllipseItem(-5, 35, 10, 10, self)
            
        self.port.setBrush(QBrush(port_color))
        self.port.setPen(QPen(port_color.darker(), 2))
        self.port.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)  # Don't block mouse events
        
        # Set draggable and selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
    def get_port_pos(self) -> QPointF:
        """Get port position"""
        return self.mapToScene(self.port.pos() + QPointF(5, 5))
    
    def set_image(self, image):
        """Set image data and update visual representation - 支持单张图片或图片列表"""
        self.image_data = image

        # Update visual feedback to show image has been updated
        if image is not None:
            if isinstance(image, list):
                # 多张图片模式
                image_count = len(image)
                debug(f"ImageNode {self.node_id} 已设置{image_count}张新图像", "CHAIN")
                if self.node_type == "output":
                    # 输出节点多张图片时的颜色
                    self.setBrush(QBrush(QColor(255, 200, 150)))  # 更深的橙色
                # 更新显示文本
                self.update_display_for_multiple_images(image_count)
            else:
                # 单张图片模式
                debug(f"ImageNode {self.node_id} 已设置新图像，尺寸: {image.shape}", "CHAIN")
                if self.node_type == "output":
                    # Make output node slightly darker when it has new data
                    self.setBrush(QBrush(QColor(255, 220, 180)))  # Darker orange
                # 清空多图片显示
                self.update_display_for_multiple_images(0)
        else:
            debug(f"ImageNode {self.node_id} 图像数据被清空", "CHAIN")
            # Restore original appearance
            if self.node_type == "output":
                self.setBrush(QBrush(QColor(255, 230, 200)))  # Original orange
            # 清空多图片显示
            self.update_display_for_multiple_images(0)

        # Trigger visual update
        self.update()
        
    def itemChange(self, change, value):
        """Item change event"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.is_selected = value
            if value:
                self.setPen(QPen(QColor(0, 120, 215), 3))
            else:
                self.setPen(QPen(QColor(100, 100, 100), 2))
        return super().itemChange(change, value)
    
    def mousePressEvent(self, event):
        """Mouse press event"""
        # Call parent method first to ensure event propagation
        super().mousePressEvent(event)
        
        # Show image info on click
        if self.image_data is not None:
            self.show_image_info()
        
        # Notify canvas that node is selected (for parameter configuration)
        if hasattr(self.canvas, 'node_selected'):
            self.canvas.node_selected.emit(self)
    
    def mouseDoubleClickEvent(self, event):
        """Mouse double-click event"""
        super().mouseDoubleClickEvent(event)
        
        debug(f"双击{self.node_type}图像节点，有图像数据: {self.image_data is not None}", "CHAIN")
        
        # Handle input/output image nodes
        if self.node_type == "input":
            # For input node, load new image (load_image handles the display if needed)
            self.load_image()
            # Don't automatically show image here - let load_image decide what to display
            debug(f"输入节点图片加载完成", "CHAIN")
        elif self.node_type == "output":
            # For output node, always try to get the latest result first
            # This ensures we show the most recent execution result, not cached data
            debug(f"输出节点双击，主动获取最新执行结果", "CHAIN")
            self._try_get_latest_output_image()

            # If we still have image data after trying to get latest, show it
            if self.image_data is not None:
                debug(f"显示输出图像节点数据，尺寸: {self.image_data.shape}", "CHAIN")
                self.show_image()
            else:
                debug(f"输出图像节点没有数据，显示提示信息", "CHAIN")
    
    def load_image(self):
        """Load image - 支持单张图片或多张图片输入"""
        try:
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            from utils.image_utils import load_image as utils_load_image

            # 提供输入模式选择
            msg_box = QMessageBox()
            msg_box.setWindowTitle("选择输入模式")
            msg_box.setText("请选择图像输入模式：")
            single_button = msg_box.addButton("单张图片", QMessageBox.ButtonRole.AcceptRole)
            multiple_button = msg_box.addButton("多张图片", QMessageBox.ButtonRole.AcceptRole)
            folder_button = msg_box.addButton("整个文件夹", QMessageBox.ButtonRole.AcceptRole)
            cancel_button = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()

            images = []
            file_paths = []  # 存储文件路径
            source_info = ""

            if msg_box.clickedButton() == cancel_button:
                return
            elif msg_box.clickedButton() == single_button:
                # 单张图片模式
                file_path, _ = QFileDialog.getOpenFileName(
                    None,
                    '选择输入图像',
                    '',
                    '图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff)'
                )
                if file_path:
                    image = utils_load_image(file_path)
                    if image is not None:
                        images = [image]
                        file_paths = [file_path]
                        source_info = f"单张图片: {file_path}"
            elif msg_box.clickedButton() == multiple_button:
                # 多张图片模式
                file_paths, _ = QFileDialog.getOpenFileNames(
                    None,
                    '选择多张输入图像',
                    '',
                    '图像文件 (*.png *.jpg *.jpeg *.bmp *.tiff)'
                )
                if file_paths:
                    for file_path in file_paths:
                        image = utils_load_image(file_path)
                        if image is not None:
                            images.append(image)
                    source_info = f"多张图片: {len(images)}张"
            elif msg_box.clickedButton() == folder_button:
                # 整个文件夹模式
                folder_path = QFileDialog.getExistingDirectory(
                    None,
                    '选择图像文件夹'
                )
                if folder_path:
                    import os
                    import glob
                    # 支持常见图像格式
                    image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tiff']
                    for ext in image_extensions:
                        pattern = os.path.join(folder_path, ext)
                        for file_path in glob.glob(pattern):
                            image = utils_load_image(file_path)
                            if image is not None:
                                images.append(image)
                                file_paths.append(file_path)
                    source_info = f"文件夹: {len(images)}张图片"

            if images:
                if len(images) == 1:
                    # 单张图片模式，直接设置
                    self.image_data = images[0]
                    # 存储文件信息
                    if file_paths:
                        self.file_paths = file_paths
                        self.file_path = file_paths[0]
                    else:
                        self.file_paths = []
                        self.file_path = "未知路径"
                    # Update node appearance to show image loaded
                    self.setBrush(QBrush(QColor(150, 200, 255)))
                    # 更新节点显示文本
                    self.update_display_for_multiple_images(0)
                else:
                    # 多张图片模式，存储为列表
                    self.image_data = images  # 存储为图像列表
                    # 存储文件路径信息
                    self.file_paths = file_paths if file_paths else [f"图片_{i+1}" for i in range(len(images))]
                    self.file_path = f"{len(images)}张图片"
                    # Update node appearance to show multiple images loaded
                    self.setBrush(QBrush(QColor(120, 180, 255)))  # 稍微不同的蓝色表示多张图片

                # Notify canvas to update status bar
                if hasattr(self.canvas, 'status_update_callback'):
                    self.canvas.status_update_callback(f"输入图像已加载 - {source_info}")

                # 更新节点显示文本以反映多图片状态
                self.update_display_for_multiple_images(len(images))

            else:
                if hasattr(self.canvas, 'status_update_callback'):
                    self.canvas.status_update_callback("未找到有效的图像文件")

        except Exception as e:
            if hasattr(self.canvas, 'status_update_callback'):
                self.canvas.status_update_callback(f"加载图像时出错: {str(e)}")
            from core.managers.log_manager import error
            error(f"加载图像时出错: {str(e)}", "IMAGE_NODE")

    def update_display_for_multiple_images(self, image_count: int):
        """更新节点显示以反映多图片状态"""
        if image_count > 1:
            # 更新副标题显示图片数量
            self.subtitle_text.setPlainText(f"{image_count}张图片")
        else:
            # 单张图片时清空副标题
            self.subtitle_text.setPlainText("")

    def show_image(self):
        """Show image - 使用统一的预览接口"""
        if self.image_data is not None:
            try:
                from .image_dialog import ImageDisplayDialog

                # 创建标题
                if isinstance(self.image_data, list):
                    title = "所有图片预览"
                else:
                    title = f"{self.node_type}图像预览"

                # 使用统一的图片预览对话框
                dialog = ImageDisplayDialog(self.image_data, title, self.canvas)
                dialog.exec()

            except Exception as e:
                from core.managers.log_manager import error
                error(f"显示图片时出错: {str(e)}", "IMAGE_NODE")
    
    def _try_get_latest_output_image(self):
        """Try to get the latest output image from canvas execution results"""
        try:
            # Get parent dialog to access execution results
            if hasattr(self.canvas, 'parent_dialog') and self.canvas.parent_dialog:
                parent_dialog = self.canvas.parent_dialog

                latest_image = None
                latest_timestamp = 0

                # Method 1: Try to get from current execution order first (most reliable)
                if hasattr(parent_dialog, 'current_execution_order'):
                    execution_order = parent_dialog.current_execution_order
                    debug(f"找到执行顺序，包含 {len(execution_order)} 个节点", "CHAIN")

                    # Find the last algorithm with successful execution result
                    for node in reversed(execution_order):
                        if (hasattr(node, 'execution_result') and
                            node.execution_result and
                            node.execution_result.success and
                            node.execution_result.output_image is not None):

                            debug(f"从节点 {node.algorithm.get_info().display_name} 获取输出图像", "CHAIN")
                            latest_image = node.execution_result.output_image
                            # Found result, break and use it
                            break

                # Method 2: If no result from execution order, try current_output_image
                if latest_image is None and hasattr(parent_dialog, 'current_output_image') and parent_dialog.current_output_image is not None:
                    debug(f"从parent_dialog.current_output_image获取输出图像", "CHAIN")
                    latest_image = parent_dialog.current_output_image

                # Method 3: Last resort - check all algorithm nodes on canvas for any execution result
                if latest_image is None:
                    debug(f"尝试从画布上的所有算法节点查找最新结果", "CHAIN")
                    for node_id, node in parent_dialog.canvas.nodes.items():
                        if (hasattr(node, 'execution_result') and
                            node.execution_result and
                            node.execution_result.success and
                            node.execution_result.output_image is not None):

                            # Check if this result has a timestamp (if available)
                            result_time = getattr(node.execution_result, 'timestamp', 0)
                            if result_time > latest_timestamp:
                                latest_image = node.execution_result.output_image
                                latest_timestamp = result_time
                                debug(f"找到更新的结果从节点 {node.algorithm.get_info().display_name}", "CHAIN")

                # If we found an image, set it (but don't show - let caller handle display)
                if latest_image is not None:
                    debug(f"成功获取到输出图像，尺寸: {latest_image.shape}", "CHAIN")
                    self.set_image(latest_image)
                    return
                else:
                    debug(f"未找到任何有效的输出图像", "CHAIN")

            # No result found - show message
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                None, 
                "提示", 
                "输出节点没有图像数据。\n请先执行算法链，或确保最后一个算法产生输出图像。"
            )
            
        except Exception as e:
            debug(f"尝试获取最新输出图像时出错: {str(e)}", "CHAIN")
            import traceback
            debug(f"错误详情: {traceback.format_exc()}", "CHAIN")

    def show_image_info(self):
        """Show image info - 支持多张图片信息显示"""
        if self.image_data is not None:
            if isinstance(self.image_data, list):
                # 多张图片模式
                image_count = len(self.image_data)
                if image_count == 0:
                    return

                # 获取第一张图片的基本信息
                first_image = self.image_data[0]
                height, width = first_image.shape[:2]
                channels = first_image.shape[2] if len(first_image.shape) == 3 else 1

                # 格式化图片信息
                if channels == 1:
                    channel_info = "灰度图像"
                elif channels == 3:
                    channel_info = "彩色图像 (BGR)"
                elif channels == 4:
                    channel_info = "彩色图像 (BGRA)"
                else:
                    channel_info = f"{channels}通道图像"

                # 计算总大小
                total_size = sum(img.nbytes for img in self.image_data)

                info_text = f"""所有图片信息:
图片数量: {image_count} 张
单张尺寸: {width} × {height} 像素
通道格式: {channel_info}
数据类型: {first_image.dtype}
总内存占用: {total_size / 1024:.1f} KB ({total_size / 1024 / 1024:.1f} MB)"""

                # Display info in status bar
                if hasattr(self.canvas, 'status_update_callback'):
                    self.canvas.status_update_callback(f"多张图片: {image_count}张, {width}×{height}, {channel_info}")

                # If there's parameter configuration area, show detailed info
                if hasattr(self.canvas, 'show_image_info_in_params'):
                    self.canvas.show_image_info_in_params(info_text, self.image_data[0])
            else:
                # 单张图片模式
                height, width = self.image_data.shape[:2]
                channels = self.image_data.shape[2] if len(self.image_data.shape) == 3 else 1

                # Format image info
                if channels == 1:
                    channel_info = "灰度图像"
                elif channels == 3:
                    channel_info = "彩色图像 (BGR)"
                elif channels == 4:
                    channel_info = "彩色图像 (BGRA)"
                else:
                    channel_info = f"{channels}通道图像"

                info_text = f"""图像信息:
尺寸: {width} × {height} 像素
通道: {channel_info}
数据类型: {self.image_data.dtype}
文件大小: {self.image_data.nbytes / 1024:.1f} KB"""

                # Display info in status bar
                if hasattr(self.canvas, 'status_update_callback'):
                    self.canvas.status_update_callback(f"图像: {width}×{height}, {channel_info}")

                # If there's parameter configuration area, show detailed info
                if hasattr(self.canvas, 'show_image_info_in_params'):
                    self.canvas.show_image_info_in_params(info_text, self.image_data)
    
    def update_port_color(self):
        """Update port color"""
        if self.connected:
            # Turns green after connection
            self.port.setBrush(QBrush(QColor(0, 255, 0)))
            self.port.setPen(QPen(QColor(0, 200, 0), 2))
        else:
            # Red color when not connected (both input and output)
            self.port.setBrush(QBrush(QColor(255, 0, 0)))
            self.port.setPen(QPen(QColor(200, 0, 0), 2))
    
    def update_port_colors_realtime(self):
        """Update port color based on actual connection status in real-time"""
        #debug(f"=== ImageNode {getattr(self, 'node_id', 'unknown')} 开始更新端口颜色 ===", "CHAIN")
        if not self.canvas or not hasattr(self, 'port'):
            debug(f"ImageNode {getattr(self, 'node_id', 'unknown')} 无法更新端口颜色: 缺少canvas或port", "CHAIN")
            return
        
        # Check actual connection status from canvas
        # input node has right port (output), output node has left port (input)
        port_direction = 'right' if self.node_type == 'input' else 'left'
        is_actually_connected = self.canvas.is_port_connected(self, port_direction)
        
        # debug(f"ImageNode {getattr(self, 'node_id', 'unknown')} ({self.node_type}) 连接状态: {port_direction}={is_actually_connected}", "CHAIN")
        
        # Update port color based on real connection status
        if is_actually_connected:
            # Green when connected
            self.port.setBrush(QBrush(QColor(0, 255, 0)))
            self.port.setPen(QPen(QColor(0, 200, 0), 2))
            # debug(f"ImageNode {getattr(self, 'node_id', 'unknown')} 端口设为绿色", "CHAIN")
        else:
            # Red when not connected
            self.port.setBrush(QBrush(QColor(255, 100, 100)))
            self.port.setPen(QPen(QColor(200, 50, 50), 2))
            # debug(f"ImageNode {getattr(self, 'node_id', 'unknown')} 端口设为红色", "CHAIN")
        
        # Update internal state for compatibility
        self.connected = is_actually_connected
        
        # Force UI update
        if hasattr(self, 'scene') and self.scene():
            self.scene().update()
        if hasattr(self, 'update'):
            self.update()
        # debug(f"ImageNode {getattr(self, 'node_id', 'unknown')} UI 已强制刷新", "CHAIN")