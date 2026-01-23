#!/usr/bin/env python3
"""
C++扩展包装器
提供Python接口调用C++实现的高性能视觉算法
"""

import numpy as np
import cv2
import os
import sys
# 添加扩展模块所在目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'extensions'))

# 添加src目录到路径，以便导入日志模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from typing import List, Tuple

try:
    from core.managers.log_manager import info, warning, LogCategory
except ImportError:
    # 如果无法导入日志模块，使用print作为备用
    def info(msg, module, category):
        print(f"[INFO] [{module}] {msg}")
    def warning(msg, module, category):
        print(f"[WARNING] [{module}] {msg}")
    class LogCategory:
        SOFTWARE = "software"

# 尝试导入C++扩展
try:
    import vision_cpp_ext
    CPP_EXTENSION_AVAILABLE = True
    info("C++ extension loaded successfully.", "CPP_WRAPPER", LogCategory.SOFTWARE)
except ImportError:
    CPP_EXTENSION_AVAILABLE = False
    warning("Warning: C++ extension not available. Using Python implementation.", "CPP_WRAPPER", LogCategory.SOFTWARE)


def roi_edge_detection_cpp(image: np.ndarray, 
                          roi_x: int, roi_y: int, roi_width: int, roi_height: int,
                          threshold: int = 127, min_line_length: int = 50) -> List[Tuple[float, float, float]]:
    """
    使用C++扩展的ROI抓边检测
    
    Args:
        image: 输入图像
        roi_x, roi_y: ROI起始坐标
        roi_width, roi_height: ROI尺寸
        threshold: 边缘检测阈值
        min_line_length: 最小线段长度
        
    Returns:
        List of (x, y, angle) tuples representing edge points
    """
    if not CPP_EXTENSION_AVAILABLE:
        raise RuntimeError("C++ extension not available")
    
    # 转换为灰度图
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # 调用C++函数
    edge_points = vision_cpp_ext.roi_edge_detection(
        gray, roi_x, roi_y, roi_width, roi_height, threshold, min_line_length
    )
    
    return edge_points


def template_matching_cpp(image: np.ndarray, template: np.ndarray,
                         method: int = cv2.TM_CCOEFF_NORMED, threshold: float = 0.8,
                         multiple_matches: bool = False,
                         roi_x: int = 0, roi_y: int = 0, roi_width: int = 0, roi_height: int = 0) -> List[Tuple[int, int, float]]:
    """
    使用C++扩展的模板匹配
    
    Args:
        image: 输入图像
        template: 模板图像
        method: 匹配方法
        threshold: 匹配阈值
        multiple_matches: 是否检测多个匹配
        roi_x, roi_y: ROI起始坐标
        roi_width, roi_height: ROI尺寸 (0表示全图)
        
    Returns:
        List of (x, y, confidence) tuples representing matches
    """
    if not CPP_EXTENSION_AVAILABLE:
        raise RuntimeError("C++ extension not available")
    
    # 转换为灰度图
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    if len(template.shape) == 3:
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    else:
        template_gray = template
    
    # 调用C++函数
    matches = vision_cpp_ext.template_matching(
        gray, template_gray, method, threshold, multiple_matches,
        roi_x, roi_y, roi_width, roi_height
    )
    
    return matches


# Python实现的备选方案
def roi_edge_detection_py(image: np.ndarray, 
                         roi_x: int, roi_y: int, roi_width: int, roi_height: int,
                         threshold: int = 127, min_line_length: int = 50) -> List[Tuple[float, float, float]]:
    """
    Python实现的ROI抓边检测（备选方案）
    """
    # 确保ROI不超出图像边界
    h, w = image.shape[:2]
    roi_x = min(roi_x, w - 1)
    roi_y = min(roi_y, h - 1)
    roi_width = min(roi_width, w - roi_x)
    roi_height = min(roi_height, h - roi_y)
    
    # 提取ROI
    roi_image = image[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width]
    
    # 转换为灰度图
    if len(roi_image.shape) == 3:
        gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi_image
    
    # 高斯模糊
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Canny边缘检测
    edges = cv2.Canny(blurred, threshold, threshold * 2)
    
    # 形态学操作
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    
    # 霍夫直线检测
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, 
                           minLineLength=min_line_length, maxLineGap=10)
    
    edge_points = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # 计算线段中点
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            
            # 计算角度
            angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
            
            # 调整坐标到原图坐标系
            mid_x += roi_x
            mid_y += roi_y
            
            edge_points.append((mid_x, mid_y, angle))
    
    return edge_points


def template_matching_py(image: np.ndarray, template: np.ndarray,
                        method: int = cv2.TM_CCOEFF_NORMED, threshold: float = 0.8,
                        multiple_matches: bool = False,
                        roi_x: int = 0, roi_y: int = 0, roi_width: int = 0, roi_height: int = 0) -> List[Tuple[int, int, float]]:
    """
    Python实现的模板匹配（备选方案）
    """
    # 处理ROI
    h, w = image.shape[:2]
    if roi_width == 0 or roi_height == 0:
        # 使用全图
        roi_x, roi_y = 0, 0
        roi_width, roi_height = w, h
    else:
        # 确保ROI不超出图像边界
        roi_x = min(roi_x, w - 1)
        roi_y = min(roi_y, h - 1)
        roi_width = min(roi_width, w - roi_x)
        roi_height = min(roi_height, h - roi_y)
    
    # 提取ROI
    roi_image = image[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width]
    
    # 转换输入图像为灰度
    if len(roi_image.shape) == 3:
        gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi_image
    
    if len(template.shape) == 3:
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    else:
        template_gray = template
    
    # 模板匹配
    result_matrix = cv2.matchTemplate(gray, template_gray, method)
    
    matches = []
    template_h, template_w = template_gray.shape
    
    if multiple_matches:
        # 多匹配检测
        locations = np.where(result_matrix >= threshold)
        for pt in zip(*locations[::-1]):
            # 调整坐标到原图坐标系
            abs_x = pt[0] + roi_x
            abs_y = pt[1] + roi_y
            
            confidence = result_matrix[pt[1], pt[0]]
            matches.append((abs_x, abs_y, confidence))
    else:
        # 单一最佳匹配
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result_matrix)
        
        if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            match_loc = min_loc
            confidence = 1 - min_val
        else:
            match_loc = max_loc
            confidence = max_val
        
        if confidence >= threshold:
            # 调整坐标到原图坐标系
            abs_x = match_loc[0] + roi_x
            abs_y = match_loc[1] + roi_y
            
            matches.append((abs_x, abs_y, confidence))
    
    return matches


# 统一接口函数
def roi_edge_detection(image: np.ndarray, 
                      roi_x: int, roi_y: int, roi_width: int, roi_height: int,
                      threshold: int = 127, min_line_length: int = 50):
    """
    ROI抓边检测统一接口
    """
    if CPP_EXTENSION_AVAILABLE:
        return roi_edge_detection_cpp(image, roi_x, roi_y, roi_width, roi_height, threshold, min_line_length)
    else:
        return roi_edge_detection_py(image, roi_x, roi_y, roi_width, roi_height, threshold, min_line_length)


def template_matching(image: np.ndarray, template: np.ndarray,
                     method: int = cv2.TM_CCOEFF_NORMED, threshold: float = 0.8,
                     multiple_matches: bool = False,
                     roi_x: int = 0, roi_y: int = 0, roi_width: int = 0, roi_height: int = 0):
    """
    模板匹配统一接口
    """
    if CPP_EXTENSION_AVAILABLE:
        return template_matching_cpp(image, template, method, threshold, multiple_matches, roi_x, roi_y, roi_width, roi_height)
    else:
        return template_matching_py(image, template, method, threshold, multiple_matches, roi_x, roi_y, roi_width, roi_height)