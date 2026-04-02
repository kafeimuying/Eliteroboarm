# 项目分析与 Elite SDK 学习笔记

更新时间: 2026-03-06

## 1. 项目定位

这个仓库不是单一的机械臂控制程序，而是一个“视觉 + 硬件 + 机械臂”的一体化工作站，面向柔性拍摄、视觉引导和标定联调。

从代码看，项目至少支持三种使用方式：

1. `python launcher.py --hardware`
   面向硬件控制台，包含相机、机械臂、光源、硬件配置四个主标签页。
2. `python launcher.py --canvas`
   面向视觉算法链调试，支持把多个算法节点拖到画布上串起来执行。
3. `python launcher.py --vision-robot`
   面向 VMC（Vision Motion Control，视觉-机械臂协同）工作流，把相机节点、视觉节点、机器人动作节点编排成流程。

结论：这个项目的核心目标是把“采图、识别、坐标修正、机械臂执行”放在同一套桌面工具里。

## 2. 仓库结构

### 2.1 顶层目录

- `launcher.py`
  总入口，负责选择运行模式。
- `src/`
  主体代码，包含 UI、核心服务、驱动、算法、配置管理。
- `config/`
  系统配置和硬件配置。
- `workspace/`
  运行态数据目录，包含抓图、路径、日志、临时文件、标定数据。
- `cpp_extensions/`
  Pybind11 C++ 扩展，包含 Elite 机械臂高性能控制/标定扩展。
- `Elite_CPP_Interface/`
  本地随仓携带的 Elite C++ SDK 头文件和 DLL。
- `AprilTagInterface/`
  AprilTag 检测的独立子模块。
- `manual_correction_tool.py`
  手眼标定后，根据视觉偏差计算机械臂补偿位姿。
- `multi_point_servo.py`
  多点位视觉伺服配方与偏差传播。
- `calc_deviation.py`
  基于 AprilTag / ArUco 的示教图与生产图偏差计算脚本。

### 2.2 `src/` 内部模块

- `src/app`
  启动器和 bootstrap。
- `src/core`
  配置、容器、服务层、执行器、事件总线、中间件。
- `src/drivers`
  相机、机械臂、光源、通信驱动。
- `src/ui_libs`
  PyQt6 界面。
- `src/algorithms`
  基础算法、高级算法、性能算法、组合算法。
- `src/simple_test`
  视觉逻辑的离线测试脚本。

粗略统计：

- Python 文件约 150 个
- C++ 源/头文件约 33 个
- 这是一个典型的“以 Python 为主、局部用 C++ 加速或封装设备协议”的工程

## 3. 启动与运行链路

### 3.1 总入口

`launcher.py` 负责：

- 把 `src/` 加到 `sys.path`
- 把 `cpp_extensions/extensions/Release` 加到 Python 模块与 DLL 搜索路径
- 按参数切换三种模式

### 3.2 硬件模式

主链路：

`launcher.py`
-> `src/app/hardware_launcher.py`
-> `src/app/bootstrap.py`
-> `Container` 注册服务
-> `HardwareManagementMainWindow`
-> `RobotControlTab` / `CameraControlTab` / `LightControlTab`

这里的关键点不是一个“后端服务进程”，而是 UI 直接持有 service，再由 service 调 driver。

### 3.3 视觉算法画布

主链路：

`launcher.py --canvas`
-> `src/ui_libs/vision_canvas/...`
-> `PipelineExecutor`

它更像一个通用算法实验台，负责把图像处理算法串成链。

### 3.4 VMC 模式

主链路：

`launcher.py --vision-robot`
-> `src/ui_libs/vision_robot_widget/vision_robot_dialog.py`
-> 画布节点组织 VMC 配置
-> `src/core/managers/vmc_pipeline_executor.py`
-> 依次执行 camera -> vision -> robot

这部分是真正把视觉输出转为机器人动作的工作流层。

## 4. 核心架构

### 4.1 配置层

主要文件：

- `config/system.yaml`
- `config/hardware_config.json`
- `src/core/managers/app_config.py`

`AppConfigManager` 负责：

- 统一管理 `config/` 与 `workspace/`
- 自动创建 `workspace/logs`、`workspace/captures`、`workspace/paths` 等目录
- 提供系统配置、硬件配置、应用配置的读取能力

### 4.2 容器层

`src/core/container.py` 是一个非常轻量的 DI 容器，支持：

- `register`
- `register_factory`
- `register_singleton`
- `resolve`

它不是复杂框架，更像全局对象注册表。

### 4.3 服务层

主要服务：

- `RobotService`
- `CameraService`
- `LightService`
- `CalibrationService`

服务层的职责是：

- 向 UI 提供统一返回结构
- 屏蔽具体 driver 差异
- 追加路径保存、标定流程、状态整理等业务逻辑

### 4.4 驱动层

驱动接口定义在：

- `src/core/interfaces/hardware/robot_interface.py`
- `src/core/interfaces/hardware/camera_interface.py`
- `src/core/interfaces/hardware/light_interface.py`

实现位于：

- `src/drivers/robot/*.py`
- `src/drivers/camera/*.py`
- `src/drivers/light/*.py`

这里的设计思路是“上层统一抽象，下层各品牌适配”。

### 4.5 设备管理存在两条并行路线

这是后续工作必须记住的第一件事。

项目里并不是只有一套“设备创建流程”，而是至少两套：

1. `RobotFactory` / `CameraFactory` 路线
   `RobotService.connect(config)`、`CameraService.connect(config)` 会按配置动态创建具体驱动。
2. `HardwareManager` / `DeviceRegistry` 路线
   通过初始化硬件配置，预先把设备实例挂到容器里。

这会带来一个非常重要的现象：

- 某些 UI 页面是直接走 service + factory 的
- 某些 VMC 节点是先从 `HardwareManager` 拿现成设备的

因此，同一台设备在不同入口上的可用性可能不同。

## 5. 视觉与工作流逻辑

### 5.1 算法层

视觉算法分为四类：

- `src/algorithms/basic`
  阈值、模糊、边缘、形态学
- `src/algorithms/advanced`
  模板匹配、轮廓、几何、颜色、ROI
- `src/algorithms/performance`
  高性能版本，部分依赖 C++ 扩展
- `src/algorithms/composite`
  组合算法 JSON

### 5.2 视觉执行器

`src/core/managers/vision_pipeline_executor.py` 做三件事：

1. 注册基础算法类
2. 加载组合算法 JSON
3. 根据连接关系构建拓扑顺序并执行

它本质上是“算法链运行时”。

### 5.3 组合算法管理

`src/core/managers/combined_algorithm_manager.py` 负责：

- 把算法链保存为 JSON
- 从 JSON 恢复为 `ChainConfig`
- 生成 `CombinedAlgorithm` 工厂

例如：

- `src/algorithms/composite/line_detect01.json`

表示一个“高斯模糊 -> 高性能 ROI 抓边”的组合链。

### 5.4 VMC 执行器

`src/core/managers/vmc_pipeline_executor.py` 是项目业务价值最高的模块之一。

它把 VMC 拆成三个阶段：

1. 相机节点
   连接硬件、设曝光/增益、触发采图、保存图像
2. 视觉节点
   读取算法配置 JSON，调用 `PipelineExecutor`
3. 机器人节点
   从视觉结果提取目标位姿，再调用机器人移动逻辑

这个执行器说明：项目已经具备“从图像到动作”的基本闭环。

## 6. 业务脚本与真实场景逻辑

如果只看框架，很容易误判项目目标。真正体现业务意图的，是下面三份脚本。

### 6.1 `calc_deviation.py`

用途：

- 读取示教图和生产图
- 检测 AprilTag 或 ArUco
- 计算两次拍摄之间的平移偏差和旋转偏差

输出结果是：

- `dX`
- `dY`
- `dZ`
- `dRZ`

这说明项目的一个关键场景是：

- 先有示教拍照
- 再有生产拍照
- 然后根据 tag 偏差修正机器人动作

### 6.2 `manual_correction_tool.py`

用途：

- 读手眼标定矩阵 `T_eye_in_hand_chessboard.json`
- 把 Elite 当前位姿转换成齐次矩阵
- 在相机坐标系中施加偏差
- 再转换回机械臂目标位姿

核心公式：

`T_B_F_new = T_B_F_cur @ T_F_C @ T_dev @ T_F_C_inv`

这个脚本说明项目不是简单平移补偿，而是已经进入手眼标定后的空间变换层。

### 6.3 `multi_point_servo.py`

用途：

- 记录标准点位的 tag 位姿
- 记录多个拍照点位
- 计算每个拍照点相对标准 tag 的变换
- 当标准点 tag 重新检测后，把偏差传播到全部拍照点

这是比单点补偿更成熟的方案，适合“整包料、整治具整体偏移”的场景。

结论：项目真实业务并不是“随便抓图”，而是“基于标准点的多点位柔性拍摄与偏差传播”。

## 7. 相机侧逻辑

### 7.1 当前支持的相机类型

从配置和驱动看，项目至少支持：

- 模拟相机
- Daheng / Galaxy
- RealSense D435i
- Hikvision
- Basler
- Flir

### 7.2 相机服务模型

`CameraService` 封装了：

- connect / disconnect
- capture_frame
- start_streaming / stop_streaming
- set_exposure / set_gain
- auto_focus
- software trigger

### 7.3 RealSense 驱动特点

`src/drivers/camera/realsense.py` 显示：

- 依赖 `pyrealsense2`
- 支持彩色流与深度流
- 支持 depth 对齐到 color
- 采图时会缓存内参和 depth scale

这对后续做 3D 重建、深度测量、点云扩展是有基础的。

### 7.4 Daheng 驱动特点

`src/drivers/camera/daheng.py` 显示：

- 依赖 `gxipy`
- 支持按 SN/IP/MAC 查找设备
- 支持 autofocus 尝试
- 抓图流程考虑了 Bayer/RGB 转换

## 8. Elite 机械臂接入结构

这是后续工作的重点。

### 8.1 本地已有的 Elite 相关资产

仓库内已经带了完整的 Elite 接入材料：

- `src/drivers/robot/elite.py`
  Python 主驱动
- `src/drivers/robot/elite_sdk_wrapper.py`
  ctypes 包装层
- `src/drivers/robot/elite_wrapper/elite_wrapper.cpp`
  C 风格 DLL 导出层
- `cpp_extensions/elite_ext.cpp`
  Pybind11 C++ 扩展
- `cpp_extensions/EliteRobotController.*`
  C++ 控制器封装
- `Elite_CPP_Interface/include/Elite/*.hpp`
  Elite C++ SDK 头文件
- `src/drivers/robot/bin/elite_wrapper.dll`
- `src/drivers/robot/bin/elite-cs-series-sdk.dll`
- `cpp_extensions/elite-cs-series-sdk.dll`
- `input_recipe.txt` / `output_recipe.txt`
  RTSI recipe
- `external_control.script`
  外部控制脚本模板

结论：这个仓库不是“准备接 SDK”，而是已经把 SDK 接进来了，只是实现路径比较分散。

### 8.2 Elite 驱动的三层控制路径

`EliteRobot` 实际混用了三套机制。

#### 路径 A: Pybind11 C++ 扩展 `elite_ext`

优先级最高。

特点：

- 直接在 Python 中导入 `elite_ext`
- 使用 `EliteRobotController`
- 通过 C++ 调用：
  - `DashboardClient`
  - `PrimaryPortInterface`
  - `RtsiIOInterface`

负责能力：

- connect
- get_position
- set_speed
- move_to
- jog

这条路径是当前最像“正式方案”的路径。

#### 路径 B: ctypes + `elite_wrapper.dll`

次优路径。

Python 端通过 `EliteSDK` 暴露：

- `Elite_Create`
- `Elite_Destroy`
- `Elite_IsConnected`
- `Elite_SendScript`
- `Elite_GetPose`

其底层 C++ 用的是：

- `EliteDriver`
- `RtsiIOInterface`

这条路径更多是“最小可用 SDK 包装层”。

#### 路径 C: 原始 socket 回退

兜底路径。

直接操作：

- Dashboard: `29999`
- Primary: `30001`
- RTSI: `30004`

主要用途：

- 上电
- 松刹车
- 发脚本
- 在 SDK 或 C++ 扩展不可用时维持基本控制

### 8.3 `EliteRobot.connect()` 的真实行为

连接顺序大致如下：

1. 优先尝试 `elite_ext.EliteRobotController.connect(ip, recipe_dir)`
2. 如果失败，再初始化 `elite_wrapper.dll`
3. 再 fallback 到纯 socket：
   - ping IP
   - 连接 Dashboard 29999
   - 连接 Primary 30001
   - 尝试连接 RTSI 30004
   - 发送 `robotControl -on`
   - 关闭安全弹窗 / 解保护停
   - 发送 `brakeRelease`

这说明 Elite 驱动是“分层降级”的，不是单一实现。

### 8.4 `EliteRobot.get_position()` 的优先级

位姿读取优先顺序是：

1. `elite_ext` 的 `get_position()`
2. `elite_wrapper.dll` 的 `Elite_GetPose()`
3. 解析 Primary 30001 的二进制包
4. 尝试 Dashboard 文本命令 `get_actual_tcp_pose`

返回给上层统一成：

- 位置: mm
- 姿态: deg

但需要注意，底层原始来源通常是：

- 位置: m
- 姿态: rad

### 8.5 `EliteRobot.move_to()` 的行为

上层接口是：

- 输入 `x, y, z, rx, ry, rz`
- 单位视为 `mm + deg`

内部执行时：

- 如果是 `elite_ext`，直接调用 C++ `move_to`
- 否则拼装脚本 `movel(...)`
- 转换成 `m + rad`

所以后续所有新功能都必须严格遵守这一层单位转换，不要直接把底层单位带到 UI 或 service 层。

### 8.6 Jog / Path / Calibration

Elite 驱动已经实现了：

- 连续点动 `start_jogging()` / `stop_jogging()`
- 定距 jog `jog_move()`
- 路径记录 `start_path_recording()` / `add_path_point()`
- 路径播放 `play_path()`
- 9 点标定
- 3D 标定

其中标定逻辑有两套：

1. Python 内部 9 点逻辑
2. C++ 高性能标定逻辑

`CalibrationService` 会把相机抓图回调注入到机器人驱动，形成“机械臂移动到点位 -> 回调触发拍照”的协同链路。

### 8.7 `cpp_extensions/elite_ext.cpp` 在做什么

这个文件非常关键。

它暴露了两个主要类：

- `EliteRobotController`
- `EliteCalibration`

`EliteRobotController` 负责：

- 通过 Dashboard + Primary + RTSI 建立连接
- 调 `powerOn()`、`brakeRelease()`
- 从 RTSI 读取 TCP pose
- 通过 Primary 发 `movel` / `stopj`

`EliteCalibration` 负责：

- 9 点标定
- 3D 标定
- 向 Python 回调日志、抓图请求、当前位姿

也就是说，项目当前最强的 Elite 能力不是在 Python，而是在这个 C++ 扩展里。

### 8.8 本地 SDK 头文件透露的信息

`Elite_CPP_Interface/include/Elite/EliteDriver.hpp` 显示：

- SDK 主类是 `EliteDriver`
- 支持：
  - `writeServoj`
  - `writeSpeedl`
  - `writeSpeedj`
  - `writeTrajectoryPoint`
  - `writeFreedrive`
  - `stopControl`
  - `zeroFTSensor`
  - `setPayload`
  - `setToolVoltage`
  - `startForceMode`
  - `endForceMode`
  - `sendScript`

并且 `EliteDriverConfig` 里可以看到它依赖一套外部控制端口：

- `script_sender_port = 50002`
- `reverse_port = 50001`
- `trajectory_port = 50003`
- `script_command_port = 50004`

这说明 Elite 官方 SDK 并不只是“发文本命令”，而是支持更完整的外部控制模式。

## 9. Elite SDK 的官方资料结论

结合本地 SDK 头文件和官方资料，可以得到下面几条对后续工作有用的结论。

### 9.1 当前官方产品线

Elite 官方在 2025-11-17 发布的说明里明确表示：

- `EC/EA` 系列已停止生产
- 主推 `CS/ES` 系列

官方来源：

- [What is the difference between EC and CS, and EA and ES series collaborative robots?](https://docs.elibot.com/sdk-website/EliteEcV4/wiki/12_FAQ/Questions)

仓库里的 DLL 名称是 `elite-cs-series-sdk.dll`，与当前产品线一致。

### 9.2 官方开放的典型接口端口

官方资料里能确认：

- Dashboard 相关接口常见端口是 `29999`
- Primary 端口是 `30001`
- RTSI 端口是 `30004`
- 另有 `8055` JSON 数据接口

官方来源：

- [How to use port 8055](https://docs.elibot.com/sdk-website/EliteEcV4/wiki/12_FAQ/Questions)

这和仓库里的连接实现是对得上的。

### 9.3 远程模式要求

官方文档提到：

- 某些远程接口需要在远程模式下使用

这意味着后续如果你遇到“端口能连但命令不执行”的问题，不能只看代码，也要排查控制器是否进入了正确模式。

### 9.4 项目目前只用到了 SDK 的一部分

本地 `EliteDriver.hpp` 显示，官方 SDK 已经具备：

- 轨迹下发
- 速度控制
- force mode
- freedrive
- payload / tool voltage

但本项目当前主要只用到了：

- `sendScript`
- RTSI 位姿读取
- Dashboard 上电/松刹车

所以后续如果要做：

- 更平滑的连续跟随
- 真正高频视觉伺服
- 轨迹前瞻或队列控制

应该优先评估直接扩展 `EliteDriver` 路线，而不是继续堆更多字符串脚本。

## 10. 当前识别到的架构风险

### 10.1 Elite 在不同入口上的可用性不一致

这是目前最重要的风险。

`RobotFactory` 支持 `elite`，但：

- `HardwareManager._get_robot_driver_class()` 没有 `elite`
- `HardwareManager._register_driver_classes()` 也没注册 `EliteRobot`
- `DeviceRegistry` 内置注册表同样没有 `elite`

结果是：

- 硬件控制页里的机器人连接，走 `RobotService.connect(config)`，通常能连 Elite
- 某些 VMC / HardwareManager 路径，未必能拿到 Elite 驱动实例

这解释了为什么“配置里有 Elite，但某些模块里仍可能提示找不到机器人”。

### 10.2 相机也存在类似的双路径问题

`DeviceRegistry` 是否注册真实相机受 `system.yaml` 的 `camera_driver_check_enabled` 控制。

当前配置是：

- `camera_driver_check_enabled: false`

因此：

- 某些依赖 `DeviceRegistry` 的流程不会预注册真实相机
- 但 `CameraService.connect(config)` 仍可以通过 `CameraFactory` 直接连接真实相机

说明项目里“设备发现”和“设备连接”并不完全统一。

### 10.3 姿态表示存在潜在混淆

这是 Elite 相关开发最容易踩坑的点。

代码里同时出现了两种说法：

1. RTSI / SDK 返回 TCP pose 时，常按 `rotation vector` 处理
2. `manual_correction_tool.py` 明确按 `Euler XYZ` 处理

同时上层接口又把姿态统一暴露成 `rx, ry, rz`。

如果后续你要做：

- 手眼标定结果复用
- VMC 位姿输出
- 机械臂末端姿态补偿

必须先统一一个文档：

- “某个模块的 `rx, ry, rz` 到底是旋转向量，还是欧拉角”

否则很容易出现“平移对、姿态错”。

### 10.4 Elite 驱动内部回退逻辑较多

`elite.py` 同时包含：

- C++ 扩展路径
- ctypes SDK 路径
- 原始 socket 路径
- 多种 get_position 回退

这提高了兼容性，但也增加了“路径依赖”：

- 一台机器上能跑，不代表另一台机器走的是同一条路径
- 某些问题只在某种 DLL / recipe / import 状态下出现

后续排障时必须先回答：

- 当前到底走的是哪条控制路径

### 10.5 构建产物直接放在仓库里

仓库里已经包含：

- `dll`
- `lib`
- `obj`
- `exp`
- `build/`
- `out/build/`

这对现场部署有帮助，但对源码维护不利：

- 很难确认当前实际使用的是哪个编译版本
- 容易出现“源码已改但加载的还是旧 DLL”

## 11. 后续工作的建议切入顺序

如果接下来要继续开发，不建议从 UI 开始看。推荐顺序如下。

### 第一阶段：建立运行地图

1. `launcher.py`
2. `src/app/hardware_launcher.py`
3. `src/ui_libs/hardware_widget/hardware_management_main_window.py`
4. `src/ui_libs/hardware_widget/robotic_arm/robot_control.py`
5. `src/core/services/robot_service.py`
6. `src/drivers/robot/elite.py`

### 第二阶段：建立 Elite 底层认知

1. `src/drivers/robot/elite_sdk_wrapper.py`
2. `src/drivers/robot/elite_wrapper/elite_wrapper.cpp`
3. `cpp_extensions/elite_ext.cpp`
4. `Elite_CPP_Interface/include/Elite/EliteDriver.hpp`
5. `Elite_CPP_Interface/include/Elite/DashboardClient.hpp`
6. `Elite_CPP_Interface/include/Elite/RtsiIOInterface.hpp`

### 第三阶段：建立视觉补偿认知

1. `AprilTagInterface/src/detector.py`
2. `calc_deviation.py`
3. `manual_correction_tool.py`
4. `multi_point_servo.py`

### 第四阶段：建立 VMC 闭环认知

1. `src/ui_libs/vision_robot_widget/vision_robot_dialog.py`
2. `src/ui_libs/vision_robot_widget/nodes.py`
3. `src/core/managers/vmc_pipeline_executor.py`
4. `src/core/managers/vision_pipeline_executor.py`

## 12. 我对项目当前状态的判断

### 已经具备的能力

- 桌面化硬件控制
- 多品牌相机接入
- Elite 机械臂基础控制
- 9 点 / 3D 标定
- AprilTag / ArUco 偏差计算
- 手眼标定后的位姿修正
- 多点位偏差传播
- VMC 工作流编排

### 目前更像“工程样机”的部分

- 设备创建路径不统一
- Elite 姿态约定没有被文档化
- C++/DLL/脚本三套控制链并存
- VMC 与硬件管理之间还有适配缝隙

### 最值得优先收敛的方向

1. 统一 Elite 设备注册与创建路径
2. 明确姿态表示标准
3. 确定后续主用的 Elite 控制链
   建议优先考虑 `elite_ext` 或直接扩展 `EliteDriver`，不要继续扩大纯脚本回退的范围
4. 给 VMC 闭环加最小可复现的联调样例

## 13. 对后续工作的直接建议

如果下一步要真正进入开发，而不是继续纯阅读，建议按这个顺序落地：

1. 先做一份 Elite 接口约定
   统一单位、姿态表示、坐标系、端口依赖。
2. 把 Elite 补进 `HardwareManager` / `DeviceRegistry`
   解决不同入口行为不一致的问题。
3. 给 `elite.py` 加运行路径日志
   启动时明确打印“当前使用 C++ 扩展 / ctypes SDK / raw socket 哪条路径”。
4. 用一个固定的 VMC demo 跑通
   相机采图 -> AprilTag 偏差 -> 位姿修正 -> Elite 移动。

如果后续你让我继续推进，我建议优先做第 1 和第 2 步，因为那两步能显著降低后面所有工作的不确定性。
