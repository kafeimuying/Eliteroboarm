"""
Application Launcher
Main entry point for the robot control application
"""

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from app.bootstrap import ApplicationBootstrap
from core.container import Container
from core.managers.app_config import AppConfigManager
from core.managers.log_manager import LogManager
from core.managers.log_manager import info, debug, warning, error


class ApplicationLauncher:
    """
    Main application launcher
    """

    def __init__(self):
        self.bootstrap: ApplicationBootstrap = None
        self.config_manager: AppConfigManager = None
        self.log_manager: LogManager = None
        self.container: Container = None
        self.app: QApplication = None

    def initialize(self) -> bool:
        """
        Initialize the application

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Initialize bootstrap
            self.bootstrap = ApplicationBootstrap()
            self.bootstrap.initialize()

            # Get managers
            self.config_manager = self.bootstrap.get_config_manager()
            self.log_manager = self.bootstrap.get_log_manager()
            self.container = self.bootstrap.get_container()

            self.log_manager.info("Application initialization successful", "LAUNCHER")
            return True

        except Exception as e:
            self._show_error(f"Application initialization failed: {e}")
            return False

    def create_qt_application(self) -> None:
        """Create and configure Qt application"""
        try:
            # 从配置获取Qt设置
            app_config = self.config_manager.get_application_config()
            qt_high_dpi = app_config.get("qt_high_dpi_scaling", False)

            # 设置环境变量，避免可能的Qt兼容性问题
            import os
            os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
            if qt_high_dpi:
                os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
            else:
                os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'

            # 使用配置的应用名称
            self.app = QApplication([])
            self.app.setApplicationName(self.config_manager.get_app_name())
            self.app.setOrganizationName(self.config_manager.get_org_name())

            # 不设置任何样式，使用默认样式
            # self.app.setStyle("Fusion")  # 注释掉样式

            self.log_manager.info(f"Qt application created: {self.config_manager.get_app_name()}", "LAUNCHER")

        except Exception as e:
            self._show_error(f"Failed to create Qt application: {e}")
            raise

    def load_hardware_manager(self):
        """
        Load the hardware manager view
        """
        try:
            info("Loading hardware manager UI", "LAUNCHER")

            # Create services through DI container - no hardware instances yet
            robot_service = self.container.resolve("robot_service")
            camera_service = self.container.resolve("camera_service")
            light_service = self.container.resolve("light_service")

            # Try to load the main window
            try:
                from ui_libs.hardware_widget.hardware_management_main_window import HardwareManagementMainWindow

                main_window = HardwareManagementMainWindow(
                    device_manager=self.container.resolve("device_manager"),
                    robot_service=robot_service,
                    camera_service=camera_service,
                    light_service=light_service
                )
                main_window.show()

                info("Main window UI loaded successfully", "LAUNCHER")

            except ImportError as e:
                error(f"Could not load main window UI: {e}", "LAUNCHER")
                raise RuntimeError(f"Failed to load hardware management UI: {e}")

        except Exception as e:
            error(f"Failed to load hardware manager: {e}", "LAUNCHER")
            raise

    
    def _load_legacy_ui(self, robot_service, camera_service, light_service):
        """
        Load the legacy UI as final fallback
        """
        try:
            from ui.main_window_v4 import MainWindow

            legacy_window = MainWindow(
                device_manager=self.container.resolve("device_manager"),
                robot_service=robot_service,
                camera_service=camera_service,
                light_service=light_service
            )
            legacy_window.show()

            info("Legacy UI loaded as final fallback", "LAUNCHER")

        except ImportError as e:
            error(f"Could not load legacy UI: {e}", "LAUNCHER")
            raise RuntimeError("No UI available to load")

    def run(self, debug_mode: bool = False) -> int:
        """
        Run the application

        Args:
            debug_mode: If True, enable debug mode

        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            # Initialize application first
            if not self.initialize():
                return 1

            # Now we can safely use debug mode
            if debug_mode:
                debug("Debug mode enabled", "LAUNCHER")
                self.log_manager.update_debug_mode(debug_mode)

            # Create Qt application
            self.create_qt_application()

            # Load hardware manager
            self.load_hardware_manager()

            # Run the application
            debug_msg = " (DEBUG)" if debug_mode else ""
            info(f"Starting application event loop{debug_msg}", "LAUNCHER")

            # 标准的事件循环方法
            info("Starting standard Qt event loop", "LAUNCHER")

            try:
                # 使用标准的Qt事件循环
                exit_code = self.app.exec()
                info(f"Application exited with code: {exit_code}", "LAUNCHER")
                return exit_code
            except KeyboardInterrupt:
                info("Application interrupted by user", "LAUNCHER")
                return 130
            except Exception as e:
                error(f"Event loop error: {e}", "LAUNCHER")
                return 1

        except Exception as e:
            self._show_error(f"Application runtime error: {e}")
            return 1

    def _show_error(self, message: str):
        """Show error message dialog"""
        if QApplication.instance() is None:
            # Qt not yet initialized, use log manager
            error(message, "LAUNCHER")
            return

        QMessageBox.critical(None, "Application Error", message)


def main(debug_mode: bool = False) -> int:
    """
    Main entry point

    Args:
        debug_mode: Run in debug mode

    Returns:
        Exit code
    """
    launcher = ApplicationLauncher()
    return launcher.run(debug_mode=debug_mode)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Robot Control System")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    parser.add_argument("-d", action="store_true", help="Run in debug mode (short form)")
    args = parser.parse_args()

    debug_mode = args.debug or args.d
    sys.exit(main(debug_mode=debug_mode))