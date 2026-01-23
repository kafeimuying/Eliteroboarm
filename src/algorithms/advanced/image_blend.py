#!/usr/bin/env python3
"""
图像加权平均算法
基于多张图片输入进行加权平均融合，通过索引选择输入图像
"""

import cv2
import numpy as np
import time
from typing import List, Union

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)
from core.managers.log_manager import info, debug, error, LogCategory


class ImageBlendAlgorithm(AlgorithmBase):
    """图像加权平均算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="image_blend",
            display_name="图像加权平均",
            description="基于多张图片输入进行加权平均融合，支持索引选择和权重设置",
            category="高级算子",
            secondary_category="图像融合",
            version="2.0.0",
            author="System",
            tags=["图像融合", "加权平均", "多图片输入", "索引", "测试"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="image1_index",
                param_type=ParameterType.INT,
                default_value=0,
                description="第一张图片的索引 (从0开始)",
                min_value=0,
                max_value=100,
                required=True
            ),
            AlgorithmParameter(
                name="image2_index",
                param_type=ParameterType.INT,
                default_value=1,
                description="第二张图片的索引",
                min_value=0,
                max_value=100,
                required=True
            ),
            AlgorithmParameter(
                name="weight1",
                param_type=ParameterType.FLOAT,
                default_value=0.5,
                description="第一张图片的权重 (0.0-1.0)，第二张图片权重为 (1-weight1)",
                min_value=0.0,
                max_value=1.0,
                step=0.01
            )
        ]

    def process(self, input_image: Union[np.ndarray, List[np.ndarray]], **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:

            image1_index = self.get_parameter("image1_index")
            image2_index = self.get_parameter("image2_index")
            weight1 = self.get_parameter("weight1")

            debug(f"图像加权平均开始 - 索引: {image1_index}, {image2_index}, 权重: {weight1}", "IMAGE_BLEND", LogCategory.ALGO)
            debug(f"主输入图像类型: {type(input_image)}", "IMAGE_BLEND", LogCategory.ALGO)

            # 获取图片列表
            if isinstance(input_image, list):
                image_list = input_image
                debug(f"接收到图片列表，包含 {len(image_list)} 张图片", "IMAGE_BLEND", LogCategory.ALGO)
            elif isinstance(input_image, np.ndarray):
                image_list = [input_image]
                debug(f"接收到单张图片，转换为列表", "IMAGE_BLEND", LogCategory.ALGO)
            else:
                return AlgorithmResult(
                    success=False,
                    error_message=f"输入图像类型不支持: {type(input_image)}"
                )

            # 检查索引有效性
            if image1_index >= len(image_list):
                return AlgorithmResult(
                    success=False,
                    error_message=f"索引 {image1_index} 超出图片列表范围 (0-{len(image_list)-1})"
                )

            if image2_index >= len(image_list):
                return AlgorithmResult(
                    success=False,
                    error_message=f"索引 {image2_index} 超出图片列表范围 (0-{len(image_list)-1})"
                )

            # 获取两张图片
            img1 = image_list[image1_index].copy()
            img2 = image_list[image2_index].copy()

            debug(f"图片1 (索引{image1_index}) 尺寸: {img1.shape}", "IMAGE_BLEND", LogCategory.ALGO)
            debug(f"图片2 (索引{image2_index}) 尺寸: {img2.shape}", "IMAGE_BLEND", LogCategory.ALGO)

            # 调整图片尺寸一致
            target_height = min(img1.shape[0], img2.shape[0])
            target_width = min(img1.shape[1], img2.shape[1])

            if img1.shape[:2] != (target_height, target_width):
                img1 = cv2.resize(img1, (target_width, target_height))
                debug(f"调整图片1尺寸为: {img1.shape}", "IMAGE_BLEND", LogCategory.ALGO)

            if img2.shape[:2] != (target_height, target_width):
                img2 = cv2.resize(img2, (target_width, target_height))
                debug(f"调整图片2尺寸为: {img2.shape}", "IMAGE_BLEND", LogCategory.ALGO)

            # 确保颜色通道数一致
            if len(img1.shape) == 3 and len(img2.shape) == 2:
                img2 = cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)
                debug(f"将图片2转换为BGR格式", "IMAGE_BLEND", LogCategory.ALGO)
            elif len(img1.shape) == 2 and len(img2.shape) == 3:
                img1 = cv2.cvtColor(img1, cv2.COLOR_GRAY2BGR)
                debug(f"将图片1转换为BGR格式", "IMAGE_BLEND", LogCategory.ALGO)
            elif len(img1.shape) == 2 and len(img2.shape) == 2:
                img1 = cv2.cvtColor(img1, cv2.COLOR_GRAY2BGR)
                img2 = cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)
                debug(f"将两张图片都转换为BGR格式", "IMAGE_BLEND", LogCategory.ALGO)

            # 计算权重
            weight1 = float(weight1)
            weight2 = 1.0 - weight1

            debug(f"权重设置 - 图片1: {weight1:.3f}, 图片2: {weight2:.3f}", "IMAGE_BLEND", LogCategory.ALGO)

            # 执行加权平均
            result_image = cv2.addWeighted(img1, weight1, img2, weight2, 0)

            # 在结果图像上添加信息文本
            text1 = f"Blend: [{image1_index}]x{weight1:.2f} + [{image2_index}]x{weight2:.2f}"
            text2 = f"Total images: {len(image_list)}"

            # 添加黑色背景的文本框
            cv2.rectangle(result_image, (5, 5), (400, 65), (0, 0, 0), -1)
            cv2.putText(result_image, text1, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(result_image, text2, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            processing_time = time.time() - start_time
            info(f"图像加权平均完成 - 索引[{image1_index},{image2_index}], 输出尺寸: {result_image.shape}, 耗时: {processing_time:.3f}s", "IMAGE_BLEND", LogCategory.ALGO)

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={
                    "total_images": len(image_list),
                    "image1_index": image1_index,
                    "image2_index": image2_index,
                    "weight1": weight1,
                    "weight2": weight2,
                    "image1_shape": img1.shape,
                    "image2_shape": img2.shape,
                    "output_shape": result_image.shape
                }
            )

            # 保存中间结果用于调试
            result.add_intermediate_result("image1", img1)
            result.add_intermediate_result("image2", img2)
            result.add_intermediate_result("image_list_info", f"Total: {len(image_list)} images")

            return result

        except Exception as e:
            error(f"图像加权平均执行异常: {str(e)}", "IMAGE_BLEND", LogCategory.ALGO)
            import traceback
            error(f"异常详情: {traceback.format_exc()}", "IMAGE_BLEND", LogCategory.ALGO)
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )