#!/usr/bin/env python3
"""
高斯模糊算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class GaussianBlurAlgorithm(AlgorithmBase):
    """高斯模糊算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="gaussian_blur",
            display_name="高斯模糊",
            description="对图像进行高斯模糊处理，可用于降噪和预处理",
            category="基础算子",  # 一级目录
            secondary_category="预处理",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["模糊", "降噪", "预处理"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="kernel_size",
                param_type=ParameterType.INT,
                default_value=5,
                description="模糊核大小（必须为奇数）",
                min_value=1,
                max_value=31,
                step=2
            ),
            AlgorithmParameter(
                name="sigma_x",
                param_type=ParameterType.FLOAT,
                default_value=0.0,
                description="X方向标准差（0表示自动计算）",
                min_value=0.0,
                max_value=10.0,
                step=0.1
            ),
            AlgorithmParameter(
                name="sigma_y",
                param_type=ParameterType.FLOAT,
                default_value=0.0,
                description="Y方向标准差（0表示自动计算）",
                min_value=0.0,
                max_value=10.0,
                step=0.1
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            kernel_size = self.get_parameter("kernel_size")
            sigma_x = self.get_parameter("sigma_x")
            sigma_y = self.get_parameter("sigma_y")

            # 确保核大小为奇数
            if kernel_size % 2 == 0:
                kernel_size += 1

            # 执行高斯模糊
            blurred = cv2.GaussianBlur(input_image, (kernel_size, kernel_size), sigma_x, sigmaY=sigma_y)

            processing_time = time.time() - start_time

            return AlgorithmResult(
                success=True,
                output_image=blurred,
                processing_time=processing_time
            )

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )