"""
机器人驱动工厂
根据配置创建对应的机器人驱动实例
"""

import importlib
import sys
from typing import Optional, Dict, Any
from ..interfaces.hardware import IRobot
from ..managers.log_manager import info, debug, warning, error


class RobotFactory:
    """机器人驱动工厂类"""

    @staticmethod
    def create_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """
        根据配置创建机器人驱动实例

        Args:
            config: 机器人配置字典

        Returns:
            机器人驱动实例，创建失败返回None
        """
        brand = config.get('brand', '').lower()
        connection_type = config.get('connection_type', '').lower()

        debug(f"Creating robot driver for brand: {brand}, connection: {connection_type}")

        try:
            # 首先处理模拟驱动
            if connection_type == 'simulation' or brand == 'simulation':
                debug("Creating simulation robot driver")
                return RobotFactory._create_simulation_robot(config)

            # 根据品牌创建对应的驱动
            if brand == 'yamaha':
                return RobotFactory._create_yamaha_robot(config)
            elif brand == 'universal':
                return RobotFactory._create_universal_robot(config)
            elif brand == 'fanuc':
                return RobotFactory._create_fanuc_robot(config)
            elif brand == 'abb':
                return RobotFactory._create_abb_robot(config)
            elif brand == 'elite':
                return RobotFactory._create_elite_robot(config)
            else:
                # 尝试通用机器人驱动
                warning(f"Unknown robot brand: {brand}, trying universal driver")
                return RobotFactory._create_universal_robot(config)

        except Exception as e:
            error(f"Failed to create robot driver: {e}")
            return None

    @staticmethod
    def _create_elite_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """创建Elite机器人驱动"""
        try:
            from drivers.robot.elite import EliteRobot
            robot = EliteRobot()
            debug("Elite robot driver created successfully")
            return robot
        except ImportError as e:
            error(f"Elite robot driver not available: {e}")
            return None
        except Exception as e:
            error(f"Failed to create Elite robot: {e}")
            return None

    @staticmethod
    def _create_simulation_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """创建模拟机器人驱动"""
        try:
            from drivers.robot.simulation import SimulationRobot
            robot = SimulationRobot()
            debug("Simulation robot driver created successfully")
            return robot
        except ImportError as e:
            error(f"Simulation robot driver not available: {e}")
            return None
        except Exception as e:
            error(f"Failed to create simulation robot: {e}")
            return None

    @staticmethod
    def _create_yamaha_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """创建Yamaha机器人驱动"""
        try:
            from drivers.robot.yamaha import YamahaRobot
            robot = YamahaRobot()
            debug("Yamaha robot driver created successfully")
            return robot
        except ImportError as e:
            error(f"Yamaha robot driver not available: {e}")
            return None
        except Exception as e:
            error(f"Failed to create Yamaha robot: {e}")
            return None

    @staticmethod
    def _create_universal_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """创建通用机器人驱动"""
        try:
            from drivers.robot.universal_robot import UniversalRobot
            robot = UniversalRobot()
            debug("Universal robot driver created successfully")
            return robot
        except ImportError as e:
            error(f"Universal robot driver not available: {e}")
            return None
        except Exception as e:
            error(f"Failed to create universal robot: {e}")
            return None

    @staticmethod
    def _create_fanuc_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """创建Fanuc机器人驱动"""
        try:
            from drivers.robot.fanuc import FanucRobot
            robot = FanucRobot()
            debug("Fanuc robot driver created successfully")
            return robot
        except ImportError as e:
            error(f"Fanuc robot driver not available: {e}")
            return None
        except Exception as e:
            error(f"Failed to create Fanuc robot: {e}")
            return None

    @staticmethod
    def _create_abb_robot(config: Dict[str, Any]) -> Optional[IRobot]:
        """创建ABB机器人驱动"""
        try:
            from drivers.robot.abb import ABBRobot
            robot = ABBRobot()
            debug("ABB robot driver created successfully")
            return robot
        except ImportError as e:
            error(f"ABB robot driver not available: {e}")
            return None
        except Exception as e:
            error(f"Failed to create ABB robot: {e}")
            return None

    @staticmethod
    def list_available_drivers() -> Dict[str, bool]:
        """
        列出所有可用的机器人驱动

        Returns:
            驱动可用性字典，key为驱动名称，value为是否可用
        """
        drivers = {}

        # 检查模拟驱动
        try:
            importlib.import_module('drivers.robot.simulation')
            drivers['simulation'] = True
        except ImportError:
            drivers['simulation'] = False

        # 检查各品牌驱动
        brand_modules = {
            'yamaha': 'drivers.robot.yamaha',
            'universal': 'drivers.robot.universal_robot',
            'fanuc': 'drivers.robot.fanuc',
            'abb': 'drivers.robot.abb'
        }

        for brand, module_name in brand_modules.items():
            try:
                importlib.import_module(module_name)
                drivers[brand] = True
            except ImportError:
                drivers[brand] = False

        return drivers

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        """
        验证机器人配置是否有效

        Args:
            config: 机器人配置

        Returns:
            配置是否有效
        """
        required_fields = ['id', 'name', 'brand', 'connection_type']

        for field in required_fields:
            if field not in config:
                warning(f"Missing required field in robot config: {field}")
                return False

        # 检查品牌是否支持
        brand = config.get('brand', '').lower()
        available_drivers = RobotFactory.list_available_drivers()

        if brand not in available_drivers or not available_drivers[brand]:
            error(f"Robot brand '{brand}' is not supported or driver not available")
            return False

        return True