"""
多点位自动化视觉伺服模块
=======================================
核心思路：
  1. 示教阶段：在标准位置拍照记录AprilTag位姿 + 示教多个普通拍照点位
  2. 生产阶段：移动pack后，在标准位置重新检测AprilTag计算偏差，
     利用偏差传播算法自动更新所有普通拍照点位的位姿

数学原理：
  - 标准阶段得到 T_base_tag_std (tag 在基座系中的位姿)
  - 每个普通点 i 的位姿 T_base_flange_i 相对于 tag 的变换:
      T_tag_flange_i = T_base_tag_std_inv @ T_base_flange_i
    这个**相对关系在 pack 移动后不变**（假设 tag 和拍照目标刚性连接）。
  - 生产阶段得到新的 T_base_tag_new
  - 普通点 i 的新位姿:
      T_base_flange_i_new = T_base_tag_new @ T_tag_flange_i

这种方法的优点：
  - 每个普通点不需要再做视觉检测
  - 偏移+旋转的传播是精确的（齐次矩阵乘法）
  - 不依赖欧拉角分解（避免万向节锁问题）
"""

import json
import os
import time
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from manual_correction_tool import (
    elite_pose_to_matrix, matrix_to_elite_pose, load_json_matrix
)


# ==================== 数据结构 ====================

@dataclass
class PhotoPoint:
    """拍照点位"""
    name: str
    pose: List[float]              # [x, y, z, rx, ry, rz] mm/deg
    rel_transform: Optional[List[List[float]]] = None  # 4x4 T_tag_flange (相对标准tag的变换)
    snapshot_path: Optional[str] = None
    tag_data: Optional[Dict] = None  # 示教时的AprilTag检测数据 (tvec, rvec, id等)

@dataclass 
class ServoRecipe:
    """视觉伺服配方 — 包含标准点 + 多个拍照点"""
    id: str = ""
    name: str = ""
    created_time: float = 0.0
    description: str = ""
    
    # 标准点（偏差计算点位）
    std_robot_pose: Optional[List[float]] = None       # 标准位置机械臂位姿
    std_tag_data: Optional[Dict] = None                # 标准位置 AprilTag 检测数据
    T_base_tag_std: Optional[List[List[float]]] = None # tag 在基座系中的齐次矩阵
    
    # 普通拍照点位列表
    photo_points: List[PhotoPoint] = field(default_factory=list)
    
    # 手眼标定矩阵路径
    hand_eye_file: str = "T_eye_in_hand_chessboard.json"

    def to_dict(self) -> dict:
        """序列化为字典"""
        d = {
            'id': self.id,
            'name': self.name,
            'created_time': self.created_time,
            'description': self.description,
            'std_robot_pose': self.std_robot_pose,
            'std_tag_data': _sanitize_tag_data(self.std_tag_data),
            'T_base_tag_std': self.T_base_tag_std,
            'hand_eye_file': self.hand_eye_file,
            'photo_points': []
        }
        for pp in self.photo_points:
            d['photo_points'].append({
                'name': pp.name,
                'pose': pp.pose,
                'rel_transform': pp.rel_transform,
                'snapshot_path': pp.snapshot_path,
                'tag_data': _sanitize_tag_data(pp.tag_data),
            })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'ServoRecipe':
        """从字典反序列化"""
        recipe = cls(
            id=d.get('id', ''),
            name=d.get('name', ''),
            created_time=d.get('created_time', 0.0),
            description=d.get('description', ''),
            std_robot_pose=d.get('std_robot_pose'),
            std_tag_data=d.get('std_tag_data'),
            T_base_tag_std=d.get('T_base_tag_std'),
            hand_eye_file=d.get('hand_eye_file', 'T_eye_in_hand_chessboard.json'),
        )
        for pp_data in d.get('photo_points', []):
            recipe.photo_points.append(PhotoPoint(
                name=pp_data.get('name', ''),
                pose=pp_data.get('pose', []),
                rel_transform=pp_data.get('rel_transform'),
                snapshot_path=pp_data.get('snapshot_path'),
                tag_data=pp_data.get('tag_data'),
            ))
        return recipe


def _sanitize_tag_data(tag_data: Optional[Dict]) -> Optional[Dict]:
    """将 tag_data 中的 numpy 数组和标量转为 Python 原生类型以便 JSON 序列化"""
    if tag_data is None:
        return None
    result = {}
    for k, v in tag_data.items():
        if v is None:
            result[k] = None
        elif hasattr(v, 'tolist'):
            # numpy数组或标量 -> list或Python原生类型
            result[k] = v.tolist()
        elif isinstance(v, (np.floating, np.integer)):
            # numpy标量类型 (float32, int64等)
            result[k] = v.item()
        elif isinstance(v, dict):
            # 递归处理嵌套字典
            result[k] = _sanitize_tag_data(v)
        elif isinstance(v, (list, tuple)):
            # 处理列表/元组中的numpy类型
            result[k] = [
                x.item() if isinstance(x, (np.floating, np.integer)) else 
                (x.tolist() if hasattr(x, 'tolist') else x) 
                for x in v
            ]
        else:
            result[k] = v
    return result


# ==================== 核心算法 ====================

def compute_T_base_tag(robot_pose: List[float], tag_tvec: np.ndarray,
                       tag_rvec: np.ndarray, T_flange_cam: np.ndarray,
                       is_degree: bool = True) -> np.ndarray:
    """
    计算 AprilTag 在基座坐标系中的齐次变换矩阵
    
    链式关系: T_base_tag = T_base_flange @ T_flange_cam @ T_cam_tag
    
    Args:
        robot_pose: [x, y, z, rx, ry, rz] 机械臂当前位姿 (mm, deg)
        tag_tvec: Tag 在相机坐标系中的平移向量 (m)  
        tag_rvec: Tag 在相机坐标系中的旋转向量 (cv2 Rodrigues)
        T_flange_cam: 4x4 手眼标定矩阵 (flange → camera)
        is_degree: 机械臂角度单位是否为度
    Returns:
        T_base_tag: 4x4 齐次矩阵
    """
    import cv2
    
    T_base_flange = elite_pose_to_matrix(robot_pose, is_degree=is_degree)
    
    # 构造 T_cam_tag
    R_cam_tag, _ = cv2.Rodrigues(tag_rvec.reshape(3, 1))
    T_cam_tag = np.eye(4)
    T_cam_tag[:3, :3] = R_cam_tag
    T_cam_tag[:3, 3] = tag_tvec * 1000.0  # m → mm (与机械臂单位统一)
    
    T_base_tag = T_base_flange @ T_flange_cam @ T_cam_tag
    return T_base_tag


def compute_relative_transforms(T_base_tag_std: np.ndarray,
                                 photo_points: List[PhotoPoint]) -> List[PhotoPoint]:
    """
    计算每个普通拍照点位相对于标准 tag 的变换
    
    T_tag_flange_i = T_base_tag_std_inv @ T_base_flange_i
    
    这个相对变换在 pack 整体移动后保持不变。
    """
    T_base_tag_inv = np.linalg.inv(T_base_tag_std)
    
    for pp in photo_points:
        T_base_flange_i = elite_pose_to_matrix(pp.pose, is_degree=True)
        T_tag_flange_i = T_base_tag_inv @ T_base_flange_i
        pp.rel_transform = T_tag_flange_i.tolist()
    
    return photo_points


def propagate_deviation(T_base_tag_new: np.ndarray,
                        recipe: ServoRecipe) -> List[Tuple[str, List[float]]]:
    """
    偏差传播：根据新的 tag 位姿计算所有普通点位的新位姿
    
    T_base_flange_i_new = T_base_tag_new @ T_tag_flange_i
    
    Args:
        T_base_tag_new: 新的 tag 在基座系中的齐次矩阵
        recipe: 包含所有点位及其相对变换的配方
    Returns:
        List of (point_name, new_pose_vec)
    """
    results = []
    
    for pp in recipe.photo_points:
        if pp.rel_transform is None:
            continue
        
        T_tag_flange_i = np.array(pp.rel_transform)
        T_base_flange_new = T_base_tag_new @ T_tag_flange_i
        new_pose = matrix_to_elite_pose(T_base_flange_new, is_degree=True)
        
        results.append((pp.name, new_pose))
    
    return results


# ==================== 配方持久化 ====================

RECIPE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "workspace", "paths", "recipes")


def save_recipe(recipe: ServoRecipe, save_dir: str = None) -> str:
    """保存配方到 JSON"""
    if save_dir is None:
        save_dir = RECIPE_DIR
    os.makedirs(save_dir, exist_ok=True)
    
    if not recipe.id:
        recipe.id = f"recipe_{int(time.time())}"
    if not recipe.created_time:
        recipe.created_time = time.time()
    
    filepath = os.path.join(save_dir, f"{recipe.id}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(recipe.to_dict(), f, indent=2, ensure_ascii=False)
    
    return filepath


def load_recipe(filepath: str) -> ServoRecipe:
    """从 JSON 加载配方"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return ServoRecipe.from_dict(data)


def list_recipes(recipe_dir: str = None) -> List[str]:
    """列出所有可用配方文件"""
    if recipe_dir is None:
        recipe_dir = RECIPE_DIR
    if not os.path.exists(recipe_dir):
        return []
    return sorted([f for f in os.listdir(recipe_dir) if f.endswith('.json')])


# ==================== 便捷接口 ====================

class MultiPointServo:
    """多点位视觉伺服控制器"""
    
    def __init__(self, hand_eye_file: str = None):
        if hand_eye_file is None:
            hand_eye_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "T_eye_in_hand_chessboard.json"
            )
        self.T_flange_cam = load_json_matrix(hand_eye_file, "T")
        self.current_recipe: Optional[ServoRecipe] = None
    
    def start_teaching(self, name: str = "") -> ServoRecipe:
        """开始新的示教流程，创建空配方"""
        recipe = ServoRecipe(
            id=f"recipe_{int(time.time())}",
            name=name or f"配方_{time.strftime('%Y%m%d_%H%M%S')}",
            created_time=time.time(),
        )
        self.current_recipe = recipe
        return recipe
    
    def record_standard_point(self, robot_pose: List[float], 
                               tag_result: Dict) -> bool:
        """
        记录标准点（偏差计算点位）
        
        Args:
            robot_pose: 当前机械臂位姿 [x,y,z,rx,ry,rz] (mm, deg)
            tag_result: AprilTag 检测结果 dict，含 'tvec', 'rvec', 'id', 'euler' 等
        Returns:
            True if success
        """
        if self.current_recipe is None:
            return False
        
        self.current_recipe.std_robot_pose = list(robot_pose)
        self.current_recipe.std_tag_data = _sanitize_tag_data(tag_result)
        
        # 计算 T_base_tag_std
        T_base_tag = compute_T_base_tag(
            robot_pose, 
            np.array(tag_result['tvec']),
            np.array(tag_result['rvec']),
            self.T_flange_cam,
            is_degree=True
        )
        self.current_recipe.T_base_tag_std = T_base_tag.tolist()
        
        return True
    
    def add_photo_point(self, name: str, robot_pose: List[float],
                        snapshot_path: str = None, tag_data: Dict = None) -> int:
        """
        添加普通拍照点位
        
        Args:
            name: 点位名称
            robot_pose: 机械臂位姿 [x,y,z,rx,ry,rz]
            snapshot_path: 快照路径 (可选)
            tag_data: AprilTag检测数据 (可选，用于纠偏后误差计算)
        Returns:
            当前点位总数
        """
        if self.current_recipe is None:
            return 0
        
        pp = PhotoPoint(
            name=name,
            pose=list(robot_pose),
            snapshot_path=snapshot_path,
            tag_data=tag_data,
        )
        self.current_recipe.photo_points.append(pp)
        return len(self.current_recipe.photo_points)
    
    def finish_teaching(self) -> ServoRecipe:
        """
        完成示教，计算所有点位的相对变换并持久化
        """
        recipe = self.current_recipe
        if recipe is None or recipe.T_base_tag_std is None:
            raise ValueError("标准点未记录，请先调用 record_standard_point")
        
        T_base_tag_std = np.array(recipe.T_base_tag_std)
        
        # 计算每个拍照点位相对于 tag 的变换
        compute_relative_transforms(T_base_tag_std, recipe.photo_points)
        
        # 持久化
        filepath = save_recipe(recipe)
        
        return recipe
    
    def compute_new_poses(self, robot_pose: List[float],
                          tag_result: Dict) -> List[Tuple[str, List[float]]]:
        """
        生产阶段：根据新检测到的 tag 位姿计算所有点位的新位姿
        
        Args:
            robot_pose: 标准位置当前机械臂位姿
            tag_result: 当前 AprilTag 检测结果
        Returns:
            List of (point_name, new_pose)
        """
        recipe = self.current_recipe
        if recipe is None:
            raise ValueError("没有加载配方")
        
        # 计算新的 T_base_tag
        T_base_tag_new = compute_T_base_tag(
            robot_pose,
            np.array(tag_result['tvec']),
            np.array(tag_result['rvec']),
            self.T_flange_cam,
            is_degree=True
        )
        
        return propagate_deviation(T_base_tag_new, recipe)
    
    def load(self, filepath: str):
        """加载已有配方"""
        self.current_recipe = load_recipe(filepath)
