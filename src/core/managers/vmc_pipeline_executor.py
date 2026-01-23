#!/usr/bin/env python3
"""
VMC Pipeline Executor
专门用于处理视觉-机械臂协调工作流的执行器
"""

import json
import time
import numpy as np
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass

# 导入核心模块
from ..managers.log_manager import info, debug, warning, error, LogCategory
from ..managers.vision_pipeline_executor import PipelineExecutor
from ..services.camera_service import CameraService
from ..services.robot_service import RobotService


@dataclass
class VMCExecutionResult:
    """VMC工作流执行结果"""
    success: bool = True
    execution_time: float = 0.0
    error_message: str = ""
    
    # 各阶段执行结果
    camera_output: Optional[Dict[str, List[np.ndarray]]] = None  # 字典格式：{camera_id: [image_list]}
    vision_output: Optional[Dict[str, Any]] = None
    robot_actions: List[Dict[str, Any]] = None
    
    # 执行详情
    execution_details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.robot_actions is None:
            self.robot_actions = []
        if self.execution_details is None:
            self.execution_details = {}


class VMCPipelineExecutor:
    """VMC工作流执行器
    
    专门用于处理相机拍照 → 视觉处理 → 机械臂移动的协调工作流
    """
    
    def __init__(self):
        """初始化VMC执行器"""
        # 初始化服务
        self.camera_service = CameraService()
        self.robot_service = RobotService()
        self.vision_executor = PipelineExecutor()
        
        # 执行状态
        self.is_executing = False
        self.execution_callbacks = {}
        self.step_mode = False  # 单步模式标志
        self.current_step = 0  # 当前执行步骤
        self.execution_plan = []  # 执行计划
        
        info("VMCPipelineExecutor: 初始化完成", "VMC_EXECUTOR", LogCategory.SOFTWARE)
    
    def add_execution_callback(self, event_type: str, callback):
        """添加执行回调函数"""
        if event_type not in self.execution_callbacks:
            self.execution_callbacks[event_type] = []
        self.execution_callbacks[event_type].append(callback)
    
    def _trigger_callback(self, event_type: str, *args, **kwargs):
        """触发回调函数"""
        if event_type in self.execution_callbacks:
            for callback in self.execution_callbacks[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    error(f"VMC执行回调失败: {e}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
    
    def load_vmc_config(self, config_path: str) -> Dict[str, Any]:
        """加载VMC配置文件"""
        try:
            debug(f"VMC执行器: 加载配置文件 {config_path}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 验证配置格式
            if 'vmc_workflow' not in config:
                raise ValueError("配置文件格式错误：缺少vmc_workflow字段")
            
            if 'nodes' not in config['vmc_workflow']:
                raise ValueError("配置文件格式错误：缺少nodes字段")
            
            debug(f"VMC配置加载成功，包含 {len(config['vmc_workflow']['nodes'])} 个节点", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return config
            
        except Exception as e:
            error(f"VMC配置加载失败: {e}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            raise
    
    def enable_step_mode(self):
        """启用单步调试模式"""
        self.step_mode = True
        self.current_step = 0
        debug("VMC执行器已启用单步模式", "VMC_EXECUTOR", LogCategory.SOFTWARE)
    
    def disable_step_mode(self):
        """禁用单步模式，切换到连续执行"""
        self.step_mode = False
        debug("VMC执行器已切换到连续执行模式", "VMC_EXECUTOR", LogCategory.SOFTWARE)
    
    def prepare_execution_plan(self, config_path: str):
        """准备执行计划（用于单步调试）"""
        config = self.load_vmc_config(config_path)
        workflow = config['vmc_workflow']
        nodes = workflow.get('nodes', [])
        connections = workflow.get('connections', [])
        
        self.execution_plan = self._analyze_execution_order(nodes, connections)
        self.current_step = 0
        
        debug(f"VMC执行计划已准备，共 {len(self.execution_plan)} 个步骤", "VMC_EXECUTOR", LogCategory.SOFTWARE)
        
        return self.execution_plan
    
    def step_execute(self) -> bool:
        """执行单步操作"""
        if not self.step_mode:
            warning("当前不是单步模式，请先启用单步调试", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return False
        
        if self.current_step >= len(self.execution_plan):
            warning("所有步骤已执行完毕", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return False
        
        try:
            node_info = self.execution_plan[self.current_step]
            node_type = node_info['type']
            node_config = node_info['config']
            
            debug(f"执行第 {self.current_step + 1} 步: {node_type} 节点", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            
            # 执行对应类型的节点
            if node_type == 'camera':
                result = self._execute_camera_node(node_config)
                # 存储结果供后续步骤使用
                if not hasattr(self, '_step_camera_outputs'):
                    self._step_camera_outputs = []
                self._step_camera_outputs.append(result)
                
            elif node_type == 'vision':
                if not hasattr(self, '_step_camera_outputs') or not self._step_camera_outputs:
                    raise Exception("单步执行：视觉节点需要相机输入图像")
                
                # 使用最新的相机输出
                camera_output = self._step_camera_outputs[-1]
                result = self._execute_vision_node(node_config, camera_output)
                self._step_vision_output = result
                
            elif node_type == 'robot':
                if not hasattr(self, '_step_vision_output') or not self._step_vision_output:
                    raise Exception("单步执行：机械臂节点需要视觉处理结果")
                
                result = self._execute_robot_node(node_config, self._step_vision_output)
            
            self.current_step += 1
            debug(f"第 {self.current_step} 步执行成功", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return True
            
        except Exception as e:
            error(f"单步执行失败: {e}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return False
    
    def get_step_info(self) -> Dict[str, Any]:
        """获取当前步骤信息"""
        return {
            'current_step': self.current_step,
            'total_steps': len(self.execution_plan),
            'step_mode': self.step_mode,
            'current_node': self.execution_plan[self.current_step] if self.current_step < len(self.execution_plan) else None
        }

    def _execute_camera_node(self, node_config: Dict[str, Any]) -> Optional[Dict[str, List[np.ndarray]]]:
        """执行相机节点（使用服务依赖注入）"""
        try:
            node_id = node_config.get('id', 'unknown_camera')
            config = node_config.get('config', {})
            
            debug(f"执行相机节点: {node_id}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            self._trigger_callback('camera_started', node_id)
            
            # 通过HardwareManager进行依赖注入获取相机实例
            hardware_id = config.get('hardware_id', 'default_camera')
            
            # 获取HardwareManager实例
            from ..managers.hardware_manager import HardwareManager
            from ..container import Container
            from ..managers.app_config import AppConfigManager
            from ..managers.log_manager import LogManager
            
            container = Container()
            config_manager = AppConfigManager()
            log_manager = LogManager()
            hardware_manager = HardwareManager(container, config_manager, log_manager)
            
            # 初始化硬件管理器（如果尚未初始化）
            if not hardware_manager.hardware_config:
                hardware_manager.initialize_from_config()
            # 获取相机实例
            camera = hardware_manager.get_camera(hardware_id)
            
            if camera is None:
                raise Exception(f"无法获取相机实例: {hardware_id}")
            
            # 设置相机参数
            exposure_time = config.get('exposure_time', 1000.0)
            gain = config.get('gain', 1.0)
            
            if exposure_time > 0:
                if hasattr(camera, 'set_exposure'):
                    camera.set_exposure(exposure_time)
                    debug(f"相机参数设置: 曝光时间={exposure_time}ms", "VMC_EXECUTOR", LogCategory.HARDWARE)
            
            if gain > 0:
                if hasattr(camera, 'set_gain'):
                    camera.set_gain(gain)
                    debug(f"相机参数设置: 增益={gain}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            
            # 触发拍照
            trigger_mode = config.get('trigger_mode', 'software')
            if trigger_mode == 'software':
                if hasattr(camera, 'trigger_software'):
                    success = camera.trigger_software()
                    if not success:
                        raise Exception("软件触发失败")
                    debug(f"软件触发相机拍照", "VMC_EXECUTOR", LogCategory.HARDWARE)
            
            # 获取图像（支持多相机图像列表）
            images = []
            if hasattr(camera, 'capture_frame'):
                image = camera.capture_frame()
                if image is not None:
                    images = [image]  # 单张图像包装为列表
            elif hasattr(camera, 'capture_images'):
                images = camera.capture_images()  # 已经是列表
                if images is None:
                    images = []
            
            if not images:
                raise Exception("相机捕获图像失败")
            
            # 返回字典格式：{camera_id: [image_list]}
            camera_output = {hardware_id: images}
            
            # 检查是否需要保存图像
            if config.get('save_image', False):
                for i, image in enumerate(images):
                    self._save_camera_image(image, f"{node_id}_{i}", config)
            
            debug(f"相机节点执行成功，捕获{len(images)}张图像", "VMC_EXECUTOR", LogCategory.HARDWARE)
            self._trigger_callback('camera_completed', node_id, camera_output)
            
            return camera_output
            
        except Exception as e:
            error(f"相机节点执行失败: {e}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            self._trigger_callback('camera_failed', node_id, str(e))
            return None
    
    def _save_camera_image(self, image: np.ndarray, node_id: str, config: Dict[str, Any]):
        """保存相机图像到文件"""
        try:
            from ..managers.app_config import AppConfigManager
            
            app_config = AppConfigManager()
            captures_dir = app_config.get_captures_directory()
            captures_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"vmc_camera_{node_id}_{timestamp}.jpg"
            save_path = captures_dir / filename
            
            import cv2
            success = cv2.imwrite(str(save_path), image)
            
            if success:
                debug(f"相机图像已保存: {save_path}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            else:
                warning(f"保存相机图像失败: {save_path}", "VMC_EXECUTOR", LogCategory.HARDWARE)
                
        except Exception as e:
            error(f"保存相机图像时出错: {e}", "VMC_EXECUTOR", LogCategory.HARDWARE)
    
    def _execute_vision_node(self, node_config: Dict[str, Any], camera_output: Dict[str, List[np.ndarray]]) -> Optional[Dict[str, Any]]:
        """执行视觉处理节点"""
        try:
            node_id = node_config.get('id', 'unknown_vision')
            config = node_config.get('config', {})
            
            debug(f"执行视觉节点: {node_id}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            self._trigger_callback('vision_started', node_id)
            
            # 获取算法配置文件路径
            algorithm_config_file = config.get('algorithm_config_file')
            if not algorithm_config_file:
                raise Exception("缺少算法配置文件路径")
            
            # 检查文件是否存在
            config_path = Path(algorithm_config_file)
            if not config_path.is_absolute():
                # 相对路径，相对于workspace目录
                from ..managers.app_config import AppConfigManager
                app_config = AppConfigManager()
                config_path = app_config.workspace_dir / algorithm_config_file
            
            if not config_path.exists():
                raise Exception(f"算法配置文件不存在: {config_path}")
            
            # 处理多相机输入：选择第一个相机或指定相机的主要图像
            primary_image = None
            if camera_output:
                # 如果指定了主相机ID，使用该相机的第一张图像
                primary_camera_id = config.get('primary_camera_id')
                if primary_camera_id and primary_camera_id in camera_output:
                    images = camera_output[primary_camera_id]
                    if images:
                        primary_image = images[0]
                else:
                    # 否则使用第一个相机的第一张图像
                    first_camera_id = list(camera_output.keys())[0]
                    images = camera_output[first_camera_id]
                    if images:
                        primary_image = images[0]
            
            if primary_image is None:
                raise Exception("无法从相机输出中获取主图像用于视觉处理")
            
            # 使用vision_pipeline_executor执行算法
            vision_result = self.vision_executor.execute_pipeline_from_config(
                str(config_path), 
                primary_image, 
                verbose=False
            )
            
            if not vision_result.success:
                raise Exception(f"视觉算法执行失败: {vision_result.error_message}")
            
            # 获取输出映射配置
            output_mapping = config.get('output_mapping', {})
            
            # 构建结构化输出，包含多相机信息
            structured_output = {
                'success': True,
                'algorithm_config_file': str(config_path),
                'processing_time': vision_result.execution_time,
                'final_image_shape': vision_result.final_image.shape if vision_result.final_image is not None else None,
                'camera_info': {
                    'camera_count': len(camera_output),
                    'camera_ids': list(camera_output.keys()),
                    'total_images': sum(len(images) for images in camera_output.values()),
                    'primary_camera': config.get('primary_camera_id') or (list(camera_output.keys())[0] if camera_output else None)
                },
                'input_camera_data': camera_output  # 保留原始相机数据供后续处理
            }
            
            # 根据映射配置提取输出数据
            # 这里需要根据具体的算法结果格式进行映射
            # 暂时使用基本的结果信息
            if vision_result.final_image is not None:
                structured_output.update({
                    'image_processed': True,
                    'image_size': {
                        'height': vision_result.final_image.shape[0],
                        'width': vision_result.final_image.shape[1] if len(vision_result.final_image.shape) > 1 else 1
                    }
                })
            
            # TODO: 根据具体的算法结果实现更精确的输出映射
            # 这里需要与具体的算法结果格式配合
            
            debug(f"视觉节点执行成功，处理时间: {vision_result.execution_time:.3f}s", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            self._trigger_callback('vision_completed', node_id, structured_output)
            
            return structured_output
            
        except Exception as e:
            error(f"视觉节点执行失败: {e}", "VMC_EXECUTOR")
            self._trigger_callback('vision_failed', node_id, str(e))
            return None
    
    def _execute_robot_node(self, node_config: Dict[str, Any], vision_data: Dict[str, Any]) -> bool:
        """执行机械臂节点"""
        try:
            node_id = node_config.get('id', 'unknown_robot')
            config = node_config.get('config', {})
            
            debug(f"执行机械臂节点: {node_id}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            self._trigger_callback('robot_started', node_id)
            
            # 获取硬件配置
            hardware_id = config.get('hardware_id', 'default_robot')
            speed = config.get('speed', 50.0)
            
            # 获取HardwareManager实例
            from ..managers.hardware_manager import HardwareManager
            from ..container import Container
            from ..managers.app_config import AppConfigManager
            from ..managers.log_manager import LogManager
            
            container = Container()
            config_manager = AppConfigManager()
            log_manager = LogManager()
            hardware_manager = HardwareManager(container, config_manager, log_manager)
            
            # 初始化硬件管理器（如果尚未初始化）
            if not hardware_manager.hardware_config:
                hardware_manager.initialize_from_config()
            
            # 获取机器人实例
            robot = hardware_manager.get_robot(hardware_id)
            if robot is None:
                raise Exception(f"无法获取机器人实例: {hardware_id}")
            
            # 设置速度
            if hasattr(robot, 'set_speed'):
                robot.set_speed(speed)
            elif hasattr(robot, 'set_velocity'):
                robot.set_velocity(speed / 100.0)  # 转换为比例
            
            # 从视觉数据中提取目标位置
            target_position = self._extract_target_position(vision_data, config)
            if target_position is None:
                raise Exception("无法从视觉数据中提取目标位置")
            
            # 获取当前位置
            current_position = None
            if hasattr(robot, 'get_position'):
                current_position = robot.get_position()
            elif hasattr(robot, 'get_current_position'):
                current_position = robot.get_current_position()
                
            if current_position is None:
                warning("无法获取机械臂当前位置，使用默认位置", "VMC_EXECUTOR", LogCategory.HARDWARE)
                current_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            
            # 执行移动算法
            execution_algorithm = config.get('execution_algorithm', {})
            success = self._execute_movement_algorithm(
                robot,
                current_position, 
                target_position, 
                execution_algorithm
            )
            
            if success:
                debug(f"机械臂节点执行成功，移动到: {target_position}", "VMC_EXECUTOR", LogCategory.HARDWARE)
                self._trigger_callback('robot_completed', node_id, target_position)
            else:
                raise Exception("机械臂移动失败")
            
            return success
            
        except Exception as e:
            error(f"机械臂节点执行失败: {e}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            self._trigger_callback('robot_failed', node_id, str(e))
            return False
    
    def _extract_target_position(self, vision_data: Dict[str, Any], config: Dict[str, Any]) -> Optional[tuple]:
        """从视觉数据中提取目标位置"""
        try:
            # 这里需要根据实际的视觉数据格式进行位置提取
            # 暂时使用示例数据
            
            # 优先从输出映射中获取位置信息
            output_mapping = config.get('output_mapping', {})
            position_input = config.get('position_input', 'target_position')
            
            # 如果视觉数据中包含位置信息
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
            
            # 如果没有找到位置信息，返回图像中心对应的坐标
            if vision_data.get('image_size'):
                img_size = vision_data['image_size']
                # 示例：将图像中心转换为机械臂坐标
                center_x = img_size.get('width', 640) / 2
                center_y = img_size.get('height', 480) / 2
                
                # 这里需要根据实际的坐标系转换进行调整
                # 暂时使用简单的线性映射
                robot_x = center_x / 10  # 示例转换
                robot_y = center_y / 10
                robot_z = 100.0  # 默认高度
                
                return (robot_x, robot_y, robot_z, 0.0, 0.0, 0.0)
            
            warning("无法从视觉数据中提取有效的目标位置", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return None
            
        except Exception as e:
            error(f"提取目标位置失败: {e}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return None
    
    def _execute_movement_algorithm(self, robot, current_pos: tuple, target_pos: tuple, algorithm_config: Dict[str, Any]) -> bool:
        """执行机械臂移动算法"""
        try:
            # 获取算法参数
            approach_distance = algorithm_config.get('approach_distance', 50.0)
            safety_height = algorithm_config.get('safety_height', 200.0)
            
            # 简化的移动算法：
            # 1. 先提升到安全高度
            # 2. 移动到目标位置上方
            # 3. 下降到目标位置
            
            # 计算安全位置（保持x,y不变，提升到安全高度）
            safety_pos = (target_pos[0], target_pos[1], safety_height, target_pos[3], target_pos[4], target_pos[5])
            
            # 1. 提升到安全高度
            debug(f"移动到安全位置: {safety_pos}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            success = robot.move_to(*safety_pos)
            if not success:
                raise Exception("移动到安全位置失败")
            
            # 等待移动完成
            self._wait_for_robot_stop(robot)
            
            # 2. 移动到目标位置（考虑接近距离）
            if approach_distance > 0:
                # 计算接近位置
                approach_z = target_pos[2] + approach_distance
                approach_pos = (target_pos[0], target_pos[1], approach_z, target_pos[3], target_pos[4], target_pos[5])
                
                debug(f"移动到接近位置: {approach_pos}", "VMC_EXECUTOR", LogCategory.HARDWARE)
                success = robot.move_to(*approach_pos)
                if not success:
                    raise Exception("移动到接近位置失败")
                
                self._wait_for_robot_stop(robot)
            
            # 3. 移动到最终目标位置
            debug(f"移动到目标位置: {target_pos}", "VMC_EXECUTOR", LogCategory.HARDWARE)
            success = robot.move_to(*target_pos)
            if not success:
                raise Exception("移动到目标位置失败")
            
            self._wait_for_robot_stop(robot)
            
            return True
            
        except Exception as e:
            error(f"移动算法执行失败: {e}", "VMC_EXECUTOR", LogCategory.HARDWARE)
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
                debug(f"检查机器人状态失败: {check_error}", "VMC_EXECUTOR", LogCategory.HARDWARE)
                time.sleep(0.5)
                return True
                
            time.sleep(0.1)
        
        warning("机械臂移动超时", "VMC_EXECUTOR", LogCategory.HARDWARE)
        return False
    
    def execute_vmc_workflow(self, config_path: str) -> VMCExecutionResult:
        """执行完整的VMC工作流
        
        Args:
            config_path: VMC配置文件路径
            
        Returns:
            VMCExecutionResult: 执行结果
        """
        start_time = time.time()
        result = VMCExecutionResult()
        
        try:
            if self.is_executing:
                raise Exception("VMC工作流正在执行中")
            
            self.is_executing = True
            debug(f"开始执行VMC工作流: {config_path}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            self._trigger_callback('workflow_started')
            
            # 加载配置
            config = self.load_vmc_config(config_path)
            workflow = config['vmc_workflow']
            nodes = workflow.get('nodes', [])
            connections = workflow.get('connections', [])
            
            # 分析节点执行顺序
            execution_order = self._analyze_execution_order(nodes, connections)
            
            # 执行工作流
            last_camera_output = None
            last_vision_output = None
            
            for node_info in execution_order:
                node_type = node_info['type']
                node_config = node_info['config']
                
                if node_type == 'camera':
                    # 执行相机节点
                    last_camera_output = self._execute_camera_node(node_config)
                    if last_camera_output is None:
                        raise Exception("相机节点执行失败")
                    
                    result.camera_output = last_camera_output
                    # 更新执行详情以反映多相机输出
                    total_images = sum(len(images) for images in last_camera_output.values())
                    result.execution_details['camera'] = {
                        'success': True,
                        'camera_count': len(last_camera_output),
                        'camera_ids': list(last_camera_output.keys()),
                        'total_images': total_images,
                        'image_shapes': {
                            camera_id: [img.shape for img in images] 
                            for camera_id, images in last_camera_output.items()
                        }
                    }
                    
                elif node_type == 'vision':
                    # 执行视觉节点
                    if last_camera_output is None:
                        raise Exception("视觉节点需要相机输入图像")
                    
                    last_vision_output = self._execute_vision_node(node_config, last_camera_output)
                    if last_vision_output is None:
                        raise Exception("视觉节点执行失败")
                    
                    result.vision_output = last_vision_output
                    result.execution_details['vision'] = {
                        'success': True,
                        'processing_time': last_vision_output.get('processing_time', 0.0)
                    }
                    
                elif node_type == 'robot':
                    # 执行机械臂节点
                    if last_vision_output is None:
                        raise Exception("机械臂节点需要视觉处理结果")
                    
                    robot_success = self._execute_robot_node(node_config, last_vision_output)
                    if not robot_success:
                        raise Exception("机械臂节点执行失败")
                    
                    result.robot_actions.append({
                        'node_id': node_config.get('id', 'unknown'),
                        'success': True
                    })
                    result.execution_details['robot'] = {
                        'success': True
                    }
            
            # 执行成功
            result.success = True
            result.execution_time = time.time() - start_time
            
            debug(f"VMC工作流执行成功，耗时: {result.execution_time:.3f}s", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            self._trigger_callback('workflow_completed', result)
            
            return result
            
        except Exception as e:
            # 执行失败
            result.success = False
            result.error_message = str(e)
            result.execution_time = time.time() - start_time
            
            error(f"VMC工作流执行失败: {e}", "VMC_EXECUTOR")
            self._trigger_callback('workflow_failed', result)
            
            return result
            
        finally:
            self.is_executing = False
    
    def _analyze_execution_order(self, nodes: List[Dict[str, Any]], connections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """分析节点执行顺序"""
        try:
            # 构建节点映射
            node_map = {node['id']: node for node in nodes}
            
            # 构建连接图
            graph = {}
            for conn in connections:
                from_node = conn.get('from')
                to_node = conn.get('to')
                
                if from_node not in graph:
                    graph[from_node] = []
                graph[from_node].append(to_node)
            
            # 拓扑排序
            execution_order = []
            visited = set()
            temp_visited = set()
            
            def dfs(node_id):
                if node_id in temp_visited:
                    raise Exception(f"检测到循环依赖: {node_id}")
                if node_id in visited:
                    return
                
                temp_visited.add(node_id)
                if node_id in graph:
                    for next_node in graph[node_id]:
                        dfs(next_node)
                temp_visited.remove(node_id)
                visited.add(node_id)
                
                if node_id in node_map:
                    execution_order.append(node_map[node_id])
            
            # 找到起始节点（没有前驱的节点）
            all_nodes = set(node_map.keys())
            with_predecessor = set()
            for conn in connections:
                with_predecessor.add(conn.get('to'))
            
            start_nodes = all_nodes - with_predecessor
            
            for node_id in start_nodes:
                dfs(node_id)
            
            # 确保所有节点都被包含
            for node_id in all_nodes:
                if node_id not in visited:
                    if node_id in node_map:
                        execution_order.append(node_map[node_id])
            
            debug(f"VMC节点执行顺序分析完成，共 {len(execution_order)} 个节点", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            return execution_order
            
        except Exception as e:
            error(f"执行顺序分析失败: {e}", "VMC_EXECUTOR", LogCategory.SOFTWARE)
            # 如果分析失败，按原始顺序执行
            return nodes


# 便捷函数，供外部直接调用
def execute_vmc_workflow(config_path: str) -> VMCExecutionResult:
    """便捷函数：执行VMC工作流"""
    executor = VMCPipelineExecutor()
    return executor.execute_vmc_workflow(config_path)