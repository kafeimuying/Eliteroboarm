#!/usr/bin/env python3
"""
高性能视觉算法实现
使用C++扩展实现的高性能算法
"""

import cv2
import numpy as np
import time
import os
from typing import List

# 导入C++扩展包装器
# cpp_wrapper已经处理了导入失败的情况，会自动回退到Python实现
from cpp_extensions.cpp_wrapper import roi_edge_detection, template_matching

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class HighPerformanceROIEdgeDetectionAlgorithm(AlgorithmBase):
    """高性能ROI抓边检测算法"""
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="hp_roi_edge_detection",
            display_name="高性能ROI抓边检测",
            description="使用C++扩展实现的高性能ROI区域抓边检测算法",
            category="高性能算子",  # 一级目录
            secondary_category="边缘检测",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["抓边", "边缘检测", "高性能", "C++"]
        )
    
    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="roi_region",
                param_type=ParameterType.ROI,
                default_value={"x": 0, "y": 0, "width": 200, "height": 200},
                description="感兴趣区域",
                roi_mode="manual"
            ),
            AlgorithmParameter(
                name="threshold",
                param_type=ParameterType.INT,
                default_value=127,
                description="边缘检测阈值",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="min_line_length",
                param_type=ParameterType.INT,
                default_value=50,
                description="最小线段长度",
                min_value=10,
                max_value=500
            )
        ]
    
    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()
        
        try:
            # 获取参数
            roi_region = self.get_parameter("roi_region")
            roi_x = roi_region.get("x", 0)
            roi_y = roi_region.get("y", 0)
            roi_width = roi_region.get("width", 200)
            roi_height = roi_region.get("height", 200)
            threshold = self.get_parameter("threshold")
            min_line_length = self.get_parameter("min_line_length")
            
            # 使用C++扩展或Python实现执行抓边检测
            # cpp_wrapper已经处理了回退机制
            edge_points = roi_edge_detection(
                input_image, roi_x, roi_y, roi_width, roi_height, threshold, min_line_length
            )
            
            # 绘制结果
            result_image = input_image.copy()
            
            # 绘制ROI框
            h, w = input_image.shape[:2]
            roi_x = min(roi_x, w - 1)
            roi_y = min(roi_y, h - 1)
            roi_width = min(roi_width, w - roi_x)
            roi_height = min(roi_height, h - roi_y)
            
            cv2.rectangle(result_image, (roi_x, roi_y), 
                         (roi_x + roi_width, roi_y + roi_height), (0, 255, 0), 2)
            
            # 绘制边缘点
            for x, y, angle in edge_points:
                # 绘制边缘点
                cv2.circle(result_image, (int(x), int(y)), 5, (0, 255, 0), -1)
                
                # 绘制角度线
                length = 20
                end_x = int(x + length * np.cos(angle * np.pi / 180))
                end_y = int(y + length * np.sin(angle * np.pi / 180))
                cv2.line(result_image, (int(x), int(y)), (end_x, end_y), (0, 255, 0), 2)
            
            processing_time = time.time() - start_time
            
            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={"edge_points_count": len(edge_points)}
            )
            
            return result
            
        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )


class HighPerformanceTemplateMatchingAlgorithm(AlgorithmBase):
    """高性能模板匹配算法"""
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="hp_template_matching",
            display_name="高性能模板匹配",
            description="使用C++扩展实现的高性能模板匹配算法",
            category="高性能算子",  # 一级目录
            secondary_category="模式匹配",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["模板匹配", "模式识别", "高性能", "C++"]
        )
    
    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="template_path",
                param_type=ParameterType.FILE,
                default_value="",
                description="模板图像路径",
                required=True
            ),
            AlgorithmParameter(
                name="method",
                param_type=ParameterType.CHOICE,
                default_value="TM_CCOEFF_NORMED",
                description="匹配方法",
                choices=["TM_CCOEFF", "TM_CCOEFF_NORMED", "TM_CCORR", 
                        "TM_CCORR_NORMED", "TM_SQDIFF", "TM_SQDIFF_NORMED"]
            ),
            AlgorithmParameter(
                name="threshold",
                param_type=ParameterType.FLOAT,
                default_value=0.8,
                description="匹配阈值",
                min_value=0.0,
                max_value=1.0,
                step=0.01
            ),
            AlgorithmParameter(
                name="multiple_matches",
                param_type=ParameterType.BOOL,
                default_value=False,
                description="检测多个匹配"
            ),
            AlgorithmParameter(
                name="roi_region",
                param_type=ParameterType.ROI,
                default_value={"x": 0, "y": 0, "width": 0, "height": 0},
                description="感兴趣区域 (宽高为0表示全图)",
                roi_mode="manual"
            )
        ]
    
    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()
        
        try:
            # 获取参数
            template_path = self.get_parameter("template_path")
            method_name = self.get_parameter("method")
            threshold = self.get_parameter("threshold")
            multiple_matches = self.get_parameter("multiple_matches")
            roi_region = self.get_parameter("roi_region")
            roi_x = roi_region.get("x", 0)
            roi_y = roi_region.get("y", 0)
            roi_width = roi_region.get("width", 0)
            roi_height = roi_region.get("height", 0)
            
            if not template_path or not os.path.exists(template_path):
                return AlgorithmResult(
                    success=False,
                    error_message="模板文件不存在或路径为空"
                )
            
            # 加载模板
            template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
            if template is None:
                return AlgorithmResult(
                    success=False,
                    error_message="无法加载模板图像"
                )
            
            # 获取OpenCV方法常量
            method = getattr(cv2, method_name)
            
            # 使用C++扩展或Python实现执行模板匹配
            # cpp_wrapper已经处理了回退机制
            matches = template_matching(
                input_image, template, method, threshold, multiple_matches,
                roi_x, roi_y, roi_width, roi_height
            )
            
            # 绘制结果
            result_image = input_image.copy()
            template_h, template_w = template.shape
            
            for x, y, confidence in matches:
                cv2.rectangle(result_image, (x, y), 
                            (x + template_w, y + template_h), (0, 255, 0), 2)
            
            processing_time = time.time() - start_time
            
            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={"match_count": len(matches), "matches": [
                    {"position": (x, y), "confidence": confidence} for x, y, confidence in matches
                ]}
            )
            
            return result
            
        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )