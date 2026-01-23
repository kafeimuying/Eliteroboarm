cmake_minimum_required(VERSION 3.12)
project(vision_cpp_ext)

# 设置C++标准 - Elite SDK需要C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 检测操作系统和架构
message(STATUS "System: ${CMAKE_SYSTEM_NAME}")
message(STATUS "Processor: ${CMAKE_SYSTEM_PROCESSOR}")

# 根据系统配置不同的设置
if(APPLE)
    message(STATUS "Configuring for macOS")
    # 设置目标架构为arm64
    set(CMAKE_OSX_ARCHITECTURES "arm64")
    
    # macOS使用conda/miniforge环境中的pybind11
    set(pybind11_DIR "/Users/annanshu/miniforge3/envs/calibrate/lib/python3.11/site-packages/pybind11/share/cmake/pybind11")
    
    # macOS使用Homebrew安装的OpenCV
    set(OpenCV_DIR "/opt/homebrew/Cellar/opencv/4.12.0_8/lib/cmake/opencv4")
    
    # macOS OpenCV包含路径
    include_directories("/opt/homebrew/Cellar/opencv/4.12.0_8/include/opencv4")
    
elseif(WIN32)
    message(STATUS "Configuring for Windows")
    
    # Windows/MSYS2配置
    if(MINGW)
        message(STATUS "Using MINGW/MSYS2")
        
        # 设置目标架构为x86_64
        set(CMAKE_SYSTEM_PROCESSOR "x86_64")
        
        # MSYS2环境下的pybind11路径（需要根据实际安装路径调整）
        set(pybind11_DIR "C:/Users/shuan/anaconda3/envs/calibrate/Lib/site-packages/pybind11/share/cmake/pybind11")
        
        # MSYS2下OpenCV的常见安装位置
        set(OpenCV_DIR "C:/msys64/mingw64/lib/cmake/opencv4")
        
        # MSYS2 OpenCV包含路径
        include_directories("C:/msys64/mingw64/include/opencv4")
        
        # 添加MSYS2的库路径
        link_directories("C:/msys64/mingw64/lib")
        
    else()
        # Visual Studio环境
        message(STATUS "Using Visual Studio")
        
        # Visual Studio下的OpenCV配置（假设使用vcpkg或自定义安装）
        if(DEFINED ENV{VCPKG_ROOT})
            set(CMAKE_TOOLCHAIN_FILE "$ENV{VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake")
        else()
            # 手动指定OpenCV路径
            set(OpenCV_DIR "C:/opencv/build")
            include_directories("C:/opencv/include")
        endif()
    endif()
endif()

# 查找Python和pybind11
# set(Python_EXECUTABLE "/Users/annanshu/miniforge3/envs/calibrate/bin/python") # Commented out hardcoded path
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# 如果没有通过上面的方式找到pybind11_DIR，尝试自动查找
if(NOT pybind11_DIR)
    find_package(pybind11 CONFIG REQUIRED)
else()
    find_package(pybind11 CONFIG REQUIRED HINTS ${pybind11_DIR})
endif()

# 查找OpenCV
if(OpenCV_DIR)
    find_package(OpenCV REQUIRED HINTS ${OpenCV_DIR})
else()
    find_package(OpenCV REQUIRED)
endif()

# 显示找到的版本信息
message(STATUS "Python version: ${Python_VERSION}")
message(STATUS "OpenCV version: ${OpenCV_VERSION}")
message(STATUS "pybind11 version: ${pybind11_VERSION}")


# 包含目录
include_directories(${OpenCV_INCLUDE_DIRS})

# 创建pybind11模块
pybind11_add_module(vision_cpp_ext vision_cpp_ext.cpp)

# 链接OpenCV库
target_link_libraries(vision_cpp_ext PRIVATE ${OpenCV_LIBS})

# Elite SDK Configuration
set(ELITE_SDK_INCLUDE_DIR "W:/CATL/Elite/Elite-main/Elite-main/include")
set(ELITE_SDK_LIB_DIR "W:/CATL/Elite/Elite-main/Elite-main/Release")
set(ELITE_SDK_LIB "elite-cs-series-sdk")

include_directories(${ELITE_SDK_INCLUDE_DIR})
link_directories(${ELITE_SDK_LIB_DIR})

# Elite Robot Extension
pybind11_add_module(elite_ext elite_ext.cpp)
target_link_libraries(elite_ext PRIVATE ${ELITE_SDK_LIB})

# 根据系统设置不同的编译选项
if(APPLE)
    # macOS特定的编译选项
    target_compile_options(vision_cpp_ext PRIVATE -O3)
    
    # macOS的库路径
    link_directories("/opt/homebrew/lib")
    
elseif(WIN32 AND MINGW)
    # MSYS2/MinGW特定的编译选项
    if(WINDOWS_ARCH STREQUAL "x64")
        target_compile_options(vision_cpp_ext PRIVATE -O3 -march=x86-64)
        message(STATUS "Compiling for x86_64 Windows")
    else()
        target_compile_options(vision_cpp_ext PRIVATE -O3 -march=i686)
        message(STATUS "Compiling for x86 Windows")
    endif()
    
    # 添加Windows特定的链接选项
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        target_link_options(vision_cpp_ext PRIVATE -static-libgcc -static-libstdc++)
    endif()
    
elseif(WIN32)
    # Visual Studio特定的编译选项
    target_compile_options(vision_cpp_ext PRIVATE /O2)
endif()

# 设置输出目录
set_target_properties(vision_cpp_ext PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/extensions
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/extensions  # Windows需要
)

set_target_properties(elite_ext PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/extensions
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/extensions
)

# 平台特定的后处理
if(WIN32)
    # Windows下可能需要复制依赖的DLL
    # 这里可以添加自定义命令来复制必要的DLL文件
endif()

# 输出最终配置信息
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ compiler: ${CMAKE_CXX_COMPILER}")
message(STATUS "Output directory: ${CMAKE_CURRENT_SOURCE_DIR}/extensions")