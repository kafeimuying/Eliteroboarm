"""
Basler相机驱动实现
支持Basler ace、dart、pulse系列等相机
"""

import time
import threading
from typing import Optional, Dict, Any, Callable
import numpy as np
from core.interfaces.hardware.camera_interface import ICamera

try:
    # 尝试导入Basler官方SDK (pylon)
    from pypylon import pylon
    BASLER_SDK_AVAILABLE = True
except ImportError:
    BASLER_SDK_AVAILABLE = False

try:
    # 尝试导入OpenCV作为图像处理备选
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from core.managers.log_manager import warning, info, error, debug


class BaslerCamera(ICamera):
    """Basler相机驱动实现"""

    def __init__(self):
        # 在初始化时显示SDK可用性警告
        if not BASLER_SDK_AVAILABLE:
            warning("Basler pylon SDK not available - real camera connection not possible", "CAMERA_DRIVER")

        self.camera = None
        self.connected = False
        self.streaming = False
        self.frame_callback = None
        self.stream_thread = None
        self.config = {}

        # Basler特定参数
        self.camera_info = None
        self.grab_timeout = 5000  # 5秒超时
        self.frame_rate = 30.0
        self.exposure_time = 10000.0  # 微秒
        self.gain = 1.0

        # 图像缓存
        self.latest_frame = None
        self.frame_lock = threading.Lock()

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接Basler相机"""
        try:
            self.config = config
            info("Connecting to Basler camera", "CAMERA_DRIVER")

            if not BASLER_SDK_AVAILABLE:
                error("Basler pylon SDK not available - cannot connect to real camera", "CAMERA_DRIVER")
                return False

            # 使用Basler pylon SDK连接
            return self._connect_pylon(config)

        except Exception as e:
            error(f"Failed to connect Basler camera: {e}", "CAMERA_DRIVER")
            self.connected = False
            return False

    def _connect_pylon(self, config: Dict[str, Any]) -> bool:
        """使用pylon SDK连接相机"""
        try:
            # 获取相机设备
            if 'device_serial_number' in config:
                # 通过序列号连接特定相机
                device_info = pylon.DeviceInfo()
                device_info.SetSerialNumber(config['device_serial_number'])
                self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(device_info))
            elif 'device_ip' in config:
                # 通过IP连接GigE相机
                device_info = pylon.DeviceInfo()
                device_info.SetIpAddress(config['device_ip'])
                self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(device_info))
            else:
                # 连接第一个可用的相机
                self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())

            if self.camera is None:
                error("No Basler camera found", "CAMERA_DRIVER")
                return False

            # 打开相机
            self.camera.Open()

            # 获取相机信息
            self.camera_info = {
                'serial_number': self.camera.GetDeviceInfo().GetSerialNumber(),
                'model_name': self.camera.GetDeviceInfo().GetModelName(),
                'vendor_name': self.camera.GetDeviceInfo().GetVendorName(),
                'device_class': self.camera.GetDeviceInfo().GetDeviceClass()
            }

            # 配置相机参数
            if self.camera.IsGigE():
                self.camera.GevSCPSPacketSize.SetValue(1500)  # 设置数据包大小

            # 设置参数
            if 'frame_rate' in config:
                self.frame_rate = config['frame_rate']
                if hasattr(self.camera, 'AcquisitionFrameRateEnable'):
                    self.camera.AcquisitionFrameRateEnable.SetValue(True)
                    self.camera.AcquisitionFrameRate.SetValue(self.frame_rate)

            if 'exposure_time' in config:
                self.exposure_time = config['exposure_time']
                if hasattr(self.camera, 'ExposureTimeAbs'):
                    self.camera.ExposureTimeAbs.SetValue(self.exposure_time)
                elif hasattr(self.camera, 'ExposureTime'):
                    self.camera.ExposureTime.SetValue(self.exposure_time)

            if 'gain' in config:
                self.gain = config['gain']
                if hasattr(self.camera, 'GainRaw'):
                    self.camera.GainRaw.SetValue(int(self.gain))
                elif hasattr(self.camera, 'Gain'):
                    self.camera.Gain.SetValue(self.gain)

            # 设置像素格式
            if hasattr(self.camera, 'PixelFormat'):
                try:
                    self.camera.PixelFormat.SetValue("Mono8")
                except:
                    try:
                        self.camera.PixelFormat.SetValue("RGB8")
                    except:
                        logger.warning("Could not set pixel format")

            info(f"Basler camera connected: {self.camera_info}", "CAMERA_DRIVER")
            self.connected = True
            return True

        except Exception as e:
            error(f"Failed to connect via pylon: {e}", "CAMERA_DRIVER")
            return False

    def disconnect(self) -> bool:
        """断开相机连接"""
        try:
            # 停止视频流
            if self.streaming:
                self.stop_streaming()

            if BASLER_SDK_AVAILABLE and self.camera:
                if self.camera.IsOpen():
                    self.camera.Close()
                self.camera = None

            self.connected = False
            info("Basler camera disconnected", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to disconnect Basler camera: {e}", "CAMERA_DRIVER")
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        if BASLER_SDK_AVAILABLE and self.camera:
            return self.camera.IsOpen() and self.connected
        return self.connected

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return None

        try:
            if BASLER_SDK_AVAILABLE and self.camera:
                # 使用SDK抓取图像
                if not self.camera.IsGrabbing():
                    self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

                grab_result = self.camera.RetrieveResult(self.grab_timeout, pylon.TimeoutHandling_ThrowException)

                if grab_result.GrabSucceeded():
                    # 转换图像格式
                    image = self._convert_grab_result(grab_result)
                    grab_result.Release()

                    with self.frame_lock:
                        self.latest_frame = image

                    logger.debug("Frame captured successfully")
                    return image
                else:
                    logger.error(f"Grab failed: {grab_result.ErrorDescription}")
                    grab_result.Release()
                    return None
            else:
                # 模拟抓取
                return self._generate_mock_frame()

        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
            return None

    def _convert_grab_result(self, grab_result) -> Optional[np.ndarray]:
        """转换Basler抓取结果为numpy数组"""
        try:
            # 获取图像数据
            if hasattr(grab_result, 'GetArray'):
                # 新版本pylon
                image_array = grab_result.GetArray()
            elif hasattr(grab_result, 'GetPixelData'):
                # 旧版本pylon
                image_array = grab_result.GetPixelData()
                width = grab_result.GetWidth()
                height = grab_result.GetHeight()
                image_array = image_array.reshape(height, width)
            else:
                logger.error("Cannot convert grab result to array")
                return None

            # 确保数据类型正确
            if image_array.dtype == np.uint16:
                image_array = (image_array // 256).astype(np.uint8)

            return image_array

        except Exception as e:
            logger.error(f"Failed to convert grab result: {e}")
            return None

    def _generate_mock_frame(self) -> Optional[np.ndarray]:
        """生成模拟图像"""
        try:
            import time
            current_time = time.time()

            # 创建模拟图像 (640x480灰度图)
            height, width = 480, 640
            image = np.zeros((height, width), dtype=np.uint8)

            # 添加移动的圆形作为动态内容
            center_x = int(width * (current_time % 10) / 10)
            center_y = height // 2 + int(100 * np.sin(current_time))

            y, x = np.ogrid[:height, :width]
            mask = (x - center_x)**2 + (y - center_y)**2 < (50**2)
            image[mask] = 128 + int(127 * np.sin(current_time * 2))

            return image

        except Exception as e:
            logger.error(f"Failed to generate mock frame: {e}")
            return None

    def start_streaming(self, callback: Callable[[np.ndarray], None]) -> bool:
        """开始视频流"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return False

        try:
            if self.streaming:
                logger.warning("Already streaming")
                return False

            self.frame_callback = callback

            if BASLER_SDK_AVAILABLE and self.camera:
                # 使用SDK开始抓取
                self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

            # 启动流线程
            self.streaming = True
            self.stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
            self.stream_thread.start()

            logger.info("Basler camera streaming started")
            return True

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.streaming = False
            return False

    def stop_streaming(self) -> bool:
        """停止视频流"""
        try:
            if not self.streaming:
                logger.warning("Not streaming")
                return False

            # 停止流线程
            self.streaming = False
            if self.stream_thread and self.stream_thread.is_alive():
                self.stream_thread.join(timeout=2.0)

            if BASLER_SDK_AVAILABLE and self.camera:
                # 停止抓取
                if self.camera.IsGrabbing():
                    self.camera.StopGrabbing()

            self.frame_callback = None
            logger.info("Basler camera streaming stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop streaming: {e}")
            return False

    def is_streaming(self) -> bool:
        """检查是否正在流式传输"""
        return self.streaming

    def set_exposure(self, exposure: float) -> bool:
        """设置曝光时间"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return False

        try:
            if BASLER_SDK_AVAILABLE and self.camera:
                # Basler曝光时间单位为微秒
                if hasattr(self.camera, 'ExposureTimeAbs'):
                    self.camera.ExposureTimeAbs.SetValue(exposure)
                elif hasattr(self.camera, 'ExposureTime'):
                    self.camera.ExposureTime.SetValue(exposure)
                else:
                    logger.warning("Camera does not support exposure control")
                    return False

            self.exposure_time = exposure
            logger.info(f"Basler exposure set to {exposure} μs")
            return True

        except Exception as e:
            logger.error(f"Failed to set exposure: {e}")
            return False

    def set_gain(self, gain: float) -> bool:
        """设置增益"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return False

        try:
            if BASLER_SDK_AVAILABLE and self.camera:
                if hasattr(self.camera, 'GainRaw'):
                    # Basler增益通常为整数值
                    self.camera.GainRaw.SetValue(int(gain))
                elif hasattr(self.camera, 'Gain'):
                    self.camera.Gain.SetValue(gain)
                else:
                    logger.warning("Camera does not support gain control")
                    return False

            self.gain = gain
            logger.info(f"Basler gain set to {gain}")
            return True

        except Exception as e:
            logger.error(f"Failed to set gain: {e}")
            return False

    def trigger_software(self) -> bool:
        """软件触发"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return False

        try:
            if BASLER_SDK_AVAILABLE and self.camera:
                # 配置为软件触发模式
                if hasattr(self.camera, 'TriggerMode'):
                    self.camera.TriggerMode.SetValue('On')
                    self.camera.TriggerSource.SetValue('Software')

                    # 发送软件触发
                    if hasattr(self.camera, 'TriggerSoftware'):
                        self.camera.TriggerSoftware()

                    # 恢复连续模式
                    self.camera.TriggerMode.SetValue('Off')
                else:
                    logger.warning("Camera does not support software trigger")
                    return False

            logger.info("Basler software trigger completed")
            return True

        except Exception as e:
            logger.error(f"Failed to trigger software capture: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取相机信息"""
        info = {
            'brand': 'Basler',
            'type': 'Camera',
            'connected': self.is_connected(),
            'streaming': self.streaming,
            'sdk_available': BASLER_SDK_AVAILABLE,
            'frame_rate': self.frame_rate,
            'exposure_time': self.exposure_time,
            'gain': self.gain
        }

        if self.camera_info:
            info.update(self.camera_info)

        if BASLER_SDK_AVAILABLE and self.camera and self.camera.IsOpen():
            try:
                # 获取相机特定参数
                if hasattr(self.camera, 'Width'):
                    info['width'] = self.camera.Width.GetValue()
                if hasattr(self.camera, 'Height'):
                    info['height'] = self.camera.Height.GetValue()
                if hasattr(self.camera, 'PixelFormat'):
                    info['pixel_format'] = self.camera.PixelFormat.GetValue()
            except Exception as e:
                logger.warning(f"Failed to get camera parameters: {e}")

        return info

    def test_connection(self) -> Dict[str, Any]:
        """测试连接"""
        result = {
            'success': False,
            'error': None,
            'info': self.get_info()
        }

        try:
            if not self.is_connected():
                result['error'] = 'Camera not connected'
                return result

            # 测试抓取图像
            frame = self.capture_frame()
            if frame is None:
                result['error'] = 'Failed to capture frame'
                return result

            # 测试设备信息获取
            info = self.get_info()
            if not info:
                result['error'] = 'Failed to get device info'
                return result

            result['success'] = True
            result['frame_shape'] = frame.shape

        except Exception as e:
            result['error'] = str(e)

        return result

    def _stream_worker(self):
        """视频流工作线程"""
        logger.info("Basler stream worker started")

        while self.streaming:
            try:
                if BASLER_SDK_AVAILABLE and self.camera:
                    # 使用SDK获取图像
                    grab_result = self.camera.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)

                    if grab_result.GrabSucceeded():
                        image = self._convert_grab_result(grab_result)
                        grab_result.Release()

                        if image is not None and self.frame_callback:
                            with self.frame_lock:
                                self.latest_frame = image
                            try:
                                self.frame_callback(image)
                            except Exception as callback_error:
                                logger.error(f"Frame callback error: {callback_error}")
                    else:
                        grab_result.Release()
                else:
                    # 模拟图像流
                    image = self._generate_mock_frame()
                    if image is not None and self.frame_callback:
                        with self.frame_lock:
                            self.latest_frame = image
                        try:
                            self.frame_callback(image)
                        except Exception as callback_error:
                            logger.error(f"Frame callback error: {callback_error}")

                # 控制帧率
                time.sleep(1.0 / self.frame_rate)

            except Exception as e:
                logger.error(f"Stream worker error: {e}")
                time.sleep(0.1)

        logger.info("Basler stream worker stopped")

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新的图像帧"""
        with self.frame_lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def set_frame_rate(self, frame_rate: float) -> bool:
        """设置帧率"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return False

        try:
            if BASLER_SDK_AVAILABLE and self.camera:
                if hasattr(self.camera, 'AcquisitionFrameRateEnable'):
                    self.camera.AcquisitionFrameRateEnable.SetValue(True)
                    self.camera.AcquisitionFrameRate.SetValue(frame_rate)

            self.frame_rate = frame_rate
            logger.info(f"Basler frame rate set to {frame_rate} fps")
            return True

        except Exception as e:
            logger.error(f"Failed to set frame rate: {e}")
            return False

    def get_frame_rate(self) -> float:
        """获取当前帧率"""
        return self.frame_rate

    def set_pixel_format(self, pixel_format: str) -> bool:
        """设置像素格式"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return False

        try:
            if BASLER_SDK_AVAILABLE and self.camera:
                if hasattr(self.camera, 'PixelFormat'):
                    self.camera.PixelFormat.SetValue(pixel_format)
                    logger.info(f"Basler pixel format set to {pixel_format}")
                    return True
                else:
                    logger.warning("Camera does not support pixel format setting")
                    return False
            else:
                logger.info(f"Mock pixel format set to {pixel_format}")
                return True

        except Exception as e:
            logger.error(f"Failed to set pixel format: {e}")
            return False

    def get_pixel_format(self) -> str:
        """获取当前像素格式"""
        if BASLER_SDK_AVAILABLE and self.camera and hasattr(self.camera, 'PixelFormat'):
            try:
                return self.camera.PixelFormat.GetValue()
            except:
                pass
        return "Unknown"