"""
全局状态管理器
统一管理应用的全局状态，提供状态订阅、更新和持久化功能
"""

from typing import Any, Dict, List, Optional, Callable, Set, Type
from dataclasses import dataclass, field, asdict
from enum import Enum
from threading import RLock, Lock
import json
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from PyQt6.QtCore import QTimer

from .event_bus import EventBus, EventType, Event, get_event_bus
from .types_dto import DeviceType, ConnectionStatus, SystemStatus, DeviceInfo, ConnectionInfo
from ..managers.log_manager import info, debug, error, warning


class StateChangeEvent(Enum):
    """状态变更事件类型"""
    DEVICE_ADDED = "device_added"
    DEVICE_REMOVED = "device_removed"
    DEVICE_UPDATED = "device_updated"
    CONNECTION_CHANGED = "connection_changed"
    SYSTEM_STATUS_CHANGED = "system_status_changed"
    CONFIG_CHANGED = "config_changed"
    ERROR_OCCURRED = "error_occurred"
    ERROR_RESOLVED = "error_resolved"


@dataclass
class StateSnapshot:
    """状态快照"""
    timestamp: float
    system_status: SystemStatus
    devices: Dict[str, Dict[str, Any]]
    config_hash: str
    event_count: int
    error_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'system_status': asdict(self.system_status),
            'devices': self.devices,
            'config_hash': self.config_hash,
            'event_count': self.event_count,
            'error_count': self.error_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateSnapshot':
        return cls(
            timestamp=data['timestamp'],
            system_status=SystemStatus(**data['system_status']),
            devices=data['devices'],
            config_hash=data['config_hash'],
            event_count=data['event_count'],
            error_count=data['error_count']
        )


class StateSubscriber(ABC):
    """状态订阅者抽象基类"""

    @abstractmethod
    def on_state_changed(self, state_key: str, old_value: Any, new_value: Any) -> None:
        """状态变更回调"""
        pass

    @abstractmethod
    def get_subscribed_keys(self) -> Set[str]:
        """获取要订阅的状态键"""
        pass


class StateManager:
    """全局状态管理器"""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus or get_event_bus()
        self._state: Dict[str, Any] = {}
        self._subscribers: Dict[str, List[StateSubscriber]] = defaultdict(list)
        self._state_history: List[StateSnapshot] = []
        self._max_history_size = 100
        self._lock = RLock()
        self._persistence_enabled = True
        self._auto_save_interval = 30.0  # 自动保存间隔（秒）
        self._last_save_time = 0
        self._config_file_path = os.path.join(
            os.path.dirname(__file__),
            '../../../config/app_state.json'
        )

        # 初始化核心状态
        self._initialize_state()

        # 启动自动保存
        self._setup_auto_save()

        info("StateManager initialized", "STATE_MANAGER")

    def _initialize_state(self) -> None:
        """初始化核心状态"""
        self._state.update({
            'system': {
                'application_ready': False,
                'total_devices': 0,
                'connected_devices': 0,
                'error_count': 0,
                'last_update': time.time(),
                'cpu_usage': 0.0,
                'memory_usage': 0.0,
                'disk_usage': 0.0,
                'debug_mode': False,
                'auto_save_enabled': True
            },
            'devices': {},  # 设备状态
            'config': {
                'last_modified': 0,
                'config_version': '1.0',
                'auto_save_interval': self._auto_save_interval
            },
            'ui': {
                'current_theme': 'light',
                'language': 'zh_CN',
                'window_size': [1200, 800],
                'window_state': 'normal',
                'show_status_bar': True,
                'show_toolbar': True
            },
            'performance': {
                'frame_rate': 0.0,
                'response_time': 0.0,
                'command_queue_size': 0,
                'cache_hit_rate': 0.0
            },
            'counters': {
                'events_processed': 0,
                'commands_executed': 0,
                'errors_occurred': 0,
                'auto_saves': 0
            }
        })

    def get_state(self, key: str = None, default: Any = None) -> Any:
        """获取状态值"""
        with self._lock:
            if key is None:
                return self._state.copy()
            return self._state.get(key, default)

    def set_state(self, key: str, value: Any, persist: bool = True) -> None:
        """设置状态值"""
        with self._lock:
            old_value = self._state.get(key)
            self._state[key] = value

        # 通知订阅者
        self._notify_subscribers(key, old_value, value)

        # 发布状态变更事件
        self._publish_state_change_event(key, old_value, value)

        # 持久化
        if persist and self._persistence_enabled:
            self._schedule_auto_save()

        debug(f"State changed: {key} = {value}", "STATE_MANAGER")

    def update_state(self, updates: Dict[str, Any], persist: bool = True) -> None:
        """批量更新状态"""
        with self._lock:
            changed_keys = []
            for key, value in updates.items():
                old_value = self._state.get(key)
                self._state[key] = value
                changed_keys.append((key, old_value))

        # 通知订阅者
        for key, old_value in changed_keys:
            self._notify_subscribers(key, old_value, self._state[key])

        # 发布状态变更事件
        for key, old_value in changed_keys:
            self._publish_state_change_event(key, old_value, self._state[key])

        # 持久化
        if persist and self._persistence_enabled:
            self._schedule_auto_save()

        debug(f"Batch state update: {len(updates)} keys changed", "STATE_MANAGER")

    def subscribe(self, subscriber: StateSubscriber) -> None:
        """订阅状态变更"""
        with self._lock:
            for key in subscriber.get_subscribed_keys():
                self._subscribers[key].append(subscriber)
        debug(f"State subscriber added: {subscriber.__class__.__name__}", "STATE_MANAGER")

    def unsubscribe(self, subscriber: StateSubscriber) -> None:
        """取消订阅状态变更"""
        with self._lock:
            for key in subscriber.get_subscribed_keys():
                if subscriber in self._subscribers[key]:
                    self._subscribers[key].remove(subscriber)
        debug(f"State subscriber removed: {subscriber.__class__.__name__}", "STATE_MANAGER")

    def _notify_subscribers(self, key: str, old_value: Any, new_value: Any) -> None:
        """通知订阅者状态变更"""
        with self._lock:
            subscribers = self._subscribers.get(key, [])
            for subscriber in subscribers:
                try:
                    subscriber.on_state_changed(key, old_value, new_value)
                except Exception as e:
                    error(f"Error in state subscriber {subscriber.__class__.__name__}: {e}", "STATE_MANAGER")

    def _publish_state_change_event(self, key: str, old_value: Any, new_value: Any) -> None:
        """发布状态变更事件"""
        event_data = {
            'key': key,
            'old_value': old_value,
            'new_value': new_value,
            'timestamp': time.time()
        }

        # 根据状态键确定事件类型
        if key == 'devices':
            if old_value and not new_value:  # 设备被移除
                event_type = StateChangeEvent.DEVICE_REMOVED
            elif not old_value and new_value:  # 设备被添加
                event_type = StateChangeEvent.DEVICE_ADDED
            else:  # 设备被更新
                event_type = StateChangeEvent.DEVICE_UPDATED
        elif key == 'system':
            event_type = StateChangeEvent.SYSTEM_STATUS_CHANGED
        elif key.startswith('config'):
            event_type = StateChangeEvent.CONFIG_CHANGED
        elif 'error' in key.lower():
            event_type = StateChangeEvent.ERROR_OCCURRED if new_value else StateChangeEvent.ERROR_RESOLVED
        else:
            return  # 其他状态变更不发布事件

        self._event_bus.publish(
            EventType.APPLICATION_READY if key == 'system.application_ready' else EventType.HARDWARE_STATUS_CHANGED,
            event_data,
            "state_manager"
        )

    def add_device(self, device_id: str, device_info: DeviceInfo) -> None:
        """添加设备"""
        self.update_state({
            'devices': {
                **self.get_state('devices', {}),
                device_id: asdict(device_info)
            },
            'system.total_devices': self.get_state('system.total_devices', 0) + 1
        })

    def remove_device(self, device_id: str) -> None:
        """移除设备"""
        devices = self.get_state('devices', {}).copy()
        if device_id in devices:
            del devices[device_id]
            connected_count = self.get_state('system.connected_devices', 0)
            if devices[device_id].get('connection', {}).get('status') == 'connected':
                connected_count -= 1

            self.update_state({
                'devices': devices,
                'system.total_devices': max(0, len(devices)),
                'system.connected_devices': connected_count
            })

    def update_device_connection(self, device_id: str, connection_info: ConnectionInfo) -> None:
        """更新设备连接状态"""
        devices = self.get_state('devices', {})
        if device_id in devices:
            devices[device_id]['connection'] = asdict(connection_info)

            # 更新连接设备计数
            old_devices = devices[device_id].get('connection', {}).get('status')
            new_status = connection_info.status
            connected_count = self.get_state('system.connected_devices', 0)

            if old_status == 'connected' and new_status != 'connected':
                connected_count -= 1
            elif old_status != 'connected' and new_status == 'connected':
                connected_count += 1

            self.update_state({
                'devices': devices,
                'system.connected_devices': connected_count
            })

    def get_device_state(self, device_id: str) -> Optional[Dict[str, Any]]:
        """获取设备状态"""
        devices = self.get_state('devices', {})
        return devices.get(device_id)

    def get_all_devices(self) -> Dict[str, Dict[str, Any]]:
        """获取所有设备状态"""
        return self.get_state('devices', {})

    def get_connected_devices(self) -> List[str]:
        """获取已连接的设备ID列表"""
        devices = self.get_all_devices()
        return [
            device_id for device_id, device_info in devices.items()
            if device_info.get('connection', {}).get('status') == 'connected'
        ]

    def get_devices_by_type(self, device_type: DeviceType) -> List[Dict[str, Any]]:
        """根据设备类型获取设备列表"""
        devices = self.get_all_devices()
        return [
            device_info for device_info in devices.values()
            if device_info.get('device_type') == device_type.value
        ]

    def increment_counter(self, counter_name: str) -> int:
        """递增计数器"""
        current_value = self.get_state(f'counters.{counter_name}', 0)
        new_value = current_value + 1
        self.set_state(f'counters.{counter_name}', new_value)
        return new_value

    def get_counter(self, counter_name: str) -> int:
        """获取计数器值"""
        return self.get_state(f'counters.{counter_name}', 0)

    def reset_counter(self, counter_name: str) -> None:
        """重置计数器"""
        self.set_state(f'counters.{counter_name}', 0)

    def create_snapshot(self) -> StateSnapshot:
        """创建状态快照"""
        with self._lock:
            system_status = self.get_state('system')
            devices = self.get_state('devices', {})
            counters = self.get_state('counters', {})

            config_hash = self._calculate_config_hash()

            snapshot = StateSnapshot(
                timestamp=time.time(),
                system_status=SystemStatus(**system_status),
                devices=devices,
                config_hash=config_hash,
                event_count=counters.get('events_processed', 0),
                error_count=counters.get('errors_occurred', 0)
            )

            self._state_history.append(snapshot)
            if len(self._state_history) > self._max_history_size:
                self._state_history.pop(0)

            return snapshot

    def get_snapshot_history(self, limit: Optional[int] = None) -> List[StateSnapshot]:
        """获取状态快照历史"""
        with self._lock:
            history = self._state_history.copy()
            if limit:
                history = history[-limit:]
            return history

    def _calculate_config_hash(self) -> str:
        """计算配置哈希"""
        config_str = json.dumps(self.get_state('config', {}), sort_keys=True)
        return hash(config_str)

    def _setup_auto_save(self) -> None:
        """设置自动保存"""
        # 定期检查是否需要自动保存
        self._auto_save_timer = QTimer()
        self._auto_save_timer.timeout.connect(self._check_auto_save)
        self._auto_save_timer.start(5000)  # 每5秒检查一次

    def _check_auto_save(self) -> None:
        """检查是否需要自动保存"""
        current_time = time.time()
        auto_save_interval = self.get_state('config.auto_save_interval', self._auto_save_interval)

        if self._persistence_enabled and current_time - self._last_save_time >= auto_save_interval:
            self._save_state()
            self._last_save_time = current_time
            self.increment_counter('auto_saves')

    def _schedule_auto_save(self) -> None:
        """调度自动保存"""
        # 立即调度检查
        self._check_auto_save()

    def save_state(self) -> bool:
        """保存状态到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self._config_file_path), exist_ok=True)

            # 创建状态快照并保存
            snapshot = self.create_snapshot()

            with open(self._config_file_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False)

            info(f"State saved to {self._config_file_path}", "STATE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to save state: {e}", "STATE_MANAGER")
            return False

    def load_state(self) -> bool:
        """从文件加载状态"""
        try:
            if not os.path.exists(self._config_file_path):
                info(f"State file not found: {self._config_file_path}", "STATE_MANAGER")
                return False

            with open(self._config_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            snapshot = StateSnapshot.from_dict(data)

            # 恢复状态
            self._state.update({
                'system': asdict(snapshot.system_status),
                'devices': snapshot.devices,
                'config': {
                    'last_modified': snapshot.timestamp,
                    'config_version': '1.0',
                    'auto_save_interval': self.get_state('config.auto_save_interval', self._auto_save_interval)
                },
                'counters': {
                    'events_processed': snapshot.event_count,
                    'errors_occurred': snapshot.error_count
                }
            })

            self._last_save_time = time.time()
            info(f"State loaded from {self._config_file_path}", "STATE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to load state: {e}", "STATE_MANAGER")
            return False

    def enable_persistence(self, enabled: bool = True) -> None:
        """启用或禁用状态持久化"""
        self._persistence_enabled = enabled
        info(f"State persistence {'enabled' if enabled else 'disabled'}", "STATE_MANAGER")

    def set_auto_save_interval(self, interval: float) -> None:
        """设置自动保存间隔"""
        self._auto_save_interval = interval
        self.set_state('config.auto_save_interval', interval)

    def clear_history(self) -> None:
        """清空状态历史"""
        with self._lock:
            self._state_history.clear()
        info("State history cleared", "STATE_MANAGER")

    def export_state(self, file_path: str) -> bool:
        """导出状态到文件"""
        try:
            snapshot = self.create_snapshot()

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False)

            info(f"State exported to {file_path}", "STATE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to export state: {e}", "STATE_MANAGER")
            return False

    def import_state(self, file_path: str) -> bool:
        """从文件导入状态"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            snapshot = StateSnapshot.from_dict(data)

            # 恢复状态
            self._state.update({
                'system': asdict(snapshot.system_status),
                'devices': snapshot.devices,
                'config': {
                    'last_modified': snapshot.timestamp,
                    'config_version': '1.0',
                    'auto_save_interval': self.get_state('config.auto_save_interval', self._auto_save_interval)
                },
                'counters': {
                    'events_processed': snapshot.event_count,
                    'errors_occurred': snapshot.error_count
                }
            })

            self._notify_all_subscribers()
            info(f"State imported from {file_path}", "STATE_MANAGER")
            return True

        except Exception as e:
            error(f"Failed to import state: {e}", "STATE_MANAGER")
            return False

    def _notify_all_subscribers(self) -> None:
        """通知所有订阅者"""
        # 这里可以广播全局状态变更事件
        pass

    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        return {
            'devices': {
                'total': self.get_state('system.total_devices', 0),
                'connected': self.get_state('system.connected_devices', 0),
                'by_type': {
                    'camera': len(self.get_devices_by_type(DeviceType.CAMERA)),
                    'robot': len(self.get_devices_by_type(DeviceType.ROBOT)),
                    'light': len(self.get_devices_by_type(DeviceType.LIGHT))
                }
            },
            'system': self.get_state('system'),
            'performance': self.get_state('performance'),
            'counters': self.get_state('counters')
        }


# 全局状态管理器实例
_global_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """获取全局状态管理器实例"""
    global _global_state_manager
    if _global_state_manager is None:
        _global_state_manager = StateManager()
        # 尝试加载已保存的状态
        _global_state_manager.load_state()
    return _global_state_manager