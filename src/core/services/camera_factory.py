"""
相机工厂类
根据配置创建正确的相机驱动实例
"""

from typing import Dict, Any, Optional
from ..interfaces.hardware import ICamera
from ..managers.log_manager import debug, info, warning, error


class CameraFactory:
    """相机工厂类"""

    @staticmethod
    def create_camera(config: Dict[str, Any]) -> Optional[ICamera]:
        """
        根据配置创建相机驱动实例

        Args:
            config: 相机配置字典

        Returns:
            相机驱动实例，如果创建失败返回None
        """
        try:
            brand = config.get('brand', '').lower()
            connection_type = config.get('connection_type', '').lower()

            camera_name = config.get('name', 'Unknown Camera')
            info(f"Creating camera driver for {camera_name}: brand={brand}, connection_type={connection_type}", "CAMERA_FACTORY")

            # 检查是否为模拟相机
            if (config.get('is_simulation', False) or
                connection_type == 'simulation' or
                brand == 'simulation'):

                debug(f"Creating simulation camera for {camera_name}", "CAMERA_FACTORY")
                try:
                    from drivers.camera import SimulationCamera
                    return SimulationCamera(camera_id=config.get('id', 'simulation_camera'))
                except ImportError as e:
                    error(f"Failed to import SimulationCamera: {e}", "CAMERA_FACTORY")
                    return None

            # 真实相机驱动
            elif connection_type == 'network' or connection_type == 'tcp':
                if brand == 'hikvision':
                    debug(f"Creating Hikvision camera for {camera_name}", "CAMERA_FACTORY")
                    try:
                        from drivers.camera import HikvisionCamera
                        return HikvisionCamera()
                    except ImportError as e:
                        error(f"Failed to import HikvisionCamera: {e}", "CAMERA_FACTORY")
                        return None
                elif brand == 'basler':
                    debug(f"Creating Basler camera for {camera_name}", "CAMERA_FACTORY")
                    try:
                        from drivers.camera import BaslerCamera
                        return BaslerCamera()
                    except ImportError as e:
                        error(f"Failed to import BaslerCamera: {e}", "CAMERA_FACTORY")
                        return None
                elif brand == 'flir':
                    debug(f"Creating FLIR camera for {camera_name}", "CAMERA_FACTORY")
                    try:
                        from drivers.camera import FlirCamera
                        return FlirCamera()
                    except ImportError as e:
                        error(f"Failed to import FlirCamera: {e}", "CAMERA_FACTORY")
                        return None
                elif brand == 'daheng' or brand == 'galaxy':
                    debug(f"Creating Daheng camera for {camera_name}", "CAMERA_FACTORY")
                    try:
                        from drivers.camera import DahengCamera
                        return DahengCamera()
                    except ImportError as e:
                        error(f"Failed to import DahengCamera: {e}", "CAMERA_FACTORY")
                        return None
                else:
                    warning(f"Unsupported camera brand: {brand}", "CAMERA_FACTORY")
                    return None

            elif connection_type == 'rtsp':
                # RTSP相机（通用）
                debug(f"Creating RTSP camera for {camera_name}", "CAMERA_FACTORY")
                # TODO: 实现RTSP相机
                warning(f"RTSP camera not yet implemented: {camera_name}", "CAMERA_FACTORY")
                return None

            elif connection_type == 'usb':
                # USB相机
                debug(f"Creating USB camera for {camera_name}", "CAMERA_FACTORY")
                # TODO: 实现USB相机
                warning(f"USB camera not yet implemented: {camera_name}", "CAMERA_FACTORY")
                return None

            else:
                warning(f"Unsupported connection type: {connection_type} for camera {camera_name}", "CAMERA_FACTORY")
                return None

        except Exception as e:
            error(f"Failed to create camera for {config.get('name', 'Unknown')}: {e}", "CAMERA_FACTORY")
            return None

    @staticmethod
    def get_supported_brands() -> Dict[str, list]:
        """获取支持的相机品牌和连接类型"""
        return {
            'simulation': ['simulation'],
            'hikvision': ['network', 'tcp'],
            'basler': ['network', 'tcp'],
            'flir': ['network', 'tcp'],
            'generic': ['rtsp', 'usb']
        }

    @staticmethod
    def is_config_supported(config: Dict[str, Any]) -> bool:
        """检查配置是否支持"""
        brand = config.get('brand', '').lower()
        connection_type = config.get('connection_type', '').lower()

        supported = CameraFactory.get_supported_brands()

        # 检查模拟相机
        if (config.get('is_simulation', False) or
            connection_type == 'simulation' or
            brand == 'simulation'):
            return True

        # 检查真实相机
        if brand in supported:
            return connection_type in supported[brand]

        return False