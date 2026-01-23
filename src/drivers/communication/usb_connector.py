"""
USB硬件连接器
支持USB设备的连接和管理
"""

# 不再导入logging，日志记录将集中到Service层
import time
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
import threading
try:
    import usb.core
    import usb.util
    USB_AVAILABLE = True
except ImportError:
    USB_AVAILABLE = False
    usb = None

# 不再创建logger，日志记录将集中到Service层


class USBDeviceType(Enum):
    """USB设备类型"""
    HID = "hid"
    CDC = "cdc"  # Communications Device Class
    CUSTOM = "custom"
    VENDOR_SPECIFIC = "vendor_specific"


class USBConnector:
    """USB连接器"""

    def __init__(self):
        self.device: Optional[Any] = None  # usb.core.Device
        self.is_connected_flag = False
        self.connection_lock = threading.Lock()
        self.read_thread: Optional[threading.Thread] = None
        self.stop_reading = False
        self.data_callback: Optional[Callable] = None
        self.connection_params: Dict[str, Any] = {}

        # USB配置
        self.configuration = None
        self.interface = None
        self.endpoint_in = None
        self.endpoint_out = None

        # 统计信息
        self.bytes_sent = 0
        self.bytes_received = 0
        self.connection_time: Optional[float] = None
        self.last_activity: Optional[float] = None

        if not USB_AVAILABLE:
            pass  # Service层将处理PyUSB不可用的情况

    def list_available_devices(self) -> List[Dict[str, Any]]:
        """列出可用的USB设备"""
        if not USB_AVAILABLE:
            return []

        try:
            devices = []
            for dev in usb.core.find(find_all=True):
                try:
                    device_info = {
                        'id': f"{dev.bus:03d}:{dev.address:03d}",
                        'vendor_id': hex(dev.idVendor),
                        'product_id': hex(dev.idProduct),
                        'manufacturer': usb.util.get_string(dev, dev.iManufacturer) or 'Unknown',
                        'product': usb.util.get_string(dev, dev.iProduct) or 'Unknown',
                        'serial_number': usb.util.get_string(dev, dev.iSerialNumber) or 'Unknown',
                        'bus': dev.bus,
                        'address': dev.address
                    }
                    devices.append(device_info)
                except Exception as e:
                    continue

            return devices
        except Exception as e:
            return []  # Service层将处理异常并记录日志

    def connect(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """连接USB设备"""
        if not USB_AVAILABLE:
            return {
                'success': False,
                'error': 'PyUSB not available. Install with: pip install pyusb'
            }

        try:
            with self.connection_lock:
                if self.is_connected_flag:
                    return {'success': False, 'error': 'Already connected'}

                # 获取连接参数
                device_id = params.get('device_id')
                vendor_id = params.get('vendor_id')
                product_id = params.get('product_id')
                interface_num = params.get('interface', 0)
                timeout = params.get('timeout', 5.0)

                # 查找设备
                device = None
                if device_id:
                    # 通过设备ID查找
                    if ':' in device_id:
                        bus, address = device_id.split(':')
                        device = usb.core.find(bus=int(bus), address=int(address))
                    else:
                        # 通过设备ID字符串匹配
                        all_devices = usb.core.find(find_all=True)
                        for dev in all_devices:
                            dev_id = f"{dev.bus:03d}:{dev.address:03d}"
                            if dev_id == device_id:
                                device = dev
                                break
                elif vendor_id and product_id:
                    # 通过VID和PID查找
                    device = usb.core.find(idVendor=vendor_id, idProduct=product_id)

                if device is None:
                    return {'success': False, 'error': 'Device not found'}

                # 尝试连接设备
                try:
                    # 检查设备是否已被内核驱动占用
                    for cfg in device:
                        for intf in cfg:
                            if device.is_kernel_driver_active(intf.bInterfaceNumber):
                                try:
                                    device.detach_kernel_driver(intf.bInterfaceNumber)
                                    # Service层将记录内核驱动分离日志
                                except usb.core.USBError as e:
                                    pass  # Service层将处理内核驱动分离失败

                    # 设置配置
                    device.set_configuration()

                    # 获取接口
                    cfg = device.get_active_configuration()
                    interface = cfg[(interface_num, 0)]

                    # 查找端点
                    endpoint_in = None
                    endpoint_out = None

                    for endpoint in interface.endpoints():
                        if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN:
                            endpoint_in = endpoint
                        elif usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_OUT:
                            endpoint_out = endpoint

                    # 存储连接信息
                    self.device = device
                    self.configuration = cfg
                    self.interface = interface
                    self.endpoint_in = endpoint_in
                    self.endpoint_out = endpoint_out
                    self.is_connected_flag = True
                    self.connection_params = params.copy()
                    self.connection_time = time.time()
                    self.last_activity = time.time()
                    self.bytes_sent = 0
                    self.bytes_received = 0

                    # 启动读取线程（如果有输入端点）
                    if self.endpoint_in:
                        self.stop_reading = False
                        self.read_thread = threading.Thread(target=self._read_worker, daemon=True)
                        self.read_thread.start()

                    device_info = {
                        'vendor_id': hex(device.idVendor),
                        'product_id': hex(device.idProduct),
                        'manufacturer': usb.util.get_string(device, device.iManufacturer) or 'Unknown',
                        'product': usb.util.get_string(device, device.iProduct) or 'Unknown',
                        'serial_number': usb.util.get_string(device, device.iSerialNumber) or 'Unknown',
                        'connection_time': self.connection_time
                    }

                    # Service层将记录USB连接建立日志

                    return {
                        'success': True,
                        'message': f'Connected to USB device',
                        'device_info': device_info
                    }

                except usb.core.USBError as e:
                    return {'success': False, 'error': f'USB error: {str(e)}'}

        except Exception as e:
            error_msg = f"USB connection error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def disconnect(self) -> Dict[str, Any]:
        """断开USB连接"""
        try:
            with self.connection_lock:
                if not self.is_connected_flag:
                    return {'success': True, 'message': 'Already disconnected'}

                # 停止读取线程
                self.stop_reading = True
                if self.read_thread and self.read_thread.is_alive():
                    self.read_thread.join(timeout=2.0)

                # 释放USB设备
                if self.device:
                    try:
                        usb.util.dispose_resources(self.device)
                    except Exception as e:
                        pass  # Service层将处理USB资源释放异常

                self.is_connected_flag = False
                self.device = None
                self.configuration = None
                self.interface = None
                self.endpoint_in = None
                self.endpoint_out = None
                self.connection_params = {}

                # Service层将记录USB连接关闭日志
                return {'success': True, 'message': 'Disconnected successfully'}

        except Exception as e:
            error_msg = f"USB disconnect error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def send_data(self, data: bytes) -> Dict[str, Any]:
        """发送数据"""
        if not self.is_connected_flag or not self.device or not self.endpoint_out:
            return {'success': False, 'error': 'Not connected or no output endpoint'}

        try:
            bytes_written = self.endpoint_out.write(data)
            self.bytes_sent += bytes_written
            self.last_activity = time.time()

            return {
                'success': True,
                'bytes_sent': bytes_written,
                'data_hex': data.hex()
            }

        except Exception as e:
            error_msg = f"Send data error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def send_command(self, command: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """发送文本命令"""
        try:
            data = command.encode(encoding)
            return self.send_data(data)
        except Exception as e:
            error_msg = f"Send command error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def read_data(self, size: int = None) -> Dict[str, Any]:
        """读取数据"""
        if not self.is_connected_flag or not self.device or not self.endpoint_in:
            return {'success': False, 'error': 'Not connected or no input endpoint'}

        try:
            if size is None:
                size = self.endpoint_in.wMaxPacketSize

            data = self.endpoint_in.read(size, timeout=1000)
            if data:
                self.bytes_received += len(data)
                self.last_activity = time.time()

                return {
                    'success': True,
                    'data': data,
                    'data_hex': data.hex(),
                    'data_str': data.decode('utf-8', errors='ignore')
                }
            else:
                return {'success': False, 'error': 'No data available'}

        except Exception as e:
            error_msg = f"Read data error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def set_data_callback(self, callback: Callable):
        """设置数据接收回调函数"""
        self.data_callback = callback

    def is_connected(self) -> bool:
        """检查连接状态"""
        return (self.is_connected_flag and
                self.device is not None)

    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        if not self.is_connected_flag:
            return {'connected': False}

        current_time = time.time()
        uptime = current_time - self.connection_time if self.connection_time else 0

        info = {
            'connected': True,
            'uptime_seconds': uptime,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'last_activity_seconds_ago': current_time - self.last_activity if self.last_activity else 0,
            'connection_params': self.connection_params.copy()
        }

        if self.device:
            info.update({
                'vendor_id': hex(self.device.idVendor),
                'product_id': hex(self.device.idProduct),
                'bus': self.device.bus,
                'address': self.device.address
            })

        return info

    def control_transfer(self, request_type: int, request: int, value: int = 0,
                        index: int = 0, data: bytes = None) -> Dict[str, Any]:
        """控制传输"""
        if not self.is_connected_flag or not self.device:
            return {'success': False, 'error': 'Not connected'}

        try:
            if data:
                result = self.device.ctrl_transfer(
                    request_type, request, value, index, data
                )
            else:
                result = self.device.ctrl_transfer(
                    request_type, request, value, index
                )

            return {
                'success': True,
                'result': result,
                'data_hex': result.hex() if isinstance(result, bytes) else None
            }

        except Exception as e:
            error_msg = f"Control transfer error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def _read_worker(self):
        """读取数据的工作线程"""
        # Service层将记录读取线程启动日志

        while not self.stop_reading and self.is_connected_flag:
            try:
                if self.endpoint_in:
                    try:
                        data = self.endpoint_in.read(self.endpoint_in.wMaxPacketSize, timeout=100)
                        if data and self.data_callback:
                            self.bytes_received += len(data)
                            self.last_activity = time.time()
                            try:
                                self.data_callback(data)
                            except Exception as callback_error:
                                pass  # Service层将处理数据回调异常
                    except usb.core.USBError:
                        # 超时或无数据，继续循环
                        pass

                time.sleep(0.01)  # 10ms轮询间隔

            except Exception as e:
                time.sleep(0.1)

        # Service层将记录读取线程停止日志


class USBManager:
    """USB管理器"""

    def __init__(self):
        self.connectors: Dict[str, USBConnector] = {}
        self.next_connector_id = 1

    def create_connector(self) -> USBConnector:
        """创建新的USB连接器"""
        connector = USBConnector()
        connector_id = f"usb_{self.next_connector_id}"
        self.next_connector_id += 1
        self.connectors[connector_id] = connector
        return connector

    def get_connector(self, connector_id: str) -> Optional[USBConnector]:
        """获取USB连接器"""
        return self.connectors.get(connector_id)

    def remove_connector(self, connector_id: str):
        """移除USB连接器"""
        if connector_id in self.connectors:
            connector = self.connectors[connector_id]
            if connector.is_connected():
                connector.disconnect()
            del self.connectors[connector_id]

    def list_available_devices(self) -> List[Dict[str, Any]]:
        """列出所有可用USB设备"""
        return USBConnector().list_available_devices()

    def get_all_connection_info(self) -> Dict[str, Dict[str, Any]]:
        """获取所有连接信息"""
        return {
            connector_id: connector.get_connection_info()
            for connector_id, connector in self.connectors.items()
        }

    def shutdown(self):
        """关闭所有连接"""
        for connector_id in list(self.connectors.keys()):
            self.remove_connector(connector_id)