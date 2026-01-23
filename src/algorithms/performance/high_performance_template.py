#!/usr/bin/env python3
"""
高性能模板匹配算法
"""

import cv2
import numpy as np
import time
import os
from typing import List

# 导入C++扩展包装器
from cpp_extensions.cpp_wrapper import template_matching

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
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