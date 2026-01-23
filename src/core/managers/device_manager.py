"""
设备管理器
支持设备注册、管理和运行时切换
"""

from typing import Dict, Any, Optional, List
from ..interfaces.hardware import IRobot, ICamera, ILight
from .device_registry import get_device_registry
from ..managers.log_manager import info, debug, warning, error


class DeviceManager:
    """设备管理器，支持运行时设备切换"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # 当前活跃的设备实例
        self.current_robot: Optional[IRobot] = None
        self.current_camera: Optional[ICamera] = None
        self.current_light: Optional[ILight] = None

        # 当前设备品牌
        self.current_robot_brand: Optional[str] = None
        self.current_camera_brand: Optional[str] = None
        self.current_light_brand: Optional[str] = None

        # 设备配置缓存
        self.robot_configs: Dict[str, Dict[str, Any]] = {}
        self.camera_configs: Dict[str, Dict[str, Any]] = {}
        self.light_configs: Dict[str, Dict[str, Any]] = {}

    def register_robot_config(self, brand: str, config: Dict[str, Any]):
        """注册机器人配置"""
        self.robot_configs[brand.lower()] = config
        info(f"Registered robot config for {brand}", "DEVICE_MANAGER")

    def register_camera_config(self, brand: str, config: Dict[str, Any]):
        """注册相机配置"""
        self.camera_configs[brand.lower()] = config
        info(f"Registered camera config for {brand}", "DEVICE_MANAGER")

    def register_light_config(self, brand: str, config: Dict[str, Any]):
        """注册光源配置"""
        self.light_configs[brand.lower()] = config
        info(f"Registered light config for {brand}", "DEVICE_MANAGER")

    def switch_robot(self, brand: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """切换机器人设备"""
        try:
            brand = brand.lower()

            # 如果已经有相同品牌的机器人，先断开
            if self.current_robot and self.current_robot_brand == brand:
                info(f"Robot {brand} is already active", "DEVICE_MANAGER")
                return True

            # 断开当前机器人
            if self.current_robot:
                info(f"Disconnecting current robot: {self.current_robot_brand}", "DEVICE_MANAGER")
                self.current_robot.disconnect()

            # 创建新的机器人实例
            new_robot = get_device_registry().create_robot(brand)
            if not new_robot:
                error(f"Failed to create robot {brand}", "DEVICE_MANAGER")
                return False

            # 获取配置
            robot_config = config or self.robot_configs.get(brand, {})
            if not robot_config:
                error(f"No config available for robot {brand}", "DEVICE_MANAGER")
                return False

            # 连接新机器人
            info(f"Connecting to robot {brand}", "DEVICE_MANAGER")
            if not new_robot.connect(robot_config):
                error(f"Failed to connect to robot {brand}", "DEVICE_MANAGER")
                return False

            # 切换成功
            if self.current_robot:
                self.current_robot.disconnect()

            self.current_robot = new_robot
            self.current_robot_brand = brand

            info(f"Successfully switched to robot {brand}", "DEVICE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to switch robot: {e}", "DEVICE_MANAGER")
            return False

    def switch_camera(self, brand: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """切换相机设备"""
        try:
            brand = brand.lower()

            # 如果已经有相同品牌的相机，先断开
            if self.current_camera and self.current_camera_brand == brand:
                info(f"Camera {brand} is already active", "DEVICE_MANAGER")
                return True

            # 断开当前相机
            if self.current_camera:
                info(f"Disconnecting current camera: {self.current_camera_brand}", "DEVICE_MANAGER")
                self.current_camera.stop_streaming()
                self.current_camera.disconnect()

            # 创建新的相机实例
            new_camera = get_device_registry().create_camera(brand)
            if not new_camera:
                error(f"Failed to create camera {brand}", "DEVICE_MANAGER")
                return False

            # 获取配置
            camera_config = config or self.camera_configs.get(brand, {})
            if not camera_config:
                error(f"No config available for camera {brand}", "DEVICE_MANAGER")
                return False

            # 连接新相机
            info(f"Connecting to camera {brand}", "DEVICE_MANAGER")
            if not new_camera.connect(camera_config):
                error(f"Failed to connect to camera {brand}", "DEVICE_MANAGER")
                return False

            # 切换成功
            if self.current_camera:
                self.current_camera.stop_streaming()
                self.current_camera.disconnect()

            self.current_camera = new_camera
            self.current_camera_brand = brand

            info(f"Successfully switched to camera {brand}", "DEVICE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to switch camera: {e}", "DEVICE_MANAGER")
            return False

    def switch_light(self, brand: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """切换光源设备"""
        try:
            brand = brand.lower()

            # 如果已经有相同品牌的光源，先断开
            if self.current_light and self.current_light_brand == brand:
                info(f"Light {brand} is already active", "DEVICE_MANAGER")
                return True

            # 断开当前光源
            if self.current_light:
                info(f"Disconnecting current light: {self.current_light_brand}", "DEVICE_MANAGER")
                self.current_light.disconnect()

            # 创建新的光源实例
            new_light = get_device_registry().create_light(brand)
            if not new_light:
                error(f"Failed to create light {brand}", "DEVICE_MANAGER")
                return False

            # 获取配置
            light_config = config or self.light_configs.get(brand, {})
            if not light_config:
                error(f"No config available for light {brand}", "DEVICE_MANAGER")
                return False

            # 连接新光源
            info(f"Connecting to light {brand}", "DEVICE_MANAGER")
            if not new_light.connect(light_config):
                error(f"Failed to connect to light {brand}", "DEVICE_MANAGER")
                return False

            # 切换成功
            if self.current_light:
                self.current_light.disconnect()

            self.current_light = new_light
            self.current_light_brand = brand

            info(f"Successfully switched to light {brand}", "DEVICE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to switch light: {e}", "DEVICE_MANAGER")
            return False

    def get_robot(self) -> Optional[IRobot]:
        """获取当前机器人实例"""
        return self.current_robot

    def get_camera(self) -> Optional[ICamera]:
        """获取当前相机实例"""
        return self.current_camera

    def get_light(self) -> Optional[ILight]:
        """获取当前光源实例"""
        return self.current_light

    def get_current_robot_brand(self) -> Optional[str]:
        """获取当前机器人品牌"""
        return self.current_robot_brand

    def get_current_camera_brand(self) -> Optional[str]:
        """获取当前相机品牌"""
        return self.current_camera_brand

    def get_current_light_brand(self) -> Optional[str]:
        """获取当前光源品牌"""
        return self.current_light_brand

    def get_available_robots(self) -> List[str]:
        """获取可用的机器人品牌"""
        return get_device_registry().get_available_robot_brands()

    def get_available_cameras(self) -> List[str]:
        """获取可用的相机品牌"""
        return get_device_registry().get_available_camera_brands()

    def get_available_lights(self) -> List[str]:
        """获取可用的光源品牌"""
        return get_device_registry().get_available_light_brands()

    def get_device_status(self) -> Dict[str, Any]:
        """获取所有设备状态"""
        status = {
            'robot': {
                'brand': self.current_robot_brand,
                'connected': self.current_robot.is_connected() if self.current_robot else False,
                'info': self.current_robot.get_info() if self.current_robot else None
            },
            'camera': {
                'brand': self.current_camera_brand,
                'connected': self.current_camera.is_connected() if self.current_camera else False,
                'info': self.current_camera.get_info() if self.current_camera else None
            },
            'light': {
                'brand': self.current_light_brand,
                'connected': self.current_light.is_connected() if self.current_light else False,
                'info': self.current_light.get_info() if self.current_light else None
            },
            'available': {
                'robots': self.get_available_robots(),
                'cameras': self.get_available_cameras(),
                'lights': self.get_available_lights()
            }
        }
        return status

    def disconnect_all(self) -> bool:
        """断开所有设备连接"""
        try:
            success = True

            if self.current_robot:
                success &= self.current_robot.disconnect()
                self.current_robot = None
                self.current_robot_brand = None

            if self.current_camera:
                self.current_camera.stop_streaming()
                success &= self.current_camera.disconnect()
                self.current_camera = None
                self.current_camera_brand = None

            if self.current_light:
                success &= self.current_light.disconnect()
                self.current_light = None
                self.current_light_brand = None

            info("All devices disconnected", "DEVICE_MANAGER")
            return success

        except Exception as e:
            error(f"Error disconnecting devices: {e}", "DEVICE_MANAGER")
            return False

    def initialize_from_config(self, config: Dict[str, Any]) -> bool:
        """从配置初始化设备"""
        try:
            success = True

            # 初始化机器人
            robot_config = config.get('robot', {})
            if robot_config:
                brand = robot_config.get('brand')
                if brand:
                    self.register_robot_config(brand, robot_config)
                    success &= self.switch_robot(brand)

            # 初始化相机
            camera_config = config.get('camera', {})
            if camera_config:
                brand = camera_config.get('brand')
                if brand:
                    self.register_camera_config(brand, camera_config)
                    success &= self.switch_camera(brand)

            # 初始化光源
            light_config = config.get('light', {})
            if light_config:
                brand = light_config.get('brand')
                if brand:
                    self.register_light_config(brand, light_config)
                    success &= self.switch_light(brand)

            return success

        except Exception as e:
            error(f"Failed to initialize from config: {e}", "DEVICE_MANAGER")
            return False