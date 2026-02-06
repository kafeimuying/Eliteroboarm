"""
相机服务层
提供相机的高级业务逻辑和UI接口
"""

from typing import Optional, Dict, Any, Callable, List
import numpy as np
from ..interfaces.hardware import ICamera
from ..managers.log_manager import debug, info, warning, error
from .camera_factory import CameraFactory


class CameraService:
    """相机服务类，封装业务逻辑"""

    def __init__(self, camera: Optional[ICamera] = None):
        self.camera = camera

        # 回调函数缓存
        self._frame_callback: Optional[Callable[[np.ndarray], None]] = None

    def get_camera_list(self) -> List[Any]:
        """获取所有可用相机列表"""
        try:
            from ..container import Container
            
            # 尝试从硬件管理器获取
            if Container.is_registered("hardware_manager"):
                hardware_manager = Container.resolve("hardware_manager")
                cameras = hardware_manager.list_cameras()
                return list(cameras.values())
            
            return []
        except Exception as e:
            error(f"Failed to get camera list: {e}", "CAMERA_SERVICE")
            return []

    @staticmethod
    def get_camera_service(hardware_id: str) -> Optional['CameraService']:
        """
        获取相机服务实例的工厂方法
        
        Args:
            hardware_id: 硬件ID
            
        Returns:
            CameraService实例，失败返回None
        """
        try:
            # 从HardwareManager获取相机实例
            from ..managers.hardware_manager import HardwareManager
            from ..container import Container
            from ..managers.app_config import AppConfigManager
            from ..managers.log_manager import LogManager
            
            container = Container()
            config_manager = AppConfigManager()
            log_manager = LogManager()
            hardware_manager = HardwareManager(container, config_manager, log_manager)
            
            # 初始化硬件管理器（如果尚未初始化）
            if not hardware_manager.hardware_config:
                hardware_manager.initialize_from_config()
            
            # 获取相机实例
            camera = hardware_manager.get_camera(hardware_id)
            if camera is None:
                error(f"Camera '{hardware_id}' not found in hardware manager", "CAMERA_SERVICE")
                return None
                
            return CameraService(camera)
            
        except Exception as e:
            error(f"Failed to create camera service for '{hardware_id}': {e}", "CAMERA_SERVICE")
            return None

    def set_camera(self, camera: ICamera):
        """设置相机实例（用于运行时切换）"""
        # 如果当前有视频流，先停止
        if self.camera and hasattr(self.camera, 'is_streaming') and self.camera.is_streaming():
            self.camera.stop_streaming()

        self.camera = camera
        self._frame_callback = None
        info("Camera service updated with new camera instance")

    def set_device(self, camera: ICamera):
        """设置设备实例（与set_camera功能相同，用于统一接口）"""
        self.set_camera(camera)

    def connect(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """连接相机"""
        camera_name = config.get('name', 'Unknown Camera')
        info(f"Attempting to connect to camera: {camera_name}")

        try:
            # 如果没有相机实例，尝试自动创建
            if not self.camera:
                debug(f"No camera instance available, creating from config for {camera_name}")
                self.camera = CameraFactory.create_camera(config)
                if not self.camera:
                    error(f"Failed to create camera driver for {camera_name}")
                    return {'success': False, 'error': 'Failed to create camera driver'}

            success = self.camera.connect(config)
            if success:
                info(f"Camera '{camera_name}' connected successfully")
                return {'success': True, 'message': 'Camera connected'}
            else:
                error(f"Failed to connect camera: {camera_name}")
                return {'success': False, 'error': 'Failed to connect camera'}
        except Exception as e:
            error(f"Camera connection error for '{camera_name}': {e}")
            return {'success': False, 'error': str(e)}

    def disconnect(self) -> Dict[str, Any]:
        """断开相机连接"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        info("Attempting to disconnect camera")

        try:
            # 先停止视频流
            if hasattr(self.camera, 'is_streaming') and self.camera.is_streaming():
                debug("Stopping camera streaming before disconnect")
                self.camera.stop_streaming()

            success = self.camera.disconnect()
            if success:
                self._frame_callback = None
                info("Camera disconnected successfully")
                return {'success': True, 'message': 'Camera disconnected'}
            else:
                error("Failed to disconnect camera")
                return {'success': False, 'error': 'Failed to disconnect camera'}
        except Exception as e:
            error(f"Camera disconnection error: {e}")
            return {'success': False, 'error': str(e)}

    def connect_camera(self, camera_id: str) -> Dict[str, Any]:
        """连接指定ID的相机"""
        try:
            from ..container import Container
            if Container.is_registered("hardware_manager"):
                hardware_manager = Container.resolve("hardware_manager")
                camera = hardware_manager.get_camera(camera_id)
                
                if not camera:
                    return {'success': False, 'error': f"Camera {camera_id} not found"}
                
                self.set_camera(camera)
                # 使用ID和名称作为基本配置进行连接
                # 实际驱动可能需要完整配置，但如果是由HardwareManager初始化的，
                # 它可能已经配置好了，或者我们可以从HardwareManager获取配置
                connect_config = {'id': camera_id, 'name': camera_id}
                
                # 尝试从ConfigManager获取该相机的配置? 
                # 这里简化处理，直接调用connect
                return self.connect(connect_config)
                
            return {'success': False, 'error': "Hardware Manager not found"}
        except Exception as e:
            error(f"Failed to connect camera {camera_id}: {e}", "CAMERA_SERVICE")
            return {'success': False, 'error': str(e)}

    def is_connected(self, camera_id: str = None) -> bool:
        """检查连接状态"""
        if camera_id:
            from ..container import Container
            if Container.is_registered("hardware_manager"):
                hardware_manager = Container.resolve("hardware_manager")
                camera = hardware_manager.get_camera(camera_id)
                if camera:
                    return camera.is_connected()
                return False
        return self.camera is not None and self.camera.is_connected()

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像"""
        if not self.camera or not self.camera.is_connected():
            error("Camera not connected for frame capture")
            return None

        debug("Attempting to capture frame")

        try:
            frame = self.camera.capture_frame()
            if frame is not None:
                debug(f"Frame captured successfully, shape: {frame.shape}")
            else:
                warning("Frame capture returned None")
            return frame
        except Exception as e:
            error(f"Frame capture error: {e}")
            return None

    def auto_focus(self) -> Dict[str, Any]:
        """
        触发自动对焦
        """
        if not self.camera or not self.camera.is_connected():
            return {'success': False, 'error': 'Camera not connected'}
        
        try:
            # 检查相机驱动是否支持自动对焦
            if hasattr(self.camera, 'auto_focus'):
                success = self.camera.auto_focus()
                if success:
                    return {'success': True, 'message': 'Auto focus triggered'}
                else:
                    return {'success': False, 'error': 'Auto focus failed'}
            else:
                return {'success': False, 'error': 'Camera driver does not support auto-focus'}
        except Exception as e:
            error(f"Auto focus exception: {e}", "CAMERA_SERVICE")
            return {'success': False, 'error': str(e)}

    def start_streaming(self, callback: Callable[[np.ndarray], None]) -> Dict[str, Any]:
        """开始视频流"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        if not self.camera.is_connected():
            return {'success': False, 'error': 'Camera not connected'}

        try:
            # 如果已经在流式传输，先停止
            if hasattr(self.camera, 'is_streaming') and self.camera.is_streaming():
                self.camera.stop_streaming()

            self._frame_callback = callback
            success = self.camera.start_streaming(callback)

            if success:
                info("Camera streaming started")
                return {'success': True, 'message': 'Streaming started'}
            else:
                error("Failed to start camera streaming")
                self._frame_callback = None
                return {'success': False, 'error': 'Failed to start streaming'}
        except Exception as e:
            error(f"Start streaming error: {e}")
            self._frame_callback = None
            return {'success': False, 'error': str(e)}

    def stop_streaming(self) -> Dict[str, Any]:
        """停止视频流"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        try:
            success = self.camera.stop_streaming()
            if success:
                self._frame_callback = None
                info("Camera streaming stopped")
                return {'success': True, 'message': 'Streaming stopped'}
            else:
                error("Failed to stop camera streaming")
                return {'success': False, 'error': 'Failed to stop streaming'}
        except Exception as e:
            error(f"Stop streaming error: {e}")
            return {'success': False, 'error': str(e)}

    def is_streaming(self) -> bool:
        """检查是否正在流式传输"""
        if not self.camera:
            return False

        # 检查相机是否支持流状态查询
        if hasattr(self.camera, 'is_streaming'):
            # 确保总是返回布尔值，防止相机驱动返回None
            streaming_status = self.camera.is_streaming()
            return bool(streaming_status) if streaming_status is not None else False

        # 备用检查方法：是否有回调函数
        return self._frame_callback is not None

    def set_exposure(self, exposure: float) -> Dict[str, Any]:
        """设置曝光时间"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        if not self.camera.is_connected():
            return {'success': False, 'error': 'Camera not connected'}

        try:
            info(f"Setting camera exposure to {exposure}")
            success = self.camera.set_exposure(exposure)

            if success:
                info(f"Camera exposure set to {exposure}")
                return {'success': True, 'message': f'Exposure set to {exposure}'}
            else:
                error("Failed to set camera exposure")
                return {'success': False, 'error': 'Failed to set exposure'}
        except Exception as e:
            error(f"Set exposure error: {e}")
            return {'success': False, 'error': str(e)}

    def set_gain(self, gain: float) -> Dict[str, Any]:
        """设置增益"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        if not self.camera.is_connected():
            return {'success': False, 'error': 'Camera not connected'}

        try:
            info(f"Setting camera gain to {gain}")
            success = self.camera.set_gain(gain)

            if success:
                info(f"Camera gain set to {gain}")
                return {'success': True, 'message': f'Gain set to {gain}'}
            else:
                error("Failed to set camera gain")
                return {'success': False, 'error': 'Failed to set gain'}
        except Exception as e:
            error(f"Set gain error: {e}")
            return {'success': False, 'error': str(e)}

    def trigger_software(self) -> Dict[str, Any]:
        """软件触发"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        if not self.camera.is_connected():
            return {'success': False, 'error': 'Camera not connected'}

        try:
            info("Triggering software capture")
            success = self.camera.trigger_software()

            if success:
                info("Software trigger completed")
                return {'success': True, 'message': 'Software trigger completed'}
            else:
                error("Failed to trigger software capture")
                return {'success': False, 'error': 'Failed to trigger'}
        except Exception as e:
            error(f"Software trigger error: {e}")
            return {'success': False, 'error': str(e)}

    def auto_focus(self) -> Dict[str, Any]:
        """执行自动对焦"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}
        
        if not self.camera.is_connected():
            return {'success': False, 'error': 'Camera not connected'}
            
        try:
            # Check if underlying camera has auto_focus method
            if hasattr(self.camera, 'auto_focus'):
                info("Requesting auto-focus...")
                success = self.camera.auto_focus()
                if success:
                    info("Auto-focus completed successfully")
                    return {'success': True}
                else:
                    return {'success': False, 'error': 'Auto-focus returned failure'}
            else:
                return {'success': False, 'error': 'Camera driver does not support auto-focus'}
        except Exception as e:
            error(f"Auto-focus error: {e}")
            return {'success': False, 'error': str(e)}

            return {'success': False, 'error': str(e)}

    def get_info(self) -> Optional[Dict[str, Any]]:
        """获取相机信息"""
        if not self.camera:
            return None

        try:
            return self.camera.get_info()
        except Exception as e:
            error(f"Failed to get camera info: {e}")
            return None

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        if not self.camera:
            return {'success': False, 'error': 'No camera instance available'}

        try:
            return self.camera.test_connection()
        except Exception as e:
            error(f"Connection test error: {e}")
            return {'success': False, 'error': str(e)}

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'connected': self.is_connected(),
            'streaming': self.is_streaming(),
            'has_callback': self._frame_callback is not None,
            'camera_info': self.get_info()
        }

    def get_frame_info(self, frame: np.ndarray) -> Dict[str, Any]:
        """获取帧信息"""
        if frame is None:
            return {'error': 'No frame provided'}

        try:
            return {
                'shape': frame.shape,
                'dtype': str(frame.dtype),
                'size': frame.size,
                'channels': len(frame.shape) if len(frame.shape) == 3 else 1,
                'width': frame.shape[1] if len(frame.shape) >= 2 else 0,
                'height': frame.shape[0] if len(frame.shape) >= 1 else 0
            }
        except Exception as e:
            error(f"Failed to get frame info: {e}")
            return {'error': str(e)}