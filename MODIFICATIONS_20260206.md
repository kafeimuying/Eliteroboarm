# 修改说明文档

## 日期：2026-02-06

## 已完成的修改

### ✅ 1. 拍照文件名去除中文

**修改文件**：`src/ui_libs/hardware_widget/camera/camera_control.py`

**修改内容**：

- 原来：`filename = f"{camera_name}_{timestamp}.jpg"`（使用相机名称，可能包含中文）
- 修改后：`filename = f"camera_{camera_id}_{timestamp}.jpg"`（使用相机ID，纯英文数字）

**效果**：

- 修改前：`RealSense深度相机_20260206_150530.jpg`
- 修改后：`camera_realsense_01_20260206_150530.jpg`

---

### ✅ 2. 3D标定棱台尺寸参数最小值修改为0

**修改文件**：`src/ui_libs/hardware_widget/robotic_arm/robot_control.py`

**修改内容**：
为三个尺寸参数都添加了 `.setMinimum(0.0)`：

- 底面边长：最小值 0 mm
- 顶面边长：最小值 0 mm
- 总高度：最小值 0 mm

**效果**：
用户现在可以在3D标定设置界面中将参数设置为0，而不是之前的默认最小值。

---

### ✅ 3. 四棱台层数增加6层选项

**修改文件**：`src/ui_libs/hardware_widget/robotic_arm/robot_control.py`

**修改内容**：

- 原来：`layer_spin.setRange(2, 5)`（只能选择2-5层）
- 修改后：`layer_spin.setRange(2, 6)`（可以选择2-6层）

**6层拍照点位逻辑**：
根据C++扩展代码（`cpp_extensions/elite_ext.cpp`）的实现：

- 每层生成4个角点（棱台的四个顶点）
- 6层总共生成 6 × 4 = 24个拍照点位
- 点位分布：从底层到顶层，每层按照四棱台的大小比例分配

---

### ✅ 4. RealSense深度图自动保存功能

**修改文件**：`src/ui_libs/hardware_widget/camera/camera_control.py`

**新增功能**：
当使用RealSense相机拍照时，系统会**自动保存3个文件**：

1. **彩色图像**：`camera_{camera_id}_{timestamp}.jpg`
   - 标准的彩色照片（BGR格式）
2. **深度图原始数据**：`camera_{camera_id}_{timestamp}_depth.png`
   - 16位PNG格式
   - 保存原始深度值（单位：毫米）
   - 可用于精确的深度测量和3D重建

3. **深度图可视化**：`camera_{camera_id}_{timestamp}_depth_vis.jpg`
   - 伪彩色显示（JET色图）
   - 方便人眼查看深度信息
   - 红色表示近处，蓝色表示远处

**效果示例**：

```
拍照成功
彩色图像已保存到: workspace/captures/camera_realsense_01_20260206_150530.jpg
分辨率: 640x480
文件大小: 123456 bytes

深度图已保存:
- 原始数据: camera_realsense_01_20260206_150530_depth.png
- 可视化图: camera_realsense_01_20260206_150530_depth_vis.jpg
```

**注意**：

- 此功能仅对RealSense相机有效
- 大恒相机等普通相机不受影响，仍然只保存彩色图像
- 深度图保存失败不会影响彩色图的保存

---

## 使用说明

### 拍照功能

1. 连接RealSense相机
2. 点击"拍照"按钮
3. 系统自动保存彩色图和深度图（共3个文件）

### 深度图使用

深度图的原始数据（`_depth.png`）可以用Python读取：

```python
import cv2
import numpy as np

# 读取深度图
depth_image = cv2.imread('camera_realsense_01_20260206_150530_depth.png', cv2.IMREAD_UNCHANGED)

# 获取某个像素的深度值（单位：毫米）
depth_mm = depth_image[y, x]

# 转换为米
depth_m = depth_mm / 1000.0

# 创建点云
# ... 使用相机内参进行3D坐标计算
```

### 3D标定功能

1. 点击"执行3D标定"按钮
2. 在弹出的对话框中：
   - 选择层数：2-6层（新增6层选项）
   - 设置尺寸参数：最小值现在是0 mm（可以设置为0）
   - 选择生成方向：Z+, Z-, X+, X-, Y+, Y-
3. 点击"OK"开始执行

---

## 技术细节

### 文件命名规则

- 使用相机ID而不是相机名称
- 格式：`camera_{id}_{timestamp}{suffix}`
- 避免中文字符，兼容性更好

### 深度图格式

- 原始深度：16位单通道PNG（CV_16UC1）
- 可视化：8位三通道JPG（伪彩色）
- 深度值范围：0-65535（对应0-65.535米）

### 6层标定说明

C++代码会自动生成6层共24个点位，分布如下：

- 第1层（底层）：4个角点，边长 = base_width
- 第2层：4个角点，边长稍小
- ...
- 第6层（顶层）：4个角点，边长 = top_width

每层的高度和宽度按线性插值计算。

---

## 测试建议

1. **测试拍照功能**：
   - 连接RealSense相机
   - 拍照并检查生成的3个文件
   - 验证深度图可视化是否正确

2. **测试3D标定**：
   - 尝试设置参数为0
   - 选择6层标定
   - 验证点位生成是否正确

3. **测试普通相机**：
   - 连接大恒等其他相机
   - 验证拍照只生成彩色图（不生成深度图）
   - 验证文件名格式正确

---

## 已知限制

1. 深度图自动保存
   - 仅RealSense相机支持
   - 如果深度流未启用，深度图将为空

2. 6层标定逻辑
   - 当前C++实现是每层4个角点
   - 如需"侧棱等分点"逻辑，需要修改C++扩展

3. 文件命名
   - 依赖camera_id字段
   - 如果camera_id包含特殊字符，会被替换为下划线

---

## 后续改进建议

1. **可选的深度保存**：
   - 添加设置选项，让用户选择是否保存深度图
   - 避免不需要时占用额外存储空间

2. **深度图格式选项**：
   - 支持保存为NPY格式（NumPy数组）
   - 支持保存为PLY点云格式

3. **6层标定优化**：
   - 如需要，可以修改C++代码实现侧棱等分点逻辑
   - 或在Python层面生成自定义点位

---

更新时间：2026-02-06
