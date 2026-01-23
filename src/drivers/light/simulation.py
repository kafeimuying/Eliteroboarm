"""
模拟光源驱动
用于测试和演示光源功能
"""

import logging
import time
import threading
from typing import Optional, Dict, Any, List
from core.interfaces.hardware.light_interface import ILight

logger = logging.getLogger(__name__)


class SimulationLight(ILight):
    """模拟光源实现"""

    def __init__(self, light_id: str = "sim_light_001"):
        """初始化模拟光源"""
        self.light_id = light_id
        self.connected = False

        # 模拟光源参数
        self.channel_count = 4
        self.brightness_levels = [0.0] * self.channel_count  # 每个通道的亮度 (0-100)
        self.channel_enabled = [True] * self.channel_count  # 每个通道的启用状态

        # 模拟光源特性
        self.max_brightness = 100.0
        self.min_brightness = 0.0
        self.brightness_step = 1.0

        # 状态回调
        self.state_callbacks = []

        # 定时器用于模拟亮度变化
        self.update_timer = None
        self.is_fading = False
        self.fade_thread = None
        self.stop_fade = threading.Event()

        logger.info(f"Simulation light initialized: {light_id}")

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接光源"""
        if self.connected:
            logger.warning("Light already connected")
            return True

        logger.info(f"Connecting simulation light with config: {config}")

        # 从配置中获取通道数
        if 'channel_count' in config:
            self.channel_count = config['channel_count']
            self.brightness_levels = [0.0] * self.channel_count
            self.channel_enabled = [True] * self.channel_count

        # 模拟连接延迟
        time.sleep(0.1)
        self.connected = True

        logger.info(f"Simulation light connected with {self.channel_count} channels")
        return True

    def disconnect(self) -> bool:
        """断开连接"""
        if not self.connected:
            return True

        logger.info("Disconnecting simulation light")

        # 停止所有渐变效果
        self.stop_fade_effects()

        # 关闭所有通道
        for i in range(self.channel_count):
            self.set_brightness(i, 0.0)

        self.connected = False
        logger.info("Simulation light disconnected")
        return True

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected

    def set_brightness(self, channel: int, brightness: float) -> bool:
        """设置通道亮度"""
        if not self.connected:
            logger.error("Light not connected")
            return False

        if channel < 0 or channel >= self.channel_count:
            logger.error(f"Invalid channel: {channel}")
            return False

        if brightness < self.min_brightness or brightness > self.max_brightness:
            logger.error(f"Invalid brightness: {brightness}")
            return False

        old_brightness = self.brightness_levels[channel]
        self.brightness_levels[channel] = brightness

        logger.info(f"Channel {channel} brightness set to {brightness}%")

        # 通知状态变化
        self._notify_state_change(channel, 'brightness', old_brightness, brightness)

        return True

    def get_brightness(self, channel: int) -> Optional[float]:
        """获取通道亮度"""
        if not self.connected:
            logger.warning("Light not connected")
            return None

        if channel < 0 or channel >= self.channel_count:
            logger.error(f"Invalid channel: {channel}")
            return None

        return self.brightness_levels[channel]

    def enable_channel(self, channel: int, enabled: bool) -> bool:
        """启用/禁用通道"""
        if not self.connected:
            logger.error("Light not connected")
            return False

        if channel < 0 or channel >= self.channel_count:
            logger.error(f"Invalid channel: {channel}")
            return False

        old_enabled = self.channel_enabled[channel]
        self.channel_enabled[channel] = enabled

        action = "enabled" if enabled else "disabled"
        logger.info(f"Channel {channel} {action}")

        # 如果禁用通道，亮度归零
        if not enabled:
            self.set_brightness(channel, 0.0)

        # 通知状态变化
        self._notify_state_change(channel, 'enabled', old_enabled, enabled)

        return True

    def trigger_all(self) -> bool:
        """触发所有通道"""
        if not self.connected:
            logger.error("Light not connected")
            return False

        logger.info("Triggering all channels")

        # 将所有通道设置为最大亮度
        for i in range(self.channel_count):
            self.set_brightness(i, self.max_brightness)

        # 保持一段时间后恢复
        def trigger_worker():
            time.sleep(2.0)  # 保持2秒
            if self.connected:
                for i in range(self.channel_count):
                    self.set_brightness(i, 0.0)

        threading.Thread(target=trigger_worker, daemon=True).start()
        return True

    def emergency_off(self) -> bool:
        """紧急关闭所有通道"""
        try:
            logger.warning("Emergency off all channels")

            # 停止所有渐变效果
            self.stop_fade_effects()

            # 立即关闭所有通道
            for i in range(self.channel_count):
                self.brightness_levels[i] = 0.0
                self.channel_enabled[i] = True

            # 通知状态变化
            for i in range(self.channel_count):
                self._notify_state_change(i, 'brightness', self.max_brightness, 0.0)

            return True
        except Exception as e:
            logger.error(f"Emergency off error: {e}")
            return False

    def get_channel_count(self) -> int:
        """获取通道数量"""
        return self.channel_count

    def get_info(self) -> Optional[Dict[str, Any]]:
        """获取光源信息"""
        if not self.connected:
            return None

        return {
            'type': 'Simulation Light',
            'model': 'SIM-LIGHT-001',
            'serial_number': self.light_id,
            'firmware': '1.0.0',
            'channel_count': self.channel_count,
            'max_brightness': self.max_brightness,
            'min_brightness': self.min_brightness,
            'power_consumption': f"{self.channel_count * 10}W",  # 模拟功率消耗
            'control_interface': 'Simulation'
        }

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self.connected:
            return {
                'success': False,
                'error': 'Not connected',
                'message': 'Simulation light not connected'
            }

        try:
            # 测试设置亮度
            test_channel = 0
            original_brightness = self.brightness_levels[test_channel]

            # 设置测试亮度
            test_brightness = 50.0
            success = self.set_brightness(test_channel, test_brightness)

            if success and abs(self.brightness_levels[test_channel] - test_brightness) < 0.1:
                # 恢复原始亮度
                self.set_brightness(test_channel, original_brightness)

                return {
                    'success': True,
                    'message': 'Simulation light connection test successful',
                    'device_info': self.get_info(),
                    'response_time_ms': 5,
                    'channel_count': self.channel_count
                }
            else:
                return {
                    'success': False,
                    'error': 'Brightness control test failed'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Connection test error: {str(e)}'
            }

    # ========== 高级功能 ==========
    def set_all_brightness(self, brightness: float) -> bool:
        """设置所有通道亮度"""
        if not self.connected:
            return False

        if brightness < self.min_brightness or brightness > self.max_brightness:
            return False

        success = True
        for i in range(self.channel_count):
            if not self.set_brightness(i, brightness):
                success = False

        return success

    def enable_all_channels(self, enabled: bool) -> bool:
        """启用/禁用所有通道"""
        if not self.connected:
            return False

        success = True
        for i in range(self.channel_count):
            if not self.enable_channel(i, enabled):
                success = False

        return success

    def get_all_brightness(self) -> List[float]:
        """获取所有通道亮度"""
        return self.brightness_levels.copy()

    def get_all_enabled(self) -> List[bool]:
        """获取所有通道启用状态"""
        return self.channel_enabled.copy()

    def fade_channel(self, channel: int, start_brightness: float, end_brightness: float, duration: float) -> bool:
        """通道亮度渐变"""
        if not self.connected:
            return False

        if channel < 0 or channel >= self.channel_count:
            return False

        if duration <= 0:
            return self.set_brightness(channel, end_brightness)

        def fade_worker():
            steps = int(duration * 20)  # 20 steps per second
            step_delay = duration / steps
            step_size = (end_brightness - start_brightness) / steps

            for i in range(steps):
                if self.stop_fade.is_set():
                    break

                current_brightness = start_brightness + step_size * i
                self.set_brightness(channel, current_brightness)
                time.sleep(step_delay)

            # 设置最终值
            if not self.stop_fade.is_set():
                self.set_brightness(channel, end_brightness)

        # 停止之前的渐变
        self.stop_fade_effects()

        self.is_fading = True
        self.fade_thread = threading.Thread(target=fade_worker, daemon=True)
        self.fade_thread.start()

        return True

    def fade_all_channels(self, start_brightness: float, end_brightness: float, duration: float) -> bool:
        """所有通道亮度渐变"""
        if not self.connected:
            return False

        # 为每个通道创建渐变线程
        threads = []
        for i in range(self.channel_count):
            thread = threading.Thread(
                target=self._fade_channel_worker,
                args=(i, start_brightness, end_brightness, duration),
                daemon=True
            )
            threads.append(thread)

        # 停止之前的渐变
        self.stop_fade_effects()

        self.is_fading = True
        for thread in threads:
            thread.start()

        return True

    def create_pattern(self, pattern: List[Dict[str, Any]]) -> bool:
        """创建亮度模式"""
        if not self.connected:
            return False

        def pattern_worker():
            self.stop_fade.clear()

            while not self.stop_fade.is_set():
                for step in pattern:
                    if self.stop_fade.is_set():
                        break

                    if 'channel' in step:
                        # 单通道模式
                        channel = step['channel']
                        brightness = step['brightness']
                        duration = step.get('duration', 1.0)
                        self.set_brightness(channel, brightness)
                    else:
                        # 所有通道模式
                        brightness = step['brightness']
                        duration = step.get('duration', 1.0)
                        self.set_all_brightness(brightness)

                    time.sleep(duration)

        # 停止之前的模式
        self.stop_fade_effects()

        thread = threading.Thread(target=pattern_worker, daemon=True)
        thread.start()

        return True

    def stop_fade_effects(self) -> bool:
        """停止所有渐变效果"""
        try:
            self.stop_fade.set()
            self.is_fading = False

            if self.fade_thread and self.fade_thread.is_alive():
                self.fade_thread.join(timeout=0.5)

            return True
        except Exception as e:
            logger.error(f"Error stopping fade effects: {e}")
            return False

    def _fade_channel_worker(self, channel: int, start_brightness: float, end_brightness: float, duration: float):
        """单个通道渐变工作线程"""
        steps = int(duration * 20)
        step_delay = duration / steps
        step_size = (end_brightness - start_brightness) / steps

        for i in range(steps):
            if self.stop_fade.is_set():
                break

            current_brightness = start_brightness + step_size * i
            self.set_brightness(channel, current_brightness)
            time.sleep(step_delay)

        if not self.stop_fade.is_set():
            self.set_brightness(channel, end_brightness)

    def _notify_state_change(self, channel: int, property_name: str, old_value: Any, new_value: Any):
        """通知状态变化"""
        for callback in self.state_callbacks:
            try:
                callback({
                    'light_id': self.light_id,
                    'channel': channel,
                    'property': property_name,
                    'old_value': old_value,
                    'new_value': new_value,
                    'timestamp': time.time()
                })
            except Exception as e:
                logger.error(f"State callback error: {e}")

    def register_state_callback(self, callback) -> bool:
        """注册状态变化回调函数"""
        if callback not in self.state_callbacks:
            self.state_callbacks.append(callback)
            return True
        return False

    def unregister_state_callback(self, callback) -> bool:
        """取消注册状态变化回调函数"""
        if callback in self.state_callbacks:
            self.state_callbacks.remove(callback)
            return True
        return False