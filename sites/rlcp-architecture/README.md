# RLCP 算法模块化架构网页

2026-10-30，v0.2 讨论稿。基于用户手绘与两轮职责补充；是架构评审文档，不是产品运行程序。未修改 rlcp 或 roboframe 实现。

按用户 2026-10-30 的要求，后续仅维护本地可访问版本，不再发布或同步在线站点。页面全部资源在本地，无需外网。

直接用浏览器打开 `dist/index.html`，无需安装依赖或启动服务。也可在本目录执行 `python -m http.server 8765 --bind 127.0.0.1 --directory dist` 后访问本机 8765 端口。

## 内容与维护

- `dist/model.js`：模块、职责、接口、依据、专题视图、待确认问题和流程的数据源。用户确认、用户修订与补充建议分别标注，内部职责不直接映射为代码结构。
- `dist/app.js`、`dist/style.css`、`dist/index.html`：交互与页面呈现。
- `.openai/hosting.json`：保留先前的站点标识，仅供历史追溯；本地浏览不使用它，不代表需要继续发布。

图支持模块与接口查看、系统总览 / 定位与地图 / 调度与异常三个专题、数据 / 指令 / 反馈筛选、部署候选视图、五条交互流程和浏览器打印。TF 广播单独画出便于阅读，但它是 SLAM 的公共接口，不是独立服务。窄屏可横向滚动画布，职责面板放在图下方。架构内容只通过源文件更新，页面没有多人在线编辑或后端保存。

## 本轮设计依据

本轮细化并取代 v0.1 的笼统地图分工：

- SLAM 提供 base_link → odom → map TF，初期可广播；Percep、Nav Map、Global planner 和 Local planner 都消费 TF，总览直接展示这四条关系。Percep 累计 Submap 只使用 odom 关系。另需提供历史 Submap 原点在 map 系下的 pose 更新机制，内部 PoseGraph 类设计尚未定稿。
- Percep 输出 local BEV OCC 与多帧累计的重叠双 Submap。Submap 累计仅用 odom；两张部分重叠的设计来自用户描述，不表示完整复制 Cartographer 的实现。
- Nav Map 管局部动态层、可保存障碍物地图和建图边界轨迹。机器人位于 local costmap 中心；边界轨迹保存后内容与 map 坐标均冻结，后续 SLAM 优化不得修改。Global / Local planner 直接从 Nav Map 获取 costmap。
- Map Server 只提供文件保存、位置、读取、删除和两侧文件配套，不修改或消费地图内容，不提供运行时 costmap。地图解析和语义由 SLAM / Nav Map 自己负责。
- Decision 含状态机，以非阻塞 client 方式调度能力 server，接收底板 / 堵转信号与算法异常。Server 为逻辑角色，不强制独立进程或同步 RPC。
- 新增异常检测，强依赖 SLAM / Percep，输出打滑、相机遮挡、LiDAR 算法侧异常；具体策略由 Decision 决定。

Submap 锚点登记接口、优化批次与贡献替换、文件配套提交协议、异步请求 / 取消 / 超时等均为设计建议。历史节点关联、地图融合细节、建图 ID 的业务归属、轮速对时和失效处理仍待讨论；网页明确标注当前解释，不能作为已确认协议。

Global planner 仍输出几何路径 / 作业路线，Local planner 接收底板轮速并生成可执行运动。轮速消费者已确认，不再暂画到 Nav Map。初期采用 IPC，Percep 可以编入 SLAM；未来单进程是候选，不是既定迁移要求。覆盖、沿边、刀盘和对桩尚未完整展开。

相关范围见仓库 `docs/REPOSITORY_SCOPE.md`、`docs/RLCP_BASELINE.md`；未重新核对产品源码，也未进行机器人运行或硬件测试。后续评审统一关联根目录 TODO 的 T-001、T-002、T-004。

## 验证

执行 `node check.cjs` 检查图数据和流程引用。若已有 Playwright，可执行 `node check.cjs <playwright模块绝对路径>`；浏览器检查使用已安装的 Microsoft Edge，不给网页增加运行依赖。

检查还约束 costmap 必须来自 Nav Map、Map Server 不直接供图，以及未定的 Submap 登记协议仍标为建议。浏览器检查覆盖所有模块职责、三个专题、接口筛选、详情快捷入口的滚动与焦点、连线键盘操作、部署视图、五条流程、手机宽度溢出和无外网请求。截图写入本仓库忽略提交的 `.local-archive/`。这只验证网页行为和设计表达一致性，不验证算法正确性或产品实现。
