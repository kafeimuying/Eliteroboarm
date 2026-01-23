import subprocess
import os
import threading
import socket
import time
import math
import struct
from typing import Dict, Any, Optional, Tuple, List
from core.interfaces.hardware import IRobot, RobotState, MotionMode, RobotPosition, PathPoint, RobotPath
from core.managers.log_manager import info, error, warning

# Try to import the SDK wrapper
try:
    from .elite_sdk_wrapper import EliteSDK
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

# Try to import the compiled C++ extension
CPP_EXT_AVAILABLE = False
try:
    import elite_ext
    CPP_EXT_AVAILABLE = True
    info("Success loading Elite C++ Extension", "ROBOT_DRIVER")
except ImportError:
    # 尝试自动添加路径 (Development Environment Fallback)
    try:
        import sys
        from pathlib import Path
        
        # 假设当前文件在 src/drivers/robot/elite.py
        # 目标在 project_root/cpp_extensions/extensions/Release
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        ext_path = project_root / "cpp_extensions" / "extensions" / "Release"
        
        if ext_path.exists() and str(ext_path) not in sys.path:
            sys.path.append(str(ext_path))
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(str(ext_path))
                except:
                    pass
            
            import elite_ext
            CPP_EXT_AVAILABLE = True
            info(f"Success loading Elite C++ Extension from {ext_path}", "ROBOT_DRIVER")
            
    except ImportError as e:
        CPP_EXT_AVAILABLE = False
        info(f"Elite C++ Extension not found ({e}), falling back to Python Implementation", "ROBOT_DRIVER")
except Exception:
    CPP_EXT_AVAILABLE = False

class EliteRobot(IRobot):
    """Elite机器人驱动实现"""

    def __init__(self):
        self.connected = False
        self.config = {}
        # External EXE path removed/deprecated
        self.exe_path = r"W:\CATL\Elite\elitesdk\x64\Debug\LetRobotMove.exe"
        self.motion_mode = MotionMode.MANUAL
        self.state = RobotState.IDLE
        self.calibration_process = None
        self.log_callbacks = []
        self.last_position = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        
        # Internal Calibration State
        self._calib_thread = None
        self._calib_event = threading.Event()
        self._calib_stop_event = threading.Event()
        self._capture_callback = None  # 自动拍照回调

        # SDK Wrapper instance
        self.sdk = None
        self.driver_handle = None
        
        # C++ Extension Controller
        self.controller = None
        self.calibration_controller = None
        if CPP_EXT_AVAILABLE:
            try:
                self.controller = elite_ext.EliteRobotController()
                self.calibration_controller = elite_ext.EliteCalibration()
                info("EliteRobotController and Calibration instantiated", "ROBOT_DRIVER")
            except Exception as e:
                error(f"Failed to instantiate EliteRobotController: {e}", "ROBOT_DRIVER")
                self.controller = None
                self.calibration_controller = None

    def set_capture_callback(self, callback):
        """设置自动拍照回调函数"""
        self._capture_callback = callback

    def register_log_callback(self, callback) -> bool:
        """注册日志回调"""
        if callback not in self.log_callbacks:
            self.log_callbacks.append(callback)
        return True

    def unregister_log_callback(self, callback) -> bool:
        """取消注册日志回调"""
        if callback in self.log_callbacks:
            self.log_callbacks.remove(callback)
        return True

    def _monitor_process_output(self, process):
        """监控进程输出并发送到日志回调"""
        try:
            # 读取标准输出
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if line:
                    # 发送日志
                    for callback in self.log_callbacks:
                        try:
                            callback("信息", f"[Elite] {line}")
                        except:
                            pass
                    info(f"[Elite Output] {line}", "ROBOT_DRIVER")
            
            # 进程结束后检查返回码
            process.wait()
            if process.returncode != 0:
                err_msg = f"Process exited with code {process.returncode}"
                for callback in self.log_callbacks:
                    try:
                        callback("错误", f"[Elite] {err_msg}")
                    except:
                        pass
                error(f"[Elite] {err_msg}", "ROBOT_DRIVER")
            else:
                success_msg = "Calibration process completed successfully"
                for callback in self.log_callbacks:
                    try:
                        callback("信息", f"[Elite] {success_msg}")
                    except:
                        pass
                info(f"[Elite] {success_msg}", "ROBOT_DRIVER")

        except Exception as e:
            error(f"Error monitoring process output: {e}", "ROBOT_DRIVER")
        finally:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

    def connect(self, config: Dict[str, Any]) -> bool:
        """连接Elite机器人"""
        self.config = config
        ip = config.get('connection_params', {}).get('ip', '127.0.0.1')
        self.robot_ip = ip
        self.global_speed_ratio = 0.5 # 默认50%速度
        info(f"Connecting to Elite robot at {ip}", "ROBOT_DRIVER")
        
        # 1. 优先尝试使用 C++ Extension 连接
        if self.controller:
            try:
                # 假设 config 中有 recipe_dir，或者使用默认项目路径
                # 这里的 recipe_dir 用于查找 input_recipe.txt / output_recipe.txt
                # 使用项目根目录作为 recipe_dir (假设 W:\CATL\Roboarm)
                recipe_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                
                info(f"Connecting via C++ Extension... Recipe Dir: {recipe_dir}", "ROBOT_DRIVER")
                success = self.controller.connect(ip, recipe_dir)
                
                if success:
                    info("Connected successfully via C++ Extension", "ROBOT_DRIVER")
                    self.connected = True
                    self.state = RobotState.IDLE
                    
                    # 同步初始速度
                    self.controller.set_speed(int(self.global_speed_ratio * 100))
                    return True
                else:
                    warning("C++ Extension connection failed, falling back to legacy method", "ROBOT_DRIVER")
            except Exception as e:
                error(f"C++ connect error: {e}", "ROBOT_DRIVER")
                # Fallthrough to legacy method

        # 2. Legacy Connection Method (Ping -> Dashboard -> Primary)
        # 尝试初始化SDK (用于获取位姿和发送脚本)
        if SDK_AVAILABLE:
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                dll_path = os.path.join(current_dir, "bin", "elite_wrapper.dll")
                
                if os.path.exists(dll_path):
                    info(f"Initializing SDK wrapper: {dll_path}", "ROBOT_DRIVER")
                    self.sdk = EliteSDK(dll_path)
                    self.driver_handle = self.sdk.create_driver(ip)
                    
                    if self.driver_handle:
                        is_connected = self.sdk.is_connected(self.driver_handle)
                        info(f"SDK initialized. Connected: {is_connected}", "ROBOT_DRIVER")
                    else:
                        warning("Failed to create SDK driver handle", "ROBOT_DRIVER")
            except Exception as e:
                error(f"SDK initialization failed: {e}", "ROBOT_DRIVER")

        # 执行Ping命令检查连接
        try:
            # Windows下ping命令参数为-n，Linux下为-c
            param = '-n' if os.name == 'nt' else '-c'
            command = ['ping', param, '1', ip]
            
            # 隐藏控制台窗口 (Windows only)
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            
            if result.returncode == 0:
                info(f"Ping {ip} successful", "ROBOT_DRIVER")
                
                # 连接Dashboard进行上电和松刹车
                try:
                    info("Connecting to Dashboard (29999)...", "ROBOT_DRIVER")
                    # 保持Dashboard连接
                    self.dashboard_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.dashboard_socket.settimeout(10.0)
                    self.dashboard_socket.connect((ip, 29999))
                    
                    # 接收欢迎消息
                    try:
                        welcome = self.dashboard_socket.recv(1024).decode('utf-8').strip()
                        info(f"Dashboard welcome: {welcome}", "ROBOT_DRIVER")
                    except:
                        pass

                    # 尝试获取当前状态（用于调试和潜在的优化）
                    try:
                        self.dashboard_socket.sendall(b"getRobotMode\n")
                        current_mode = self.dashboard_socket.recv(1024).decode('utf-8').strip()
                        info(f"Current Robot Mode: {current_mode}", "ROBOT_DRIVER")
                    except:
                        pass

                    # 模拟C++代码：同时连接Primary Port (30001) 和 RTSI (30004)
                    # C++: if (!dashboard->connect(robot_ip) || !rtsi->connect(robot_ip) || !primary->connect(robot_ip))
                    try:
                        info("Connecting to Primary Port (30001)...", "ROBOT_DRIVER")
                        self.primary_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.primary_socket.settimeout(5.0)
                        self.primary_socket.connect((ip, 30001))
                        info("Primary Port connected", "ROBOT_DRIVER")
                    except Exception as e:
                        warning(f"Failed to connect to Primary Port: {e}", "ROBOT_DRIVER")

                    try:
                        info("Connecting to RTSI Port (30004)...", "ROBOT_DRIVER")
                        self.rtsi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.rtsi_socket.settimeout(5.0)
                        self.rtsi_socket.connect((ip, 30004))
                        info("RTSI Port connected", "ROBOT_DRIVER")
                    except Exception as e:
                        warning(f"Failed to connect to RTSI Port: {e}", "ROBOT_DRIVER")

                    # 1. 上电 (C++: dashboard->powerOn())
                    # 根据Dashboard help信息，正确命令是 'robotControl -on'
                    info("Sending 'robotControl -on' command...", "ROBOT_DRIVER")
                    self.dashboard_socket.sendall(b"robotControl -on\n")
                    time.sleep(1.0)
                    try:
                        response = self.dashboard_socket.recv(1024).decode('utf-8').strip()
                        info(f"Power On response: {response}", "ROBOT_DRIVER")
                    except:
                        pass
                        
                    # 等待上电完成
                    info("Waiting for power on (15s)...", "ROBOT_DRIVER")
                    time.sleep(15.0)
                    
                    # 尝试清除可能存在的弹窗或保护停止，这可能是导致无法松刹车的原因
                    try:
                        self.dashboard_socket.settimeout(1.0)
                        self.dashboard_socket.sendall(b"closeSafetyDialog\n")
                        try: self.dashboard_socket.recv(1024) 
                        except: pass
                        
                        self.dashboard_socket.sendall(b"unlockProtectiveStop\n")
                        try: self.dashboard_socket.recv(1024)
                        except: pass
                        self.dashboard_socket.settimeout(10.0)
                    except:
                        pass

                    # 2. 松刹车 (C++: dashboard->brakeRelease())
                    info("Sending 'brakeRelease' command...", "ROBOT_DRIVER")
                    self.dashboard_socket.sendall(b"brakeRelease\n")
                    time.sleep(1.0)
                    try:
                        response = self.dashboard_socket.recv(1024).decode('utf-8').strip()
                        info(f"Brake Release response: {response}", "ROBOT_DRIVER")
                        
                        # 如果因为安全原因失败，尝试重试
                        if "safety reasons" in response or "Can't" in response:
                            warning("Brake release failed, retrying in 5s...", "ROBOT_DRIVER")
                            time.sleep(5.0)
                            self.dashboard_socket.sendall(b"brakeRelease\n")
                            response = self.dashboard_socket.recv(1024).decode('utf-8').strip()
                            info(f"Brake Release retry response: {response}", "ROBOT_DRIVER")
                    except:
                        pass
                    
                    # 等待松刹车完成
                    info("Waiting for brake release...", "ROBOT_DRIVER")
                    time.sleep(10.0)
                    
                    info("Robot initialization completed", "ROBOT_DRIVER")
                    
                    # 关闭临时连接
                    # 注意：保留Primary Port连接用于get_position回退方案
                    # if hasattr(self, 'primary_socket'):
                    #     try:
                    #         self.primary_socket.close()
                    #     except:
                    #         pass
                    
                    # 关闭RTSI连接 (我们不使用Python端的RTSI，避免冲突)
                    if hasattr(self, 'rtsi_socket'):
                        try:
                            self.rtsi_socket.close()
                        except:
                            pass
                    
                    # 保持Dashboard连接，用于后续发送速度控制等命令
                    # self.dashboard_socket.close() 
                        
                    self.connected = True
                    self.state = RobotState.IDLE
                    return True

                except Exception as e:
                    error(f"Dashboard initialization failed: {e}", "ROBOT_DRIVER")
                    self.connected = False
                    return False
            else:
                error(f"Ping {ip} failed", "ROBOT_DRIVER")
                self.connected = False
                return False
        except Exception as e:
            error(f"Ping check failed: {e}", "ROBOT_DRIVER")
            self.connected = False
            return False

    def send_script(self, script: str) -> bool:
        """发送脚本命令到机器人"""
        if not self.connected or not self.robot_ip:
            return False
        
        try:
            # Elite机器人通常使用30001端口接收脚本命令
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.robot_ip, 30001))
                s.sendall((script + "\n").encode('utf-8'))
            return True
        except Exception as e:
            error(f"Failed to send script to Elite robot: {e}", "ROBOT_DRIVER")
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        # 先执行清理操作，再改变状态
        
        # C++ Extension Disconnect
        if self.controller:
            try:
                self.controller.disconnect()
                info("Disconnected via C++ Extension", "ROBOT_DRIVER")
            except Exception as e:
                error(f"C++ disconnect error: {e}", "ROBOT_DRIVER")
        
        # 关闭Dashboard连接
        if hasattr(self, 'dashboard_socket'):
            try:
                self.dashboard_socket.close()
            except:
                pass
        
        # 清理SDK资源
        if self.sdk and self.driver_handle:
            try:
                self.sdk.destroy_driver(self.driver_handle)
                self.driver_handle = None
                info("SDK driver destroyed", "ROBOT_DRIVER")
            except Exception as e:
                error(f"Failed to destroy SDK driver: {e}", "ROBOT_DRIVER")

        # 停止内部标定线程
        if self._calib_thread and self._calib_thread.is_alive():
            try:
                self._calib_stop_event.set()
                self._calib_event.set() # 唤醒以使其退出
                self._calib_thread.join(timeout=2.0)
                info("Stopped internal calibration thread", "ROBOT_DRIVER")
            except Exception as e:
                error(f"Failed to stop calibration thread: {e}", "ROBOT_DRIVER")

        # 如果有正在运行的标定程序（旧版兼容），尝试关闭它
        if self.calibration_process and self.calibration_process.poll() is None:
            try:
                self.calibration_process.terminate()
                info("Terminated running calibration process", "ROBOT_DRIVER")
            except Exception as e:
                error(f"Failed to terminate calibration process: {e}", "ROBOT_DRIVER")
        
        # 最后改变状态
        self.connected = False
        self.state = RobotState.DISCONNECTED
        info("Elite robot disconnected", "ROBOT_DRIVER")
        return True

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected

    def get_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        return {
            'brand': 'Elite',
            'model': 'Elite Robot',
            'version': '1.0.0'
        }

    def test_connection(self) -> Dict[str, Any]:
        """测试连接 - 启动内置标定流程"""
        ip = self.config.get('connection_params', {}).get('ip', '')
        if not ip:
            return {'success': False, 'error': "IP address not configured"}

        # 确保已连接
        if not self.connected:
             warning("Robot not connected, attempting to connect...", "ROBOT_DRIVER")
             if not self.connect(self.config):
                 return {'success': False, 'error': "Failed to connect to robot"}

        # 检查是否已有标定在运行
        if self._calib_thread and self._calib_thread.is_alive():
            warning("Calibration already running", "ROBOT_DRIVER")
            return {'success': True, 'message': "Calibration process already running"}

        try:
            self._calib_stop_event.clear()
            self._calib_event.clear()
            self._calib_thread = threading.Thread(
                target=self._run_internal_calibration,
                daemon=True
            )
            self._calib_thread.start()
            
            info("Elite robot internal calibration started", "ROBOT_DRIVER")
            return {
                'success': True, 
                'message': f'Calibration process started on {ip}',
                'device_info': {'type': 'Elite Robot', 'model': 'Elite', 'ip': ip}
            }
                
        except Exception as e:
            error(f"Failed to start Elite robot calibration: {e}", "ROBOT_DRIVER")
            return {'success': False, 'error': str(e)}

    def _run_cpp_calibration(self):
        """Invoke C++ Calibration Implementation"""
        info("[Calibration] Starting C++ 9-point calibration (Optimization Enabled)...", "ROBOT_DRIVER")
        self._broadcast_log("启动C++高性能标定流程 (RTSI Bypass模式)...")

        ip = self.config.get('connection_params', {}).get('ip', '127.0.0.1')
        recipe_path = os.getcwd()

        # 1. Connect Calibration Controller (Dashboard/Primary only)
        if not self.calibration_controller.connect(ip, recipe_path):
             self._broadcast_log("Error: C++标定控制器连接失败")
             return

        # 2. Define Callbacks
        def log_wrapper(msg: str):
            self._broadcast_log(f"[Native] {msg}")

        def capture_wrapper(idx: int):
            if self._capture_callback:
                self._broadcast_log(f"触发拍照 (点 {idx})...")
                self._capture_callback(idx)

        def get_pose_wrapper() -> List[float]:
            p = self.get_position()
            if p:
                return list(p)
            return []

        # 3. Run Calibration
        try:
            # Pass 3 callbacks: log, capture, get_pose
            self.calibration_controller.run_calibration(log_wrapper, capture_wrapper, get_pose_wrapper)
            self._broadcast_log("C++标定流程结束")
        except Exception as e:
            self._broadcast_log(f"C++标定异常: {e}")
            error(f"C++ Calibration Exception: {e}", "ROBOT_DRIVER")
        finally:
            self.calibration_controller.disconnect()

    def _run_internal_calibration(self):
        """内置9点标定逻辑"""
        # 优先使用 C++ 模块 (如果可用)
        if self.calibration_controller:
            try:
                self._run_cpp_calibration()
                return
            except Exception as e:
                error(f"C++ Calibration failed ({e}), falling back to Python implementation", "ROBOT_DRIVER")
                self._broadcast_log("C++标定失败，回退到Python模式...")

        try:
            GRID_STEP = 50.0  # mm
            MOVE_SPEED = 0.2  # 20%
            
            info("[Calibration] Starting 9-point calibration (YOZ Plane)...", "ROBOT_DRIVER")
            self._broadcast_log("开始9点标定流程 (YOZ平面, 镜头面向X+)...")
            
            # 1. 获取中心点 (P5)
            # 尝试多次获取，确保数据有效
            center_pose = None
            for _ in range(3):
                p = self.get_position()
                if p and not all(v == 0 for v in p):
                    center_pose = list(p)
                    break
                time.sleep(0.5)
                
            if not center_pose:
                self._broadcast_log("错误：无法获取当前机器人位置")
                return

            cx, cy, cz, crx, cry, crz = center_pose
            self._broadcast_log(f"中心点已记录: [{cx:.1f}, {cy:.1f}, {cz:.1f}]")

            # 定义9个点的偏移量 (相对于中心点)
            # 用户要求: 标定棋盘格平面平行于YOZ平面，镜头面向X+
            # 因此保持 X 不变，在 Y 和 Z 轴上生成网格
            # 生成 3x3 网格
            # 顺序: 为了方便数据整理，通常先遍历一个轴，再遍历另一个
            # 假设 Z 轴为行（外循环），Y 轴为列（内循环）
            # Row 1 (Bottom): Z-Step -> Y: -Step, 0, +Step
            # Row 2 (Mid):    Z        -> Y: -Step, 0, +Step
            # Row 3 (Top):    Z+Step -> Y: -Step, 0, +Step
            
            offsets = []
            for dz in [-GRID_STEP, 0, GRID_STEP]:
                for dy in [-GRID_STEP, 0, GRID_STEP]:
                    offsets.append((0, dy, dz))
            
            # 设置全局速度
            self.set_speed(int(MOVE_SPEED * 100))
            
            output_data_lines = []

            for i, (dx, dy, dz) in enumerate(offsets):
                if self._calib_stop_event.is_set():
                    self._broadcast_log("标定已取消")
                    return

                target_x = cx + dx
                target_y = cy + dy
                target_z = cz + dz
                point_idx = i + 1
                
                msg = f"正在移动到点 {point_idx} (Y: {target_y:.1f}, Z: {target_z:.1f})..."
                self._broadcast_log(msg)
                info(msg, "ROBOT_DRIVER")
                
                # 移动
                self.move_to(target_x, target_y, target_z, crx, cry, crz)
                
                # 等待到位
                if not self._wait_until_reached((target_x, target_y, target_z, crx, cry, crz)):
                    self._broadcast_log(f"错误：移动到点 {point_idx} 超时")
                    return

                # 到位停留一会，确保稳定并获取精确坐标
                time.sleep(0.5)
                
                # 获取当前精确位姿用于记录
                # get_position 返回: [x(mm), y, z, rx(deg), ry, rz]
                # 用户要求输出: PointID, X(m), Y(m), Z(m), Rx(rad), Ry(rad), Rz(rad)
                curr_pos = self.get_position()
                if curr_pos:
                    x_m = curr_pos[0] / 1000.0
                    y_m = curr_pos[1] / 1000.0
                    z_m = curr_pos[2] / 1000.0
                    rx_rad = curr_pos[3] / 57.29578
                    ry_rad = curr_pos[4] / 57.29578
                    rz_rad = curr_pos[5] / 57.29578
                    
                    data_str = f"{point_idx}, {x_m:.6f}, {y_m:.6f}, {z_m:.6f}, {rx_rad:.6f}, {ry_rad:.6f}, {rz_rad:.6f}"
                    output_data_lines.append(data_str)
                    
                    # 打印到日志供用户查看
                    self._broadcast_log(f"点 {point_idx} 数据: {data_str}")
                else:
                    self._broadcast_log(f"警告: 点 {point_idx} 数据获取失败")

                self._broadcast_log(f"到达点 {point_idx}。")
                
                if self._capture_callback:
                    # 自动模式：调用回调进行拍照
                    self._broadcast_log(f"正在自动拍照 (点 {point_idx})...")
                    try:
                        # 调用回调，传入点序号
                        self._capture_callback(point_idx)
                        self._broadcast_log(f"点 {point_idx} 拍照完成")
                    except Exception as e:
                        self._broadcast_log(f"自动拍照失败: {e}")
                        error(f"Auto capture failed at point {point_idx}: {e}", "ROBOT_DRIVER")
                        # 如果自动拍照失败，是否暂停？还是继续？这里选择继续但记录错误
                else:
                    # 手动模式：等待用户确认
                    self._broadcast_log("请手动拍照，然后点击确认继续。")
                    self._calib_event.clear()
                    self._calib_event.wait() 
                
                if self._calib_stop_event.is_set(): 
                    return

            # 输出汇总数据
            self._broadcast_log("--- 9点标定数据汇总 ---")
            info("--- 9-Point Calibration Data Summary ---", "ROBOT_DRIVER")
            
            # 使用AppConfigManager获取 workspace 目录
            try:
                from core.managers.app_config import AppConfigManager
                app_config = AppConfigManager()
                calib_file_path = app_config.workspace_dir / "calibration_data.txt"
                
                with open(calib_file_path, 'w', encoding='utf-8') as f:
                    f.write("PointID, X, Y, Z, Rx, Ry, Rz\n")
                    for line in output_data_lines:
                        self._broadcast_log(line)
                        info(line, "ROBOT_DRIVER")
                        f.write(line + "\n")
                
                self._broadcast_log(f"标定数据已保存至: {calib_file_path}")
            except Exception as e:
                self._broadcast_log(f"保存标定文件失败: {e}")
                error(f"Failed to save calibration data: {e}", "ROBOT_DRIVER")

            # 完成，回原点
            self._broadcast_log("标定完成，正在返回中心点...")
            self.move_to(cx, cy, cz, crx, cry, crz)
            self._broadcast_log("已返回中心点。流程结束。")

        except Exception as e:
            error(f"Internal calibration error: {e}", "ROBOT_DRIVER")
            self._broadcast_log(f"标定异常中止: {str(e)}")

    def _wait_until_reached(self, target_pose, tolerance=2.0, timeout=15.0):
        """等待机器人到达目标位置"""
        start_time = time.time()
        tx, ty, tz = target_pose[0], target_pose[1], target_pose[2]
        
        while time.time() - start_time < timeout:
            if self._calib_stop_event.is_set():
                return False
                
            curr = self.get_position()
            if not curr:
                time.sleep(0.1)
                continue
                
            cx, cy, cz = curr[0], curr[1], curr[2]
            
            dist = math.sqrt((cx-tx)**2 + (cy-ty)**2 + (cz-tz)**2)
            if dist < tolerance:
                # 简单的稳定性检查（可选）
                time.sleep(0.5)
                return True
                
            time.sleep(0.1)
            
        return False

    def _broadcast_log(self, message):
        """辅助发送日志到回调"""
        for callback in self.log_callbacks:
            try:
                callback("信息", f"[Elite] {message}")
            except:
                pass
        
    def confirm_calibration(self) -> bool:
        """确认下一步"""
        if self._calib_thread and self._calib_thread.is_alive():
            self._calib_event.set()
            info("User confirmed calibration step", "ROBOT_DRIVER")
            return True
        
        # 兼容旧逻辑 (虽然已废弃EXE)
        if self.calibration_process and self.calibration_process.poll() is None:
            try:
                if self.calibration_process.stdin:
                    self.calibration_process.stdin.write("\n")
                    self.calibration_process.stdin.flush()
                    return True
            except: 
                pass
                
        warning("No active calibration process to confirm", "ROBOT_DRIVER")
        return False

    def move_to(self, x: float, y: float, z: float,
                rx: float = 0, ry: float = 0, rz: float = 0) -> bool:
        """移动到指定位置"""
        info(f"Elite robot move_to: {x}, {y}, {z}", "ROBOT_DRIVER")

        # C++ Extension Move
        if self.controller and self.controller.is_connected():
            try:
                # move_to(x, y, z, rx, ry, rz) -> bool (mm, deg)
                return self.controller.move_to(x, y, z, rx, ry, rz)
            except Exception as e:
                error(f"C++ move_to error: {e}", "ROBOT_DRIVER")
        
        # 使用全局速度
        speed = getattr(self, 'global_speed_ratio', 0.5)
        
        # 单位转换: mm -> m, deg -> rad
        target_pose = f"p[{x/1000.0}, {y/1000.0}, {z/1000.0}, {rx/57.29578}, {ry/57.29578}, {rz/57.29578}]"
        
        # movel(pose, a=0.5, v=speed)
        script = f"movel({target_pose}, a=0.5, v={speed})"
        
        if self.sdk and self.driver_handle:
            try:
                return self.sdk.send_script(self.driver_handle, script)
            except Exception as e:
                error(f"SDK send_script failed: {e}", "ROBOT_DRIVER")
        
        return self.send_script(script)

    def get_position(self) -> Optional[Tuple[float, float, float, float, float, float]]:
        """获取当前位置"""
        # 1. C++ Extension GetPosition
        if self.controller and self.controller.is_connected():
            try:
                # get_position() -> [x, y, z, rx, ry, rz] (mm, deg)
                pos = self.controller.get_position()
                if pos and len(pos) >= 6:
                    self.last_position = (pos[0], pos[1], pos[2], pos[3], pos[4], pos[5])
                    return self.last_position
            except Exception as e:
                # pass to fallback
                pass

        # 优先尝试使用SDK获取位置
        if self.sdk and self.driver_handle:
            try:
                pose = self.sdk.get_pose(self.driver_handle)
                if pose and len(pose) >= 6:
                    # SDK返回的是m和rad，需要转换
                    x, y, z = pose[0] * 1000.0, pose[1] * 1000.0, pose[2] * 1000.0
                    rx, ry, rz = pose[3] * 57.29578, pose[4] * 57.29578, pose[5] * 57.29578
                    
                    # 简单的异常值过滤
                    if abs(x) > 10000 or abs(y) > 10000 or abs(z) > 10000:
                        # warning(f"Abnormal pose detected from SDK: {x}, {y}, {z}", "ROBOT_DRIVER")
                        return self.last_position if hasattr(self, 'last_position') else (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                        
                    self.last_position = (x, y, z, rx, ry, rz)
                    return (x, y, z, rx, ry, rz)
            except Exception as e:
                # 避免高频报错
                pass

        # Fallback: Use Primary Port (30001) if available
        # Note: self.primary_socket might be closed if not handled correctly in connect()
        # We should try to reconnect if it's missing or closed
        if not hasattr(self, 'primary_socket') or self.primary_socket.fileno() == -1:
             try:
                self.primary_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.primary_socket.settimeout(0.2)
                self.primary_socket.connect((self.robot_ip, 30001))
             except:
                pass

        if hasattr(self, 'primary_socket') and self.primary_socket:
            try:
                # Clear buffer to get fresh data
                self.primary_socket.settimeout(0.001)
                try:
                    while self.primary_socket.recv(4096): pass
                except:
                    pass
                
                # Read new packet
                self.primary_socket.settimeout(0.2)
                # The packet size is large, read enough bytes
                data = self.primary_socket.recv(2048)
                
                if len(data) > 458: # Ensure we have enough data for offset 410 + 48 bytes
                    # Offset 410 is where TCP pose starts
                    offset = 410
                    pose_data = data[offset:offset+48]
                    if len(pose_data) == 48:
                        # Unpack 6 doubles (Big Endian)
                        vals = struct.unpack('>6d', pose_data)
                        
                        x, y, z = vals[0] * 1000.0, vals[1] * 1000.0, vals[2] * 1000.0
                        rx, ry, rz = vals[3] * 57.29578, vals[4] * 57.29578, vals[5] * 57.29578
                        return (x, y, z, rx, ry, rz)
            except Exception as e:
                pass

        if not self.connected or not hasattr(self, 'dashboard_socket'):
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        try:
            # 清空接收缓冲区，防止读取到旧数据
            self.dashboard_socket.settimeout(0.01)
            try:
                while self.dashboard_socket.recv(1024): pass
            except:
                pass

            self.dashboard_socket.settimeout(0.5)
            # 尝试发送获取位姿命令
            # 注意：如果Dashboard不支持此命令，可能需要使用RTSI端口(30004)解析二进制数据
            # 这里先尝试Dashboard文本命令
            self.dashboard_socket.sendall(b"get_actual_tcp_pose\n")
            response = self.dashboard_socket.recv(1024).decode('utf-8').strip()
            
            # 如果命令被拒绝，尝试另一种格式
            if 'Unknown' in response:
                 self.dashboard_socket.sendall(b"GetActualTCPPose\n")
                 response = self.dashboard_socket.recv(1024).decode('utf-8').strip()

            if response and 'Unknown' not in response:
                # 假设返回格式为 p[x, y, z, rx, ry, rz] 或类似 CSV
                # 示例: p[0.1, 0.2, 0.3, 0.1, 0.0, 0.0] (单位通常是 m 和 rad)
                clean_resp = response.replace('p[', '').replace('[', '').replace(']', '').replace(';', '')
                parts = clean_resp.split(',')
                
                if len(parts) >= 6:
                    vals = [float(x) for x in parts[:6]]
                    # 转换为 mm 和 度 (通常协议返回的是 m 和 rad)
                    x, y, z = vals[0] * 1000.0, vals[1] * 1000.0, vals[2] * 1000.0
                    rx, ry, rz = vals[3] * 57.29578, vals[4] * 57.29578, vals[5] * 57.29578
                    
                    # 打印调试信息，类似C++输出
                    # info(f">> Robot TCP: {vals}", "ROBOT_DRIVER")
                    info(f">> Robot TCP: {vals}", "ROBOT_DRIVER")
                    return (x, y, z, rx, ry, rz)
                    
        except Exception as e:
            # 避免高频报错污染日志
            pass
            
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def home(self) -> bool:
        """回到原点"""
        info("Elite robot home", "ROBOT_DRIVER")
        # 定义一个安全的原点位置 (关节角，单位：弧度)
        # 假设所有关节归零是安全位置，或者根据实际情况调整
        # movej([0, -1.57, 0, -1.57, 0, 0], a=1.4, v=1.05)
        # 这里使用一个常见的垂直姿态作为Home点
        home_joint_pos = "[0, -1.57, 0, -1.57, 0, 0]" 
        script = f"movej({home_joint_pos}, a=0.5, v=0.5)"
        
        if self.sdk and self.driver_handle:
            try:
                return self.sdk.send_script(self.driver_handle, script)
            except Exception as e:
                error(f"SDK send_script failed: {e}", "ROBOT_DRIVER")
        
        return self.send_script(script)

    def emergency_stop(self) -> bool:
        """紧急停止"""
        info("Elite robot emergency stop", "ROBOT_DRIVER")
        self.state = RobotState.ERROR
        
        # 发送停止脚本命令
        # stopj(a) 减速停止，a是减速度
        script = "stopj(2.0)"
        
        success = False
        if self.sdk and self.driver_handle:
            try:
                success = self.sdk.send_script(self.driver_handle, script)
            except:
                pass
        
        if not success:
            success = self.send_script(script)
            
        # 也可以尝试通过Dashboard停止
        if hasattr(self, 'dashboard_socket'):
            try:
                self.dashboard_socket.sendall(b"stop\n")
            except:
                pass
                
        return True

    def set_speed(self, speed: float) -> bool:
        """设置全局速度比例 (0-100)"""
        # 1. 保存内部速度比例，供move_to等方法使用
        self.global_speed_ratio = max(0.01, min(1.0, speed / 100.0))
        info(f"Set global speed ratio to {self.global_speed_ratio}", "ROBOT_DRIVER")
        
        # C++ Extension Speed
        if self.controller and self.controller.is_connected():
            try:
                self.controller.set_speed(float(speed))
            except Exception as e:
                error(f"C++ set_speed error: {e}", "ROBOT_DRIVER")

        # 2. 尝试通过Dashboard设置示教器速度滑块 (0-100)
        # Elite Dashboard命令: speed <value> (0-100)
        if hasattr(self, 'dashboard_socket'):
            try:
                # 检查socket是否已关闭
                if self.dashboard_socket.fileno() == -1:
                    # 尝试重新连接
                    info("Dashboard socket closed, reconnecting...", "ROBOT_DRIVER")
                    self.dashboard_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.dashboard_socket.settimeout(2.0)
                    self.dashboard_socket.connect((self.robot_ip, 29999))
                    # 接收欢迎消息
                    try: self.dashboard_socket.recv(1024) 
                    except: pass

                # 发送 speed 命令
                # 根据错误提示: speed [  | -set <speed value> | -h]
                cmd = f"speed -set {int(speed)}\n"
                self.dashboard_socket.sendall(cmd.encode('utf-8'))
                
                # 读取响应 (非阻塞尝试)
                self.dashboard_socket.settimeout(0.2)
                try:
                    resp = self.dashboard_socket.recv(1024).decode('utf-8').strip()
                    info(f"Dashboard speed response: {resp}", "ROBOT_DRIVER")
                except:
                    pass
                self.dashboard_socket.settimeout(10.0) # 恢复超时
            except Exception as e:
                warning(f"Failed to set dashboard speed: {e}", "ROBOT_DRIVER")
                
        return True

    def move_circular(self, center: Any, radius: float, angle: float, speed: float) -> bool:
        """圆弧移动"""
        return True

    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> bool:
        """设置工件坐标系"""
        return True

    def set_work_coordinate_system(self, wcs: Dict[str, Any]) -> bool:
        """设置工件坐标系"""
        return True

    def get_work_coordinate_system(self) -> Optional[Dict[str, Any]]:
        """获取工件坐标系"""
        return {}

    def toggle_work_coordinate_system(self) -> bool:
        """切换工件坐标系"""
        return True

    # ========== 实时控制相关方法 ==========
    def start_jogging(self, axis: str) -> bool:
        """开始点动运动"""
        return True

    def stop_jogging(self) -> bool:
        """停止点动运动"""
        return True

    def jog_move(self, axis: str, speed: float, distance: float) -> bool:
        """点动移动指定轴"""
        
        # C++ Extension Jog
        if self.controller and self.controller.is_connected():
            try:
                # jog(axis_idx, direction, distance_mm)
                # axis: 0=X, 1=Y, 2=Z, 3=RX...
                # Current implementation supports X/Y/Z translation in Base Frame
                axis_map = {'X': 0, 'Y': 1, 'Z': 2}
                if axis in axis_map:
                    axis_idx = axis_map[axis]
                    direction = 1 if distance >= 0 else -1
                    dist_abs = abs(distance)
                    
                    # Update speed if needed
                    self.controller.set_speed(speed)
                    
                    return self.controller.jog(axis_idx, direction, dist_abs)
            except Exception as e:
                error(f"C++ jog error: {e}", "ROBOT_DRIVER")

        # distance单位是mm，转换为m
        dist_m = distance / 1000.0
        
        dx, dy, dz = 0.0, 0.0, 0.0
        if axis == 'X': dx = dist_m
        elif axis == 'Y': dy = dist_m
        elif axis == 'Z': dz = dist_m
        
        # 构建Elite脚本命令 (类似于URScript)
        # 使用pose_add进行基座坐标系下的相对移动 (pose_trans是工具坐标系)
        # movel(pose_add(get_actual_tcp_pose(), p[dx, dy, dz, 0, 0, 0]), a=0.5, v=speed_m_s)
        
        # 速度转换: speed是百分比(0-100)，假设最大速度为1.0 m/s
        speed_val = max(0.01, min(1.0, speed / 100.0))
        
        # 直接嵌套调用，避免变量定义问题
        # 注意：Elite脚本中p[...]可能被识别为函数调用，直接使用列表[...]即可
        script = f"movel(pose_add(get_actual_tcp_pose(), [{dx}, {dy}, {dz}, 0, 0, 0]), a=0.5, v={speed_val})"
        
        info(f"Sending jog command: {axis} {distance}mm", "ROBOT_DRIVER")
        
        # 优先使用SDK发送脚本
        if self.sdk and self.driver_handle:
            try:
                return self.sdk.send_script(self.driver_handle, script)
            except Exception as e:
                error(f"SDK send_script failed: {e}", "ROBOT_DRIVER")
                # Fallback to raw socket
        
        return self.send_script(script)

    def set_motion_mode(self, mode: MotionMode) -> bool:
        """设置运动模式"""
        self.motion_mode = mode
        return True

    def get_motion_mode(self) -> Optional[MotionMode]:
        """获取当前运动模式"""
        return self.motion_mode

    def get_state(self) -> RobotState:
        """获取机器人当前状态"""
        return self.state

    def is_moving(self) -> bool:
        """检查是否正在运动"""
        return False

    # ========== 路径记录相关方法 ==========
    def start_path_recording(self, path_name: str) -> bool:
        """开始记录路径"""
        return True

    def stop_path_recording(self) -> bool:
        """停止记录路径"""
        return True

    def add_path_point(self, point: Optional[PathPoint] = None) -> bool:
        """添加路径点"""
        return True

    def get_recorded_path(self) -> Optional[RobotPath]:
        """获取当前记录的路径"""
        return None

    def clear_recorded_path(self) -> bool:
        """清空当前记录的路径"""
        return True

    def play_path(self, path: RobotPath, loop_count: int = 1) -> bool:
        """播放路径"""
        return True

    def stop_path_playback(self) -> bool:
        """停止路径播放"""
        return True

    def is_path_playing(self) -> bool:
        """检查是否正在播放路径"""
        return False

    # ========== 高级控制功能 ==========
    def move_linear(self, start_pos: RobotPosition, end_pos: RobotPosition, speed: float) -> bool:
        """线性移动"""
        return True

