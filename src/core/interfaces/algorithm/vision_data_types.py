import numpy as np
import time
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Position3D:
    """3D位置数据类"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    rz: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            'x': self.x, 'y': self.y, 'z': self.z,
            'rx': self.rx, 'ry': self.ry, 'rz': self.rz
        }

    def copy(self) -> 'Position3D':
        """创建副本"""
        return Position3D(self.x, self.y, self.z, self.rx, self.ry, self.rz)
    
    def from_dict(self, data: Dict[str, float]):
        self.x = data.get('x', 0.0)
        self.y = data.get('y', 0.0)
        self.z = data.get('z', 0.0)
        self.rx = data.get('rx', 0.0)
        self.ry = data.get('ry', 0.0)
        self.rz = data.get('rz', 0.0)
    

@dataclass
class CalibrationData:
    """标定数据类"""
    camera_matrix: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    rotation_matrix: Optional[np.ndarray] = None
    translation_vector: Optional[np.ndarray] = None
    calibration_date: Optional[str] = None
    is_valid: bool = False