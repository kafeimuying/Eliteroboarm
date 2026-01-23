#!/usr/bin/env python3
"""
Base definitions for vision algorithms
视觉算法基础定义
"""

from .algorithm_base import (
    AlgorithmBase,
    AlgorithmInfo,
    AlgorithmParameter,
    AlgorithmResult,
    ParameterType,
    CompositeAlgorithm
)

__all__ = [
    'AlgorithmBase',
    'AlgorithmInfo',
    'AlgorithmParameter',
    'AlgorithmResult',
    'ParameterType',
    'CompositeAlgorithm'
]