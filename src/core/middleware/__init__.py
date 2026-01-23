"""
Middleware模块 - 中间件层
提供统一的数据传输、状态管理、事件通信和核心服务
"""

from ..managers.log_manager import info

from .event_bus import (
    EventBus, EventType, Event, EventHandler,
    get_event_bus, publish, subscribe, unsubscribe,
    get_event_history
)

# 注释掉旧的dto导入，因为已重命名为types_dto
# from .dto import (
#     DeviceType, ConnectionStatus, MotionMode,
#     DeviceInfo, ConnectionInfo, CameraInfo, RobotInfo,
#     LightChannelInfo, LightPreset, FrameData, SystemStatus,
#     AlgorithmResult, VisionResult, PathPoint, RobotPath,
#     ConfigChange, PerformanceMetric, ErrorReport, UserAction,
#     StateSubscriber, DTOValidator, DTOConverter,
#     DeviceInfoValidator, DeviceInfoConverter,
#     create_device_info, create_connection_info,
#     create_frame_data, create_algorithm_result
# )

from .state_manager import (
    StateManager, StateChangeEvent, StateSnapshot,
    StateSubscriber, get_state_manager
)

from .data_report_service import (
    DataReportService, DataReporter, ReportConfig, ReportData,
    ReportType, ReportFrequency,
    FileDataReporter, WebSocketDataReporter, BatchProcessor,
    get_data_report_service, add_report_config, remove_report_config,
    get_report_service_status
)

from .core_engine_service import (
    CoreEngineService, VisionAlgorithm, AlgorithmStatus,
    TaskPriority, ExecutionMode, AlgorithmConfig,
    ProcessingTask, PipelineConfig, TaskScheduler, Pipeline,
    ObjectDetectionAlgorithm, ImageClassificationAlgorithm,
    get_core_engine_service, process_frame, get_algorithm_status,
    get_all_algorithms_status
)

__all__ = [
    # Event Bus
    'EventBus', 'EventType', 'Event', 'EventHandler',
    'get_event_bus', 'publish', 'subscribe', 'unsubscribe',
    'get_event_history',

    # State Manager
    'StateManager', 'StateChangeEvent', 'StateSnapshot',
    'get_state_manager',

    # Data Report Service
    'DataReportService', 'DataReporter', 'ReportConfig', 'ReportData',
    'ReportType', 'ReportFrequency', 
    'FileDataReporter', 'WebSocketDataReporter', 'BatchProcessor',
    'get_data_report_service', 'add_report_config', 'remove_report_config',
    'get_report_service_status',

    # Core Engine Service
    'CoreEngineService', 'VisionAlgorithm', 'AlgorithmStatus',
    'TaskPriority', 'ExecutionMode', 'AlgorithmConfig',
    'ProcessingTask', 'PipelineConfig', 'TaskScheduler', 'Pipeline',
    'ObjectDetectionAlgorithm', 'ImageClassificationAlgorithm',
    'get_core_engine_service', 'process_frame', 'get_algorithm_status',
    'get_all_algorithms_status'
]

# 版本信息
__version__ = '1.0.0'
__author__ = 'Robot Control System'

# 模块级别的初始化
def initialize_middleware():
    """初始化中间件模块"""
    # 初始化全局事件总线
    event_bus = get_event_bus()

    # 初始化全局状态管理器
    state_manager = get_state_manager()

    # 初始化数据报告服务
    data_report_service = get_data_report_service()

    # 初始化核心引擎服务
    core_engine = get_core_engine_service()

    # 发布中间件初始化完成事件
    event_bus.publish(
        EventType.APPLICATION_READY,
        {
            'middleware_version': __version__,
            'components': [
                'event_bus',
                'state_manager',
                'data_report_service',
                'core_engine_service'
            ]
        },
        'middleware'
    )

    return {
        'event_bus': event_bus,
        'state_manager': state_manager,
        'data_report_service': data_report_service,
        'core_engine': core_engine
    }

def get_middleware_status() -> dict:
    """获取中间件模块状态"""
    return {
        'version': __version__,
        'components': {
            'event_bus': get_event_bus().get_stats(),
            'state_manager': get_state_manager().get_state_summary(),
            'data_report_service': get_report_service_status(),
            'core_engine': get_all_algorithms_status()
        }
    }

def shutdown_middleware():
    """关闭中间件模块"""
    # 关闭核心引擎服务
    core_engine = get_core_engine_service()
    core_engine.shutdown()

    # 关闭数据报告服务
    data_report_service = get_data_report_service()
    data_report_service.cleanup()

    # 启用状态持久化并保存状态
    state_manager = get_state_manager()
    state_manager.enable_persistence(True)
    state_manager.save_state()

    # 禁用事件总线
    event_bus = get_event_bus()
    event_bus.set_enabled(False)

    info("Middleware shutdown completed", "MIDDLEWARE")