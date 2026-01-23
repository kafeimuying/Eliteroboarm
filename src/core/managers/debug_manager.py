#!/usr/bin/env python3
"""
全局调试模式管理器
用法： python launcher.py --canvas --debug
"""

import os
import sys
from typing import Optional


class DebugManager:
    """调试模式管理器"""
    
    def __init__(self):
        self._debug_mode = False
        self._initialized = False
    
    def initialize(self, debug_mode: bool = False):
        """初始化调试模式"""
        self._debug_mode = debug_mode
        self._initialized = True
        
        # 设置环境变量供其他模块使用
        os.environ['DEBUG_MODE'] = str(debug_mode)
    
    def is_debug_mode(self) -> bool:
        """检查是否为调试模式"""
        if not self._initialized:
            # 从环境变量读取，防止在LogManager初始化时还未设置
            return os.environ.get('DEBUG_MODE', 'False').lower() == 'true'
        return self._debug_mode
    
    def enable_debug(self):
        """启用调试模式"""
        self._debug_mode = True
        os.environ['DEBUG_MODE'] = 'true'
    
    def disable_debug(self):
        """禁用调试模式"""
        self._debug_mode = False
        os.environ['DEBUG_MODE'] = 'false'
    
    def toggle_debug(self):
        """切换调试模式"""
        self._debug_mode = not self._debug_mode
        os.environ['DEBUG_MODE'] = str(self._debug_mode)


# 全局实例
debug_manager = DebugManager()


def is_debug_enabled() -> bool:
    """检查是否启用了调试模式（便捷函数）"""
    return debug_manager.is_debug_mode()


def enable_debug():
    """启用调试模式（便捷函数）"""
    debug_manager.enable_debug()


def disable_debug():
    """禁用调试模式（便捷函数）"""
    debug_manager.disable_debug()


def parse_debug_args():
    """解析命令行参数中的debug选项"""
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv
    debug_manager.initialize(debug_mode)
    return debug_mode