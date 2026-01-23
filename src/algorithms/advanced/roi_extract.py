#!/usr/bin/env python3
"""
ROI区域提取算法
"""

import cv2
import numpy as np
import time
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class ROIExtractAlgorithm(AlgorithmBase):
    """ROI区域提取算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="roi_extract",
            display_name="ROI区域提取",
            description="从图像中提取指定的感兴趣区域",
            category="高级算子",  # 一级目录
            secondary_category="预处理",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["ROI", "区域提取", "预处理"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="roi_region",
                param_type=ParameterType.ROI,
                default_value={"x": 0, "y": 0, "width": 200, "height": 200},
                description="感兴趣区域",
                roi_mode="manual"
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            roi_region = self.get_parameter("roi_region")
            roi_x = roi_region.get("x", 0)
            roi_y = roi_region.get("y", 0)
            roi_width = roi_region.get("width", 200)
            roi_height = roi_region.get("height", 200)

            # 确保ROI不超出图像边界
            h, w = input_image.shape[:2]
            roi_x = min(roi_x, w - 1)
            roi_y = min(roi_y, h - 1)
            roi_width = min(roi_width, w - roi_x)
            roi_height = min(roi_height, h - roi_y)

            # 提取ROI
            roi_image = input_image[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width]

            # 创建标记了ROI的原图
            marked_image = input_image.copy()
            cv2.rectangle(marked_image, (roi_x, roi_y),
                         (roi_x + roi_width, roi_y + roi_height), (0, 255, 0), 2)

            processing_time = time.time() - start_time

            result = AlgorithmResult(
                success=True,
                output_image=roi_image,
                processing_time=processing_time
            )

            result.add_intermediate_result("marked_image", marked_image)
            return result

        except Exception as e:
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )