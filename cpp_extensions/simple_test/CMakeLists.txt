cmake_minimum_required(VERSION 3.12)
project(simple_ext)

# 设置C++标准
set(CMAKE_CXX_STANDARD 14)

# 设置目标架构为arm64
set(CMAKE_OSX_ARCHITECTURES "arm64")

# 设置pybind11的路径
set(pybind11_DIR "/Users/annanshu/opt/anaconda3/envs/calibrate/lib/python3.11/site-packages/pybind11/share/cmake/pybind11")

# 查找Python和pybind11
find_package(Python COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

# 创建pybind11模块
pybind11_add_module(simple_ext simple_ext.cpp)

# 设置输出目录为当前目录
set_target_properties(simple_ext PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
)