"""
海康威视相机驱动实现
调用海康威视SDK进行具体设备控制
"""

import time
import threading
from typing import Optional, Dict, Any, Callable

try:
    # 尝试导入海康威视官方SDK（如果存在）
    import hikvision_sdk as hik_sdk
    HIKVISION_SDK_AVAILABLE = True
except ImportError:
    # 如果没有官方SDK，无法连接真实设备
    HIKVISION_SDK_AVAILABLE = False

import numpy as np
from core.interfaces.hardware.camera_interface import ICamera
from core.managers.log_manager import warning, info, error, debug


class HikvisionCamera(ICamera):
    """海康威视相机驱动实现"""

    def __init__(self):
        # 在初始化时显示SDK可用性警告
        if not HIKVISION_SDK_AVAILABLE:
            warning("Hikvision SDK not available - real camera connection not possible", "CAMERA_DRIVER")

        self.sdk = None
        self.connected = False
        self.streaming = False
        self.frame_callback = None
        self.stream_thread = None
        self.config = {}

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接海康威视相机"""
        try:
            self.config = config
            info(f"Connecting to Hikvision camera at {config.get('ip')}:{config.get('port')}", "CAMERA_DRIVER")

            if not HIKVISION_SDK_AVAILABLE:
                error("Hikvision SDK not available - cannot connect to real camera", "CAMERA_DRIVER")
                return False

            # 使用官方SDK连接
            self.sdk = hik_sdk.Camera()
            success = self.sdk.connect(
                ip=config['ip'],
                port=config.get('port', 8000),
                username=config.get('username', 'admin'),
                password=config.get('password', 'admin123'),
                channel=config.get('channel', 1)
            )

            if success:
                self.connected = True
                info(f"Hikvision camera connected successfully at {config.get('ip')}", "CAMERA_DRIVER")
            else:
                error(f"Failed to connect to Hikvision camera at {config.get('ip')}", "CAMERA_DRIVER")
                self.connected = False

            return self.connected

        except Exception as e:
            error(f"Failed to connect Hikvision camera: {e}", "CAMERA_DRIVER")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """断开连接""" 
        try:
            # 先停止视频流
            if self.streaming:
                self.stop_streaming()

            if self.sdk and HIKVISION_SDK_AVAILABLE:
                self.sdk.disconnect()
                self.sdk = None

            self.connected = False
            info("Hikvision camera disconnected", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to disconnect Hikvision camera: {e}", "CAMERA_DRIVER")
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        if self.sdk and HIKVISION_SDK_AVAILABLE:
            return self.sdk.is_connected()
        return self.connected

    def is_streaming(self) -> bool:
        """检查是否正在流式传输"""
        return bool(self.streaming)  # 确保返回明确的布尔值

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像"""
        if not self.is_connected():
            error("Camera not connected", "CAMERA_DRIVER")
            return None

        try:
            if self.sdk and HIKVISION_SDK_AVAILABLE:
                # 使用官方SDK抓图
                frame = self.sdk.capture_frame()
                return frame
            else:
                error("SDK not available - cannot capture real frame", "CAMERA_DRIVER")
                return None

        except Exception as e:
            error(f"Failed to capture frame: {e}", "CAMERA_DRIVER")
            return None

    def start_streaming(self, callback: Callable[[np.ndarray], None]) -> bool:
        """开始视频流"""
        if not self.is_connected():
            error("Camera not connected", "CAMERA_DRIVER")
            return False

        try:
            if self.streaming:
                warning("Streaming already started", "CAMERA_DRIVER")
                return True

            self.frame_callback = callback

            if self.sdk and HIKVISION_SDK_AVAILABLE:
                # 使用官方SDK开始流
                success = self.sdk.start_streaming(callback)
                self.streaming = success
                if success:
                    info("Streaming started successfully", "CAMERA_DRIVER")
                return success
            else:
                error("SDK not available - cannot start real streaming", "CAMERA_DRIVER")
                return False

        except Exception as e:
            error(f"Failed to start streaming: {e}", "CAMERA_DRIVER")
            self.streaming = False
            return False

    def stop_streaming(self) -> bool:
        """停止视频流"""
        try:
            if not self.streaming:
                return True

            if self.sdk and HIKVISION_SDK_AVAILABLE:
                # 使用官方SDK停止流
                success = self.sdk.stop_streaming()
            else:
                success = True

            self.streaming = False
            self.frame_callback = None
            info("Streaming stopped", "CAMERA_DRIVER")
            return success

        except Exception as e:
            error(f"Failed to stop streaming: {e}", "CAMERA_DRIVER")
            return False

  
    def set_exposure(self, exposure: float) -> bool:
        """设置曝光时间"""
        if not self.is_connected():
            error("Camera not connected", "CAMERA_DRIVER")
            return False

        try:
            info(f"Setting exposure to {exposure}", "CAMERA_DRIVER")

            if self.sdk and HIKVISION_SDK_AVAILABLE:
                return self.sdk.set_exposure(exposure)
            else:
                error("SDK not available - cannot set exposure", "CAMERA_DRIVER")
                return False

        except Exception as e:
            error(f"Failed to set exposure: {e}", "CAMERA_DRIVER")
            return False

    def set_gain(self, gain: float) -> bool:
        """设置增益"""
        if not self.is_connected():
            error("Camera not connected", "CAMERA_DRIVER")
            return False

        try:
            info(f"Setting gain to {gain}", "CAMERA_DRIVER")

            if self.sdk and HIKVISION_SDK_AVAILABLE:
                return self.sdk.set_gain(gain)
            else:
                error("SDK not available - cannot set gain", "CAMERA_DRIVER")
                return False

        except Exception as e:
            error(f"Failed to set gain: {e}", "CAMERA_DRIVER")
            return False

    def trigger_software(self) -> bool:
        """软件触发"""
        if not self.is_connected():
            error("Camera not connected", "CAMERA_DRIVER")
            return False

        try:
            info("Software trigger", "CAMERA_DRIVER")

            if self.sdk and HIKVISION_SDK_AVAILABLE:
                return self.sdk.trigger_software()
            else:
                error("SDK not available - cannot trigger software", "CAMERA_DRIVER")
                return False

        except Exception as e:
            error(f"Failed to software trigger: {e}", "CAMERA_DRIVER")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        info = {
            'brand': 'Hikvision',
            'type': 'Camera',
            'connected': self.is_connected(),
            'streaming': self.streaming,
            'ip': self.config.get('ip', 'Unknown'),
            'channel': self.config.get('channel', 1),
            'sdk_available': HIKVISION_SDK_AVAILABLE
        }

        if self.sdk and HIKVISION_SDK_AVAILABLE:
            try:
                sdk_info = self.sdk.get_camera_info()
                info.update(sdk_info)
            except Exception as e:
                warning(f"Failed to get SDK info: {e}", "CAMERA_DRIVER")

        return info

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        result = {
            'success': False,
            'error': None,
            'info': self.get_info()
        }

        try:
            if not self.is_connected():
                result['error'] = 'Camera not connected'
                return result

            # 测试抓图
            frame = self.capture_frame()
            if frame is None:
                result['error'] = 'Failed to capture frame'
                return result

            # 测试设备信息获取
            info = self.get_info()
            if not info:
                result['error'] = 'Failed to get device info'
                return result

            result['success'] = True
            result['frame_shape'] = frame.shape if frame is not None else None

        except Exception as e:
            result['error'] = str(e)

        return result