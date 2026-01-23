"""
数字光源驱动实现
调用光源控制器SDK进行具体设备控制
"""

import time
from typing import Optional, Dict, Any

try:
    # 尝试导入光源SDK（如果存在）
    import light_sdk as light_sdk
    LIGHT_SDK_AVAILABLE = True
except ImportError:
    # 如果没有SDK，无法连接真实设备
    LIGHT_SDK_AVAILABLE = False

from core.interfaces.hardware.light_interface import ILight
from core.managers.log_manager import warning, info, error, debug


class DigitalLight(ILight):
    """数字光源驱动实现"""

    def __init__(self):
        # 在初始化时显示SDK可用性警告
        if not LIGHT_SDK_AVAILABLE:
            warning("Light SDK not available - real light connection not possible", "LIGHT_DRIVER")

        self.sdk = None
        self.connected = False
        self.channel_count = 8
        self.channel_brightness = [0.0] * self.channel_count
        self.channel_enabled = [False] * self.channel_count
        self.config = {}

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接数字光源"""
        try:
            self.config = config
            info(f"Connecting to digital light at {config.get('ip')}:{config.get('port')}", "LIGHT_DRIVER")

            if not LIGHT_SDK_AVAILABLE:
                error("Light SDK not available - cannot connect to real light", "LIGHT_DRIVER")
                return False

            # 使用SDK连接
            self.sdk = light_sdk.DigitalLightController()
            success = self.sdk.connect(
                ip=config['ip'],
                port=config.get('port', 8080),
                timeout=config.get('timeout', 5.0)
            )

            if success:
                # 获取实际的通道数量
                self.channel_count = self.sdk.get_channel_count()
                self.channel_brightness = [0.0] * self.channel_count
                self.channel_enabled = [False] * self.channel_count
                self.connected = True
                info(f"Digital light connected successfully at {config.get('ip')}", "LIGHT_DRIVER")
            else:
                error(f"Failed to connect to digital light at {config.get('ip')}", "LIGHT_DRIVER")
                self.connected = False

            return self.connected

        except Exception as e:
            error(f"Failed to connect digital light: {e}", "LIGHT_DRIVER")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.sdk and LIGHT_SDK_AVAILABLE:
                self.sdk.disconnect()
                self.sdk = None

            self.connected = False
            self.channel_brightness = [0.0] * self.channel_count
            self.channel_enabled = [False] * self.channel_count
            logger.info("Digital light disconnected")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect digital light: {e}")
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        if self.sdk and LIGHT_SDK_AVAILABLE:
            return self.sdk.is_connected()
        return self.connected

    def set_brightness(self, channel: int, brightness: float) -> bool:
        """设置通道亮度"""
        if not self.is_connected():
            logger.error("Light not connected")
            return False

        if not (0 <= channel < self.channel_count):
            logger.error(f"Invalid channel: {channel}")
            return False

        if not (0 <= brightness <= 100):
            logger.error(f"Invalid brightness: {brightness}")
            return False

        try:
            logger.info(f"Setting channel {channel} brightness to {brightness}%")

            if self.sdk and LIGHT_SDK_AVAILABLE:
                success = self.sdk.set_channel_brightness(channel, brightness)
                if success:
                    self.channel_brightness[channel] = brightness
                return success
            else:
                # 模拟设置亮度
                self.channel_brightness[channel] = brightness
                logger.info(f"Mock channel {channel} brightness set to {brightness}%")
                return True

        except Exception as e:
            logger.error(f"Failed to set brightness: {e}")
            return False

    def get_brightness(self, channel: int) -> Optional[float]:
        """获取通道亮度"""
        if not self.is_connected():
            logger.warning("Light not connected")
            return None

        if not (0 <= channel < self.channel_count):
            logger.error(f"Invalid channel: {channel}")
            return None

        try:
            if self.sdk and LIGHT_SDK_AVAILABLE:
                brightness = self.sdk.get_channel_brightness(channel)
                if brightness is not None:
                    self.channel_brightness[channel] = brightness
                return brightness
            else:
                # 返回缓存值
                return self.channel_brightness[channel]

        except Exception as e:
            logger.error(f"Failed to get brightness: {e}")
            return None

    def enable_channel(self, channel: int, enabled: bool) -> bool:
        """启用/禁用通道"""
        if not self.is_connected():
            logger.error("Light not connected")
            return False

        if not (0 <= channel < self.channel_count):
            logger.error(f"Invalid channel: {channel}")
            return False

        try:
            logger.info(f"{'Enabling' if enabled else 'Disabling'} channel {channel}")

            if self.sdk and LIGHT_SDK_AVAILABLE:
                success = self.sdk.enable_channel(channel, enabled)
                if success:
                    self.channel_enabled[channel] = enabled
                return success
            else:
                # 模拟启用/禁用
                self.channel_enabled[channel] = enabled
                logger.info(f"Mock channel {channel} {'enabled' if enabled else 'disabled'}")
                return True

        except Exception as e:
            logger.error(f"Failed to enable/disable channel: {e}")
            return False

    def trigger_all(self) -> bool:
        """触发所有通道"""
        if not self.is_connected():
            logger.error("Light not connected")
            return False

        try:
            logger.info("Triggering all channels")

            if self.sdk and LIGHT_SDK_AVAILABLE:
                return self.sdk.trigger_all_channels()
            else:
                # 模拟触发
                time.sleep(0.1)  # 模拟触发延迟
                logger.info("Mock trigger completed")
                return True

        except Exception as e:
            logger.error(f"Failed to trigger: {e}")
            return False

    def emergency_off(self) -> bool:
        """紧急关闭所有通道"""
        try:
            logger.warning("Emergency off all channels")

            if self.sdk and LIGHT_SDK_AVAILABLE:
                success = self.sdk.emergency_off()
                if success:
                    self.channel_brightness = [0.0] * self.channel_count
                    self.channel_enabled = [False] * self.channel_count
                return success
            else:
                # 模拟紧急关闭
                self.channel_brightness = [0.0] * self.channel_count
                self.channel_enabled = [False] * self.channel_count
                logger.warning("Mock emergency off completed")
                return True

        except Exception as e:
            logger.error(f"Failed to emergency off: {e}")
            return False

    def get_channel_count(self) -> int:
        """获取通道数量"""
        if not self.is_connected():
            return 0

        try:
            if self.sdk and LIGHT_SDK_AVAILABLE:
                count = self.sdk.get_channel_count()
                if count > 0:
                    self.channel_count = count
            return self.channel_count
        except Exception as e:
            logger.error(f"Failed to get channel count: {e}")
            return 0

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        info = {
            'brand': 'Generic',
            'type': 'Digital Light',
            'connected': self.is_connected(),
            'channel_count': self.channel_count,
            'ip': self.config.get('ip', 'Unknown'),
            'sdk_available': LIGHT_SDK_AVAILABLE,
            'channel_brightness': self.channel_brightness.copy(),
            'channel_enabled': self.channel_enabled.copy()
        }

        if self.sdk and LIGHT_SDK_AVAILABLE:
            try:
                sdk_info = self.sdk.get_light_info()
                info.update(sdk_info)
            except Exception as e:
                logger.warning(f"Failed to get SDK info: {e}")

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
                result['error'] = 'Light not connected'
                return result

            # 测试获取通道数量
            count = self.get_channel_count()
            if count <= 0:
                result['error'] = 'Failed to get channel count'
                return result

            # 测试设置亮度
            if count > 0:
                # 测试第一个通道
                test_brightness = 50.0
                if self.set_brightness(0, test_brightness):
                    retrieved_brightness = self.get_brightness(0)
                    if retrieved_brightness is None:
                        result['error'] = 'Failed to get brightness'
                        return result
                else:
                    result['error'] = 'Failed to set brightness'
                    return result

            result['success'] = True
            result['channel_count'] = count

        except Exception as e:
            result['error'] = str(e)

        return result