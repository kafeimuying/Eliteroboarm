# LarminarVision - 视觉算法调试系统

## 📋 项目概述

LarminarVision 是一个基于 PyQt6 的视觉算法调试系统，专注于提供直观的画布式算法链开发和调试环境。项目采用模块化架构，支持算法拖拽、实时预览、参数调整等功能。

## 🎯 核心功能

- **画布式算法编辑器**：可视化拖拽算法节点，构建处理链
- **实时算法执行**：即时预览算法处理结果
- **参数动态调整**：实时修改算法参数并查看效果
- **多算法支持**：基础算子、高级算子、高性能算子、组合算法
- **图像处理工具**：ROI选择、结果对比、中间结果查看
- **算法组合保存**：支持将算法链保存为新的组合算法

## 🏗️ 项目架构

```
Lui-01/
├── launcher.py                    # 主启动器（简化版，仅支持画布模式）
├── core/                         # 核心模块（不可修改）
│   ├── vision_algorithms/         # 算法基础类
│   │   └── base/
│   │       ├── algorithm_base.py  # 算法基类和接口
│   │       └── combined_algorithm.py # 组合算法基类
│   ├── algorithm_registry.py      # 算法注册表
│   ├── log_manager.py             # 🔹 日志管理系统
│   ├── debug_manager.py           # 调试管理
│   └── types.py                   # 类型定义
├── algorithms/                    # 算法实现
│   ├── basic/                     # 基础算子
│   ├── advanced/                  # 高级算子
│   ├── performance/               # 高性能算子
│   └── composite/                 # 组合算法
├── ui/                           # 用户界面
│   ├── canvas/                   # 画布核心模块
│   │   ├── canvas_dialog.py       # 主画布对话框
│   │   ├── canvas.py              # 画布逻辑
│   │   ├── nodes.py               # 节点管理
│   │   ├── connections.py         # 连接线管理
│   │   └── image_dialog.py        # 图像显示对话框
│   ├── components/               # UI组件
│   │   ├── algorithm_panel.py     # 算法面板
│   │   ├── parameter_widget.py    # 参数控件
│   │   └── type_aware_parameter_widget.py # 类型感知参数控件
│   └── dialogs/                  # 对话框
│       ├── interactive_roi_selection.py # ROI选择
│       ├── intermediate_result_dialog.py # 中间结果
│       └── save_combined_algorithm_dialog.py # 保存组合算法
├── config/                       # 配置文件
├── data/                         # 数据目录
├── logs/                         # 日志目录
└── utils/                        # 工具函数
```

## 🔧 开发规范

### ⚠️ 核心模块使用规范

**绝对禁止修改 `core/` 目录中的任何文件！**

- `core/` 目录包含系统核心功能，**必须复用，如无特殊情况，不允许重新开发**
- 算法开发必须继承 `core/vision_algorithms/base/algorithm_base.py` 中的基类
- 使用 `core/algorithm_registry.py` 进行算法注册和管理
- 配置和类型定义使用 `core/types.py` 中的标准类型
- `core/utils`包含常用功能，**必须复用，如无特殊情况，不允许重新开发**

### 🔹 日志使用规范

**统一使用 `core/log_manager.py` 中的日志方法！**

```python
# 在文件顶部导入
from core.log_manager import info, debug, warning, error

# 使用日志方法
info("操作完成", "MODULE_NAME")
debug("调试信息", "MODULE_NAME")
warning("警告信息", "MODULE_NAME")
error("错误信息", "MODULE_NAME")

# 禁止使用 print() 语句
# ❌ 错误：print("信息")
# ✅ 正确：info("信息", "MODULE_NAME")
```

**日志级别说明：**
- `info()`：一般信息、操作完成状态
- `debug()`：调试信息、详细执行过程
- `warning()`：警告信息、可恢复的问题
- `error()`：错误信息、严重问题

### 📦 算法开发规范

#### 算法分类体系
- **一级分类 (category)**：基础算子、高级算子、高性能算子、组合算法
- **二级分类 (secondary_category)**：具体功能分类，如预处理、检测、分析等

#### 算法结构模板
```python
#!/usr/bin/env python3
"""
算法描述
"""

from core.vision_algorithms.base.algorithm_base import AlgorithmBase, AlgorithmInfo, AlgorithmResult, AlgorithmParameter
from core.types import ParameterType
import cv2
import numpy as np

class YourAlgorithm(AlgorithmBase):
    def get_algorithm_info(self):
        return AlgorithmInfo(
            name="your_algorithm_id",
            display_name="算法显示名称",
            description="算法功能描述",
            category="基础算子",  # 一级分类
            secondary_category="预处理",  # 二级分类
            version="1.0.0",
            author="YourName",
            tags=["标签1", "标签2"]
        )

    def get_parameters(self):
        return [
            AlgorithmParameter(
                name="param_name",
                param_type=ParameterType.INT,
                default_value=10,
                min_value=1,
                max_value=100,
                description="参数描述"
            )
        ]

    def process(self, input_image: np.ndarray) -> AlgorithmResult:
        try:
            # 获取参数
            param_value = self.get_parameter("param_name")

            # 算法处理逻辑
            output_image = your_processing_logic(input_image, param_value)

            return AlgorithmResult(
                success=True,
                output_image=output_image,
                processing_time=processing_time
            )
        except Exception as e:
            from core.log_manager import error
            error(f"算法执行失败: {e}", "YOUR_ALGORITHM")
            return AlgorithmResult(
                success=False,
                error_message=str(e)
            )
```

## 🚀 启动方式

### 命令行启动
```bash
# 启动画布模式
python launcher.py --canvas

# 启动画布模式并自动生成测试图像
python launcher.py --canvas --input

# 启动调试模式
python launcher.py --canvas --debug

# 设置日志级别
python launcher.py --canvas --log-level DEBUG

# 查看版本信息
python launcher.py --version
```

### 支持的参数
- `--canvas`：启动画布模式（必需）
- `--input`：自动生成测试图像
- `--debug`：启用调试模式
- `--log-level`：设置日志级别 (DEBUG/INFO/WARNING/ERROR)

## 🎨 用户界面

### 画布操作
- **拖拽算法**：从右侧算法面板拖拽算法到画布
- **连接节点**：点击端口并拖拽到目标端口建立连接
- **参数调整**：双击算法节点打开参数配置面板
- **执行算法**：点击执行按钮或按 F5 运行算法链
- **查看结果**：双击输出节点查看处理结果

### 节点类型
- **输入节点**：加载输入图像（蓝色）
- **算法节点**：执行具体算法处理（绿色）
- **输出节点**：显示最终结果（橙色）

### 快捷键
- `F5`：执行算法链
- `Ctrl+S`：保存算法配置
- `Ctrl+O`：加载算法配置
- `Delete`：删除选中节点

## 📊 算法分类

### 基础算子
- **预处理**：高斯模糊、阈值处理、形态学操作
- **边缘检测**：Canny边缘检测、Sobel算子
- **颜色空间**：RGB转换、HSV处理

### 高级算子
- **特征检测**：角点检测、斑点检测
- **图像分割**：阈值分割、区域生长
- **几何分析**：轮廓检测、形状分析
- **模板匹配**：模板匹配、特征匹配

### 高性能算子
- **并行处理**：多线程图像处理
- **GPU加速**：CUDA加速算法（可选）
- **内存优化**：大图像分块处理

### 组合算法
- **用户自定义**：用户创建的算法组合
- **预设组合**：常用的算法处理流程

## 🛠️ 开发工具

### 调试功能
- **中间结果查看**：查看算法链中任意节点的处理结果
- **参数实时调整**：动态修改参数并立即看到效果
- **性能监控**：显示算法执行时间和资源使用情况
- **错误诊断**：详细的错误信息和调试日志

### 配置管理
- **算法配置保存**：保存算法链配置为JSON文件
- **参数预设**：保存常用参数组合
- **工作空间**：保存和恢复完整的工作状态

## 📝 日志和调试

### 日志位置
- 控制台输出：实时日志信息
- 日志文件：`logs/` 目录下的日志文件

### 调试技巧
1. 使用 `--debug` 参数启用详细日志
2. 检查 `logs/` 目录中的日志文件
3. 使用算法节点的"查看结果"功能检查中间输出
4. 使用性能监控分析算法瓶颈

## 🔧 扩展开发

### 添加新算法
1. 在对应的分类目录下创建算法文件
2. 继承 `AlgorithmBase` 基类
3. 实现必要的方法
4. 算法会被自动发现和注册

### 创建组合算法
1. 在画布上构建算法链
2. 配置所有参数
3. 使用"保存组合算法"功能
4. 组合算法会被添加到算法库中

### 自定义UI组件
1. 在 `ui/components/` 中创建组件
2. 继承相应的Qt基类
3. 在主对话框中集成组件

## 📄 许可证

本项目采用 MIT 许可证，详见 LICENSE 文件。

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📞 支持

如有问题或建议，请提交 Issue 或联系开发团队。

---

**重要提醒：**
- 🔸 **core/** 目录文件不可修改，必须复用现有功能
- 🔸 **必须使用** `core/log_manager.py` 中的日志方法
- 🔸 **禁止使用** `print()` 语句，统一使用日志系统
- 🔸 遵循现有的代码规范和架构设计