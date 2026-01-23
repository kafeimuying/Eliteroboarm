#!/usr/bin/env python3
"""
模拟相机驱动
用于测试和演示相机功能
"""

import time
import threading
import os
import random
import glob
from typing import Optional, Tuple, Dict, Any, List, Callable
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

from core.interfaces.hardware.camera_interface import ICamera, CameraState
from core.managers.log_manager import debug, info, warning, error


class SimulationCamera(ICamera):
    """模拟相机实现"""

    def __init__(self, camera_id: str = "sim_001"):
        """初始化模拟相机"""
        self.camera_id = camera_id

        # 相机状态
        self._connected = False
        self._state = CameraState.IDLE
        self._capturing = False
        self._recording = False

        # 相机参数
        self.width = 1920
        self.height = 1080
        self.fps = 30
        self.exposure = 10.0
        self.gain = 1.0

        # 模拟图像生成
        self._frame_count = 0
        self._preview_thread: Optional[threading.Thread] = None
        self._stop_preview = threading.Event()

        # 模拟媒体文件路径
        self._media_files: List[str] = []
        self._current_media_index = 0
        self._media_type = "image"  # "image" or "video"

        # 预览回调
        self._preview_callbacks = []

        info(f"Simulation camera initialized: {camera_id}", "SIMULATION_CAMERA")

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接相机"""
        if self._connected:
            warning("Camera already connected", "SIMULATION_CAMERA")
            return True

        info(f"Connecting simulation camera with config: {config}", "SIMULATION_CAMERA")

        # 设置初始相机参数（后续可能会根据实际图像尺寸调整）
        self.fps = config.get('fps', 30)

        # 处理媒体文件配置
        media_type = config.get('media_type', '程序生成')
        media_path = config.get('media_path', '')
        self._is_program_generated = False  # 标记是否为程序生成模式

        if media_path:
            info(f"Processing media source: {media_type}, path: {media_path}", "SIMULATION_CAMERA")

            # 重置媒体索引，确保从第一张图片开始
            self._current_media_index = 0

            # 检查是否是单个文件（包括media_type为"程序生成"但有media_path的情况）
            if os.path.isfile(media_path):
                # 单个文件模式
                file_ext = os.path.splitext(media_path)[1].lower()
                image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp']
                video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.m4v', '.webm', '.3gp', '.mpeg']

                if file_ext in image_extensions:
                    # 单个图片文件
                    self.set_media_source('image', [media_path])
                    info(f"Set single image media source: {os.path.basename(media_path)}", "SIMULATION_CAMERA")
                    self._media_type = 'image'
                elif file_ext in video_extensions:
                    # 单个视频文件
                    self.set_media_source('video', [media_path])
                    info(f"Set single video media source: {os.path.basename(media_path)}", "SIMULATION_CAMERA")
                    self._media_type = 'video'
                else:
                    warning(f"Unsupported file format: {file_ext}", "SIMULATION_CAMERA")
            elif media_type in ["图片文件夹", "视频文件"]:
                # 文件夹模式
                if os.path.exists(media_path):
                    if media_type == "图片文件夹":
                        # 获取图片文件列表
                        image_files = []
                        image_extensions = [
                            '*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif', '*.tiff', '*.tif',
                            '*.JPG', '*.JPEG', '*.PNG', '*.BMP', '*.GIF', '*.TIFF', '*.TIF',
                            '*.webp', '*.WEBP'
                        ]
                        for ext in image_extensions:
                            image_files.extend(glob.glob(os.path.join(media_path, ext)))
                        image_files.sort()

                        if image_files:
                            self.set_media_source('image', image_files)
                            info(f"Set image media source: {len(image_files)} images", "SIMULATION_CAMERA")
                            debug(f"Folder mode: will start from image index 0", "SIMULATION_CAMERA")
                        else:
                            warning(f"No supported image files found in directory {media_path}", "SIMULATION_CAMERA")
                    else:  # 视频文件
                        video_files = []
                        video_extensions = [
                            '*.mp4', '*.avi', '*.mov', '*.mkv', '*.wmv', '*.flv', '*.m4v',
                            '*.MP4', '*.AVI', '*.MOV', '*.MKV', '*.WMV', '*.FLV', '*.M4V',
                            '*.webm', '*.WEBM', '*.3gp', '*.3GP', '*.mpeg', '*.MPEG'
                        ]
                        for ext in video_extensions:
                            video_files.extend(glob.glob(os.path.join(media_path, ext)))
                        video_files.sort()

                        if video_files:
                            self.set_media_source('video', video_files)
                            info(f"Set video media source: {len(video_files)} videos", "SIMULATION_CAMERA")
                        else:
                            warning(f"No supported video files found in directory {media_path}", "SIMULATION_CAMERA")
                else:
                    warning(f"Media path does not exist: {media_path}", "SIMULATION_CAMERA")
            else:
                # 程序生成模式 - 不设置媒体文件
                info("Using program-generated mode", "SIMULATION_CAMERA")
                self._is_program_generated = True
                self._media_files = []  # 确保媒体文件列表为空
        else:
            # 没有media_path，默认为程序生成模式
            info("Using program-generated mode", "SIMULATION_CAMERA")
            self._is_program_generated = True
            self._media_files = []  # 确保媒体文件列表为空

        # 模拟连接延迟
        time.sleep(0.1)
        self._connected = True
        self._state = CameraState.IDLE

        # 只有在非程序生成模式下且没有设置媒体文件时，才创建默认的模拟图片
        if not self._media_files and not self._is_program_generated:
            self._initialize_media_files()

        info("Simulation camera connected successfully", "SIMULATION_CAMERA")
        return True

    def disconnect(self) -> bool:
        """断开连接"""
        if not self._connected:
            return True

        info("Disconnecting simulation camera", "SIMULATION_CAMERA")

        # 停止预览和流式传输
        self.stop_preview()
        self.stop_streaming()

        # 清除所有回调
        self._preview_callbacks.clear()

        # 清除媒体文件
        self._media_files.clear()
        self._current_media_index = 0

        self._connected = False
        self._state = CameraState.IDLE

        info("Simulation camera disconnected", "SIMULATION_CAMERA")
        return True

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    def capture_image(self) -> Optional[np.ndarray]:
        """拍摄单张图片"""
        if not self._connected:
            error("Camera not connected", "SIMULATION_CAMERA")
            return None

        debug("Capturing simulation image", "SIMULATION_CAMERA")

        # 如果是程序生成模式，直接生成模拟图像
        if self._is_program_generated:
            image = self._generate_simulation_image()
            debug(f"Captured from program-generated image: {image.shape}", "SIMULATION_CAMERA")

            # 转换为numpy数组
            frame_array = np.array(image)

            # 模拟曝光和增益效果
            frame_array = self._apply_camera_effects(frame_array)

            debug(f"Captured generated image: {frame_array.shape}", "SIMULATION_CAMERA")
            return frame_array

        # 非程序生成模式：优先使用媒体文件，如果没有媒体文件则生成模拟图像
        if self._media_files:
            # 使用媒体文件
            frame_array = self._get_media_frame()
            if frame_array is not None:
                debug(f"Captured from media file: {frame_array.shape}", "SIMULATION_CAMERA")
                return frame_array
            else:
                warning("Failed to get media frame, falling back to generated image", "SIMULATION_CAMERA")

        # 生成模拟图像（回退方案）
        image = self._generate_simulation_image()
        debug(f"Captured from generated image: {image.shape}", "SIMULATION_CAMERA")

        # 转换为numpy数组
        frame_array = np.array(image)

        # 模拟曝光和增益效果
        frame_array = self._apply_camera_effects(frame_array)

        debug(f"Captured generated image: {frame_array.shape}", "SIMULATION_CAMERA")
        return frame_array

    def start_preview(self, callback=None) -> bool:
        """开始实时预览"""
        if not self._connected:
            return False

        if self._preview_thread and self._preview_thread.is_alive():
            warning("Preview already running", "SIMULATION_CAMERA")
            return True

        info("Starting simulation preview", "SIMULATION_CAMERA")
        self._stop_preview.clear()

        if callback:
            self._preview_callbacks.append(callback)

        self._preview_thread = threading.Thread(
            target=self._preview_worker,
            daemon=True
        )
        self._preview_thread.start()

        return True

    def stop_preview(self) -> bool:
        """停止实时预览"""
        info("Stopping preview", "SIMULATION_CAMERA")
        self._stop_preview.set()

        if self._preview_thread and self._preview_thread.is_alive():
            self._preview_thread.join(timeout=1.0)

        self._preview_callbacks.clear()
        return True

    def set_exposure(self, exposure: float) -> bool:
        """设置曝光时间"""
        if not self._connected:
            return False

        self.exposure = max(0.1, min(1000.0, exposure))
        info(f"Exposure set to {self.exposure}ms", "SIMULATION_CAMERA")
        return True

    def set_gain(self, gain: float) -> bool:
        """设置增益"""
        if not self._connected:
            return False

        self.gain = max(1.0, min(100.0, gain))
        info(f"Gain set to {self.gain}", "SIMULATION_CAMERA")
        return True

    def set_resolution(self, width: int, height: int) -> bool:
        """设置分辨率"""
        if not self._connected:
            return False

        self.width = width
        self.height = height
        info(f"Resolution set to {width}x{height}", "SIMULATION_CAMERA")
        return True

    def set_fps(self, fps: int) -> bool:
        """设置帧率"""
        if not self._connected:
            return False

        self.fps = max(1, min(120, fps))
        info(f"FPS set to {self.fps}", "SIMULATION_CAMERA")
        return True

    def get_info(self) -> Dict[str, Any]:
        """获取相机信息"""
        return {
            'type': 'Simulation Camera',
            'model': 'SIM-CAM-001',
            'serial_number': self.camera_id,
            'firmware': '1.0.0',
            'max_resolution': f"{self.width}x{self.height}",
            'supported_fps': [1, 15, 30, 60],
            'supported_formats': ['RGB', 'RAW', 'MJPG'],
            'interface': 'USB3.0',
            'sensor_type': 'CMOS'
        }

    def get_state(self) -> CameraState:
        """获取相机状态"""
        return self._state

    def get_supported_formats(self) -> List[str]:
        """获取支持的图像格式"""
        return ['RGB', 'RAW', 'MJPG', 'JPG', 'BMP']

    def set_media_source(self, media_type: str, media_files: List[str]) -> bool:
        """设置模拟媒体源（图片或视频）"""
        self._media_type = media_type
        self._media_files = media_files
        self._current_media_index = 0

        # 自动检测并设置相机分辨率为实际图像尺寸
        self._auto_detect_resolution()

        info(f"Media source set: {media_type}, {len(media_files)} files", "SIMULATION_CAMERA")
        info(f"Camera resolution set to: {self.width}x{self.height}", "SIMULATION_CAMERA")
        return True

    # ========== 私有方法 ==========
    def _auto_detect_resolution(self):
        """自动检测媒体文件的实际分辨率并设置相机分辨率（所有图片的最大尺寸）"""
        if not self._media_files:
            # 如果没有媒体文件，使用默认分辨率
            self.width = 1920
            self.height = 1080
            return

        max_width = 0
        max_height = 0

        try:
            # 检查所有文件来确定最大分辨率
            for i, file_path in enumerate(self._media_files):
                if os.path.exists(file_path):
                    try:
                        with Image.open(file_path) as img:
                            width, height = img.size
                            max_width = max(max_width, width)
                            max_height = max(max_height, height)
                            debug(f"Image {i+1}: {os.path.basename(file_path)} - {width}x{height}", "SIMULATION_CAMERA")
                    except Exception as e:
                        warning(f"Failed to read image {file_path}: {e}", "SIMULATION_CAMERA")

            if max_width > 0 and max_height > 0:
                self.width = max_width
                self.height = max_height
                info(f"Auto-detected max resolution from {len(self._media_files)} images: {self.width}x{self.height}", "SIMULATION_CAMERA")
            else:
                # 如果无法检测分辨率，使用默认值
                self.width = 1920
                self.height = 1080
                warning("Could not detect image resolution, using default 1920x1080", "SIMULATION_CAMERA")

        except Exception as e:
            error(f"Error during resolution detection: {e}", "SIMULATION_CAMERA")
            self.width = 1920
            self.height = 1080

    def _initialize_media_files(self):
        """初始化模拟媒体文件"""
        # 创建模拟图片
        self._create_simulation_images()

    def _create_simulation_images(self):
        """创建模拟图片"""
        # 创建模拟图片目录
        sim_dir = "workspace/data/simulation_images"
        os.makedirs(sim_dir, exist_ok=True)

        # 创建几张模拟图片
        for i in range(5):
            image = self._generate_simulation_image(pattern=i)
            image_path = os.path.join(sim_dir, f"sim_{i:03d}.jpg")
            image.save(image_path, 'JPEG')

        # 设置媒体文件列表
        self._media_files = [
            os.path.join(sim_dir, f"sim_{i:03d}.jpg")
            for i in range(5)
        ]
        self._media_type = "image"

        info(f"Created {len(self._media_files)} simulation images", "SIMULATION_CAMERA")

    def _generate_simulation_image(self, pattern: int = 0) -> Image.Image:
        """生成模拟图像 - 每个相机实例生成唯一图像"""
        # 创建基本图像
        image = Image.new('RGB', (self.width, self.height), color='black')
        draw = ImageDraw.Draw(image)

        # 根据相机ID生成唯一颜色
        camera_hash = hash(self.camera_id) % 1000
        base_color_r = (camera_hash * 137) % 256
        base_color_g = (camera_hash * 89) % 256
        base_color_b = (camera_hash * 241) % 256

        # 添加渐变背景
        for y in range(0, self.height, 10):
            color_value = int(20 + (y / self.height) * 50)
            r = min(255, base_color_r + color_value)
            g = min(255, base_color_g + color_value)
            b = min(255, base_color_b + color_value)
            color = (r, g, b)
            draw.rectangle([0, y, self.width, y + 10], fill=color)

        # 添加相机ID文本以区分不同相机实例
        try:
            # 尝试加载字体，如果失败则使用默认字体
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        except:
            font = ImageFont.load_default()

        # 显示相机信息
        camera_name = f"Camera: {self.camera_id}"
        text_bbox = draw.textbbox((0, 0), camera_name, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # 居中显示相机名称
        text_x = (self.width - text_width) // 2
        text_y = (self.height - text_height) // 2
        draw.text((text_x, text_y), camera_name, fill=(255, 255, 255), font=font)

        # 添加时间戳
        import time
        timestamp = time.strftime("%H:%M:%S")
        draw.text((10, 10), timestamp, fill=(255, 255, 0), font=font)

        # 添加帧数
        frame_text = f"Frame: {self._frame_count}"
        draw.text((10, self.height - 50), frame_text, fill=(0, 255, 255), font=font)

        # 添加图案
        if pattern == 0:
            # 网格图案
            for x in range(0, self.width, 50):
                draw.line([x, 0, x, self.height], fill=(100, 100, 150), width=1)
            for y in range(0, self.height, 50):
                draw.line([0, y, self.width, y], fill=(100, 100, 150), width=1)
        elif pattern == 1:
            # 圆形图案
            center_x, center_y = self.width // 2, self.height // 2
            for radius in range(50, min(self.width, self.height) // 2, 80):
                color = (100 + radius // 5, 150 + radius // 8, 200 + radius // 10)
                draw.ellipse([center_x - radius, center_y - radius,
                             center_x + radius, center_y + radius], outline=color)
        elif pattern == 2:
            # 条纹图案
            for x in range(0, self.width, 40):
                color = (100 + x // 10, 100 + x // 8, 100 + x // 6)
                draw.rectangle([x, 0, x + 20, self.height], fill=color)
        elif pattern == 3:
            # 棋盘图案
            for x in range(0, self.width, 100):
                for y in range(0, self.height, 100):
                    if (x + y) % 200 == 0:
                        draw.rectangle([x, y, x + 80, y + 80], fill=(120, 120, 180))
                    else:
                        draw.rectangle([x, y, x + 80, y + 80], fill=(80, 80, 120))
        else:
            # 随机噪声
            for _ in range(1000):
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                size = random.randint(1, 20)
                color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
                draw.rectangle([x, y, x + size, y + size], fill=color)

        # 添加时间戳和相机信息
        try:
            font = ImageFont.load_default()
        except:
            font = None

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        text_lines = [
            f"Simulation Camera - {self.camera_id}",
            f"Frame: {self._frame_count}",
            f"Time: {timestamp}",
            f"Resolution: {self.width}x{self.height}"
        ]

        y_offset = 20
        for line in text_lines:
            # 添加文字阴影
            if font:
                draw.text((22, y_offset + 2), line, fill=(0, 0, 0), font=font)
                draw.text((20, y_offset), line, fill=(255, 255, 255), font=font)
            y_offset += 25

        # 添加边框
        draw.rectangle([5, 5, self.width - 5, self.height - 5], outline=(200, 200, 200), width=2)

        # 添加模拟噪点
        image = image.filter(ImageFilter.GaussianBlur(radius=0.5))

        return image

    def _apply_camera_effects(self, frame_array: np.ndarray) -> np.ndarray:
        """应用相机效果"""
        # 模拟曝光效果
        exposure_factor = self.exposure / 10.0
        frame_array = np.clip(frame_array * exposure_factor, 0, 255).astype(np.uint8)

        # 模拟增益效果
        frame_array = np.clip(frame_array * self.gain, 0, 255).astype(np.uint8)

        # 添加随机噪点
        noise = np.random.normal(0, 5, frame_array.shape).astype(np.int16)
        frame_array = np.clip(frame_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        return frame_array

    def _preview_worker(self):
        """预览工作线程"""
        while not self._stop_preview.is_set():
            start_time = time.time()

            # 生成或获取图像
            if self._media_files:
                # 使用媒体文件
                frame_array = self._get_media_frame()
            else:
                # 生成模拟图像
                image = self._generate_simulation_image(pattern=(self._frame_count // 100) % 5)
                frame_array = np.array(image)
                frame_array = self._apply_camera_effects(frame_array)

            self._frame_count += 1

            # 调用预览回调
            for callback in self._preview_callbacks:
                try:
                    callback(frame_array)
                except Exception as e:
                    error(f"Preview callback error: {e}", "SIMULATION_CAMERA")

            # 控制帧率
            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / self.fps) - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _get_media_frame(self) -> np.ndarray:
        """获取媒体文件帧"""
        debug(f"Getting media frame. Media files: {len(self._media_files)}, Media type: {self._media_type}", "SIMULATION_CAMERA")

        if not self._media_files:
            # 回退到生成图像
            warning("No media files available, falling back to generated image", "SIMULATION_CAMERA")
            image = self._generate_simulation_image()
            return np.array(image)

        try:
            if self._media_type == "image":
                # 循环显示图片
                image_path = self._media_files[self._current_media_index]
                debug(f"Loading image: {image_path} (index: {self._current_media_index})", "SIMULATION_CAMERA")

                # 检查文件是否存在
                if not os.path.exists(image_path):
                    error(f"Image file does not exist: {image_path}", "SIMULATION_CAMERA")
                    image = self._generate_simulation_image()
                    return np.array(image)

                # 加载图片并转换为RGB
                image = Image.open(image_path)
                debug(f"Original image mode: {image.mode}, size: {image.size}", "SIMULATION_CAMERA")

                # 确保图片是RGB模式
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                    debug(f"Converted image to RGB mode", "SIMULATION_CAMERA")

                # 只在必要时调整大小（如果图像尺寸与相机分辨率不匹配）
                if image.size != (self.width, self.height):
                    debug(f"Resizing image from {image.size} to {self.width}x{self.height}", "SIMULATION_CAMERA")
                    image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
                else:
                    debug(f"Image size matches camera resolution: {image.size}", "SIMULATION_CAMERA")

                # 转换为numpy数组
                frame_array = np.array(image)
                debug(f"Frame array shape: {frame_array.shape}, dtype: {frame_array.dtype}", "SIMULATION_CAMERA")

                # 在返回当前帧后，立即切换到下一张图片（为下一帧做准备）
                self._current_media_index = (self._current_media_index + 1) % len(self._media_files)
                debug(f"Switching to next image: index {self._current_media_index} (next frame)", "SIMULATION_CAMERA")

            else:
                # 视频文件处理（简化实现）
                image_path = self._media_files[self._current_media_index]
                debug(f"Loading video frame: {image_path}", "SIMULATION_CAMERA")

                # 检查文件是否存在
                if not os.path.exists(image_path):
                    error(f"Video file does not exist: {image_path}", "SIMULATION_CAMERA")
                    image = self._generate_simulation_image()
                    return np.array(image)

                image = Image.open(image_path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                if image.size != (self.width, self.height):
                    image = image.resize((self.width, self.height), Image.Resampling.LANCZOS)
                frame_array = np.array(image)

                # 模拟视频播放
                if self._frame_count % self.fps == 0:
                    self._current_media_index = (self._current_media_index + 1) % len(self._media_files)

            return self._apply_camera_effects(frame_array)

        except Exception as e:
            error(f"Error loading media frame: {e}", "SIMULATION_CAMERA")
            error(f"Media files: {self._media_files}", "SIMULATION_CAMERA")
            error(f"Current media index: {self._current_media_index}", "SIMULATION_CAMERA")
            # 回退到生成图像
            image = self._generate_simulation_image()
            return np.array(image)

    def register_preview_callback(self, callback) -> bool:
        """注册预览回调函数"""
        if callback not in self._preview_callbacks:
            self._preview_callbacks.append(callback)
        return True

    def unregister_preview_callback(self, callback) -> bool:
        """取消注册预览回调函数"""
        if callback in self._preview_callbacks:
            self._preview_callbacks.remove(callback)
        return True

    def capture_frame(self) -> Optional[np.ndarray]:
        """抓取一帧图像 - 实现抽象方法"""
        return self.capture_image()

    def start_streaming(self, callback: Callable[[np.ndarray], None]) -> bool:
        """开始视频流 - 实现抽象方法"""
        if not self._connected:
            return False

        # 清除现有的预览回调
        self._preview_callbacks.clear()

        # 注册新的回调
        if callback:
            self._preview_callbacks.append(callback)
            return self.start_preview(callback)

        return False

    def stop_streaming(self) -> bool:
        """停止视频流 - 实现抽象方法"""
        result = self.stop_preview()
        # 清除所有回调
        self._preview_callbacks.clear()
        return result

    def is_streaming(self) -> bool:
        """检查是否正在流式传输"""
        return self._preview_thread and self._preview_thread.is_alive() and not self._stop_preview.is_set()

    def trigger_software(self) -> bool:
        """软件触发 - 实现抽象方法"""
        if not self._connected:
            return False
        debug("Software trigger simulation", "SIMULATION_CAMERA")
        return True

    def test_connection(self) -> Dict[str, Any]:
        """测试连接 - 实现抽象方法"""
        if self._connected:
            return {
                'success': True,
                'message': 'Simulation camera connection test successful',
                'camera_id': self.camera_id,
                'resolution': f"{self.width}x{self.height}",
                'fps': self.fps
            }
        else:
            return {
                'success': False,
                'message': 'Simulation camera not connected',
                'camera_id': self.camera_id
            }

    def get_optimized_config(self, original_config: Dict[str, Any]) -> Dict[str, Any]:
        """获取优化后的配置（包含自动检测的最大分辨率）"""
        optimized_config = original_config.copy()
        optimized_config['resolution'] = f"{self.width}x{self.height}"
        optimized_config['auto_detected_resolution'] = True

        info(f"Optimized config resolution: {self.width}x{self.height} (auto-detected from media files)", "SIMULATION_CAMERA")
        return optimized_config