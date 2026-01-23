"""
光源抽象接口
定义光源设备的抽象基类
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class ILight(ABC):
    """光源设备抽象接口"""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> bool:
        """连接光源控制器"""
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
    def set_brightness(self, channel: int, brightness: float) -> bool:
        """设置通道亮度 (0-100%)"""
        pass

    @abstractmethod
    def get_brightness(self, channel: int) -> Optional[float]:
        """获取通道亮度"""
        pass

    @abstractmethod
    def enable_channel(self, channel: int, enabled: bool) -> bool:
        """启用/禁用通道"""
        pass

    @abstractmethod
    def trigger_all(self) -> bool:
        """触发所有通道"""
        pass

    @abstractmethod
    def emergency_off(self) -> bool:
        """紧急关闭所有通道"""
        pass

    @abstractmethod
    def get_channel_count(self) -> int:
        """获取通道数量"""
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        pass