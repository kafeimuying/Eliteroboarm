# RealSense深度相机集成说明

## 概述

已成功将Intel RealSense深度相机集成到系统中，支持与大恒相机相同的所有基本功能。

## 已完成的工作

### 1. 创建RealSense相机驱动 (src/drivers/camera/realsense.py)

- 实现了完整的ICamera接口
- 支持彩色图像和深度图像采集
- 支持实时预览和单帧拍照
- 支持曝光和增益调整
- 提供额外的深度图和点云获取功能

### 2. 注册驱动模块

- 在 `src/drivers/camera/__init__.py` 中添加了RealSenseCamera导入
- 在 `src/core/services/camera_factory.py` 中添加了RealSense相机的创建逻辑
- 支持USB和网络连接类型

### 3. 配置文件更新

- 在 `config/hardware_config.json` 中添加了RealSense相机示例配置
- 配置ID: `camera_realsense_01`
- 配置名称: `RealSense深度相机`

### 4. 依赖安装

- 在 `requirements.txt` 中添加了 `pyrealsense2>=2.50.0`
- 已在roboarm环境中安装pyrealsense2 (版本 2.56.5.9235)

## 功能支持矩阵

| 功能       | 大恒相机 | RealSense相机 | 说明                  |
| ---------- | -------- | ------------- | --------------------- |
| 双击连接   | ✓        | ✓             | 支持                  |
| 开始预览   | ✓        | ✓             | 支持彩色图像实时预览  |
| 停止预览   | ✓        | ✓             | 支持                  |
| 拍照       | ✓        | ✓             | 支持单帧采集          |
| 自动对焦   | ✓        | ✗             | RealSense使用固定焦距 |
| 曝光调整   | ✓        | ✓             | 支持                  |
| 增益调整   | ✓        | ✓             | 支持                  |
| 深度图采集 | ✗        | ✓             | RealSense专有功能     |
| 点云数据   | ✗        | ✓             | RealSense专有功能     |

## 使用方法

### 1. 在相机管理界面连接RealSense相机

1. 启动应用程序
2. 打开"相机管理"界面
3. 在相机列表中找到"RealSense深度相机"
4. 双击相机名称或选中后点击"连接"按钮

### 2. 实时预览

连接成功后：

1. 点击"开始预览"按钮
2. 相机画面将显示在预览区域
3. 点击"停止预览"停止实时预览

### 3. 拍照

1. 确保相机已连接
2. 点击"拍照"按钮
3. 图像将被捕获并保存

### 4. 参数调整

在相机参数面板中可以调整：

- 曝光时间
- 增益
- 其他相机参数

## 配置说明

### 基本配置参数

```json
{
  "id": "camera_realsense_01",
  "name": "RealSense深度相机",
  "brand": "realsense",
  "connection_type": "usb",
  "width": 640,
  "height": 480,
  "fps": 30,
  "enable_depth": true,
  "depth_width": 640,
  "depth_height": 480
}
```

### 可选参数

- **serial_number**: 相机序列号（用于区分多个RealSense相机）
- **width**: 彩色图像宽度（默认640）
- **height**: 彩色图像高度（默认480）
- **fps**: 帧率（默认30）
- **enable_depth**: 是否启用深度流（默认true）
- **depth_width**: 深度图像宽度（默认640）
- **depth_height**: 深度图像高度（默认480）

### 支持的分辨率

常见RealSense型号支持的分辨率：

- 640x480 @ 30/60 fps
- 1280x720 @ 30 fps
- 1920x1080 @ 30 fps

## 多相机配置

如果需要使用多个RealSense相机，在配置中指定不同的序列号：

```json
{
  "id": "camera_realsense_02",
  "name": "RealSense相机2",
  "brand": "realsense",
  "connection_type": "usb",
  "serial_number": "123456789",
  ...
}
```

## 注意事项

1. **自动对焦**: RealSense相机使用固定焦距，不支持自动对焦功能。点击"自动对焦"按钮不会产生效果。

2. **深度功能**: RealSense相机提供额外的深度图像和点云数据功能，这些是大恒相机不具备的。

3. **USB连接**: 建议使用USB 3.0或更高版本的接口以获得最佳性能。

4. **驱动要求**: 需要安装pyrealsense2 SDK（已在requirements.txt中包含）。

5. **多相机使用**: 使用多个RealSense相机时，系统能够正确识别，但需要确保USB带宽足够。

## 测试验证

运行集成测试脚本验证安装：

```bash
conda activate roboarm
python test_realsense_integration.py
```

所有测试应该通过，输出类似：

```
通过: 5/5
✓ 所有测试通过！RealSense相机驱动集成成功！
```

## 故障排除

### 问题1: 无法连接相机

- 确认RealSense相机已通过USB连接到计算机
- 确认pyrealsense2已正确安装
- 检查USB接口是否正常工作

### 问题2: 预览画面卡顿

- 尝试降低分辨率或帧率
- 确认使用USB 3.0接口
- 检查系统资源使用情况

### 问题3: 找不到相机

- 确认相机已开机并连接
- 如果使用多个相机，确认配置了正确的序列号
- 检查Windows设备管理器中相机是否被正确识别

## 技术支持

如有问题，请参考：

- Intel RealSense SDK文档: https://github.com/IntelRealSense/librealsense
- pyrealsense2文档: https://pypi.org/project/pyrealsense2/

## 更新日志

### 2026-02-06

- ✓ 创建RealSense相机驱动类
- ✓ 在drivers/**init**.py中注册RealSense相机
- ✓ 在CameraFactory中添加RealSense支持
- ✓ 更新hardware_config.json添加示例配置
- ✓ 添加pyrealsense2依赖
- ✓ 完成集成测试验证
