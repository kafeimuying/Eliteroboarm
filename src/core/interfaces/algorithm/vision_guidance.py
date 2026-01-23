#!/usr/bin/env python3
"""
视觉引导算法模块
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict, Any
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal

from .vision_data_types import Position3D
from ....managers.log_manager import LogManager


@dataclass
class EdgePoint:
    """边缘点数据类"""
    x: float
    y: float
    angle: float = 0.0
    confidence: float = 1.0


@dataclass
class GrabResult:
    """抓取结果数据类"""
    success: bool
    edge_points: List[EdgePoint]
    image: Optional[np.ndarray] = None
    error_message: str = ""


class VisionGuidance(QObject):
    """视觉引导算法类"""
    result_ready = pyqtSignal(GrabResult)
    
    def __init__(self, log_manager: LogManager):
        super().__init__()
        self.log_manager = log_manager
        self.is_calibrated = False
        self.camera_matrix = None
        self.dist_coeffs = None
        
    def set_calibration(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        """设置相机标定参数"""
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.is_calibrated = True
        self.log_manager.log('INFO', '视觉引导算法已设置相机标定参数')
        
    def grab_edge_detection(self, image: np.ndarray, 
                           roi: Tuple[int, int, int, int] = None,
                           threshold: int = 127,
                           min_line_length: int = 50) -> GrabResult:
        """
        抓边检测算法
        
        Args:
            image: 输入图像
            roi: 感兴趣区域 (x, y, width, height)
            threshold: 边缘检测阈值
            min_line_length: 最小线段长度
            
        Returns:
            GrabResult: 抓取结果
        """
        try:
            if image is None:
                return GrabResult(False, [], error_message="输入图像为空")
            
            # 处理ROI
            if roi:
                x, y, w, h = roi
                processed_image = image[y:y+h, x:x+w]
            else:
                processed_image = image.copy()
                
            # 转换为灰度图
            if len(processed_image.shape) == 3:
                gray = cv2.cvtColor(processed_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = processed_image
                
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
                    
                    # 如果有ROI偏移，需要调整坐标
                    if roi:
                        mid_x += roi[0]
                        mid_y += roi[1]
                        
                    edge_point = EdgePoint(mid_x, mid_y, angle)
                    edge_points.append(edge_point)
                    
            # 绘制结果用于调试
            debug_image = self._draw_results(image.copy(), edge_points, roi)
            
            self.log_manager.log('INFO', f'抓边检测完成，检测到 {len(edge_points)} 个边缘点')
            return GrabResult(True, edge_points, debug_image)
            
        except Exception as e:
            self.log_manager.log('ERROR', f'抓边检测失败: {str(e)}')
            return GrabResult(False, [], error_message=str(e))
            
    def _draw_results(self, image: np.ndarray, edge_points: List[EdgePoint], 
                     roi: Tuple[int, int, int, int] = None) -> np.ndarray:
        """绘制检测结果"""
        # 绘制ROI
        if roi:
            x, y, w, h = roi
            cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)
            
        # 绘制边缘点（只绘制抓到的边，不绘制ROI框）
        for point in edge_points:
            # 绘制点
            cv2.circle(image, (int(point.x), int(point.y)), 5, (0, 255, 0), -1)  # 绿色点
            
            # 绘制角度线
            length = 20
            end_x = int(point.x + length * np.cos(point.angle * np.pi / 180))
            end_y = int(point.y + length * np.sin(point.angle * np.pi / 180))
            cv2.line(image, (int(point.x), int(point.y)), (end_x, end_y), (0, 255, 0), 2)  # 绿色线
            
        return image
        
    def convert_image_to_world(self, edge_points: List[EdgePoint], 
                              z_height: float = 0.0) -> List[Position3D]:
        """
        将图像坐标转换为世界坐标
        
        Args:
            edge_points: 图像坐标系中的边缘点
            z_height: Z轴高度
            
        Returns:
            List[Position3D]: 世界坐标系中的位置
        """
        positions = []
        
        # 简单的像素到世界坐标转换（实际应用中需要更复杂的标定）
        # 这里只是一个示例，实际应用中需要根据相机标定参数进行转换
        pixel_to_mm = 0.5  # 假设每个像素代表0.5mm
        
        for point in edge_points:
            # 转换到世界坐标系
            x_world = point.x * pixel_to_mm
            y_world = point.y * pixel_to_mm
            
            position = Position3D(x_world, y_world, z_height, 0, 0, point.angle)
            positions.append(position)
            
        return positions
        
    def filter_edge_points(self, edge_points: List[EdgePoint], 
                          criteria: Dict[str, Any]) -> List[EdgePoint]:
        """
        根据指定条件过滤边缘点
        
        Args:
            edge_points: 边缘点列表
            criteria: 过滤条件字典
            
        Returns:
            List[EdgePoint]: 过滤后的边缘点
        """
        filtered_points = edge_points.copy()
        
        # 根据置信度过滤
        if 'min_confidence' in criteria:
            filtered_points = [p for p in filtered_points 
                             if p.confidence >= criteria['min_confidence']]
                             
        # 根据角度过滤
        if 'angle_range' in criteria:
            min_angle, max_angle = criteria['angle_range']
            filtered_points = [p for p in filtered_points 
                             if min_angle <= p.angle <= max_angle]
                             
        # 根据数量过滤（选择置信度最高的N个）
        if 'max_count' in criteria:
            filtered_points.sort(key=lambda p: p.confidence, reverse=True)
            filtered_points = filtered_points[:criteria['max_count']]
            
        return filtered_points