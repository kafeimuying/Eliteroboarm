# 高性能视觉算法C++扩展

本项目包含使用C++实现的高性能视觉算法扩展，通过pybind11与Python集成。

## 依赖项

- CMake (>= 3.12)
- OpenCV (>= 4.5.0)
- pybind11 (>= 2.6.0)
- Python (>= 3.7)

## 构建步骤

1. 安装依赖项：
   ```bash
   pip install -r requirements.txt
   ```

2. 安装CMake和OpenCV开发库：
   ```bash
   # Ubuntu/Debian
   sudo apt-get install cmake libopencv-dev
   
   # macOS with Homebrew
   brew install cmake opencv
   
   # Windows with vcpkg
   vcpkg install opencv4
   ```

3. 构建C++扩展：
   ```bash
   python build_cpp_extension.py
   ```

## 使用方法

构建完成后，算法会自动使用C++扩展（如果可用），否则会回退到Python实现。

## 算法列表

1. **高性能ROI抓边检测** - 在指定ROI区域内进行边缘检测和直线提取
2. **高性能模板匹配** - 在指定ROI区域内进行模板匹配

## 性能优势

C++扩展相比纯Python实现有显著的性能提升，特别是在处理大图像或复杂算法时。