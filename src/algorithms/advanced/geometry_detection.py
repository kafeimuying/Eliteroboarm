#!/usr/bin/env python3
"""
几何检测算法（圆形检测、直线检测）
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class CircleDetectionAlgorithm(AlgorithmBase):
    """圆形检测算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="circle_detection",
            display_name="圆形检测",
            description="使用霍夫圆变换检测图像中的圆形",
            category="高级算子",  # 一级目录
            secondary_category="几何检测",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["圆形检测", "霍夫变换", "几何"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="roi_region",
                param_type=ParameterType.ROI,
                default_value={"x": 0, "y": 0, "width": 0, "height": 0},
                description="感兴趣区域 (宽高为0表示全图)",
                roi_mode="manual"
            ),
            AlgorithmParameter(
                name="dp",
                param_type=ParameterType.FLOAT,
                default_value=1.0,
                description="累加器分辨率与图像分辨率的反比",
                min_value=0.1,
                max_value=3.0,
                step=0.1
            ),
            AlgorithmParameter(
                name="min_dist",
                param_type=ParameterType.INT,
                default_value=50,
                description="检测到圆心之间的最小距离",
                min_value=1,
                max_value=200
            ),
            AlgorithmParameter(
                name="param1",
                param_type=ParameterType.INT,
                default_value=100,
                description="Canny边缘检测的高阈值",
                min_value=50,
                max_value=300
            ),
            AlgorithmParameter(
                name="param2",
                param_type=ParameterType.INT,
                default_value=30,
                description="累加器阈值",
                min_value=10,
                max_value=100
            ),
            AlgorithmParameter(
                name="min_radius",
                param_type=ParameterType.INT,
                default_value=10,
                description="最小圆半径",
                min_value=1,
                max_value=500
            ),
            AlgorithmParameter(
                name="max_radius",
                param_type=ParameterType.INT,
                default_value=100,
                description="最大圆半径",
                min_value=1,
                max_value=500
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            # 获取ROI参数
            roi_region = self.get_parameter("roi_region")
            roi_x = roi_region.get("x", 0)
            roi_y = roi_region.get("y", 0)
            roi_width = roi_region.get("width", 0)
            roi_height = roi_region.get("height", 0)

            # 转换为灰度图
            if len(input_image.shape) == 3:
                gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = input_image

            # 应用ROI（如果指定了ROI）
            working_image = gray.copy()
            if roi_width > 0 and roi_height > 0:
                h, w = gray.shape
                roi_x = min(roi_x, w - 1)
                roi_y = min(roi_y, h - 1)
                roi_width = min(roi_width, w - roi_x)
                roi_height = min(roi_height, h - roi_y)

                # 创建ROI掩码
                mask = np.zeros(gray.shape, dtype=np.uint8)
                mask[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width] = 255
                working_image = cv2.bitwise_and(gray, gray, mask=mask)

            # 获取参数
            dp = self.get_parameter("dp")
            min_dist = self.get_parameter("min_dist")
            param1 = self.get_parameter("param1")
            param2 = self.get_parameter("param2")
            min_radius = self.get_parameter("min_radius")
            max_radius = self.get_parameter("max_radius")

            # 霍夫圆检测
            circles = cv2.HoughCircles(working_image, cv2.HOUGH_GRADIENT, dp, min_dist,
                                     param1=param1, param2=param2,
                                     minRadius=min_radius, maxRadius=max_radius)

            # 绘制结果
            result_image = input_image.copy()
            circle_count = 0

            # 绘制ROI区域（如果指定了ROI）
            if roi_width > 0 and roi_height > 0:
                cv2.rectangle(result_image, (roi_x, roi_y),
                             (roi_x + roi_width, roi_y + roi_height), (255, 255, 0), 2)

            if circles is not None:
                circles = np.round(circles[0, :]).astype("int")
                circle_count = len(circles)

                for (x, y, r) in circles:
                    # 调整坐标到原图坐标系（如果使用了ROI）
                    if roi_width > 0 and roi_height > 0:
                        x += roi_x
                        y += roi_y

                    # 绘制圆
                    cv2.circle(result_image, (x, y), r, (0, 255, 0), 2)
                    # 绘制圆心
                    cv2.circle(result_image, (x, y), 2, (0, 0, 255), 3)

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={"circle_count": circle_count, "circles": circles.tolist() if circles is not None else []}
            )

            result.add_intermediate_result("gray", gray)
            return result

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )


class LineDetectionAlgorithm(AlgorithmBase):
    """直线检测算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="line_detection",
            display_name="直线检测",
            description="使用霍夫直线变换检测图像中的直线",
            category="高级算子",  # 一级目录
            secondary_category="几何检测",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["直线检测", "霍夫变换", "几何"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="roi_region",
                param_type=ParameterType.ROI,
                default_value={"x": 0, "y": 0, "width": 0, "height": 0},
                description="感兴趣区域 (宽高为0表示全图)",
                roi_mode="manual"
            ),
            AlgorithmParameter(
                name="rho",
                param_type=ParameterType.FLOAT,
                default_value=1.0,
                description="距离分辨率（像素）",
                min_value=0.1,
                max_value=10.0,
                step=0.1
            ),
            AlgorithmParameter(
                name="theta",
                param_type=ParameterType.FLOAT,
                default_value=1.0,
                description="角度分辨率（度）",
                min_value=0.1,
                max_value=10.0,
                step=0.1
            ),
            AlgorithmParameter(
                name="threshold",
                param_type=ParameterType.INT,
                default_value=100,
                description="累加器阈值",
                min_value=50,
                max_value=300
            ),
            AlgorithmParameter(
                name="min_line_length",
                param_type=ParameterType.INT,
                default_value=50,
                description="最小线段长度",
                min_value=10,
                max_value=500
            ),
            AlgorithmParameter(
                name="max_line_gap",
                param_type=ParameterType.INT,
                default_value=10,
                description="最大线段间隙",
                min_value=1,
                max_value=50
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            # 获取ROI参数
            roi_region = self.get_parameter("roi_region")
            roi_x = roi_region.get("x", 0)
            roi_y = roi_region.get("y", 0)
            roi_width = roi_region.get("width", 0)
            roi_height = roi_region.get("height", 0)

            # 转换为灰度图
            if len(input_image.shape) == 3:
                gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = input_image

            # 应用ROI（如果指定了ROI）
            working_image = gray.copy()
            if roi_width > 0 and roi_height > 0:
                h, w = gray.shape
                roi_x = min(roi_x, w - 1)
                roi_y = min(roi_y, h - 1)
                roi_width = min(roi_width, w - roi_x)
                roi_height = min(roi_height, h - roi_y)

                # 创建ROI掩码
                mask = np.zeros(gray.shape, dtype=np.uint8)
                mask[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width] = 255
                working_image = cv2.bitwise_and(gray, gray, mask=mask)

            # Canny边缘检测
            edges = cv2.Canny(working_image, 50, 150)

            # 获取参数
            rho = self.get_parameter("rho")
            theta = self.get_parameter("theta") * np.pi / 180
            threshold = self.get_parameter("threshold")
            min_line_length = self.get_parameter("min_line_length")
            max_line_gap = self.get_parameter("max_line_gap")

            # 霍夫直线检测
            lines = cv2.HoughLinesP(edges, rho, theta, threshold,
                                   minLineLength=min_line_length, maxLineGap=max_line_gap)

            # 绘制结果
            result_image = input_image.copy()
            line_count = 0

            # 绘制ROI区域（如果指定了ROI）
            if roi_width > 0 and roi_height > 0:
                cv2.rectangle(result_image, (roi_x, roi_y),
                             (roi_x + roi_width, roi_y + roi_height), (255, 255, 0), 2)

            if lines is not None:
                line_count = len(lines)
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    # 调整坐标到原图坐标系（如果使用了ROI）
                    if roi_width > 0 and roi_height > 0:
                        x1 += roi_x
                        y1 += roi_y
                        x2 += roi_x
                        y2 += roi_y
                    cv2.line(result_image, (x1, y1), (x2, y2), (0, 255, 0), 2)

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={"line_count": line_count, "lines": lines.tolist() if lines is not None else []}
            )

            result.add_intermediate_result("gray", gray)
            result.add_intermediate_result("edges", edges)
            return result

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )