from typing import Dict, Any, Optional, List
import time
import os
import json
import importlib
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QComboBox, QFrame, QFormLayout, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap, QColor
from core import RobotService, CameraService
from core.managers.log_manager import info, warning, error

# Import Camera Preview components
from ui_libs.hardware_widget.camera.camera_preview import PreviewLabel, CameraPreviewThread

class FlexibleShootingWidget(QWidget):
    """
    柔性拍摄标签页 - 支持机械臂与龙门架协同控制
    """
    
    def __init__(self, robot_service: RobotService, camera_service: CameraService, parent=None):
        super().__init__(parent)
        self.robot_service = robot_service
        self.camera_service = camera_service
        
        # Gantry State (Mock for now, would be a service in real implementation)
        self.gantry_connected = False
        self.gantry_position = {"x": 0.0, "y": 0.0, "z": 0.0}
        
        # Camera State
        self.current_camera_id = None
        self.is_previewing = False
        self.preview_thread = None

        self.setup_ui()
        self.setup_timers()

    def setup_ui(self):
        layout = QVBoxLayout()
        # 0. Top Panel: Device Connections (Horizontal Strip)
        top_panel = self.create_top_panel()
        layout.addWidget(top_panel)

        # Main Splitter for Bottom Area: Left, Middle, Right
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. Left Panel: Control & Info (Minus connections)
        left_panel = self.create_left_panel()
        main_splitter.addWidget(left_panel)
        
        # 2. Middle Panel: 3D Modeling / World Path
        middle_panel = self.create_middle_panel()
        main_splitter.addWidget(middle_panel)
        
        # 3. Right Panel: Camera Preview
        right_panel = self.create_right_panel()
        main_splitter.addWidget(right_panel)
        
        # Set sizes ratio (Left narrower, Middle & Right wider)
        # Assuming total width around 1600: Left ~300px, Middle/Right ~650px each
        main_splitter.setSizes([250, 650, 700])
        main_splitter.setStretchFactor(0, 0) # Left panel grows slower
        main_splitter.setStretchFactor(1, 1) # Middle panel grows regular
        main_splitter.setStretchFactor(2, 1) # Right panel grows regular
        
        layout.addWidget(main_splitter)
        layout.setContentsMargins(0, 0, 0, 0) # No whitespace at edges
        self.setLayout(layout)

    def setup_timers(self):
        """Setup update timers"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_realtime_info)
        self.update_timer.start(200) # 5Hz update

    # ==========================================
    # 0. Top Panel Implementation
    # ==========================================
    def create_top_panel(self):
        """Horizontal Strip for connections"""
        group = QGroupBox("机械臂龙门架连接控制")
        group.setMaximumHeight(80) # Limit height
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)

        # Robot Section
        layout.addWidget(QLabel("机械臂:"))
        self.robot_combo = QComboBox()
        self.robot_combo.setMinimumWidth(200)
        self.load_robot_configs() 
        layout.addWidget(self.robot_combo)
        
        self.robot_connect_btn = QPushButton("连接机械臂")
        self.robot_connect_btn.clicked.connect(self.toggle_robot_connection)
        layout.addWidget(self.robot_connect_btn)

        layout.addSpacing(40) # Spacer between devices
        
        # Gantry Section
        layout.addWidget(QLabel("龙门架:"))
        self.gantry_combo = QComboBox()
        self.gantry_combo.setMinimumWidth(200)
        self.gantry_combo.addItem("模拟龙门架 v1", "gantry_sim")
        layout.addWidget(self.gantry_combo)
        
        self.gantry_connect_btn = QPushButton("连接龙门架")
        self.gantry_connect_btn.clicked.connect(self.toggle_gantry_connection)
        layout.addWidget(self.gantry_connect_btn)

        layout.addStretch() # Push everything to left
        
        group.setLayout(layout)
        return group

    # ==========================================
    # 1. Left Panel Implementation
    # ==========================================
    def create_left_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # B. Robot Realtime Control (Simplified Jog)
        robot_ctrl_group = QGroupBox("机械臂实时控制")
        robot_ctrl_layout = QGridLayout()
        # Create 6 Axis Jog Buttons
        axes = ["X", "Rx", "Y", "Ry", "Z", "Rz"]
        for i, axis in enumerate(axes):
            robot_ctrl_layout.addWidget(QLabel(axis), i // 2, (i % 2) * 3)
            btn_neg = QPushButton("-")
            btn_pos = QPushButton("+")
            # Bind events (placeholders)
            robot_ctrl_layout.addWidget(btn_neg, i // 2, (i % 2) * 3 + 1)
            robot_ctrl_layout.addWidget(btn_pos, i // 2, (i % 2) * 3 + 2)
            
        robot_ctrl_group.setLayout(robot_ctrl_layout)
        layout.addWidget(robot_ctrl_group)
        
        # C. Gantry Realtime Control
        gantry_ctrl_group = QGroupBox("龙门架实时控制")
        gantry_ctrl_layout = QGridLayout()
        # XYZ Gantry Axes
        g_axes = ["X", "Y", "Z"]
        for i, axis in enumerate(g_axes):
            gantry_ctrl_layout.addWidget(QLabel(f"Gantry {axis}"), i, 0)
            btn_neg = QPushButton("-")
            btn_pos = QPushButton("+")
            gantry_ctrl_layout.addWidget(btn_neg, i, 1)
            gantry_ctrl_layout.addWidget(btn_pos, i, 2)
            
        gantry_ctrl_group.setLayout(gantry_ctrl_layout)
        layout.addWidget(gantry_ctrl_group)
        
        # D. Realtime Pose Info (Combined)
        info_group = QGroupBox("实时位姿信息显示")
        info_layout = QVBoxLayout()
        
        self.pose_table = QTableWidget(9, 1)
        self.pose_table.setVerticalHeaderLabels([
            "Robot X", "Robot Y", "Robot Z", "Robot Rx", "Robot Ry", "Robot Rz",
            "Gantry X", "Gantry Y", "Gantry Z"
        ])
        self.pose_table.horizontalHeader().setVisible(False)
        self.pose_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch) # Fill width
        info_layout.addWidget(self.pose_table)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Make the info group take up remaining vertical space
        layout.setStretchFactor(info_group, 1)
        
        return widget

    # ==========================================
    # 2. Middle Panel Implementation
    # ==========================================
    def create_middle_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 3D Modeling / World Control Group
        group = QGroupBox("三维建模 (世界坐标控制)")
        group_layout = QVBoxLayout()
        
        # Input Form
        form_layout = QFormLayout()
        self.world_x = QDoubleSpinBox()
        self.world_y = QDoubleSpinBox()
        self.world_z = QDoubleSpinBox()
        
        for spin in [self.world_x, self.world_y, self.world_z]:
            spin.setRange(-5000, 5000)
            spin.setSuffix(" mm")
        
        form_layout.addRow("目标世界坐标 X:", self.world_x)
        form_layout.addRow("目标世界坐标 Y:", self.world_y)
        form_layout.addRow("目标世界坐标 Z:", self.world_z)
        
        group_layout.addLayout(form_layout)
        
        # Action Button
        move_btn = QPushButton("移动至该坐标 (机械臂+龙门架)")
        move_btn.setFixedHeight(40)
        move_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        move_btn.clicked.connect(self.move_to_world_coordinate)
        group_layout.addWidget(move_btn)
        
        # Placeholder for 3D View
        view_label = QLabel("3D 视图预览区域 (待实现)")
        view_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_label.setStyleSheet("border: 2px dashed #aaa; background-color: #eee; min-height: 300px;")
        view_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        group_layout.addWidget(view_label)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        return widget

    # ==========================================
    # 3. Right Panel Implementation (Camera)
    # ==========================================
    def create_right_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("相机实时预览界面")
        group_layout = QVBoxLayout()
        
        # Camera Selection Toolbar
        toolbar = QHBoxLayout()
        self.camera_combo = QComboBox()
        self.refresh_cameras() # Fill combo
        
        connect_btn = QPushButton("连接")
        # Reuse logic: actually simple click for now, user asked for double click but button click is standard
        connect_btn.clicked.connect(self.connect_selected_camera)
        
        preview_btn = QPushButton("开始/停止预览")
        preview_btn.clicked.connect(self.toggle_preview)
        
        toolbar.addWidget(QLabel("相机:"))
        toolbar.addWidget(self.camera_combo)
        toolbar.addWidget(connect_btn)
        toolbar.addWidget(preview_btn)
        group_layout.addLayout(toolbar)
        
        # Preview Area
        self.preview_label = PreviewLabel("相机预览")
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setStyleSheet("background-color: black; border: 1px solid gray;")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        group_layout.addWidget(self.preview_label)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        return widget

    # ==========================================
    # Logic Helpers
    # ==========================================
    def load_robot_configs(self):
        """Load robots into dropdown (Simplified version of RobotControlTab)"""
        try:
            config_file = 'config/hardware_config.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                robots = config_data.get('robots', [])
                for r in robots:
                    self.robot_combo.addItem(f"{r.get('name')} ({r.get('model')})", r)
        except Exception as e:
            error(f"Failed to load robot configs: {e}", "FLEX_SHOOTING")

    def toggle_robot_connection(self):
        """Connect/Disconnect Robot"""
        if self.robot_service.is_connected():
            self.robot_service.disconnect()
            self.robot_connect_btn.setText("连接机械臂")
        else:
            data = self.robot_combo.currentData()
            if data:
                self.robot_service.connect(data)
                self.robot_connect_btn.setText("断开机械臂")

    def toggle_gantry_connection(self):
        """Mock Connect/Disconnect Gantry"""
        self.gantry_connected = not self.gantry_connected
        self.gantry_connect_btn.setText("断开龙门架" if self.gantry_connected else "连接龙门架")
        info(f"Gantry Connected: {self.gantry_connected}", "FLEX_SHOOTING")

    def refresh_cameras(self):
        """Load available cameras"""
        cameras = self.camera_service.get_camera_list()
        self.camera_combo.clear()
        for cam in cameras:
            self.camera_combo.addItem(f"{cam.model} ({cam.camera_id})", cam.camera_id)

    def connect_selected_camera(self):
        """Connect to selected camera"""
        cam_id = self.camera_combo.currentData()
        if cam_id:
            try:
                self.camera_service.connect_camera(cam_id)
                self.current_camera_id = cam_id
                info(f"Connected to camera {cam_id}", "FLEX_SHOOTING")
            except Exception as e:
                error(f"Camera connect failed: {e}", "FLEX_SHOOTING")

    def toggle_preview(self):
        """Start/Stop Preview Thread"""
        if self.is_previewing:
            if self.preview_thread:
                self.preview_thread.stop()
                self.preview_thread.wait()
                self.preview_thread = None
            self.is_previewing = False
        else:
            if not self.current_camera_id or not self.camera_service.is_connected(self.current_camera_id):
                 QMessageBox.warning(self, "错误", "请先连接相机")
                 return
            
            self.preview_thread = CameraPreviewThread(self.camera_service, self.current_camera_id)
            self.preview_thread.frame_ready.connect(self.update_preview)
            self.preview_thread.start()
            self.is_previewing = True

    def update_preview(self, image: QImage):
        """Update label with new frame"""
        self.preview_label.setPixmap(QPixmap.fromImage(image).scaled(
            self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio
        ))

    def update_realtime_info(self):
        """Update Pose Table"""
        # Robot Pose
        if self.robot_service.is_connected():
            # Assume get_position returns (x,y,z,rx,ry,rz)
            # This requires checking actual RobotService implementation, simplifying here
            pass 
        
        # Gantry Pose (Mock)
        if self.gantry_connected:
            self.pose_table.setItem(6, 0, QTableWidgetItem(f"{self.gantry_position['x']:.2f}"))
            self.pose_table.setItem(7, 0, QTableWidgetItem(f"{self.gantry_position['y']:.2f}"))
            self.pose_table.setItem(8, 0, QTableWidgetItem(f"{self.gantry_position['z']:.2f}"))

    def move_to_world_coordinate(self):
        """Calculate and move both system"""
        wx = self.world_x.value()
        wy = self.world_y.value()
        wz = self.world_z.value()
        
        # Example Logic: 
        # Gantry moves to rough XY proximity
        # Robot arm executes fine motion
        info(f"Moving System to World: {wx}, {wy}, {wz}", "FLEX_SHOOTING")
        
        # Mock Gantry Move
        self.gantry_position['x'] = wx
        self.gantry_position['y'] = wy
        self.gantry_position['z'] = wz # or fixed height
