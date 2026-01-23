"""
Algorithm Canvas Component

This module provides the main canvas component for visual algorithm chain
editing with drag-and-drop, connection management, and interactive features.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsLineItem,
                             QMenu, QMessageBox)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal, QMimeData, QTimer, QLineF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter

import numpy as np

from core.managers.log_manager import debug
from .nodes import AlgorithmNode, ImageNode
from .connections import ConnectionLine
from .image_dialog import ImageDisplayDialog


class AlgorithmCanvas(QGraphicsView):
    """Algorithm canvas"""
    
    algorithm_dropped = pyqtSignal(str, float, float)  # Algorithm drag signal
    node_selected = pyqtSignal(object)  # Node selection signal
    connection_created = pyqtSignal(object, object)  # Connection creation signal
    execution_requested = pyqtSignal()  # Execution request signal
    connection_hover = pyqtSignal(object, str)  # Connection hover signal
    
    def __init__(self, parent_dialog=None):
        super().__init__()
        self.parent_dialog = parent_dialog  # Reference parent dialog for recursive debugging
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Enable drag acceptance
        self.setAcceptDrops(True)
        
        # Canvas settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        # Node and connection management
        self.nodes: Dict[str, object] = {}
        self.connections: List[ConnectionLine] = []
        
        # Connection state
        self.connecting_from = None
        self.temp_connection_line = None
        self.hovered_port = None
        self.hover_hint = None
        
        # Status bar update function
        self.status_update_callback = None
        
        # Global debounce save timer
        self._global_save_timer = None
        
        # Set background
        self.setBackgroundBrush(QBrush(QColor(245, 245, 245)))
        
        # Grid
        self.draw_grid()
        
    def draw_grid(self):
        """Draw grid"""
        grid_size = 20
        pen = QPen(QColor(220, 220, 220), 1)
        
        # Draw vertical lines
        for x in range(0, 2000, grid_size):
            self.scene.addLine(x, 0, x, 2000, pen)
            
        # Draw horizontal lines
        for y in range(0, 2000, grid_size):
            self.scene.addLine(0, y, 2000, y, pen)
    
    def add_algorithm_node(self, algorithm, x: float, y: float) -> AlgorithmNode:
        """Add algorithm node"""
        node_id = f"algorithm_{len(self.nodes)}"
        node = AlgorithmNode(algorithm, x, y, node_id, self)
        
        # Initialize node configuration
        from core.interfaces.algorithm.vision_config_types import AlgorithmConfig
        node.config = AlgorithmConfig.from_algorithm_base(algorithm)
        
        self.scene.addItem(node)
        self.nodes[node_id] = node
        
        # Initialize port colors based on current connection status
        if hasattr(node, 'update_port_colors_realtime'):
            node.update_port_colors_realtime()
        
        return node
    
    def debounce_save_config(self, delay_ms=500):
        """Debounce save configuration"""
        if (hasattr(self, 'parent_dialog') and 
            self.parent_dialog and 
            hasattr(self.parent_dialog, 'save_config_to_cache')):
            
            # Cancel previous save timer
            if self._global_save_timer:
                self._global_save_timer.stop()
            
            # Create new save timer
            self._global_save_timer = QTimer()
            self._global_save_timer.setSingleShot(True)
            self._global_save_timer.timeout.connect(self.parent_dialog.save_config_to_cache)
            self._global_save_timer.start(delay_ms)
    
    def add_image_node(self, node_type: str, x: float, y: float) -> ImageNode:
        """Add image node"""
        node_id = f"{node_type}_image"
        node = ImageNode(node_type, x, y, node_id, self)
        
        self.scene.addItem(node)
        self.nodes[node_id] = node
        
        # Initialize port colors based on current connection status
        if hasattr(node, 'update_port_colors_realtime'):
            node.update_port_colors_realtime()
        
        return node
    
    def add_connection(self, start_item, end_item):
        """Add connection"""
        from .connections import ConnectionLine
        connection = ConnectionLine(start_item, end_item)
        self.scene.addItem(connection)
        self.connections.append(connection)
        
        # Update all port colors based on actual connection status
        self.update_all_node_port_colors()
        
        # Save configuration to cache
        if (hasattr(self, 'parent_dialog') and 
            self.parent_dialog and 
            hasattr(self.parent_dialog, 'save_config_to_cache')):
            self.parent_dialog.save_config_to_cache()
        
    def add_node(self, node):
        """Add existing node to canvas"""
        if hasattr(node, 'node_id'):
            self.scene.addItem(node)
            self.nodes[node.node_id] = node
    
    def mousePressEvent(self, event):
        """Mouse press event"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on a port
            scene_pos = self.mapToScene(event.position().toPoint())
            clicked_port = self.get_port_at_position(scene_pos)
            
            if clicked_port:
                # Start connection
                self.start_connection(clicked_port)
                return
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Mouse move event"""
        if self.connecting_from and self.temp_connection_line:
            # Update temporary connection line
            scene_pos = self.mapToScene(event.position().toPoint())
            start_pos = self.connecting_from[2]  # Use stored position coordinates
            self.temp_connection_line.setLine(QLineF(start_pos, scene_pos))
            
            # Check hover target
            self.check_hover_target(scene_pos)
        else:
            # Clear hover hint
            self.clear_hover_hint()
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Mouse release event"""
        if self.connecting_from:
            # Prefer hovered port (supports auto-connection)
            target_port = self.hovered_port
            
            # If no hovered port, try to get port at current position
            if not target_port:
                scene_pos = self.mapToScene(event.position().toPoint())
                target_port = self.get_port_at_position(scene_pos)
            
            if target_port and target_port != self.connecting_from:
                # Complete connection
                self.complete_connection(self.connecting_from, target_port)
            else:
                # Cancel connection
                self.cancel_connection()
        else:
            # Handle connection selection (only for left button)
            scene_pos = self.mapToScene(event.position().toPoint())
            items = self.scene.items(scene_pos)
            
            found_connection = False
            for item in items:
                if hasattr(item, 'get_connection_info'):  # Check if it's a connection line
                    # Let the connection handle the mouse event directly
                    if hasattr(item, 'handle_canvas_mouse_event'):
                        if item.handle_canvas_mouse_event(event):
                            found_connection = True
                            break
            
            # If no connection was clicked, deselect all connections
            if not found_connection:
                self.deselect_all_connections()
        
        super().mouseReleaseEvent(event)
    
    def get_port_at_position(self, pos: QPointF) -> tuple:
        """Get port at specified position"""
        for node_id, node in self.nodes.items():
            if isinstance(node, AlgorithmNode):
                # Check all pins
                for port_name, port_item in node.ports.items():
                    port_rect = port_item.sceneBoundingRect()
                    if port_rect.contains(pos):
                        return (node, port_name, node.get_port_pos(port_name))
            
            elif isinstance(node, ImageNode):
                # Check image node port
                port_rect = node.port.sceneBoundingRect()
                if port_rect.contains(pos):
                    return (node, 'port', node.get_port_pos())
        
        return None
    
    def start_connection(self, from_port: tuple):
        """Start connection"""
        self.connecting_from = from_port
        node, port_type, pos = from_port
        
        # Create temporary connection line
        self.temp_connection_line = QGraphicsLineItem(QLineF(pos, pos))
        self.temp_connection_line.setPen(QPen(QColor(255, 165, 0), 2, Qt.PenStyle.DashLine))
        self.scene.addItem(self.temp_connection_line)
    
    def complete_connection(self, from_port: tuple, to_port: tuple):
        """Complete connection"""
        from_node, from_type, from_pos = from_port
        to_node, to_type, to_pos = to_port
        
        # Validate connection
        is_valid = self.validate_connection(from_node, from_type, to_node, to_type)
        
        if is_valid:
            # Create connection, pass port information
            connection = ConnectionLine(from_node, to_node, from_type, to_type)
            self.scene.addItem(connection)
            self.connections.append(connection)
            
            # Use debounce save configuration to cache
            self.debounce_save_config(200)  # Connection operations use shorter delay
            
            # Update all port colors based on actual connection status
            debug(f"创建连接后开始更新所有节点端口颜色", "CHAIN")
            self.update_all_node_port_colors()
            
            # Update status bar
            if self.status_update_callback:
                from_name = from_node.algorithm.get_info().display_name if hasattr(from_node, 'algorithm') else from_node.node_type
                to_name = to_node.algorithm.get_info().display_name if hasattr(to_node, 'algorithm') else to_node.node_type
                self.status_update_callback(f"连接已创建: {from_name} → {to_name}")
        else:
            if self.status_update_callback:
                self.status_update_callback("连接无效: 无法建立此连接")
        
        self.cancel_connection()
    
    def validate_connection(self, from_node, from_type, to_node, to_type) -> bool:
        """Validate if connection is valid"""
        # Cannot connect to self
        if from_node == to_node:
            return False
        
        # Algorithm node connections - only allow right output to left input
        if isinstance(from_node, AlgorithmNode) and isinstance(to_node, AlgorithmNode):
            return from_type == 'right' and to_type == 'left'
        
        # Image node to algorithm node
        if isinstance(from_node, ImageNode) and isinstance(to_node, AlgorithmNode):
            return from_node.node_type == "input" and to_type == 'left'
        
        # Algorithm node to image node
        if isinstance(from_node, AlgorithmNode) and isinstance(to_node, ImageNode):
            return from_type == 'right' and to_node.node_type == "output"
        
        return False
    
    def update_port_states(self, from_node, to_node):
        """Update port states"""
        if isinstance(from_node, AlgorithmNode):
            from_node.output_connected = True
            from_node.update_port_colors()
        elif isinstance(from_node, ImageNode):
            from_node.connected = True
            from_node.update_port_color()
        
        if isinstance(to_node, AlgorithmNode):
            to_node.input_connected = True
            to_node.update_port_colors()
        elif isinstance(to_node, ImageNode):
            to_node.connected = True
            to_node.update_port_color()
    
    def cancel_connection(self):
        """Cancel connection"""
        if self.temp_connection_line:
            self.scene.removeItem(self.temp_connection_line)
            self.temp_connection_line = None
        self.connecting_from = None
        self.clear_hover_hint()
    
    def check_hover_target(self, scene_pos):
        """Check hover target and show hint"""
        target_port = self.get_port_at_position(scene_pos)
        
        if target_port and target_port != self.connecting_from:
            # Validate if can connect
            if self.validate_connection(
                target_port[0], target_port[1], 
                self.connecting_from[0], self.connecting_from[1]
            ):
                self.show_hover_hint(target_port)
                self.hovered_port = target_port
            else:
                self.clear_hover_hint()
                self.hovered_port = None
        else:
            self.clear_hover_hint()
            self.hovered_port = None
    
    def show_hover_hint(self, target_port):
        """Show connection hint"""
        if self.hover_hint:
            # If there's already a hint, remove it first
            self.scene.removeItem(self.hover_hint)
        
        node, port_type, pos = target_port
        
        # Create highlight circle
        hint = QGraphicsEllipseItem(-12, -12, 24, 24)
        hint.setPos(pos)
        hint.setBrush(QBrush(QColor(0, 255, 0, 100)))
        hint.setPen(QPen(QColor(0, 255, 0), 3))
        hint.setZValue(10)
        
        self.scene.addItem(hint)
        self.hover_hint = hint
        
        # Update status bar hint
        if self.status_update_callback:
            target_name = node.algorithm.get_info().display_name if hasattr(node, 'algorithm') else node.node_type
            self.status_update_callback(f"松开鼠标连接到: {target_name}")
    
    def clear_hover_hint(self):
        """Clear connection hint"""
        if self.hover_hint:
            self.scene.removeItem(self.hover_hint)
            self.hover_hint = None
        
        if self.hovered_port:
            self.hovered_port = None
        
        if self.status_update_callback and self.connecting_from:
            self.status_update_callback("拖动到目标端口以创建连接")
    
    def show_algorithm_result(self, algorithm_node):
        """Show algorithm result - unified result viewing interface"""
        if not algorithm_node.execution_result:
            return
            
        # Use parent_dialog if available, otherwise use parent
        parent = getattr(self, 'parent_dialog', None) or self.parent()
        from ..dialogs.intermediate_result_dialog import IntermediateResultDialog
        dialog = IntermediateResultDialog(algorithm_node, parent)
        dialog.exec()
    
    def on_node_double_clicked(self, node):
        """Node double-click event"""
        if hasattr(self, 'parent_dialog') and hasattr(self.parent_dialog, 'on_node_double_clicked'):
            # Delegate to parent dialog
            self.parent_dialog.on_node_double_clicked(node)
        elif isinstance(node, ImageNode):
            # Show image
            if node.image_data is not None:
                self.show_fullscreen_image(node.image_data, node.node_type + "图像")
                if self.status_update_callback:
                    self.status_update_callback(f"Viewing {node.node_type} image")
            else:
                if self.status_update_callback:
                    self.status_update_callback("This node has no image data")
    
    def deselect_all_connections(self):
        """Deselect all connection lines"""
        try:
            for connection in self.connections:
                if hasattr(connection, 'setSelected'):
                    connection.setSelected(False)
            debug(f"已取消选中所有连线", "CHAIN")
        except Exception as e:
            debug(f"取消选中连线时出错: {str(e)}", "CHAIN")

    def show_fullscreen_image(self, image: np.ndarray, title: str):
        """Show fullscreen image - supports zoom"""
        dialog = ImageDisplayDialog(image, title, self)
        dialog.exec()
    
    def show_image_info_in_params_for_node(self, image_node):
        """Show image node information in parameter area"""
        if image_node.image_data is None:
            return
        
        height, width = image_node.image_data.shape[:2]
        channels = image_node.image_data.shape[2] if len(image_node.image_data.shape) == 3 else 1
        
        # Format image information
        if channels == 1:
            channel_info = "Grayscale image"
        elif channels == 3:
            channel_info = "Color image (BGR)"
        elif channels == 4:
            channel_info = "Color image (BGRA)"
        else:
            channel_info = f"{channels} channel image"
        
        info_text = f"""Image node information
Node type: {image_node.node_type}
Image size: {width} × {height} pixels
Channel count: {channel_info}
Data type: {image_node.image_data.dtype}
Memory usage: {image_node.image_data.nbytes / 1024:.1f} KB

Operation tips:
• Single-click to view image information
• Double-click to open image viewer
• Drag port to connect algorithms"""
        
        # Try to display in parameter area
        try:
            # Clear parameter configuration area
            if hasattr(self, 'parameter_widget'):
                try:
                    self.parameter_widget.clear_parameters()
                except:
                    pass
                
                # Create information display label
                info_label = QLabel(info_text)
                info_label.setStyleSheet("""
                    QLabel {
                        background-color: #f8f9fa;
                        border: 1px solid #dee2e6;
                        border-radius: 6px;
                        padding: 10px;
                        font-family: 'Consolas', 'Monaco', monospace;
                        font-size: 12px;
                        color: #495057;
                    }
                """)
                info_label.setAlignment(Qt.AlignmentFlag.AlignTop)
                info_label.setWordWrap(True)
                
                # Create information group
                info_group = QGroupBox("Image Node Information")
                info_layout = QVBoxLayout(info_group)
                info_layout.addWidget(info_label)
                
                # Add information group to parameter area's content layout
                try:
                    self.parameter_widget.content_layout.addWidget(info_group)
                except:
                    pass
            
        except Exception:
            # If cannot display in parameter area, at least show basic info in status bar
            if self.status_update_callback:
                self.status_update_callback(f"Image: {width}×{height}, {channel_info}")
    
    def dragEnterEvent(self, event):
        """Drag enter event"""
        if event.mimeData().hasFormat("application/x-algorithm-id"):
            event.acceptProposedAction()
    
    def dragMoveEvent(self, event):
        """Drag move event"""
        if event.mimeData().hasFormat("application/x-algorithm-id"):
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """Drag drop event"""
        if event.mimeData().hasFormat("application/x-algorithm-id"):
            algorithm_id = event.mimeData().data("application/x-algorithm-id").data().decode()
            
            # Convert to scene coordinates
            scene_pos = self.mapToScene(event.position().toPoint())
            
            self.algorithm_dropped.emit(algorithm_id, scene_pos.x(), scene_pos.y())
            event.acceptProposedAction()
    
    def keyPressEvent(self, event):
        """Key press event"""
        if event.key() == Qt.Key.Key_Delete:
            # Delete selected nodes
            selected_items = self.scene.selectedItems()
            for item in selected_items:
                if isinstance(item, (AlgorithmNode, ImageNode)):
                    self.remove_node(item)
        elif event.key() == Qt.Key.Key_F5:
            # Execute algorithm chain
            self.execution_requested.emit()
        elif event.key() == Qt.Key.Key_Escape:
            # Cancel current connection operation
            if hasattr(self, 'temp_connection_line') and self.temp_connection_line:
                self.scene.removeItem(self.temp_connection_line)
                self.temp_connection_line = None
                self.connection_start_node = None
                self.connection_start_port = None
        else:
            super().keyPressEvent(event)
    
    def remove_node(self, node):
        """Remove node"""
        # Remove related connections
        connections_to_remove = []
        for connection in self.connections:
            if connection.start_item == node or connection.end_item == node:
                connections_to_remove.append(connection)
        
        for connection in connections_to_remove:
            self.scene.removeItem(connection)
            self.connections.remove(connection)
        
        # Remove node
        self.scene.removeItem(node)
        
        # Remove from node dictionary
        node_id_to_remove = None
        for node_id, n in self.nodes.items():
            if n == node:
                node_id_to_remove = node_id
                break
        
        if node_id_to_remove:
            del self.nodes[node_id_to_remove]
        
        # Use debounce save configuration to cache
        self.debounce_save_config(100)  # Delete operation saves immediately
    
    def contextMenuEvent(self, event):
        """Canvas context menu"""
        menu = QMenu()
        
        # Basic operations
        clear_action = menu.addAction("🗑️ 清空画布")
        clear_action.triggered.connect(lambda: self.parent_dialog.clear_canvas() if self.parent_dialog else None)
        
        menu.addSeparator()
        
        # Save and load
        save_action = menu.addAction("💾 保存配置")
        save_action.triggered.connect(lambda: self.parent_dialog.save_chain_config() if self.parent_dialog else None)
        
        load_action = menu.addAction("📂 加载配置")
        load_action.triggered.connect(lambda: self.parent_dialog.load_chain_config() if self.parent_dialog else None)
        
        menu.addSeparator()
        
        # Save as combined algorithm
        save_combined_action = menu.addAction("🔗 保存为组合算法")
        save_combined_action.triggered.connect(lambda: self.parent_dialog.save_as_combined_algorithm() if self.parent_dialog else None)
        
        # If there's an algorithm chain, can execute
        execution_order = self.parent_dialog.build_execution_order() if self.parent_dialog else []
        if execution_order:
            menu.addSeparator()
            execute_action = menu.addAction("▶️ 执行算法链")
            execute_action.triggered.connect(lambda: self.execution_requested.emit())
        
        # Show menu
        menu.exec(event.globalPos())
    
    def clear_canvas(self):
        """Clear canvas content"""
        self.scene.clear()
        self.nodes.clear()
        self.connections.clear()
    
    def is_port_connected(self, node, port_direction):
        """Check if a specific port is actually connected in real-time"""
        if not hasattr(self, 'connections') or not self.connections:
            # debug(f"节点 {getattr(node, 'node_id', 'unknown')} 端口 {port_direction} 无连接: 连接列表为空", "CHAIN")
            return False
        
        node_id = getattr(node, 'node_id', 'unknown')
        node_type = getattr(node, 'node_type', 'unknown')
        # debug(f"检查节点 {node_id} ({node_type}) 端口 {port_direction} 连接状态，总连接数: {len(self.connections)}", "CHAIN")
        
        # Check all connections to see if any connect to this node's port
        for i, connection in enumerate(self.connections):
            if hasattr(connection, 'start_item') and hasattr(connection, 'end_item'):
                # Check if node is connected via its right (output) port
                if connection.start_item == node and port_direction == 'right':
                    debug(f"找到连接 {i}: 节点 {node_id} 作为起始节点，输出端口 (right) 连接", "CHAIN")
                    return True
                # Check if node is connected via its left (input) port  
                elif connection.end_item == node and port_direction == 'left':
                    debug(f"找到连接 {i}: 节点 {node_id} 作为结束节点，输入端口 (left) 连接", "CHAIN")
                    return True
        
        # debug(f"节点 {node_id} 端口 {port_direction} 无连接", "CHAIN")
        return False
    
    def update_all_node_port_colors(self):
        """Update port colors for all nodes based on actual connection status"""
        debug(f"开始更新所有节点的端口颜色，节点数量: {len(self.nodes)}", "CHAIN")
        
        for node in self.nodes.values():
            node_id = getattr(node, 'node_id', 'unknown')
            node_type = type(node).__name__
            debug(f"处理节点 {node_id}，类型: {node_type}", "CHAIN")
            
            # Check if node has the realtime update method
            if hasattr(node, 'update_port_colors_realtime'):
                debug(f"节点 {node_id} 有 update_port_colors_realtime 方法，准备调用", "CHAIN")
                
                # Check if node has canvas reference
                if hasattr(node, 'canvas'):
                    debug(f"节点 {node_id} 有 canvas 引用", "CHAIN")
                else:
                    debug(f"节点 {node_id} 没有 canvas 引用！", "CHAIN")
                    continue
                    
                # Check if node has ports (for AlgorithmNode) or port (for ImageNode)
                if hasattr(node, 'ports'):
                    debug(f"节点 {node_id} 有 ports 属性", "CHAIN")
                elif hasattr(node, 'port'):
                    debug(f"节点 {node_id} 有 port 属性", "CHAIN")
                else:
                    debug(f"节点 {node_id} 没有 ports 或 port 属性！", "CHAIN")
                    continue
                
                debug(f"调用节点 {node_id} 的实时颜色更新", "CHAIN")
                node.update_port_colors_realtime()
            else:
                debug(f"节点 {node_id} 没有 update_port_colors_realtime 方法", "CHAIN")
                
                # Fallback: try to call old method or force update
                if hasattr(node, 'update_port_colors'):
                    debug(f"节点 {node_id} 使用旧的 update_port_colors 方法", "CHAIN")
                    node.update_port_colors()
                elif hasattr(node, 'update_port_color'):
                    debug(f"节点 {node_id} 使用旧的 update_port_color 方法", "CHAIN")
                    node.update_port_color()
                    
        # Force scene update
        if hasattr(self, 'scene'):
            self.scene.update()
            debug(f"强制更新场景", "CHAIN")