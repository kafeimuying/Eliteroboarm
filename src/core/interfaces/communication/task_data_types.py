import numpy as np
import time
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "等待中"
    RUNNING = "执行中"
    SUCCESS = "成功"
    FAILED = "失败"
    CANCELLED = "已取消"


class TaskState(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

    def is_active(self) -> bool:
        """检查是否为活动状态"""
        return self in [self.RUNNING, self.PAUSED]

    def is_finished(self) -> bool:
        """检查是否为结束状态"""
        return self in [self.COMPLETED, self.FAILED, self.CANCELLED, self.TIMEOUT]
    

@dataclass
class Task:
    """系统任务"""
    task_id: str
    task_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    state: TaskState = TaskState.PENDING
    created_time: float = field(default_factory=time.time)
    started_time: Optional[float] = None
    completed_time: Optional[float] = None
    error_message: Optional[str] = None
    timeout: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务ID

    def __post_init__(self):
        """生成任务ID"""
        if not self.task_id:
            import uuid
            self.task_id = str(uuid.uuid4())

    def start(self):
        """开始任务"""
        self.state = TaskState.RUNNING
        self.started_time = time.time()

    def complete(self):
        """完成任务"""
        self.state = TaskState.COMPLETED
        self.completed_time = time.time()

    def fail(self, error_message: str):
        """任务失败"""
        self.state = TaskState.FAILED
        self.error_message = error_message
        self.completed_time = time.time()

    def cancel(self):
        """取消任务"""
        self.state = TaskState.CANCELLED
        self.completed_time = time.time()

    def is_timeout(self) -> bool:
        """检查是否超时"""
        if self.timeout is None or self.started_time is None:
            return False
        return time.time() - self.started_time > self.timeout

    def get_duration(self) -> float:
        """获取任务执行时间"""
        if self.started_time is None:
            return 0.0
        end_time = self.completed_time or time.time()
        return end_time - self.started_time

    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return (self.state == TaskState.FAILED and
                self.retry_count < self.max_retries)

    def retry(self):
        """重试任务"""
        if self.can_retry():
            self.retry_count += 1
            self.state = TaskState.PENDING
            self.started_time = None
            self.completed_time = None
            self.error_message = None