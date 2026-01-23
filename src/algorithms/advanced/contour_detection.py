#!/usr/bin/env python3
"""
轮廓检测算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class ContourDetectionAlgorithm(AlgorithmBase):
    """轮廓检测算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="contour_detection",
            display_name="轮廓检测",
            description="检测并分析图像中的轮廓",
            category="高级算子",  # 一级目录
            secondary_category="形状检测",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["轮廓检测", "形状分析", "几何"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="threshold_value",
                param_type=ParameterType.INT,
                default_value=127,
                description="二值化阈值",
                min_value=0,
                max_value=255
            ),
            AlgorithmParameter(
                name="min_area",
                param_type=ParameterType.INT,
                default_value=100,
                description="最小轮廓面积",
                min_value=1,
                max_value=10000
            ),
            AlgorithmParameter(
                name="max_area",
                param_type=ParameterType.INT,
                default_value=10000,
                description="最大轮廓面积",
                min_value=1,
                max_value=100000
            ),
            AlgorithmParameter(
                name="approximation",
                param_type=ParameterType.CHOICE,
                default_value="CHAIN_APPROX_SIMPLE",
                description="轮廓近似方法",
                choices=["CHAIN_APPROX_NONE", "CHAIN_APPROX_SIMPLE"]
            ),
            AlgorithmParameter(
                name="show_bounding_rect",
                param_type=ParameterType.BOOL,
                default_value=True,
                description="显示边界矩形"
            ),
            AlgorithmParameter(
                name="show_centroid",
                param_type=ParameterType.BOOL,
                default_value=True,
                description="显示质心"
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            # 转换为灰度图
            if len(input_image.shape) == 3:
                gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = input_image

            # 获取参数
            threshold_value = self.get_parameter("threshold_value")
            min_area = self.get_parameter("min_area")
            max_area = self.get_parameter("max_area")
            approximation = self.get_parameter("approximation")
            show_bounding_rect = self.get_parameter("show_bounding_rect")
            show_centroid = self.get_parameter("show_centroid")

            # 二值化
            _, binary = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY)

            # 查找轮廓
            approx_method = getattr(cv2, approximation)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, approx_method)

            # 过滤轮廓
            filtered_contours = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if min_area <= area <= max_area:
                    filtered_contours.append(contour)

            # 绘制结果
            result_image = input_image.copy()
            contour_data = []

            for i, contour in enumerate(filtered_contours):
                # 绘制轮廓
                cv2.drawContours(result_image, [contour], -1, (0, 255, 0), 2)

                # 计算面积和周长
                area = cv2.contourArea(contour)
                perimeter = cv2.arcLength(contour, True)

                # 边界矩形
                if show_bounding_rect:
                    x, y, w, h = cv2.boundingRect(contour)
                    cv2.rectangle(result_image, (x, y), (x + w, y + h), (255, 0, 0), 2)

                # 质心
                if show_centroid:
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        cv2.circle(result_image, (cx, cy), 5, (0, 0, 255), -1)

                contour_data.append({
                    "id": i,
                    "area": area,
                    "perimeter": perimeter,
                    "centroid": (cx, cy) if show_centroid and M["m00"] != 0 else None
                })

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={"contour_count": len(filtered_contours), "contours": contour_data}
            )

            result.add_intermediate_result("gray", gray)
            result.add_intermediate_result("binary", binary)
            return result

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )