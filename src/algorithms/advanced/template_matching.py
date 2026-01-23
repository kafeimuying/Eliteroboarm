#!/usr/bin/env python3
"""
模板匹配算法
"""

import cv2
import numpy as np
import time
import os
from typing import List

from core.interfaces.algorithm.base import (
    AlgorithmBase, AlgorithmInfo, AlgorithmParameter,
    AlgorithmResult, ParameterType
)


class TemplateMatchingAlgorithm(AlgorithmBase):
    """模板匹配算法"""

    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="template_matching",
            display_name="模板匹配",
            description="在图像中搜索指定模板的位置",
            category="高级算子",  # 一级目录
            secondary_category="模式匹配",  # 二级目录
            version="1.0.0",
            author="System",
            tags=["模板匹配", "模式识别", "定位"]
        )

    def get_parameters(self) -> List[AlgorithmParameter]:
        return [
            AlgorithmParameter(
                name="template_image",
                param_type=ParameterType.IMAGE,
                default_value=None,
                description="模板图像",
                required=True,
                image_format="GRAY"  # 建议使用灰度图像
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
            )
        ]

    def process(self, input_image: np.ndarray, **kwargs) -> AlgorithmResult:
        start_time = time.time()

        try:
            from core.managers.log_manager import info, debug, warning, LogCategory

            template_image = self.get_parameter("template_image")
            method_name = self.get_parameter("method")
            threshold = self.get_parameter("threshold")
            multiple_matches = self.get_parameter("multiple_matches")

            debug(f"模板匹配开始 - 方法: {method_name}, 阈值: {threshold}, 多匹配: {multiple_matches}", "TEMPLATE_MATCHING", LogCategory.ALGO)
            debug(f"模板图像参数类型: {type(template_image)}, 值: {template_image}", "TEMPLATE_MATCHING", LogCategory.ALGO)

            if template_image is None:
                return AlgorithmResult(
                    success=False,
                    error_message="模板图像未提供"
                )

            # 处理模板图像 - 支持字符串路径或numpy数组
            if isinstance(template_image, str):
                # 如果是字符串路径，加载图像
                debug(f"从路径加载模板图像: {template_image}", "TEMPLATE_MATCHING", LogCategory.ALGO)
                if not os.path.exists(template_image):
                    return AlgorithmResult(
                        success=False,
                        error_message=f"模板图像文件不存在: {template_image}"
                    )
                template = cv2.imread(template_image, cv2.IMREAD_GRAYSCALE)
                if template is None:
                    return AlgorithmResult(
                        success=False,
                        error_message=f"无法加载模板图像: {template_image}"
                    )
            else:
                # 如果是numpy数组，直接使用
                if len(template_image.shape) == 3:
                    template = cv2.cvtColor(template_image, cv2.COLOR_BGR2GRAY)
                else:
                    template = template_image

            if template is None:
                return AlgorithmResult(
                    success=False,
                    error_message="无法处理模板图像"
                )

            debug(f"输入图像尺寸: {input_image.shape}, 模板图像尺寸: {template.shape}", "TEMPLATE_MATCHING", LogCategory.ALGO)

            # 转换输入图像为灰度
            if len(input_image.shape) == 3:
                gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
            else:
                gray = input_image

            # 模板匹配
            method = getattr(cv2, method_name)
            result_matrix = cv2.matchTemplate(gray, template, method)

            # 绘制结果
            result_image = input_image.copy()
            h, w = template.shape
            matches = []

            if multiple_matches:
                # 改进的多匹配检测 - 使用非极大值抑制避免重叠框
                # 首先找到所有满足阈值的候选位置
                locations = np.where(result_matrix >= threshold)
                candidate_points = list(zip(*locations[::-1]))
                candidate_confidences = [result_matrix[pt[1], pt[0]] for pt in candidate_points]

                debug(f"找到 {len(candidate_points)} 个候选匹配点", "TEMPLATE_MATCHING", LogCategory.ALGO)

                if candidate_points:
                    # 按置信度排序
                    sorted_indices = np.argsort(candidate_confidences)[::-1]

                    # 非极大值抑制
                    selected_matches = []
                    for idx in sorted_indices:
                        pt = candidate_points[idx]
                        conf = candidate_confidences[idx]

                        # 检查是否与已选的匹配重叠
                        overlap = False
                        for selected_match in selected_matches:
                            selected_pt = selected_match["position"]
                            # 计算中心点距离
                            center_dist = np.sqrt((pt[0] - selected_pt[0])**2 + (pt[1] - selected_pt[1])**2)
                            if center_dist < min(w, h) * 0.5:  # 如果距离小于模板尺寸的一半，认为重叠
                                overlap = True
                                break

                        if not overlap:
                            selected_matches.append({"position": pt, "confidence": conf})
                            # 绘制更明显的矩形框
                            cv2.rectangle(result_image, pt, (pt[0] + w, pt[1] + h), (0, 255, 0), 3)
                            # 添加十字标记中心
                            center = (pt[0] + w//2, pt[1] + h//2)
                            cv2.drawMarker(result_image, center, (0, 0, 255), cv2.MARKER_CROSS, 15, 3)
                            # 添加置信度文本
                            cv2.putText(result_image, f"{conf:.3f}", (pt[0], pt[1]-5),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                    matches = selected_matches

            else:
                # 单一最佳匹配
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result_matrix)

                if method_name in ['TM_SQDIFF', 'TM_SQDIFF_NORMED']:
                    match_loc = min_loc
                    confidence = 1 - min_val
                else:
                    match_loc = max_loc
                    confidence = max_val

                debug(f"最佳匹配 - 位置: {match_loc}, 置信度: {confidence:.4f}, 阈值: {threshold}", "TEMPLATE_MATCHING", LogCategory.ALGO)

                if confidence >= threshold:
                    # 绘制更明显的矩形框
                    cv2.rectangle(result_image, match_loc,
                                (match_loc[0] + w, match_loc[1] + h), (0, 255, 0), 3)
                    # 添加十字标记中心
                    center = (match_loc[0] + w//2, match_loc[1] + h//2)
                    cv2.drawMarker(result_image, center, (0, 0, 255), cv2.MARKER_CROSS, 20, 3)
                    # 添加置信度文本
                    cv2.putText(result_image, f"{confidence:.3f}", (match_loc[0], match_loc[1]-10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    matches.append({"position": match_loc, "confidence": confidence})
                else:
                    debug(f"匹配置信度 {confidence:.4f} 低于阈值 {threshold}", "TEMPLATE_MATCHING", LogCategory.ALGO)

            processing_time = time.time() - start_time
            info(f"模板匹配完成 - 找到 {len(matches)} 个匹配，耗时 {processing_time:.3f}s", "TEMPLATE_MATCHING", LogCategory.ALGO)

            result = AlgorithmResult(
                success=True,
                output_image=result_image,
                processing_time=processing_time,
                data={
                    "match_count": len(matches),
                    "matches": matches,
                    "method": method_name,
                    "threshold": threshold
                }
            )

            result.add_intermediate_result("gray", gray)
            result.add_intermediate_result("template", template)
            result.add_intermediate_result("match_result", result_matrix)
            return result

        except Exception as e:
            from core.managers.log_manager import error, LogCategory
            error(f"模板匹配执行异常: {str(e)}", "TEMPLATE_MATCHING", LogCategory.ALGO)
            import traceback
            error(f"异常详情: {traceback.format_exc()}", "TEMPLATE_MATCHING", LogCategory.ALGO)
            return AlgorithmResult(
                success=False,
                error_message=str(e),
                processing_time=time.time() - start_time
            )