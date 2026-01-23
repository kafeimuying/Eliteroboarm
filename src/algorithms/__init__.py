#!/usr/bin/env python3
"""
Vision algorithms implementation
视觉算法实现
"""

from . import basic
from . import advanced
from . import performance
from . import composite

# 导入基础算法
from .basic import (
    GaussianBlurAlgorithm,
    CannyEdgeDetectionAlgorithm,
    ThresholdAlgorithm,
    MorphologyAlgorithm
)

# 导入高级视觉算法
from .advanced import (
    ROIExtractAlgorithm,
    CircleDetectionAlgorithm,
    LineDetectionAlgorithm,
    ContourDetectionAlgorithm,
    TemplateMatchingAlgorithm,
    ColorDetectionAlgorithm
)

# 导入高性能视觉算法
from .performance import (
    HighPerformanceROIEdgeDetectionAlgorithm,
    HighPerformanceTemplateMatchingAlgorithm
)

__all__ = [
    'basic',
    'advanced',
    'performance',
    'composite',
    # 基础算法
    'GaussianBlurAlgorithm',
    'CannyEdgeDetectionAlgorithm',
    'ThresholdAlgorithm',
    'MorphologyAlgorithm',
    # 高级算法
    'ROIExtractAlgorithm',
    'CircleDetectionAlgorithm',
    'LineDetectionAlgorithm',
    'ContourDetectionAlgorithm',
    'TemplateMatchingAlgorithm',
    'ColorDetectionAlgorithm',
    # 高性能算法
    'HighPerformanceROIEdgeDetectionAlgorithm',
    'HighPerformanceTemplateMatchingAlgorithm'
]