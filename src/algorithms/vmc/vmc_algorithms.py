#!/usr/bin/env python3
"""
VMC算法节点实现
包含相机、视觉处理、机械臂三种节点的算法实现
"""

import cv2
import numpy as np
from typing import Dict, Any, Optional
import json
import time
from pathlib import Path

from core.interfaces.algorithm.base.algorithm_base import AlgorithmBase, AlgorithmInfo, AlgorithmResult, AlgorithmParameter, ParameterType
from core.managers.log_manager import info, debug, warning, error


class VMCCameraAlgorithm(AlgorithmBase):
    """VMC相机拍照算法"""
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="vmc_camera_capture",
            display_name="VMC相机拍照",
            description="VMC工作流中的相机拍照触发节点",
            category="VMC硬件节点",
            secondary_category="相机节点",
            version="1.0.0",
            author="VMC System",
            tags=["vmc", "camera", "capture", "hardware"]
        )
    
    def get_parameters(self) -> list:
        return [
            AlgorithmParameter(
                name="hardware_id",
                param_type=ParameterType.STRING,
                default_value="camera_001",
                description="硬件管理系统中的相机ID"
            ),
            AlgorithmParameter(
                name="trigger_mode",
                param_type=ParameterType.ENUM,
                default_value="software",
                description="触发模式",
                enum_values=["software", "hardware", "auto"]
            ),
            AlgorithmParameter(
                name="exposure_time",
                param_type=ParameterType.FLOAT,
                default_value=1000.0,
                min_value=0.1,
                max_value=10000.0,
                description="曝光时间(ms)"
            ),
            AlgorithmParameter(
                name="gain",
                param_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.1,
                max_value=16.0,
                description="增益"
            ),
            AlgorithmParameter(
                name="save_image",
                param_type=ParameterType.BOOLEAN,
                default_value=True,
                description="是否保存图像"
            )
        ]
    
    def process(self, input_image: np.ndarray) -> AlgorithmResult:
        try:
            start_time = time.time()
            
            # 获取参数
            hardware_id = self.get_parameter("hardware_id")
            trigger_mode = self.get_parameter("trigger_mode")
            exposure_time = self.get_parameter("exposure_time")
            gain = self.get_parameter("gain")
            save_image = self.get_parameter("save_image")
            
            debug(f"VMC相机算法开始执行: {hardware_id}", "HARDWARE")
            
            # 通过HardwareManager获取相机实例（依赖注入）
            from ...managers.hardware_manager import HardwareManager
            from ...container import Container
            from ...managers.app_config import AppConfigManager
            from ...managers.log_manager import LogManager
            
            # 获取HardwareManager实例
            try:
                container = Container()
                config_manager = AppConfigManager()
                log_manager = LogManager()
                hardware_manager = HardwareManager(container, config_manager, log_manager)
                
                # 初始化硬件管理器（如果尚未初始化）
                if not hardware_manager.hardware_config:
                    hardware_manager.initialize_from_config()
                
                # 获取相机实例
                camera = hardware_manager.get_camera(hardware_id)
                if not camera:
                    return AlgorithmResult(
                        success=False,
                        error_message=f"Camera '{hardware_id}' not found in hardware manager"
                    )
                    
            except Exception as e:
                error(f"Failed to get camera from hardware manager: {e}", "HARDWARE")
                # 降级为直接使用服务
                from ...services.camera_service import CameraService
                camera_service = CameraService()
                camera_config = {
                    'name': f"VMC_Camera_{hardware_id}",
                    'hardware_id': hardware_id,
                    'type': 'virtual'
                }
                connect_result = camera_service.connect(camera_config)
                if not connect_result.get('success', False):
                    return AlgorithmResult(
                        success=False,
                        error_message=f"相机连接失败: {connect_result.get('error', '未知错误')}"
                    )
                camera = camera_service.camera
            
            # 使用相机实例进行操作
            captured_images = []
            
            # 设置参数（如果相机支持）
            try:
                if hasattr(camera, 'set_exposure') and exposure_time > 0:
                    camera.set_exposure(exposure_time)
                if hasattr(camera, 'set_gain') and gain > 0:
                    camera.set_gain(gain)
            except Exception as param_error:
                warning(f"设置相机参数失败: {param_error}", "HARDWARE")
            
            # 触发拍照
            if trigger_mode == 'software':
                try:
                    if hasattr(camera, 'trigger_software'):
                        success = camera.trigger_software()
                        if not success:
                            return AlgorithmResult(
                                success=False,
                                error_message="软件触发失败"
                            )
                    else:
                        debug("相机不支持软件触发，直接捕获图像", "HARDWARE")
                except Exception as trigger_error:
                    warning(f"软件触发失败，尝试直接捕获: {trigger_error}", "HARDWARE")
            
            # 捕获图像
            try:
                if hasattr(camera, 'capture_frame'):
                    captured_image = camera.capture_frame()
                    if captured_image is not None:
                        captured_images = [captured_image]  # 单张图像包装为列表
                elif hasattr(camera, 'capture_images'):
                    captured_images = camera.capture_images()  # 已经是列表
                    if captured_images is None:
                        captured_images = []
                
                if not captured_images:
                    return AlgorithmResult(
                        success=False,
                        error_message="相机捕获图像失败"
                    )
                    
            except Exception as capture_error:
                error(f"图像捕获异常: {capture_error}", "HARDWARE")
                return AlgorithmResult(
                    success=False,
                    error_message=f"图像捕获异常: {capture_error}"
                )
            
            # 保存图像（如果需要）
            if save_image:
                try:
                    from ...managers.app_config import AppConfigManager
                    app_config = AppConfigManager()
                    captures_dir = app_config.get_captures_directory()
                    captures_dir.mkdir(parents=True, exist_ok=True)
                    
                    timestamp = int(time.time())
                    for i, img in enumerate(captured_images):
                        save_path = captures_dir / f"vmc_capture_{timestamp}_{hardware_id}_{i}.jpg"
                        cv2.imwrite(str(save_path), img)
                        debug(f"图像已保存到: {save_path}", "HARDWARE")
                except Exception as save_error:
                    warning(f"保存图像失败: {save_error}", "HARDWARE")
            
            processing_time = time.time() - start_time
            
            # 将图像添加到全局字典
            from ...managers.global_image_manager import get_global_image_manager
            global_image_manager = get_global_image_manager()
            global_image_manager.add_camera_images(hardware_id, captured_images)
            
            debug(f"VMC相机算法执行成功，捕获{len(captured_images)}张图像并添加到全局字典，耗时: {processing_time:.3f}s", "HARDWARE")
            
            # 返回第一张图像作为主要输出（单图像兼容）
            output_image = captured_images[0] if captured_images else None
            
            return AlgorithmResult(
                success=True,
                output_image=output_image,
                processing_time=processing_time,
                metadata={
                    'hardware_id': hardware_id,
                    'trigger_mode': trigger_mode,
                    'exposure_time': exposure_time,
                    'gain': gain,
                    'image_count': len(captured_images),
                    'image_shape': output_image.shape if output_image is not None else None,
                    'added_to_global_dict': True,
                    'global_dict_key': hardware_id
                }
            )
            
        except Exception as e:
            error(f"VMC相机算法执行失败: {e}", "HARDWARE")
            return AlgorithmResult(
                success=False,
                error_message=str(e)
            )


class VMCVisionAlgorithm(AlgorithmBase):
    """VMC视觉处理算法"""
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="vmc_vision_processor",
            display_name="VMC视觉处理",
            description="VMC工作流中的视觉算法处理节点，支持可配置输出",
            category="VMC处理节点",
            secondary_category="视觉节点",
            version="1.0.0",
            author="VMC System",
            tags=["vmc", "vision", "processing", "algorithm"]
        )
    
    def get_parameters(self) -> list:
        return [
            AlgorithmParameter(
                name="algorithm_config_file",
                param_type=ParameterType.FILE_PATH,
                default_value="workspace/pipeline/vmc_vision_config.json",
                description="算法配置文件路径"
            ),
            AlgorithmParameter(
                name="output_mapping",
                param_type=ParameterType.JSON,
                default_value='{"target_position": "result.center", "confidence": "result.confidence"}',
                description="输出参数映射配置（JSON格式）"
            ),
            AlgorithmParameter(
                name="image_source_key",
                param_type=ParameterType.STRING,
                default_value="",
                description="图像源key（留空则使用输入图像，否则从全局字典中获取指定key的图像）"
            ),
            AlgorithmParameter(
                name="use_latest_image",
                param_type=ParameterType.BOOLEAN,
                default_value=True,
                description="是否使用指定key的最新图像（False则使用第一张图像）"
            )
        ]
    
    def process(self, input_image: np.ndarray) -> AlgorithmResult:
        try:
            start_time = time.time()
            
            # 获取参数
            algorithm_config_file = self.get_parameter("algorithm_config_file")
            output_mapping_str = self.get_parameter("output_mapping")
            image_source_key = self.get_parameter("image_source_key")
            use_latest_image = self.get_parameter("use_latest_image")
            
            debug(f"VMC视觉算法开始执行: {algorithm_config_file}", "HARDWARE")
            
            # 确定输入图像源
            process_image = input_image
            if image_source_key:
                # 从全局字典获取图像
                from ...managers.global_image_manager import get_global_image_manager
                global_image_manager = get_global_image_manager()
                
                if use_latest_image:
                    process_image = global_image_manager.get_latest_image(image_source_key)
                    debug(f"从全局字典获取最新图像: {image_source_key}", "HARDWARE")
                else:
                    images = global_image_manager.get_images(image_source_key)
                    process_image = images[0] if images else None
                    debug(f"从全局字典获取第一张图像: {image_source_key}", "HARDWARE")
                
                if process_image is None:
                    return AlgorithmResult(
                        success=False,
                        error_message=f"无法从全局字典中获取图像: {image_source_key}"
                    )
            else:
                debug(f"使用输入图像进行处理", "HARDWARE")
            
            # 解析输出映射
            try:
                output_mapping = json.loads(output_mapping_str) if output_mapping_str else {}
            except json.JSONDecodeError:
                warning("输出映射配置格式错误，使用默认配置", "HARDWARE")
                output_mapping = {"target_position": "result.center", "confidence": "result.confidence"}
            
            # 检查配置文件是否存在
            config_path = Path(algorithm_config_file)
            if not config_path.is_absolute():
                from ...managers.app_config import AppConfigManager
                app_config = AppConfigManager()
                config_path = app_config.workspace_dir / algorithm_config_file
            
            if not config_path.exists():
                # 如果配置文件不存在，尝试创建一个默认的配置
                debug(f"算法配置文件不存在，创建默认配置: {config_path}", "HARDWARE")
                self._create_default_vision_config(config_path)
            
            # 使用vision_pipeline_executor执行算法
            from ...managers.vision_pipeline_executor import PipelineExecutor
            vision_executor = PipelineExecutor()
            
            vision_result = vision_executor.execute_pipeline_from_config(
                str(config_path),
                process_image,
                verbose=False
            )
            
            if not vision_result.success:
                return AlgorithmResult(
                    success=False,
                    error_message=f"视觉算法执行失败: {vision_result.error_message}"
                )
            
            # 构建结构化输出数据
            structured_output = {
                'success': True,
                'algorithm_config_file': str(config_path),
                'processing_time': vision_result.execution_time,
                'output_mapping': output_mapping,
                'image_source': {
                    'used_global_dict': bool(image_source_key),
                    'source_key': image_source_key or 'input_image',
                    'use_latest_image': use_latest_image if image_source_key else None
                }
            }
            
            # 尝试从算法结果中提取映射的数据
            # 这里需要根据具体的算法结果格式进行适配
            processed_image = vision_result.final_image
            
            # 添加图像处理结果信息
            if processed_image is not None:
                structured_output.update({
                    'image_processed': True,
                    'image_size': {
                        'height': processed_image.shape[0],
                        'width': processed_image.shape[1] if len(processed_image.shape) > 1 else 1,
                        'channels': processed_image.shape[2] if len(processed_image.shape) > 2 else 1
                    }
                })
                
                # 示例：简单的目标检测（这里使用图像中心作为示例目标）
                height, width = processed_image.shape[:2]
                center_x, center_y = width // 2, height // 2
                
                # 根据输出映射配置生成输出数据
                if 'target_position' in output_mapping:
                    structured_output['target_position'] = {
                        'x': float(center_x),
                        'y': float(center_y),
                        'z': 0.0  # 默认深度
                    }
                
                if 'confidence' in output_mapping:
                    # 示例置信度计算
                    structured_output['confidence'] = 0.85
                
                if 'target_size' in output_mapping:
                    # 示例目标尺寸
                    structured_output['target_size'] = {
                        'width': 50.0,
                        'height': 50.0
                    }
            
            processing_time = time.time() - start_time
            debug(f"VMC视觉算法执行成功，耗时: {processing_time:.3f}s", "VMC_VISION")
            
            return AlgorithmResult(
                success=True,
                output_image=processed_image,
                processing_time=processing_time,
                metadata={
                    'structured_data': structured_output,
                    'algorithm_config_file': str(config_path),
                    'vision_execution_time': vision_result.execution_time
                }
            )
            
        except Exception as e:
            error(f"VMC视觉算法执行失败: {e}", "VMC_VISION")
            return AlgorithmResult(
                success=False,
                error_message=str(e)
            )
    
    def _create_default_vision_config(self, config_path: Path):
        """创建默认的视觉算法配置文件"""
        try:
            default_config = {
                "chain": [
                    {
                        "algorithm_id": "gaussian_blur",
                        "display_name": "高斯模糊",
                        "category": "基础算子",
                        "parameters": {
                            "kernel_size": 5,
                            "sigma_x": 1.0,
                            "sigma_y": 1.0
                        },
                        "layout": {
                            "position": {"x": 100, "y": 100},
                            "node_id": "blur_001"
                        }
                    }
                ],
                "metadata": {
                    "version": "1.0",
                    "algorithm_count": 1,
                    "canvas_layout": True,
                    "created_at": time.strftime("%a %b %d %H:%M:%S %Y")
                },
                "connections": []
            }
            
            # 确保目录存在
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            debug(f"默认视觉配置文件已创建: {config_path}", "VMC_VISION")
            
        except Exception as e:
            warning(f"创建默认视觉配置文件失败: {e}", "VMC_VISION")


class VMCRobotAlgorithm(AlgorithmBase):
    """VMC机械臂控制算法"""
    
    def get_algorithm_info(self) -> AlgorithmInfo:
        return AlgorithmInfo(
            name="vmc_robot_move",
            display_name="VMC机械臂移动",
            description="VMC工作流中的机械臂位置移动执行节点",
            category="VMC执行节点",
            secondary_category="机械臂节点",
            version="1.0.0",
            author="VMC System",
            tags=["vmc", "robot", "movement", "execution"]
        )
    
    def get_parameters(self) -> list:
        return [
            AlgorithmParameter(
                name="hardware_id",
                param_type=ParameterType.STRING,
                default_value="robot_001",
                description="硬件管理系统中的机械臂ID"
            ),
            AlgorithmParameter(
                name="connection_config",
                param_type=ParameterType.JSON,
                default_value='{"ip": "192.168.1.100", "port": 30003}',
                description="机械臂连接配置（JSON格式）"
            ),
            AlgorithmParameter(
                name="speed",
                param_type=ParameterType.FLOAT,
                default_value=50.0,
                min_value=1.0,
                max_value=100.0,
                description="移动速度(%)"
            ),
            AlgorithmParameter(
                name="position_input",
                param_type=ParameterType.STRING,
                default_value="target_position",
                description="位置数据输入参数名"
            ),
            AlgorithmParameter(
                name="approach_distance",
                param_type=ParameterType.FLOAT,
                default_value=50.0,
                min_value=0.0,
                max_value=200.0,
                description="接近距离(mm)"
            ),
            AlgorithmParameter(
                name="safety_height",
                param_type=ParameterType.FLOAT,
                default_value=200.0,
                min_value=50.0,
                max_value=500.0,
                description="安全高度(mm)"
            )
        ]
    
    def process(self, input_image: np.ndarray) -> AlgorithmResult:
        try:
            start_time = time.time()
            
            # 获取参数
            hardware_id = self.get_parameter("hardware_id")
            connection_config_str = self.get_parameter("connection_config")
            speed = self.get_parameter("speed")
            position_input = self.get_parameter("position_input")
            approach_distance = self.get_parameter("approach_distance")
            safety_height = self.get_parameter("safety_height")
            
            debug(f"VMC机械臂算法开始执行: {hardware_id}", "HARDWARE")
            
            # 解析连接配置
            try:
                connection_config = json.loads(connection_config_str) if connection_config_str else {}
            except json.JSONDecodeError:
                warning("连接配置格式错误，使用默认配置", "HARDWARE")
                connection_config = {"ip": "192.168.1.100", "port": 30003}
            
            # 从输入数据中获取视觉处理结果（支持字典格式和单图像格式）
            vision_data = None
            
            # 如果输入是字典格式（多相机或结构化数据）
            if isinstance(input_image, dict):
                vision_data = input_image.get('structured_data')
                if vision_data is None and 'results' in input_image:
                    # 如果results中包含视觉算法的输出
                    results = input_image['results']
                    if results:
                        # 取第一个结果的结构化数据
                        first_result = list(results.values())[0] if isinstance(results, dict) else results[0]
                        vision_data = getattr(first_result, 'metadata', {}).get('structured_data', None)
            else:
                # 单图像格式，从元数据获取
                if hasattr(input_image, '__metadata__'):
                    vision_data = input_image.__metadata__.get('structured_data')
            
            if vision_data is None:
                return AlgorithmResult(
                    success=False,
                    error_message="无法获取视觉处理结果数据"
                )
            
            # 通过HardwareManager获取机器人实例（依赖注入）
            from ...managers.hardware_manager import HardwareManager
            from ...container import Container
            from ...managers.app_config import AppConfigManager
            from ...managers.log_manager import LogManager
            
            # 获取HardwareManager实例
            try:
                container = Container()
                config_manager = AppConfigManager()
                log_manager = LogManager()
                hardware_manager = HardwareManager(container, config_manager, log_manager)
                
                # 初始化硬件管理器（如果尚未初始化）
                if not hardware_manager.hardware_config:
                    hardware_manager.initialize_from_config()
                
                # 获取机器人实例
                robot = hardware_manager.get_robot(hardware_id)
                if not robot:
                    return AlgorithmResult(
                        success=False,
                        error_message=f"Robot '{hardware_id}' not found in hardware manager"
                    )
                    
            except Exception as e:
                error(f"Failed to get robot from hardware manager: {e}", "HARDWARE")
                # 降级为直接使用服务
                from ...services.robot_service import RobotService
                robot_service = RobotService()
                
                # 构建机械臂连接配置
                robot_config = {
                    'name': f"VMC_Robot_{hardware_id}",
                    'hardware_id': hardware_id,
                'type': 'virtual',
                **connection_config
            }
            
            connect_result = robot_service.connect(robot_config)
            if not connect_result.get('success', False):
                return AlgorithmResult(
                    success=False,
                    error_message=f"机械臂连接失败: {connect_result.get('error', '未知错误')}"
                )
                robot = robot_service.robot
            
            # 从视觉数据中提取目标位置
            target_position = self._extract_target_position(vision_data)
            if target_position is None:
                return AlgorithmResult(
                    success=False,
                    error_message="无法从视觉数据中提取目标位置"
                )
            
            # 使用机器人实例进行操作
            try:
                # 设置速度（如果支持）
                if hasattr(robot, 'set_speed'):
                    robot.set_speed(speed)
                elif hasattr(robot, 'set_velocity'):
                    robot.set_velocity(speed / 100.0)  # 转换为比例
                
                # 获取当前位置
                current_position = None
                if hasattr(robot, 'get_position'):
                    current_position = robot.get_position()
                elif hasattr(robot, 'get_current_position'):
                    current_position = robot.get_current_position()
                
                if current_position is None:
                    warning("无法获取机械臂当前位置，使用默认位置", "HARDWARE")
                    current_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                
                # 执行移动算法
                success = self._execute_movement_algorithm(
                    robot, 
                    current_position, 
                    target_position, 
                    approach_distance,
                    safety_height
                )
                
            except Exception as robot_error:
                error(f"机器人操作异常: {robot_error}", "HARDWARE")
                return AlgorithmResult(
                    success=False,
                    error_message=f"机器人操作异常: {robot_error}"
                )
            
            if not success:
                return AlgorithmResult(
                    success=False,
                    error_message="机械臂移动失败"
                )
            
            processing_time = time.time() - start_time
            debug(f"VMC机械臂算法执行成功，耗时: {processing_time:.3f}s", "HARDWARE")
            
            # 机械臂算法不需要输出图像，但可以返回当前状态信息
            status_image = self._create_status_image(target_position, processing_time)
            
            return AlgorithmResult(
                success=True,
                output_image=status_image,
                processing_time=processing_time,
                metadata={
                    'hardware_id': hardware_id,
                    'target_position': target_position,
                    'current_position': current_position,
                    'movement_completed': True,
                    'robot_actions': [{
                        'action': 'move_to_position',
                        'target': target_position,
                        'success': True
                    }]
                }
            )
            
        except Exception as e:
            error(f"VMC机械臂算法执行失败: {e}", "HARDWARE")
            return AlgorithmResult(
                success=False,
                error_message=str(e)
            )
    
    def _extract_target_position(self, vision_data: Dict[str, Any]) -> Optional[tuple]:
        """从视觉数据中提取目标位置"""
        try:
            if 'target_position' in vision_data:
                pos_data = vision_data['target_position']
                if isinstance(pos_data, dict):
                    return (
                        pos_data.get('x', 0.0),
                        pos_data.get('y', 0.0), 
                        pos_data.get('z', 0.0),
                        pos_data.get('rx', 0.0),
                        pos_data.get('ry', 0.0),
                        pos_data.get('rz', 0.0)
                    )
                elif isinstance(pos_data, (list, tuple)) and len(pos_data) >= 3:
                    return tuple(pos_data) + (0.0, 0.0, 0.0)
            
            # 如果没有找到位置信息，生成示例位置
            if vision_data.get('image_size'):
                img_size = vision_data['image_size']
                center_x = img_size.get('width', 640) / 2
                center_y = img_size.get('height', 480) / 2
                
                # 简单的坐标转换
                robot_x = center_x / 10  # 示例转换
                robot_y = center_y / 10
                robot_z = 100.0  # 默认高度
                
                return (robot_x, robot_y, robot_z, 0.0, 0.0, 0.0)
            
            return None
            
        except Exception as e:
            error(f"提取目标位置失败: {e}", "HARDWARE")
            return None
    
    def _execute_movement_algorithm(self, robot, current_pos: tuple, target_pos: tuple, 
                                  approach_distance: float, safety_height: float) -> bool:
        """执行机械臂移动算法"""
        try:
            # 计算安全位置
            safety_pos = (target_pos[0], target_pos[1], safety_height, target_pos[3], target_pos[4], target_pos[5])
            
            # 1. 提升到安全高度
            debug(f"移动到安全位置: {safety_pos}", "HARDWARE")
            success = robot.move_to(*safety_pos)
            if not success:
                raise Exception("移动到安全位置失败")
            
            # 等待移动完成
            self._wait_for_robot_stop(robot)
            
            # 2. 移动到接近位置
            if approach_distance > 0:
                approach_z = target_pos[2] + approach_distance
                approach_pos = (target_pos[0], target_pos[1], approach_z, target_pos[3], target_pos[4], target_pos[5])
                
                debug(f"移动到接近位置: {approach_pos}", "HARDWARE")
                success = robot.move_to(*approach_pos)
                if not success:
                    raise Exception("移动到接近位置失败")
                
                self._wait_for_robot_stop(robot)
            
            # 3. 移动到最终目标位置
            debug(f"移动到目标位置: {target_pos}", "HARDWARE")
            success = robot.move_to(*target_pos)
            if not success:
                raise Exception("移动到目标位置失败")
            
            self._wait_for_robot_stop(robot)
            
            return True
            
        except Exception as e:
            error(f"移动算法执行失败: {e}", "HARDWARE")
            return False
    
    def _wait_for_robot_stop(self, robot, timeout: float = 30.0) -> bool:
        """等待机械臂停止移动"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 检查机器人是否在移动（检查是否有is_moving方法）
            try:
                if hasattr(robot, 'is_moving'):
                    if not robot.is_moving():
                        return True
                elif hasattr(robot, 'get_state'):
                    state = robot.get_state()
                    if state and hasattr(state, 'is_moving') and not state.is_moving:
                        return True
                else:
                    # 如果没有移动状态检查方法，等待一个短时间后假设完成
                    time.sleep(0.5)
                    return True
            except Exception as check_error:
                debug(f"检查机器人状态失败: {check_error}", "HARDWARE")
                time.sleep(0.5)
                return True
                
            time.sleep(0.1)
        
        warning("机械臂移动超时", "HARDWARE")
        return False
    
    def _create_status_image(self, target_position: tuple, processing_time: float) -> np.ndarray:
        """创建状态显示图像"""
        try:
            # 创建一个状态显示图像
            img = np.zeros((200, 400, 3), dtype=np.uint8)
            img.fill(240)  # 浅灰色背景
            
            # 添加状态文本
            font = cv2.FONT_HERSHEY_SIMPLEX
            
            # 标题
            cv2.putText(img, "VMC Robot Status", (20, 30), font, 0.7, (0, 0, 0), 2)
            
            # 目标位置
            pos_text = f"Target: ({target_position[0]:.1f}, {target_position[1]:.1f}, {target_position[2]:.1f})"
            cv2.putText(img, pos_text, (20, 70), font, 0.5, (0, 100, 0), 1)
            
            # 处理时间
            time_text = f"Processing Time: {processing_time:.3f}s"
            cv2.putText(img, time_text, (20, 100), font, 0.5, (0, 0, 100), 1)
            
            # 状态
            cv2.putText(img, "Status: Movement Completed", (20, 130), font, 0.5, (0, 150, 0), 1)
            
            # 时间戳
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(img, timestamp, (20, 170), font, 0.4, (100, 100, 100), 1)
            
            return img
            
        except Exception as e:
            error(f"创建状态图像失败: {e}", "HARDWARE")
            # 返回一个简单的状态图像
            return np.ones((100, 300, 3), dtype=np.uint8) * 240