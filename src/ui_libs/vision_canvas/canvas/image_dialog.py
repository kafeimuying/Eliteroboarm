"""
Enhanced Image Display Dialog with Zoom Capabilities

This module provides a feature-rich image viewing dialog with zoom controls,
pan support, and system viewer integration.
"""

import os
import subprocess
import sys
import tempfile
import threading
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QScrollArea, QMessageBox)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPixmap

import numpy as np

# Import image conversion utilities
from utils.image_utils import numpy_to_qpixmap


class ImageDisplayDialog(QDialog):
    """Enhanced image display dialog - supports zoom and multiple images"""

    def __init__(self, image_or_images, title: str, parent=None):
        super().__init__(parent)

        # 支持单张图片或图片列表
        if isinstance(image_or_images, list):
            self.images = image_or_images
            self.current_index = 0
        else:
            self.images = [image_or_images]
            self.current_index = 0

        self.image = self.images[self.current_index]
        self.original_pixmap = None
        self.current_scale = 1.0
        self.min_scale = 0.1
        self.max_scale = 5.0

        self.init_ui(title)
        self.convert_image()
        
    def init_ui(self, title: str):
        """Initialize UI"""
        self.setWindowTitle(title)
        self.setGeometry(100, 100, 1200, 800)
        self.setWindowState(Qt.WindowState.WindowMaximized)

        # Create main layout
        layout = QVBoxLayout(self)

        # Create navigation toolbar (only show if multiple images)
        if len(self.images) > 1:
            nav_toolbar = QHBoxLayout()

            # Previous button
            self.prev_btn = QPushButton('⬅️ 上一张')
            self.prev_btn.clicked.connect(self.previous_image)
            nav_toolbar.addWidget(self.prev_btn)

            # Image counter
            self.image_counter = QLabel(f'图片 {self.current_index + 1} / {len(self.images)}')
            self.image_counter.setStyleSheet("font-weight: bold; color: #333;")
            nav_toolbar.addWidget(self.image_counter)

            # Next button
            self.next_btn = QPushButton('➡️ 下一张')
            self.next_btn.clicked.connect(self.next_image)
            nav_toolbar.addWidget(self.next_btn)

            nav_toolbar.addStretch()

            # Add to main layout
            layout.addLayout(nav_toolbar)

            # Update navigation buttons state
            self.update_navigation_buttons()

        # Create toolbar
        toolbar = QHBoxLayout()

        # Zoom buttons
        self.zoom_in_btn = QPushButton('🔍+ 放大')
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        toolbar.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton('🔍- 缩小')
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        toolbar.addWidget(self.zoom_out_btn)

        self.fit_btn = QPushButton('📐 适应窗口')
        self.fit_btn.clicked.connect(self.fit_to_window)
        toolbar.addWidget(self.fit_btn)

        self.original_btn = QPushButton('1:1 原始大小')
        self.original_btn.clicked.connect(self.original_size)
        toolbar.addWidget(self.original_btn)

        # Zoom display label
        self.zoom_label = QLabel('100%')
        toolbar.addWidget(self.zoom_label)

        toolbar.addStretch()

        # Double-click hint
        hint_label = QLabel('💡 双击图片使用系统看图器')
        hint_label.setStyleSheet("color: #666; font-size: 10px;")
        toolbar.addWidget(hint_label)

        # Close button
        close_btn = QPushButton('❌ 关闭')
        close_btn.clicked.connect(self.accept)
        toolbar.addWidget(close_btn)

        layout.addLayout(toolbar)
        
        # Create image display area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)
        
        # Set mouse tracking
        self.setMouseTracking(True)
        self.image_label.setMouseTracking(True)
        
        # Install event filter
        self.image_label.installEventFilter(self)
        
    def convert_image(self):
        """Convert numpy array to QPixmap"""
        try:
            # Use unified image conversion utility
            self.original_pixmap = numpy_to_qpixmap(self.image)
            self.fit_to_window()
            
        except Exception as e:
            self.image_label.setText(f"图像转换错误: {e}")
    
    def zoom_in(self):
        """Zoom in"""
        if self.current_scale < self.max_scale:
            self.current_scale *= 1.2
            self.update_image_display()
    
    def zoom_out(self):
        """Zoom out"""
        if self.current_scale > self.min_scale:
            self.current_scale /= 1.2
            self.update_image_display()
    
    def fit_to_window(self):
        """Fit to window size"""
        if self.original_pixmap:
            # Calculate appropriate scale
            viewport_size = self.scroll_area.viewport().size()
            pixmap_size = self.original_pixmap.size()
            
            scale_x = viewport_size.width() / pixmap_size.width()
            scale_y = viewport_size.height() / pixmap_size.height()
            self.current_scale = min(scale_x, scale_y, 1.0)  # Don't exceed original size
            
            self.update_image_display()
    
    def original_size(self):
        """Original size"""
        self.current_scale = 1.0
        self.update_image_display()
    
    def update_image_display(self):
        """Update image display"""
        if self.original_pixmap:
            # Calculate scaled size
            new_size = self.original_pixmap.size() * self.current_scale
            scaled_pixmap = self.original_pixmap.scaled(
                new_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setMinimumSize(new_size)
            
            # Update zoom display
            self.zoom_label.setText(f'{int(self.current_scale * 100)}%')
    
    def eventFilter(self, obj, event):
        """Event filter - handle mouse wheel zoom and double-click"""
        if obj == self.image_label:
            if event.type() == event.Type.Wheel:
                # Get wheel angle
                delta = event.angleDelta().y()
                if delta > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()
                return True
            elif event.type() == event.Type.MouseButtonDblClick:
                # Double-click to open system viewer
                self.open_in_system_viewer()
                return True
        
        return super().eventFilter(obj, event)
    
    def open_in_system_viewer(self):
        """Open image in system viewer"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                if len(self.image.shape) == 3:
                    # Color image
                    import cv2
                    cv2.imwrite(tmp_file.name, self.image)
                else:
                    # Grayscale image
                    import cv2
                    cv2.imwrite(tmp_file.name, self.image)
                
                # Use system default program to open
                if sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', tmp_file.name])
                elif sys.platform == 'win32':  # Windows
                    subprocess.run(['start', tmp_file.name], shell=True)
                else:  # Linux
                    subprocess.run(['xdg-open', tmp_file.name])
                
                # Delay delete temporary file (give system viewer time to open)
                def delete_tmp_file():
                    import time
                    time.sleep(2)  # Wait 2 seconds
                    try:
                        os.unlink(tmp_file.name)
                    except:
                        pass
                
                threading.Thread(target=delete_tmp_file, daemon=True).start()
                
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开系统看图器: {e}")

    def previous_image(self):
        """Navigate to previous image"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()

    def next_image(self):
        """Navigate to next image"""
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            self.load_current_image()

    def load_current_image(self):
        """Load current image and update display"""
        self.image = self.images[self.current_index]
        self.convert_image()
        self.update_navigation_buttons()
        self.update_image_counter()

    def update_navigation_buttons(self):
        """Update navigation buttons state"""
        if len(self.images) > 1 and hasattr(self, 'prev_btn') and hasattr(self, 'next_btn'):
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.images) - 1)

    def update_image_counter(self):
        """Update image counter display"""
        if len(self.images) > 1 and hasattr(self, 'image_counter'):
            self.image_counter.setText(f'图片 {self.current_index + 1} / {len(self.images)}')

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if len(self.images) > 1:
            if event.key() == Qt.Key.Key_Left:
                self.previous_image()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Right:
                self.next_image()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Up:
                self.previous_image()  # 上键等效于上一张
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Down:
                self.next_image()  # 下键等效于下一张
                event.accept()
                return

        # Handle zoom with keyboard
        if event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            self.zoom_in()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
            event.accept()
            return

        super().keyPressEvent(event)

    def showEvent(self, event):
        """Handle window show event - ensure first image fits to window"""
        super().showEvent(event)
        # 确保第一张图片正确适应窗口
        if hasattr(self, 'original_pixmap') and self.original_pixmap:
            # 延迟执行以确保窗口完全显示
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self.fit_to_window)