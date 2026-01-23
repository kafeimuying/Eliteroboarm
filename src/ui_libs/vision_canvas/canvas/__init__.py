"""
Canvas UI Components Module

This module contains all canvas-related UI components for the algorithm chain interface,
including nodes, connections, canvas view, and supporting dialogs.

Components:
- AlgorithmCanvas: Main canvas view for algorithm chain editing
- AlgorithmNode: Visual representation of algorithms on the canvas
- ImageNode: Visual representation of input/output image nodes
- ConnectionLine: Visual connections between nodes
- ImageDisplayDialog: Enhanced image viewing dialog with zoom capabilities
"""

from .canvas import AlgorithmCanvas
from .nodes import AlgorithmNode, ImageNode
from .connections import ConnectionLine
from .image_dialog import ImageDisplayDialog
from .canvas_dialog import LarminarVisionAlgorithmChainDialog

__all__ = [
    'AlgorithmCanvas',
    'AlgorithmNode', 
    'ImageNode',
    'ConnectionLine',
    'ImageDisplayDialog',
    'LarminarVisionAlgorithmChainDialog'
]