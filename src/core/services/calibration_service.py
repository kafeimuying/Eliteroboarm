"""
标定服务层
负责协调机器人和相机进行自动标定流程
"""

from typing import Optional, Callable, Dict, Any
from pathlib import Path
from datetime import datetime
import cv2
import time

from ..services.robot_service import RobotService
from ..services.camera_service import CameraService
from ..managers.log_manager import info, error, warning

class CalibrationService:
    """
    标定服务类
    封装了标定流程的逻辑，协调RobotService和CameraService
    """

    def __init__(self, robot_service: RobotService, camera_service: CameraService):
        self.robot_service = robot_service
        self.camera_service = camera_service
        self._log_callback: Optional[Callable[[str, str], None]] = None

    def set_log_callback(self, callback: Callable[[str, str], None]):
        """设置日志回调函数 (level, message)"""
        self._log_callback = callback

    def _log(self, level: str, message: str):
        """内部日志处理"""
        if self._log_callback:
            # 捕获回调异常，防止影响核心流程
            try:
                self._log_callback(level, message)
            except Exception:
                pass
        
        # 同时记录到系统日志
        if level == "错误":
            error(message, "CALIBRATION")
        elif level == "警告":
            warning(message, "CALIBRATION")
        else:
            info(message, "CALIBRATION")

    def _auto_capture_callback(self, point_idx: int):
        """
        自动拍照回调
        此方法将被注入到机器人驱动中，由机器人线程在到达点位时调用
        """
        try:
            # 1. 检查相机连接
            if not self.camera_service or not self.camera_service.is_connected():
                self._log("错误", f"自动拍照失败：相机未连接 (点 {point_idx})")
                return

            # 2. 抓取图像
            self._log("信息", f"正在拍照 (点 {point_idx})...")
            frame = self.camera_service.capture_frame()
            
            if frame is None:
                self._log("错误", f"自动拍照失败：无法获取图像 (点 {point_idx})")
                return

            # 3. 确定保存路径
            try:
                from ..managers.app_config import AppConfigManager
                app_config = AppConfigManager()
                work_dir = app_config.get_captures_directory()
            except Exception:
                work_dir = Path("workspace/captures")
            
            if not work_dir.exists():
                work_dir.mkdir(parents=True, exist_ok=True)

            # 4. 生成文件名并保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"calib_pt{point_idx}_{timestamp}.jpg"
            filepath = work_dir / filename
            
            # 使用cv2保存
            success = cv2.imwrite(str(filepath), frame)
            
            if success:
                self._log("信息", f"✅ 自动拍照成功: {filename}")
                # 可以在这里扩展：记录图片路径到标定数据文件等
            else:
                self._log("错误", f"❌ 保存图像失败: {filename}")

        except Exception as e:
            self._log("错误", f"自动拍照回调遇到异常: {e}")

    def start_calibration(self) -> Dict[str, Any]:
        """
        启动标定流程
        """
        if not self.robot_service.is_connected():
            return {'success': False, 'error': 'Robot not connected'}

        # 获取底层驱动实例
        driver = getattr(self.robot_service, 'robot', None)
        if not driver:
            return {'success': False, 'error': 'Robot driver instance not found'}

        # 检查驱动是否支持自动拍照回调注入
        if hasattr(driver, 'set_capture_callback'):
            self._log("信息", "配置自动标定：注入拍照回调函数")
            driver.set_capture_callback(self._auto_capture_callback)
        else:
            self._log("警告", "当前机器人驱动不支持自动拍照回调，将回退到手动模式")

        # 调用机器人驱动的标定/测试连接接口
        # 注意：目前Elite驱动的标定逻辑挂载在test_connection上
        # 未来应该在IRobot接口中规范化 start_calibration 方法
        result = self.robot_service.test_connection()
        
        if result.get('success'):
            device_info = result.get('device_info', {})
            model = device_info.get('model', 'Unknown')
            self._log("信息", f"标定流程已启动 (设备: {model})")
        else:
            self._log("错误", f"标定启动失败: {result.get('error')}")

        return result

    def start_3d_calibration(self, layers: int, params: Dict[str, float]) -> Dict[str, Any]:
        """
        启动3D标定流程 (C++加速)
        """
        if not self.robot_service.is_connected():
            return {'success': False, 'error': 'Robot not connected'}

        # 获取底层驱动实例
        driver = getattr(self.robot_service, 'robot', None)
        if not driver:
            return {'success': False, 'error': 'Robot driver instance not found'}
            
        # 检查是否为Elite机器人且支持C++扩展
        if not hasattr(driver, '_run_cpp_3d_calibration') or not hasattr(driver, 'calibration_controller'):
             return {'success': False, 'error': 'Current robot driver does not support C++ 3D calibration'}

        # 注入拍照回调
        if hasattr(driver, 'set_capture_callback'):
            self._log("信息", "配置3D自动标定：注入拍照回调函数")
            driver.set_capture_callback(self._auto_capture_callback)

        self._log("信息", f"启动3D标定流程 (层数: {layers}, 尺寸: {params})")

        # 在新线程中运行，避免阻塞UI
        import threading
        base_width = params.get('base_width', 300.0)
        top_width = params.get('top_width', 150.0)
        height = params.get('height', 100.0)
        tilt_angle = params.get('tilt_angle', 10.0)
        direction = params.get('direction', 'Z+')

        def run_thread():
            try:
                driver._run_cpp_3d_calibration(layers, base_width, top_width, height, tilt_angle, direction)
            except Exception as e:
                self._log("错误", f"3D标定执行异常: {e}")

        threading.Thread(target=run_thread, daemon=True).start()

        return {'success': True, 'message': '3D Calibration started'}
