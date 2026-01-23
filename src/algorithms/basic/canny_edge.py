#!/usr/bin/env python3
"""
Canny边缘检测算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class CannyEdgeDetectionAlgorithm(AlgorithmBase):
    """Canny边缘检测算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="canny_edge",
            display_name="Canny边缘检测",
            description="使用Canny算法进行边缘检测",
            category="基础算子",  # 一级目录
            secondary_category="边缘检测",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["边缘检测", "特征提取"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="low_threshold",
                param_type=ParameterType.INT,
                default_value=50,
                description="低阈值",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="high_threshold",
                param_type=ParameterType.INT,
                default_value=150,
                description="高阈值",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="aperture_size",
                param_type=ParameterType.CHOICE,
                default_value="3",
                description="Sobel算子核大小",
                choices=["3", "5", "7"]
            ),
            AlgorithmParameter(
                name="l2_gradient",
                param_type=ParameterType.BOOL,
                default_value=False,
                description="是否使用L2范数计算梯度"
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            low_threshold = self.get_parameter("low_threshold")
            high_threshold = self.get_parameter("high_threshold")
            aperture_size = int(self.get_parameter("aperture_size"))
            l2_gradient = self.get_parameter("l2_gradient")

            # 转换为灰度图
            if len(input_image.shape) == 3:
                gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = input_image

            # Canny边缘检测
            edges = cv2.Canny(gray, low_threshold, high_threshold,
                            apertureSize=aperture_size, L2gradient=l2_gradient)

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=edges,
                processing_time=processing_time
            )

            # 添加中间结果
            result.add_intermediate_result("gray", gray)

            return result

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )