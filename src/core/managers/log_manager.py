#!/usr/bin/env python3
"""
日志管理器 - 支持多文件分流 (System/Algo/Hardware/Software)
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from collections import deque
from enum import Enum
from PyQt6.QtCore import QObject, pyqtSignal

from .debug_manager import is_debug_enabled
from .app_config import AppConfigManager


class LogCategory(str, Enum):
    """日志分类枚举，对应不同的日志文件名"""
    SYSTEM = "system"       # 系统日志
    ALGO = "algo"           # 算法日志
    SOFTWARE = "software"   # 软件业务逻辑
    HARDWARE = "hardware"   # 硬件交互日志

    @classmethod
    def _missing_(cls, value):
        return cls.SYSTEM


class LogManager(QObject):
    """
    日志管理器 (单例模式) - 支持多文件分流
    """
    # 信号增加一个参数 category: (category, level, message, timestamp)
    log_added = pyqtSignal(str, str, str, str)
    
    _instance = None

    @classmethod
    def instance(cls, logs_dir=None):
        if cls._instance is None:
            cls._instance = cls(logs_dir=logs_dir)
        elif logs_dir is not None and cls._instance.logs_dir != logs_dir:
            # 如果已有实例但路径不同，需要重新创建
            cls._instance = cls(logs_dir=logs_dir)
        return cls._instance

    def __init__(self, logs_dir="./workspace/logs"):
        # Call parent constructor first to properly initialize QObject
        super().__init__()

        # Check if already initialized to prevent double initialization
        if hasattr(self, '_initialized'):
            return

        self._initialized = True

        # 配置基础目录
        if logs_dir is None:
            logs_dir = "./workspace/logs"
        self.logs_dir = Path(logs_dir) if isinstance(logs_dir, str) else logs_dir
        if self.logs_dir is None:
            self.logs_dir = Path("./workspace/logs")

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 存储所有分类的 logger 实例
        # 结构: { "system": <Logger>, "algo": <Logger>, ... }
        self.loggers: Dict[str, logging.Logger] = {}
        self._console_handler: Optional[logging.Handler] = None
        
        self.setup_loggers()

    def setup_loggers(self):
        """初始化所有分类的日志器"""
        # 1. 创建共享的控制台处理器 (所有分类都共用这个，打印到终端)
        self._console_handler = logging.StreamHandler()
        self._update_console_handler_level()

        # 2. 为每个分类创建独立的 Logger 和 FileHandler
        timestamp_suffix = datetime.now().strftime('%Y%m%d')
        
        for category in LogCategory:
            cat_name = category.value
            logger_name = f"App.{cat_name}" # 例如: App.algo
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.DEBUG)
            logger.handlers.clear() # 防止重载时重复添加
            
            # --- 独立的文件处理器 ---
            # 文件名例如: logs/system/20231010/system_20231010.log
            category_dir = self.logs_dir / cat_name
            date_dir = category_dir / timestamp_suffix
            date_dir.mkdir(parents=True, exist_ok=True)

            log_file = date_dir / f"{cat_name}_{timestamp_suffix}.log"


            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setLevel(logging.DEBUG) # 文件总是记录最全的细节
            file_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - [%(module_tag)s] %(message)s'
            )
            fh.setFormatter(file_formatter)
            
            logger.addHandler(fh)
            logger.addHandler(self._console_handler) # 同时输出到控制台
            
            self.loggers[cat_name] = logger

    def _update_console_handler_level(self):
        """更新控制台显示的详细程度"""
        if not self._console_handler:
            return

        if is_debug_enabled():
            self._console_handler.setLevel(logging.DEBUG)
            # Debug模式下显示更详细，包含Logger名字以便区分来源
            formatter = logging.Formatter(
                '%(asctime)s [DEBUG] [%(name)s] %(message)s',
                datefmt='%H:%M:%S'
            )
        else:
            self._console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'
            )
        self._console_handler.setFormatter(formatter)

    def update_debug_mode(self, debug_enabled: bool):
        """外部切换Debug模式"""
        self._update_console_handler_level()
        # 记录一条系统日志告知状态变更
        self.info(f"Debug mode changed to: {debug_enabled}", category=LogCategory.SYSTEM)

    def _emit_log(self, category: str, level: str, message: str):
        """发送信号给 UI"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        self.log_added.emit(category, level, message, timestamp)

    # --- 核心记录方法 ---

    def log(self, level: str, message: str, category: LogCategory = LogCategory.SYSTEM, module: str = ""):
        """通用日志记录入口"""
        # 获取对应的 logger
        target_logger = self.loggers.get(category.value)
        if not target_logger:
            target_logger = self.loggers[LogCategory.SYSTEM.value] # 降级默认

        # 使用 extra 字典将 module 传递给 Formatter
        # 如果 module 为空，使用 category 作为标签，否则使用传入的 module
        module_tag = module if module else category.value.upper()
        extra = {'module_tag': module_tag}

        # 写入 Logger (文件 + 控制台)
        if level == 'DEBUG':
            if is_debug_enabled(): # 只有开启Debug才记录Debug级别
                target_logger.debug(message, extra=extra)
        elif level == 'INFO':
            target_logger.info(message, extra=extra)
        elif level == 'WARNING':
            target_logger.warning(message, extra=extra)
        elif level == 'ERROR':
            target_logger.error(message, extra=extra)
        elif level == 'CRITICAL':
            target_logger.critical(message, extra=extra)
        
        # 触发 UI 信号 (Debug级别需判断开关)
        if level != 'DEBUG' or is_debug_enabled():
            self._emit_log(category.value, level, f"[{module_tag}] {message}")

    # --- 便捷方法 (保留原有签名，增加 category 参数) ---

    def debug(self, message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
        self.log('DEBUG', message, category, module)

    def info(self, message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
        self.log('INFO', message, category, module)

    def warning(self, message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
        self.log('WARNING', message, category, module)

    def error(self, message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
        self.log('ERROR', message, category, module)
    
    def critical(self, message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
        self.log('CRITICAL', message, category, module)

    def get_recent_logs(self, category: LogCategory = LogCategory.SYSTEM, count: int = 100) -> List[str]:
        """获取特定分类的最近日志"""
        timestamp_suffix = datetime.now().strftime('%Y%m%d')
        target_file = self.logs_dir / timestamp_suffix / category.value / f"{category.value}_{timestamp_suffix}.log"

        if target_file.exists():
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    return list(deque(f, maxlen=count))
            except Exception:
                return []
        return []

# --- 全局便捷函数 ---

def get_log_manager() -> LogManager:
    return LogManager.instance()

# 使用示例：info("算法启动", category=LogCategory.ALGO)
def debug(message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
    LogManager.instance().debug(message, module, category)

def info(message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
    LogManager.instance().info(message, module, category)

def warning(message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
    LogManager.instance().warning(message, module, category)

def error(message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
    LogManager.instance().error(message, module, category)

def critical(message: str, module: str = "", category: LogCategory = LogCategory.SYSTEM):
    LogManager.instance().critical(message, module, category)