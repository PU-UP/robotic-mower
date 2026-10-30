# rlcp：首款实际产品架构基线

更新：2026-10-30。依据用户确认的工作范围，以及 WSL2 `Ubuntu-22.04` 中 `/home/watermango/work/rlcp` 的目录、构建入口、启动配置和业务接口。此前检查时 HEAD 为 `1eb74a207`，工作区无未提交改动；此处只是观察记录，不指定当前应使用的版本，也不表示持续跟踪最新代码。当时未修改该仓库，也未构建或运行其程序。

## 工作范围与重构方向

实际工作范围侧重感知、定位、规划控制等算法，并包括相关业务决策模块；本页不逐个认领组织责任。rlcp 是首款实际落地产品的完整软件与算法基线，未来在现有实现上渐进重构，借鉴 roboframe 的职责划分与组件组织，不以完整迁移 roboframe 或合并为单进程作为前提。

本仓库负责架构设计、产品对照和演进讨论，实际代码与测试分别在 rlcp 和 roboframe 中维护。旧 Python Brain 与 simulation 已退役；`Brain` 作为业务决策角色仍可讨论，但不预设替换整个 `business_core`。其职责和名称将结合实际业务重新定义，详见 [仓库职责](REPOSITORY_SCOPE.md)。

## 实际代码组织

当前 C++ 软件主体位于 `rlcp/slamMower/`。根目录 README 仍描述另一套农机 ROS2 节点，不足以代表该代码主体；以实际构建与启动配置为准。

| 位置（相对 slamMower） | 本次确认的内容 |
| --- | --- |
| `src/modules/business_core/` | 业务状态、任务策略、建图服务、消息处理，以及编入同一程序的业务地图、故障、历史轨迹等功能 |
| `src/modules/slam/` | 定位建图相关实现，构建 `fast_mapping` 等程序 |
| `src/modules/ccpp_planner/` | 全覆盖规划模块 |
| `src/modules/local_planner/` | 局部规划模块 |
| `src/modules/motion_control/` | 运动控制，包含充电对桩控制实现 |
| `src/modules/costmap_2d/` | 代价地图库与 `costmap_node` |
| `src/modules/around_edge/` | 视觉沿边相关感知、任务与控制代码 |
| `src/modules/camera/`、`recovery_node/` | 相机相关功能、恢复节点；内部算法和职责细节本次不展开 |
| `src/modules/` 中其他模块 | 通信路由、系统监控、蓝牙/Wi-Fi、OTA、语音、NTRIP、时间同步等配套能力 |
| `src/hw_abstract/`、`src/drivers/` | 硬件抽象与驱动，是业务和算法协作边界的一部分 |
| `msg/` | Protobuf 消息定义，包括业务、算法、规划和硬件协议 |

`src/CMakeLists.txt` 与各模块构建文件定义多个程序；`config/default_autoboot.conf`、`user_autoboot.conf` 分别列出启动项。模块可构建不代表默认启动，配置也不证明实机当前运行状态。已查看的业务通信代码使用 ZeroMQ 和 Protobuf。

## 与已退役 Python 原型的关键差异

| 项目 | 旧原型行为（不再作为要求） | rlcp 基线及后续处理 |
| --- | --- | --- |
| 执行边界 | 单一 `RoboframeDouble` 与统一状态反馈 | 多个模块程序；后续按真实接口设计适配，不把替身结构当作部署要求 |
| 业务范围 | 任务顺序、建图会话、暂停、低电回充、恢复 | `business_core` 还包含日历、设备状态、业务地图、消息与硬件交互；先分清哪些保留在业务核心 |
| 状态表达 | 业务 Mode、Mission 生命周期、PREPARE/EXECUTE/COMMIT | `device_task.proto` 包含设备状态、任务状态和原因；不能按名称机械对应 |
| 协议 | Python JSON directive/status 与 revision/task_id | `TaskRequest/TaskResponse`、`CmdNav` 等 Protobuf 接口；兼容关系尚未设计 |
| 回充后恢复 | 电量恢复后要求显式 RESUME | `lowBatteryLogic` 存在中断型回充满足条件后自动续割的分支；需要按产品行为补充场景，不能直接套用旧规则 |
| 启动与建图 | 固定退桩 1.5 米、回归通道、区域/通道采集 | `DevTaskManager`、`MappingService` 包含出桩、重定位及建图准入流程；距离、地图元素与流程的对应关系待逐项确认 |
| 地图归属 | 业务地图模型在仿真中，Brain 不做几何运算 | `business_core` 构建时编入 `manualctr` 地图代码；拆分应保留现有数据、保存和调用语义 |
| 系统边界 | 旧设计预设 SSM / Foundation | 实际存在硬件抽象、监控及分散的业务处理；不能将目录直接等同旧 SSM / Foundation 职责 |

主要核对入口：`src/modules/business_core/main_core/CMakeLists.txt`、`business_strategy.cpp`、`include/devtask_manager.h`、`include/mapping_service.h`，以及 `msg/business_core/device_task.proto`、`msg/algorithm/algorithm_cmd_req.proto`。上述结论是代码结构与分支观察，不是完整行为或实机验收。

## 后续演进

rlcp 现有行为是重构起点，不意味着所有实现都应保留；参考架构提供候选职责划分，也不要求产品立即采用。每次调整先明确产品问题、兼容要求和验收依据，再决定哪些变化留在产品、哪些经验反馈到 roboframe。

业务、算法和验证代码在对应实现仓库变更。本仓库记录跨模块设计、迁移决策、实现核对证据和验证结论，不再另建业务原型或替身运行环境。下一步可选择一个业务流程，重新定义决策、执行与反馈的归属；无需先给所有模块改名或重组进程。

尚待明确的工作统一进入 [TODO](../TODO.md)，不根据上述差异自动重构产品代码；核对与验收边界见 [工作约定](REPOSITORY_SCOPE.md)。
