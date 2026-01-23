"""
数据报告服务接口
监听EventBus事件并基于DTO进行数据额外发送和处理
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import time
import json
import threading
from queue import Queue, Empty
from datetime import datetime

from ..managers.log_manager import info, debug, error, warning

from .event_bus import EventBus, EventType, Event, get_event_bus
from .types_dto import (
    DeviceInfo, ConnectionInfo, FrameData, AlgorithmResult, VisionResult,
    PerformanceMetric, ErrorReport, UserAction, SystemStatus
)


class ReportType(Enum):
    """报告类型枚举"""
    HTTP_POST = "http_post"
    WEB_SOCKET = "web_socket"
    FILE_EXPORT = "file_export"
    DATABASE = "database"
    EMAIL = "email"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class ReportFrequency(Enum):
    """报告频率枚举"""
    REAL_TIME = "real_time"       # 实时报告
    BATCH = "batch"               # 批量报告
    SCHEDULED = "scheduled"       # 定时报告
    ON_DEMAND = "on_demand"       # 按需报告
    EVENT_DRIVEN = "event_driven" # 事件驱动


@dataclass
class ReportConfig:
    """报告配置"""
    report_id: str
    name: str
    report_type: ReportType
    frequency: ReportFrequency
    enabled: bool = True
    endpoint: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    file_path: Optional[str] = None
    batch_size: int = 10
    retry_count: int = 3
    timeout_seconds: float = 5.0
    filter_events: Optional[List[EventType]] = None
    custom_handler: Optional[Callable] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ReportData:
    """报告数据"""
    report_id: str
    timestamp: float
    event_type: EventType
    data: Any
    processed_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None


class DataReporter(ABC):
    """数据报告器抽象基类"""

    @abstractmethod
    def report(self, data: ReportData) -> bool:
        """发送报告数据"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查报告器是否可用"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取报告器状态"""
        pass


class FileDataReporter(DataReporter):
    """文件数据报告器"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._status = {
            'success_count': 0,
            'error_count': 0,
            'last_success': None,
            'last_error': None
        }

    def report(self, data: ReportData) -> bool:
        try:
            with self._lock:
                with open(self.file_path, 'a', encoding='utf-8') as f:
                    report_entry = {
                        'timestamp': data.timestamp,
                        'report_id': data.report_id,
                        'event_type': data.event_type.value,
                        'data': data.data,
                        'processed_count': data.processed_count,
                        'error_count': data.error_count
                    }
                    f.write(json.dumps(report_entry, ensure_ascii=False) + '\n')
                    f.flush()

            self._status['success_count'] += 1
            self._status['last_success'] = time.time()
            return True

        except Exception as e:
            self._status['error_count'] += 1
            self._status['last_error'] = str(e)
            error(f"Failed to write file report: {e}", "DATA_REPORT")
            return False

    def is_available(self) -> bool:
        try:
            # 检查文件是否可写
            import os
            directory = os.path.dirname(self.file_path)
            return os.access(directory, os.W_OK) if directory else True
        except:
            return False

    def get_status(self) -> Dict[str, Any]:
        return {
            'file_path': self.file_path,
            'available': self.is_available(),
            **self._status
        }


class WebSocketDataReporter(DataReporter):
    """WebSocket数据报告器"""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._connection = None
        self._status = {
            'connected': False,
            'success_count': 0,
            'error_count': 0,
            'last_success': None,
            'last_error': None
        }

    def report(self, data: ReportData) -> bool:
        try:
            if not self._ensure_connection():
                return False

            payload = {
                'type': 'data_report',
                'data': {
                    'report_id': data.report_id,
                    'timestamp': data.timestamp,
                    'event_type': data.event_type.value,
                    'data': data.data
                }
            }

            self._connection.send(json.dumps(payload))
            self._status['success_count'] += 1
            self._status['last_success'] = time.time()
            return True

        except Exception as e:
            self._status['error_count'] += 1
            self._status['last_error'] = str(e)
            error(f"Failed to send WebSocket report: {e}", "DATA_REPORT")
            return False

    def _ensure_connection(self) -> bool:
        # WebSocket连接管理逻辑（简化版本）
        # 实际实现需要使用websocket-client库
        return True

    def is_available(self) -> bool:
        return self._status.get('connected', False)

    def get_status(self) -> Dict[str, Any]:
        return {
            'endpoint': self.endpoint,
            **self._status
        }


class BatchProcessor:
    """批量数据处理器"""

    def __init__(self, batch_size: int = 10, flush_interval: float = 30.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue = Queue()
        self._batch_data: List[ReportData] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._reporters: List[DataReporter] = []

    def add_reporter(self, reporter: DataReporter):
        """添加报告器"""
        self._reporters.append(reporter)

    def add_data(self, data: ReportData):
        """添加报告数据到批次"""
        self._queue.put(data)

    def process_batch(self):
        """处理批量数据"""
        while True:
            try:
                # 收集批次数据
                batch = []
                while len(batch) < self.batch_size:
                    try:
                        data = self._queue.get(timeout=1.0)
                        batch.append(data)
                    except Empty:
                        break

                if not batch:
                    continue

                # 发送到所有报告器
                for reporter in self._reporters:
                    for data in batch:
                        success = reporter.report(data)
                        if not success:
                            data.error_count += 1
                        data.processed_count += 1

                info(f"Processed batch of {len(batch)} reports", "DATA_REPORT")

            except Exception as e:
                error(f"Error in batch processing: {e}", "DATA_REPORT")


class DataReportService:
    """数据报告服务"""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or get_event_bus()
        self._reporters: Dict[str, DataReporter] = {}
        self._configs: Dict[str, ReportConfig] = {}
        self._batch_processors: Dict[str, BatchProcessor] = {}
        self._event_handlers: Dict[EventType, List[Callable]] = {}
        self._enabled = True
        self._lock = threading.Lock()

        # 启动后台处理线程
        self._processing_thread = threading.Thread(target=self._process_background, daemon=True)
        self._processing_thread.start()

        info("DataReportService initialized", "DATA_REPORT")

    def add_report_config(self, config: ReportConfig) -> bool:
        """添加报告配置"""
        try:
            with self._lock:
                self._configs[config.report_id] = config

                # 创建报告器
                reporter = self._create_reporter(config)
                if reporter:
                    self._reporters[config.report_id] = reporter

                    # 为批量报告创建批量处理器
                    if config.frequency == ReportFrequency.BATCH:
                        batch_processor = BatchProcessor(
                            batch_size=config.batch_size,
                            flush_interval=30.0
                        )
                        batch_processor.add_reporter(reporter)
                        self._batch_processors[config.report_id] = batch_processor
                        # 启动批量处理线程
                        threading.Thread(
                            target=batch_processor.process_batch,
                            daemon=True
                        ).start()

                    # 订阅相关事件
                    self._subscribe_events(config)

            info(f"Report config added: {config.report_id}", "DATA_REPORT")
            return True

        except Exception as e:
            error(f"Failed to add report config: {e}", "DATA_REPORT")
            return False

    def remove_report_config(self, report_id: str) -> bool:
        """移除报告配置"""
        try:
            with self._lock:
                if report_id in self._configs:
                    config = self._configs[report_id]

                    # 取消事件订阅
                    self._unsubscribe_events(config)

                    # 清理资源
                    self._reporters.pop(report_id, None)
                    self._batch_processors.pop(report_id, None)
                    self._configs.pop(report_id, None)

            info(f"Report config removed: {report_id}", "DATA_REPORT")
            return True

        except Exception as e:
            error(f"Failed to remove report config: {e}", "DATA_REPORT")
            return False

    def _create_reporter(self, config: ReportConfig) -> Optional[DataReporter]:
        """创建数据报告器"""
        try:

            if config.report_type == ReportType.FILE_EXPORT:
                return FileDataReporter(file_path=config.file_path)
            elif config.report_type == ReportType.WEB_SOCKET:
                return WebSocketDataReporter(endpoint=config.endpoint)
            elif config.report_type == ReportType.CUSTOM and config.custom_handler:
                # 自定义报告器
                return config.custom_handler()
            else:
                warning(f"Unsupported report type: {config.report_type}", "DATA_REPORT")
                return None

        except Exception as e:
            error(f"Failed to create reporter: {e}", "DATA_REPORT")
            return None

    def _subscribe_events(self, config: ReportConfig):
        """订阅相关事件"""
        event_types = config.filter_events or [EventType.ANY]

        for event_type in event_types:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
                self.event_bus.subscribe(event_type, self)

            self._event_handlers[event_type].append(config.report_id)

    def _unsubscribe_events(self, config: ReportConfig):
        """取消事件订阅"""
        event_types = config.filter_events or [EventType.ANY]

        for event_type in event_types:
            if event_type in self._event_handlers:
                if config.report_id in self._event_handlers[event_type]:
                    self._event_handlers[event_type].remove(config.report_id)

                if not self._event_handlers[event_type]:
                    del self._event_handlers[event_type]

    def handle(self, event: Event) -> None:
        """处理事件"""
        if not self._enabled:
            return

        # 查找相关配置
        if event.type in self._event_handlers:
            for report_id in self._event_handlers[event.type]:
                config = self._configs.get(report_id)
                if config and config.enabled:
                    self._process_event(config, event)

    def _process_event(self, config: ReportConfig, event: Event):
        """处理事件数据"""
        try:
            # 创建报告数据
            report_data = ReportData(
                report_id=config.report_id,
                timestamp=event.timestamp,
                event_type=event.type,
                data=self._extract_relevant_data(event),
                processed_count=0,
                error_count=0
            )

            # 根据频率处理
            if config.frequency == ReportFrequency.REAL_TIME:
                # 实时处理
                reporter = self._reporters.get(config.report_id)
                if reporter:
                    reporter.report(report_data)

            elif config.frequency == ReportFrequency.BATCH:
                # 批量处理
                batch_processor = self._batch_processors.get(config.report_id)
                if batch_processor:
                    batch_processor.add_data(report_data)

            elif config.frequency == ReportFrequency.EVENT_DRIVEN:
                # 事件驱动
                self._handle_event_driven_report(config, event, report_data)

        except Exception as e:
            error(f"Error processing event for report {config.report_id}: {e}", "DATA_REPORT")

    def _extract_relevant_data(self, event: Event) -> Dict[str, Any]:
        """提取相关数据"""
        # 根据事件类型提取相关数据
        extracted_data = {
            'event_source': event.source,
            'event_metadata': event.metadata
        }

        # 处理特定类型的数据
        if hasattr(event.data, '__dict__'):
            # 如果是DTO对象，转换为字典
            extracted_data.update({
                key: getattr(event.data, key)
                for key in dir(event.data)
                if not key.startswith('_')
            })
        else:
            extracted_data['raw_data'] = event.data

        return extracted_data

    def _handle_event_driven_report(self, config: ReportConfig, event: Event, report_data: ReportData):
        """处理事件驱动报告"""
        # 根据事件类型进行特定处理
        if event.type == EventType.ALGORITHM_COMPLETED:
            self._handle_algorithm_completed(config, event, report_data)
        elif event.type == EventType.VISION_RESULT_READY:
            self._handle_vision_result_ready(config, event, report_data)
        elif event.type == EventType.HARDWARE_ERROR:
            self._handle_hardware_error(config, event, report_data)

    def _handle_algorithm_completed(self, config: ReportConfig, event: Event, report_data: ReportData):
        """处理算法完成事件"""
        if isinstance(event.data, AlgorithmResult):
            result = event.data
            report_data.data.update({
                'algorithm_id': result.algorithm_id,
                'algorithm_type': result.algorithm_type,
                'status': result.status,
                'confidence': result.confidence,
                'processing_time_ms': result.processing_time_ms
            })

        # 发送报告
        reporter = self._reporters.get(config.report_id)
        if reporter:
            reporter.report(report_data)

    def _handle_vision_result_ready(self, config: ReportConfig, event: Event, report_data: ReportData):
        """处理视觉结果就绪事件"""
        if isinstance(event.data, VisionResult):
            result = event.data
            report_data.data.update({
                'detections_count': len(result.detections),
                'classifications_count': len(result.classifications),
                'confidence': result.confidence,
                'processing_time_ms': result.processing_time_ms
            })

        # 发送报告
        reporter = self._reporters.get(config.report_id)
        if reporter:
            reporter.report(report_data)

    def _handle_hardware_error(self, config: ReportConfig, event: Event, report_data: ReportData):
        """处理硬件错误事件"""
        # 硬件错误需要立即报告
        reporter = self._reporters.get(config.report_id)
        if reporter:
            reporter.report(report_data)

    def _process_background(self):
        """后台处理任务"""
        while True:
            try:
                # 定时任务，如状态检查、重连等
                time.sleep(60)  # 每分钟执行一次
                self._background_maintenance()

            except Exception as e:
                error(f"Error in background processing: {e}", "DATA_REPORT")

    def _background_maintenance(self):
        """后台维护任务"""
        # 检查报告器状态
        for report_id, reporter in self._reporters.items():
            if not reporter.is_available():
                warning(f"Reporter {report_id} is not available", "DATA_REPORT")

    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'enabled': self._enabled,
            'configs_count': len(self._configs),
            'reporters_count': len(self._reporters),
            'batch_processors_count': len(self._batch_processors),
            'event_handlers_count': len(self._event_handlers),
            'reporters_status': {
                report_id: reporter.get_status()
                for report_id, reporter in self._reporters.items()
            }
        }

    def set_enabled(self, enabled: bool):
        """启用或禁用服务"""
        self._enabled = enabled
        info(f"DataReportService {'enabled' if enabled else 'disabled'}", "DATA_REPORT")

    def cleanup(self):
        """清理资源"""
        self.set_enabled(False)
        info("DataReportService cleaned up", "DATA_REPORT")


# 全局数据报告服务实例
_global_data_report_service: Optional[DataReportService] = None


def get_data_report_service() -> DataReportService:
    """获取全局数据报告服务实例"""
    global _global_data_report_service
    if _global_data_report_service is None:
        _global_data_report_service = DataReportService()
    return _global_data_report_service


# 便捷函数
def add_report_config(config: ReportConfig) -> bool:
    """添加报告配置的便捷函数"""
    return get_data_report_service().add_report_config(config)


def remove_report_config(report_id: str) -> bool:
    """移除报告配置的便捷函数"""
    return get_data_report_service().remove_report_config(report_id)


def get_report_service_status() -> Dict[str, Any]:
    """获取报告服务状态的便捷函数"""
    return get_data_report_service().get_service_status()