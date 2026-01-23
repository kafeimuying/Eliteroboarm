"""
硬件连接管理器
管理所有硬件设备的连接状态、连接测试和自动重连
"""

import threading
import time
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import QWidget

from ..services.robot_service import RobotService
from ..services.camera_service import CameraService
from ..services.light_service import LightService
from .config_manager import HardwareConfig, HardwareType, ConnectionStatus, ConnectionTestResult
from .log_manager import info, debug, warning, error


class ConnectionEvent(Enum):
    """连接事件类型"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTION_LOST = "connection_lost"
    ERROR = "error"
    TEST_COMPLETED = "test_completed"


class ConnectionManager:
    """硬件连接管理器"""

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # 服务实例
        self.robot_service: Optional[RobotService] = None
        self.camera_service: Optional[CameraService] = None
        self.light_service: Optional[LightService] = None

        # 连接状态管理
        self.active_connections: Dict[str, Any] = {}  # config_id -> service_instance
        self.connection_threads: Dict[str, threading.Thread] = {}
        self.connection_lock = threading.Lock()

        # 事件回调
        self.event_callbacks: List[Callable] = []

        # 自动重连设置
        self.auto_reconnect = True
        self.reconnect_interval = 30.0  # 秒
        self.reconnect_attempts = 3

        # 健康检查设置
        self.health_check_interval = 60.0  # 秒
        self.health_check_thread: Optional[threading.Thread] = None
        self.health_check_running = False

        info("Connection manager initialized", "CONNECTION_MANAGER")

    def set_services(self, robot_service: RobotService,
                    camera_service: CameraService,
                    light_service: LightService):
        """设置服务实例"""
        self.robot_service = robot_service
        self.camera_service = camera_service
        self.light_service = light_service
        info("Services set for connection manager", "CONNECTION_MANAGER")

    def register_event_callback(self, callback: Callable):
        """注册事件回调函数"""
        if callback not in self.event_callbacks:
            self.event_callbacks.append(callback)
            info(f"Event callback registered: {callback}", "CONNECTION_MANAGER")

    def unregister_event_callback(self, callback: Callable):
        """取消注册事件回调函数"""
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)
            info(f"Event callback unregistered: {callback}", "CONNECTION_MANAGER")

    def _emit_event(self, event: ConnectionEvent, config_id: str, data: Dict[str, Any] = None):
        """发出连接事件"""
        event_data = {
            'event': event.value,
            'config_id': config_id,
            'timestamp': time.time(),
            'data': data or {}
        }

        for callback in self.event_callbacks:
            try:
                callback(event_data)
            except Exception as e:
                error(f"Event callback error: {e}", "CONNECTION_MANAGER")

    def connect_hardware(self, config_id: str, config) -> Dict[str, Any]:
        """连接硬件设备"""
        try:
            with self.connection_lock:
                if config_id in self.active_connections:
                    return {'success': False, 'error': 'Already connected'}

                self._emit_event(ConnectionEvent.CONNECTING, config_id)

                # 根据硬件类型选择相应的服务
                service = self._get_service_for_hardware(config.hardware_type)
                if not service:
                    return {'success': False, 'error': f'No service available for {config.hardware_type.value}'}

                # 尝试连接
                result = service.connect(config.connection_params)

                if result.get('success', False):
                    self.active_connections[config_id] = {
                        'service': service,
                        'config': config,
                        'connected_time': time.time(),
                        'last_health_check': time.time()
                    }

                    self._emit_event(ConnectionEvent.CONNECTED, config_id, {
                        'response_time': result.get('response_time'),
                        'device_info': result.get('device_info')
                    })

                    info(f"Hardware connected successfully: {config_id}", "CONNECTION_MANAGER")
                    return {'success': True, 'message': 'Connected successfully'}

                else:
                    self._emit_event(ConnectionEvent.ERROR, config_id, {
                        'error': result.get('error')
                    })
                    return result

        except Exception as e:
            error_msg = f"Connection error: {str(e)}"
            error(f"Failed to connect hardware {config_id}: {e}", "CONNECTION_MANAGER")
            self._emit_event(ConnectionEvent.ERROR, config_id, {'error': error_msg})
            return {'success': False, 'error': error_msg}

    def disconnect_hardware(self, config_id: str) -> Dict[str, Any]:
        """断开硬件连接"""
        try:
            with self.connection_lock:
                if config_id not in self.active_connections:
                    return {'success': False, 'error': 'Not connected'}

                connection_info = self.active_connections[config_id]
                service = connection_info['service']

                # 调用断开连接
                if hasattr(service, 'disconnect'):
                    result = service.disconnect()
                else:
                    result = {'success': True, 'message': 'No disconnect method available'}

                # 清理连接信息
                del self.active_connections[config_id]

                self._emit_event(ConnectionEvent.DISCONNECTED, config_id)

                info(f"Hardware disconnected: {config_id}", "CONNECTION_MANAGER")
                return {'success': True, 'message': 'Disconnected successfully'}

        except Exception as e:
            error_msg = f"Disconnect error: {str(e)}"
            error(f"Failed to disconnect hardware {config_id}: {e}", "CONNECTION_MANAGER")
            self._emit_event(ConnectionEvent.ERROR, config_id, {'error': error_msg})
            return {'success': False, 'error': error_msg}

    def test_connection(self, config_id: str, config) -> ConnectionTestResult:
        """测试硬件连接"""
        try:
            start_time = time.time()

            service = self._get_service_for_hardware(config.hardware_type)
            if not service:
                return ConnectionTestResult(
                    success=False,
                    message=f'No service available for {config.hardware_type.value}'
                )

            # 调用测试连接方法
            if hasattr(service, 'test_connection'):
                result = service.test_connection()
                success = result.get('success', False)
                message = result.get('message', result.get('error', 'Test completed'))
            else:
                # 简单的ping测试
                try:
                    # 尝试连接然后立即断开
                    connect_result = service.connect(config.connection_params)
                    success = connect_result.get('success', False)
                    if success and hasattr(service, 'disconnect'):
                        service.disconnect()
                    message = "Connection test completed" if success else "Connection failed"
                except Exception as e:
                    success = False
                    message = f"Connection test failed: {str(e)}"

            response_time = time.time() - start_time

            test_result = ConnectionTestResult(
                success=success,
                message=message,
                response_time=response_time,
                device_info=result.get('device_info') if 'result' in locals() else None
            )

            self._emit_event(ConnectionEvent.TEST_COMPLETED, config_id, {
                'success': success,
                'response_time': response_time
            })

            return test_result

        except Exception as e:
            error(f"Connection test failed for {config_id}: {e}", "CONNECTION_MANAGER")
            test_result = ConnectionTestResult(
                success=False,
                message=f"Test error: {str(e)}",
                error_details=str(e)
            )

            self._emit_event(ConnectionEvent.TEST_COMPLETED, config_id, {
                'success': False,
                'error': str(e)
            })

            return test_result

    def test_all_connections(self, configs: Dict[str, HardwareConfig]) -> Dict[str, ConnectionTestResult]:
        """批量测试所有连接"""
        results = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有测试任务
            future_to_config = {
                executor.submit(self.test_connection, config_id, config): config_id
                for config_id, config in configs.items()
            }

            # 收集结果
            for future in as_completed(future_to_config):
                config_id = future_to_config[future]
                try:
                    result = future.result()
                    results[config_id] = result
                except Exception as e:
                    error(f"Batch connection test failed for {config_id}: {e}", "CONNECTION_MANAGER")
                    results[config_id] = ConnectionTestResult(
                        success=False,
                        message=f"Test error: {str(e)}",
                        error_details=str(e)
                    )

        return results

    def is_connected(self, config_id: str) -> bool:
        """检查硬件是否已连接"""
        return config_id in self.active_connections

    def get_active_connections(self) -> List[str]:
        """获取所有活跃连接的ID"""
        return list(self.active_connections.keys())

    def get_connection_info(self, config_id: str) -> Optional[Dict[str, Any]]:
        """获取连接信息"""
        if config_id in self.active_connections:
            info = self.active_connections[config_id].copy()
            # 移除service对象，避免序列化问题
            info.pop('service', None)
            return info
        return None

    def _get_service_for_hardware(self, hardware_type: HardwareType) -> Optional[Any]:
        """根据硬件类型获取相应的服务"""
        if hardware_type == HardwareType.ROBOT:
            return self.robot_service
        elif hardware_type == HardwareType.CAMERA:
            return self.camera_service
        elif hardware_type == HardwareType.LIGHT:
            return self.light_service
        else:
            return None

    def start_health_check(self):
        """启动健康检查线程"""
        if self.health_check_running:
            return

        self.health_check_running = True
        self.health_check_thread = threading.Thread(target=self._health_check_worker, daemon=True)
        self.health_check_thread.start()
        info("Health check thread started", "CONNECTION_MANAGER")

    def stop_health_check(self):
        """停止健康检查线程"""
        self.health_check_running = False
        if self.health_check_thread and self.health_check_thread.is_alive():
            self.health_check_thread.join(timeout=5.0)
        info("Health check thread stopped", "CONNECTION_MANAGER")

    def _health_check_worker(self):
        """健康检查工作线程"""
        info("Health check worker started", "CONNECTION_MANAGER")

        while self.health_check_running:
            try:
                current_time = time.time()
                connections_to_check = []

                with self.connection_lock:
                    for config_id, conn_info in list(self.active_connections.items()):
                        # 检查是否需要健康检查
                        if current_time - conn_info['last_health_check'] >= self.health_check_interval:
                            connections_to_check.append((config_id, conn_info))

                # 执行健康检查
                for config_id, conn_info in connections_to_check:
                    try:
                        service = conn_info['service']

                        # 调用服务的健康检查方法
                        if hasattr(service, 'test_connection'):
                            result = service.test_connection()
                            is_healthy = result.get('success', False)
                        else:
                            # 简单的ping检查
                            is_healthy = service.is_connected() if hasattr(service, 'is_connected') else True

                        if is_healthy:
                            # 更新健康检查时间
                            with self.connection_lock:
                                if config_id in self.active_connections:
                                    self.active_connections[config_id]['last_health_check'] = current_time
                        else:
                            warning(f"Health check failed for {config_id}", "CONNECTION_MANAGER")
                            self._emit_event(ConnectionEvent.CONNECTION_LOST, config_id)

                            # 如果启用自动重连
                            if self.auto_reconnect:
                                self._schedule_reconnect(config_id, conn_info['config'])

                    except Exception as e:
                        error(f"Health check error for {config_id}: {e}", "CONNECTION_MANAGER")
                        self._emit_event(ConnectionEvent.ERROR, config_id, {'error': str(e)})

            except Exception as e:
                error(f"Health check worker error: {e}", "CONNECTION_MANAGER")

            # 等待下次检查
            time.sleep(self.health_check_interval)

        info("Health check worker stopped", "CONNECTION_MANAGER")

    def _schedule_reconnect(self, config_id: str, config):
        """调度自动重连"""
        def reconnect_worker():
            for attempt in range(self.reconnect_attempts):
                try:
                    info(f"Auto-reconnect attempt {attempt + 1}/{self.reconnect_attempts} for {config_id}", "CONNECTION_MANAGER")

                    result = self.connect_hardware(config_id, config)
                    if result.get('success'):
                        info(f"Auto-reconnect successful for {config_id}", "CONNECTION_MANAGER")
                        break
                    else:
                        warning(f"Auto-reconnect failed for {config_id}: {result.get('error')}", "CONNECTION_MANAGER")

                except Exception as e:
                    error(f"Auto-reconnect error for {config_id}: {e}", "CONNECTION_MANAGER")

                if attempt < self.reconnect_attempts - 1:
                    time.sleep(self.reconnect_interval)

        # 在新线程中执行重连
        reconnect_thread = threading.Thread(target=reconnect_worker, daemon=True)
        reconnect_thread.start()

    def get_connection_statistics(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        current_time = time.time()

        stats = {
            'active_connections': len(self.active_connections),
            'health_check_running': self.health_check_running,
            'auto_reconnect_enabled': self.auto_reconnect,
            'connections': {}
        }

        with self.connection_lock:
            for config_id, conn_info in self.active_connections.items():
                uptime = current_time - conn_info['connected_time']
                last_check = current_time - conn_info['last_health_check']

                stats['connections'][config_id] = {
                    'uptime_seconds': uptime,
                    'uptime_hours': uptime / 3600,
                    'last_health_check_seconds_ago': last_check,
                    'hardware_type': conn_info['config'].hardware_type.value
                }

        return stats

    def shutdown(self):
        """关闭连接管理器"""
        info("Shutting down connection manager", "CONNECTION_MANAGER")

        # 停止健康检查
        self.stop_health_check()

        # 断开所有连接
        with self.connection_lock:
            for config_id in list(self.active_connections.keys()):
                try:
                    self.disconnect_hardware(config_id)
                except Exception as e:
                    error(f"Error disconnecting {config_id} during shutdown: {e}", "CONNECTION_MANAGER")

        # 关闭线程池
        self.executor.shutdown(wait=True)

        info("Connection manager shutdown completed", "CONNECTION_MANAGER")