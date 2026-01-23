"""
光源服务层
提供光源的高级业务逻辑和UI接口
"""

from typing import Optional, Dict, Any, List
from ..interfaces.hardware import ILight
from ..managers.log_manager import info, debug, warning, error


class LightService:
    """光源服务类，封装业务逻辑"""

    def __init__(self, light: Optional[ILight] = None):
        self.light = light

    def set_light(self, light: ILight):
        """设置光源实例（用于运行时切换）"""
        self.light = light
        info("Light service updated with new light instance")

    def set_device(self, light: ILight):
        """设置设备实例（与set_light功能相同，用于统一接口）"""
        self.set_light(light)

    def connect(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """连接光源"""
        if not self.light:
            return {'success': False, 'error': 'No light instance available'}

        try:
            success = self.light.connect(config)
            if success:
                info("Light connected successfully")
                return {'success': True, 'message': 'Light connected'}
            else:
                error("Failed to connect light")
                return {'success': False, 'error': 'Failed to connect light'}
        except Exception as e:
            error(f"Light connection error: {e}")
            return {'success': False, 'error': str(e)}

    def disconnect(self) -> Dict[str, Any]:
        """断开光源连接"""
        if not self.light:
            return {'success': False, 'error': 'No light instance available'}

        try:
            success = self.light.disconnect()
            if success:
                info("Light disconnected successfully")
                return {'success': True, 'message': 'Light disconnected'}
            else:
                error("Failed to disconnect light")
                return {'success': False, 'error': 'Failed to disconnect light'}
        except Exception as e:
            error(f"Light disconnection error: {e}")
            return {'success': False, 'error': str(e)}

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.light is not None and self.light.is_connected()

    def set_brightness(self, channel: int, brightness: float) -> Dict[str, Any]:
        """设置通道亮度"""
        if not self.light:
            return {'success': False, 'error': 'No light instance available'}

        if not self.light.is_connected():
            return {'success': False, 'error': 'Light not connected'}

        if not (0 <= brightness <= 100):
            return {'success': False, 'error': 'Brightness must be between 0 and 100'}

        try:
            info(f"Setting channel {channel} brightness to {brightness}%")
            success = self.light.set_brightness(channel, brightness)

            if success:
                info(f"Channel {channel} brightness set to {brightness}%")
                return {'success': True, 'message': f'Channel {channel} brightness set to {brightness}%'}
            else:
                error(f"Failed to set channel {channel} brightness")
                return {'success': False, 'error': f'Failed to set channel {channel} brightness'}
        except Exception as e:
            error(f"Set brightness error: {e}")
            return {'success': False, 'error': str(e)}

    def get_brightness(self, channel: int) -> Optional[float]:
        """获取通道亮度"""
        if not self.light or not self.light.is_connected():
            warning("Light not connected")
            return None

        try:
            brightness = self.light.get_brightness(channel)
            if brightness is not None:
                debug(f"Channel {channel} brightness: {brightness}%")
            return brightness
        except Exception as e:
            error(f"Failed to get channel {channel} brightness: {e}")
            return None

    def enable_channel(self, channel: int, enabled: bool) -> Dict[str, Any]:
        """启用/禁用通道"""
        if not self.light:
            return {'success': False, 'error': 'No light instance available'}

        if not self.light.is_connected():
            return {'success': False, 'error': 'Light not connected'}

        try:
            action = "Enabling" if enabled else "Disabling"
            info(f"{action} channel {channel}")
            success = self.light.enable_channel(channel, enabled)

            if success:
                info(f"Channel {channel} {action.lower()}ed")
                return {'success': True, 'message': f'Channel {channel} {action.lower()}ed'}
            else:
                error(f"Failed to {action.lower()} channel {channel}")
                return {'success': False, 'error': f'Failed to {action.lower()} channel {channel}'}
        except Exception as e:
            error(f"Enable/disable channel error: {e}")
            return {'success': False, 'error': str(e)}

    def trigger_all(self) -> Dict[str, Any]:
        """触发所有通道"""
        if not self.light:
            return {'success': False, 'error': 'No light instance available'}

        if not self.light.is_connected():
            return {'success': False, 'error': 'Light not connected'}

        try:
            info("Triggering all light channels")
            success = self.light.trigger_all()

            if success:
                info("All channels triggered")
                return {'success': True, 'message': 'All channels triggered'}
            else:
                error("Failed to trigger all channels")
                return {'success': False, 'error': 'Failed to trigger all channels'}
        except Exception as e:
            error(f"Trigger all channels error: {e}")
            return {'success': False, 'error': str(e)}

    def emergency_off(self) -> Dict[str, Any]:
        """紧急关闭所有通道"""
        try:
            warning("Emergency off all light channels")

            if self.light:
                success = self.light.emergency_off()
            else:
                # 即使没有光源实例，也要返回成功
                success = True

            if success:
                warning("Emergency off completed")
                return {'success': True, 'message': 'Emergency off completed'}
            else:
                error("Failed to emergency off")
                return {'success': False, 'error': 'Failed to emergency off'}
        except Exception as e:
            error(f"Emergency off error: {e}")
            return {'success': False, 'error': str(e)}

    def get_channel_count(self) -> int:
        """获取通道数量"""
        if not self.light or not self.light.is_connected():
            return 0

        try:
            return self.light.get_channel_count()
        except Exception as e:
            error(f"Failed to get channel count: {e}")
            return 0

    def get_info(self) -> Optional[Dict[str, Any]]:
        """获取光源信息"""
        if not self.light:
            return None

        try:
            return self.light.get_info()
        except Exception as e:
            error(f"Failed to get light info: {e}")
            return None

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self.light:
            return {'success': False, 'error': 'No light instance available'}

        try:
            return self.light.test_connection()
        except Exception as e:
            error(f"Connection test error: {e}")
            return {'success': False, 'error': str(e)}

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        status = {
            'connected': self.is_connected(),
            'channel_count': self.get_channel_count(),
            'light_info': self.get_info()
        }

        # 添加所有通道的当前状态
        if self.is_connected():
            channel_count = self.get_channel_count()
            channel_status = []
            for channel in range(channel_count):
                brightness = self.get_brightness(channel)
                channel_status.append({
                    'channel': channel,
                    'brightness': brightness,
                    'enabled': True  # 可以从光源设备获取实际状态
                })
            status['channels'] = channel_status

        return status

    def set_all_brightness(self, brightness: float) -> Dict[str, Any]:
        """设置所有通道亮度"""
        if not (0 <= brightness <= 100):
            return {'success': False, 'error': 'Brightness must be between 0 and 100'}

        channel_count = self.get_channel_count()
        if channel_count == 0:
            return {'success': False, 'error': 'No channels available'}

        try:
            info(f"Setting all {channel_count} channels to {brightness}%")
            success = True
            failed_channels = []

            for channel in range(channel_count):
                result = self.set_brightness(channel, brightness)
                if not result['success']:
                    success = False
                    failed_channels.append(channel)

            if success:
                info(f"All channels set to {brightness}%")
                return {'success': True, 'message': f'All channels set to {brightness}%'}
            else:
                error_msg = f'Failed to set channels: {failed_channels}'
                error(error_msg)
                return {'success': False, 'error': error_msg}
        except Exception as e:
            error(f"Set all brightness error: {e}")
            return {'success': False, 'error': str(e)}

    def enable_all_channels(self, enabled: bool) -> Dict[str, Any]:
        """启用/禁用所有通道"""
        channel_count = self.get_channel_count()
        if channel_count == 0:
            return {'success': False, 'error': 'No channels available'}

        try:
            action = "Enabling" if enabled else "Disabling"
            info(f"{action.lower()} all {channel_count} channels")
            success = True
            failed_channels = []

            for channel in range(channel_count):
                result = self.enable_channel(channel, enabled)
                if not result['success']:
                    success = False
                    failed_channels.append(channel)

            if success:
                info(f"All channels {action.lower()}ed")
                return {'success': True, 'message': f'All channels {action.lower()}ed'}
            else:
                error_msg = f'Failed to {action.lower()} channels: {failed_channels}'
                error(error_msg)
                return {'success': False, 'error': error_msg}
        except Exception as e:
            error(f"Enable/disable all channels error: {e}")
            return {'success': False, 'error': str(e)}