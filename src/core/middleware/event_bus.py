"""
硬件事件总线
统一管理应用内的硬件事件通信，提供解耦的异步事件机制
使用强类型DTO对象替代字典，提供类型安全和IDE智能提示
"""

from ..managers.log_manager import info, debug, error, warning
from typing import Callable, Dict, List, Optional, Set, Union, Any
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal
import threading
import warnings
import time
from abc import ABC, abstractmethod

from .types_dto import HardwareEvent, HardwareEventType



class HardwareEventBus(QObject):
    """硬件事件总线 - 单例模式"""

    # 统一硬件信号：所有硬件事件都通过这一个信号发送
    signal_hardware_event = pyqtSignal(HardwareEvent)

    # 调试信号：用于日志记录和监控
    signal_debug_event = pyqtSignal(str)  # 事件描述字符串

    _instance = None
    _initialized = False

    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化硬件事件总线"""
        if not self._initialized:
            super().__init__()
            self._global_handlers: List[Callable[[HardwareEvent], None]] = []
            self._event_history: List[HardwareEvent] = []
            self._max_history_size = 1000
            self._lock = threading.RLock()
            self._enabled = True

            HardwareEventBus._initialized = True
            info("HardwareEventBus initialized", "EVENT_BUS")

    @classmethod
    def get_instance(cls) -> 'HardwareEventBus':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = HardwareEventBus()
        return cls._instance

    def subscribe_all(self, handler: Callable[[HardwareEvent], None]) -> None:
        """订阅所有硬件事件"""
        with self._lock:
            self._global_handlers.append(handler)

        debug(f"订阅所有硬件事件: {handler.__name__}", "EVENT_BUS")

    def unsubscribe_all(self, handler: Callable[[HardwareEvent], None]) -> None:
        """取消订阅所有硬件事件"""
        with self._lock:
            try:
                self._global_handlers.remove(handler)
                debug(f"取消订阅所有硬件事件: {handler.__name__}", "EVENT_BUS")
            except ValueError:
                warning(f"未找到全局事件处理器: {handler.__name__}", "EVENT_BUS")

    def publish(self, event: HardwareEvent) -> None:
        """发布硬件事件"""
        if not self._enabled:
            warning("硬件事件总线已禁用，事件被忽略", "EVENT_BUS")
            return

        # 记录事件历史
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history_size:
                self._event_history.pop(0)

        # 发布Qt信号 - 这是主要的通信方式
        self.signal_hardware_event.emit(event)

        # 发送调试信号
        self.signal_debug_event.emit(f"[{event.event_type.value}] {event.message}")

        # 处理全局处理器
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                error(f"全局硬件事件处理器错误 {handler.__name__}: {e}", "EVENT_BUS")

        # 记录事件日志
        debug(f"硬件事件已发布: {event.event_type.value} from {event.source}", "EVENT_BUS")

    def publish_camera_connected(self, source: str, camera_connection_info):
        """发布相机连接事件 - 便捷方法"""
        from .types_dto import create_camera_connected_event
        self.publish(create_camera_connected_event(source, camera_connection_info))

    def publish_camera_disconnected(self, source: str, camera_connection_info):
        """发布相机断开事件 - 便捷方法"""
        from .types_dto import create_camera_disconnected_event
        self.publish(create_camera_disconnected_event(source, camera_connection_info))

    def publish_camera_frame(self, source: str, frame_info):
        """发布相机帧捕获事件 - 便捷方法"""
        from .types_dto import create_camera_frame_event
        self.publish(create_camera_frame_event(source, frame_info))

    def publish_robot_connected(self, source: str, robot_connection_info):
        """发布机械臂连接事件 - 便捷方法"""
        from .types_dto import create_robot_connected_event
        self.publish(create_robot_connected_event(source, robot_connection_info))

    def publish_robot_position(self, source: str, position_info):
        """发布机械臂位置变化事件 - 便捷方法"""
        from .types_dto import create_robot_position_event
        self.publish(create_robot_position_event(source, position_info))

    def publish_hardware_error(self, source: str, error_info):
        """发布硬件错误事件 - 便捷方法"""
        from .types_dto import create_hardware_error_event
        self.publish(create_hardware_error_event(source, error_info))

    def get_event_history(self, event_type: Optional[HardwareEventType] = None,
                          limit: Optional[int] = None) -> List[HardwareEvent]:
        """获取硬件事件历史"""
        with self._lock:
            history = self._event_history.copy()

            if event_type:
                history = [e for e in history if e.event_type == event_type]

            if limit:
                history = history[-limit:]

            return history

    def get_camera_events(self, limit: Optional[int] = None) -> List[HardwareEvent]:
        """获取相机相关事件"""
        return [e for e in self.get_event_history(limit=limit) if e.is_camera_event()]

    def get_robot_events(self, limit: Optional[int] = None) -> List[HardwareEvent]:
        """获取机械臂相关事件"""
        return [e for e in self.get_event_history(limit=limit) if e.is_robot_event()]

    def get_error_events(self, limit: Optional[int] = None) -> List[HardwareEvent]:
        """获取错误相关事件"""
        return [e for e in self.get_event_history(limit=limit) if e.is_error_event()]

    def clear_history(self) -> None:
        """清空事件历史"""
        with self._lock:
            self._event_history.clear()
        info("硬件事件历史已清空", "EVENT_BUS")

    def set_enabled(self, enabled: bool) -> None:
        """启用或禁用事件总线"""
        self._enabled = enabled
        info(f"硬件事件总线 {'已启用' if enabled else '已禁用'}", "EVENT_BUS")

    def get_stats(self) -> Dict[str, any]:
        """获取事件总线统计信息"""
        with self._lock:
            return {
                'enabled': self._enabled,
                'global_handlers_count': len(self._global_handlers),
                'history_size': len(self._event_history),
                'max_history_size': self._max_history_size,
                'camera_events_count': len(self.get_camera_events()),
                'robot_events_count': len(self.get_robot_events()),
                'error_events_count': len(self.get_error_events())
            }


# ==================== 便捷函数 ====================

def get_hardware_event_bus() -> HardwareEventBus:
    """获取硬件事件总线实例"""
    return HardwareEventBus.get_instance()


def subscribe_all_hardware_events(handler: Callable[[HardwareEvent], None]) -> None:
    """订阅所有硬件事件的便捷函数"""
    get_hardware_event_bus().subscribe_all(handler)


def get_hardware_event_history(event_type: Optional[HardwareEventType] = None,
                              limit: Optional[int] = None) -> List[HardwareEvent]:
    """获取硬件事件历史的便捷函数"""
    return get_hardware_event_bus().get_event_history(event_type, limit)


# ==================== 向后兼容性支持 ====================
# 为了保持与现有代码的兼容性，提供旧的事件系统类

class EventType:
    """已弃用：旧的事件类型枚举，请使用HardwareEventType"""
    APPLICATION_READY = "application_ready"
    ALGORITHM_STARTED = "algorithm_started"
    ALGORITHM_COMPLETED = "algorithm_completed"
    ALGORITHM_ERROR = "algorithm_error"
    VISION_RESULT_READY = "vision_result_ready"


class EventHandler(ABC):
    """已弃用：旧的事件处理器抽象基类，请使用HardwareEventBus"""

    @abstractmethod
    def handle(self, event: 'Event') -> None:
        """处理事件"""
        pass




@dataclass
class Event:
    """已弃用：旧的事件类，请使用HardwareEvent"""
    type: str
    data: Any
    source: str
    timestamp: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
        if self.metadata is None:
            self.metadata = {}


class EventBus(QObject):
    """已弃用：旧的事件总线类，请使用HardwareEventBus"""

    event_occurred = pyqtSignal(object)

    def __init__(self):
        warnings.warn("EventBus is deprecated, use HardwareEventBus instead",
                      DeprecationWarning, stacklevel=2)
        super().__init__()
        self._handlers = {}
        self._global_handlers = []

    def publish(self, event_type: str, data: Any, source: str = "unknown",
                metadata: Optional[Dict[str, Any]] = None) -> None:
        """发布事件 - 已弃用"""
        warnings.warn("EventBus.publish is deprecated, use HardwareEventBus instead",
                      DeprecationWarning, stacklevel=2)

        event = Event(
            type=event_type,
            data=data,
            source=source,
            timestamp=time.time(),
            metadata=metadata or {}
        )

        self.event_occurred.emit(event)

    def subscribe_all(self, handler: Callable) -> None:
        """订阅所有事件 - 已弃用"""
        warnings.warn("EventBus.subscribe_all is deprecated, use HardwareEventBus instead",
                      DeprecationWarning, stacklevel=2)
        self._global_handlers.append(handler)

    def get_event_history(self, event_type: Optional[str] = None,
                          limit: Optional[int] = None) -> List[Event]:
        """获取事件历史 - 已弃用"""
        warnings.warn("EventBus.get_event_history is deprecated", DeprecationWarning, stacklevel=2)
        return []


# 向后兼容的便捷函数
def get_event_bus() -> EventBus:
    """已弃用：获取旧的事件总线实例，请使用get_hardware_event_bus()"""
    warnings.warn("get_event_bus is deprecated, use get_hardware_event_bus instead",
                  DeprecationWarning, stacklevel=2)
    return EventBus()


def publish(event_type: str, data: Any, source: str = "unknown",
           metadata: Optional[Dict[str, Any]] = None) -> None:
    """已弃用：发布事件的便捷函数，请使用HardwareEventBus的方法"""
    warnings.warn("publish is deprecated, use get_hardware_event_bus().publish() instead",
                  DeprecationWarning, stacklevel=2)
    get_event_bus().publish(event_type, data, source, metadata)


def subscribe(event_type: str, handler: EventHandler) -> None:
    """已弃用：订阅事件的便捷函数，请使用HardwareEventBus的方法"""
    warnings.warn("subscribe is deprecated, use HardwareEventBus methods instead",
                  DeprecationWarning, stacklevel=2)
    # 简化实现，不实际订阅
    pass


def unsubscribe(event_type: str, handler: EventHandler) -> None:
    """已弃用：取消订阅事件的便捷函数，请使用HardwareEventBus的方法"""
    warnings.warn("unsubscribe is deprecated, use HardwareEventBus methods instead",
                  DeprecationWarning, stacklevel=2)
    # 简化实现，不实际取消订阅
    pass


def get_event_history(event_type: Optional[str] = None, limit: Optional[int] = None) -> List['Event']:
    """已弃用：获取事件历史的便捷函数，请使用HardwareEventBus的方法"""
    warnings.warn("get_event_history is deprecated, use HardwareEventBus methods instead",
                  DeprecationWarning, stacklevel=2)
    return []