"""
Application Bootstrap
Handles application initialization and dependency setup
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.container import Container
from core.managers.app_config import AppConfigManager
from core.managers.log_manager import LogManager
from core.managers.log_manager import info, debug, warning, error
from core.managers.debug_manager import is_debug_enabled

# Import interfaces
from core.interfaces.hardware.robot_interface import IRobot
from core.interfaces.hardware.camera_interface import ICamera
from core.interfaces.hardware.light_interface import ILight

class ApplicationBootstrap:
    """
    Application bootstrap class that handles initialization
    """

    def __init__(self):
        self.config_manager = AppConfigManager()
        self.container = Container()
        self.log_manager: Optional[LogManager] = None

    def initialize(self) -> None:
        """
        Initialize the application

        Raises:
            RuntimeError: If initialization fails
        """
        try:
            # Initialize configuration
            self._setup_configuration()

            # Initialize logging
            self._setup_logging()

            # Initialize dependency injection container
            self._setup_container()

            info("Application bootstrap completed", "BOOTSTRAP")

        except Exception as e:
            error(f"Application bootstrap failed: {e}", "BOOTSTRAP")
            raise RuntimeError(f"Application bootstrap failed: {e}")

    def _setup_configuration(self) -> None:
        """Setup configuration management"""
        try:
            # Load system configuration
            system_config = self.config_manager.get_system_config()
            self.container.register("system_config", system_config)

            # Extract debug mode from config
            debug_mode = system_config.get("system", {}).get("debug_mode", False)
            self.container.register("debug_mode", debug_mode)

        except Exception as e:
            # Use defaults if config loading fails
            self.container.register("system_config", {})
            self.container.register("debug_mode", False)

    def _setup_logging(self) -> None:
        """Setup logging system"""
        self.log_manager = LogManager()

        # Update debug mode from system configuration
        debug_mode = self.container.resolve("debug_mode", False)
        if debug_mode or is_debug_enabled():
            self.log_manager.update_debug_mode(True)

        # Register log manager in container
        self.container.register(LogManager, self.log_manager)

    def _setup_container(self) -> None:
        """Setup dependency injection container"""
        # Register configuration manager
        self.container.register(AppConfigManager, self.config_manager)

        # Register hardware configuration
        try:
            hardware_config = self.config_manager.get_hardware_config()
            self.container.register("hardware_config", hardware_config)
        except Exception as e:
            if self.log_manager:
                self.log_manager.warning(f"Failed to load hardware config: {e}", "BOOTSTRAP")
            self.container.register("hardware_config", {})

        # Register core services (without hardware instances initially)
        self._register_core_services()

    def _register_core_services(self) -> None:
        """Register core services to container"""
        from core.managers.device_manager import DeviceManager
        from core.services.robot_service import RobotService
        from core.services.camera_service import CameraService
        from core.services.light_service import LightService

        # Register device manager
        device_manager = DeviceManager()
        self.container.register("device_manager", device_manager)

        # Register services without hardware instances initially
        # UI will inject hardware when needed
        robot_service = RobotService()  # No robot initially
        camera_service = CameraService()  # No camera initially
        light_service = LightService()    # No light initially

        self.container.register("robot_service", robot_service)
        self.container.register("camera_service", camera_service)
        self.container.register("light_service", light_service)

    def load_drivers_from_config(self) -> None:
        """
        Load and register drivers based on configuration

        This method should be called after hardware drivers are available
        """
        try:
            hardware_config = self.container.resolve("hardware_config")

            # TODO: Load robot drivers
            self._load_robot_drivers(hardware_config.get("robots", {}))

            # TODO: Load camera drivers
            self._load_camera_drivers(hardware_config.get("cameras", {}))

            # TODO: Load light drivers
            self._load_light_drivers(hardware_config.get("lights", {}))

            if self.log_manager:
                self.log_manager.info("All drivers loaded from configuration", "BOOTSTRAP")

        except Exception as e:
            if self.log_manager:
                self.log_manager.error(f"Failed to load drivers from config: {e}", "BOOTSTRAP")
            raise

    def _load_robot_drivers(self, robot_configs: Dict[str, Any]) -> None:
        """Load robot drivers from configuration"""
        for name, config in robot_configs.items():
            try:
                # TODO: Implement robot driver loading logic
                # This will be implemented in Step 5
                pass
            except Exception as e:
                if self.log_manager:
                    self.log_manager.warning(f"Failed to load robot driver {name}: {e}", "BOOTSTRAP")

    def _load_camera_drivers(self, camera_configs: Dict[str, Any]) -> None:
        """Load camera drivers from configuration"""
        for name, config in camera_configs.items():
            try:
                # TODO: Implement camera driver loading logic
                # This will be implemented in Step 5
                pass
            except Exception as e:
                if self.log_manager:
                    self.log_manager.warning(f"Failed to load camera driver {name}: {e}", "BOOTSTRAP")

    def _load_light_drivers(self, light_configs: Dict[str, Any]) -> None:
        """Load light drivers from configuration"""
        for name, config in light_configs.items():
            try:
                # TODO: Implement light driver loading logic
                # This will be implemented in Step 5
                pass
            except Exception as e:
                if self.log_manager:
                    self.log_manager.warning(f"Failed to load light driver {name}: {e}", "BOOTSTRAP")

    def get_container(self) -> Container:
        """
        Get the dependency injection container

        Returns:
            The configured container instance
        """
        return self.container

    def get_config_manager(self) -> AppConfigManager:
        """
        Get the configuration manager

        Returns:
            The configuration manager instance
        """
        return self.config_manager

    def get_log_manager(self) -> LogManager:
        """
        Get the log manager

        Returns:
            The log manager instance
        """
        if self.log_manager is None:
            raise RuntimeError("Log manager not initialized")
        return self.log_manager