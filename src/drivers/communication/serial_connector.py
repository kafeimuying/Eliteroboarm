"""
串口通信连接器
支持RS232、RS485等串口通信协议
"""

import time
from typing import Dict, Any, Optional, Callable
from enum import Enum
import threading
from serial.tools import list_ports
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    serial = None

# 不再导入日志管理器，日志记录将集中到Service层


class SerialProtocol(Enum):
    """串口协议类型"""
    RS232 = "rs232"
    RS485 = "rs485"
    TTL = "ttl"
    MODBUS_RTU = "modbus_rtu"


class SerialConnector:
    """串口连接器"""

    def __init__(self):
        self.connection: Optional[serial.Serial] = None
        self.is_connected_flag = False
        self.connection_lock = threading.Lock()
        self.read_thread: Optional[threading.Thread] = None
        self.stop_reading = False
        self.data_callback: Optional[Callable] = None
        self.connection_params: Dict[str, Any] = {}

        # 统计信息
        self.bytes_sent = 0
        self.bytes_received = 0
        self.connection_time: Optional[float] = None
        self.last_activity: Optional[float] = None

        if not SERIAL_AVAILABLE:
            pass  # Service层将处理PySerial不可用的情况

    def list_available_ports(self) -> list:
        """列出可用的串口"""
        if not SERIAL_AVAILABLE:
            return []

        try:
            ports = list_ports.comports()
            port_list = []
            for port in ports:
                port_info = {
                    'device': port.device,
                    'name': port.name,
                    'description': port.description,
                    'manufacturer': port.manufacturer or 'Unknown',
                    'vid': port.vid,
                    'pid': port.pid,
                    'serial_number': port.serial_number
                }
                port_list.append(port_info)
            return port_list
        except Exception as e:
            return []  # Service层将处理异常并记录日志

    def connect(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """连接串口设备"""
        if not SERIAL_AVAILABLE:
            return {
                'success': False,
                'error': 'PySerial not available. Install with: pip install pyserial'
            }

        try:
            with self.connection_lock:
                if self.is_connected_flag:
                    return {'success': False, 'error': 'Already connected'}

                # 获取连接参数
                port = params.get('port')
                baudrate = params.get('baudrate', 9600)
                data_bits = params.get('data_bits', 8)
                stop_bits = params.get('stop_bits', 1)
                parity = params.get('parity', '无')
                timeout = params.get('timeout', 5.0)
                protocol = params.get('protocol', 'rs232')

                if not port:
                    return {'success': False, 'error': 'Port parameter is required'}

                # 转换校验位
                parity_map = {
                    '无': serial.PARITY_NONE,
                    '奇校验': serial.PARITY_ODD,
                    '偶校验': serial.PARITY_EVEN
                }
                serial_parity = parity_map.get(parity, serial.PARITY_NONE)

                # 创建串口连接
                self.connection = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=data_bits,
                    parity=serial_parity,
                    stopbits=stop_bits,
                    timeout=timeout,
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False
                )

                # 配置RS485模式（如果需要）
                if protocol == SerialProtocol.RS485.value:
                    self._configure_rs485()

                # 测试连接
                if self.connection.is_open:
                    self.is_connected_flag = True
                    self.connection_params = params.copy()
                    self.connection_time = time.time()
                    self.last_activity = time.time()
                    self.bytes_sent = 0
                    self.bytes_received = 0

                    # 启动读取线程
                    self.stop_reading = False
                    self.read_thread = threading.Thread(target=self._read_worker, daemon=True)
                    self.read_thread.start()

                    # Service层将记录连接成功的日志

                    return {
                        'success': True,
                        'message': f'Connected to {port} at {baudrate} baud',
                        'device_info': {
                            'port': port,
                            'baudrate': baudrate,
                            'protocol': protocol,
                            'connection_time': self.connection_time
                        }
                    }
                else:
                    return {'success': False, 'error': 'Failed to open serial port'}

        except Exception as e:
            error_msg = f"Serial connection error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def disconnect(self) -> Dict[str, Any]:
        """断开串口连接"""
        try:
            with self.connection_lock:
                if not self.is_connected_flag:
                    return {'success': True, 'message': 'Already disconnected'}

                # 停止读取线程
                self.stop_reading = True
                if self.read_thread and self.read_thread.is_alive():
                    self.read_thread.join(timeout=2.0)

                # 关闭串口连接
                if self.connection and self.connection.is_open:
                    self.connection.close()

                self.is_connected_flag = False
                self.connection = None
                self.connection_params = {}

                # Service层将记录断开连接的日志
                return {'success': True, 'message': 'Disconnected successfully'}

        except Exception as e:
            error_msg = f"Serial disconnect error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def send_data(self, data: bytes) -> Dict[str, Any]:
        """发送数据"""
        if not self.is_connected_flag or not self.connection:
            return {'success': False, 'error': 'Not connected'}

        try:
            bytes_written = self.connection.write(data)
            self.connection.flush()
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

    def read_data(self, size: int = 1) -> Dict[str, Any]:
        """读取数据"""
        if not self.is_connected_flag or not self.connection:
            return {'success': False, 'error': 'Not connected'}

        try:
            data = self.connection.read(size)
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

    def read_line(self) -> Dict[str, Any]:
        """读取一行数据"""
        if not self.is_connected_flag or not self.connection:
            return {'success': False, 'error': 'Not connected'}

        try:
            line = self.connection.readline()
            if line:
                self.bytes_received += len(line)
                self.last_activity = time.time()

                return {
                    'success': True,
                    'data': line,
                    'data_hex': line.hex(),
                    'data_str': line.decode('utf-8', errors='ignore').strip()
                }
            else:
                return {'success': False, 'error': 'No line available'}

        except Exception as e:
            error_msg = f"Read line error: {str(e)}"
            return {'success': False, 'error': error_msg}

    def set_data_callback(self, callback: Callable):
        """设置数据接收回调函数"""
        self.data_callback = callback

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.is_connected_flag and self.connection and self.connection.is_open

    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        if not self.is_connected_flag:
            return {'connected': False}

        current_time = time.time()
        uptime = current_time - self.connection_time if self.connection_time else 0

        return {
            'connected': True,
            'uptime_seconds': uptime,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'last_activity_seconds_ago': current_time - self.last_activity if self.last_activity else 0,
            'connection_params': self.connection_params.copy()
        }

    def _configure_rs485(self):
        """配置RS485模式"""
        if hasattr(serial, 'RS485Settings'):
            try:
                rs485_settings = serial.RS485Settings(
                    rts_level_for_tx=True,
                    rts_level_for_rx=False,
                    loopback=False,
                    delay_before_tx=0.001,
                    delay_after_tx=0.001
                )
                self.connection.rs485_settings = rs485_settings
                # Service层将记录RS485配置日志
            except Exception as e:
                pass  # Service层将处理RS485配置失败

    def _read_worker(self):
        """读取数据的工作线程"""
        # Service层将记录读取线程启动日志

        while not self.stop_reading and self.is_connected_flag:
            try:
                if self.connection and self.connection.in_waiting > 0:
                    data = self.connection.read(self.connection.in_waiting)
                    if data and self.data_callback:
                        self.bytes_received += len(data)
                        self.last_activity = time.time()
                        try:
                            self.data_callback(data)
                        except Exception as callback_error:
                            pass  # Service层将处理数据回调异常

                time.sleep(0.01)  # 10ms轮询间隔

            except Exception as e:
                time.sleep(0.1)

        # Service层将记录读取线程停止日志


class SerialManager:
    """串口管理器"""

    def __init__(self):
        self.connectors: Dict[str, SerialConnector] = {}
        self.next_connector_id = 1

    def create_connector(self) -> SerialConnector:
        """创建新的串口连接器"""
        connector = SerialConnector()
        connector_id = f"serial_{self.next_connector_id}"
        self.next_connector_id += 1
        self.connectors[connector_id] = connector
        return connector

    def get_connector(self, connector_id: str) -> Optional[SerialConnector]:
        """获取串口连接器"""
        return self.connectors.get(connector_id)

    def remove_connector(self, connector_id: str):
        """移除串口连接器"""
        if connector_id in self.connectors:
            connector = self.connectors[connector_id]
            if connector.is_connected():
                connector.disconnect()
            del self.connectors[connector_id]

    def list_available_ports(self) -> list:
        """列出所有可用串口"""
        return SerialConnector().list_available_ports()

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