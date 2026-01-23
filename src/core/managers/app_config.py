"""
Application Configuration Manager
Handles loading and managing application-wide configuration
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path

class AppConfigManager:
    """
    Application configuration manager that handles config/ and workspace/ directories
    """

    def __init__(self):
        # 首先设置默认路径
        self.config_dir = Path("config")
        self.workspace_dir = Path("workspace")

        # Ensure directories exist
        self.config_dir.mkdir(exist_ok=True)
        self.workspace_dir.mkdir(exist_ok=True)

        # 初始化缓存
        self._config_cache: Dict[str, Any] = {}

        # 现在安全地获取系统配置
        self._load_system_configuration()

    def _load_system_configuration(self):
        """加载系统配置"""
        try:
            system_config = self.get_system_config()

            # 从配置获取路径，如果配置不存在则使用默认值
            config = system_config.get("paths", {})
            ui_config = system_config.get("ui", {})
            app_config = system_config.get("application", {})

            # 更新路径配置（支持配置覆盖）
            self.config_dir = Path(config.get("config_dir", "config"))
            self.workspace_dir = Path(config.get("workspace_dir", "workspace"))

            # 确保目录存在
            self.config_dir.mkdir(exist_ok=True)
            self.workspace_dir.mkdir(exist_ok=True)

            # Workspace subdirectories - 支持配置
            self.logs_dir = self.workspace_dir / Path(config.get("logs_subdir", "logs"))
            self.captures_dir = self.workspace_dir / Path(config.get("captures_subdir", "captures"))
            self.data_dir = self.workspace_dir / Path(config.get("data_subdir", "data"))
            self.paths_dir = self.workspace_dir / Path(config.get("paths_subdir", "paths"))
            self.pipeline_dir = self.workspace_dir / Path(config.get("pipeline_subdir", "pipeline"))
            self.canvas_temp_dir = self.workspace_dir / Path(config.get("canvas_temp_subdir", "canvas_temp"))

            # Workspace config directory for window settings etc.
            self.workspace_config_dir = self.workspace_dir / Path(config.get("workspace_config_subdir", "config"))

            # Create workspace subdirectories with parents=True to handle nested paths
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            self.captures_dir.mkdir(parents=True, exist_ok=True)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.paths_dir.mkdir(parents=True, exist_ok=True)
            self.pipeline_dir.mkdir(parents=True, exist_ok=True)
            self.canvas_temp_dir.mkdir(parents=True, exist_ok=True)
            self.workspace_config_dir.mkdir(parents=True, exist_ok=True)

            # Source code directories
            self.algorithms_composite_dir = Path(config.get("algorithms_composite_dir", "src/algorithms/composite"))

            # UI配置缓存
            self._ui_config = ui_config
            # 应用配置缓存
            self._app_config = app_config

            
        except Exception as e:
            # 如果配置加载失败，使用默认配置
            # 不依赖LogManager避免循环依赖，直接使用print
            print(f"[APP_CONFIG] 配置加载失败，使用默认配置: {e}")
            self._load_default_configuration()

    def _load_default_configuration(self):
        """加载默认配置"""
        default_config = self.get_default_system_config()

        config = default_config.get("paths", {})
        ui_config = default_config.get("ui", {})
        app_config = default_config.get("application", {})

        # 更新路径配置
        self.config_dir = Path(config.get("config_dir", "config"))
        self.workspace_dir = Path(config.get("workspace_dir", "workspace"))

        # 确保目录存在
        self.config_dir.mkdir(exist_ok=True)
        self.workspace_dir.mkdir(exist_ok=True)

        # Workspace subdirectories
        self.logs_dir = self.workspace_dir / Path(config.get("logs_subdir", "logs"))
        self.captures_dir = self.workspace_dir / Path(config.get("captures_subdir", "captures"))
        self.data_dir = self.workspace_dir / Path(config.get("data_subdir", "data"))
        self.paths_dir = self.workspace_dir / Path(config.get("paths_subdir", "paths"))
        self.pipeline_dir = self.workspace_dir / Path(config.get("pipeline_subdir", "pipeline"))
        self.canvas_temp_dir = self.workspace_dir / Path(config.get("canvas_temp_subdir", "canvas_temp"))

        # Workspace config directory for window settings etc.
        self.workspace_config_dir = self.workspace_dir / Path(config.get("workspace_config_subdir", "config"))

        # Create workspace subdirectories with parents=True to handle nested paths
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)
        self.canvas_temp_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_config_dir.mkdir(parents=True, exist_ok=True)

        # Source code directories
        self.algorithms_composite_dir = Path(config.get("algorithms_composite_dir", "src/algorithms/composite"))

        # UI配置缓存
        self._ui_config = ui_config

        # 应用配置缓存
        self._app_config = app_config

        
    def get_config_path(self, filename: str) -> Path:
        """
        Get the full path for a config file

        Args:
            filename: Config filename

        Returns:
            Full path to the config file
        """
        return self.config_dir / filename

    def get_workspace_path(self, subpath: str = "") -> Path:
        """
        Get a path within the workspace directory

        Args:
            subpath: Subpath within workspace (e.g., "logs", "captures")

        Returns:
            Full path to the workspace location
        """
        if subpath:
            return self.workspace_dir / subpath
        return self.workspace_dir

    def load_config(self, filename: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load a configuration file

        Args:
            filename: Config filename
            use_cache: Whether to use cached version if available

        Returns:
            Configuration dictionary
        """
        config_path = self.get_config_path(filename)

        # Check cache first
        if use_cache and str(config_path) in self._config_cache:
            return self._config_cache[str(config_path)]

        # Load from file
        try:
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")

            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    config = yaml.safe_load(f) or {}
                elif config_path.suffix.lower() == '.json':
                    config = json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")

            # Cache the result
            if use_cache:
                self._config_cache[str(config_path)] = config

            return config

        except Exception as e:
            raise RuntimeError(f"Failed to load config {filename}: {e}")

    def save_config(self, filename: str, config: Dict[str, Any]) -> None:
        """
        Save a configuration file

        Args:
            filename: Config filename
            config: Configuration dictionary to save
        """
        config_path = self.get_config_path(filename)

        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(config, f, default_flow_style=False, indent=2)
                elif config_path.suffix.lower() == '.json':
                    json.dump(config, f, indent=2, ensure_ascii=False)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")

            # Update cache
            self._config_cache[str(config_path)] = config

        except Exception as e:
            raise RuntimeError(f"Failed to save config {filename}: {e}")

    def get_hardware_config(self) -> Dict[str, Any]:
        """
        Get the hardware configuration

        Returns:
            Hardware configuration dictionary
        """
        try:
            return self.load_config("hardware_config.json")
        except FileNotFoundError:
            # Return default config if file doesn't exist
            return self.get_default_hardware_config()

    def get_default_hardware_config(self) -> Dict[str, Any]:
        """
        Get the default hardware configuration

        Returns:
            Default hardware configuration
        """
        return {
            "robots": {},
            "cameras": {},
            "lights": {},
            "communication": {},
            "global": {
                "debug_mode": False,
                "auto_connect": False,
                "timeout": 5.0
            }
        }

    def get_log_directory(self) -> Path:
        """Get the log directory path"""
        return self.logs_dir

    def get_captures_directory(self) -> Path:
        """Get the captures directory path"""
        return self.captures_dir

    def get_data_directory(self) -> Path:
        """Get the data directory path"""
        return self.data_dir

    def get_paths_directory(self) -> Path:
        """Get the paths directory path"""
        return self.paths_dir

    def get_system_config(self) -> Dict[str, Any]:
        """
        Get the system configuration from system.yaml

        Returns:
            System configuration dictionary
        """
        try:
            return self.load_config("system.yaml")
        except FileNotFoundError:
            # Return default config if file doesn't exist
            return self.get_default_system_config()

    def get_default_system_config(self) -> Dict[str, Any]:
        """
        Get the default system configuration

        Returns:
            Default system configuration
        """
        return {
            "system": {
                "debug_mode": False,
                "camera_driver_check_enabled": False
            },
            "paths": {
                "config_dir": "config",
                "workspace_dir": "workspace",
                "logs_subdir": "logs",
                "captures_subdir": "captures",
                "data_subdir": "data",
                "paths_subdir": "paths"
            },
            "ui": {
                "window": {
                    "width": 1400,
                    "height": 800,
                    "title": "机器人控制系统"
                },
                "update_intervals": {
                    "status_update_ms": 1000,
                    "video_update_ms": 33
                },
                "camera_display": {
                    "width": 640,
                    "height": 480
                }
            },
            "application": {
                "app_name": "Robot Control System",
                "org_name": "Robot Control",
                "qt_high_dpi_scaling": False
            }
        }

    def is_camera_driver_check_enabled(self) -> bool:
        """
        Check if camera driver import check is enabled

        Returns:
            True if camera driver check should be performed, False otherwise
        """
        system_config = self.get_system_config()
        return system_config.get("system", {}).get("camera_driver_check_enabled", True)

    def get_debug_mode(self) -> bool:
        """
        Get debug mode setting

        Returns:
            True if debug mode is enabled, False otherwise
        """
        system_config = self.get_system_config()
        return system_config.get("system", {}).get("debug_mode", False)

    def get_ui_config(self) -> Dict[str, Any]:
        """
        Get UI configuration

        Returns:
            UI configuration dictionary
        """
        return self._ui_config

    def get_application_config(self) -> Dict[str, Any]:
        """
        Get application configuration

        Returns:
            Application configuration dictionary
        """
        return self._app_config

    def get_app_name(self) -> str:
        """Get application name"""
        return self._app_config.get("app_name", "Robot Control System")

    def get_org_name(self) -> str:
        """Get organization name"""
        return self._app_config.get("org_name", "Robot Control")

    def is_qt_high_dpi_scaling_enabled(self) -> bool:
        """Check if Qt high DPI scaling is enabled"""
        return self._app_config.get("qt_high_dpi_scaling", False)

    
    def reset_system_config(self) -> bool:
        """
        Reset system.yaml to default configuration (one-click repair)

        Returns:
            True if reset successful, False otherwise
        """
        try:
            import shutil
            from pathlib import Path

            system_config_path = self.config_dir / "system.yaml"
            backup_path = self.config_dir / "system.yaml.backup"

            # Create backup of existing config
            if system_config_path.exists():
                shutil.copy2(system_config_path, backup_path)
                try:
                    print(f"[APP_CONFIG] 已备份原有配置到: {backup_path}")
                except ImportError:
                    print(f"[APP_CONFIG] 已备份原有配置到: {backup_path}")

            # Get default config
            default_config = self.get_default_system_config()

            # Write default config to file
            with open(system_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, default_flow_style=False,
                         allow_unicode=True, indent=2)

            # Clear cache
            self.clear_cache()

            # Log success
            try:
                print(f"[APP_CONFIG] 系统配置已重置为默认值: {system_config_path}")
            except ImportError:
                print(f"[APP_CONFIG] 系统配置已重置为默认值: {system_config_path}")

            return True

        except Exception as e:
            try:
                from ..managers.log_manager import error
                error(f"重置系统配置失败: {e}", "APP_CONFIG")
            except ImportError:
                print(f"[APP_CONFIG] 重置系统配置失败: {e}")
            return False

    def validate_system_config(self) -> Dict[str, Any]:
        """
        Validate system configuration and return issues

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        try:
            config = self.get_system_config()

            # Check required sections
            required_sections = ["system", "paths", "ui", "application"]
            for section in required_sections:
                if section not in config:
                    issues.append(f"缺少必需的配置节: {section}")

            # Validate system section
            if "system" in config:
                system_config = config["system"]
                if "debug_mode" in system_config and not isinstance(system_config["debug_mode"], bool):
                    issues.append("system.debug_mode 必须是布尔值")

                if "camera_driver_check_enabled" in system_config and not isinstance(system_config["camera_driver_check_enabled"], bool):
                    issues.append("system.camera_driver_check_enabled 必须是布尔值")

            # Validate paths section
            if "paths" in config:
                paths_config = config["paths"]
                required_path_fields = ["config_dir", "workspace_dir", "logs_subdir", "captures_subdir", "data_subdir", "paths_subdir"]
                for field in required_path_fields:
                    if field not in paths_config:
                        warnings.append(f"paths.{field} 使用默认值")

            # Validate UI section
            if "ui" in config:
                ui_config = config["ui"]
                if "window" in ui_config:
                    window_config = ui_config["window"]
                    for field in ["width", "height"]:
                        if field in window_config and (not isinstance(window_config[field], int) or window_config[field] <= 0):
                            issues.append(f"ui.window.{field} 必须是正整数")

                if "update_intervals" in ui_config:
                    intervals_config = ui_config["update_intervals"]
                    for field in ["status_update_ms", "video_update_ms"]:
                        if field in intervals_config and (not isinstance(intervals_config[field], int) or intervals_config[field] <= 0):
                            issues.append(f"ui.update_intervals.{field} 必须是正整数")

            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
                "config": config
            }

        except Exception as e:
            return {
                "valid": False,
                "issues": [f"配置验证失败: {str(e)}"],
                "warnings": [],
                "config": None
            }

    def clear_cache(self) -> None:
        """Clear the configuration cache"""
        self._config_cache.clear()

    def reload_config(self, filename: str) -> Dict[str, Any]:
        """
        Reload a configuration file (ignores cache)

        Args:
            filename: Config filename

        Returns:
            Configuration dictionary
        """
        # Remove from cache if present
        config_path = str(self.get_config_path(filename))
        if config_path in self._config_cache:
            del self._config_cache[config_path]

        # Load fresh from file
        return self.load_config(filename, use_cache=False)