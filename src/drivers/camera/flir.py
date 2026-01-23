"""
FLIR相机驱动实现
支持FLIR Blackfly、Chameleon、Flea系列等相机
"""

import time
import threading
from typing import Optional, Dict, Any, Callable
import numpy as np
from core.interfaces.hardware.camera_interface import ICamera

try:
    # 尝试导入FLIR官方SDK (Spinnaker)
    import PySpin
    FLIR_SDK_AVAILABLE = True
except ImportError:
    FLIR_SDK_AVAILABLE = False

try:
    # 尝试导入OpenCV作为图像处理备选
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from core.managers.log_manager import warning, info, error, debug


class FlirCamera(ICamera):
    """FLIR相机驱动实现"""

    def __init__(self):
        # 在初始化时显示SDK可用性警告
        if not FLIR_SDK_AVAILABLE:
            warning("FLIR Spinnaker SDK not available - real camera connection not possible", "CAMERA_DRIVER")

        self.system = None
        self.camera = None
        self.connected = False
        self.streaming = False
        self.frame_callback = None
        self.stream_thread = None
        self.config = {}

        # FLIR特定参数
        self.camera_info = None
        self.grab_timeout = 5000  # 5秒超时
        self.frame_rate = 30.0
        self.exposure_time = 10000.0  # 微秒
        self.gain = 1.0

        # 图像缓存
        self.latest_frame = None
        self.frame_lock = threading.Lock()

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接FLIR相机"""
        try:
            self.config = config
            info("Connecting to FLIR camera", "CAMERA_DRIVER")

            if not FLIR_SDK_AVAILABLE:
                error("FLIR Spinnaker SDK not available - cannot connect to real camera", "CAMERA_DRIVER")
                return False

            # 使用FLIR Spinnaker SDK连接
            return self._connect_spinnaker(config)

        except Exception as e:
            error(f"Failed to connect FLIR camera: {e}", "CAMERA_DRIVER")
            self.connected = False
            return False

    def _connect_spinnaker(self, config: Dict[str, Any]) -> bool:
        """使用Spinnaker SDK连接相机"""
        try:
            # 获取系统实例
            self.system = PySpin.System.GetInstance()

            # 获取相机列表
            cam_list = self.system.GetCameras()

            if cam_list.GetSize() == 0:
                error("No FLIR cameras found", "CAMERA_DRIVER")
                cam_list.Clear()
                return False

            # 查找指定相机
            selected_camera = None

            if 'device_serial_number' in config:
                # 通过序列号查找
                serial_number = config['device_serial_number']
                for i in range(cam_list.GetSize()):
                    cam = cam_list.GetByIndex(i)
                    cam_info = cam.GetTLDeviceNodeMap()
                    if PySpin.CStringPtr(cam_info.GetNode('DeviceSerialNumber')).GetValue() == serial_number:
                        selected_camera = cam
                        break
                    else:
                        cam.Release()
            elif 'device_index' in config:
                # 通过索引查找
                index = config['device_index']
                if 0 <= index < cam_list.GetSize():
                    selected_camera = cam_list.GetByIndex(index)
            else:
                # 使用第一个相机
                selected_camera = cam_list.GetByIndex(0)

            if selected_camera is None:
                error("Specified FLIR camera not found", "CAMERA_DRIVER")
                cam_list.Clear()
                return False

            # 初始化相机
            self.camera = selected_camera
            self.camera.Init()

            # 获取相机信息
            nodemap = self.camera.GetTLDeviceNodeMap()
            self.camera_info = {
                'serial_number': PySpin.CStringPtr(nodemap.GetNode('DeviceSerialNumber')).GetValue(),
                'model_name': PySpin.CStringPtr(nodemap.GetNode('DeviceModelName')).GetValue(),
                'vendor_name': PySpin.CStringPtr(nodemap.GetNode('DeviceVendorName')).GetValue(),
                'device_version': PySpin.CStringPtr(nodemap.GetNode('DeviceVersion')).GetValue()
            }

            # 配置相机参数
            nodemap = self.camera.GetNodeMap()

            # 设置帧率
            if 'frame_rate' in config:
                self.frame_rate = config['frame_rate']
                try:
                    node_acquisition_framerate = PySpin.CFloatPtr(nodemap.GetNode('AcquisitionFrameRate'))
                    if PySpin.IsAvailable(node_acquisition_framerate) and PySpin.IsWritable(node_acquisition_framerate):
                        node_acquisition_framerate.SetValue(self.frame_rate)

                    # 启用帧率控制
                    node_frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode('AcquisitionFrameRateEnable'))
                    if PySpin.IsAvailable(node_frame_rate_enable) and PySpin.IsWritable(node_frame_rate_enable):
                        node_frame_rate_enable.SetValue(True)
                except:
                    logger.warning("Could not set frame rate")

            # 设置曝光时间
            if 'exposure_time' in config:
                self.exposure_time = config['exposure_time']
                try:
                    node_exposure_time = PySpin.CFloatPtr(nodemap.GetNode('ExposureTime'))
                    if PySpin.IsAvailable(node_exposure_time) and PySpin.IsWritable(node_exposure_time):
                        node_exposure_time.SetValue(self.exposure_time)
                except:
                    logger.warning("Could not set exposure time")

            # 设置增益
            if 'gain' in config:
                self.gain = config['gain']
                try:
                    node_gain = PySpin.CFloatPtr(nodemap.GetNode('Gain'))
                    if PySpin.IsAvailable(node_gain) and PySpin.IsWritable(node_gain):
                        node_gain.SetValue(self.gain)
                except:
                    logger.warning("Could not set gain")

            # 设置像素格式
            try:
                node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
                if PySpin.IsAvailable(node_pixel_format) and PySpin.IsWritable(node_pixel_format):
                    # 尝试设置常用格式
                    formats = ['Mono8', 'RGB8', 'BGR8', 'YUV422Packed']
                    for format_name in formats:
                        try:
                            node_pixel_format.SetIntValue(PySpin.CEnumEntryPtr(node_pixel_format.GetEntryByName(format_name)).GetValue())
                            break
                        except:
                            continue
            except:
                logger.warning("Could not set pixel format")

            info(f"FLIR camera connected: {self.camera_info}", "CAMERA_DRIVER")
            self.connected = True
            return True

        except Exception as e:
            error(f"Failed to connect via Spinnaker: {e}", "CAMERA_DRIVER")
            self._cleanup()
            return False

    def disconnect(self) -> bool:
        """断开相机连接"""
        try:
            # 停止视频流
            if self.streaming:
                self.stop_streaming()

            self._cleanup()

            self.connected = False
            info("FLIR camera disconnected", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to disconnect FLIR camera: {e}", "CAMERA_DRIVER")
            return False

    def _cleanup(self):
        """清理资源"""
        try:
            if self.camera:
                if self.camera.IsInitialized():
                    # 停止采集
                    if self.camera.IsStreaming():
                        self.camera.EndAcquisition()
                    # 反初始化
                    self.camera.DeInit()
                # 释放相机
                self.camera = None

            if self.system:
                # 释放系统
                self.system.ReleaseInstance()
                self.system = None
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def is_connected(self) -> bool:
        """检查连接状态"""
        if FLIR_SDK_AVAILABLE and self.camera:
            return self.camera.IsInitialized() and self.connected
        return self.connected

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像"""
        if not self.is_connected():
            logger.error("Camera not connected")
            return None

        try:
            if FLIR_SDK_AVAILABLE and self.camera:
                # 使用SDK抓取图像
                if not self.camera.IsStreaming():
                    self.camera.BeginAcquisition()

                image_result = self.camera.GetNextImage(self.grab_timeout)

                if image_result.IsIncomplete():
                    logger.error(f"Image incomplete: {image_result.GetIncompleteStatus()}")
                    image_result.Release()
                    return None

                # 转换图像格式
                image = self._convert_image_result(image_result)
                image_result.Release()

                with self.frame_lock:
                    self.latest_frame = image

                logger.debug("Frame captured successfully")
                return image
            else:
                # 模拟抓取
                return self._generate_mock_frame()

        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
            return None

    def _convert_image_result(self, image_result) -> Optional[np.ndarray]:
        """转换FLIR图像结果为numpy数组"""
        try:
            # 转换为RGB8格式
            converted_image = image_result.Convert(PySpin.PixelFormat_BGR8, PySpin.HQ_LINEAR)

            # 获取图像数据
            width = converted_image.GetWidth()
            height = converted_image.GetHeight()

            # 创建numpy数组
            image_data = converted_image.GetData()
            image_array = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width, 3))

            return image_array

        except Exception as e:
            logger.error(f"Failed to convert image result: {e}")
            return None

    def _generate_mock_frame(self) -> Optional[np.ndarray]:
        """生成模拟图像"""
        try:
            import time
            current_time = time.time()

            # 创建彩色模拟图像 (640x480)
            height, width = 480, 640
            image = np.zeros((height, width, 3), dtype=np.uint8)

            # 添加动态内容 - 移动的彩色方块
            center_x = int(width * (current_time % 10) / 10)
            center_y = height // 2 + int(100 * np.sin(current_time))

            # 不同颜色的圆形
            colors = [
                (255, 0, 0),    # 红色
                (0, 255, 0),    # 绿色
                (0, 0, 255),    # 蓝色
            ]

            for i, color in enumerate(colors):
                offset_x = i * 30 - 30
                offset_y = i * 30 - 30
                y, x = np.ogrid[:height, :width]
                mask = (x - (center_x + offset_x))**2 + (y - (center_y + offset_y))**2 < (25**2)
                image[mask] = color

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

            if FLIR_SDK_AVAILABLE and self.camera:
                # 开始图像采集
                self.camera.BeginAcquisition()

            # 启动流线程
            self.streaming = True
            self.stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
            self.stream_thread.start()

            logger.info("FLIR camera streaming started")
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

            if FLIR_SDK_AVAILABLE and self.camera and self.camera.IsStreaming():
                # 停止图像采集
                self.camera.EndAcquisition()

            self.frame_callback = None
            logger.info("FLIR camera streaming stopped")
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
            if FLIR_SDK_AVAILABLE and self.camera:
                nodemap = self.camera.GetNodeMap()
                node_exposure_time = PySpin.CFloatPtr(nodemap.GetNode('ExposureTime'))
                if PySpin.IsAvailable(node_exposure_time) and PySpin.IsWritable(node_exposure_time):
                    node_exposure_time.SetValue(exposure)
                else:
                    logger.warning("Camera does not support exposure control")
                    return False

            self.exposure_time = exposure
            logger.info(f"FLIR exposure set to {exposure} μs")
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
            if FLIR_SDK_AVAILABLE and self.camera:
                nodemap = self.camera.GetNodeMap()
                node_gain = PySpin.CFloatPtr(nodemap.GetNode('Gain'))
                if PySpin.IsAvailable(node_gain) and PySpin.IsWritable(node_gain):
                    node_gain.SetValue(gain)
                else:
                    logger.warning("Camera does not support gain control")
                    return False

            self.gain = gain
            logger.info(f"FLIR gain set to {gain}")
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
            if FLIR_SDK_AVAILABLE and self.camera:
                nodemap = self.camera.GetNodeMap()

                # 配置为软件触发模式
                node_trigger_mode = PySpin.CBooleanPtr(nodemap.GetNode('TriggerMode'))
                if PySpin.IsAvailable(node_trigger_mode) and PySpin.IsWritable(node_trigger_mode):
                    node_trigger_mode.SetValue(True)

                    node_trigger_source = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerSource'))
                    if PySpin.IsAvailable(node_trigger_source) and PySpin.IsWritable(node_trigger_source):
                        node_trigger_source.SetIntValue(PySpin.CEnumEntryPtr(node_trigger_source.GetEntryByName('Software')).GetValue())

                    # 发送软件触发
                    node_trigger_software = PySpin.CCommandPtr(nodemap.GetNode('TriggerSoftware'))
                    if PySpin.IsAvailable(node_trigger_software) and PySpin.IsWritable(node_trigger_software):
                        node_trigger_software.Execute()

                    # 恢复连续模式
                    node_trigger_mode.SetValue(False)
                else:
                    logger.warning("Camera does not support software trigger")
                    return False

            logger.info("FLIR software trigger completed")
            return True

        except Exception as e:
            logger.error(f"Failed to trigger software capture: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取相机信息"""
        info = {
            'brand': 'FLIR',
            'type': 'Camera',
            'connected': self.is_connected(),
            'streaming': self.streaming,
            'sdk_available': FLIR_SDK_AVAILABLE,
            'frame_rate': self.frame_rate,
            'exposure_time': self.exposure_time,
            'gain': self.gain
        }

        if self.camera_info:
            info.update(self.camera_info)

        if FLIR_SDK_AVAILABLE and self.camera and self.camera.IsInitialized():
            try:
                # 获取相机特定参数
                nodemap = self.camera.GetNodeMap()

                # 获取图像尺寸
                node_width = PySpin.CIntegerPtr(nodemap.GetNode('Width'))
                if PySpin.IsAvailable(node_width):
                    info['width'] = node_width.GetValue()

                node_height = PySpin.CIntegerPtr(nodemap.GetNode('Height'))
                if PySpin.IsAvailable(node_height):
                    info['height'] = node_height.GetValue()

                # 获取像素格式
                node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
                if PySpin.IsAvailable(node_pixel_format):
                    info['pixel_format'] = PySpin.CEnumEntryPtr(node_pixel_format.GetCurrentEntry()).GetSymbolic()

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
        logger.info("FLIR stream worker started")

        while self.streaming:
            try:
                if FLIR_SDK_AVAILABLE and self.camera:
                    # 使用SDK获取图像
                    image_result = self.camera.GetNextImage(1000)

                    if image_result.IsIncomplete():
                        logger.error(f"Image incomplete: {image_result.GetIncompleteStatus()}")
                        image_result.Release()
                        continue

                    image = self._convert_image_result(image_result)
                    image_result.Release()

                    if image is not None and self.frame_callback:
                        with self.frame_lock:
                            self.latest_frame = image
                        try:
                            self.frame_callback(image)
                        except Exception as callback_error:
                            logger.error(f"Frame callback error: {callback_error}")
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

        logger.info("FLIR stream worker stopped")

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
            if FLIR_SDK_AVAILABLE and self.camera:
                nodemap = self.camera.GetNodeMap()
                node_frame_rate = PySpin.CFloatPtr(nodemap.GetNode('AcquisitionFrameRate'))
                if PySpin.IsAvailable(node_frame_rate) and PySpin.IsWritable(node_frame_rate):
                    node_frame_rate.SetValue(frame_rate)

            self.frame_rate = frame_rate
            logger.info(f"FLIR frame rate set to {frame_rate} fps")
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
            if FLIR_SDK_AVAILABLE and self.camera:
                nodemap = self.camera.GetNodeMap()
                node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
                if PySpin.IsAvailable(node_pixel_format) and PySpin.IsWritable(node_pixel_format):
                    entry = node_pixel_format.GetEntryByName(pixel_format)
                    if PySpin.IsAvailable(entry):
                        node_pixel_format.SetIntValue(entry.GetValue())
                        logger.info(f"FLIR pixel format set to {pixel_format}")
                        return True

            logger.info(f"Mock pixel format set to {pixel_format}")
            return True

        except Exception as e:
            logger.error(f"Failed to set pixel format: {e}")
            return False

    def get_pixel_format(self) -> str:
        """获取当前像素格式"""
        if FLIR_SDK_AVAILABLE and self.camera:
            try:
                nodemap = self.camera.GetNodeMap()
                node_pixel_format = PySpin.CEnumerationPtr(nodemap.GetNode('PixelFormat'))
                if PySpin.IsAvailable(node_pixel_format):
                    entry = node_pixel_format.GetCurrentEntry()
                    return entry.GetSymbolic()
            except:
                pass
        return "Unknown"