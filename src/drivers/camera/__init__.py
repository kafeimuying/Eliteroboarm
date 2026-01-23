"""
相机驱动
"""

from core.managers.log_manager import warning
from .hikvision import HikvisionCamera
from .daheng import DahengCamera
from .simulation import SimulationCamera

# 尝试导入Basler相机，如果失败则使用Mock
try:
    from .basler import BaslerCamera
except ImportError as e:
    warning(f"Could not import BaslerCamera: {e}", "CAMERA_DRIVER")
    class BaslerCamera:
        def __init__(self):
            raise ImportError("BaslerCamera not available")

# 尝试导入Flir相机，如果失败则使用Mock
try:
    from .flir import FlirCamera
except ImportError as e:
    warning(f"Could not import FlirCamera: {e}", "CAMERA_DRIVER")
    class FlirCamera:
        def __init__(self):
            raise ImportError("FlirCamera not available")

__all__ = ['HikvisionCamera', 'DahengCamera', 'SimulationCamera', 'BaslerCamera', 'FlirCamera']