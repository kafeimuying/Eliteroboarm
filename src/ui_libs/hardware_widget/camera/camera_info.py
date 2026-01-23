"""
相机信息类
"""

from typing import Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal


class CameraInfo(QObject):
    """相机信息类"""
    frame_captured = pyqtSignal(object)  # 帧数据

    def __init__(self, camera_id: str, config: Dict[str, Any] = None):
        super().__init__()
        self.camera_id = camera_id
        self.name = camera_id  # 添加名称属性
        self.camera_type = "未知相机"
        self.resolution = "1920x1080"
        self.config = config or {}
        self.connected = False
        self.current_frame = None
        self.preview_thread = None
        self.camera_driver = None  # 实际的相机驱动实例

        # 添加额外的属性
        self.fps = 30
        self.last_frame_time = None