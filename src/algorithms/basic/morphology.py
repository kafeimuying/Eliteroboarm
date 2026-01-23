#!/usr/bin/env python3
"""
形态学操作算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class MorphologyAlgorithm(AlgorithmBase):
    """形态学操作算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="morphology",
            display_name="形态学操作",
            description="对图像进行形态学操作（腐蚀、膨胀、开运算、闭运算等）",
            category="基础算子",  # 一级目录
            secondary_category="形态学",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["形态学", "腐蚀", "膨胀", "开运算", "闭运算"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="operation",
                param_type=ParameterType.CHOICE,
                default_value="MORPH_CLOSE",
                description="形态学操作类型",
                choices=["MORPH_ERODE", "MORPH_DILATE", "MORPH_OPEN",
                        "MORPH_CLOSE", "MORPH_GRADIENT", "MORPH_TOPHAT", "MORPH_BLACKHAT"]
            ),
            AlgorithmParameter(
                name="kernel_shape",
                param_type=ParameterType.CHOICE,
                default_value="MORPH_RECT",
                description="核形状",
                choices=["MORPH_RECT", "MORPH_ELLIPSE", "MORPH_CROSS"]
            ),
            AlgorithmParameter(
                name="kernel_size",
                param_type=ParameterType.INT,
                default_value=5,
                description="核大小",
                min_value=1,
                max_value=31
            ),
            AlgorithmParameter(
                name="iterations",
                param_type=ParameterType.INT,
                default_value=1,
                description="迭代次数",
                min_value=1,
                max_value=10
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            operation = self.get_parameter("operation")
            kernel_shape = self.get_parameter("kernel_shape")
            kernel_size = self.get_parameter("kernel_size")
            iterations = self.get_parameter("iterations")

            # 创建核
            shape = getattr(cv2, kernel_shape)
            kernel = cv2.getStructuringElement(shape, (kernel_size, kernel_size))

            # 执行形态学操作
            op = getattr(cv2, operation)
            if operation in ["MORPH_ERODE", "MORPH_DILATE"]:
                if operation == "MORPH_ERODE":
                    result_image = cv2.erode(input_image, kernel, iterations=iterations)
                else:
                    result_image = cv2.dilate(input_image, kernel, iterations=iterations)
            else:
                result_image = cv2.morphologyEx(input_image, op, kernel, iterations=iterations)

            processing_time = time.time() - start_time

            return AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time
            )

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )