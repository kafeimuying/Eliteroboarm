#!/usr/bin/env python3
"""
构建C++扩展的脚本
"""

import os
import subprocess
import sys
from pathlib import Path

def build_cpp_extension() -> bool:
    """构建C++扩展"""
    # 获取项目根目录 (Assumes script is in src/utils/)
    # Resolves to W:\CATL\Roboarm\src\utils\..\.. -> W:\CATL\Roboarm
    project_root: Path = Path(__file__).resolve().parent.parent.parent
    cpp_dir: Path = project_root / "cpp_extensions"
    build_dir: Path = cpp_dir / "build"
    
    # 创建构建目录
    build_dir.mkdir(exist_ok=True)
    
    # 进入构建目录并运行CMake
    try:
        # 配置项目
        print("Configuring C++ extension...")
        subprocess.run([
            "cmake", 
            "-S", str(cpp_dir),
            "-B", str(build_dir),
            "-DPYTHON_EXECUTABLE=" + sys.executable
        ], check=True, cwd=build_dir)
        
        # 构建项目
        print("Building C++ extension...")
        subprocess.run([
            "cmake", 
            "--build", str(build_dir),
            "--config", "Release"
        ], check=True, cwd=build_dir)
        
        print("C++ extension built successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error building C++ extension: {e}")
        return False
    except FileNotFoundError:
        print("Error: CMake not found. Please install CMake to build the C++ extension.")
        return False

def copy_extension_to_package():
    """将构建的扩展复制到Python包目录"""
    project_root = Path(__file__).parent
    build_dir = project_root / "cpp_extensions" / "build"
    package_dir = project_root / "cpp_extensions"
    
    # 查找构建的扩展文件
    extension_files = []
    
    # 方法1: 在extensions目录中查找.so文件（根据CMakeLists.txt设置）
    extensions_dir = project_root / "cpp_extensions" / "extensions"
    if extensions_dir.exists():
        for ext in ['*.so', '*.pyd', '*.dylib']:
            extension_files.extend(extensions_dir.glob(f"vision_cpp_ext{ext}"))
    
    # 方法2: 如果方法1没有找到，查找build目录下所有可能的扩展文件
    if not extension_files:
        for root, dirs, files in os.walk(build_dir):
            for file in files:
                if file.startswith("vision_cpp_ext") and file.endswith(('.so', '.pyd', '.dylib')):
                    file_path = Path(root) / file
                    # 确保不是目录
                    if file_path.is_file():
                        extension_files.append(file_path)
    
    if not extension_files:
        print("No extension file found!")
        print(f"Build directory contents:")
        for item in build_dir.rglob("*"):
            if item.is_file():
                print(f"  {item.relative_to(build_dir)}")
        return False
    
    # 选择第一个找到的扩展文件
    extension_file = extension_files[0]
    target_file = package_dir / "vision_cpp_ext.so"  # 标准化文件名
    
    print(f"Found extension file: {extension_file}")
    print(f"Copying to: {target_file}")
    
    try:
        import shutil
        shutil.copy2(extension_file, target_file)
        print(f"Extension copied to {target_file}")
        return True
    except Exception as e:
        print(f"Error copying extension: {e}")
        return False

def main():
    """主函数"""
    print("Building C++ extension for vision algorithms...")
    
    # 构建扩展
    if not build_cpp_extension():
        print("Failed to build C++ extension")
        return 1
    
    # 复制扩展到包目录
    if not copy_extension_to_package():
        print("Failed to copy extension to package directory")
        return 1
    
    print("C++ extension built and installed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())