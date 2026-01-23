"""
核心引擎服务
集成视觉算法处理、任务调度和系统协调功能
"""

from ..managers.log_manager import info, debug, error, warning
from typing import Any, Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, Future
import numpy as np
from pathlib import Path

from .event_bus import EventBus, EventType, Event, get_event_bus
from .types_dto import (
    DeviceInfo, FrameData, AlgorithmResult, VisionResult,
    PerformanceMetric, ErrorReport, RobotInfo, CameraInfo, LightChannelInfo
)

# 使用log_manager替代标准logging


class AlgorithmStatus(Enum):
    """算法状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"
    STOPPED = "stopped"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class ExecutionMode(Enum):
    """执行模式"""
    SEQUENTIAL = "sequential"  # 顺序执行
    PARALLEL = "parallel"      # 并行执行
    PIPELINE = "pipeline"      # 流水线执行


@dataclass
class AlgorithmConfig:
    """算法配置"""
    algorithm_id: str
    name: str
    algorithm_type: str
    version: str
    config_params: Dict[str, Any]
    enabled: bool = True
    priority: TaskPriority = TaskPriority.NORMAL
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    timeout_seconds: float = 30.0
    retry_count: int = 3
    memory_limit_mb: int = 1024
    gpu_required: bool = False


@dataclass
class ProcessingTask:
    """处理任务"""
    task_id: str
    algorithm_config: AlgorithmConfig
    input_data: Any
    callback: Optional[Callable] = None
    timestamp: float = 0.0
    retry_count: int = 0
    priority: TaskPriority = TaskPriority.NORMAL
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PipelineConfig:
    """流水线配置"""
    pipeline_id: str
    name: str
    algorithm_ids: List[str]
    execution_mode: ExecutionMode
    parallel_limit: int = 4
    data_dependencies: Optional[Dict[str, str]] = None


class VisionAlgorithm(ABC):
    """视觉算法抽象基类"""

    def __init__(self, algorithm_id: str, name: str):
        self.algorithm_id = algorithm_id
        self.name = name
        self._status = AlgorithmStatus.IDLE
        self._config = {}

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化算法"""
        pass

    @abstractmethod
    def process(self, input_data: Any) -> AlgorithmResult:
        """处理输入数据"""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """清理资源"""
        pass

    @abstractmethod
    def get_requirements(self) -> Dict[str, Any]:
        """获取算法需求"""
        pass

    def get_status(self) -> AlgorithmStatus:
        """获取算法状态"""
        return self._status

    def set_status(self, status: AlgorithmStatus):
        """设置算法状态"""
        self._status = status


class ObjectDetectionAlgorithm(VisionAlgorithm):
    """目标检测算法"""

    def __init__(self, algorithm_id: str, name: str = "Object Detection"):
        super().__init__(algorithm_id, name)
        self._model = None
        self._confidence_threshold = 0.5

    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self._config = config
            self._confidence_threshold = config.get('confidence_threshold', 0.5)

            # 这里应该加载实际的检测模型
            # self._model = load_detection_model(config.get('model_path'))

            self.set_status(AlgorithmStatus.IDLE)
            info(f"Object detection algorithm {self.algorithm_id} initialized", "CORE_ENGINE")
            return True

        except Exception as e:
            error(f"Failed to initialize object detection algorithm: {e}", "CORE_ENGINE")
            self.set_status(AlgorithmStatus.ERROR)
            return False

    def process(self, input_data: Any) -> AlgorithmResult:
        start_time = time.time()

        try:
            self.set_status(AlgorithmStatus.RUNNING)

            if isinstance(input_data, FrameData):
                # 处理图像帧数据
                frame_array = np.frombuffer(input_data.data, dtype=np.uint8)
                frame_array = frame_array.reshape((input_data.height, input_data.width, input_data.channels))

                # 模拟目标检测
                detections = self._simulate_detection(frame_array)

                processing_time = (time.time() - start_time) * 1000

                result = AlgorithmResult(
                    algorithm_id=self.algorithm_id,
                    algorithm_type="object_detection",
                    status="completed",
                    confidence=max([d.get('confidence', 0) for d in detections], default=0),
                    data=detections,
                    processing_time_ms=processing_time,
                    timestamp=time.time()
                )

                self.set_status(AlgorithmStatus.COMPLETED)
                return result

            else:
                raise ValueError("Invalid input data type for object detection")

        except Exception as e:
            error(f"Error in object detection processing: {e}", "CORE_ENGINE")
            self.set_status(AlgorithmStatus.ERROR)
            return AlgorithmResult(
                algorithm_id=self.algorithm_id,
                algorithm_type="object_detection",
                status="error",
                data=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )

    def cleanup(self):
        self._model = None
        self.set_status(AlgorithmStatus.IDLE)

    def get_requirements(self) -> Dict[str, Any]:
        return {
            'input_types': ['FrameData'],
            'memory_mb': 512,
            'gpu_required': False,
            'supported_formats': ['rgb24', 'bgr24']
        }

    def _simulate_detection(self, frame_array: np.ndarray) -> List[Dict[str, Any]]:
        """模拟目标检测结果"""
        # 这里返回模拟的检测结果
        return [
            {
                'class': 'object_1',
                'confidence': 0.85,
                'bbox': [100, 100, 200, 200],
                'label': 'Sample Object'
            },
            {
                'class': 'object_2',
                'confidence': 0.72,
                'bbox': [300, 150, 400, 250],
                'label': 'Another Object'
            }
        ]


class ImageClassificationAlgorithm(VisionAlgorithm):
    """图像分类算法"""

    def __init__(self, algorithm_id: str, name: str = "Image Classification"):
        super().__init__(algorithm_id, name)
        self._model = None

    def initialize(self, config: Dict[str, Any]) -> bool:
        try:
            self._config = config

            # 这里应该加载实际的分类模型
            # self._model = load_classification_model(config.get('model_path'))

            self.set_status(AlgorithmStatus.IDLE)
            info(f"Image classification algorithm {self.algorithm_id} initialized", "CORE_ENGINE")
            return True

        except Exception as e:
            error(f"Failed to initialize image classification algorithm: {e}", "CORE_ENGINE")
            self.set_status(AlgorithmStatus.ERROR)
            return False

    def process(self, input_data: Any) -> AlgorithmResult:
        start_time = time.time()

        try:
            self.set_status(AlgorithmStatus.RUNNING)

            if isinstance(input_data, FrameData):
                # 处理图像帧数据
                frame_array = np.frombuffer(input_data.data, dtype=np.uint8)
                frame_array = frame_array.reshape((input_data.height, input_data.width, input_data.channels))

                # 模拟图像分类
                classifications = self._simulate_classification(frame_array)

                processing_time = (time.time() - start_time) * 1000

                result = AlgorithmResult(
                    algorithm_id=self.algorithm_id,
                    algorithm_type="image_classification",
                    status="completed",
                    confidence=max([c.get('confidence', 0) for c in classifications], default=0),
                    data=classifications,
                    processing_time_ms=processing_time,
                    timestamp=time.time()
                )

                self.set_status(AlgorithmStatus.COMPLETED)
                return result

            else:
                raise ValueError("Invalid input data type for image classification")

        except Exception as e:
            error(f"Error in image classification processing: {e}", "CORE_ENGINE")
            self.set_status(AlgorithmStatus.ERROR)
            return AlgorithmResult(
                algorithm_id=self.algorithm_id,
                algorithm_type="image_classification",
                status="error",
                data=str(e),
                processing_time_ms=(time.time() - start_time) * 1000,
                timestamp=time.time()
            )

    def cleanup(self):
        self._model = None
        self.set_status(AlgorithmStatus.IDLE)

    def get_requirements(self) -> Dict[str, Any]:
        return {
            'input_types': ['FrameData'],
            'memory_mb': 256,
            'gpu_required': False,
            'supported_formats': ['rgb24', 'bgr24']
        }

    def _simulate_classification(self, frame_array: np.ndarray) -> List[Dict[str, Any]]:
        """模拟图像分类结果"""
        return [
            {
                'class': 'category_1',
                'confidence': 0.65,
                'label': 'Sample Category 1'
            },
            {
                'class': 'category_2',
                'confidence': 0.25,
                'label': 'Sample Category 2'
            }
        ]


class TaskScheduler:
    """任务调度器"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._task_queue = queue.PriorityQueue()
        self._running_tasks: Dict[str, Future] = {}
        self._task_status: Dict[str, AlgorithmStatus] = {}
        self._lock = threading.Lock()

    def submit_task(self, task: ProcessingTask, algorithm: VisionAlgorithm) -> Future:
        """提交任务"""
        try:
            # 创建任务优先级 (负数表示高优先级)
            priority = -task.priority.value

            with self._lock:
                self._task_status[task.task_id] = AlgorithmStatus.RUNNING

            # 提交到线程池
            future = self._executor.submit(self._execute_task, task, algorithm)

            with self._lock:
                self._running_tasks[task.task_id] = future

            # 设置完成回调
            future.add_done_callback(lambda f: self._task_completed(task.task_id, f))

            info(f"Task {task.task_id} submitted for execution", "CORE_ENGINE")
            return future

        except Exception as e:
            error(f"Failed to submit task {task.task_id}: {e}", "CORE_ENGINE")
            with self._lock:
                self._task_status[task.task_id] = AlgorithmStatus.ERROR
            return None

    def _execute_task(self, task: ProcessingTask, algorithm: VisionAlgorithm) -> AlgorithmResult:
        """执行任务"""
        try:
            info(f"Executing task {task.task_id} with algorithm {algorithm.algorithm_id}", "CORE_ENGINE")

            # 执行算法处理
            result = algorithm.process(task.input_data)

            # 调用回调函数
            if task.callback:
                task.callback(result, task.metadata)

            return result

        except Exception as e:
            error(f"Error executing task {task.task_id}: {e}", "CORE_ENGINE")
            return AlgorithmResult(
                algorithm_id=algorithm.algorithm_id,
                algorithm_type="unknown",
                status="error",
                data=str(e),
                processing_time_ms=0,
                timestamp=time.time()
            )

    def _task_completed(self, task_id: str, future: Future):
        """任务完成回调"""
        try:
            result = future.result()
            with self._lock:
                status = AlgorithmStatus.COMPLETED if result.status == "completed" else AlgorithmStatus.ERROR
                self._task_status[task_id] = status
                self._running_tasks.pop(task_id, None)

            info(f"Task {task_id} completed with status: {result.status}", "CORE_ENGINE")

        except Exception as e:
            error(f"Task {task_id} failed: {e}", "CORE_ENGINE")
            with self._lock:
                self._task_status[task_id] = AlgorithmStatus.ERROR
                self._running_tasks.pop(task_id, None)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            with self._lock:
                if task_id in self._running_tasks:
                    future = self._running_tasks[task_id]
                    cancelled = future.cancel()
                    if cancelled:
                        self._task_status[task_id] = AlgorithmStatus.STOPPED
                        self._running_tasks.pop(task_id, None)
                    return cancelled
            return False

        except Exception as e:
            error(f"Failed to cancel task {task_id}: {e}", "CORE_ENGINE")
            return False

    def get_task_status(self, task_id: str) -> Optional[AlgorithmStatus]:
        """获取任务状态"""
        with self._lock:
            return self._task_status.get(task_id)

    def get_running_tasks(self) -> Dict[str, AlgorithmStatus]:
        """获取运行中的任务"""
        with self._lock:
            return self._task_status.copy()

    def shutdown(self):
        """关闭调度器"""
        self._executor.shutdown(wait=True)
        info("Task scheduler shutdown", "CORE_ENGINE")


class Pipeline:
    """算法流水线"""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._algorithms: List[VisionAlgorithm] = []
        self._scheduler: Optional[TaskScheduler] = None

    def add_algorithm(self, algorithm: VisionAlgorithm):
        """添加算法到流水线"""
        self._algorithms.append(algorithm)

    def set_scheduler(self, scheduler: TaskScheduler):
        """设置任务调度器"""
        self._scheduler = scheduler

    def execute(self, input_data: Any, callback: Optional[Callable] = None) -> List[AlgorithmResult]:
        """执行流水线"""
        results = []
        current_data = input_data

        for algorithm in self._algorithms:
            try:
                # 创建处理任务
                task = ProcessingTask(
                    task_id=f"{self.config.pipeline_id}_{algorithm.algorithm_id}_{int(time.time())}",
                    algorithm_config=AlgorithmConfig(
                        algorithm_id=algorithm.algorithm_id,
                        name=algorithm.name,
                        algorithm_type=algorithm.__class__.__name__,
                        config_params={},
                        priority=TaskPriority.NORMAL
                    ),
                    input_data=current_data,
                    callback=callback
                )

                # 提交任务
                if self._scheduler:
                    future = self._scheduler.submit_task(task, algorithm)
                    result = future.result(timeout=30.0)
                else:
                    result = algorithm.process(current_data)

                results.append(result)

                # 更新下一级输入数据
                if result.status == "completed" and result.data:
                    current_data = result.data
                else:
                    error(f"Algorithm {algorithm.algorithm_id} failed in pipeline", "CORE_ENGINE")
                    break

            except Exception as e:
                error(f"Error in pipeline execution: {e}", "CORE_ENGINE")
                break

        return results


class CoreEngineService:
    """核心引擎服务"""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or get_event_bus()
        self._algorithms: Dict[str, VisionAlgorithm] = {}
        self._configs: Dict[str, AlgorithmConfig] = {}
        self._pipelines: Dict[str, Pipeline] = {}
        self._scheduler = TaskScheduler(max_workers=4)
        self._performance_metrics: List[PerformanceMetric] = []
        self._enabled = True
        self._lock = threading.Lock()

        # 初始化内置算法
        self._initialize_builtin_algorithms()

        # 启动性能监控
        self._start_performance_monitoring()

        info("CoreEngineService initialized", "CORE_ENGINE")

    def _initialize_builtin_algorithms(self):
        """初始化内置算法"""
        # 注册目标检测算法
        detector = ObjectDetectionAlgorithm("builtin_detector", "Built-in Object Detector")
        self.register_algorithm(detector)

        # 注册图像分类算法
        classifier = ImageClassificationAlgorithm("builtin_classifier", "Built-in Image Classifier")
        self.register_algorithm(classifier)

    def register_algorithm(self, algorithm: VisionAlgorithm) -> bool:
        """注册算法"""
        try:
            with self._lock:
                self._algorithms[algorithm.algorithm_id] = algorithm

            info(f"Algorithm registered: {algorithm.algorithm_id}", "CORE_ENGINE")
            return True

        except Exception as e:
            error(f"Failed to register algorithm {algorithm.algorithm_id}: {e}", "CORE_ENGINE")
            return False

    def unregister_algorithm(self, algorithm_id: str) -> bool:
        """注销算法"""
        try:
            with self._lock:
                if algorithm_id in self._algorithms:
                    algorithm = self._algorithms[algorithm_id]
                    algorithm.cleanup()
                    del self._algorithms[algorithm_id]

            info(f"Algorithm unregistered: {algorithm_id}", "CORE_ENGINE")
            return True

        except Exception as e:
            error(f"Failed to unregister algorithm {algorithm_id}: {e}", "CORE_ENGINE")
            return False

    def add_algorithm_config(self, config: AlgorithmConfig) -> bool:
        """添加算法配置"""
        try:
            with self._lock:
                self._configs[config.algorithm_id] = config

            # 初始化算法
            if config.algorithm_id in self._algorithms:
                algorithm = self._algorithms[config.algorithm_id]
                algorithm.initialize(config.config_params)

            info(f"Algorithm config added: {config.algorithm_id}", "CORE_ENGINE")
            return True

        except Exception as e:
            error(f"Failed to add algorithm config {config.algorithm_id}: {e}", "CORE_ENGINE")
            return False

    def process_frame(self, frame_data: FrameData, algorithm_id: str,
                     callback: Optional[Callable] = None) -> Optional[Future]:
        """处理图像帧"""
        try:
            if not self._enabled:
                warning("Core engine service is disabled", "CORE_ENGINE")
                return None

            # 获取算法
            algorithm = self._algorithms.get(algorithm_id)
            if not algorithm:
                error(f"Algorithm not found: {algorithm_id}", "CORE_ENGINE")
                return None

            # 获取配置
            config = self._configs.get(algorithm_id)
            if config and not config.enabled:
                warning(f"Algorithm {algorithm_id} is disabled", "CORE_ENGINE")
                return None

            # 创建处理任务
            task = ProcessingTask(
                task_id=f"{algorithm_id}_{int(time.time())}",
                algorithm_config=config or AlgorithmConfig(
                    algorithm_id=algorithm_id,
                    name=algorithm.name,
                    algorithm_type="unknown",
                    config_params={}
                ),
                input_data=frame_data,
                callback=callback,
                priority=config.priority if config else TaskPriority.NORMAL
            )

            # 提交任务
            future = self._scheduler.submit_task(task, algorithm)

            # 发布算法开始事件
            self.event_bus.publish(
                EventType.ALGORITHM_STARTED,
                {
                    'algorithm_id': algorithm_id,
                    'frame_id': frame_data.frame_id,
                    'task_id': task.task_id
                },
                "core_engine"
            )

            info(f"Frame processing task submitted: {task.task_id}", "CORE_ENGINE")
            return future

        except Exception as e:
            error(f"Failed to process frame: {e}", "CORE_ENGINE")
            return None

    def create_pipeline(self, config: PipelineConfig) -> Optional[Pipeline]:
        """创建算法流水线"""
        try:
            pipeline = Pipeline(config)

            # 添加算法到流水线
            for algorithm_id in config.algorithm_ids:
                algorithm = self._algorithms.get(algorithm_id)
                if algorithm:
                    pipeline.add_algorithm(algorithm)
                else:
                    error(f"Algorithm not found for pipeline: {algorithm_id}", "CORE_ENGINE")
                    return None

            # 设置调度器
            pipeline.set_scheduler(self._scheduler)

            # 注册流水线
            with self._lock:
                self._pipelines[config.pipeline_id] = pipeline

            info(f"Pipeline created: {config.pipeline_id}", "CORE_ENGINE")
            return pipeline

        except Exception as e:
            error(f"Failed to create pipeline {config.pipeline_id}: {e}", "CORE_ENGINE")
            return None

    def execute_pipeline(self, pipeline_id: str, input_data: Any,
                        callback: Optional[Callable] = None) -> List[AlgorithmResult]:
        """执行算法流水线"""
        try:
            pipeline = self._pipelines.get(pipeline_id)
            if not pipeline:
                error(f"Pipeline not found: {pipeline_id}", "CORE_ENGINE")
                return []

            results = pipeline.execute(input_data, callback)

            # 发布流水线完成事件
            self.event_bus.publish(
                EventType.ALGORITHM_COMPLETED,
                {
                    'pipeline_id': pipeline_id,
                    'results_count': len(results),
                    'success_count': sum(1 for r in results if r.status == "completed")
                },
                "core_engine"
            )

            info(f"Pipeline {pipeline_id} executed with {len(results)} results", "CORE_ENGINE")
            return results

        except Exception as e:
            error(f"Failed to execute pipeline {pipeline_id}: {e}", "CORE_ENGINE")
            return []

    def get_algorithm_status(self, algorithm_id: str) -> Optional[AlgorithmStatus]:
        """获取算法状态"""
        algorithm = self._algorithms.get(algorithm_id)
        if algorithm:
            return algorithm.get_status()
        return None

    def get_all_algorithms_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有算法状态"""
        status = {}
        for algorithm_id, algorithm in self._algorithms.items():
            status[algorithm_id] = {
                'name': algorithm.name,
                'status': algorithm.get_status().value,
                'type': algorithm.__class__.__name__
            }
        return status

    def get_running_tasks(self) -> Dict[str, AlgorithmStatus]:
        """获取运行中的任务"""
        return self._scheduler.get_running_tasks()

    def get_performance_metrics(self) -> List[PerformanceMetric]:
        """获取性能指标"""
        return self._performance_metrics.copy()

    def _start_performance_monitoring(self):
        """启动性能监控"""
        def monitor():
            while self._enabled:
                try:
                    # 收集性能指标
                    timestamp = time.time()

                    # 任务队列大小
                    queue_size = len(self._scheduler._task_queue.queue)
                    self._performance_metrics.append(
                        PerformanceMetric(
                            metric_name="task_queue_size",
                            value=float(queue_size),
                            unit="tasks",
                            timestamp=timestamp,
                            category="engine"
                        )
                    )

                    # 运行任务数
                    running_tasks = len(self._scheduler._running_tasks)
                    self._performance_metrics.append(
                        PerformanceMetric(
                            metric_name="running_tasks",
                            value=float(running_tasks),
                            unit="tasks",
                            timestamp=timestamp,
                            category="engine"
                        )
                    )

                    # 内存使用情况
                    import psutil
                    process = psutil.Process()
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    self._performance_metrics.append(
                        PerformanceMetric(
                            metric_name="memory_usage",
                            value=memory_mb,
                            unit="MB",
                            timestamp=timestamp,
                            category="system"
                        )
                    )

                    # 限制指标历史大小
                    if len(self._performance_metrics) > 1000:
                        self._performance_metrics = self._performance_metrics[-500:]

                    time.sleep(10)  # 每10秒收集一次

                except Exception as e:
                    error(f"Error in performance monitoring: {e}", "CORE_ENGINE")
                    time.sleep(10)

        # 启动监控线程
        monitoring_thread = threading.Thread(target=monitor, daemon=True)
        monitoring_thread.start()

    def set_enabled(self, enabled: bool):
        """启用或禁用服务"""
        self._enabled = enabled
        info(f"CoreEngineService {'enabled' if enabled else 'disabled'}", "CORE_ENGINE")

    def shutdown(self):
        """关闭服务"""
        self.set_enabled(False)
        self._scheduler.shutdown()

        # 清理所有算法
        for algorithm in self._algorithms.values():
            algorithm.cleanup()

        info("CoreEngineService shutdown", "CORE_ENGINE")


# 全局核心引擎服务实例
_global_core_engine: Optional[CoreEngineService] = None


def get_core_engine_service() -> CoreEngineService:
    """获取全局核心引擎服务实例"""
    global _global_core_engine
    if _global_core_engine is None:
        _global_core_engine = CoreEngineService()
    return _global_core_engine


# 便捷函数
def process_frame(frame_data: FrameData, algorithm_id: str,
                 callback: Optional[Callable] = None) -> Optional[Future]:
    """处理图像帧的便捷函数"""
    return get_core_engine_service().process_frame(frame_data, algorithm_id, callback)


def get_algorithm_status(algorithm_id: str) -> Optional[AlgorithmStatus]:
    """获取算法状态的便捷函数"""
    return get_core_engine_service().get_algorithm_status(algorithm_id)


def get_all_algorithms_status() -> Dict[str, Dict[str, Any]]:
    """获取所有算法状态的便捷函数"""
    return get_core_engine_service().get_all_algorithms_status()