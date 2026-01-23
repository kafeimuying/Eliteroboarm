"""
VMC Canvas Node Components

This module provides visual node components for the vision-motion control algorithm canvas,
including data processing nodes, hardware nodes, and control nodes with full interaction support.
Based on ui/canvas/nodes.py with VMC prefix (Vision-Motion Control).
"""

import os
import sys
import subprocess
import cv2
from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsItem,
                             QGraphicsTextItem, QMenu, QMessageBox, QFileDialog,
                             QGroupBox, QVBoxLayout, QLabel, QPushButton)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal, QMimeData
from PyQt6.QtGui import QPen, QBrush, QColor, QFont, QDrag

import numpy as np

from core.managers.log_manager import debug
from core.interfaces.algorithm.composite.combined_algorithm import CombinedAlgorithm
from enum import Enum


class VMCNodeBase(QGraphicsRectItem):
    """VMC Base node class - foundation for all VMC nodes"""

    # Position change signal
    scenePositionChanged = pyqtSignal()

    def __init__(self, node_type: str, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__(0, 0, 160, 80)
        self.node_type = node_type
        self.node_id = node_id
        self.canvas = canvas
        self.title = title
        self.setPos(x, y)
        self.setZValue(1)

        # Common node state
        self.is_selected = False
        self.is_executing = False
        self.execution_result = None
        self.execution_status = None  # 'success', 'failure', 'executing', None

        # Store original colors for status feedback
        self.default_brush = None

        # Configuration storage
        self.config = None

        # Ports storage - initialize before setup_base_ui
        self.ports = {}  # Store all ports: {'left': port, 'right': port, ...}

        self.setup_base_ui()

    def setup_base_ui(self):
        """Set up base node UI"""
        # Set node style based on node_type
        self.set_node_appearance()

        # Add title
        title_text = QGraphicsTextItem(self.get_display_title(), self)
        title_text.setPos(10, 10)
        title_text.setDefaultTextColor(QColor(0, 0, 0))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        title_text.setFont(font)
        self.title_item = title_text

        # Add pins in the middle of four sides
        self.create_ports()
        
        # Set draggable and selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        
        # Add parameter button (top right corner) - only for nodes that need it
        # This method will be overridden by subclasses that don't need parameter button
        self.add_param_button_if_needed()

    def add_param_button_if_needed(self):
        """Add parameter button - can be overridden by subclasses"""
        # Default implementation - no parameter button
        pass

    def add_param_button(self):
        """Add parameter button - common implementation for all nodes"""
        self.param_button = QGraphicsRectItem(self.rect().width() - 25, 5, 20, 20, self)
        self.param_button.setBrush(QBrush(QColor(100, 150, 200)))
        self.param_button.setPen(QPen(QColor(50, 100, 150), 1))

        # Add parameter icon
        param_text = QGraphicsTextItem("⚙", self.param_button)
        param_text.setPos(2, 0)
        param_text.setDefaultTextColor(QColor(255, 255, 255))

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

    def set_node_appearance(self):
        """Set node appearance based on type"""
        type_colors = {
            'input': QColor(200, 230, 255),      # Light blue
            'output': QColor(255, 230, 200),     # Light orange
            'vision': QColor(100, 200, 255),     # Blue
            'robot': QColor(100, 255, 100),      # Green
            'hardware': QColor(255, 200, 255),   # Pink
            'control': QColor(200, 150, 255),    # Purple
            'executor': QColor(255, 200, 100)    # Orange
        }

        default_color = QColor(240, 240, 240)
        color = type_colors.get(self.node_type, default_color)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(100, 100, 100), 2))
        self.default_brush = self.brush()

    def get_display_title(self):
        """Get display title for node"""
        if self.title:
            return self.title
        return f"{self.node_type.upper()} Node"

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

        # Note: Removed single-click node_selected.emit to allow double-click to work properly

    
    def show_context_menu(self, event):
        """Show context menu"""
        try:
            debug(f"VMC Context: Showing context menu for node {self.node_id} (type: {getattr(self, 'node_type', 'unknown')})", "VMC")

            menu = QMenu()

            # Basic operations
            delete_action = menu.addAction("🗑️ 删除节点")
            delete_action.triggered.connect(lambda: self._handle_delete_action())

            menu.addSeparator()

            # Parameter configuration
            config_action = menu.addAction("⚙️ 参数配置")
            config_action.triggered.connect(lambda: self._handle_config_action())

            debug(f"VMC Context: Menu created with {len(menu.actions())} actions", "VMC")

            # Show menu
            menu_result = menu.exec(event.screenPos())
            debug(f"VMC Context: Menu execution completed, result: {menu_result}", "VMC")

        except Exception as e:
            debug(f"VMC Context: Failed to show context menu: {e}", "VMC")
            import traceback
            debug(f"VMC Context: Traceback: {traceback.format_exc()}", "VMC")

    def _handle_delete_action(self):
        """Handle delete action"""
        try:
            debug(f"VMC Context: Delete action triggered for node {self.node_id}", "VMC")
            if hasattr(self.canvas, 'remove_node'):
                self.canvas.remove_node(self)
            else:
                debug(f"VMC Context: Canvas has no remove_node method", "VMC")
        except Exception as e:
            debug(f"VMC Context: Failed to handle delete action: {e}", "VMC")

    def _handle_config_action(self):
        """Handle configuration action"""
        try:
            debug(f"VMC Context: Config action triggered for node {self.node_id}", "VMC")
            if hasattr(self.canvas, 'node_selected'):
                self.canvas.node_selected.emit(self)
                debug(f"VMC Context: Emitted node_selected signal for {self.node_id}", "VMC")
            else:
                debug(f"VMC Context: Canvas has no node_selected signal, calling show_param_dialog directly", "VMC")
                if hasattr(self, 'show_param_dialog'):
                    self.show_param_dialog()
                else:
                    debug(f"VMC Context: Node {self.node_id} has no show_param_dialog method", "VMC")
        except Exception as e:
            debug(f"VMC Context: Failed to handle config action: {e}", "VMC")

    def set_executing(self, executing: bool):
        """Set execution state"""
        self.is_executing = executing
        if executing:
            self.setBrush(QBrush(QColor(255, 255, 200)))
        else:
            self.setBrush(self.default_brush)

    def set_execution_result(self, success: bool):
        """Set execution result"""
        if success:
            self.setBrush(QBrush(QColor(200, 255, 200)))
        else:
            self.setBrush(QBrush(QColor(255, 200, 200)))

    def update_port_colors_realtime(self):
        """Update port colors based on actual connection status in real-time"""
        if not self.canvas or not hasattr(self, 'ports'):
            return

        # Update input port
        if 'left' in self.ports:
            left_connected = self.canvas.is_port_connected(self, 'left')
            if left_connected:
                self.ports['left'].setBrush(QBrush(QColor(0, 255, 0)))
                self.ports['left'].setPen(QPen(QColor(0, 200, 0), 2))
            else:
                self.ports['left'].setBrush(QBrush(QColor(255, 100, 100)))
                self.ports['left'].setPen(QPen(QColor(200, 50, 50), 2))
            # Update connection state if node has these attributes
            if hasattr(self, 'input_connected'):
                self.input_connected = left_connected

        # Update output port
        if 'right' in self.ports:
            right_connected = self.canvas.is_port_connected(self, 'right')
            if right_connected:
                self.ports['right'].setBrush(QBrush(QColor(0, 255, 0)))
                self.ports['right'].setPen(QPen(QColor(0, 200, 0), 2))
            else:
                self.ports['right'].setBrush(QBrush(QColor(255, 100, 100)))
                self.ports['right'].setPen(QPen(QColor(200, 50, 50), 2))
            # Update connection state if node has these attributes
            if hasattr(self, 'output_connected'):
                self.output_connected = right_connected

    def get_port_pos(self, port_name: str) -> QPointF:
        """Get specified port position"""
        if port_name in self.ports:
            return self.mapToScene(self.ports[port_name].rect().center() + self.ports[port_name].pos())
        return self.sceneBoundingRect().center()


class VMCDataNode(VMCNodeBase):
    """VMC Data processing node base class"""

    def __init__(self, node_type: str, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__(node_type, x, y, node_id, canvas, title)

        # Connection state
        self.input_connected = False
        self.output_connected = False

        # Port hover state
        self.port_hover = False

        self.create_data_ports()

    def create_data_ports(self):
        """Create data flow ports"""
        node_rect = self.rect()
        width = node_rect.width()
        height = node_rect.height()

        # Input port (left side)
        if self.node_type != 'input':
            input_port = QGraphicsRectItem(-6, height//2 - 6, 12, 12, self)
            input_port.setBrush(QBrush(QColor(255, 100, 100)))
            input_port.setPen(QPen(QColor(200, 50, 50), 2))
            input_port.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.ports['left'] = input_port

        # Output port (right side)
        if self.node_type != 'output':
            output_port = QGraphicsRectItem(width - 6, height//2 - 6, 12, 12, self)
            output_port.setBrush(QBrush(QColor(255, 100, 100)))
            output_port.setPen(QPen(QColor(200, 50, 50), 2))
            output_port.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.ports['right'] = output_port

    
class VMCInputNode(VMCDataNode):
    """VMC Input node for data input (images, sensor data, etc.)"""

    def __init__(self, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__('input', x, y, node_id, canvas, title or "输入节点")
        self.data = None

    def set_data(self, data):
        """Set input data"""
        self.data = data
        if data is not None:
            # Update appearance to show data loaded
            self.setBrush(QBrush(QColor(150, 200, 255)))
            
            # Store data in canvas data_buffer as "input_data"
            if hasattr(self.canvas, 'data_buffer'):
                import numpy as np
                # Handle both single image and list of images
                if isinstance(data, list):
                    # Already a list, add directly
                    self.canvas.data_buffer.setdefault("input_data", []).extend(data)
                else:
                    # Single image, add to list
                    self.canvas.data_buffer.setdefault("input_data", []).append(data)
                debug(f"VMC Input: Stored {len(data) if isinstance(data, list) else 1} image(s) in data_buffer with key 'input_data'", "VMC")
            else:
                warning("VMC Input: Canvas data_buffer not available for data storage", "VMC")

    def clear_data_from_buffer(self):
        """Clear input data from canvas data_buffer"""
        if hasattr(self.canvas, 'data_buffer') and "input_data" in self.canvas.data_buffer:
            self.canvas.data_buffer["input_data"].clear()
            debug("VMC Input: Cleared input_data from canvas data_buffer", "VMC")

    def show_param_dialog(self):
        """Show input node parameter configuration dialog"""
        try:
            debug(f"VMC Input: Showing parameter dialog for node {self.node_id}", "VMC")
            from .node_parameter_dialogs import QMessageBox
            QMessageBox.information(None, "输入节点", "输入节点暂无特殊配置参数\n\n此节点用于接收图像数据源")
        except Exception as e:
            debug(f"VMC Input: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Input: Traceback: {traceback.format_exc()}", "VMC")


class VMCOutputNode(VMCDataNode):
    """VMC Output node for data output (results, visualizations, etc.)"""

    def __init__(self, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__('output', x, y, node_id, canvas, title or "输出节点")
        self.result_data = None

    def set_result(self, result):
        """Set output result"""
        self.result_data = result
        if result is not None:
            # Update appearance to show result available
            self.setBrush(QBrush(QColor(255, 220, 180)))

    def show_param_dialog(self):
        """Show output node parameter configuration dialog"""
        try:
            debug(f"VMC Output: Showing parameter dialog for node {self.node_id}", "VMC")
            from .node_parameter_dialogs import QMessageBox
            QMessageBox.information(None, "输出节点", "输出节点暂无特殊配置参数\n\n此节点用于显示处理结果")
        except Exception as e:
            debug(f"VMC Output: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Output: Traceback: {traceback.format_exc()}", "VMC")


class VMCAlgorithmNode(VMCDataNode):
    """VMC Algorithm processing node base class"""

    def __init__(self, algorithm, node_type: str, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__(node_type, x, y, node_id, canvas, title)
        self.algorithm = algorithm

        # Parameter button will be added by base class if needed

        # Update UI based on algorithm if available
        if hasattr(algorithm, 'get_info') and algorithm:
            self.update_from_algorithm_info()

    def add_param_button_if_needed(self):
        """Algorithm nodes need parameter button"""
        self.add_param_button()

        # Set smaller font for algorithm nodes
        if hasattr(self, 'param_button'):
            for item in self.param_button.childItems():
                if isinstance(item, QGraphicsTextItem):
                    small_font = QFont()
                    small_font.setPointSize(10)
                    item.setFont(small_font)

    def update_from_algorithm_info(self):
        """Update node display from algorithm info"""
        try:
            info = self.algorithm.get_info()

            # Update title
            if hasattr(self, 'title_item'):
                self.title_item.setPlainText(info.display_name)

            # Add category/subtitle
            category_text = QGraphicsTextItem(info.category, self)
            category_text.setPos(10, 30)
            category_text.setDefaultTextColor(QColor(100, 100, 100))
            small_font = QFont()
            small_font.setPointSize(8)
            category_text.setFont(small_font)

        except Exception as e:
            debug(f"Failed to update from algorithm info: {e}", "VMC")


class VMCVisionAlgorithmNode(VMCAlgorithmNode):
    """VMC Vision Algorithm node - specialized for computer vision processing"""

    def __init__(self, algorithm, x: float, y: float, node_id: str, canvas):
        super().__init__(algorithm, 'vision', x, y, node_id, canvas)

        # Vision-specific properties
        self.vision_type = getattr(algorithm, 'vision_type', 'general')
        self.processing_time = 0
        self.detection_count = 0
        
        # Dialog management
        self.vision_dialog = None
        self.vision_dialog_id = None  # Track dialog ID for debugging
        
        # Algorithm configuration storage
        self.algorithm_configs = []  # Store algorithm configurations from vision dialog

        # Update visual appearance
        self._add_vision_indicator()

    def _add_vision_indicator(self):
        """Add vision-specific visual indicator"""
        # Visual indicators removed - keeping method for compatibility
        pass

    def show_param_dialog(self):
        """Show vision algorithm parameter configuration dialog with latest config"""
        try:
            debug(f"VMC Vision: Showing parameter dialog for node {self.node_id}", "VMC")
            
            # Refresh current statistics and buffer status
            debug(f"VMC Vision: Current stats - processing_time: {self.processing_time:.3f}s, detection_count: {self.detection_count}", "VMC")
            if hasattr(self.canvas, 'data_buffer') and self.canvas.data_buffer:
                total_images = sum(len(images) for images in self.canvas.data_buffer.values())
                buffer_sources = list(self.canvas.data_buffer.keys())
                debug(f"VMC Vision: Current buffer - {total_images} images from {len(buffer_sources)} sources", "VMC")
            
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLabel, QPushButton, QMessageBox, QTextEdit
            
            # Create configuration dialog
            dialog = QDialog()
            dialog.setWindowTitle(f"视觉算法参数配置 - {self.node_id}")
            dialog.setMinimumSize(600, 500)
            
            layout = QVBoxLayout()
            
            # Algorithm information group
            if self.algorithm:
                info_group = QGroupBox("算法信息")
                info_layout = QFormLayout()
                
                # Get algorithm info
                try:
                    if hasattr(self.algorithm, 'get_info'):
                        alg_info = self.algorithm.get_info()
                        info_layout.addRow("算法ID:", QLabel(alg_info.algorithm_id or "N/A"))
                        info_layout.addRow("显示名称:", QLabel(alg_info.display_name or "N/A"))
                        info_layout.addRow("描述:", QLabel(alg_info.description or "N/A"))
                        info_layout.addRow("版本:", QLabel(alg_info.version or "N/A"))
                        info_layout.addRow("作者:", QLabel(alg_info.author or "N/A"))
                        info_layout.addRow("分类:", QLabel(f"{alg_info.category} / {alg_info.secondary_category or 'N/A'}"))
                        
                        if hasattr(alg_info, 'tags') and alg_info.tags:
                            tags_text = ", ".join(alg_info.tags)
                            info_layout.addRow("标签:", QLabel(tags_text))
                        
                        # Processing statistics
                        stats_layout = QHBoxLayout()
                        stats_layout.addWidget(QLabel(f"处理时间: {self.processing_time:.3f}s"))
                        stats_layout.addWidget(QLabel(f"检测数量: {self.detection_count}"))
                        info_layout.addRow("执行统计:", stats_layout)
                        
                except Exception as e:
                    info_layout.addRow("算法ID:", QLabel(str(getattr(self.algorithm, '_algorithm_id', 'unknown'))))
                    info_layout.addRow("类型:", QLabel(f"{self.vision_type}"))
                    debug(f"VMC Vision: Failed to get algorithm info: {e}", "VMC")
                
                info_group.setLayout(info_layout)
                layout.addWidget(info_group)
            
            # Vision configuration group
            vision_group = QGroupBox("视觉配置")
            vision_layout = QFormLayout()
            
            # Current buffer data status
            if hasattr(self.canvas, 'data_buffer') and self.canvas.data_buffer:
                total_images = sum(len(images) for images in self.canvas.data_buffer.values())
                buffer_sources = list(self.canvas.data_buffer.keys())
                vision_layout.addRow("缓冲状态:", QLabel(f"{total_images} 张图片来自 {len(buffer_sources)} 个源"))
                vision_layout.addRow("数据源:", QLabel(", ".join(buffer_sources)))
            else:
                vision_layout.addRow("缓冲状态:", QLabel("无数据"))
                vision_layout.addRow("数据源:", QLabel("无"))
            
            # Data buffer management
            buffer_btn = QPushButton("清空数据缓冲")
            buffer_btn.clicked.connect(lambda: self._clear_data_buffer())
            vision_layout.addRow("缓冲管理:", buffer_btn)
            
            vision_group.setLayout(vision_layout)
            layout.addWidget(vision_group)
            
            # Data flow status
            flow_group = QGroupBox("数据流状态")
            flow_layout = QFormLayout()
            
            # Check input connections
            input_node = self._get_connected_input_node()
            if input_node and hasattr(input_node, 'data') and input_node.data is not None:
                input_status = "有数据"
                if isinstance(input_node.data, list):
                    input_status = f"{len(input_node.data)} 张图片"
                flow_layout.addRow("输入节点:", QLabel(input_status))
                flow_layout.addRow("输入类型:", QLabel(type(input_node.data).__name__))
            else:
                flow_layout.addRow("输入节点:", QLabel("无连接"))
            
            # Check camera nodes in buffer
            if hasattr(self.canvas, 'data_buffer') and self.canvas.data_buffer:
                camera_sources = [k for k in self.canvas.data_buffer.keys() if 'camera' in k.lower()]
                if camera_sources:
                    flow_layout.addRow("相机数据源:", QLabel(", ".join(camera_sources)))
                    total_camera_images = sum(len(self.canvas.data_buffer[k]) for k in camera_sources)
                    flow_layout.addRow("相机图片数:", QLabel(str(total_camera_images)))
            
            flow_group.setLayout(flow_layout)
            layout.addWidget(flow_group)
            
            # Control buttons
            button_layout = QHBoxLayout()
            
            # Refresh buffer status button
            refresh_btn = QPushButton("刷新状态")
            refresh_btn.clicked.connect(lambda: self._refresh_and_reload_dialog(dialog))
            
            # Open vision debug dialog button
            debug_btn = QPushButton("打开视觉调试")
            debug_btn.clicked.connect(lambda: self._show_vision_debug_dialog())
            
            button_layout.addWidget(refresh_btn)
            button_layout.addWidget(debug_btn)
            
            layout.addLayout(button_layout)
            
            dialog.setLayout(layout)
            
            # Store reference for refresh functionality
            dialog.info_layout = info_layout if 'info_layout' in locals() else None
            
            dialog.exec()
            
        except Exception as e:
            debug(f"VMC Vision: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Vision: Traceback: {traceback.format_exc()}", "VMC")
    
    def _clear_data_buffer(self):
        """Clear the canvas data buffer"""
        try:
            if hasattr(self.canvas, 'data_buffer'):
                old_size = sum(len(images) for images in self.canvas.data_buffer.values())
                self.canvas.data_buffer.clear()
                debug(f"VMC Vision: Cleared data buffer (removed {old_size} images)", "VMC")
                QMessageBox.information(None, "清理完成", f"数据缓冲已清空\n移除了 {old_size} 张图片")
            else:
                QMessageBox.warning(None, "清理失败", "画布没有数据缓冲")
                
        except Exception as e:
            QMessageBox.critical(None, "清理失败", f"清空数据缓冲时出错: {e}")
    
    def _refresh_and_reload_dialog(self, dialog):
        """Refresh buffer status and reload dialog"""
        try:
            debug("VMC Vision: Refreshing buffer status", "VMC")
            
            # Update buffer status in dialog if info_layout exists
            if hasattr(dialog, 'info_layout') and hasattr(self.canvas, 'data_buffer') and self.canvas.data_buffer:
                # Remove old buffer status rows
                for i in reversed(range(dialog.info_layout.rowCount())):
                    if "缓冲状态:" in dialog.info_layout.itemAt(i, 0).text():
                        dialog.info_layout.removeRow(i)
                    elif "数据源:" in dialog.info_layout.itemAt(i, 0).text():
                        dialog.info_layout.removeRow(i)
                
                # Add updated buffer status
                total_images = sum(len(images) for images in self.canvas.data_buffer.values())
                buffer_sources = list(self.canvas.data_buffer.keys())
                dialog.info_layout.addRow("缓冲状态:", QLabel(f"{total_images} 张图片来自 {len(buffer_sources)} 个源"))
                dialog.info_layout.addRow("数据源:", QLabel(", ".join(buffer_sources)))
                
            QMessageBox.information(dialog, "刷新完成", "数据缓冲状态已更新")
            
        except Exception as e:
            QMessageBox.critical(dialog, "刷新失败", f"刷新状态时出错: {e}")

    def execute_vision_task(self, input_image):
        """Execute vision-specific task using vision_pipeline_executor"""
        try:
            import time
            start_time = time.time()

            # Use vision_pipeline_executor for processing
            from core.managers.vision_pipeline_executor import VisionPipelineExecutor
            
            # Create executor instance
            executor = VisionPipelineExecutor()
            
            # Get algorithm configuration if available
            algorithm_config = getattr(self, 'algorithm_config', {})
            
            # Execute the vision algorithm using the executor
            result = executor.execute_single_algorithm(self.algorithm, input_image, algorithm_config)

            # Update vision metrics
            self.processing_time = time.time() - start_time

            # Count detections if this is a detection algorithm
            if hasattr(result, 'detections'):
                self.detection_count = len(result.detections)
            elif hasattr(result, 'output_image') and hasattr(result.output_image, 'shape'):
                self.detection_count = 1  # Simple processing task

            debug(f"VMC Vision task completed: {self.processing_time:.3f}s, {self.detection_count} results", "VMC")
            return result

        except Exception as e:
            debug(f"VMC Vision task failed: {e}", "VMC")
            return None

    
    def set_content(self, content_text):
        """Set node content text"""
        try:
            if hasattr(self, 'content_label'):
                self.content_label.setText(content_text)
            # Also update title if available
            if hasattr(self, 'title_label'):
                self.title_label.setText(content_text)
            debug(f"VMC Vision: Set content to '{content_text}'", "VMC")
        except Exception as e:
            debug(f"VMC Vision: Failed to set content: {e}", "VMC")

    def _load_config_to_vision_dialog(self, vision_dialog, config_data):
        """Load configuration to vision dialog using existing ChainConfig mechanism"""
        try:
            from core.interfaces.algorithm.vision_config_types import ChainConfig

            # Convert config data to ChainConfig
            if isinstance(config_data, dict):
                # If it's a dict, assume it's in the format ChainConfig.from_dict expects
                chain_config = ChainConfig.from_dict(config_data)
            else:
                debug("VMC Vision: Config data is not in expected format", "VMC")
                return

            # Clear canvas first
            if hasattr(vision_dialog, 'clear_canvas_silent'):
                vision_dialog.clear_canvas_silent()
            elif hasattr(vision_dialog, 'clear_canvas'):
                vision_dialog.clear_canvas()

            # Use existing algorithm manager to load the config
            if hasattr(vision_dialog, 'algorithm_manager') and vision_dialog.algorithm_manager:
                registry = vision_dialog.algorithm_manager.get_registry()

                # Load algorithms from config (similar to load_chain_config logic)
                algorithm_nodes = []
                for algorithm_config in chain_config.algorithms:
                    try:
                        algorithm = registry.create_algorithm_instance(algorithm_config.algorithm_id)
                        if algorithm:
                            algorithm_config.apply_to_algorithm(algorithm)

                            # Determine position
                            x, y = 250, 200
                            if algorithm_config.layout and "position" in algorithm_config.layout:
                                x = float(algorithm_config.layout["position"]["x"])
                                y = float(algorithm_config.layout["position"]["y"])

                            # Add to canvas
                            node = vision_dialog.canvas.add_algorithm_node(algorithm, x, y)
                            algorithm_nodes.append(node)
                            debug(f"VMC Vision: Loaded algorithm {algorithm_config.algorithm_id}", "VMC")
                        else:
                            debug(f"VMC Vision: Failed to create algorithm {algorithm_config.algorithm_id}", "VMC")
                    except Exception as e:
                        debug(f"VMC Vision: Error loading algorithm {algorithm_config.algorithm_id}: {e}", "VMC")

                # Auto-connect input to first algorithm
                input_node = vision_dialog.canvas.nodes.get("input_image")
                if input_node and algorithm_nodes:
                    first_algorithm = algorithm_nodes[0]
                    if hasattr(vision_dialog.canvas, 'validate_connection') and \
                       vision_dialog.canvas.validate_connection(input_node, 'port', first_algorithm, 'left'):
                        from ..vision_canvas.canvas.connections import ConnectionLine
                        connection = ConnectionLine(input_node, first_algorithm, 'port', 'left')
                        vision_dialog.canvas.scene.addItem(connection)
                        vision_dialog.canvas.connections.append(connection)
                        if hasattr(vision_dialog.canvas, 'update_port_states'):
                            vision_dialog.canvas.update_port_states(input_node, first_algorithm)

                debug(f"VMC Vision: Successfully loaded {len(algorithm_nodes)} algorithms", "VMC")
            else:
                debug("VMC Vision: No algorithm manager available in vision dialog", "VMC")

        except Exception as e:
            debug(f"VMC Vision: Failed to load config to vision dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Vision: Traceback: {traceback.format_exc()}", "VMC")

    def mouseDoubleClickEvent(self, event):
        """Mouse double click event - override for vision-specific behavior"""
        if event.button() == Qt.MouseButton.LeftButton:
            debug(f"VMC Vision node double-clicked: {self.node_id}", "VMC")
            self._show_vision_debug_dialog()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _show_vision_debug_dialog(self):
        """Show vision debug dialog"""
        try:
            # Enhanced debugging: check dialog state
            debug(f"VMC Vision: Dialog check - Node ID: {self.node_id}, Dialog exists: {self.vision_dialog is not None}", "VMC")
            if self.vision_dialog is not None:
                debug(f"VMC Vision: Dialog state - Dialog ID: {self.vision_dialog_id}, isVisible: {self.vision_dialog.isVisible()}", "VMC")
            
            # Check if dialog already exists (regardless of visibility)
            if self.vision_dialog is not None:
                if self.vision_dialog.isVisible():
                    # Dialog is visible, just activate it
                    self.vision_dialog.activateWindow()
                    self.vision_dialog.raise_()
                    debug(f"VMC Vision: Activated existing visible vision dialog - Node ID: {self.node_id}, Dialog ID: {self.vision_dialog_id}", "VMC")
                else:
                    # Dialog exists but not visible, show and activate it
                    self.vision_dialog.show()
                    self.vision_dialog.activateWindow()
                    self.vision_dialog.raise_()
                    debug(f"VMC Vision: Re-showed existing hidden vision dialog - Node ID: {self.node_id}, Dialog ID: {self.vision_dialog_id}", "VMC")
                return

            # If we reach here, no existing dialog, proceed to create new one
            debug(f"VMC Vision: No existing dialog found, creating new one - Node ID: {self.node_id}", "VMC")

            from ..vision_canvas.canvas.canvas_dialog import LarminarVisionAlgorithmChainDialog
            from PyQt6.QtWidgets import QApplication

            # Define callback function for VMC node synchronization
            def vmc_node_callback(algorithm_configs):
                """Callback to update VMC node's algorithm configuration"""
                debug(f"VMC Vision: Received {len(algorithm_configs)} algorithm configs from VisionDialog", "VMC")
                # Store algorithm configurations in the vision node
                self.algorithm_configs = algorithm_configs
                debug(f"VMC Vision: Updated algorithm configs, total: {len(algorithm_configs)}", "VMC")
                
                # Save VMC configuration to cache after algorithm configuration change
                if hasattr(self.canvas, 'parent_dialog') and hasattr(self.canvas.parent_dialog, '_save_vmc_config_to_cache'):
                    try:
                        # Generate VMC configuration with updated algorithm configs
                        vmc_config = self.canvas.parent_dialog._generate_vmc_config()
                        self.canvas.parent_dialog._save_vmc_config_to_cache(vmc_config)
                        debug("VMC Vision: Successfully saved VMC configuration to cache after algorithm configuration change", "VMC")
                    except Exception as e:
                        debug(f"VMC Vision: Failed to save VMC configuration to cache: {e}", "VMC")
            
            # Create vision dialog with VMC node synchronization
            vision_dialog = LarminarVisionAlgorithmChainDialog(
                parent=None, 
                algorithm_chain=None,
                vmc_node=self,
                vmc_callback=vmc_node_callback
            )
            
            # Store dialog reference
            self.vision_dialog = vision_dialog
            self.vision_dialog_id = f"vision_dialog_{self.node_id}_{id(vision_dialog)}"
            debug(f"VMC Vision: Created new vision dialog with VMC sync - Node ID: {self.node_id}, Dialog ID: {self.vision_dialog_id}", "VMC")

            # If node has configured algorithm, apply it to the vision dialog
            if self.algorithm:
                try:
                    # Try to load the node's algorithm into the vision dialog
                    if hasattr(vision_dialog, 'load_algorithm'):
                        vision_dialog.load_algorithm(self.algorithm)
                        debug(f"VMC Vision: Loaded node algorithm {getattr(self.algorithm, '_algorithm_id', 'unknown')} into new vision dialog", "VMC")
                    elif hasattr(vision_dialog, 'canvas'):
                        # Alternative: add algorithm to canvas
                        from core import AlgorithmManager
                        from core.managers.app_config import AppConfigManager
                        log_manager = AppConfigManager().get_log_manager()
                        algorithm_manager = AlgorithmManager(log_manager)

                        # Add algorithm to vision canvas
                        vision_dialog.canvas.add_algorithm_node(self.algorithm, 100, 100)
                        debug(f"VMC Vision: Added node algorithm to new vision canvas", "VMC")
                except Exception as load_error:
                    debug(f"VMC Vision: Failed to load algorithm into new vision dialog: {load_error}", "VMC")
            else:
                debug("VMC Vision: No algorithm configured in node, opening empty new vision dialog", "VMC")

            # Set input from canvas data_buffer first (priority), then fallback to input node
            merged_input_data = []
            
            # Get data from canvas data_buffer
            if hasattr(self.canvas, 'data_buffer') and self.canvas.data_buffer:
                import numpy as np
                # Collect all images from data_buffer in order
                for key, image_list in self.canvas.data_buffer.items():
                    if image_list:  # Only add if list is not empty
                        merged_input_data.extend(image_list)
                        debug(f"VMC Vision: Retrieved {len(image_list)} image(s) from data_buffer key '{key}'", "VMC")
                
                # Remove duplicates while preserving order
                seen_ids = set()
                unique_data = []
                for img in merged_input_data:
                    # Use image id() as unique identifier
                    img_id = id(img)
                    if img_id not in seen_ids:
                        seen_ids.add(img_id)
                        unique_data.append(img)
                
                merged_input_data = unique_data
                debug(f"VMC Vision: Total merged input data: {len(merged_input_data)} unique image(s)", "VMC")
            
            # If no data in buffer, try to get from connected input node (fallback)
            if not merged_input_data:
                input_node = self._get_connected_input_node()
                if input_node and hasattr(input_node, 'data') and input_node.data is not None:
                    if isinstance(input_node.data, list):
                        merged_input_data = input_node.data
                    else:
                        merged_input_data = [input_node.data]
                    debug("VMC Vision: Fallback to connected input node data", "VMC")
            
            # Set input to vision dialog if we have data
            if merged_input_data:
                vision_dialog.set_input_image(merged_input_data)
                debug(f"VMC Vision: Set {len(merged_input_data)} image(s) to vision dialog", "VMC")
            else:
                debug("VMC Vision: No input data available from data_buffer or input node", "VMC")

            # Apply saved vision config if available
            if hasattr(self, 'vision_config') and self.vision_config:
                try:
                    # Use existing vision dialog's config loading functionality
                    self._load_config_to_vision_dialog(vision_dialog, self.vision_config)
                    debug(f"VMC Vision: Applied saved vision config with {len(self.vision_config)} items to debug dialog", "VMC")
                except Exception as config_error:
                    debug(f"VMC Vision: Failed to apply saved config: {config_error}", "VMC")

            # Override closeEvent to hide instead of close
            def dialog_close_event(event):
                debug(f"VMC Vision: Dialog close event intercepted, hiding instead of closing - Node ID: {self.node_id}, Dialog ID: {self.vision_dialog_id}", "VMC")
                event.ignore()  # Ignore the close event
                vision_dialog.hide()  # Hide the dialog instead
                debug(f"VMC Vision: Dialog hidden, reference kept for reuse - Node ID: {self.node_id}", "VMC")
            
            vision_dialog.closeEvent = dialog_close_event
            
            # Also handle finished signal as backup
            def on_dialog_closed():
                debug(f"VMC Vision: Dialog finished signal received but keeping reference for reuse - Node ID: {self.node_id}, Dialog ID: {self.vision_dialog_id}", "VMC")
                debug("VMC Vision: Vision dialog reference kept for future reuse", "VMC")
            
            vision_dialog.finished.connect(on_dialog_closed)
            
            vision_dialog.show()

            debug("VMC Vision: Vision debug dialog opened", "VMC")

        except Exception as e:
            debug(f"VMC Vision: Failed to open vision debug dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Vision: Traceback: {traceback.format_exc()}", "VMC")

    def _get_connected_input_node(self):
        """Get the connected input node"""
        if not self.canvas or not hasattr(self.canvas, 'connections'):
            return None

        # Find input node connected to this vision node
        for connection in self.canvas.connections:
            if (connection.end_item == self and
                hasattr(connection.start_item, 'node_type') and
                connection.start_item.node_type == 'input'):
                return connection.start_item

        return None

    def show_context_menu(self, event):
        """Show context menu with vision-specific options"""
        menu = QMenu()

        # Basic operations
        delete_action = menu.addAction("🗑️ 删除节点")
        delete_action.triggered.connect(lambda: self.canvas.remove_node(self))

        menu.addSeparator()

        # Parameter configuration
        config_action = menu.addAction("⚙️ 参数配置")
        config_action.triggered.connect(lambda: self.canvas.node_selected.emit(self))

        # Vision-specific options
        menu.addSeparator()
        debug_action = menu.addAction("🔍 视觉调试")
        debug_action.triggered.connect(lambda: self._show_vision_debug_dialog())

        # If combined algorithm, add recursive debug options
        if isinstance(self.algorithm, CombinedAlgorithm):
            menu.addSeparator()
            recursive_debug_action = menu.addAction("🔍 递归调试组合算法")
            recursive_debug_action.triggered.connect(lambda: self.debug_combined_algorithm())

            # View internal structure
            view_structure_action = menu.addAction("📋 查看内部结构")
            view_structure_action.triggered.connect(lambda: self.view_combined_structure())

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
        dialog.setWindowTitle(f"VMC组合算法结构 - {self.algorithm.get_info().display_name}")
        dialog.setIcon(QMessageBox.Icon.Information)

        # Build structure info
        structure_info = f"VMC组合算法: {self.algorithm.get_info().display_name}\n"
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

    def show_param_dialog(self):
        """Show vision algorithm parameter configuration dialog"""
        try:
            from .node_parameter_dialogs import VisionAlgorithmParameterDialog
            dialog = VisionAlgorithmParameterDialog(self)
            dialog.exec()
            debug(f"VMC Vision: Parameter configuration dialog finished", "VMC")
        except Exception as e:
            debug(f"VMC Vision: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Vision: Traceback: {traceback.format_exc()}", "VMC")


class VMCMotionAlgorithmNode(VMCAlgorithmNode):
    """VMC Motion Algorithm node - specialized for robot motion control"""

    def __init__(self, algorithm, x: float, y: float, node_id: str, canvas):
        super().__init__(algorithm, 'robot', x, y, node_id, canvas)

        # Motion-specific properties
        self.motion_type = getattr(algorithm, 'motion_type', 'general')
        self.position = [0.0, 0.0, 0.0]  # X, Y, Z coordinates
        self.robot_status = 'idle'  # 'idle', 'moving', 'error'
        
        # Robot hardware configuration
        self.robot_config = {}
        self.selected_hardware_id = None
        
        # Dialog management
        self.robot_dialog = None
        self.robot_dialog_id = None  # Track dialog ID for debugging

        # Update visual appearance
        self._add_motion_indicator()
        
        # Load robot configurations from hardware_config.json
        self.load_robot_config()
    
    def load_robot_config(self):
        """Load robot configuration from config file"""
        try:
            import json
            import os
            config_path = "config/hardware_config.json"
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Get robots list from config
                if 'robots' in config:
                    self.robot_config = {item['id']: item for item in config['robots']}
                    debug(f"Loaded {len(self.robot_config)} robot configs", "VMC")
                    
        except Exception as e:
            debug(f"Failed to load robot config: {e}", "VMC")
            self.robot_config = {}

    def _add_motion_indicator(self):
        """Add motion-specific visual indicator"""
        # Visual indicators removed - keeping method for compatibility
        pass

    def execute_motion_task(self, vision_result):
        """Execute motion-specific task using robot_service"""
        try:
            import time
            start_time = time.time()

            # Update robot status
            self.robot_status = 'moving'

            # Get robot service
            robot_service = self._get_robot_service()
            if not robot_service:
                raise Exception("无法获取机器人服务")

            # Execute the motion algorithm
            result = self.algorithm.process(vision_result)

            # Process vision result to robot command
            if hasattr(result, 'position'):
                target_position = result.position
            elif hasattr(vision_result, 'detections') and vision_result.detections:
                # Move to first detection
                detection = vision_result.detections[0]
                if hasattr(detection, 'center'):
                    target_position = [detection.center[0], detection.center[1], 0.0]
            else:
                target_position = [0.0, 0.0, 0.0]  # Default position

            # Execute robot movement using robot_service
            try:
                # Convert to robot service format (assuming 6-DOF robot)
                if len(target_position) == 3:
                    # Add default joint angles for 6-DOF robot
                    robot_joints = target_position + [0.0, 90.0, 0.0]  # Default J4, J5, J6
                else:
                    robot_joints = target_position[:6]  # Take first 6 values

                # Move robot using service
                move_result = robot_service.move_joints(robot_joints)
                
                if move_result.get('success', False):
                    self.position = target_position
                    debug(f"VMC Motion: Robot moved to position {target_position}", "VMC")
                else:
                    raise Exception(f"Robot movement failed: {move_result.get('error', 'Unknown error')}")
                    
            except Exception as robot_error:
                debug(f"VMC Motion: Robot movement error: {robot_error}", "VMC")
                # Continue with algorithm result even if robot movement fails

            processing_time = time.time() - start_time
            self.robot_status = 'idle'

            debug(f"VMC Motion task completed: {processing_time:.3f}s, pos={self.position}", "VMC")
            return {
                'success': True,
                'position': self.position,
                'robot_status': self.robot_status,
                'processing_time': processing_time,
                'robot_move_result': move_result if 'move_result' in locals() else None
            }

        except Exception as e:
            self.robot_status = 'error'
            debug(f"VMC Motion task failed: {e}", "VMC")
            return None

    def _get_robot_service(self, hardware_id=None):
        """获取或创建 RobotService 实例 using hardware service factory"""
        try:
            from core.services.robot_service import RobotService
            
            # Use specific hardware ID if provided, otherwise try to use configured one
            robot_id = hardware_id or getattr(self, 'selected_hardware_id', None)
            if robot_id:
                return RobotService.get_robot_service(robot_id)
            else:
                # Fallback to old method if no hardware ID is configured
                from core import RobotService as OldRobotService
                return OldRobotService()
        except Exception as e:
            debug(f"VMC Robot: 创建 RobotService 失败: {e}", "VMC")
            return None

    def mouseDoubleClickEvent(self, event):
        """Mouse double click event - override for motion-specific behavior"""
        if event.button() == Qt.MouseButton.LeftButton:
            debug(f"VMC Motion node double-clicked: {self.node_id}", "VMC")
            self._show_robot_control_dialog()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _show_robot_control_dialog(self):
        """Show robot control dialog with auto-loaded configured robot"""
        try:
            # Enhanced debugging: check dialog state
            debug(f"VMC Robot: Dialog check - Node ID: {self.node_id}, Dialog exists: {self.robot_dialog is not None}", "VMC")
            if self.robot_dialog is not None:
                debug(f"VMC Robot: Dialog state - Dialog ID: {self.robot_dialog_id}, isVisible: {self.robot_dialog.isVisible()}", "VMC")
            
            # Check if dialog already exists (regardless of visibility)
            if self.robot_dialog is not None:
                if self.robot_dialog.isVisible():
                    # Dialog is visible, just activate it
                    self.robot_dialog.activateWindow()
                    self.robot_dialog.raise_()
                    debug(f"VMC Robot: Activated existing visible robot dialog - Node ID: {self.node_id}, Dialog ID: {self.robot_dialog_id}", "VMC")
                else:
                    # Dialog exists but not visible, show and activate it
                    self.robot_dialog.show()
                    self.robot_dialog.activateWindow()
                    self.robot_dialog.raise_()
                    debug(f"VMC Robot: Re-showed existing hidden robot dialog - Node ID: {self.node_id}, Dialog ID: {self.robot_dialog_id}", "VMC")
                return

            # If we reach here, no existing dialog, proceed to create new one
            debug(f"VMC Robot: No existing dialog found, creating new one - Node ID: {self.node_id}", "VMC")

            from ui_libs.hardware_widget.robotic_arm.robot_control import RobotControlTab
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QLabel
            from core.services.robot_service import RobotService

            # If robot is configured, get the specific robot service
            robot_service = None
            if self.selected_hardware_id:
                debug(f"VMC Robot: Loading configured robot {self.selected_hardware_id}", "VMC")
                robot_service = RobotService.get_robot_service(self.selected_hardware_id)
            
            # Fallback to generic robot service if no specific robot is configured
            if not robot_service:
                robot_service = self._get_robot_service()
                if not robot_service:
                    QMessageBox.warning(None, "警告", "无法创建机器人服务")
                    return
            else:
                # If configured robot service is not connected, try to connect
                if not robot_service.is_connected():
                    debug(f"VMC Robot: Attempting to connect to configured robot {self.selected_hardware_id}", "VMC")
                    try:
                        # Get robot config from hardware config
                        robot_info = self.robot_config.get(self.selected_hardware_id, {})
                        connect_result = robot_service.connect(robot_info)
                        if connect_result.get('success', False):
                            debug(f"VMC Robot: Successfully connected to robot {self.selected_hardware_id}", "VMC")
                            # Apply robot parameters if configured
                            if hasattr(self, 'robot_params'):
                                params = self.robot_params
                                try:
                                    # Note: Robot service may have different parameter setting methods
                                    # This is a generic approach - specific implementation may vary
                                    debug(f"VMC Robot: Applied configured parameters to {self.selected_hardware_id}", "VMC")
                                except Exception as param_error:
                                    debug(f"VMC Robot: Failed to apply parameters: {param_error}", "VMC")
                        else:
                            warning(f"VMC Robot: Failed to connect to robot {self.selected_hardware_id}: {connect_result.get('error', 'Unknown error')}", "VMC")
                    except Exception as connect_error:
                        warning(f"VMC Robot: Connection error for {self.selected_hardware_id}: {connect_error}", "VMC")

            # Create dialog
            dialog = QDialog()
            dialog.setWindowTitle(f"机器人控制 - {self.selected_hardware_id or '通用机器人'}")
            dialog.setMinimumSize(800, 600)
            
            # Store dialog reference
            self.robot_dialog = dialog
            self.robot_dialog_id = f"robot_dialog_{self.node_id}_{id(dialog)}"
            debug(f"VMC Robot: Created new robot dialog - Node ID: {self.node_id}, Dialog ID: {self.robot_dialog_id}", "VMC")

            # Create layout and add RobotControlTab
            layout = QVBoxLayout()
            
            # Define callback function for VMC node synchronization
            def vmc_node_callback(robot_id: str):
                """Callback to update VMC node's selected_hardware_id"""
                debug(f"VMC Robot: Received robot_id {robot_id} from RobotControlTab", "VMC")
                self.selected_hardware_id = robot_id
                debug(f"VMC Robot: Updated selected_hardware_id to {self.selected_hardware_id}", "VMC")
                
                # Save configuration to cache after hardware ID change
                if hasattr(self.canvas, 'parent_dialog') and hasattr(self.canvas.parent_dialog, 'save_config_to_cache'):
                    self.canvas.parent_dialog.save_config_to_cache()
                    debug("VMC Robot: Triggered configuration save after hardware ID change", "VMC")
            
            robot_control_tab = RobotControlTab(robot_service, dialog, vmc_node=self, vmc_callback=vmc_node_callback)
            layout.addWidget(robot_control_tab)

            # Add info label showing configured robot if available
            if self.selected_hardware_id:
                robot_info = self.robot_config.get(self.selected_hardware_id, {})
                info_text = f"已配置机器人: {robot_info.get('name', self.selected_hardware_id)}"
                if hasattr(self, 'robot_params'):
                    params = self.robot_params
                    info_text += f" | 速度: {params.get('speed', 50.0)}mm/s | 加速度: {params.get('acceleration', 200.0)}mm/s² | 精度: {params.get('precision', 0.1)}mm"
                
                info_label = QLabel(info_text)
                info_label.setStyleSheet("background-color: #f0f0e0; padding: 8px; margin: 5px; border-radius: 4px;")
                layout.insertWidget(0, info_label)  # Insert at the top

            dialog.setLayout(layout)
            
            # Override closeEvent to hide instead of close
            def dialog_close_event(event):
                debug(f"VMC Robot: Dialog close event intercepted, hiding instead of closing - Node ID: {self.node_id}, Dialog ID: {self.robot_dialog_id}", "VMC")
                event.ignore()  # Ignore the close event
                dialog.hide()  # Hide the dialog instead
                debug(f"VMC Robot: Dialog hidden, reference kept for reuse - Node ID: {self.node_id}", "VMC")
            
            dialog.closeEvent = dialog_close_event
            
            # Also handle finished signal as backup
            def on_dialog_closed():
                debug(f"VMC Robot: Dialog finished signal received but keeping reference for reuse - Node ID: {self.node_id}, Dialog ID: {self.robot_dialog_id}", "VMC")
                debug("VMC Robot: Robot dialog reference kept for future reuse", "VMC")
            
            dialog.finished.connect(on_dialog_closed)
            
            dialog.show()  # Use show() instead of exec() to allow non-modal behavior
            debug("VMC Robot: 机器人控制对话框已打开", "VMC")

        except ImportError as e:
            import traceback
            tb_list = traceback.extract_tb(e.__traceback__)
            if tb_list:
                last_error = tb_list[-1]
                print(f"[Import Error] {e} (发生在: {last_error.filename}:{last_error.lineno})", flush=True)

        except Exception as e:
            debug(f"VMC Robot: 打开机器人控制对话框失败: {e}", "VMC")
            import traceback
            debug(f"VMC Robot: Traceback: {traceback.format_exc()}", "VMC")

    def show_param_dialog(self):
        """Show robot parameter configuration dialog with latest config"""
        try:
            debug(f"VMC Robot: Showing parameter dialog for node {self.node_id}", "VMC")
            
            # Reload robot config to get latest configuration
            self._load_robot_config()
            debug(f"VMC Robot: Reloaded robot config, available robots: {list(self.robot_config.keys()) if self.robot_config else []}", "VMC")
            
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QComboBox, QLabel, QPushButton, QMessageBox, QDoubleSpinBox, QSpinBox
            
            # Create configuration dialog
            dialog = QDialog()
            dialog.setWindowTitle(f"机械臂参数配置 - {self.node_id}")
            dialog.setMinimumSize(600, 500)
            
            layout = QVBoxLayout()
            
            # Hardware selection group
            hardware_group = QGroupBox("硬件选择")
            hardware_layout = QFormLayout()
            
            # Robot selection combo box
            robot_combo = QComboBox()
            robot_combo.addItem("未选择", None)
            
            # Populate robot options
            if self.robot_config:
                for robot_id, robot_config in self.robot_config.items():
                    display_name = f"{robot_config.get('name', robot_id)} ({robot_id})"
                    robot_combo.addItem(display_name, robot_id)
                    
                    # Select current hardware if set
                    if self.selected_hardware_id == robot_id:
                        robot_combo.setCurrentText(display_name)
            
            hardware_layout.addRow("选择机械臂:", robot_combo)
            hardware_group.setLayout(hardware_layout)
            layout.addWidget(hardware_group)
            
            # Current configuration info
            if self.selected_hardware_id and self.selected_hardware_id in self.robot_config:
                config_group = QGroupBox("当前配置")
                config_layout = QFormLayout()
                
                robot_config = self.robot_config[self.selected_hardware_id]
                
                config_layout.addRow("机械臂ID:", QLabel(robot_config.get('id', 'N/A')))
                config_layout.addRow("名称:", QLabel(robot_config.get('name', 'N/A')))
                config_layout.addRow("品牌:", QLabel(robot_config.get('brand', 'N/A')))
                config_layout.addRow("型号:", QLabel(robot_config.get('model', 'N/A')))
                config_layout.addRow("连接类型:", QLabel(robot_config.get('connection_type', 'N/A')))
                
                config_group.setLayout(config_layout)
                layout.addWidget(config_group)
            
            # Motion parameters group
            motion_group = QGroupBox("运动参数")
            motion_layout = QFormLayout()
            
            # Position controls
            position_group = QGroupBox("当前位置")
            position_layout = QFormLayout()
            
            self.x_spinbox = QDoubleSpinBox()
            self.x_spinbox.setRange(-9999, 9999)
            self.x_spinbox.setDecimals(2)
            self.x_spinbox.setSuffix(" mm")
            self.x_spinbox.setValue(self.position[0])
            
            self.y_spinbox = QDoubleSpinBox()
            self.y_spinbox.setRange(-9999, 9999)
            self.y_spinbox.setDecimals(2)
            self.y_spinbox.setSuffix(" mm")
            self.y_spinbox.setValue(self.position[1])
            
            self.z_spinbox = QDoubleSpinBox()
            self.z_spinbox.setRange(-9999, 9999)
            self.z_spinbox.setDecimals(2)
            self.z_spinbox.setSuffix(" mm")
            self.z_spinbox.setValue(self.position[2])
            
            position_layout.addRow("X:", self.x_spinbox)
            position_layout.addRow("Y:", self.y_spinbox)
            position_layout.addRow("Z:", self.z_spinbox)
            position_group.setLayout(position_layout)
            
            motion_layout.addRow(position_group)
            
            # Motion controls
            self.speed_spinbox = QDoubleSpinBox()
            self.speed_spinbox.setRange(0.1, 1000)
            self.speed_spinbox.setDecimals(1)
            self.speed_spinbox.setSuffix(" mm/s")
            self.speed_spinbox.setValue(getattr(self, 'motion_speed', 50.0))
            
            self.accel_spinbox = QDoubleSpinBox()
            self.accel_spinbox.setRange(0.1, 2000)
            self.accel_spinbox.setDecimals(1)
            self.accel_spinbox.setSuffix(" mm/s²")
            self.accel_spinbox.setValue(getattr(self, 'motion_acceleration', 200.0))
            
            self.precision_spinbox = QDoubleSpinBox()
            self.precision_spinbox.setRange(0.01, 10)
            self.precision_spinbox.setDecimals(2)
            self.precision_spinbox.setSuffix(" mm")
            self.precision_spinbox.setValue(getattr(self, 'motion_precision', 0.1))
            
            motion_layout.addRow("速度:", self.speed_spinbox)
            motion_layout.addRow("加速度:", self.accel_spinbox)
            motion_layout.addRow("精度:", self.precision_spinbox)
            
            motion_group.setLayout(motion_layout)
            layout.addWidget(motion_group)
            
            # Connection status
            status_group = QGroupBox("连接状态")
            status_layout = QFormLayout()
            
            if self.selected_hardware_id:
                from core.services.robot_service import RobotService
                robot_service = RobotService.get_robot_service(self.selected_hardware_id)
                if robot_service:
                    is_connected = robot_service.is_connected()
                    status_color = "green" if is_connected else "red"
                    status_text = "已连接" if is_connected else "未连接"
                    status_label = QLabel(f'<span style="color: {status_color}; font-weight: bold;">{status_text}</span>')
                    status_layout.addRow("机械臂状态:", status_label)
                    
                    # Robot status
                    status_layout.addRow("运行状态:", QLabel(self.robot_status.capitalize()))
                else:
                    status_layout.addRow("机械臂服务:", QLabel("未获取到"))
            else:
                status_layout.addRow("机械臂状态:", QLabel("未选择"))
            
            status_group.setLayout(status_layout)
            layout.addWidget(status_group)
            
            # Buttons
            button_layout = QHBoxLayout()
            
            # Test connection button
            test_btn = QPushButton("测试连接")
            test_btn.clicked.connect(lambda: self._test_robot_connection())
            
            # Refresh config button  
            refresh_btn = QPushButton("刷新配置")
            refresh_btn.clicked.connect(lambda: self._refresh_and_reload_dialog(dialog))
            
            # Move to position button
            move_btn = QPushButton("移动到位置")
            move_btn.clicked.connect(lambda: self._move_to_position())
            
            button_layout.addWidget(test_btn)
            button_layout.addWidget(refresh_btn)
            button_layout.addWidget(move_btn)
            
            layout.addLayout(button_layout)
            
            dialog.setLayout(layout)
            
            # Store reference for refresh functionality
            dialog.robot_combo = robot_combo
            
            # Handle dialog result
            def on_dialog_finished(result):
                if result == QDialog.DialogCode.Accepted:
                    # Update selected hardware if changed
                    selected_robot_id = robot_combo.currentData()
                    if selected_robot_id and selected_robot_id != self.selected_hardware_id:
                        old_id = self.selected_hardware_id
                        self.selected_hardware_id = selected_robot_id
                        debug(f"VMC Robot: Updated selected hardware from {old_id} to {selected_robot_id}", "VMC")
                        
                        # Save configuration to cache after hardware ID change
                        if hasattr(self.canvas, 'parent_dialog') and hasattr(self.canvas.parent_dialog, 'save_config_to_cache'):
                            self.canvas.parent_dialog.save_config_to_cache()
                            debug("VMC Robot: Triggered configuration save after parameter configuration change", "VMC")
                        
                        # Load robot config for new selection
                        self._load_robot_config()
                    
                    # Update motion parameters
                    self.position = [self.x_spinbox.value(), self.y_spinbox.value(), self.z_spinbox.value()]
                    self.motion_speed = self.speed_spinbox.value()
                    self.motion_acceleration = self.accel_spinbox.value()
                    self.motion_precision = self.precision_spinbox.value()
                    
                    debug(f"VMC Robot: Updated motion parameters - position: {self.position}, speed: {self.motion_speed}", "VMC")
            
            dialog.finished.connect(on_dialog_finished)
            dialog.exec()
            
        except Exception as e:
            debug(f"VMC Robot: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Robot: Traceback: {traceback.format_exc()}", "VMC")
    
    def _load_robot_config(self):
        """Load robot configuration from config file"""
        try:
            import json
            config_path = "config/hardware_config.json"
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Get robot configuration
                robots_config = config.get('robots', [])
                self.robot_config = {item['id']: item for item in robots_config}
                debug(f"Loaded {len(self.robot_config)} robot configs", "VMC")
                    
        except Exception as e:
            debug(f"VMC Robot: Failed to load robot config: {e}", "VMC")
            self.robot_config = {}
    
    def _test_robot_connection(self):
        """Test connection for selected robot"""
        try:
            if not self.selected_hardware_id:
                QMessageBox.warning(None, "测试连接", "请先选择一个机械臂")
                return
                
            from core.services.robot_service import RobotService
            robot_service = RobotService.get_robot_service(self.selected_hardware_id)
            if not robot_service:
                QMessageBox.critical(None, "测试连接", "无法获取机械臂服务")
                return
                
            # Test connection
            result = robot_service.test_connection()
            if result.get('success', False):
                QMessageBox.information(None, "测试连接", f"机械臂连接成功!\n{result.get('message', '')}")
            else:
                QMessageBox.warning(None, "测试连接", f"机械臂连接失败!\n{result.get('error', '未知错误')}")
                
        except Exception as e:
            QMessageBox.critical(None, "测试连接", f"测试连接时出错: {e}")
    
    def _refresh_and_reload_dialog(self, dialog):
        """Refresh hardware config and reload dialog"""
        try:
            debug("VMC Robot: Refreshing hardware configuration", "VMC")
            
            # Reload config
            old_selection = self.selected_hardware_id
            self._load_robot_config()
            
            # Update combo box
            if hasattr(dialog, 'robot_combo'):
                dialog.robot_combo.clear()
                dialog.robot_combo.addItem("未选择", None)
                
                if self.robot_config:
                    for robot_id, robot_config in self.robot_config.items():
                        display_name = f"{robot_config.get('name', robot_id)} ({robot_id})"
                        dialog.robot_combo.addItem(display_name, robot_id)
                        
                        # Restore selection
                        if self.selected_hardware_id == robot_id:
                            dialog.robot_combo.setCurrentText(display_name)
            
            QMessageBox.information(dialog, "刷新完成", f"硬件配置已刷新\n发现 {len(self.robot_config) if self.robot_config else 0} 个机械臂配置")
            
        except Exception as e:
            QMessageBox.critical(dialog, "刷新失败", f"刷新配置时出错: {e}")
    
    def _move_to_position(self):
        """Move robot to configured position"""
        try:
            if not self.selected_hardware_id:
                QMessageBox.warning(None, "移动位置", "请先选择一个机械臂")
                return
                
            from core.services.robot_service import RobotService
            robot_service = RobotService.get_robot_service(self.selected_hardware_id)
            if not robot_service:
                QMessageBox.critical(None, "移动位置", "无法获取机械臂服务")
                return
                
            if not robot_service.is_connected():
                QMessageBox.warning(None, "移动位置", "机械臂未连接")
                return
            
            # Get target position
            target_pos = [self.x_spinbox.value(), self.y_spinbox.value(), self.z_spinbox.value()]
            
            # Move to position
            result = robot_service.move_to_position(target_pos)
            if result.get('success', False):
                QMessageBox.information(None, "移动完成", f"机械臂已移动到位置: {target_pos}")
                self.robot_status = 'idle'
            else:
                QMessageBox.warning(None, "移动失败", f"机械臂移动失败: {result.get('error', '未知错误')}")
                self.robot_status = 'error'
                
        except Exception as e:
            QMessageBox.critical(None, "移动位置", f"移动时出错: {e}")


class VMCHardwareNode(VMCNodeBase):
    """VMC Hardware node base class"""

    def __init__(self, hardware_type: str, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__('hardware', x, y, node_id, canvas, title or f"{hardware_type}硬件节点")

        # Hardware-specific properties
        self.hardware_type = hardware_type
        self.service = None
        self.is_connected = False

        # Hardware configuration
        self.hardware_config = {}
        self.selected_hardware_id = None

        # Add hardware-specific indicator
        self._add_hardware_indicator()

    def _add_hardware_indicator(self):
        """Add hardware-specific visual indicator"""
        # Visual indicators removed - keeping method for compatibility
        pass

    def add_param_button_if_needed(self):
        """Hardware nodes need parameter button for hardware selection"""
        self.add_param_button()

    def load_hardware_config(self):
        """Load hardware configuration from config file"""
        try:
            import json
            config_path = "config/hardware_config.json"
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Get relevant hardware list based on hardware_type
                hardware_key = f"{self.hardware_type}s"  # cameras, robots, lights
                if hardware_key in config:
                    self.hardware_config = {item['id']: item for item in config[hardware_key]}
                    debug(f"Loaded {len(self.hardware_config)} {self.hardware_type} configs", "VMC")
                    
        except Exception as e:
            debug(f"Failed to load hardware config: {e}", "VMC")
            self.hardware_config = {}


class VMCCameraNode(VMCHardwareNode):
    """VMC Camera hardware node"""

    def __init__(self, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__('camera', x, y, node_id, canvas, title or "相机节点")

        # Camera-specific properties
        self.camera_service = None
        self.camera_index = 0
        self.is_capturing = False
        
        # Data capture properties
        self.auto_trigger_config = None
        self.captured_images = []  # Store captured images for this camera
        
        # Dialog management
        self.camera_dialog = None
        self.camera_dialog_id = None  # Track dialog ID for debugging
        
        # Load camera configurations from hardware_config.json
        self.load_hardware_config()

    def load_hardware_config(self):
        """Load camera configuration including auto trigger settings"""
        # Call parent method first
        super().load_hardware_config()
        
        # Load auto trigger configuration for selected camera
        if self.selected_hardware_id and self.selected_hardware_id in self.hardware_config:
            camera_config = self.hardware_config[self.selected_hardware_id]
            self.auto_trigger_config = camera_config.get('auto_trigger', {})
            if self.auto_trigger_config and self.auto_trigger_config.get('enabled', False):
                debug(f"VMC Camera: Loaded auto trigger config for {self.selected_hardware_id}: {self.auto_trigger_config}", "VMC")
            else:
                self.auto_trigger_config = None
        else:
            self.auto_trigger_config = None

    def _get_camera_service(self):
        """Create CameraService instance"""
        try:
            from core import CameraService
            return CameraService()
        except Exception as e:
            debug(f"VMC Camera: 创建 CameraService 失败: {e}", "VMC")
            return None

    def show_param_dialog(self):
        """Show camera parameter configuration dialog with latest config"""
        try:
            debug(f"VMC Camera: Showing parameter dialog for node {self.node_id}", "VMC")
            
            # Reload hardware config to get latest configuration
            self.load_hardware_config()
            debug(f"VMC Camera: Reloaded hardware config, available cameras: {list(self.hardware_config.keys()) if self.hardware_config else []}", "VMC")
            
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QComboBox, QLabel, QPushButton, QMessageBox
            
            # Create configuration dialog
            dialog = QDialog()
            dialog.setWindowTitle(f"相机参数配置 - {self.node_id}")
            dialog.setMinimumSize(500, 400)
            
            layout = QVBoxLayout()
            
            # Hardware selection group
            hardware_group = QGroupBox("硬件选择")
            hardware_layout = QFormLayout()
            
            # Camera selection combo box
            camera_combo = QComboBox()
            camera_combo.addItem("未选择", None)
            
            # Populate camera options
            if self.hardware_config:
                for camera_id, camera_config in self.hardware_config.items():
                    display_name = f"{camera_config.get('name', camera_id)} ({camera_id})"
                    camera_combo.addItem(display_name, camera_id)
                    
                    # Select current hardware if set
                    if self.selected_hardware_id == camera_id:
                        camera_combo.setCurrentText(display_name)
            
            hardware_layout.addRow("选择相机:", camera_combo)
            hardware_group.setLayout(hardware_layout)
            layout.addWidget(hardware_group)
            
            # Current configuration info
            if self.selected_hardware_id and self.selected_hardware_id in self.hardware_config:
                config_group = QGroupBox("当前配置")
                config_layout = QFormLayout()
                
                camera_config = self.hardware_config[self.selected_hardware_id]
                
                config_layout.addRow("相机ID:", QLabel(camera_config.get('id', 'N/A')))
                config_layout.addRow("名称:", QLabel(camera_config.get('name', 'N/A')))
                config_layout.addRow("品牌:", QLabel(camera_config.get('brand', 'N/A')))
                config_layout.addRow("型号:", QLabel(camera_config.get('model', 'N/A')))
                config_layout.addRow("连接类型:", QLabel(camera_config.get('connection_type', 'N/A')))
                config_layout.addRow("分辨率:", QLabel(camera_config.get('resolution', 'N/A')))
                config_layout.addRow("帧率:", QLabel(f"{camera_config.get('fps', 'N/A')} fps"))
                
                # Auto trigger configuration
                auto_trigger = camera_config.get('auto_trigger', {})
                if auto_trigger and auto_trigger.get('enabled', False):
                    trigger_layout = QVBoxLayout()
                    trigger_layout.addWidget(QLabel("自动触发: 启用"))
                    trigger_layout.addWidget(QLabel(f"触发模式: {auto_trigger.get('trigger_mode', 'N/A')}"))
                    trigger_layout.addWidget(QLabel(f"触发次数: {auto_trigger.get('trigger_count', 'N/A')}"))
                    trigger_layout.addWidget(QLabel(f"触发间隔: {auto_trigger.get('trigger_interval', 'N/A')}ms"))
                    config_layout.addRow("自动触发配置:", trigger_layout)
                else:
                    config_layout.addRow("自动触发:", QLabel("未启用"))
                
                config_group.setLayout(config_layout)
                layout.addWidget(config_group)
            
            # Connection status
            status_group = QGroupBox("连接状态")
            status_layout = QFormLayout()
            
            if self.selected_hardware_id:
                from core.services.camera_service import CameraService
                camera_service = CameraService.get_camera_service(self.selected_hardware_id)
                if camera_service:
                    is_connected = camera_service.is_connected()
                    status_color = "green" if is_connected else "red"
                    status_text = "已连接" if is_connected else "未连接"
                    status_label = QLabel(f'<span style="color: {status_color}; font-weight: bold;">{status_text}</span>')
                    status_layout.addRow("相机状态:", status_label)
                else:
                    status_layout.addRow("相机服务:", QLabel("未获取到"))
            else:
                status_layout.addRow("相机状态:", QLabel("未选择"))
            
            status_group.setLayout(status_layout)
            layout.addWidget(status_group)
            
            # Buttons
            button_layout = QHBoxLayout()
            
            # Test connection button
            test_btn = QPushButton("测试连接")
            test_btn.clicked.connect(lambda: self._test_camera_connection())
            
            # Refresh config button  
            refresh_btn = QPushButton("刷新配置")
            refresh_btn.clicked.connect(lambda: self._refresh_and_reload_dialog(dialog))
            
            button_layout.addWidget(test_btn)
            button_layout.addWidget(refresh_btn)
            
            layout.addLayout(button_layout)
            
            dialog.setLayout(layout)
            
            # Store reference for refresh functionality
            dialog.camera_combo = camera_combo
            
            # Handle dialog result
            def on_dialog_finished(result):
                if result == QDialog.DialogCode.Accepted:
                    # Update selected hardware if changed
                    selected_camera_id = camera_combo.currentData()
                    if selected_camera_id and selected_camera_id != self.selected_hardware_id:
                        old_id = self.selected_hardware_id
                        self.selected_hardware_id = selected_camera_id
                        debug(f"VMC Camera: Updated selected hardware from {old_id} to {selected_camera_id}", "VMC")
                        
                        # Save configuration to cache after hardware ID change
                        if hasattr(self.canvas, 'parent_dialog') and hasattr(self.canvas.parent_dialog, 'save_config_to_cache'):
                            self.canvas.parent_dialog.save_config_to_cache()
                            debug("VMC Camera: Triggered configuration save after parameter configuration change", "VMC")
                        
                        # Load auto trigger config for new selection
                        self.load_hardware_config()
            
            dialog.finished.connect(on_dialog_finished)
            dialog.exec()
            
        except Exception as e:
            debug(f"VMC Camera: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Camera: Traceback: {traceback.format_exc()}", "VMC")
    
    def _test_camera_connection(self):
        """Test connection for selected camera"""
        try:
            if not self.selected_hardware_id:
                QMessageBox.warning(None, "测试连接", "请先选择一个相机")
                return
                
            from core.services.camera_service import CameraService
            camera_service = CameraService.get_camera_service(self.selected_hardware_id)
            if not camera_service:
                QMessageBox.critical(None, "测试连接", "无法获取相机服务")
                return
                
            # Test connection
            result = camera_service.test_connection()
            if result.get('success', False):
                QMessageBox.information(None, "测试连接", f"相机连接成功!\n{result.get('message', '')}")
            else:
                QMessageBox.warning(None, "测试连接", f"相机连接失败!\n{result.get('error', '未知错误')}")
                
        except Exception as e:
            QMessageBox.critical(None, "测试连接", f"测试连接时出错: {e}")
    
    def _refresh_and_reload_dialog(self, dialog):
        """Refresh hardware config and reload dialog"""
        try:
            debug("VMC Camera: Refreshing hardware configuration", "VMC")
            
            # Reload config
            old_selection = self.selected_hardware_id
            self.load_hardware_config()
            
            # Update combo box
            if hasattr(dialog, 'camera_combo'):
                dialog.camera_combo.clear()
                dialog.camera_combo.addItem("未选择", None)
                
                if self.hardware_config:
                    for camera_id, camera_config in self.hardware_config.items():
                        display_name = f"{camera_config.get('name', camera_id)} ({camera_id})"
                        dialog.camera_combo.addItem(display_name, camera_id)
                        
                        # Restore selection
                        if self.selected_hardware_id == camera_id:
                            dialog.camera_combo.setCurrentText(display_name)
            
            QMessageBox.information(dialog, "刷新完成", f"硬件配置已刷新\n发现 {len(self.hardware_config) if self.hardware_config else 0} 个相机配置")
            
        except Exception as e:
            QMessageBox.critical(dialog, "刷新失败", f"刷新配置时出错: {e}")

    def mouseDoubleClickEvent(self, event):
        """Mouse double click event - override for camera-specific behavior"""
        if event.button() == Qt.MouseButton.LeftButton:
            debug(f"VMC Camera node double-clicked: {self.node_id}", "VMC")
            self._show_camera_manager_dialog()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _show_camera_manager_dialog(self):
        """Show camera manager dialog with auto-loaded configured camera"""
        try:
            # Enhanced debugging: check dialog state
            debug(f"VMC Camera: Dialog check - Node ID: {self.node_id}, Dialog exists: {self.camera_dialog is not None}", "VMC")
            if self.camera_dialog is not None:
                debug(f"VMC Camera: Dialog state - Dialog ID: {self.camera_dialog_id}, isVisible: {self.camera_dialog.isVisible()}", "VMC")
            
            # Check if dialog already exists (regardless of visibility)
            if self.camera_dialog is not None:
                if self.camera_dialog.isVisible():
                    # Dialog is visible, just activate it
                    self.camera_dialog.activateWindow()
                    self.camera_dialog.raise_()
                    debug(f"VMC Camera: Activated existing visible camera dialog - Node ID: {self.node_id}, Dialog ID: {self.camera_dialog_id}", "VMC")
                else:
                    # Dialog exists but not visible, show and activate it
                    self.camera_dialog.show()
                    self.camera_dialog.activateWindow()
                    self.camera_dialog.raise_()
                    debug(f"VMC Camera: Re-showed existing hidden camera dialog - Node ID: {self.node_id}, Dialog ID: {self.camera_dialog_id}", "VMC")
                return

            # If we reach here, no existing dialog, proceed to create new one
            debug(f"VMC Camera: No existing dialog found, creating new one - Node ID: {self.node_id}", "VMC")

            from ui_libs.hardware_widget.camera.camera_control import CameraControlTab
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QMessageBox, QLabel
            from core.services.camera_service import CameraService

            # If camera is configured, get the specific camera service
            camera_service = None
            if self.selected_hardware_id:
                debug(f"VMC Camera: Loading configured camera {self.selected_hardware_id}", "VMC")
                camera_service = CameraService.get_camera_service(self.selected_hardware_id)
            
            # Fallback to generic camera service if no specific camera is configured
            if not camera_service:
                camera_service = self._get_camera_service()
                if not camera_service:
                    QMessageBox.warning(None, "警告", "无法创建相机服务")
                    return
            else:
                # If configured camera service is not connected, try to connect
                if not camera_service.is_connected():
                    debug(f"VMC Camera: Attempting to connect to configured camera {self.selected_hardware_id}", "VMC")
                    try:
                        # Get camera config from hardware config
                        camera_info = self.hardware_config.get(self.selected_hardware_id, {})
                        connect_result = camera_service.connect(camera_info)
                        if connect_result.get('success', False):
                            debug(f"VMC Camera: Successfully connected to camera {self.selected_hardware_id}", "VMC")
                            # Apply camera parameters if configured
                            if hasattr(self, 'camera_params'):
                                params = self.camera_params
                                try:
                                    camera_service.set_exposure(params.get('exposure', 10.0))
                                    camera_service.set_gain(params.get('gain', 1.0))
                                    debug(f"VMC Camera: Applied configured parameters to {self.selected_hardware_id}", "VMC")
                                except Exception as param_error:
                                    debug(f"VMC Camera: Failed to apply parameters: {param_error}", "VMC")
                        else:
                            warning(f"VMC Camera: Failed to connect to camera {self.selected_hardware_id}: {connect_result.get('error', 'Unknown error')}", "VMC")
                    except Exception as connect_error:
                        warning(f"VMC Camera: Connection error for {self.selected_hardware_id}: {connect_error}", "VMC")

            # Create dialog
            dialog = QDialog()
            dialog.setWindowTitle(f"相机管理 - {self.selected_hardware_id or '通用相机'}")
            dialog.setMinimumSize(800, 600)
            
            # Store dialog reference
            self.camera_dialog = dialog
            self.camera_dialog_id = f"camera_dialog_{self.node_id}_{id(dialog)}"
            debug(f"VMC Camera: Created new camera dialog - Node ID: {self.node_id}, Dialog ID: {self.camera_dialog_id}", "VMC")

            # Create layout and add CameraControlTab
            layout = QVBoxLayout()
            
            # Define callback function for VMC node synchronization
            def vmc_node_callback(camera_id: str):
                """Callback to update VMC node's selected_hardware_id"""
                debug(f"VMC Camera: Received camera_id {camera_id} from CameraControlTab", "VMC")
                self.selected_hardware_id = camera_id
                debug(f"VMC Camera: Updated selected_hardware_id to {self.selected_hardware_id}", "VMC")
                
                # Save configuration to cache after hardware ID change
                if hasattr(self.canvas, 'parent_dialog') and hasattr(self.canvas.parent_dialog, 'save_config_to_cache'):
                    self.canvas.parent_dialog.save_config_to_cache()
                    debug("VMC Camera: Triggered configuration save after hardware ID change", "VMC")
            
            camera_control_tab = CameraControlTab(camera_service, dialog, vmc_node=self, vmc_callback=vmc_node_callback)

            # Auto-add configured camera to the list
            if self.selected_hardware_id:
                camera_info = self.hardware_config.get(self.selected_hardware_id, {})
                if camera_info:
                    # Import CameraInfo from the camera module
                    import sys
                    import os
                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))
                    from ui_libs.hardware_widget.camera.camera_info import CameraInfo
                    
                    camera_obj = CameraInfo(self.selected_hardware_id, camera_info)
                    camera_obj.name = camera_info.get('name', self.selected_hardware_id)
                    camera_obj.camera_type = camera_info.get('brand', 'unknown')
                    camera_obj.resolution = camera_info.get('resolution', '1920x1080')
                    camera_obj.config = camera_info.copy()
                    
                    # Check if camera already exists in the list
                    camera_exists = any(
                        cam.camera_id == self.selected_hardware_id or cam.name == camera_obj.name 
                        for cam in camera_control_tab.camera_list
                    )
                    
                    if not camera_exists:
                        camera_control_tab.camera_list.append(camera_obj)
                        camera_control_tab.update_camera_table()
                        debug(f"VMC Camera: Auto-added configured camera {self.selected_hardware_id} to camera list", "VMC")

            layout.addWidget(camera_control_tab)

            # Add info label showing configured camera if available
            if self.selected_hardware_id:
                camera_info = self.hardware_config.get(self.selected_hardware_id, {})
                info_text = f"已配置相机: {camera_info.get('name', self.selected_hardware_id)}"
                if hasattr(self, 'camera_params'):
                    params = self.camera_params
                    info_text += f" | 曝光: {params.get('exposure', 10.0)}ms | 增益: {params.get('gain', 1.0)} | 帧率: {params.get('fps', 30)}"
                
                info_label = QLabel(info_text)
                info_label.setStyleSheet("background-color: #e0f0ff; padding: 8px; margin: 5px; border-radius: 4px;")
                layout.insertWidget(0, info_label)  # Insert at the top

            dialog.setLayout(layout)
            
            # Override closeEvent to hide instead of close
            def dialog_close_event(event):
                debug(f"VMC Camera: Dialog close event intercepted, hiding instead of closing - Node ID: {self.node_id}, Dialog ID: {self.camera_dialog_id}", "VMC")
                event.ignore()  # Ignore the close event
                dialog.hide()  # Hide the dialog instead
                debug(f"VMC Camera: Dialog hidden, reference kept for reuse - Node ID: {self.node_id}", "VMC")
            
            dialog.closeEvent = dialog_close_event
            
            # Also handle finished signal as backup
            def on_dialog_closed():
                debug(f"VMC Camera: Dialog finished signal received but keeping reference for reuse - Node ID: {self.node_id}, Dialog ID: {self.camera_dialog_id}", "VMC")
                debug("VMC Camera: Camera dialog reference kept for future reuse", "VMC")
            
            dialog.finished.connect(on_dialog_closed)
            
            dialog.show()  # Use show() instead of exec() to allow non-modal behavior
            debug("VMC Camera: 相机管理对话框已打开", "VMC")

        except Exception as e:
            debug(f"VMC Camera: 打开对话框失败: {e}", "VMC")
            import traceback
            debug(f"VMC Camera: Traceback: {traceback.format_exc()}", "VMC")

    def capture_and_store_image(self):
        """Capture image and store to canvas data buffer with trigger support"""
        try:
            if not self.selected_hardware_id:
                debug("VMC Camera: No camera configured for capture", "VMC")
                return False
                
            # Get camera service
            from core.services.camera_service import CameraService
            camera_service = CameraService.get_camera_service(self.selected_hardware_id)
            if not camera_service:
                debug(f"VMC Camera: Failed to get camera service for {self.selected_hardware_id}", "VMC")
                return False
                
            if not camera_service.is_connected():
                debug(f"VMC Camera: Camera {self.selected_hardware_id} not connected, attempting to connect", "VMC")
                
                # Get camera configuration and try to connect
                camera_config = self._get_hardware_config_for_camera()
                if not camera_config:
                    debug(f"VMC Camera: No config found for {self.selected_hardware_id}", "VMC")
                    return False
                
                connect_result = camera_service.connect(camera_config)
                if not connect_result.get('success', False):
                    debug(f"VMC Camera: Failed to connect camera {self.selected_hardware_id}: {connect_result.get('error', 'Unknown error')}", "VMC")
                    return False
                    
                debug(f"VMC Camera: Successfully connected camera {self.selected_hardware_id}", "VMC")
                
            debug(f"VMC Camera: Starting capture process for {self.selected_hardware_id}", "VMC")
            
            # Check and execute auto-trigger based on configuration
            self._execute_auto_trigger_if_needed(camera_service)
            
            debug(f"VMC Camera: Capturing image from {self.selected_hardware_id}", "VMC")
            
            # Capture single frame after trigger
            image = camera_service.capture_frame()
            if image is None:
                debug("VMC Camera: Failed to capture image", "VMC")
                return False
                
            debug(f"VMC Camera: Captured image shape: {image.shape}", "VMC")
            
            # Store to canvas data buffer
            if hasattr(self.canvas, 'data_buffer'):
                self.canvas.data_buffer.setdefault(self.selected_hardware_id, []).append(image)
                debug(f"VMC Camera: Stored image to data buffer, key: {self.selected_hardware_id}, buffer size: {len(self.canvas.data_buffer[self.selected_hardware_id])}", "VMC")
                
                # Also store in node's captured images list
                self.captured_images.append(image)
                debug(f"VMC Camera: Local capture count: {len(self.captured_images)}", "VMC")
                
                # Update node appearance to show data captured
                self.setBrush(QBrush(QColor(180, 230, 255)))  # Lighter blue to show data
                
                return True
            else:
                debug("VMC Camera: Canvas has no data buffer", "VMC")
                return False
                
        except Exception as e:
            debug(f"VMC Camera: Capture and store failed: {e}", "VMC")
            import traceback
            debug(f"VMC Camera: Traceback: {traceback.format_exc()}", "VMC")
            return False
    
    def _execute_auto_trigger_if_needed(self, camera_service):
        """Execute auto-trigger based on hardware configuration"""
        try:
            # Get hardware configuration for this camera
            hardware_config = self._get_hardware_config_for_camera()
            if not hardware_config:
                debug("VMC Camera: No hardware config found for trigger check", "VMC")
                return
                
            # Check auto_trigger configuration
            auto_trigger = hardware_config.get('auto_trigger', {})
            if not auto_trigger.get('enabled', False):
                debug("VMC Camera: Auto-trigger not enabled in configuration", "VMC")
                return
                
            trigger_mode = auto_trigger.get('trigger_mode', 'software_trigger')
            trigger_count = auto_trigger.get('trigger_count', 1)
            trigger_interval = auto_trigger.get('trigger_interval', 1000)
            
            debug(f"VMC Camera: Executing auto-trigger - mode: {trigger_mode}, count: {trigger_count}, interval: {trigger_interval}ms", "VMC")
            
            # Execute trigger based on mode
            if trigger_mode == 'software_trigger':
                # Execute software trigger multiple times if configured
                for i in range(trigger_count):
                    debug(f"VMC Camera: Executing software trigger {i+1}/{trigger_count}", "VMC")
                    
                    # Call software trigger
                    trigger_result = camera_service.trigger_software()
                    if trigger_result and trigger_result.get('success', False):
                        debug(f"VMC Camera: Software trigger {i+1} successful", "VMC")
                    else:
                        debug(f"VMC Camera: Software trigger {i+1} failed: {trigger_result.get('error', 'Unknown error') if trigger_result else 'No result'}", "VMC")
                    
                    # Wait between triggers (except after the last one)
                    if i < trigger_count - 1 and trigger_interval > 0:
                        import time
                        debug(f"VMC Camera: Waiting {trigger_interval}ms before next trigger", "VMC")
                        time.sleep(trigger_interval / 1000.0)
                        
            else:
                debug(f"VMC Camera: Trigger mode '{trigger_mode}' not supported yet", "VMC")
                
        except Exception as e:
            debug(f"VMC Camera: Auto-trigger execution failed: {e}", "VMC")
            import traceback
            debug(f"VMC Camera: Traceback: {traceback.format_exc()}", "VMC")
    
    def _get_hardware_config_for_camera(self):
        """Get hardware configuration for the selected camera"""
        try:
            import json
            import os
            
            config_path = "config/hardware_config.json"
            if not os.path.exists(config_path):
                debug("VMC Camera: Hardware config file not found", "VMC")
                return None
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Find camera configuration
            cameras = config.get('cameras', [])
            for camera_config in cameras:
                if camera_config.get('id') == self.selected_hardware_id:
                    debug(f"VMC Camera: Found hardware config for {self.selected_hardware_id}", "VMC")
                    return camera_config
                    
            debug(f"VMC Camera: Camera {self.selected_hardware_id} not found in hardware config", "VMC")
            return None
            
        except Exception as e:
            debug(f"VMC Camera: Failed to get hardware config: {e}", "VMC")
            return None

    def auto_trigger_capture(self):
        """Auto-trigger camera capture based on configuration"""
        try:
            if not self.auto_trigger_config or not self.auto_trigger_config.get('enabled', False):
                debug("VMC Camera: Auto trigger not enabled", "VMC")
                return
                
            trigger_count = self.auto_trigger_config.get('trigger_count', 1)
            trigger_interval = self.auto_trigger_config.get('trigger_interval', 1000)
            
            debug(f"VMC Camera: Auto-triggering {trigger_count} captures with {trigger_interval}ms interval", "VMC")
            
            import time
            success_count = 0
            
            for i in range(trigger_count):
                if self.capture_and_store_image():
                    success_count += 1
                    debug(f"VMC Camera: Auto-trigger capture {i+1}/{trigger_count} successful", "VMC")
                else:
                    debug(f"VMC Camera: Auto-trigger capture {i+1}/{trigger_count} failed", "VMC")
                
                # Add interval between captures
                if i < trigger_count - 1 and trigger_interval > 0:
                    time.sleep(trigger_interval / 1000.0)
                    
            debug(f"VMC Camera: Auto-trigger completed: {success_count}/{trigger_count} successful", "VMC")
            return success_count > 0
            
        except Exception as e:
            debug(f"VMC Camera: Auto-trigger failed: {e}", "VMC")
            return False

    def get_capture_status(self):
        """Get current capture status"""
        return {
            'camera_id': self.selected_hardware_id,
            'auto_trigger_enabled': self.auto_trigger_config and self.auto_trigger_config.get('enabled', False),
            'captured_count': len(self.captured_images),
            'buffer_count': len(self.canvas.data_buffer.get(self.selected_hardware_id, [])) if hasattr(self.canvas, 'data_buffer') else 0
        }

    def show_param_dialog(self):
        """Show camera parameter configuration dialog"""
        try:
            from .node_parameter_dialogs import CameraParameterDialog
            dialog = CameraParameterDialog(self)
            dialog.exec()
            debug(f"VMC Camera: Parameter configuration dialog finished", "VMC")
        except Exception as e:
            debug(f"VMC Camera: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Camera: Traceback: {traceback.format_exc()}", "VMC")


class VMCLightNode(VMCHardwareNode):
    """VMC Light hardware node"""

    def __init__(self, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__('light', x, y, node_id, canvas, title or "光源节点")

        # Light-specific properties
        self.light_service = None
        self.is_on = False
        
        # Dialog management
        self.light_dialog = None
        self.light_dialog_id = None  # Track dialog ID for debugging

    def _get_light_service(self):
        """Create LightService instance"""
        try:
            from core import LightService
            return LightService()
        except Exception as e:
            debug(f"VMC Light: 创建 LightService 失败: {e}", "VMC")
            return None

    def mouseDoubleClickEvent(self, event):
        """Mouse double click event - override for light-specific behavior"""
        if event.button() == Qt.MouseButton.LeftButton:
            debug(f"VMC Light node double-clicked: {self.node_id}", "VMC")
            self._show_light_manager_dialog()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _show_light_manager_dialog(self):
        """Show light manager dialog"""
        try:
            # Enhanced debugging: check dialog state
            debug(f"VMC Light: Dialog check - Node ID: {self.node_id}, Dialog exists: {self.light_dialog is not None}", "VMC")
            if self.light_dialog is not None:
                debug(f"VMC Light: Dialog state - Dialog ID: {self.light_dialog_id}, isVisible: {self.light_dialog.isVisible()}", "VMC")
            
            # Check if dialog already exists (regardless of visibility)
            if self.light_dialog is not None:
                if self.light_dialog.isVisible():
                    # Dialog is visible, just activate it
                    self.light_dialog.activateWindow()
                    self.light_dialog.raise_()
                    debug(f"VMC Light: Activated existing visible light dialog - Node ID: {self.node_id}, Dialog ID: {self.light_dialog_id}", "VMC")
                else:
                    # Dialog exists but not visible, show and activate it
                    self.light_dialog.show()
                    self.light_dialog.activateWindow()
                    self.light_dialog.raise_()
                    debug(f"VMC Light: Re-showed existing hidden light dialog - Node ID: {self.node_id}, Dialog ID: {self.light_dialog_id}", "VMC")
                return

            # If we reach here, no existing dialog, proceed to create new one
            debug(f"VMC Light: No existing dialog found, creating new one - Node ID: {self.node_id}", "VMC")

            from ui_libs.hardware_widget.light.light_control import LightControlTab
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QMessageBox

            # get light service
            light_service = self._get_light_service()
            if not light_service:
                QMessageBox.warning(None, "警告", "无法创建光源服务")
                return

            # Create simplified dialog
            dialog = QDialog()
            dialog.setWindowTitle("光源管理 - VMC节点控制")
            dialog.setMinimumSize(800, 600)
            
            # Store dialog reference
            self.light_dialog = dialog
            self.light_dialog_id = f"light_dialog_{self.node_id}_{id(dialog)}"
            debug(f"VMC Light: Created new light dialog - Node ID: {self.node_id}, Dialog ID: {self.light_dialog_id}", "VMC")

            # Create layout and add LightControlTab
            layout = QVBoxLayout()
            light_control_tab = LightControlTab(light_service, dialog)
            layout.addWidget(light_control_tab)

            dialog.setLayout(layout)
            
            # Override closeEvent to hide instead of close
            def dialog_close_event(event):
                debug(f"VMC Light: Dialog close event intercepted, hiding instead of closing - Node ID: {self.node_id}, Dialog ID: {self.light_dialog_id}", "VMC")
                event.ignore()  # Ignore the close event
                dialog.hide()  # Hide the dialog instead
                debug(f"VMC Light: Dialog hidden, reference kept for reuse - Node ID: {self.node_id}", "VMC")
            
            dialog.closeEvent = dialog_close_event
            
            # Also handle finished signal as backup
            def on_dialog_closed():
                debug(f"VMC Light: Dialog finished signal received but keeping reference for reuse - Node ID: {self.node_id}, Dialog ID: {self.light_dialog_id}", "VMC")
                debug("VMC Light: Light dialog reference kept for future reuse", "VMC")
            
            dialog.finished.connect(on_dialog_closed)
            
            dialog.show()  # Use show() instead of exec() to allow non-modal behavior
            debug("VMC Light: 光源管理对话框已打开", "VMC")

        except Exception as e:
            debug(f"VMC Light: 打开对话框失败: {e}", "VMC")
            import traceback
            debug(f"VMC Light: Traceback: {traceback.format_exc()}", "VMC")

    def show_param_dialog(self):
        """Show light parameter configuration dialog"""
        try:
            debug(f"VMC Light: Showing parameter dialog for node {self.node_id}", "VMC")
            from .node_parameter_dialogs import QMessageBox
            reply = QMessageBox.question(None, "光源节点",
                                       "光源节点需要更多配置选项吗？\n\n点击 '是' 打开光源管理界面\n点击 '否' 使用基本设置",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._show_light_manager_dialog()
        except Exception as e:
            debug(f"VMC Light: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Light: Traceback: {traceback.format_exc()}", "VMC")


class VMCControlNode(VMCNodeBase):
    """VMC Control node base class"""

    def __init__(self, control_type: str, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__(control_type, x, y, node_id, canvas, title or f"{control_type}控制节点")

        # Control-specific properties
        self.control_type = control_type
        self.control_mode = 'automatic'  # 'automatic', 'manual', 'supervised'
        self.system_status = 'active'   # 'active', 'paused', 'stopped', 'error'

        # Add control-specific indicator
        self._add_control_indicator()

    def _add_control_indicator(self):
        """Add control-specific visual indicator"""
        # Visual indicators removed - keeping method for compatibility
        pass


class VMCExecutorNode(VMCControlNode):
    """VMC Executor node - coordinates vision and motion operations"""

    def __init__(self, algorithm, x: float, y: float, node_id: str, canvas, title: str=None):
        super().__init__('executor', x, y, node_id, canvas, title or "执行器节点")

        # Executor-specific properties
        self.execution_mode = 'auto'  # 'auto', 'manual', 'step'
        self.step_count = 0
        self.pipeline_state = 'ready'  # 'ready', 'running', 'paused', 'completed', 'error'

        # Connected vision and motion nodes
        self.vision_node = None
        self.motion_node = None

        # Update visual appearance
        self._update_executor_appearance()

    def _update_executor_appearance(self):
        """Update appearance specific to executor node"""
        # Update title to show execution state
        if hasattr(self, 'title_item'):
            state_suffix = f" [{self.pipeline_state.upper()}]" if self.pipeline_state != 'ready' else ""
            mode_suffix = f" ({self.execution_mode})" if self.execution_mode != 'auto' else ""
            self.title_item.setPlainText(self.get_display_title() + state_suffix + mode_suffix)

    def execute_pipeline(self, input_data):
        """Execute the complete vision-motion pipeline"""
        try:
            import time
            start_time = time.time()

            self.pipeline_state = 'running'
            self._update_executor_appearance()

            # Step 1: Execute vision processing
            if self.vision_node:
                debug("VMC Pipeline: Step 1 - Vision processing", "VMC")
                vision_result = self.vision_node.execute_vision_task(input_data.get('image'))
                if not vision_result:
                    raise Exception("Vision processing failed")
            else:
                debug("VMC Pipeline: No vision node connected", "VMC")
                vision_result = None

            # Step 2: Execute motion command
            if self.motion_node and vision_result:
                debug("VMC Pipeline: Step 2 - Motion execution", "VMC")
                motion_result = self.motion_node.execute_motion_task(vision_result)
                if not motion_result:
                    raise Exception("Motion execution failed")
            else:
                debug("VMC Pipeline: No motion node connected or no vision result", "VMC")
                motion_result = None

            # Update counters and state
            self.step_count += 1
            self.pipeline_state = 'completed'
            self._update_executor_appearance()

            total_time = time.time() - start_time

            debug(f"VMC Pipeline completed: {total_time:.3f}s, {self.step_count} steps", "VMC")

            return {
                'success': True,
                'vision_result': vision_result,
                'motion_result': motion_result,
                'total_time': total_time,
                'step_count': self.step_count,
                'pipeline_state': self.pipeline_state
            }

        except Exception as e:
            self.pipeline_state = 'error'
            self._update_executor_appearance()
            debug(f"VMC Pipeline execution failed: {e}", "VMC")
            return {
                'success': False,
                'error': str(e),
                'pipeline_state': self.pipeline_state
            }

    def reset_pipeline(self):
        """Reset pipeline state"""
        self.step_count = 0
        self.pipeline_state = 'ready'
        self._update_executor_appearance()
        debug("VMC Pipeline reset to ready state", "VMC")

    def show_param_dialog(self):
        """Show executor parameter configuration dialog"""
        try:
            debug(f"VMC Executor: Showing parameter dialog for node {self.node_id}", "VMC")
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QGroupBox, QFormLayout, QComboBox, QLabel, QPushButton, QMessageBox
            from .node_parameter_dialogs import QMessageBox

            # Create configuration dialog
            dialog = QDialog()
            dialog.setWindowTitle(f"执行器配置 - {self.node_id}")
            dialog.setMinimumSize(400, 300)

            layout = QVBoxLayout()

            # Execution mode group
            mode_group = QGroupBox("执行模式")
            mode_layout = QFormLayout()

            mode_combo = QComboBox()
            mode_combo.addItems(["自动执行", "单步调试", "手动控制"])
            mode_combo.setCurrentText("自动执行" if self.execution_mode == 'auto' else "单步调试" if self.execution_mode == 'step' else "手动控制")
            mode_layout.addRow("执行模式:", mode_combo)

            mode_group.setLayout(mode_layout)
            layout.addWidget(mode_group)

            # Pipeline state info
            state_group = QGroupBox("当前状态")
            state_layout = QFormLayout()

            state_label = QLabel(f"{self.pipeline_state}")
            step_label = QLabel(f"{self.step_count}")

            state_layout.addRow("管道状态:", state_label)
            state_layout.addRow("执行步数:", step_label)

            state_group.setLayout(state_layout)
            layout.addWidget(state_group)

            # Control buttons
            button_layout = QVBoxLayout()

            reset_btn = QPushButton("重置管道")
            reset_btn.clicked.connect(self.reset_pipeline)
            button_layout.addWidget(reset_btn)

            layout.addLayout(button_layout)

            # OK/Cancel buttons
            ok_btn = QPushButton("确定")
            cancel_btn = QPushButton("取消")

            def save_config():
                mode_text = mode_combo.currentText()
                self.execution_mode = 'auto' if mode_text == '自动执行' else 'step' if mode_text == '单步调试' else 'manual'
                self._update_executor_appearance()
                dialog.accept()

            ok_btn.clicked.connect(save_config)
            cancel_btn.clicked.connect(dialog.reject())

            layout.addWidget(ok_btn)
            layout.addWidget(cancel_btn)

            dialog.setLayout(layout)
            dialog.exec()

        except Exception as e:
            debug(f"VMC Executor: Failed to show parameter dialog: {e}", "VMC")
            import traceback
            debug(f"VMC Executor: Traceback: {traceback.format_exc()}", "VMC")


# === Compatibility Classes for VisionRobotDialog ===

class NodeType(Enum):
    """Node type enumeration for compatibility"""
    INPUT = "input"
    OUTPUT = "output"
    VISION = "vision"
    MOTION = "robot"
    EXECUTOR = "executor"
    CAMERA = "camera"
    LIGHT = "light"
    HARDWARE = "hardware"
    CONTROL = "control"


class NodeState(Enum):
    """Node state enumeration for compatibility"""
    IDLE = "idle"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


