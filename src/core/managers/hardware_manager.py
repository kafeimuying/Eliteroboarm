"""
硬件管理器
集成依赖注入容器的硬件设备管理
"""

from typing import Dict, Any, Type, Optional, List
from pathlib import Path

from ..container import Container
from .app_config import AppConfigManager
from .log_manager import LogManager
from .log_manager import info, debug, warning, error

# Import interfaces
from ..interfaces.hardware import IRobot, ICamera, ILight

# Import drivers
from drivers.robot import (
    YamahaRobot, UniversalRobot, KukaRobot, SimulationRobot
)
from drivers.camera import (
    HikvisionCamera, BaslerCamera, FlirCamera, SimulationCamera, DahengCamera
)
from drivers.light import DigitalLight, SimulationLight


class HardwareManager:
    """
    硬件管理器，集成DI容器的设备管理
    """

    def __init__(self, container: Container, config_manager: AppConfigManager, log_manager: LogManager):
        self.container = container
        self.config_manager = config_manager
        self.log_manager = log_manager

        # 注册到DI容器
        container.register("hardware_manager", self)

        # 驿件注册表（将被实际的驱动实例替代）
        self._robot_instances: Dict[str, IRobot] = {}
        self._camera_instances: Dict[str, ICamera] = {}
        self._light_instances: Dict[str, ILight] = {}

        # 配置
        self.hardware_config = {}

        self.log_manager.info("Hardware manager initialized", "HARDWARE_MANAGER")

    def initialize_from_config(self) -> bool:
        """
        从配置文件初始化硬件设备

        Returns:
            True if successful, False otherwise
        """
        try:
            self.hardware_config = self.config_manager.get_hardware_config()
            self.log_manager.info("Initializing hardware from configuration", "HARDWARE_MANAGER")

            # 注册驱动类到容器
            self._register_driver_classes()

            # 实例化并注册设备
            success = True

            # 初始化机器人
            success &= self._initialize_robots()

            # 初始化相机
            success &= self._initialize_cameras()

            # 初始化光源
            success &= self._initialize_lights()

            if success:
                self.log_manager.info("Hardware initialization completed", "HARDWARE_MANAGER")
            else:
                self.log_manager.warning("Hardware initialization had issues", "HARDWARE_MANAGER")

            return success

        except Exception as e:
            self.log_manager.error(f"Hardware initialization failed: {e}", "HARDWARE_MANAGER")
            return False

    def _register_driver_classes(self):
        """注册驱动类到DI容器"""
        try:
            # 注册机器人驱动类
            self.container.register("YamahaRobot", YamahaRobot)
            self.container.register("UniversalRobot", UniversalRobot)
            self.container.register("KukaRobot", KukaRobot)
            self.container.register("SimulationRobot", SimulationRobot)

            # 注册相机驱动类
            self.container.register("HikvisionCamera", HikvisionCamera)
            self.container.register("BaslerCamera", BaslerCamera)
            self.container.register("FlirCamera", FlirCamera)
            self.container.register("SimulationCamera", SimulationCamera)

            # 注册光源驱动类
            self.container.register("DigitalLight", DigitalLight)
            self.container.register("SimulationLight", SimulationLight)

            self.log_manager.info("Driver classes registered to container", "HARDWARE_MANAGER")

        except Exception as e:
            self.log_manager.error(f"Failed to register driver classes: {e}", "HARDWARE_MANAGER")

    def _initialize_robots(self) -> bool:
        """初始化机器人设备"""
        try:
            robots_config = self.hardware_config.get("robots", [])
            
            # Handle both list and dict formats
            if isinstance(robots_config, list):
                self.log_manager.info(f"Initializing {len(robots_config)} robot devices from list format", "HARDWARE_MANAGER")
                robots_dict = {robot.get('id'): robot for robot in robots_config}
            else:
                self.log_manager.info(f"Initializing {len(robots_config)} robot devices from dict format", "HARDWARE_MANAGER")
                robots_dict = robots_config

            for robot_id, robot_config in robots_dict.items():
                try:
                    # 获取驱动类 - 优先使用brand，fallback到type
                    driver_type = robot_config.get("brand", robot_config.get("type", "simulation"))
                    driver_class = self._get_robot_driver_class(driver_type)

                    if driver_class:
                        # 创建并配置机器人实例
                        robot = driver_class()
                        self.container.register(f"robot_{robot_id}", robot)
                        self._robot_instances[robot_id] = robot

                        self.log_manager.info(f"Initialized robot {robot_id} with driver {driver_class.__name__}", "HARDWARE_MANAGER")
                    else:
                        self.log_manager.warning(f"Unknown robot driver type: {driver_type} for robot {robot_id}", "HARDWARE_MANAGER")

                except Exception as e:
                    self.log_manager.error(f"Failed to initialize robot {robot_id}: {e}", "HARDWARE_MANAGER")

            return True

        except Exception as e:
            self.log_manager.error(f"Robot initialization failed: {e}", "HARDWARE_MANAGER")
            return False

    def _initialize_cameras(self) -> bool:
        """初始化相机设备"""
        try:
            cameras_config = self.hardware_config.get("cameras", [])
            
            # Handle both list and dict formats
            if isinstance(cameras_config, list):
                self.log_manager.info(f"Initializing {len(cameras_config)} camera devices from list format", "HARDWARE_MANAGER")
                cameras_dict = {camera.get('id'): camera for camera in cameras_config}
            else:
                self.log_manager.info(f"Initializing {len(cameras_config)} camera devices from dict format", "HARDWARE_MANAGER")
                cameras_dict = cameras_config

            for camera_id, camera_config in cameras_dict.items():
                try:
                    # 获取驱动类 - 优先使用brand，fallback到type
                    driver_type = camera_config.get("brand", camera_config.get("type", "simulation"))
                    driver_class = self._get_camera_driver_class(driver_type)

                    if driver_class:
                        # 创建并配置相机实例
                        camera = driver_class()
                        self.container.register(f"camera_{camera_id}", camera)
                        self._camera_instances[camera_id] = camera

                        self.log_manager.info(f"Initialized camera {camera_id} with driver {driver_class.__name__}", "HARDWARE_MANAGER")
                    else:
                        self.log_manager.warning(f"Unknown camera driver type: {driver_type} for camera {camera_id}", "HARDWARE_MANAGER")

                except Exception as e:
                    self.log_manager.error(f"Failed to initialize camera {camera_id}: {e}", "HARDWARE_MANAGER")

            return True

        except Exception as e:
            self.log_manager.error(f"Camera initialization failed: {e}", "HARDWARE_MANAGER")
            return False

    def _initialize_lights(self) -> bool:
        """初始化光源设备"""
        try:
            lights_config = self.hardware_config.get("lights", [])
            
            # Handle both list and dict formats
            if isinstance(lights_config, list):
                self.log_manager.info(f"Initializing {len(lights_config)} light devices from list format", "HARDWARE_MANAGER")
                lights_dict = {light.get('id'): light for light in lights_config}
            else:
                self.log_manager.info(f"Initializing {len(lights_config)} light devices from dict format", "HARDWARE_MANAGER")
                lights_dict = lights_config

            for light_id, light_config in lights_dict.items():
                try:
                    # 获取驱动类 - 优先使用brand，fallback到type
                    driver_type = light_config.get("brand", light_config.get("type", "simulation"))
                    driver_class = self._get_light_driver_class(driver_type)

                    if driver_class:
                        # 创建并配置光源实例
                        light = driver_class()
                        self.container.register(f"light_{light_id}", light)
                        self._light_instances[light_id] = light

                        self.log_manager.info(f"Initialized light {light_id} with driver {driver_class.__name__}", "HARDWARE_MANAGER")
                    else:
                        self.log_manager.warning(f"Unknown light driver type: {driver_type} for light {light_id}", "HARDWARE_MANAGER")

                except Exception as e:
                    self.log_manager.error(f"Failed to initialize light {light_id}: {e}", "HARDWARE_MANAGER")

            return True

        except Exception as e:
            self.log_manager.error(f"Light initialization failed: {e}", "HARDWARE_MANAGER")
            return False

    def _get_robot_driver_class(self, driver_type: str) -> Optional[Type[IRobot]]:
        """获取机器人驱动类"""
        driver_classes = {
            "yamaha": YamahaRobot,
            "universal_robots": UniversalRobot,
            "ur": UniversalRobot,
            "kuka": KukaRobot,
            "simulation": SimulationRobot,
        }
        return driver_classes.get(driver_type.lower())

    def _get_camera_driver_class(self, driver_type: str) -> Optional[Type[ICamera]]:
        """获取相机驱动类"""
        driver_classes = {
            "hikvision": HikvisionCamera,
            "basler": BaslerCamera,
            "flir": FlirCamera,
            "daheng": DahengCamera,
            "galaxy": DahengCamera,
            "simulation": SimulationCamera,
        }
        return driver_classes.get(driver_type.lower())

    def _get_light_driver_class(self, driver_type: str) -> Optional[Type[ILight]]:
        """获取光源驱动类"""
        driver_classes = {
            "digital": DigitalLight,
            "simulation": SimulationLight,
        }
        return driver_classes.get(driver_type.lower())

    def get_robot(self, robot_id: str) -> Optional[IRobot]:
        """获取机器人实例"""
        return self._robot_instances.get(robot_id)

    def get_camera(self, camera_id: str) -> Optional[ICamera]:
        """获取相机实例"""
        return self._camera_instances.get(camera_id)

    def get_light(self, light_id: str) -> Optional[ILight]:
        """获取光源实例"""
        return self._light_instances.get(light_id)

    def list_robots(self) -> Dict[str, IRobot]:
        """获取所有机器人实例"""
        return self._robot_instances.copy()

    def list_cameras(self) -> Dict[str, ICamera]:
        """获取所有相机实例"""
        return self._camera_instances.copy()

    def list_lights(self) -> Dict[str, ILight]:
        """获取所有光源实例"""
        return self._light_instances.copy()

    def reload_config(self) -> bool:
        """重新加载配置"""
        try:
            self.log_manager.info("Reloading hardware configuration", "HARDWARE_MANAGER")

            # 重新加载配置
            self.config_manager.clear_cache()
            self.hardware_config = self.config_manager.get_hardware_config()

            # 重新初始化
            return self.initialize_from_config()

        except Exception as e:
            self.log_manager.error(f"Failed to reload configuration: {e}", "HARDWARE_MANAGER")
            return False

    def get_device_info(self) -> Dict[str, Any]:
        """获取设备信息摘要"""
        return {
            "robots_count": len(self._robot_instances),
            "cameras_count": len(self._camera_instances),
            "lights_count": len(self._light_instances),
            "total_devices": len(self._robot_instances) + len(self._camera_instances) + len(self._light_instances),
            "config_loaded": bool(self.hardware_config)
        }