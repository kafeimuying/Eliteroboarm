#!/usr/bin/env python3
"""
AprilTag 检测器
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple

# 自动选择后端
try:
    from pupil_apriltags import Detector
    BACKEND = "pupil"
except ImportError:
    try:
        from apriltag import Detector
        BACKEND = "apriltag"
    except ImportError:
        raise ImportError("未找到可用的AprilTag库")

print(f"使用后端: {BACKEND}")


class AprilTagDetector:
    def __init__(
        self,
        tag_size_m: float,
        camera_matrix: np.ndarray,
        dist_coeffs: Optional[np.ndarray] = None,
        tag_family: str = "tag36h11"
    ):
        self.tag_size = tag_size_m
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs if dist_coeffs is not None else np.zeros(4)
        
        # 初始化检测器
        if BACKEND == "pupil":
            self.detector = Detector(
                families=tag_family,
                nthreads=4,
                quad_decimate=1.0,
                quad_sigma=0.0,
                refine_edges=1,
                decode_sharpening=0.25,
                debug=0
            )
        else:
            self.detector = Detector(families=tag_family)

        # Tag角点3D坐标
        s = tag_size_m / 2.0
        self.object_points = np.array([
            [-s, -s, 0], [s, -s, 0], [s, s, 0], [-s, s, 0]
        ], dtype=np.float32)

    def detect(self, image: np.ndarray) -> List[Dict]:
        """检测图像中的AprilTag"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        detections = self.detector.detect(gray)
        results = []

        for det in detections:
            # 提取角点（兼容两种后端）
            if BACKEND == "pupil":
                corners = np.array(det.corners, dtype=np.float32)
                tag_id = det.tag_id
                center = det.center
            else:
                corners = np.array(det.corners, dtype=np.float32).reshape(-1, 2)
                tag_id = det.tag_id
                center = det.center

            # PnP位姿估计
            success, rvec, tvec = cv2.solvePnP(
                self.object_points,
                corners,
                self.camera_matrix,
                self.dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE
            )

            if success:
                R, _ = cv2.Rodrigues(rvec)
                results.append({
                    'id': int(tag_id),
                    'center': center,
                    'corners': corners,
                    'tvec': tvec.flatten(),
                    'rvec': rvec.flatten(),
                    'R': R,
                    'distance': float(np.linalg.norm(tvec)),
                    'euler': self._rotation_to_euler(R)
                })

        return results

    def _rotation_to_euler(self, R: np.ndarray) -> Tuple[float, float, float]:
        """旋转矩阵转欧拉角（ZYX顺序）"""
        import math
        sy = math.sqrt(R[0,0]**2 + R[1,0]**2)
        if sy < 1e-6:
            x = math.atan2(-R[1,2], R[1,1])
            y = math.atan2(-R[2,0], sy)
            z = 0
        else:
            x = math.atan2(R[2,1], R[2,2])
            y = math.atan2(-R[2,0], sy)
            z = math.atan2(R[1,0], R[0,0])
        return tuple(np.degrees([x, y, z]))

    def draw_detections(self, image: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """可视化检测结果"""
        img = image.copy()
        
        for det in detections:
            corners = det['corners'].astype(int)
            center = tuple(map(int, det['center']))
            
            # 绘制边框
            cv2.polylines(img, [corners.reshape(-1,1,2)], True, (0,255,0), 2)
            
            # 绘制ID和距离
            text = f"ID:{det['id']} {det['distance']:.2f}m"
            cv2.putText(img, text, (center[0]-40, center[1]-20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
            
            # 绘制坐标轴
            self._draw_axis(img, det)

        return img

    def _draw_axis(self, image: np.ndarray, det: Dict):
        """绘制3D坐标轴"""
        axis_len = self.tag_size * 0.5
        axis_points = np.float32([
            [0,0,0], [axis_len,0,0], [0,axis_len,0], [0,0,-axis_len]
        ])

        imgpts, _ = cv2.projectPoints(
            axis_points,
            det['rvec'],
            det['tvec'],
            self.camera_matrix,
            self.dist_coeffs
        )

        imgpts = imgpts.astype(int)
        corner = tuple(imgpts[0].ravel())

        cv2.line(image, corner, tuple(imgpts[1].ravel()), (0,0,255), 3)  # X-红
        cv2.line(image, corner, tuple(imgpts[2].ravel()), (0,255,0), 3)  # Y-绿
        cv2.line(image, corner, tuple(imgpts[3].ravel()), (255,0,0), 3)  # Z-蓝


# 预设相机内参（备用）
CAMERA_PRESETS = {
    '640x480': np.array([[600, 0, 320], [0, 600, 240], [0, 0, 1]], dtype=np.float32),
    '1280x720': np.array([[800, 0, 640], [0, 800, 360], [0, 0, 1]], dtype=np.float32),
}