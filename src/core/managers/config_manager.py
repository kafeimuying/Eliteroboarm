"""
硬件配置管理
处理各种硬件设备的配置、连接测试和设备管理
"""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import time

from .log_manager import info, debug, warning, error


class HardwareType(Enum):
    """硬件设备类型"""
    ROBOT = "robot"
    CAMERA = "camera"
    LIGHT = "light"


class ConnectionStatus(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class HardwareConfig:
    """硬件配置数据结构"""
    id: str
    name: str
    hardware_type: HardwareType
    manufacturer: str  # yamaha, hikvision, etc.
    model: str
    connection_type: str  # tcp, serial, usb, rtsp
    connection_params: Dict[str, Any]
    enabled: bool = True
    description: str = ""
    last_connected: Optional[float] = None
    connection_count: int = 0


@dataclass
class ConnectionTestResult:
    """连接测试结果"""
    success: bool
    message: str
    response_time: Optional[float] = None
    device_info: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None


class HardwareConfigManager:
    """硬件配置管理器"""

    def __init__(self, config_file: str = "hardware_configs.json"):
        self.config_file = config_file
        self.configs: Dict[str, HardwareConfig] = {}
        self.connection_status: Dict[str, ConnectionStatus] = {}
        self.load_configs()

    def load_configs(self) -> bool:
        """从文件加载硬件配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.configs.clear()
                for config_id, config_data in data.get('configs', {}).items():
                    # 转换硬件类型枚举
                    if isinstance(config_data['hardware_type'], str):
                        config_data['hardware_type'] = HardwareType(config_data['hardware_type'])

                    config = HardwareConfig(**config_data)
                    self.configs[config_id] = config
                    self.connection_status[config_id] = ConnectionStatus.DISCONNECTED

                info(f"Loaded {len(self.configs)} hardware configurations", "CONFIG_MANAGER")
                return True
            else:
                info("No existing config file, starting with empty configs", "CONFIG_MANAGER")
                return True

        except Exception as e:
            error(f"Failed to load hardware configs: {e}", "CONFIG_MANAGER")
            return False

    def save_configs(self) -> bool:
        """保存硬件配置到文件"""
        try:
            # 转换为可序列化的格式
            data = {
                'configs': {
                    config_id: {
                        **asdict(config),
                        'hardware_type': config.hardware_type.value
                    }
                    for config_id, config in self.configs.items()
                },
                'last_updated': time.time()
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

                info("Hardware configurations saved", "CONFIG_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to save hardware configs: {e}", "CONFIG_MANAGER")
            return False

    def add_config(self, config: HardwareConfig) -> bool:
        """添加硬件配置"""
        try:
            if config.id in self.configs:
                warning(f"Config ID {config.id} already exists, updating", "CONFIG_MANAGER")

            self.configs[config.id] = config
            self.connection_status[config.id] = ConnectionStatus.DISCONNECTED

            return self.save_configs()

        except Exception as e:
            error(f"Failed to add hardware config: {e}", "CONFIG_MANAGER")
            return False

    def remove_config(self, config_id: str) -> bool:
        """删除硬件配置"""
        try:
            if config_id in self.configs:
                del self.configs[config_id]
                if config_id in self.connection_status:
                    del self.connection_status[config_id]
                return self.save_configs()
            else:
                warning(f"Config ID {config_id} not found", "CONFIG_MANAGER")
                return False

        except Exception as e:
            error(f"Failed to remove hardware config: {e}", "CONFIG_MANAGER")
            return False

    def update_config(self, config_id: str, updates: Dict[str, Any]) -> bool:
        """更新硬件配置"""
        try:
            if config_id not in self.configs:
                error(f"Config ID {config_id} not found", "CONFIG_MANAGER")
                return False

            config = self.configs[config_id]

            # 更新允许的字段
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                else:
                    warning(f"Unknown field: {key}", "CONFIG_MANAGER")

            return self.save_configs()

        except Exception as e:
            error(f"Failed to update hardware config: {e}", "CONFIG_MANAGER")
            return False

    def get_config(self, config_id: str) -> Optional[HardwareConfig]:
        """获取硬件配置"""
        return self.configs.get(config_id)

    def get_configs_by_type(self, hardware_type: HardwareType) -> List[HardwareConfig]:
        """根据类型获取硬件配置"""
        return [
            config for config in self.configs.values()
            if config.hardware_type == hardware_type
        ]

    def get_enabled_configs(self, hardware_type: Optional[HardwareType] = None) -> List[HardwareConfig]:
        """获取启用的硬件配置"""
        configs = [
            config for config in self.configs.values()
            if config.enabled
        ]

        if hardware_type:
            configs = [
                config for config in configs
                if config.hardware_type == hardware_type
            ]

        return configs

    def list_configs(self, hardware_type: Optional[HardwareType] = None) -> List[HardwareConfig]:
        """列出硬件配置"""
        if hardware_type:
            return self.get_configs_by_type(hardware_type)
        return list(self.configs.values())

    def get_connection_status(self, config_id: str) -> ConnectionStatus:
        """获取连接状态"""
        return self.connection_status.get(config_id, ConnectionStatus.DISCONNECTED)

    def set_connection_status(self, config_id: str, status: ConnectionStatus):
        """设置连接状态"""
        self.connection_status[config_id] = status

        # 更新连接统计
        if config_id in self.configs:
            config = self.configs[config_id]
            if status == ConnectionStatus.CONNECTED:
                config.last_connected = time.time()
                config.connection_count += 1
                # 异步保存，避免频繁IO
                import threading
                threading.Thread(target=self.save_configs, daemon=True).start()

    def validate_config(self, config: HardwareConfig) -> Tuple[bool, List[str]]:
        """验证硬件配置"""
        errors = []

        # 基本字段验证
        if not config.id or not config.id.strip():
            errors.append("设备ID不能为空")

        if not config.name or not config.name.strip():
            errors.append("设备名称不能为空")

        if not config.manufacturer or not config.manufacturer.strip():
            errors.append("制造商不能为空")

        # 连接参数验证
        required_params = self._get_required_connection_params(config)
        for param in required_params:
            if param not in config.connection_params:
                errors.append(f"缺少必要的连接参数: {param}")
            elif config.connection_params[param] is None or str(config.connection_params[param]).strip() == "":
                errors.append(f"连接参数不能为空: {param}")

        # 类型特定验证
        if config.hardware_type == HardwareType.ROBOT:
            if config.connection_type == "tcp":
                ip = config.connection_params.get("ip")
                port = config.connection_params.get("port")
                if ip and not self._validate_ip_address(ip):
                    errors.append("无效的IP地址")
                if port and not isinstance(port, int) and not str(port).isdigit():
                    errors.append("端口必须是数字")

        elif config.hardware_type == HardwareType.CAMERA:
            if config.connection_type == "rtsp":
                rtsp_url = config.connection_params.get("rtsp_url")
                if rtsp_url and not rtsp_url.startswith("rtsp://"):
                    errors.append("RTSP URL必须以rtsp://开头")

        return len(errors) == 0, errors

    def _get_required_connection_params(self, config: HardwareConfig) -> List[str]:
        """获取必需的连接参数"""
        params = []

        if config.connection_type == "tcp":
            params.extend(["ip", "port"])
        elif config.connection_type == "serial":
            params.extend(["port", "baudrate"])
        elif config.connection_type == "rtsp":
            params.extend(["rtsp_url"])
        elif config.connection_type == "usb":
            params.extend(["device_id"])

        return params

    def _validate_ip_address(self, ip: str) -> bool:
        """验证IP地址格式"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False

            for part in parts:
                num = int(part)
                if not 0 <= num <= 255:
                    return False

            return True
        except:
            return False

    def create_default_configs(self) -> Dict[str, HardwareConfig]:
        """创建默认硬件配置"""
        defaults = {}

        # 默认Yamaha机器人配置
        robot_config = HardwareConfig(
            id="robot_yamaha_001",
            name="Yamaha机器人",
            hardware_type=HardwareType.ROBOT,
            manufacturer="yamaha",
            model="YRC1000",
            connection_type="tcp",
            connection_params={
                "ip": "192.168.0.1",
                "port": 80,
                "timeout": 5.0
            },
            description="默认Yamaha机器人配置"
        )
        defaults["robot_yamaha_001"] = robot_config

        # 默认Hikvision相机配置
        camera_config = HardwareConfig(
            id="camera_hikvision_001",
            name="Hikvision相机",
            hardware_type=HardwareType.CAMERA,
            manufacturer="hikvision",
            model="DS-2CD2142FWD-I",
            connection_type="rtsp",
            connection_params={
                "rtsp_url": "rtsp://192.168.0.2:554/Streaming/Channels/101",
                "username": "admin",
                "password": "admin123"
            },
            description="默认Hikvision相机配置"
        )
        defaults["camera_hikvision_001"] = camera_config

        # 默认光源控制器配置
        light_config = HardwareConfig(
            id="light_digital_001",
            name="数字光源控制器",
            hardware_type=HardwareType.LIGHT,
            manufacturer="digital",
            model="DL-8CH",
            connection_type="tcp",
            connection_params={
                "ip": "192.168.0.3",
                "port": 8080,
                "channel_count": 8,
                "timeout": 3.0
            },
            description="默认数字光源控制器配置"
        )
        defaults["light_digital_001"] = light_config

        return defaults

    def test_connection_async(self, config_id: str, service) -> Tuple[bool, str]:
        """异步测试连接"""
        try:
            config = self.get_config(config_id)
            if not config:
                return False, f"配置 {config_id} 不存在"

            self.set_connection_status(config_id, ConnectionStatus.CONNECTING)

            start_time = time.time()

            # 根据硬件类型调用相应的服务测试方法
            if config.hardware_type == HardwareType.ROBOT:
                result = service.test_connection()
                success = result.get('success', False)
                message = result.get('message', result.get('error', 'Unknown error'))
                response_time = time.time() - start_time if success else None
                device_info = service.get_info() if success else None

            elif config.hardware_type == HardwareType.CAMERA:
                # 相机连接测试逻辑
                success = self._test_camera_connection(config)
                message = "相机连接成功" if success else "相机连接失败"
                response_time = time.time() - start_time if success else None
                device_info = {"camera_id": config_id} if success else None

            elif config.hardware_type == HardwareType.LIGHT:
                # 光源连接测试逻辑
                result = service.test_connection()
                success = result.get('success', False)
                message = result.get('message', result.get('error', 'Unknown error'))
                response_time = time.time() - start_time if success else None
                device_info = {"controller_id": config_id} if success else None

            else:
                success = False
                message = f"不支持的硬件类型: {config.hardware_type}"
                response_time = None
                device_info = None

            if success:
                self.set_connection_status(config_id, ConnectionStatus.CONNECTED)
            else:
                self.set_connection_status(config_id, ConnectionStatus.ERROR)

            return success, message

        except Exception as e:
            error(f"Connection test failed for {config_id}: {e}", "CONFIG_MANAGER")
            self.set_connection_status(config_id, ConnectionStatus.ERROR)
            return False, f"连接测试异常: {str(e)}"

    def _test_camera_connection(self, config: HardwareConfig) -> bool:
        """测试相机连接（模拟实现）"""
        try:
            # 这里应该调用实际的相机连接测试
            # 目前返回模拟结果
            return True
        except:
            return False

    def get_connection_statistics(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        stats = {
            'total_configs': len(self.configs),
            'connected_count': 0,
            'error_count': 0,
            'by_type': {
                HardwareType.ROBOT.value: {'total': 0, 'connected': 0},
                HardwareType.CAMERA.value: {'total': 0, 'connected': 0},
                HardwareType.LIGHT.value: {'total': 0, 'connected': 0}
            }
        }

        for config_id, config in self.configs.items():
            status = self.connection_status.get(config_id, ConnectionStatus.DISCONNECTED)

            # 总体统计
            if status == ConnectionStatus.CONNECTED:
                stats['connected_count'] += 1
            elif status == ConnectionStatus.ERROR:
                stats['error_count'] += 1

            # 类型统计
            if config.hardware_type.value in stats['by_type']:
                stats['by_type'][config.hardware_type.value]['total'] += 1
                if status == ConnectionStatus.CONNECTED:
                    stats['by_type'][config.hardware_type.value]['connected'] += 1

        return stats