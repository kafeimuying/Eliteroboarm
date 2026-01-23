"""
VR Canvas Connection Components

This module provides visual connection line components for connecting
nodes on the vision-robot algorithm canvas.
Based on ui/canvas/connections.py with VR prefix.
"""

from PyQt6.QtWidgets import QGraphicsPathItem, QMenu
from PyQt6.QtCore import Qt, QPointF, QLineF, QTimer
from PyQt6.QtGui import QPen, QColor, QPainterPath
from .nodes import VMCInputNode
from core.managers.log_manager import debug


class VRConnectionLine(QGraphicsPathItem):
    """VR Orthogonal dashed connection line"""

    def __init__(self, start_item, end_item, start_port=None, end_port=None):
        super().__init__()
        self.start_item = start_item
        self.end_item = end_item
        self.start_port = start_port  # Store start port name
        self.end_port = end_port      # Store end port name
        self.setZValue(0.5)  # 确保连线在背景上但在节点下方

        # Selection state
        self.is_selected = False

        # Set pen - dashed style
        self.default_pen = QPen(QColor(100, 100, 100), 2)
        self.default_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.default_pen.setStyle(Qt.PenStyle.DashLine)
        self.default_pen.setDashPattern([5, 5])  # Dash pattern: 5 pixels line, 5 pixels gap

        # Selected pen - solid style with different color
        self.selected_pen = QPen(QColor(0, 120, 255), 3)  # Blue color
        self.selected_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        self.setPen(self.default_pen)

        # Make connection selectable and accept hover events
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsFocusable, True)

        # Start timer to update connection line position
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_position)
        self.update_timer.start(50)  # Update every 50ms

        self.update_position()

    def update_position(self):
        """Update connection line position - create orthogonal polyline"""
        try:
            # Check if items are still valid
            if not self.start_item or not self.end_item:
                self.setVisible(False)
                return

            # Get start and end positions, ensure fixed on pins
            start_pos = self._get_optimal_port_position(self.start_item, is_start=True)
            end_pos = self._get_optimal_port_position(self.end_item, is_start=False)

            # Create orthogonal path
            self.create_orthogonal_path(start_pos, end_pos)

            self.setVisible(True)

        except Exception:
            self.setVisible(False)

    def _get_optimal_port_position(self, item, is_start=True):
        """Get optimal port position - unified for all node types"""
        # Use unified get_port_pos method for all node types
        if hasattr(item, 'get_port_pos'):
            # Determine which port to get based on start/end
            if is_start:
                port_name = self.start_port
            else:
                port_name = self.end_port

            # Fallback to default ports if not specified
            if not port_name:
                port_name = 'right' if is_start else 'left'

            return item.get_port_pos(port_name)

        # Fallback: get center of item
        return item.sceneBoundingRect().center()

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()

    def create_orthogonal_path(self, start_pos, end_pos):
        """Create orthogonal polyline path (horizontal and vertical)"""
        path = QPainterPath()
        path.moveTo(start_pos)

        # Calculate intermediate points
        mid_x = (start_pos.x() + end_pos.x()) / 2
        mid_y = (start_pos.y() + end_pos.y()) / 2

        # Determine main direction to decide path
        dx = abs(end_pos.x() - start_pos.x())
        dy = abs(end_pos.y() - start_pos.y())

        if dx > dy:
            # Horizontal distance larger, horizontal first then vertical
            path.lineTo(QPointF(mid_x, start_pos.y()))
            path.lineTo(QPointF(mid_x, end_pos.y()))
        else:
            # Vertical distance larger, vertical first then horizontal
            path.lineTo(QPointF(start_pos.x(), mid_y))
            path.lineTo(QPointF(end_pos.x(), mid_y))

        path.lineTo(end_pos)
        self.setPath(path)

    def mousePressEvent(self, event):
        """Handle mouse press event"""
        if event.button() == Qt.MouseButton.LeftButton:
            debug(f"VR连线被点击: {self.get_connection_info()}", "VRCHAIN")
            # Select this connection
            self.setSelected(True)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            debug(f"VR右键点击连线: {self.get_connection_info()}", "VRCHAIN")
            # Show context menu
            self.show_context_menu(event.screenPos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def handle_canvas_mouse_event(self, event, scene_pos=None):
        """Handle mouse events from canvas (QMouseEvent)"""
        if event.button() == Qt.MouseButton.LeftButton:
            debug(f"VR连线被点击: {self.get_connection_info()}", "VRCHAIN")
            # Select this connection
            self.setSelected(True)
            return True
        elif event.button() == Qt.MouseButton.RightButton:
            debug(f"VR右键点击连线: {self.get_connection_info()}", "VRCHAIN")
            # Show context menu at global position
            self.show_context_menu(event.globalPosition().toPoint())
            return True
        return False

    def hoverEnterEvent(self, event):
        """Handle hover enter event"""
        debug(f"VR鼠标悬停在连线上: {self.get_connection_info()}", "VRCHAIN")
        # Change appearance when hovering
        if not self.is_selected:
            hover_pen = QPen(QColor(150, 150, 150), 3)  # Lighter gray
            hover_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.setPen(hover_pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handle hover leave event"""
        # Restore appearance
        if not self.is_selected:
            self.setPen(self.default_pen)
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        """Handle context menu event"""
        self.show_context_menu(event.screenPos())
        event.accept()

    def show_context_menu(self, pos):
        """Show context menu for connection"""
        menu = QMenu()

        # Connection info action
        info_action = menu.addAction(f"🔗 VR连线信息: {self.get_connection_info()}")
        info_action.setEnabled(False)  # Make it informational only

        # Delete action
        delete_action = menu.addAction("🗑️ 删除连线")
        delete_action.triggered.connect(lambda: self.delete_connection())

        # Show menu
        menu.exec(pos)

    def get_connection_info(self):
        """Get connection information string"""
        try:
            start_name = "Unknown"
            end_name = "Unknown"

            if self.start_item:
                if hasattr(self.start_item, 'algorithm') and self.start_item.algorithm:
                    start_name = self.start_item.algorithm.get_info().display_name
                elif hasattr(self.start_item, 'node_type'):
                    start_name = f"{self.start_item.node_type} node"

            if self.end_item:
                if hasattr(self.end_item, 'algorithm') and self.end_item.algorithm:
                    end_name = self.end_item.algorithm.get_info().display_name
                elif hasattr(self.end_item, 'node_type'):
                    end_name = f"{self.end_item.node_type} node"

            port_info = ""
            if self.start_port:
                port_info += f"({self.start_port})"
            if self.end_port:
                port_info += f" → ({self.end_port})"

            return f"{start_name} → {end_name} {port_info}"
        except Exception as e:
            return f"VR Connection info unavailable: {str(e)}"

    def delete_connection(self):
        """Delete this connection"""
        try:
            debug(f"删除VR连线: {self.get_connection_info()}", "VRCHAIN")

            # Remove from scene and canvas connections list
            scene = self.scene()
            if scene:
                scene.removeItem(self)

            # Find canvas and remove from connections list
            canvas = None
            if hasattr(self, 'start_item') and self.start_item:
                canvas = getattr(self.start_item, 'canvas', None)
            elif hasattr(self, 'end_item') and self.end_item:
                canvas = getattr(self.end_item, 'canvas', None)

            if canvas and hasattr(canvas, 'connections'):
                if self in canvas.connections:
                    canvas.connections.remove(self)
                    debug(f"已从画布连接列表中移除VR连线", "VRCHAIN")

            # Update all node port colors based on actual connection status
            if canvas and hasattr(canvas, 'update_all_node_port_colors'):
                # debug(f"删除VR连线后开始更新所有节点端口颜色", "VRCHAIN")
                canvas.update_all_node_port_colors()

            # Clean up
            self.cleanup()

            # Save configuration to cache
            if canvas and hasattr(canvas, 'parent_dialog') and canvas.parent_dialog:
                canvas.parent_dialog.save_config_to_cache()

            debug(f"VR连线删除完成", "VRCHAIN")

        except Exception as e:
            debug(f"删除VR连线时出错: {str(e)}", "VRCHAIN")
            import traceback
            debug(f"删除VR连线错误详情: {traceback.format_exc()}", "VRCHAIN")

    def update_node_connection_states(self):
        """Update node connection states after deletion"""
        try:
            # Check if canvas is available
            canvas = None
            if hasattr(self, 'start_item') and self.start_item:
                canvas = getattr(self.start_item, 'canvas', None)
            elif hasattr(self, 'end_item') and self.end_item:
                canvas = getattr(self.end_item, 'canvas', None)

            # Update start node only if it has no other connections
            if self.start_item and canvas and hasattr(canvas, 'connections'):
                has_other_connections = any(
                    conn for conn in canvas.connections
                    if conn != self and (conn.start_item == self.start_item or conn.end_item == self.start_item)
                )

                if not has_other_connections:
                    # Start node has no other connections, update its state
                    if hasattr(self.start_item, 'input_connected'):
                        self.start_item.input_connected = False
                        if hasattr(self.start_item, 'update_port_colors'):
                            self.start_item.update_port_colors()
                    elif hasattr(self.start_item, 'connected'):
                        self.start_item.connected = False
                        if hasattr(self.start_item, 'update_port_color'):
                            self.start_item.update_port_color()

            # Update end node only if it has no other connections
            if self.end_item and canvas and hasattr(canvas, 'connections'):
                has_other_connections = any(
                    conn for conn in canvas.connections
                    if conn != self and (conn.start_item == self.end_item or conn.end_item == self.end_item)
                )

                if not has_other_connections:
                    # End node has no other connections, update its state
                    if hasattr(self.end_item, 'output_connected'):
                        self.end_item.output_connected = False
                        if hasattr(self.end_item, 'update_port_colors'):
                            self.end_item.update_port_colors()
                    elif hasattr(self.end_item, 'connected'):
                        self.end_item.connected = False
                        if hasattr(self.end_item, 'update_port_color'):
                            self.end_item.update_port_color()

        except Exception as e:
            debug(f"更新VR节点连接状态时出错: {str(e)}", "VRCHAIN")

    def setSelected(self, selected):
        """Set selection state"""
        self.is_selected = selected
        if selected:
            self.setPen(self.selected_pen)
            debug(f"VR连线已选中: {self.get_connection_info()}", "VRCHAIN")
        else:
            self.setPen(self.default_pen)
            debug(f"VR连线已取消选中: {self.get_connection_info()}", "VRCHAIN")


# === Compatibility Classes for VisionRobotDialog ===

class VRConnectionManager:
    """Compatibility wrapper for connection management"""

    def __init__(self, canvas):
        self.canvas = canvas

    def create_connection(self, start_node, end_node):
        """Create connection between nodes"""
        try:
            self.canvas.add_connection(start_node, end_node)
            return True
        except Exception as e:
            debug(f"VR ConnectionManager: Failed to create connection: {e}", "VRCHAIN")
            return False

    def remove_connection(self, connection):
        """Remove a connection"""
        try:
            if connection in self.canvas.connections:
                self.canvas.connections.remove(connection)
                self.canvas.scene.removeItem(connection)
            debug("VR ConnectionManager: Connection removed", "VRCHAIN")
        except Exception as e:
            debug(f"VR ConnectionManager: Failed to remove connection: {e}", "VRCHAIN")

    def get_connections_for_node(self, node):
        """Get all connections for a node"""
        connections = []
        for conn in self.canvas.connections:
            if conn.start_item == node or conn.end_item == node:
                connections.append(conn)
        return connections

    def clear_all_connections(self):
        """Clear all connections"""
        try:
            for connection in self.canvas.connections[:]:
                self.canvas.scene.removeItem(connection)
            self.canvas.connections.clear()
            debug("VR ConnectionManager: All connections cleared", "VRCHAIN")
        except Exception as e:
            debug(f"VR ConnectionManager: Failed to clear connections: {e}", "VRCHAIN")

    def clear_all_connections_for_node(self, node):
        """Clear all connections for a specific node"""
        try:
            connections_to_remove = []
            for connection in self.canvas.connections:
                if connection.start_item == node or connection.end_item == node:
                    connections_to_remove.append(connection)

            for connection in connections_to_remove:
                self.remove_connection(connection)

            debug(f"VR ConnectionManager: Cleared {len(connections_to_remove)} connections for node", "VRCHAIN")
        except Exception as e:
            debug(f"VR ConnectionManager: Failed to clear connections for node: {e}", "VRCHAIN")