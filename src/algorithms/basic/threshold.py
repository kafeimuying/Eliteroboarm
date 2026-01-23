#!/usr/bin/env python3
"""
阈值分割算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class ThresholdAlgorithm(AlgorithmBase):
    """阈值分割算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="threshold",
            display_name="阈值分割",
            description="对图像进行阈值分割处理",
            category="基础算子",  # 一级目录
            secondary_category="分割",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["阈值", "分割", "二值化"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="threshold_value",
                param_type=ParameterType.INT,
                default_value=127,
                description="阈值",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="max_value",
                param_type=ParameterType.INT,
                default_value=255,
                description="最大值",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="threshold_type",
                param_type=ParameterType.CHOICE,
                default_value="THRESH_BINARY",
                description="阈值类型",
                choices=["THRESH_BINARY", "THRESH_BINARY_INV", "THRESH_TRUNC",
                        "THRESH_TOZERO", "THRESH_TOZERO_INV"]
            ),
            AlgorithmParameter(
                name="adaptive",
                param_type=ParameterType.BOOL,
                default_value=False,
                description="是否使用自适应阈值"
            ),
            AlgorithmParameter(
                name="adaptive_method",
                param_type=ParameterType.CHOICE,
                default_value="ADAPTIVE_THRESH_MEAN_C",
                description="自适应方法",
                choices=["ADAPTIVE_THRESH_MEAN_C", "ADAPTIVE_THRESH_GAUSSIAN_C"]
            ),
            AlgorithmParameter(
                name="block_size",
                param_type=ParameterType.INT,
                default_value=11,
                description="自适应阈值块大小",
                min_value=3,
                max_value=99,
                step=2
            ),
            AlgorithmParameter(
                name="c_constant",
                param_type=ParameterType.FLOAT,
                default_value=2.0,
                description="自适应阈值常数",
                min_value=-10.0,
                max_value=10.0,
                step=0.1
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            threshold_value = self.get_parameter("threshold_value")
            max_value = self.get_parameter("max_value")
            threshold_type = self.get_parameter("threshold_type")
            adaptive = self.get_parameter("adaptive")

            # 转换为灰度图
            if len(input_image.shape) == 3:
                gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = input_image

            if adaptive:
                # 自适应阈值
                adaptive_method = self.get_parameter("adaptive_method")
                block_size = self.get_parameter("block_size")
                c_constant = self.get_parameter("c_constant")

                # 确保块大小为奇数
                if block_size % 2 == 0:
                    block_size += 1

                method = getattr(cv2, adaptive_method)
                thresh_type = getattr(cv2, threshold_type.split('_', 1)[1])  # 移除THRESH_前缀

                result_image = cv2.adaptiveThreshold(gray, max_value, method,
                                                   thresh_type, block_size, c_constant)
            else:
                # 普通阈值
                thresh_type = getattr(cv2, threshold_type)
                _, result_image = cv2.threshold(gray, threshold_value, max_value, thresh_type)

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
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