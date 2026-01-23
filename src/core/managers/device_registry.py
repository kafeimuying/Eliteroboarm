"""
设备注册器
支持设备注册和运行时切换功能
"""

from typing import Dict, Type, Any, Optional, List
from ..interfaces.hardware import IRobot, ICamera, ILight  # 使用相对导入
from .log_manager import info, debug, warning, error

# 延迟导入驱动，避免启动时卡顿
def _safe_import_driver(module_path: str, class_name: str):
    """安全导入驱动，失败时返回None"""
    try:
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name, None)
    except ImportError:
        return None
    except Exception:
        return None

# 预定义驱动类（实际类在需要时再导入）
_ROBOT_DRIVERS = {
    "yamaha": ("drivers.robot", "YamahaRobot"),
    "universal_robots": ("drivers.robot", "UniversalRobot"),
    "ur": ("drivers.robot", "UniversalRobot"),
    "kuka": ("drivers.robot", "KukaRobot"),
    "simulation": ("drivers.robot", "SimulationRobot")
}

_CAMERA_DRIVERS = {
    "hikvision": ("drivers.camera", "HikvisionCamera"),
    "basler": ("drivers.camera", "BaslerCamera"),
    "flir": ("drivers.camera", "FlirCamera"),
    "simulation": ("drivers.camera", "SimulationCamera")
}

_LIGHT_DRIVERS = {
    "digital": ("drivers.light", "DigitalLight"),
    "simulation": ("drivers.light", "SimulationLight")
}



class DeviceRegistry:
    """设备注册器，管理设备类型和实现类的映射"""

    def __init__(self):
        self._robot_registry: Dict[str, Type[IRobot]] = {}
        self._camera_registry: Dict[str, Type[ICamera]] = {}
        self._light_registry: Dict[str, Type[ILight]] = {}

        # 自动注册内置驱动
        self._register_builtin_drivers()

    def _register_builtin_drivers(self):
        """注册内置驱动（基于配置决定是否注册相机驱动）"""
        # 注册机器人驱动
        for brand, (module_path, class_name) in _ROBOT_DRIVERS.items():
            driver_class = _safe_import_driver(module_path, class_name)
            if driver_class:
                self.register_robot_driver(brand, driver_class)

        # 检查是否应该注册相机驱动
        if self._should_register_camera_drivers():
            for brand, (module_path, class_name) in _CAMERA_DRIVERS.items():
                driver_class = _safe_import_driver(module_path, class_name)
                if driver_class:
                    self.register_camera_driver(brand, driver_class)

        # 注册光源驱动
        for brand, (module_path, class_name) in _LIGHT_DRIVERS.items():
            driver_class = _safe_import_driver(module_path, class_name)
            if driver_class:
                self.register_light_driver(brand, driver_class)

    def _should_register_camera_drivers(self) -> bool:
        """检查是否应该注册相机驱动（基于配置）"""
        try:
            from .app_config import AppConfigManager
            config_manager = AppConfigManager()
            return config_manager.is_camera_driver_check_enabled()
        except Exception:
            # 如果配置不可用，默认不注册相机驱动以避免卡顿
            return False

    def register_robot_driver(self, brand: str, driver_class: Type[IRobot]):
        """注册机器人驱动"""
        if not issubclass(driver_class, IRobot):
            raise ValueError(f"Driver {driver_class.__name__} must implement IRobot interface")

        self._robot_registry[brand.lower()] = driver_class
        info(f"Registered robot driver: {brand} -> {driver_class.__name__}", "DEVICE_REGISTRY")

    def register_camera_driver(self, brand: str, driver_class: Type[ICamera]):
        """注册相机驱动"""
        if not issubclass(driver_class, ICamera):
            raise ValueError(f"Driver {driver_class.__name__} must implement ICamera interface")

        self._camera_registry[brand.lower()] = driver_class
        info(f"Registered camera driver: {brand} -> {driver_class.__name__}", "DEVICE_REGISTRY")

    def register_light_driver(self, brand: str, driver_class: Type[ILight]):
        """注册光源驱动"""
        if not issubclass(driver_class, ILight):
            raise ValueError(f"Driver {driver_class.__name__} must implement ILight interface")

        self._light_registry[brand.lower()] = driver_class
        info(f"Registered light driver: {brand} -> {driver_class.__name__}", "DEVICE_REGISTRY")

    def create_robot(self, brand: str) -> Optional[IRobot]:
        """创建机器人实例"""
        brand = brand.lower()
        if brand not in self._robot_registry:
            error(f"No robot driver registered for brand: {brand}", "DEVICE_REGISTRY")
            return None

        try:
            driver_class = self._robot_registry[brand]
            return driver_class()
        except Exception as e:
            error(f"Failed to create robot {brand}: {e}", "DEVICE_REGISTRY")
            return None

    def create_camera(self, brand: str) -> Optional[ICamera]:
        """创建相机实例"""
        brand = brand.lower()
        if brand not in self._camera_registry:
            error(f"No camera driver registered for brand: {brand}", "DEVICE_REGISTRY")
            return None

        try:
            driver_class = self._camera_registry[brand]
            return driver_class()
        except Exception as e:
            error(f"Failed to create camera {brand}: {e}", "DEVICE_REGISTRY")
            return None

    def create_light(self, brand: str) -> Optional[ILight]:
        """创建光源实例"""
        brand = brand.lower()
        if brand not in self._light_registry:
            error(f"No light driver registered for brand: {brand}", "DEVICE_REGISTRY")
            return None

        try:
            driver_class = self._light_registry[brand]
            return driver_class()
        except Exception as e:
            error(f"Failed to create light {brand}: {e}", "DEVICE_REGISTRY")
            return None

    def create_device(self, hardware_type: str, brand: str) -> Optional[Any]:
        """创建设备实例（统一接口）"""
        hardware_type = hardware_type.lower()
        brand = brand.lower()

        try:
            if hardware_type == 'robot':
                return self.create_robot(brand)
            elif hardware_type == 'camera':
                return self.create_camera(brand)
            elif hardware_type == 'light':
                return self.create_light(brand)
            else:
                error(f"Unknown hardware type: {hardware_type}", "DEVICE_REGISTRY")
                return None
        except Exception as e:
            error(f"Failed to create device {hardware_type}/{brand}: {e}", "DEVICE_REGISTRY")
            return None

    def create_simulation_device(self, hardware_type: str) -> Optional[Any]:
        """创建模拟设备实例"""
        try:
            if hardware_type.lower() == 'robot':
                # 创建模拟机器人
                from drivers.robot.simulation import SimulationRobot
                return SimulationRobot()
            elif hardware_type.lower() == 'camera':
                # 创建模拟相机
                from drivers.camera.simulation import SimulationCamera
                return SimulationCamera()
            elif hardware_type.lower() == 'light':
                # 创建模拟光源
                from drivers.light.simulation import SimulationLight
                return SimulationLight()
            else:
                error(f"Unknown hardware type for simulation: {hardware_type}", "DEVICE_REGISTRY")
                return None
        except Exception as e:
            error(f"Failed to create simulation device {hardware_type}: {e}", "DEVICE_REGISTRY")
            return None

    def get_available_robot_brands(self) -> List[str]:
        """获取可用的机器人品牌列表"""
        return list(self._robot_registry.keys())

    def get_available_camera_brands(self) -> List[str]:
        """获取可用的相机品牌列表"""
        return list(self._camera_registry.keys())

    def get_available_light_brands(self) -> List[str]:
        """获取可用的光源品牌列表"""
        return list(self._light_registry.keys())

    def get_robot_brand_info(self) -> Dict[str, Dict[str, Any]]:
        """获取机器人品牌信息"""
        return {
            'yamaha': {
                'name': 'Yamaha',
                'models': ['YRC1000', 'YRC1000micro', 'YRC1000u'],
                'connection_types': ['tcp'],
                'description': '日本山洋电机，工业级SCARA和垂直关节机器人'
            },
            'universal_robots': {
                'name': 'Universal Robots',
                'models': ['UR3', 'UR5', 'UR10', 'UR16e'],
                'connection_types': ['tcp'],
                'description': '丹麦优傲机器人，协作型六轴机械臂'
            },
            'ur': {
                'name': 'Universal Robots (UR)',
                'models': ['UR3', 'UR5', 'UR10', 'UR16e'],
                'connection_types': ['tcp'],
                'description': '丹麦优傲机器人，协作型六轴机械臂（简称）'
            },
            'kuka': {
                'name': 'KUKA',
                'models': ['KR AGILUS', 'KR QUANTEC', 'LBR iiwa', 'KR DELTA'],
                'connection_types': ['tcp'],
                'description': '德国库卡，工业级六轴机器人和协作机器人'
            },
            'simulation': {
                'name': 'Simulation',
                'models': ['SIM-001', 'SIM-002', 'SIM-003'],
                'connection_types': ['simulation'],
                'description': '模拟设备，用于测试和演示'
            }
        }

    def get_camera_brand_info(self) -> Dict[str, Dict[str, Any]]:
        """获取相机品牌信息"""
        return {
            'hikvision': {
                'name': 'Hikvision',
                'models': ['DS-2CD', 'DS-2DE', 'DS-2DF'],
                'connection_types': ['rtsp'],
                'description': '海康威视，中国领先的视频监控设备制造商'
            },
            'basler': {
                'name': 'Basler',
                'models': ['ace', 'dart', 'pulse', 'racer'],
                'connection_types': ['usb', 'tcp'],
                'description': '德国巴斯勒，工业视觉相机专家'
            },
            'flir': {
                'name': 'FLIR',
                'models': ['Blackfly S', 'Chameleon', 'Flea3', 'Oryx'],
                'connection_types': ['usb', 'tcp'],
                'description': '美国菲力尔，热成像和工业相机领导者'
            },
            'simulation': {
                'name': 'Simulation',
                'models': ['SIM-CAM-001', 'SIM-CAM-002'],
                'connection_types': ['simulation'],
                'description': '模拟相机，用于测试和演示图像处理功能'
            }
        }

    def get_connection_type_info(self) -> Dict[str, Dict[str, Any]]:
        """获取连接类型信息"""
        return {
            'simulation': {
                'name': 'Simulation',
                'description': '模拟连接，用于测试和演示，无需真实硬件',
                'parameters': [],
                'suitable_for': ['机器人', '相机', '光源', '所有模拟设备']
            },
            'tcp': {
                'name': 'TCP/IP',
                'description': '网络连接，支持远程控制和实时通信',
                'parameters': ['ip', 'port', 'timeout'],
                'suitable_for': ['机器人', '网络相机', '光源控制器']
            },
            'rtsp': {
                'name': 'RTSP',
                'description': '实时流媒体协议，用于视频传输',
                'parameters': ['rtsp_url', 'username', 'password'],
                'suitable_for': ['网络相机']
            },
            'serial': {
                'name': 'Serial (RS232/485)',
                'description': '串口通信，适用于工业设备控制',
                'parameters': ['port', 'baudrate', 'data_bits', 'stop_bits', 'parity'],
                'suitable_for': ['PLC', '传感器', '控制器']
            },
            'usb': {
                'name': 'USB',
                'description': '通用串行总线，用于设备直接连接',
                'parameters': ['device_id', 'vendor_id', 'product_id'],
                'suitable_for': ['USB相机', '传感器', '控制设备']
            }
        }

    def get_supported_brands_for_hardware_type(self, hardware_type: str) -> Dict[str, Any]:
        """根据硬件类型获取支持的品牌"""
        if hardware_type.lower() == 'robot':
            return self.get_robot_brand_info()
        elif hardware_type.lower() == 'camera':
            return self.get_camera_brand_info()
        elif hardware_type.lower() == 'light':
            return {'digital': {
                'name': 'Digital Light',
                'models': ['Generic', 'Arduino', 'ESP32'],
                'connection_types': ['tcp', 'serial'],
                'description': '数字光源控制器'
            }}
        else:
            return {}

    def get_connection_types_for_brand(self, hardware_type: str, brand: str) -> List[str]:
        """获取指定品牌支持的连接类型"""
        brand_info = self.get_supported_brands_for_hardware_type(hardware_type)
        if brand.lower() in brand_info:
            return brand_info[brand.lower()]['connection_types']
        return []

    def recommend_connection_type(self, hardware_type: str, brand: str) -> Optional[str]:
        """推荐连接类型"""
        connection_types = self.get_connection_types_for_brand(hardware_type, brand)
        if not connection_types:
            return None

        # 如果是模拟品牌，推荐模拟连接
        if brand.lower() == 'simulation':
            return 'simulation'

        # 根据硬件类型和品牌推荐最佳连接方式
        if hardware_type.lower() == 'robot':
            return 'tcp'  # 机器人通常使用TCP连接
        elif hardware_type.lower() == 'camera':
            if brand.lower() == 'hikvision':
                return 'rtsp'  # 海康威视相机推荐RTSP
            else:
                return 'usb' if 'usb' in connection_types else 'tcp'
        elif hardware_type.lower() == 'light':
            return 'tcp'  # 光源控制器推荐TCP
        else:
            return connection_types[0] if connection_types else None

    def unregister_robot_driver(self, brand: str):
        """注销机器人驱动"""
        brand = brand.lower()
        if brand in self._robot_registry:
            del self._robot_registry[brand]
            info(f"Unregistered robot driver: {brand}", "DEVICE_REGISTRY")

    def unregister_camera_driver(self, brand: str):
        """注销相机驱动"""
        brand = brand.lower()
        if brand in self._camera_registry:
            del self._camera_registry[brand]
            info(f"Unregistered camera driver: {brand}", "DEVICE_REGISTRY")

    def unregister_light_driver(self, brand: str):
        """注销光源驱动"""
        brand = brand.lower()
        if brand in self._light_registry:
            del self._light_registry[brand]
            info(f"Unregistered light driver: {brand}", "DEVICE_REGISTRY")


# 延迟初始化的全局设备注册器实例
_device_registry = None

def get_device_registry() -> DeviceRegistry:
    """获取全局设备注册器实例（延迟初始化）"""
    global _device_registry
    if _device_registry is None:
        _device_registry = DeviceRegistry()
    return _device_registry

def get_device_registry_instance() -> DeviceRegistry:
    """获取设备注册器实例的别名，保持向后兼容"""
    return get_device_registry()