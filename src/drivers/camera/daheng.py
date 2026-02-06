"""
大恒(Galaxy)相机驱动实现
调用Galaxy SDK (gxipy) 进行具体设备控制
"""

import time
import threading
import numpy as np
import cv2
from typing import Optional, Dict, Any, Callable, List

# 尝试导入大恒相机SDK
try:
    import gxipy as gx
    GALAXY_SDK_AVAILABLE = True
except ImportError:
    GALAXY_SDK_AVAILABLE = False

from core.interfaces.hardware.camera_interface import ICamera, CameraState
from core.managers.log_manager import warning, info, error, debug


class DahengCamera(ICamera):
    """大恒(Daheng)相机驱动实现"""

    def __init__(self):
        if not GALAXY_SDK_AVAILABLE:
            warning("Galaxy SDK (gxipy) not available - real camera connection not possible", "CAMERA_DRIVER")
            warning("Please ensure 'gxipy' is installed or added to your PYTHONPATH", "CAMERA_DRIVER")

        self.device_manager = None
        self.cam = None
        self.connected = False
        self.streaming = False
        self.frame_callback = None
        self.stop_event = threading.Event()
        self.stream_thread = None
        self.config = {}
        self.state = CameraState.IDLE
        self.device_info = {}

    def connect(self, config: Dict[str, Any]) -> bool:
        """
        连接大恒相机
        config:
            ip: 相机IP地址 (可选)
            mac: 相机MAC地址 (可选)
            sn: 相机序列号 (可选)
            index: 相机索引 (默认0)
        """
        self.config = config
        info(f"Connecting to Daheng camera with config: {config}", "CAMERA_DRIVER")

        if not GALAXY_SDK_AVAILABLE:
            error("Galaxy SDK not available", "CAMERA_DRIVER")
            return False

        try:
            self.device_manager = gx.DeviceManager()
            
            # 多次尝试扫描以确保发现设备
            # 有时网络初始化或设备恢复需要时间
            max_retries = 5
            dev_num = 0
            dev_info_list = []
            
            for i in range(max_retries):
                dev_num, dev_info_list = self.device_manager.update_device_list()
                if dev_num > 0:
                    info(f"Scan attempt {i+1}/{max_retries} found {dev_num} devices", "CAMERA_DRIVER")
                    break
                
                info(f"Scan attempt {i+1}/{max_retries} found 0 devices, retrying...", "CAMERA_DRIVER")
                time.sleep(1.5)
            
            if dev_num == 0:
                error(f"No Daheng camera found after {max_retries} attempts", "CAMERA_DRIVER")
                return False

            target_device_info = None
            
            # 根据配置筛选相机
            for dev_info in dev_info_list:
                # 优先匹配序列号
                if 'sn' in config and dev_info.get("sn") == config['sn']:
                    target_device_info = dev_info
                    break
                # 匹配IP
                if 'ip' in config and dev_info.get("ip") == config['ip']:
                    target_device_info = dev_info
                    break
                # 匹配MAC
                if 'mac' in config and dev_info.get("mac") == config['mac']:
                    target_device_info = dev_info
                    break

            # 如果没有特定匹配，使用索引
            if target_device_info is None:
                idx = config.get('index', 0)
                if idx < dev_num:
                    target_device_info = dev_info_list[idx]
                else:
                    error(f"Camera index {idx} out of range (found {dev_num})", "CAMERA_DRIVER")
                    return False

            # 打开相机
            # self.device_manager.open_device 不是 DeviceManager 的方法，应该是 open_device_by_... 或其他
            # 查阅 gxipy 文档，通常是 self.device_manager.open_device_by_index 或直接用 index 字符串
            # 实际上在 gxipy 示例中，通常是: cam = device_manager.open_device_by_index(index)
            # 或者 cam = device_manager.open_device_by_sn(sn)
            
            # 尝试使用 open_device_by_index
            if hasattr(self.device_manager, 'open_device_by_index'):
                self.cam = self.device_manager.open_device_by_index(target_device_info.get("index"))
            elif hasattr(self.device_manager, 'open_device_by_sn'):
                 self.cam = self.device_manager.open_device_by_sn(target_device_info.get("sn"))
            else:
                 # 假设是旧版或标准做法，如果不确定，直接查看 inspect
                 # 查阅 gxipy 源码： DeviceManager 有 open_device_by_index, open_device_by_sn, open_device_by_ip
                 self.cam = self.device_manager.open_device_by_index(target_device_info.get("index"))
            self.device_info = target_device_info
            
            # 对于网口相机，可能需要调整包长
            if target_device_info.get("device_class") == gx.GxDeviceClassList.GEV:
                # 尝试自动协商包长，或设置最佳包长
                 self.cam.GevSCPSPacketSize.set(self.cam.GevSCPSPacketSize.get())

            self.connected = True
            self.state = CameraState.IDLE
            info(f"Daheng camera connected: {target_device_info.get('model_name')}", "CAMERA_DRIVER")
            return True

        except Exception as e:
            error(f"Failed to connect Daheng camera: {e}", "CAMERA_DRIVER")
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.streaming:
                self.stop_streaming()

            if self.cam:
                self.cam.close_device()
                self.cam = None
            
            self.connected = False
            self.state = CameraState.DISCONNECTED
            info("Daheng camera disconnected", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to disconnect Daheng camera: {e}", "CAMERA_DRIVER")
            return False

    def is_connected(self) -> bool:
        return self.connected

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像 (软件触发或单帧采集)"""
        if not self.is_connected():
            return None

        try:
            # 如果没有开启流，需要先开启流，获取一帧后再关闭?
            # 通常SDK建议保持流开启
            self.state = CameraState.CAPTURING
            
            # 发送软触发命令（如果设置为软触发模式）
            # 这里简化处理：直接获取最新一帧
            # 注意：实际应用中可能需要先配置 TriggerMode
            
            # 使用stream_on/stream_off方式采集单帧 (如果当前未在流模式)
            need_stream_control = not self.streaming
            if need_stream_control:
                self.cam.stream_on()
            
            # 获取图像 (timeout 1000ms)
            raw_image = self.cam.data_stream[0].get_image(timeout=1000)
            frame = None
            if raw_image:
                if raw_image.get_status() == gx.GxFrameStatusList.SUCCESS:
                    # 转换为numpy array
                    # 默认大恒SDK返回的是Raw图，需要转换
                    # 这里假设是RGB或Mono，简单转换
                    frame = raw_image.get_numpy_array()
                    # 如果是Bayer格式，可能需要Color转换
                    # 为了通用性，这里简化处理，直接返回numpy数组
                    # 如果是彩色相机，通常需要 cv2.cvtColor(frame, cv2.COLOR_BAYER_BG2RGB) 等
                    # raw_image.convert("RGB") 可以辅助转换
                    rgb_image = raw_image.convert("RGB")
                    frame = rgb_image.get_numpy_array()
                
            if need_stream_control:
                self.cam.stream_off()
            
            self.state = CameraState.IDLE if not self.streaming else CameraState.STREAMING
            return frame

        except Exception as e:
            error(f"Failed to capture frame: {e}", "CAMERA_DRIVER")
            self.state = CameraState.ERROR
            return None
    def auto_focus(self) -> bool:
        """尝试执行自动对焦"""
        if not self.is_connected():
            return False

        try:
            # 尝试查找并设置对焦模式
            # 常见的GenICam属性名可能是 FocusMode 或 FocusAuto
            
            success = False
            
            # 方案1: 尝试 FocusMode (0:Off, 1:Continuous, 2:Once)
            if hasattr(self.cam, "FocusMode"):
                try:
                    # 尝试设置为 Once (通常是 2)
                    self.cam.FocusMode.set(2)
                    info("Triggered Auto Focus (FocusMode=2/Once)", "CAMERA_DRIVER")
                    success = True
                except Exception as e:
                    warning(f"FocusMode=2 attempt failed: {str(e)}", "CAMERA_DRIVER")
                    # 如果2失败，尝试1 (Continuous)
                    try:
                        self.cam.FocusMode.set(1)
                        info("Triggered Auto Focus (FocusMode=1/Continuous)", "CAMERA_DRIVER")
                        success = True
                    except Exception as e2:
                        warning(f"FocusMode=1 attempt failed: {str(e2)}", "CAMERA_DRIVER")

            # 方案2: 尝试 FocusAuto (0:Off, 1:Once, 2:Continuous)
            if not success and hasattr(self.cam, "FocusAuto"):
                try:
                    self.cam.FocusAuto.set(1)
                    info("Triggered Auto Focus (FocusAuto=1/Once)", "CAMERA_DRIVER")
                    success = True
                except Exception as e:
                    warning(f"FocusAuto=1 attempt failed: {str(e)}", "CAMERA_DRIVER")
                    try:
                        self.cam.FocusAuto.set(2)
                        info("Triggered Auto Focus (FocusAuto=2/Continuous)", "CAMERA_DRIVER")
                        success = True
                    except Exception as e2:
                         warning(f"FocusAuto=2 attempt failed: {str(e2)}", "CAMERA_DRIVER")
            
            # 方案3: 检查是否有执行命令的 FocusOnePush (常见于某些相机)
            if not success and hasattr(self.cam, "FocusOnePush"):
                 try:
                    self.cam.FocusOnePush.send_command()
                    info("Triggered Auto Focus (FocusOnePush command)", "CAMERA_DRIVER")
                    success = True
                 except Exception as e:
                    warning(f"FocusOnePush attempt failed: {str(e)}", "CAMERA_DRIVER")

            if success:
                # 等待对焦完成 (简单延时)
                time.sleep(1.5)
                # 如果是 Continuous 模式，可能需要切回 Off? 暂时保留
                return True
            else:
                warning(f"Camera {self.device_info.get('model_name', 'Unknown')} does not support standard auto-focus commands (FocusMode/FocusAuto). This is expected for cameras with manual lenses.", "CAMERA_DRIVER")
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
            
            # 开启SDK流
            self.cam.stream_on()
            self.streaming = True
            self.state = CameraState.STREAMING
            
            # 启动采集线程
            self.stream_thread = threading.Thread(target=self._stream_process)
            self.stream_thread.daemon = True
            self.stream_thread.start()
            
            info("Daheng camera streaming started", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to start streaming: {e}", "CAMERA_DRIVER")
            self.streaming = False
            return False

    def _stream_process(self):
        """采集线程循环"""
        while self.streaming and not self.stop_event.is_set():
            try:
                raw_image = self.cam.data_stream[0].get_image(timeout=1000)
                if raw_image:
                    if raw_image.get_status() == gx.GxFrameStatusList.SUCCESS:
                        # 转换并回调
                        rgb_image = raw_image.convert("RGB")
                        if rgb_image:
                            frame = rgb_image.get_numpy_array()
                            if self.frame_callback:
                                self.frame_callback(frame)
            except Exception as e:
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
                
            if self.cam:
                self.cam.stream_off()
                
            self.state = CameraState.IDLE
            info("Daheng camera streaming stopped", "CAMERA_DRIVER")
            return True
        except Exception as e:
            error(f"Failed to stop streaming: {e}", "CAMERA_DRIVER")
            return False

    def is_streaming(self) -> bool:
        return self.streaming

    def set_exposure(self, exposure: float) -> bool:
        """设置曝光时间 (us)"""
        if not self.is_connected():
            return False
        try:
            self.cam.ExposureTime.set(exposure)
            return True
        except Exception as e:
            error(f"Failed to set exposure: {e}", "CAMERA_DRIVER")
            return False

    def set_gain(self, gain: float) -> bool:
        """设置增益"""
        if not self.is_connected():
            return False
        try:
            self.cam.Gain.set(gain)
            return True
        except Exception as e:
            error(f"Failed to set gain: {e}", "CAMERA_DRIVER")
            return False

    def trigger_software(self) -> bool:
        """发送软触发命令"""
        if not self.is_connected():
            return False
        try:
            self.cam.TriggerSoftware.send_command()
            return True
        except Exception as e:
            error(f"Failed to trigger software: {e}", "CAMERA_DRIVER")
            return False

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        return {
            "vendor": "Daheng",
            "model": self.device_info.get("model_name", "Unknown") if self.device_info else "Unknown",
            "sn": self.device_info.get("sn", "Unknown") if self.device_info else "Unknown",
            "ip": self.device_info.get("ip", "Unknown") if self.device_info else "Unknown",
            "connected": self.connected
        }

    def test_connection(self) -> Dict[str, Any]:
        """测试连接状况"""
        if not self.is_connected():
             return {"status": False, "message": "Not connected"}
        return {"status": True, "message": "Connected OK"}
