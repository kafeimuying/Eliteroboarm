#!/usr/bin/env python3
"""
Canvas Launcher - 简化版启动器
专门用于启动画布模式
"""

import sys
import os
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.core.managers.app_config import AppConfigManager
from PyQt6.QtWidgets import QApplication

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent
# 添加src目录
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

# 添加C++扩展库支持 (elite_ext, vision_cpp_ext)
CPP_EXT_DIR = PROJECT_ROOT / "cpp_extensions" / "extensions" / "Release"
if CPP_EXT_DIR.exists():
    # 允许Python导入pyd模块
    sys.path.append(str(CPP_EXT_DIR))
    # 允许Windows加载同目录下的依赖DLL (如 elite-cs-series-sdk.dll)
    if hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(str(CPP_EXT_DIR))
        except Exception as e:
            print(f"Warning: Failed to add DLL directory {CPP_EXT_DIR}: {e}")

from src.core.managers.log_manager import LogManager, LogCategory, info, debug, warning, error


class ApplicationLauncher:
    """应用启动器 - VMC v2.0"""

    def __init__(self):
        self.app = None

    def setup_environment(self):
        """设置环境"""
        # 设置工作目录
        os.chdir(PROJECT_ROOT)

        # 使用AppConfigManager创建workspace相关目录
        try:
            from src.core.managers.app_config import AppConfigManager
            AppConfigManager()
            # AppConfigManager已经自动创建了所有必要的workspace目录
            debug("使用AppConfigManager创建workspace目录", "LAUNCHER", LogCategory.SYSTEM)
        except Exception as e:
            # fallback: 创建基本的workspace目录
            warning(f"无法使用AppConfigManager: {e}", "LAUNCHER", LogCategory.SYSTEM)
            from pathlib import Path
            basic_directories = ["workspace", "workspace/logs", "workspace/data", "workspace/config"]
            for directory in basic_directories:
                Path(directory).mkdir(parents=True, exist_ok=True)

    def launch_canvas_mode(self, args) -> int:
        """启动画布模式 - 使用完整的对话框功能，底层使用新的canvas模块"""
        try:
            info("启动LaminarVision画布模式", "LAUNCHER")

            # 设置调试模式
            if args.debug:
                from src.core.managers.debug_manager import enable_debug
                enable_debug()
                info("调试模式已启用", "LAUNCHER")

            # 创建应用
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("Vision Canvas")
            self.app.setApplicationVersion("2.2.0")
            self.app.setStyle('Fusion')

            # 导入完整的对话框类
            from src.ui_libs.vision_canvas.canvas.canvas_dialog import LarminarVisionAlgorithmChainDialog

            if args.input:
                info("自动生成测试图像", "LAUNCHER")
                test_image = self._generate_test_image()

            # 创建完整的LarminarVision对话框
            # 对话框内部会自动创建算法管理器并加载所有组件
            dialog = LarminarVisionAlgorithmChainDialog()

            # 如果需要自动生成输入图像
            if args.input and 'test_image' in locals():
                dialog.set_input_image(test_image)

            # 显示对话框
            dialog.show()

            info("LarminarVision画布模式初始化完成", "LAUNCHER")

            # 运行应用
            exit_code = self.app.exec()

            return exit_code

        except Exception as e:
            error(f"画布模式启动失败: {e}", "LAUNCHER")
            import traceback
            traceback.print_exc()
            return 1

    def launch_vision_robot_mode(self, args) -> int:
        """启动视觉-机器人协作模式"""
        try:
            info("启动视觉-机器人协作系统", "LAUNCHER")

            # 设置调试模式
            if args.debug:
                from src.core.managers.debug_manager import enable_debug
                enable_debug()
                info("调试模式已启用", "LAUNCHER")

            # 创建应用
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("Vision Robot Collaboration System")
            self.app.setApplicationVersion("1.0.0")
            self.app.setStyle('Fusion')

            # 导入视觉-机器人对话框
            from src.ui_libs.vision_robot_widget import VisionRobotDialog

            # 创建视觉-机器人协作对话框
            dialog = VisionRobotDialog()

            # 显示对话框
            dialog.show()

            info("视觉-机器人协作系统初始化完成", "LAUNCHER")

            # 运行应用
            exit_code = self.app.exec()

            return exit_code

        except Exception as e:
            error(f"视觉-机器人协作系统启动失败: {e}", "LAUNCHER")
            import traceback
            traceback.print_exc()
            return 1

    
    def launch_hardware_mode(self, args) -> int:
        """启动硬件控制系统"""
        try:
            info("启动硬件控制系统", "LAUNCHER")

            # 设置调试模式
            if args.debug:
                from src.core.managers.debug_manager import enable_debug
                enable_debug()
                info("调试模式已启用", "LAUNCHER")

            # 直接调用 hardware_launcher.py 的 main 函数
            import sys
            from pathlib import Path

            # 添加 src 目录到路径
            project_root = Path(__file__).parent
            src_path = project_root / "src"
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))

            from app.hardware_launcher import main as hardware_main

            # 调用硬件启动器的 main 函数
            return hardware_main(debug_mode=args.debug)

        except Exception as e:
            error(f"硬件控制系统启动失败: {e}", "LAUNCHER")
            import traceback
            traceback.print_exc()
            return 1

    def _generate_test_image(self):
        """生成测试图像 - 使用统一的工具函数"""
        from src.utils.image_utils import create_test_image
        test_image = create_test_image(640, 480, 'circles')
        debug(f"已生成测试图像: {test_image.shape}", "LAUNCHER")
        return test_image


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="LarminarVision 智能算法调试系统 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🎯 主要功能模式:

1. 画布算法调试模式:
   python launcher.py --canvas                    # 启动画布算法调试对话框
   python launcher.py --canvas --input              # 启动画布模式并自动生成测试图像

2. 视觉-机器人协作模式:
   python launcher.py --vision-robot              # 启动视觉-机器人协作系统
   python launcher.py --vision-robot --debug        # 启动视觉-机器人协作系统（调试模式）

3. 🆕 硬件控制系统:
   python launcher.py --hardware                  # 启动硬件控制系统
   python launcher.py --hardware --debug          # 启动硬件控制系统（调试模式）

🔧 调试选项:
   --debug             # 启用详细调试输出
   --log-level LEVEL # 设置日志级别 (DEBUG/INFO/WARNING/ERROR)

📋 版本信息:
   --version           # 显示版本号

📚 使用示例:
   # 启动硬件控制系统
   python launcher.py --hardware --debug

   # 启动画布模式并生成测试图像
   python launcher.py --canvas --input

   # 启动视觉-机器人协作模式
   python launcher.py --vision-robot

注意事项:
- 每次只能选择一个模式启动
- --input 参数需要与 --canvas 参数一起使用
- --debug 参数会输出详细的调试信息
        """
    )

    parser.add_argument(
        '--canvas',
        action='store_true',
        help='启动画布模式'
    )

    parser.add_argument(
        '--vision-robot',
        action='store_true',
        help='启动视觉-机器人协作系统'
    )

    parser.add_argument(
        '--hardware',
        action='store_true',
        help='启动硬件控制系统'
    )

    parser.add_argument(
        '--input',
        action='store_true',
        help='自动生成输入图像并运行（需与--canvas一起使用）'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='启用调试模式'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )

    parser.add_argument(
        '--version', '-v',
        action='version',
        version='LaminarVision 2.0.0'
    )

    return parser


def main():
    """主入口函数"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # log configuration
    # initial configuration
    config_manager = AppConfigManager()
    log_path = config_manager.logs_dir

    # 初始化日志
    LogManager.instance(logs_dir=str(log_path))

    # 验证参数组合
    if not args.canvas and not args.vision_robot and not args.hardware:
        error("错误: 必须使用 --canvas、--vision-robot 或 --hardware 参数启动系统", "LAUNCHER")
        return 1

    if args.input and not args.canvas:
        error("错误: --input 参数必须与 --canvas 参数一起使用", "LAUNCHER")
        return 1

    # 确保只能选择一个模式
    mode_count = sum([bool(args.canvas), bool(args.vision_robot), bool(args.hardware)])
    if mode_count > 1:
        error("错误: 只能选择一个模式启动系统", "LAUNCHER")
        return 1

    # 创建启动器
    launcher = ApplicationLauncher()

    # 设置环境
    launcher.setup_environment()

    # 启动对应模式
    try:
        if args.hardware:
            # 启动硬件控制系统 - 调用hardware_launcher.py
            exit_code = launcher.launch_hardware_mode(args)
        elif args.vision_robot:
            exit_code = launcher.launch_vision_robot_mode(args)
        else:  # args.canvas
            exit_code = launcher.launch_canvas_mode(args)
        return exit_code

    except KeyboardInterrupt:
        info('用户中断程序', "LAUNCHER")
        return 0
    except Exception as e:
        error(f"程序异常退出: {e}", "LAUNCHER")
        return 1


if __name__ == '__main__':
    sys.exit(main())