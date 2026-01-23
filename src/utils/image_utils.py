#!/usr/bin/env python3
"""
图像转换工具函数
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List
from PyQt6.QtGui import QImage, QPixmap
from core.managers.log_manager import info, debug, warning, error


def numpy_to_qimage(image: np.ndarray) -> QImage:
    """
    将numpy数组转换为QImage，解决memoryview类型问题
    
    Args:
        image: numpy数组，可以是RGB或灰度图像
        
    Returns:
        QImage对象
    """
    try:
        if len(image.shape) == 3:
            # RGB图像
            height, width, channel = image.shape
            bytes_per_line = 3 * width
            
            # 确保数据类型正确，处理memoryview问题
            image_data = image.data
            if hasattr(image_data, 'tobytes'):
                image_data = image_data.tobytes()
            
            q_image = QImage(image_data, width, height, bytes_per_line, QImage.Format.Format_BGR888).rgbSwapped()
        else:
            # 灰度图像
            height, width = image.shape
            bytes_per_line = width
            
            # 确保数据类型正确，处理memoryview问题
            image_data = image.data
            if hasattr(image_data, 'tobytes'):
                image_data = image_data.tobytes()
            
            q_image = QImage(image_data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        
        return q_image
        
    except Exception as e:
        print(f"Error converting numpy array to QImage: {e}")
        # 返回一个空的QImage作为fallback
        return QImage()


def numpy_to_qpixmap(image: np.ndarray) -> QPixmap:
    """
    将numpy数组转换为QPixmap
    
    Args:
        image: numpy数组
        
    Returns:
        QPixmap对象
    """
    try:
        q_image = numpy_to_qimage(image)
        return QPixmap.fromImage(q_image)
    except Exception as e:
        print(f"Error converting numpy array to QPixmap: {e}")
        return QPixmap()


def ensure_contiguous(image: np.ndarray) -> np.ndarray:
    """
    确保numpy数组是内存连续的
    
    Args:
        image: 输入numpy数组
        
    Returns:
        内存连续的numpy数组
    """
    if not image.flags['C_CONTIGUOUS']:
        return np.ascontiguousarray(image)
    return image


def load_image(image_path: str, color_mode: str = 'BGR') -> Optional[np.ndarray]:
    """
    统一的图像加载函数

    Args:
        image_path: 图像文件路径
        color_mode: 颜色模式 ('BGR', 'RGB', 'GRAY')

    Returns:
        numpy.ndarray: 图像数组，失败时返回None
    """
    try:
        # 检查文件是否存在
        if not Path(image_path).exists():
            error(f"图像文件不存在: {image_path}", "IMAGE_UTILS")
            return None

        # 使用OpenCV加载图像
        image = cv2.imread(image_path)
        if image is None:
            error(f"无法读取图像文件: {image_path}", "IMAGE_UTILS")
            return None

        # 处理颜色模式
        if color_mode == 'RGB':
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        elif color_mode == 'GRAY':
            if len(image.shape) == 3:
                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # 如果已经是灰度图，保持不变

        debug(f"成功加载图像: {image_path}, 尺寸: {image.shape}, 模式: {color_mode}", "IMAGE_UTILS")
        return image

    except Exception as e:
        error(f"加载图像失败: {image_path}, 错误: {str(e)}", "IMAGE_UTILS")
        return None


def save_image(image: np.ndarray, save_path: str, quality: int = 95) -> bool:
    """
    统一的图像保存函数

    Args:
        image: 要保存的图像数组
        save_path: 保存路径
        quality: JPEG质量 (1-100)

    Returns:
        bool: 保存是否成功
    """
    try:
        # 确保目录存在
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        # 根据文件扩展名设置保存参数
        file_ext = Path(save_path).suffix.lower()
        if file_ext in ['.jpg', '.jpeg']:
            params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        elif file_ext == '.png':
            params = [cv2.IMWRITE_PNG_COMPRESSION, 9]
        else:
            params = []

        success = cv2.imwrite(save_path, image, params)

        if success:
            info(f"图像保存成功: {save_path}", "IMAGE_UTILS")
        else:
            error(f"图像保存失败: {save_path}", "IMAGE_UTILS")

        return success

    except Exception as e:
        error(f"保存图像失败: {save_path}, 错误: {str(e)}", "IMAGE_UTILS")
        return False


def get_image_info(image: np.ndarray) -> dict:
    """
    获取图像基本信息

    Args:
        image: 图像数组

    Returns:
        dict: 图像信息字典
    """
    try:
        info_dict = {
            'shape': image.shape,
            'dtype': str(image.dtype),
            'size': image.size,
            'height': image.shape[0],
            'width': image.shape[1] if len(image.shape) > 1 else 1,
            'channels': image.shape[2] if len(image.shape) == 3 else 1,
            'min_value': float(image.min()),
            'max_value': float(image.max()),
            'mean_value': float(image.mean())
        }

        debug(f"图像信息: {info_dict}", "IMAGE_UTILS")
        return info_dict

    except Exception as e:
        error(f"获取图像信息失败: {str(e)}", "IMAGE_UTILS")
        return {}


def resize_image(image: np.ndarray, size: Tuple[int, int],
                 interpolation: int = cv2.INTER_LINEAR) -> Optional[np.ndarray]:
    """
    统一的图像缩放函数

    Args:
        image: 输入图像
        size: 目标尺寸 (width, height)
        interpolation: 插值方法

    Returns:
        numpy.ndarray: 缩放后的图像，失败时返回None
    """
    try:
        resized = cv2.resize(image, size, interpolation=interpolation)
        debug(f"图像缩放: {image.shape} -> {resized.shape}", "IMAGE_UTILS")
        return resized

    except Exception as e:
        error(f"图像缩放失败: {str(e)}", "IMAGE_UTILS")
        return None


def convert_color(image: np.ndarray, conversion: str) -> Optional[np.ndarray]:
    """
    统一的颜色空间转换函数

    Args:
        image: 输入图像
        conversion: 转换类型 ('BGR2RGB', 'BGR2GRAY', 'RGB2BGR', 'GRAY2BGR')

    Returns:
        numpy.ndarray: 转换后的图像，失败时返回None
    """
    try:
        conversion_map = {
            'BGR2RGB': cv2.COLOR_BGR2RGB,
            'BGR2GRAY': cv2.COLOR_BGR2GRAY,
            'RGB2BGR': cv2.COLOR_RGB2BGR,
            'GRAY2BGR': cv2.COLOR_GRAY2BGR,
            'RGB2GRAY': cv2.COLOR_RGB2GRAY,
            'GRAY2RGB': cv2.COLOR_GRAY2RGB
        }

        if conversion not in conversion_map:
            error(f"不支持的颜色转换: {conversion}", "IMAGE_UTILS")
            return None

        converted = cv2.cvtColor(image, conversion_map[conversion])
        debug(f"颜色空间转换: {conversion}", "IMAGE_UTILS")
        return converted

    except Exception as e:
        error(f"颜色空间转换失败: {conversion}, 错误: {str(e)}", "IMAGE_UTILS")
        return None


def create_test_image(width: int = 640, height: int = 480,
                     pattern: str = 'random') -> np.ndarray:
    """
    创建测试图像

    Args:
        width: 图像宽度
        height: 图像高度
        pattern: 图案类型 ('random', 'gradient', 'checkerboard', 'circles')

    Returns:
        numpy.ndarray: 测试图像
    """
    try:
        if pattern == 'random':
            image = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        elif pattern == 'gradient':
            image = np.zeros((height, width, 3), dtype=np.uint8)
            for i in range(width):
                image[:, i] = [int(255 * i / width),
                              int(255 * (1 - i / width)),
                              128]
        elif pattern == 'checkerboard':
            image = np.zeros((height, width, 3), dtype=np.uint8)
            block_size = 32
            for i in range(0, height, block_size):
                for j in range(0, width, block_size):
                    if (i // block_size + j // block_size) % 2 == 0:
                        image[i:i+block_size, j:j+block_size] = [255, 255, 255]
        elif pattern == 'circles':
            image = np.random.randint(0, 100, (height, width, 3), dtype=np.uint8)
            # 添加一些圆形
            cv2.circle(image, (width//4, height//4), 50, (255, 0, 0), 2)
            cv2.circle(image, (3*width//4, height//4), 50, (0, 255, 0), 2)
            cv2.circle(image, (width//2, 3*height//4), 50, (0, 0, 255), 2)
            cv2.line(image, (50, height-50), (width-50, height-50), (255, 255, 255), 3)
            cv2.putText(image, "Test Image", (width//4, height//2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        else:
            image = np.zeros((height, width, 3), dtype=np.uint8)

        debug(f"创建测试图像: {width}x{height}, 模式: {pattern}", "IMAGE_UTILS")
        return image

    except Exception as e:
        error(f"创建测试图像失败: {str(e)}", "IMAGE_UTILS")
        return np.zeros((height, width, 3), dtype=np.uint8)


def validate_image(image: np.ndarray) -> bool:
    """
    验证图像数据是否有效

    Args:
        image: 图像数组

    Returns:
        bool: 图像是否有效
    """
    try:
        if image is None:
            error("图像数据为None", "IMAGE_UTILS")
            return False

        if not isinstance(image, np.ndarray):
            error(f"图像数据不是numpy数组: {type(image)}", "IMAGE_UTILS")
            return False

        if image.size == 0:
            error("图像数据为空", "IMAGE_UTILS")
            return False

        if len(image.shape) not in [2, 3]:
            error(f"不支持的图像维度: {len(image.shape)}", "IMAGE_UTILS")
            return False

        if len(image.shape) == 3 and image.shape[2] not in [1, 3, 4]:
            error(f"不支持的通道数: {image.shape[2]}", "IMAGE_UTILS")
            return False

        debug("图像数据验证通过", "IMAGE_UTILS")
        return True

    except Exception as e:
        error(f"图像数据验证失败: {str(e)}", "IMAGE_UTILS")
        return False


def get_supported_image_formats() -> List[str]:
    """
    获取支持的图像文件格式

    Returns:
        List[str]: 支持的文件扩展名列表
    """
    return [
        '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif',
        '.webp', '.jp2', '.pgm', '.pbm', '.ppm', '.sr', '.ras'
    ]


def is_image_file(file_path: str) -> bool:
    """
    检查文件是否为支持的图像格式

    Args:
        file_path: 文件路径

    Returns:
        bool: 是否为支持的图像格式
    """
    try:
        ext = Path(file_path).suffix.lower()
        supported_formats = get_supported_image_formats()
        is_supported = ext in supported_formats

        if is_supported:
            debug(f"支持的图像格式: {file_path}", "IMAGE_UTILS")
        else:
            warning(f"不支持的图像格式: {file_path}", "IMAGE_UTILS")

        return is_supported

    except Exception as e:
        error(f"检查图像格式失败: {file_path}, 错误: {str(e)}", "IMAGE_UTILS")
        return False