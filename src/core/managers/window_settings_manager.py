#!/usr/bin/env python3
"""
统一窗口设置管理器
用于管理所有窗口的状态、大小、位置等设置
"""

import os
import json
import binascii
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QMainWindow, QDialog

from .log_manager import info, warning, error, debug, LogCategory


class WindowSettingsManager:
    """统一窗口设置管理器"""

    def __init__(self, config_dir: Optional[str] = None, app_config_manager=None):
        """
        初始化窗口设置管理器

        Args:
            config_dir: 配置文件目录（可选，优先使用AppConfigManager配置）
            app_config_manager: 应用配置管理器实例
        """
        # 优先使用AppConfigManager获取配置目录
        if app_config_manager is not None:
            # 使用workspace/config作为配置目录
            self.config_dir = app_config_manager.workspace_config_dir
        elif config_dir is not None:
            self.config_dir = Path(config_dir)
        else:
            # 默认使用workspace/config
            try:
                from .app_config import AppConfigManager
                app_config = AppConfigManager()
                self.config_dir = app_config.workspace_config_dir
            except Exception:
                # fallback to workspace/config
                self.config_dir = Path("workspace") / "config"

        self.config_dir = Path(self.config_dir)
        self.settings_file = self.config_dir / 'unified_window_settings.json'

        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 加载现有设置
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        """加载设置文件"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 返回默认设置结构
                return {
                    "version": "1.0",
                    "last_updated": datetime.now().isoformat(),
                    "windows": {},
                    "global_settings": {
                        "theme": "default",
                        "auto_save": True
                    }
                }
        except Exception as e:
            error(f"加载窗口设置失败: {e}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
            return {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "windows": {},
                "global_settings": {
                    "theme": "default",
                    "auto_save": True
                }
            }

    def _save_settings(self) -> bool:
        """保存设置到文件"""
        try:
            self.settings["last_updated"] = datetime.now().isoformat()

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)

            info(f"统一窗口设置已保存到: {self.settings_file}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
            return True
        except Exception as e:
            error(f"保存窗口设置失败: {e}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
            return False

    def save_window_state(self, window: QWidget, window_id: str,
                         additional_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        保存窗口状态

        Args:
            window: 要保存的窗口对象
            window_id: 窗口的唯一标识符
            additional_data: 额外的窗口数据

        Returns:
            bool: 保存是否成功
        """
        try:
            if "windows" not in self.settings:
                self.settings["windows"] = {}

            # 初始化窗口设置
            if window_id not in self.settings["windows"]:
                self.settings["windows"][window_id] = {}

            window_settings = self.settings["windows"][window_id]

            # 保存窗口基本信息
            window_settings.update({
                "window_class": window.__class__.__name__,
                "window_title": getattr(window, 'windowTitle', lambda: "")(),
                "timestamp": datetime.now().isoformat(),
                "visible": window.isVisible()
            })

            # 保存几何状态（位置、大小、最大化等）
            if hasattr(window, 'saveGeometry'):
                geometry = window.saveGeometry()
                window_settings["geometry"] = binascii.hexlify(geometry.data()).decode('ascii')

            # 保存窗口状态（工具栏、dock widgets等）
            if hasattr(window, 'saveState'):
                state = window.saveState()
                window_settings["state"] = binascii.hexlify(state.data()).decode('ascii')

            # 保存特定窗口类型的信息
            if isinstance(window, (QMainWindow, QDialog)):
                window_settings["is_maximized"] = window.isMaximized()
                window_settings["is_fullscreen"] = window.isFullScreen()

                # 保存屏幕信息
                if window.screen():
                    window_settings["screen_number"] = window.screen().serialNumber()
                    window_settings["screen_geometry"] = {
                        "width": window.screen().size().width(),
                        "height": window.screen().size().height()
                    }

            # 保存窗口大小和位置（作为备选方案）
            window_settings["size"] = {
                "width": window.width(),
                "height": window.height()
            }
            window_settings["position"] = {
                "x": window.x(),
                "y": window.y()
            }

            # 保存额外数据
            if additional_data:
                window_settings["additional_data"] = additional_data

            return self._save_settings()

        except Exception as e:
            error(f"保存窗口状态失败 ({window_id}): {e}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
            return False

    def load_window_state(self, window: QWidget, window_id: str,
                         default_geometry: Optional[tuple] = None) -> bool:
        """
        加载窗口状态

        Args:
            window: 要恢复的窗口对象
            window_id: 窗口的唯一标识符
            default_geometry: 默认几何信息 (x, y, width, height)

        Returns:
            bool: 加载是否成功
        """
        try:
            if "windows" not in self.settings or window_id not in self.settings["windows"]:
                warning(f"未找到窗口设置: {window_id}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
                if default_geometry:
                    window.setGeometry(*default_geometry)
                return False

            window_settings = self.settings["windows"][window_id]

            # 恢复几何状态
            if "geometry" in window_settings and hasattr(window, 'restoreGeometry'):
                try:
                    geometry_bytes = binascii.unhexlify(window_settings["geometry"])
                    window.restoreGeometry(geometry_bytes)
                    info(f"已恢复窗口几何状态: {window_id}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
                except Exception as e:
                    error(f"恢复几何状态失败 ({window_id}): {e}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)

            # 恢复窗口状态
            if "state" in window_settings and hasattr(window, 'restoreState'):
                try:
                    state_bytes = binascii.unhexlify(window_settings["state"])
                    window.restoreState(state_bytes)
                    info(f"已恢复窗口状态: {window_id}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
                except Exception as e:
                    error(f"恢复窗口状态失败 ({window_id}): {e}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)

            # 恢复最大化/全屏状态
            if isinstance(window, (QMainWindow, QDialog)):
                if window_settings.get("is_maximized", False):
                    window.showMaximized()
                elif window_settings.get("is_fullscreen", False):
                    window.showFullScreen()

            # 如果没有保存几何信息，使用备选方案
            if "geometry" not in window_settings and default_geometry:
                if "size" in window_settings and "position" in window_settings:
                    size = window_settings["size"]
                    pos = window_settings["position"]
                    window.setGeometry(pos["x"], pos["y"], size["width"], size["height"])
                else:
                    window.setGeometry(*default_geometry)

            # 恢复可见性
            if "visible" in window_settings:
                window.setVisible(window_settings["visible"])

            info(f"窗口状态加载完成: {window_id}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
            return True

        except Exception as e:
            error(f"加载窗口状态失败 ({window_id}): {e}", "WINDOW_SETTINGS", LogCategory.SOFTWARE)
            if default_geometry:
                window.setGeometry(*default_geometry)
            return False

    def get_window_settings(self, window_id: str) -> Optional[Dict[str, Any]]:
        """获取指定窗口的设置"""
        if "windows" in self.settings and window_id in self.settings["windows"]:
            return self.settings["windows"][window_id]
        return None

    def remove_window_settings(self, window_id: str) -> bool:
        """删除指定窗口的设置"""
        try:
            if "windows" in self.settings and window_id in self.settings["windows"]:
                del self.settings["windows"][window_id]
                return self._save_settings()
            return True
        except Exception as e:
            print(f"删除窗口设置失败 ({window_id}): {e}")
            return False

    def get_all_window_ids(self) -> list:
        """获取所有已保存的窗口ID"""
        if "windows" in self.settings:
            return list(self.settings["windows"].keys())
        return []

    def get_global_settings(self) -> Dict[str, Any]:
        """获取全局设置"""
        return self.settings.get("global_settings", {})

    def set_global_settings(self, settings: Dict[str, Any]) -> bool:
        """设置全局设置"""
        try:
            if "global_settings" not in self.settings:
                self.settings["global_settings"] = {}
            self.settings["global_settings"].update(settings)
            return self._save_settings()
        except Exception as e:
            print(f"设置全局设置失败: {e}")
            return False

    def cleanup_invalid_settings(self) -> int:
        """清理无效的窗口设置（超过30天的设置）"""
        try:
            if "windows" not in self.settings:
                return 0

            from datetime import datetime, timedelta

            cutoff_time = datetime.now() - timedelta(days=30)
            removed_count = 0

            window_ids_to_remove = []
            for window_id, window_settings in self.settings["windows"].items():
                if "timestamp" in window_settings:
                    try:
                        timestamp = datetime.fromisoformat(window_settings["timestamp"])
                        if timestamp < cutoff_time:
                            window_ids_to_remove.append(window_id)
                    except:
                        window_ids_to_remove.append(window_id)

            for window_id in window_ids_to_remove:
                del self.settings["windows"][window_id]
                removed_count += 1

            if removed_count > 0:
                self._save_settings()
                print(f"清理了 {removed_count} 个无效窗口设置")

            return removed_count

        except Exception as e:
            print(f"清理窗口设置失败: {e}")
            return 0

    def export_settings(self, export_file: str) -> bool:
        """导出设置到指定文件"""
        try:
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            print(f"设置已导出到: {export_file}")
            return True
        except Exception as e:
            print(f"导出设置失败: {e}")
            return False

    def import_settings(self, import_file: str, merge: bool = True) -> bool:
        """从指定文件导入设置"""
        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                imported_settings = json.load(f)

            if merge:
                # 合并设置
                if "windows" in imported_settings:
                    if "windows" not in self.settings:
                        self.settings["windows"] = {}
                    self.settings["windows"].update(imported_settings["windows"])

                if "global_settings" in imported_settings:
                    if "global_settings" not in self.settings:
                        self.settings["global_settings"] = {}
                    self.settings["global_settings"].update(imported_settings["global_settings"])
            else:
                # 完全替换设置
                self.settings = imported_settings

            return self._save_settings()
        except Exception as e:
            print(f"导入设置失败: {e}")
            return False


# 全局单例实例
_window_settings_manager = None


def get_window_settings_manager(app_config_manager=None) -> WindowSettingsManager:
    """获取全局窗口设置管理器实例"""
    global _window_settings_manager
    if _window_settings_manager is None:
        _window_settings_manager = WindowSettingsManager(app_config_manager=app_config_manager)
    return _window_settings_manager