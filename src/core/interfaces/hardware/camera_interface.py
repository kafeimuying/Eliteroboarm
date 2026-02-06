"""
相机抽象接口
定义相机设备的抽象基类
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from enum import Enum
import numpy as np


class CameraState(Enum):
    """相机状态枚举"""
    IDLE = "空闲"
    CAPTURING = "采集中"
    STREAMING = "预览中"
    RECORDING = "录像中"
    ERROR = "错误"
    DISCONNECTED = "未连接"


class ICamera(ABC):
    """相机设备抽象接口"""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> bool:
        """连接相机"""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """断开连接"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        pass

    @abstractmethod
    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像"""
        pass

    @abstractmethod
    def start_streaming(self, callback: Callable[[np.ndarray], None]) -> bool:
        """开始视频流"""
        pass

    @abstractmethod
    def stop_streaming(self) -> bool:
        """停止视频流"""
        pass

    def auto_focus(self) -> bool:
        """触发自动对焦 (可选实现)"""
        return False

    @abstractmethod
    def is_streaming(self) -> bool:
        """检查是否正在流式传输"""
        pass

    @abstractmethod
    def set_exposure(self, exposure: float) -> bool:
        """设置曝光时间"""
        pass

    @abstractmethod
    def set_gain(self, gain: float) -> bool:
        """设置增益"""
        pass

    @abstractmethod
    def trigger_software(self) -> bool:
        """软件触发"""
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        pass