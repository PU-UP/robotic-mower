# RLCP 算法模块化架构网页

2026-11-03，v0.4 讨论稿。基于用户手绘与后续职责补充；是架构评审文档，不是产品运行程序。未修改 rlcp 或 roboframe 实现。

按用户 2026-10-30 的要求，后续仅维护本地可访问版本，不再发布或同步在线站点。页面全部资源在本地，无需外网。

直接用浏览器打开 `dist/index.html`，无需安装依赖或启动服务。也可在本目录执行 `python -m http.server 8765 --bind 127.0.0.1 --directory dist` 后访问本机 8765 端口。

## 内容与维护

- `dist/model.js`：模块、职责、接口、依据、专题视图、待确认问题和流程的数据源。用户确认、用户修订与补充建议分别标注，内部职责不直接映射为代码结构。
- `dist/app.js`、`dist/style.css`、`dist/index.html`：交互与页面呈现。
- `.openai/hosting.json`：保留先前的站点标识，仅供历史追溯；本地浏览不使用它，不代表需要继续发布。

图支持模块与接口查看、系统总览 / 定位与地图 / 地图协作 / 调度与异常四个专题、数据 / 指令 / 反馈筛选、部署候选视图、五条交互流程和浏览器打印。“地图协作”及“轨迹处理 → 导航就绪”流程展开本轮新职责。TF 广播单独画出便于阅读，但它是 SLAM 的公共接口，不是独立服务。窄屏可横向滚动画布，职责面板放在图下方。架构内容只通过源文件更新，页面没有多人在线编辑或后端保存。

## 本轮设计依据

本轮在 Map Server 扩展职责的基础上，调整统一调度、异常入口和三个进程的归属；此前 TF、Submap、非阻塞调度等方向继续保留：

- SLAM 提供 base_link → odom → map TF，初期可广播；Percep、Nav Map、Global planner 和 Local planner 都消费 TF，总览直接展示这四条关系。Percep 累计 Submap 只使用 odom 关系。另需提供历史 Submap 原点在 map 系下的 pose 更新机制，内部 PoseGraph 类设计尚未定稿。
- Percep 输出 local BEV OCC 与多帧累计的重叠双 Submap。Submap 累计仅用 odom；两张部分重叠的设计来自用户描述，不表示完整复制 Cartographer 的实现。
- Map Server 保留名称，接收 SLAM PoseGraph 轨迹，平滑、检查完整性、合并 / 分割，并保存起点、终点和 path；维护轨迹间连接关系以及轨迹、拓扑、ID 属性和地图配置文件。
- Business_core 提供轨迹 ID、草坪 / 通道属性、割草角度、高度等配置，与 Map Server 共同维护地图文件夹并保持对应一致。单文件写入分工、提交方式和编辑后的 ID / 属性映射仍需设计。
- Nav Map 继续管局部动态层与 Submap 障碍物地图。建议按版本消费 Map Server 的轨迹几何约束，派生导航视图，不重复平滑轨迹或维护拓扑主副本。机器人位于 local costmap 中心；Global / Local planner 直接从 Nav Map 获取 costmap。
- 已确认旧保存边界轨迹的内容与 map 坐标继续冻结，SLAM 优化不得修改。合并 / 分割产生新版本，并重新校验拓扑；Nav Map 消费所选版本，不反写保存轨迹。
- 决策模块包含 Decision 调度核心、Anomaly 和 Map Server。Decision 含状态机，以非阻塞 client 方式调度能力 server；同进程内的异常检测和轨迹 / 文件处理也不得阻塞调度核心。Server 是逻辑角色，不强制同步 RPC。
- Anomaly 是统一异常检测模块，接收算法端异常 / 诊断依据，也接收撞板、电机故障 / 堵转、刀盘堵转等底板信号；整理后报告给 Decision。对 SLAM / Percep 的依赖是数据关系，不意味着同进程。异常事实与策略分开，底板故障不直接进入调度核心；其他算法异常来源清单待细化。
- Global 与 Local planner 无直接交互：Global 返回几何路径和结果给 Decision，再由 Decision 向 Local 下发路径及执行请求；Local 反馈后由 Decision 决定是否重规划。请求、路径及地图版本关联、替换 / 取消和迟到结果处理为待细化协议。
- 当前暂按三个进程：感知定位（SLAM、Percep）；决策（Decision 调度核心、Anomaly、Map Server）；规控（Nav Map、Global / Local planner，Recovery / Motion 暂归规控）。Nav Map 放规控已获用户确认。Business_core 保持外部业务角色，TF 是 SLAM 接口。节点配色和分组卡片展示进程归属，不代表独立线程。

建议的三方交互：Decision 异步请求 Map Server 处理 / 保存轨迹资产，收到明确版本的提交结果后请求 Nav Map 加载和构建该版本；Map Server 向 Nav Map 提供轨迹几何约束与配套文件，Nav Map 返回导航就绪 / 失败。Decision 只在请求与版本匹配且导航就绪后启动规划。文件保存成功不等于 costmap 可用。

共同维护文件夹不等于共同覆盖同一文件。建议每类文件有唯一写入者，由 Map Server 统一提交配套版本；缺失业务 ID、拓扑悬空引用或属性冲突不能静默成功。具体写入协议未定。割草角度和高度属于作业配置，不直接成为 costmap 代价；通道宽度、草坪闭合与跨区域拓扑的最终消费者待讨论。

Submap 锚点登记接口、优化批次与贡献替换、轨迹约束读取、文件配套提交协议、异步请求 / 取消 / 超时等均为设计建议。历史节点关联、轨迹平滑与完整性判据、地图融合、版本切换、轮速对时和失效处理仍待讨论；不能将建议视为已确认协议。

Global planner 仍输出几何路径 / 作业路线，Local planner 接收底板轮速并生成可执行运动。轮速消费者已确认，不再暂画到 Nav Map。跨进程采用 IPC，同进程能力可库调用；Percep 可以编入 SLAM。两级 planner 虽同属规控，路径交接仍经决策进程。未来单进程是候选，不是既定迁移要求。覆盖、沿边、刀盘和对桩尚未完整展开。

相关范围见仓库 `docs/REPOSITORY_SCOPE.md`、`docs/RLCP_BASELINE.md`；未重新核对产品源码，也未进行机器人运行或硬件测试。后续评审统一关联根目录 TODO 的 T-001、T-002、T-004。

## 验证

执行 `node check.cjs` 检查图数据和流程引用。若已有 Playwright，可执行 `node check.cjs <playwright模块绝对路径>`；浏览器检查使用已安装的 Microsoft Edge，不给网页增加运行依赖。

检查还约束 costmap 必须来自 Nav Map、Map Server 不直接提供 costmap、轨迹输入和业务属性对应关系、旧版本冻结与新版本编辑，以及“提交结果 → 加载 → 导航就绪 → 规划”的示意顺序。还检查两级 planner 无直连、硬件异常必须经 Anomaly、决策子模块归属及三个进程的完整且不重复分组。未定的 Submap 登记协议仍标为建议。浏览器检查覆盖模块职责、四个专题、接口筛选、详情快捷入口的滚动与焦点、键盘操作、部署视图、五条流程、手机宽度溢出和无外网请求。截图写入忽略提交的 `.local-archive/`。这只验证网页行为和设计表达一致性，不验证算法正确性或产品实现。
