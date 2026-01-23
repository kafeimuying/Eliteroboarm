#!/usr/bin/env python3
"""
颜色检测算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class ColorDetectionAlgorithm(AlgorithmBase):
    """颜色检测算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="color_detection",
            display_name="颜色检测",
            description="检测图像中指定颜色范围的区域",
            category="高级算子",  # 一级目录
            secondary_category="颜色分析",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["颜色检测", "HSV", "色彩分析"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="color_space",
                param_type=ParameterType.CHOICE,
                default_value="HSV",
                description="颜色空间",
                choices=["HSV", "RGB", "LAB"]
            ),
            AlgorithmParameter(
                name="lower_h",
                param_type=ParameterType.INT,
                default_value=0,
                description="色调下限",
                min_value=0,
                max_value=179
            ),
            AlgorithmParameter(
                name="upper_h",
                param_type=ParameterType.INT,
                default_value=10,
                description="色调上限",
                min_value=0,
                max_value=179
            ),
            AlgorithmParameter(
                name="lower_s",
                param_type=ParameterType.INT,
                default_value=50,
                description="饱和度下限",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="upper_s",
                param_type=ParameterType.INT,
                default_value=255,
                description="饱和度上限",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="lower_v",
                param_type=ParameterType.INT,
                default_value=50,
                description="明度下限",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="upper_v",
                param_type=ParameterType.INT,
                default_value=255,
                description="明度上限",
                min_value=0,
                max_value=255
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            color_space = self.get_parameter("color_space")
            lower_h = self.get_parameter("lower_h")
            upper_h = self.get_parameter("upper_h")
            lower_s = self.get_parameter("lower_s")
            upper_s = self.get_parameter("upper_s")
            lower_v = self.get_parameter("lower_v")
            upper_v = self.get_parameter("upper_v")

            # 颜色空间转换
            if color_space == "HSV":
                converted = cv2.cvtColor(input_image, cv2.COLOR_BGR2HSV)
            elif color_space == "LAB":
                converted = cv2.cvtColor(input_image, cv2.COLOR_BGR2LAB)
            else:  # RGB
                converted = input_image

            # 定义颜色范围
            lower = np.array([lower_h, lower_s, lower_v])
            upper = np.array([upper_h, upper_s, upper_v])

            # 创建掩码
            mask = cv2.inRange(converted, lower, upper)

            # 应用掩码
            result_image = cv2.bitwise_and(input_image, input_image, mask=mask)

            # 计算检测区域面积
            detection_area = cv2.countNonZero(mask)
            total_area = mask.shape[0] * mask.shape[1]
            coverage_percentage = (detection_area / total_area) * 100

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={
                    "detection_area": detection_area,
                    "total_area": total_area,
                    "coverage_percentage": coverage_percentage
                }
            )

            result.add_intermediate_result("converted", converted)
            result.add_intermediate_result("mask", mask)
            return result

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )