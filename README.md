# robotic-mower

当前阶段：先设计 **brain 的输入输出与业务状态机**，用独立交互场景迭代；算法逐个业务替换模拟实现。

```text
robotic-mower/
├── brain/          完整业务逻辑、任务顺序、业务进度和恢复决策
├── perception/     感知定位与内部 SLAM 数据
├── map_manager/    业务地图管理及 SLAM map ID 对齐
├── pnc/            当前目标的规划与控制
├── contracts.py    JSON 控制协议及最小内部值类型
└── simulation/     算法替身、交互脚本、回归和离线回放
```

系统职责见 [SSM、Brain 与 foundation 的边界](SYSTEM_DESIGN.md)。SSM 是 Brain 的上游，负责系统许可与命令转交；Brain 是业务决策中心。根据 2026-10-12 的架构确认，原先 perception、map_manager、pnc 三个算法进程合并到 roboframe 的单一算法进程，三者保留逻辑职责边界。Brain 职责基本维持，继续管理任务顺序、业务进度、中断与恢复。SSM/foundation/HMI/App 尚未接入原型。

## roboframe 工作区与集成边界

当前算法组件关系与职责见 [roboframe 架构讨论基线](docs/ROBOFRAME_ARCHITECTURE_BASELINE.md)：保留原有八项主体，新增 CoverageManager、BladeComponent 和充电桩感知，明确 Controller 对桩模式及配套、可选能力和待定边界。Brain 保留业务决策，CoverageManager 管理某次任务的空间进度；这是目标架构讨论基线，不代表能力已经实现或接口已经定稿。

- 实际工作区：WSL2，发行版 `Ubuntu-22.04`，目录 `/home/watermango/work/roboframe`。
- GitHub 仓库：[PU-UP/roboframe](https://github.com/PU-UP/roboframe)，已核实 origin 为 `https://github.com/PU-UP/roboframe.git`。
- roboframe 的产品进程为 `robot_runtime`；算法组件由 integration 装配、接线和编排，组件内部负责算法计算。组件可以独立开发，部署在同一进程内不等于单线程，也不要求一个职责目录对应一个组件。
- Brain 继续负责业务决策；roboframe 承接当前目标所需的算法执行。具体组件拆分、内部 BT 与 Brain 的接口接入仍待明确，本次进程合并不把 Brain 的业务决策职责转移给算法组件。
- 本仓库继续用于 Brain 协议、业务状态机与交互仿真。`perception/`、`map_manager/`、`pnc/` 是现有逻辑契约与数据模型，不再表示三个独立部署进程；当前 Python 仿真尚未接入 roboframe。

## 当前原型接口

当前已实现的 Brain 局部接口如下；图中三个算法模块表示仿真中的逻辑交互，不表示产品进程划分。目标部署见系统设计中的 roboframe 单进程边界。

```mermaid
flowchart TB
    U[上游接口：目标接SSM，当前由仿真提供] --> B[brain]
    B -->|command_result / brain_status| U
    B -->|directive: mode / phase / mission| P[perception]
    B -->|directive| M[map_manager]
    B -->|directive| N[pnc]
    P -->|status| B
    M -->|status| B
    N -->|status| B
    P -->|定位、观测、SLAM map ID| M
    P -->|定位与实时环境| N
    M -->|业务地图与参考关系| N
    N --> A[执行机构]
```

下发示例：

```json
{
  "revision": 4,
  "mode": "WORKING",
  "phase": "EXECUTE",
  "mission": {"type": "COVER_REGION", "map_id": "garden", "target_id": "region-2", "control": "AUTO"}
}
```

完整定义见 [Brain 输入输出协议](brain/PROTOCOL.md)：模块 status、上层 command、外部 event、命令回执与业务状态。任务历史、完整目标顺序只留在 brain；PNC 接收当前目标与实时算法输入，没有跨任务历史依赖。

运行（项目根目录，Python 3.11+）：

```powershell
.\.venv\Scripts\python.exe -m simulation
.\.venv\Scripts\python.exe -m simulation --script simulation/scenarios/cover_regions.json
.\.venv\Scripts\python.exe -m unittest discover -s simulation -p "test_*.py" -v
```

新环境先安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

打开 [交互回放](simulation/output/report.html) 查看固定模块交互图、本步 JSON、模块基本状态和验收结果。仿真支持自动算法反馈和脚本指定反馈，格式见 [仿真说明](simulation/README.md)。

后续你提供一项业务，就增加一份独立的交互脚本，填入输入与期望输出，再迭代 brain；目前不提前规定全部业务策略。

当前下层包只定义最小数据产品，真实算法未实现。续作保留已完成目标，被打断目标重新执行；无精确轨迹续作、业务历史掉电恢复、可靠地图提交或实机运动保证。SLAM 与业务地图 ID 对齐目前只声明/校验参考关系，没有坐标变换算法。

首个业务已接入：[整次建图流程](brain/MAPPING.md)，包含两区域、一通道、遥控接管、闭合通知和最终保存。运行 python -m simulation --scenario mapping 查看独立验证。

仓库使用 main 分支。源码、协议文档和仿真场景纳入版本管理；.venv、缓存和 simulation/output 生成文件不提交。克隆后按上述步骤运行即可重新生成回放页面。
