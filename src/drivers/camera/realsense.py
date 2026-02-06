"""
Intel RealSense深度相机驱动实现
调用pyrealsense2 SDK进行具体设备控制
"""

import time
import threading
import numpy as np
import cv2
from typing import Optional, Dict, Any, Callable, List

# 尝试导入RealSense SDK
try:
    import pyrealsense2 as rs
    REALSENSE_SDK_AVAILABLE = True
except ImportError:
    REALSENSE_SDK_AVAILABLE = False

from core.interfaces.hardware.camera_interface import ICamera, CameraState
from core.managers.log_manager import warning, info, error, debug


class RealSenseCamera(ICamera):
    """Intel RealSense深度相机驱动实现"""

    def __init__(self):
        if not REALSENSE_SDK_AVAILABLE:
            warning("RealSense SDK (pyrealsense2) not available - real camera connection not possible", "CAMERA_DRIVER")
            warning("Please install pyrealsense2: pip install pyrealsense2", "CAMERA_DRIVER")

        self.pipeline = None
        self.config = None
        self.connected = False
        self.streaming = False
        self.frame_callback = None
        self.stop_event = threading.Event()
        self.stream_thread = None
        self.camera_config = {}
        self.state = CameraState.IDLE
        self.device_info = {}
        self.align = None  # 用于对齐深度图和彩色图
        
        # 相机参数
        self.color_intrinsics = None
        self.depth_scale = 1.0

    def connect(self, config: Dict[str, Any]) -> bool:
        """
        连接RealSense相机
        config:
            serial_number: 相机序列号 (可选，用于多相机区分)
            width: 彩色图像宽度 (默认1280)
            height: 彩色图像高度 (默认720) 
            fps: 帧率 (默认30)
            enable_depth: 是否启用深度流 (默认True)
            depth_width: 深度图像宽度 (默认1280)
            depth_height: 深度图像高度 (默认720)
        """
        self.camera_config = config
        info(f"Connecting to RealSense camera with config: {config}", "CAMERA_DRIVER")

        if not REALSENSE_SDK_AVAILABLE:
            error("RealSense SDK not available", "CAMERA_DRIVER")
            return False

        try:
            # 创建pipeline和config
            self.pipeline = rs.pipeline()
            self.config = rs.config()

            # 获取配置参数
            serial_number = config.get('serial_number', config.get('sn', ''))
            width = config.get('width', 1280)
            height = config.get('height', 720)
            fps = config.get('fps', 30)
            enable_depth = config.get('enable_depth', True)
            depth_width = config.get('depth_width', 1280)
            depth_height = config.get('depth_height', 720)

            # 如果指定了序列号，使用该序列号的设备
            if serial_number:
                self.config.enable_device(serial_number)
                info(f"Configuring for device with serial number: {serial_number}", "CAMERA_DRIVER")

            # 配置彩色流
            self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
            info(f"Enabled color stream: {width}x{height} @ {fps}fps", "CAMERA_DRIVER")

            # 配置深度流
            if enable_depth:
                self.config.enable_stream(rs.stream.depth, depth_width, depth_height, rs.format.z16, fps)
                info(f"Enabled depth stream: {depth_width}x{depth_height} @ {fps}fps", "CAMERA_DRIVER")
                # 创建对齐对象（将深度图对齐到彩色图）
                self.align = rs.align(rs.stream.color)

            # 启动pipeline
            profile = self.pipeline.start(self.config)

            # 获取设备信息
            device = profile.get_device()
            self.device_info = {
                'name': device.get_info(rs.camera_info.name),
                'serial_number': device.get_info(rs.camera_info.serial_number),
                'firmware_version': device.get_info(rs.camera_info.firmware_version),
                'product_line': device.get_info(rs.camera_info.product_line),
            }

            # 获取彩色相机内参
            color_stream = profile.get_stream(rs.stream.color)
            self.color_intrinsics = color_stream.as_video_stream_profile().get_intrinsics()
            
            # 获取深度传感器的深度比例（用于将深度值转换为米）
            if enable_depth:
                depth_sensor = device.first_depth_sensor()
                self.depth_scale = depth_sensor.get_depth_scale()
                info(f"Depth scale: {self.depth_scale}", "CAMERA_DRIVER")

            # 等待几帧以稳定相机
            for _ in range(5):
                self.pipeline.wait_for_frames()

            self.connected = True
            self.state = CameraState.IDLE
            info(f"RealSense camera connected: {self.device_info.get('name', 'Unknown')}", "CAMERA_DRIVER")
            return True

        except Exception as e:
            error(f"Failed to connect RealSense camera: {e}", "CAMERA_DRIVER")
            self.connected = False
            if self.pipeline:
                try:
                    self.pipeline.stop()
                except:
                    pass
                self.pipeline = None
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.streaming:
                self.stop_streaming()

            if self.pipeline:
                self.pipeline.stop()
                self.pipeline = None
            
            self.config = None
            self.connected = False
            self.state = CameraState.DISCONNECTED
            info("RealSense camera disconnected", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to disconnect RealSense camera: {e}", "CAMERA_DRIVER")
            return False

    def is_connected(self) -> bool:
        return self.connected

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像"""
        if not self.is_connected():
            return None

        try:
            self.state = CameraState.CAPTURING
            
            # 等待一帧数据
            frames = self.pipeline.wait_for_frames(timeout_ms=5000)
            
            # 如果启用了深度，进行对齐
            if self.align:
                frames = self.align.process(frames)
            
            # 获取彩色图像
            color_frame = frames.get_color_frame()
            if not color_frame:
                warning("No color frame received", "CAMERA_DRIVER")
                self.state = CameraState.IDLE if not self.streaming else CameraState.STREAMING
                return None
            
            # 转换为numpy数组
            color_image = np.asanyarray(color_frame.get_data())
            
            self.state = CameraState.IDLE if not self.streaming else CameraState.STREAMING
            return color_image

        except Exception as e:
            error(f"Failed to capture frame: {e}", "CAMERA_DRIVER")
            self.state = CameraState.ERROR
            return None

    def auto_focus(self) -> bool:
        """
        尝试执行自动对焦
        注意：RealSense相机通常使用固定焦距，不需要对焦
        部分型号(如D435i)可能支持，但大多数型号不支持自动对焦
        """
        if not self.is_connected():
            return False

        try:
            # RealSense相机大多使用固定焦距
            # 这里提供信息性消息
            info("RealSense cameras typically use fixed focus and do not support auto-focus", "CAMERA_DRIVER")
            warning("Auto-focus is not supported on most RealSense models", "CAMERA_DRIVER")
            return False

        except Exception as e:
            error(f"Auto focus exception: {e}", "CAMERA_DRIVER")
            return False

    def start_streaming(self, callback: Callable[[np.ndarray], None]) -> bool:
        """开始视频流"""
        if not self.is_connected():
            return False
            
        if self.streaming:
            return True

        try:
            self.frame_callback = callback
            self.stop_event.clear()
            self.streaming = True
            self.state = CameraState.STREAMING
            
            # 启动采集线程
            self.stream_thread = threading.Thread(target=self._stream_process)
            self.stream_thread.daemon = True
            self.stream_thread.start()
            
            info("RealSense camera streaming started", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to start streaming: {e}", "CAMERA_DRIVER")
            self.streaming = False
            return False

    def _stream_process(self):
        """采集线程循环"""
        while self.streaming and not self.stop_event.is_set():
            try:
                # 等待一帧数据
                frames = self.pipeline.wait_for_frames(timeout_ms=1000)
                
                # 如果启用了深度，进行对齐
                if self.align:
                    frames = self.align.process(frames)
                
                # 获取彩色图像
                color_frame = frames.get_color_frame()
                if color_frame:
                    # 转换为numpy数组
                    color_image = np.asanyarray(color_frame.get_data())
                    
                    # 回调
                    if self.frame_callback:
                        self.frame_callback(color_image)
                        
            except Exception as e:
                if self.streaming:  # 只在仍在流模式时记录错误
                    error(f"Error in stream process: {e}", "CAMERA_DRIVER")
                time.sleep(0.1)

    def stop_streaming(self) -> bool:
        """停止视频流"""
        if not self.streaming:
            return True
            
        try:
            self.streaming = False
            self.stop_event.set()
            
            if self.stream_thread:
                self.stream_thread.join(timeout=2.0)
                self.stream_thread = None
                
            self.state = CameraState.IDLE
            info("RealSense camera streaming stopped", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to stop streaming: {e}", "CAMERA_DRIVER")
            return False

    def is_streaming(self) -> bool:
        return self.streaming

    def set_exposure(self, exposure: float) -> bool:
        """
        设置曝光时间 (us)
        RealSense相机支持自动和手动曝光
        """
        if not self.is_connected():
            return False
        try:
            # 获取颜色传感器
            profile = self.pipeline.get_active_profile()
            device = profile.get_device()
            color_sensor = None
            
            for sensor in device.query_sensors():
                if sensor.is_color_sensor():
                    color_sensor = sensor
                    break
            
            if not color_sensor:
                warning("No color sensor found", "CAMERA_DRIVER")
                return False
            
            # 设置为手动曝光模式
            color_sensor.set_option(rs.option.enable_auto_exposure, 0)
            
            # 设置曝光时间 (单位：微秒)
            color_sensor.set_option(rs.option.exposure, exposure)
            info(f"Exposure set to {exposure} us", "CAMERA_DRIVER")
            return True
            
        except Exception as e:
            error(f"Failed to set exposure: {e}", "CAMERA_DRIVER")
            return False

    def set_gain(self, gain: float) -> bool:
        """设置增益"""
        if not self.is_connected():
            return False
        try:
            # 获取颜色传感器
            profile = self.pipeline.get_active_profile()
            device = profile.get_device()
            color_sensor = None
            
            for sensor in device.query_sensors():
                if sensor.is_color_sensor():
                    color_sensor = sensor
                    break
            
            if not color_sensor:
                warning("No color sensor found", "CAMERA_DRIVER")
                return False
            
            # 设置增益
            color_sensor.set_option(rs.option.gain, gain)
            info(f"Gain set to {gain}", "CAMERA_DRIVER")
            return True
            
        except Exception as e:
            error(f"Failed to set gain: {e}", "CAMERA_DRIVER")
            return False

    def trigger_software(self) -> bool:
        """
        软件触发
        RealSense相机通常不使用软件触发，而是连续采集
        """
        if not self.is_connected():
            return False
        try:
            # RealSense相机不需要软件触发
            # 这里返回True表示操作成功（即使什么都不做）
            debug("Software trigger called (not needed for RealSense)", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to trigger software: {e}", "CAMERA_DRIVER")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        info_dict = {
            "vendor": "Intel",
            "model": self.device_info.get("name", "Unknown"),
            "sn": self.device_info.get("serial_number", "Unknown"),
            "firmware": self.device_info.get("firmware_version", "Unknown"),
            "product_line": self.device_info.get("product_line", "Unknown"),
            "connected": self.connected
        }
        
        # 添加内参信息
        if self.color_intrinsics:
            info_dict["intrinsics"] = {
                "width": self.color_intrinsics.width,
                "height": self.color_intrinsics.height,
                "fx": self.color_intrinsics.fx,
                "fy": self.color_intrinsics.fy,
                "ppx": self.color_intrinsics.ppx,
                "ppy": self.color_intrinsics.ppy,
            }
        
        return info_dict

    def test_connection(self) -> Dict[str, Any]:
        """测试连接状况"""
        if not self.is_connected():
            return {"status": False, "message": "Not connected"}
        
        try:
            # 尝试采集一帧以测试连接
            frames = self.pipeline.wait_for_frames(timeout_ms=2000)
            if frames:
                return {"status": True, "message": "Connected OK", "info": self.get_info()}
            else:
                return {"status": False, "message": "No frames received"}
        except Exception as e:
            return {"status": False, "message": f"Connection test failed: {e}"}

    def get_depth_frame(self) -> Optional[np.ndarray]:
        """
        获取深度图像（额外功能，不在ICamera接口中）
        返回深度图像（单位：毫米）
        """
        if not self.is_connected():
            return None

        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=1000)
            
            if self.align:
                frames = self.align.process(frames)
            
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                return None
            
            # 转换为numpy数组
            depth_image = np.asanyarray(depth_frame.get_data())
            return depth_image
            
        except Exception as e:
            error(f"Failed to get depth frame: {e}", "CAMERA_DRIVER")
            return None

    def get_point_cloud(self) -> Optional[np.ndarray]:
        """
        获取点云数据（额外功能）
        返回Nx3的点云数组 (x, y, z)
        """
        if not self.is_connected():
            return None

        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=1000)
            
            if self.align:
                frames = self.align.process(frames)
            
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                return None
            
            # 创建点云对象
            pc = rs.pointcloud()
            points = pc.calculate(depth_frame)
            
            # 转换为numpy数组
            vertices = np.asanyarray(points.get_vertices())
            point_cloud = np.array([[v[0], v[1], v[2]] for v in vertices])
            
            return point_cloud
            
        except Exception as e:
            error(f"Failed to get point cloud: {e}", "CAMERA_DRIVER")
            return None
