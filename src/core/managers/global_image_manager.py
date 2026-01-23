"""
全局图像管理器
维护一个全局的图像字典，支持多相机和手动导入的图像
"""

import numpy as np
from typing import Dict, List, Optional, Any
from ..managers.log_manager import info, debug, warning, error


class GlobalImageManager:
    """全局图像管理器 - 单例模式"""
    
    _instance: Optional['GlobalImageManager'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'GlobalImageManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.global_image_dict: Dict[str, List[np.ndarray]] = {}
            self._initialized = True
            info("GlobalImageManager initialized", "IMAGE_MANAGER")
    
    def add_camera_images(self, camera_id: str, images: List[np.ndarray]) -> None:
        """
        添加相机图像到全局字典
        
        Args:
            camera_id: 相机ID，作为字典的key
            images: 图像列表
        """
        if not isinstance(images, list):
            images = [images]
        
        self.global_image_dict[camera_id] = images
        debug(f"Added {len(images)} images to global dict for camera: {camera_id}", "IMAGE_MANAGER")
        
        # 如果这是新相机，记录事件
        if camera_id not in self.global_image_dict or len(self.global_image_dict[camera_id]) != len(images):
            info(f"Camera '{camera_id}' updated with {len(images)} images", "IMAGE_MANAGER")
    
    def add_manual_image(self, image: np.ndarray) -> None:
        """
        添加手动导入的图像到全局字典
        
        Args:
            image: 手动导入的图像
        """
        if 'image_input' not in self.global_image_dict:
            self.global_image_dict['image_input'] = []
        
        self.global_image_dict['image_input'].append(image)
        debug(f"Added manual image to global dict, total: {len(self.global_image_dict['image_input'])}", "IMAGE_MANAGER")
    
    def get_images(self, key: str) -> Optional[List[np.ndarray]]:
        """
        从全局字典获取图像列表
        
        Args:
            key: 字典key（相机ID或'image_input'）
            
        Returns:
            图像列表，如果不存在返回None
        """
        return self.global_image_dict.get(key)
    
    def get_latest_image(self, key: str) -> Optional[np.ndarray]:
        """
        获取指定key的最新图像
        
        Args:
            key: 字典key（相机ID或'image_input'）
            
        Returns:
            最新图像，如果不存在返回None
        """
        images = self.global_image_dict.get(key)
        if images and len(images) > 0:
            return images[-1]
        return None
    
    def clear_camera_images(self, camera_id: str) -> None:
        """
        清除指定相机的图像
        
        Args:
            camera_id: 相机ID
        """
        if camera_id in self.global_image_dict:
            del self.global_image_dict[camera_id]
            debug(f"Cleared images for camera: {camera_id}", "IMAGE_MANAGER")
    
    def clear_manual_images(self) -> None:
        """清除所有手动导入的图像"""
        if 'image_input' in self.global_image_dict:
            del self.global_image_dict['image_input']
            debug("Cleared all manual images", "IMAGE_MANAGER")
    
    def clear_all(self) -> None:
        """清除所有图像"""
        self.global_image_dict.clear()
        info("Cleared all images from global dict", "IMAGE_MANAGER")
    
    def get_available_keys(self) -> List[str]:
        """
        获取所有可用的图像key
        
        Returns:
            可用key列表
        """
        return list(self.global_image_dict.keys())
    
    def get_dict_info(self) -> Dict[str, Any]:
        """
        获取全局字典的统计信息
        
        Returns:
            包含统计信息的字典
        """
        info_dict = {
            'total_keys': len(self.global_image_dict),
            'total_images': sum(len(images) for images in self.global_image_dict.values()),
            'keys_detail': {}
        }
        
        for key, images in self.global_image_dict.items():
            info_dict['keys_detail'][key] = {
                'image_count': len(images),
                'is_camera': key != 'image_input',
                'latest_image_shape': images[-1].shape if images else None
            }
        
        return info_dict


# 全局实例
_global_image_manager = GlobalImageManager()

def get_global_image_manager() -> GlobalImageManager:
    """获取全局图像管理器实例"""
    return _global_image_manager