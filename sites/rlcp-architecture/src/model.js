// Logical architecture; confirmed responsibilities and proposed protocols remain distinct.
const architecture = {
  modules: [
    {"id":"sensors","name":"Sensors","cn":"定位传感器","x":30,"y":30,"kind":"external","tag":"系统输入","summary":"提供激光、IMU 与里程计原始观测。","owns":"原始观测与采样时间；驱动归属不在本图展开。","parts":[["LiDAR","点云与采样时刻。"],["IMU / Odom","惯性与轮式里程计观测。"]],"boundary":"坐标外参、时间同步和观测有效性必须在接口中定义。","role":"外部输入 / 输出"},
    {"id":"camera","name":"Camera","cn":"视觉输入","x":30,"y":650,"kind":"external","tag":"系统输入","summary":"向 Percep 提供图像。","owns":"图像观测及标定信息。","parts":[["图像输入","图像、时间戳与相机标定信息。"]],"boundary":"不把图像识别结果直接当成可执行运动指令。","role":"外部输入 / 输出"},
    {"id":"business","name":"Business_core","cn":"业务核心","x":330,"y":40,"kind":"business","tag":"用户修订","summary":"提供轨迹 ID、草坪 / 通道等业务属性及割草角度、高度等配置，与 Map Server 共同维护地图文件夹及数据对应关系。","owns":"轨迹业务 ID、属性与作业配置的语义来源；业务任务策略。","parts":[["业务数据 · 已确认","提供轨迹 ID、草坪 / 通道类型，以及割草角度、高度等地图配置。"],["地图文件夹协作 · 已确认","与 Map Server 保持轨迹、拓扑、ID 属性和配置相互对应。"],["编辑后的 ID 对应 · 建议","合并 / 分割产生的新 ID 仍由 Business_core 提供；依据 Map Server 的新旧轨迹对应关系补齐属性。"],["任务入口","向 Decision 提供任务意图、目标 ID 和所选地图版本；受理和业务完成分开表达。"]],"boundary":"共同维护不意味着并发覆盖同一文件。建议约定每类文件的唯一写入者，由 Map Server 统一提交配套版本；具体写盘协议待讨论。","role":"业务入口"},
    {"id":"decision","name":"Decision","cn":"调度核心 · 状态机","x":660,"y":40,"kind":"control","tag":"用户确认","summary":"决策模块包含调度核心、Anomaly 和 Map Server。图中 Decision 专指非阻塞调度核心：统一调度两级 planner，接收 Anomaly 汇总的异常事实并决定策略。","owns":"调度状态、当前任务 / 路径交接与策略选择；轨迹资产归内部 Map Server，异常检测状态归内部 Anomaly。","parts":[["状态机与调度 · 已确认","根据业务任务、执行反馈和 Anomaly 异常事件推进状态；不直接接收底板故障信号。"],["异步服务调用 · 已确认方向","发起请求后继续处理事件；服务端以进度、结果或事件回报，决策不等待耗时操作结束。"],["地图流程调度 · 建议","调度 Map Server 处理 / 保存资产，再调度 Nav Map 加载同一明确版本；以异步结果推进，不操作轨迹几何或地图文件。"],["请求生命周期 · 建议","区分受理与完成；关联请求 ID，设置超时、取消及迟到结果隔离。"],["异常策略 · 已确认职责","统一接收 Anomaly 的算法与硬件异常；停止、重规划、恢复或上报的规则待讨论。"],["两级规划协调 · 用户确认","Global 返回几何路径给 Decision，Decision 再向 Local 下发路径与执行请求。Local 的进度 / 阻塞反馈由 Decision 决定是否重规划；两级 planner 不直接交互。"]],"boundary":"Decision 调度核心不执行轨迹处理或异常检测，委托其内部 Map Server / Anomaly；同进程的耗时处理仍不得阻塞状态机。建议校验任务、路径及地图版本，隔离取消后的迟到规划结果；地图未就绪时不启动新规划。","role":"Client · 异步调度"},
    {"id":"slam","name":"SLAM","cn":"定位 · TF · 历史位姿","x":30,"y":300,"kind":"sense","tag":"用户确认","summary":"提供 base_link → odom → map 的 TF，并提供更新历史 Submap 原点在 map 坐标系下位姿的机制。","owns":"坐标关系、定位状态、内部地图与历史锚点的 map 位姿；内部 PoseGraph 结构待设计。","parts":[["定位 / 建图与去畸变","消费定位传感器数据，为 Percep 输出去畸变点云。"],["TF 发布 · 已确认","向各模块提供 base_link → odom → map 坐标关系；初期可广播。"],["历史 Submap 位姿 · 已确认需求","支持按 Submap 标识更新原点在 map 系下的 pose；不能只提供当前机器人 TF。"],["PoseGraph 类内部能力 · 待设计","约束来源、节点选择、Submap 关联、优化触发与历史保留方式尚未定稿。"],["PoseGraph 轨迹输出 · 用户确认","向 Map Server 提供历史轨迹用于平滑、完整性检查与合并 / 分割；输出时机、坐标版本和采样标识待细化。"],["地图文件服务协作","序列化 / 解析自有地图资产；通过 Map Server 保存、定位和读取对应文件。"]],"boundary":"SLAM 内部优化方法未定。本图确认向外提供 TF、历史 Submap 位姿更新和 PoseGraph 轨迹的能力；不强制复制 Cartographer 的具体实现。","role":"Server · 能力服务"},
    {"id":"percep","name":"Percep","cn":"Local BEV · 重叠 Submap","x":30,"y":500,"kind":"sense","tag":"用户确认","summary":"输出实时 local BEV OCC，并用 odom 累计多帧观测，形成两张部分重叠的 Submap 送给 Nav Map。","owns":"感知观测、Submap 局部内容及其 odom 构建依据；历史 map 位姿由 SLAM 提供。","parts":[["Local BEV OCC · 已确认","输出局部鸟瞰占用观测，服务 Nav Map 的动态局部地图层。"],["Odom 累计 · 已确认","多帧感知只依据 odom 叠加，不把 map 修正注入正在构建的感知内容。"],["重叠双 Submap · 已确认","采用用户所述类似 Cartographer 的部分重叠设计；尺寸、切换与完成条件待细化。"],["Submap 关联元数据 · 建议","提供稳定标识、参考时刻、局部坐标与 odom 锚点；注册到 SLAM 的具体协议待讨论。"],["观测质量输出","向决策进程的 Anomaly 提供算法异常、感知结果和质量依据。"]],"boundary":"Percep 可作为 SLAM 库。Submap 内容坐标与原点在 map 下的位姿是不同数据；位姿优化不要求重新以 map 坐标堆叠感知观测。","role":"Server · 能力服务"},
    {"id":"navmap","name":"Nav Map","cn":"多层地图 · Costmap","x":330,"y":500,"kind":"map","tag":"用户确认","summary":"维护局部动态层与 Submap 障碍物地图，消费 Map Server 提供的版本化轨迹几何约束，生成供两级 planner 使用的 costmap。 部署于规控进程，与 Global / Local planner 同进程。","owns":"局部 / 障碍物地图层、融合状态、运行时 costmap 与当前加载的资产版本；不再拥有持久化边界轨迹主副本。","parts":[["局部动态层 · 已确认","local BEV OCC 转成以机器人为中心的 local costmap。"],["障碍物地图层 · 已确认","依据 Submap 与 SLAM 原点 map pose 堆叠、更新可保存障碍物地图。"],["轨迹约束投影 · 建议","按指定版本读取 Map Server 的起终点、path 和草坪 / 通道属性，派生导航边界与通行约束；不重新平滑、合并或维护拓扑主数据。"],["边界只读视图","已保存边界轨迹内容与 map 坐标均冻结，SLAM 优化不得修改；Nav Map 只维护消费视图，不能反写 Map Server 的轨迹资产。"],["Costmap 服务 · 已确认","向 Global / Local planner 直接提供 global / local costmap，回报当前加载版本及可用性。"],["文件协作 · 建议","自己生成与解析导航栅格、障碍图文件，由 Map Server 纳入对应地图版本；失败不能留下混合版本。"]],"boundary":"Nav Map 不分配业务轨迹 ID、不维护拓扑主副本。通道 path 是否为中心线及其宽度、草坪边界的闭合规则需明确；不能仅凭一条 path 猜出可通行面。割草角度 / 高度是作业配置，不直接变成 costmap 代价。","role":"Server · 能力服务"},
    {"id":"map","name":"Map Server","cn":"轨迹 · 拓扑 · 地图文件","x":330,"y":300,"kind":"map","tag":"用户修订 · 2026-11-03","summary":"隶属决策模块；沿用 Map Server 名称，处理 SLAM PoseGraph 轨迹、维护轨迹拓扑，并与 Business_core 共同维护地图文件夹。","owns":"处理后的轨迹几何（起点、终点、path）、拓扑关系及文件组织；ID 属性和作业配置的业务语义由 Business_core 提供。","parts":[["轨迹处理 · 已确认","接收 SLAM PoseGraph 轨迹，进行平滑、完整性检查及合并 / 分割，保存起点、终点与 path。"],["拓扑维护 · 已确认","记录、维护轨迹之间的连接关系；编辑后重新校验端点、引用与连接，具体判据待定义。"],["文件管理 · 已确认","保存、读取和维护轨迹、拓扑、ID 属性及地图配置；继续接收配套 SLAM / Nav Map 文件。"],["业务协作 · 已确认","采用 Business_core 提供的轨迹 ID、草坪 / 通道属性、割草角度与高度，保持跨文件对应一致。"],["保存与编辑 · 用户确认","已保存边界轨迹内容与 map 坐标均冻结，SLAM 优化不得修改。显式合并 / 分割产生新版本，并重新校验拓扑。"],["服务与提交 · 建议","异步处理、校验、保存 / 读取 / 删除；返回请求结果和明确版本，缺失 ID、悬空拓扑引用或配套失败不能报告整体成功。"]],"boundary":"新职责替代旧版“仅文件服务”。Map Server 处理持久化轨迹资产，不负责 Submap 障碍融合或运行时 costmap，也不把存储 path 当作当前可执行规划路线。平滑不得默默改变连接端点；阈值、方向、闭合和分割规则待细化。","role":"决策子模块 · 资产服务","parent":"decision"},
    {"id":"global","name":"Global planner","cn":"全局规划","x":660,"y":500,"kind":"plan","tag":"用户确认","summary":"消费 Nav Map 的 global costmap 与 SLAM TF，按 Decision 异步请求生成几何路径 / 作业路线，将结果仅交回 Decision。","owns":"当前规划请求及对应几何路线。","parts":[["目标处理","解释目标点或区域约束；覆盖规划是否包含在内待确认。"],["路线求解","生成几何路径 / 作业路线返回 Decision，由其向 Local planner 下发执行任务。"],["结果反馈","向 Decision 返回路径与规划结果；成功、无解、取消及失败的具体反馈协议待定。"]],"boundary":"与 Local planner 无直接交互；路径、取消与重规划均经 Decision 协调。不从 Map Server 获取运行时 costmap，覆盖历史归属仍待定。","role":"Server · 全局规划"},
    {"id":"local","name":"Local planner","cn":"局部规划与跟踪","x":980,"y":500,"kind":"plan","tag":"用户确认","summary":"接收 Decision 下发的路径与执行请求，消费 Nav Map 的 local costmap、SLAM TF 和底板轮速，生成可执行运动；进度和阻塞反馈给 Decision。","owns":"当前路径的局部执行状态与速度候选。","parts":[["局部规划","依据环境与机器人约束进行局部避障。"],["路径跟踪","将路线转换为 v / ω；跟踪器的实际归属待核对。"],["轮速输入 · 已确认","接收底板轮速用于局部规划 / 跟踪；采样时刻、单位、时效和失效处理需定义。"],["执行反馈","建议返回进度、到达、阻塞、失败和停止结果。"]],"boundary":"不直接向 Global 请求重规划或接收路径，统一由 Decision 协调。与 Recovery 互斥输出运动请求；轮速用于局部规划 / 跟踪，不替代 SLAM 的权威 odom / TF。服务执行不得阻塞 Decision。","role":"Server · 局部执行"},
    {"id":"recovery","name":"Recovery","cn":"恢复动作","x":660,"y":780,"kind":"control","tag":"手绘模块","summary":"在决策授权范围内执行有限的恢复动作。","owns":"单次恢复动作的执行状态与结果。","parts":[["恢复执行","实现候选脱困动作，具体动作集待定义。"],["有界退出","建议限制时长、距离和重试次数，支持取消。"],["结果报告","向决策反馈成功、失败或已停止。"]],"boundary":"恢复也必须服从系统停止与运动许可；不独立决定业务恢复或重新开始割草。","role":"Server · 能力服务"},
    {"id":"motion","name":"Motion","cn":"运动执行","x":980,"y":780,"kind":"act","tag":"手绘模块","summary":"接收 v / ω，将运动请求落实到电机接口。","owns":"最终运动输出、当前控制来源与执行有效性（建议）。","parts":[["命令接入","接入 Local planner / Recovery 的速度请求。"],["运动约束","建议统一检查控制权、命令时效、速度限制与系统许可。"],["底盘执行","输出电机请求并解释设备反馈；闭环所在层待核对。"]],"boundary":"建议在最终执行入口保证单一有效命令源；具体仲裁实现位置待定。发送零速不等于已停稳。","role":"Server · 能力服务"},
    {"id":"motor","name":"Motor","cn":"底盘 / 电机","x":1280,"y":780,"kind":"external","tag":"硬件边界","summary":"执行运动输出，并提供可用的设备事实。","owns":"真实轮速、故障和停止状态等设备事实；反馈能力待核实。","parts":[["驱动执行","接收底盘侧运动请求。"],["设备反馈","反馈实际运动与故障；不以命令值代替测量值。"]],"boundary":"本图不展开驱动、刀盘与硬件安全设计；并不表示整机可以省略这些能力。","role":"外部输入 / 输出"},
    {"id":"tf","name":"TF 广播","cn":"base_link → odom → map","x":30,"y":165,"kind":"sense","role":"SLAM 公共输出 · 非独立服务","tag":"用户确认","summary":"SLAM 提供的公共定位接口，各模块按需订阅；图中独立画出只是为了清晰表达广播关系。","owns":"权威发布者是 SLAM；这不是新增的 TF 算法模块或独立进程。","parts":[["坐标链 · 已确认","提供 base_link → odom → map；图中文字表达坐标转换链，父子边与矩阵方向必须在协议里明确。"],["按需广播 · 已确认方向","向各定位消费者分发；代表连线绘出 Percep、Nav Map 和两级 planner，其他模块也可订阅。"],["时间与有效性 · 建议","携带采样时间、source / target frame 和有效性；查询时间不匹配时不得默认为有效。"]],"boundary":"当前 TF 不能代替历史 Submap 的逐项 map pose。Percep 累计只消费 odom 关系；Nav Map 负责把 Submap 放到 map 系。"},
    {"id":"anomaly","name":"Anomaly Detection","cn":"算法 + 硬件异常检测","x":30,"y":780,"kind":"control","role":"决策子模块 · 异常检测","tag":"用户修订 · 2026-11-03","summary":"隶属决策模块。接收算法端异常与诊断依据，也接收撞板、电机故障 / 堵转、刀盘堵转等底板信号，统一检测、整理后发给 Decision 调度核心。","owns":"异常检测状态、证据及事件有效性；任务处置策略归 Decision。","parts":[["多来源异常输入 · 用户确认","算法异常和底板撞板、电机、刀盘堵转等信号统一进入 Anomaly；保留原始来源、时间和有效性，不能把不同原因合并为一种故障。"],["打滑检测 · 已确认范围","结合定位 / 感知质量及可用运动观测；是否直连底板轮速待讨论。"],["相机遮挡 · 已确认范围","基于感知观测质量产生遮挡事件；恢复判据待定义。"],["LiDAR 算法侧异常 · 已确认范围","识别算法可判断的点云或定位异常，与硬件直接上报的故障区分。"],["异常事件生命周期 · 建议","上报出现、持续、恢复，带来源、时间、有效性和证据；去抖与阈值待定。"],["事件整理 · 建议","统一输出异常出现 / 持续 / 恢复事件，保留类别与证据；去抖、去重、分级和失联判断待定义。检测过程不得阻塞调度核心。"]],"boundary":"对 SLAM / Percep 的依赖是数据依赖，部署在决策进程。打滑、堵转、撞板必须保留各自来源与含义；Anomaly 负责异常事实，Decision 负责策略。算法侧其他异常来源的接入清单待细化。","parent":"decision"},
    {"id":"board","name":"Baseboard","cn":"撞板 · 电机 · 刀盘 · 轮速","x":1280,"y":40,"kind":"external","role":"硬件事件 / 测量输入","tag":"用户新增","summary":"向 Anomaly 提供撞板、电机故障 / 堵转、刀盘堵转等信号；轮速作为测量继续直接提供给 Local planner。","owns":"底板原始异常信号、轮速测量及采样时间。","parts":[["硬件异常信号 · 用户确认","撞板、电机和刀盘堵转等信号送入 Anomaly，由其检测整理后报告 Decision，不直接绕过 Anomaly。"],["轮速 · 已确认消费者","轮速提供给 Local planner 用于规划 / 跟踪；不把原始轮速等同于完整 odom。"]],"boundary":"信号电平、触发 / 恢复事件、失联与有效性需约定。图中 Motor 表示执行对象，Baseboard 表示信号来源，不断言它们是两块硬件。"}
  ],
  edges: [
    {"id":"sensor-slam","from":"sensors","to":"slam","type":"data","label":"LiDAR · IMU · Odom","path":"M30 72 H12 V342 H30","lx":100,"ly":280,"origin":"手绘关系","meaning":"原始定位观测进入 SLAM。","contract":"采样时间、标定、单位、观测有效性和同步策略需约定。"},
    {"id":"camera-percep","from":"camera","to":"percep","type":"data","label":"图像","path":"M120 650 V584","lx":145,"ly":625,"origin":"手绘关系","meaning":"相机观测进入 Percep。","contract":"图像时间、标定、格式与对时容差。"},
    {"id":"slam-percep","from":"slam","to":"percep","type":"data","label":"去畸变点云","path":"M120 384 V500","lx":160,"ly":430,"origin":"手绘关系","meaning":"提供用于环境感知的点云。","contract":"参考时刻、坐标系和观测有效性。"},
    {"id":"slam-tf","from":"slam","to":"tf","type":"data","label":"TF 发布","path":"M170 300 V249","lx":199,"ly":275,"origin":"用户确认","meaning":"SLAM 是 base_link → odom → map 公共坐标关系的发布者。","contract":"明确变换方向、采样时间、有效性、更新频率；各模块按需订阅。"},
    {"id":"tf-percep","from":"tf","to":"percep","type":"data","label":"仅 odom","path":"M210 222 H248 V478 H170 V500","lx":258,"ly":477,"origin":"用户确认","meaning":"Percep 仅依据 odom 进行多帧累计，不用 map 位姿修正感知内容。","contract":"建议固定 Submap 局部坐标；odom 重置或时间断裂需切换会话，具体规则待讨论。"},
    {"id":"tf-nav","from":"tf","to":"navmap","type":"data","label":"TF / 当前定位","path":"M210 207 H560 V470 H460 V500","lx":437,"ly":199,"origin":"用户确认","meaning":"为 Nav Map 局部窗口和地图坐标转换提供当前定位；持久化建图轨迹来自 SLAM PoseGraph，经 Map Server 处理。","contract":"建议检查时间与有效性；历史 Submap 校正仍走专用位姿更新接口。"},
    {"id":"tf-global","from":"tf","to":"global","type":"data","label":"TF 按需订阅","path":"M210 180 H900 V455 H800 V500","lx":814,"ly":173,"origin":"用户确认","meaning":"Global planner 从公共 TF 获取当前定位。","contract":"路径与地图坐标版本一致；失效或跳变后的重规划策略待定义。"},
    {"id":"tf-local","from":"tf","to":"local","type":"data","label":"TF 按需订阅","path":"M210 239 H1135 V500","lx":1055,"ly":232,"origin":"用户确认","meaning":"Local planner 从公共 TF 获取实时定位。","contract":"不得把广播收到等同有效；时间滞后和定位失效处理待定。"},
    {"id":"percep-nav","from":"percep","to":"navmap","type":"data","label":"local BEV OCC","path":"M210 520 H330","lx":270,"ly":510,"origin":"用户确认","meaning":"实时 BEV OCC 进入 Nav Map 的局部动态层。","contract":"坐标系、范围、分辨率、未知语义和观测时间；Nav Map 生成以机器人为中心的 local costmap。"},
    {"id":"percep-submap","from":"percep","to":"navmap","type":"data","label":"重叠 Submap","path":"M210 564 H330","lx":270,"ly":589,"origin":"用户确认","meaning":"多帧累计、两张部分重叠的 Submap 供 Nav Map 堆叠障碍物地图。","contract":"建议携带 submap_id、局部内容、odom 锚点、参考时刻、内容版本与 active / finished 状态；具体 schema 待讨论。"},
    {"id":"submap-register","from":"percep","to":"slam","type":"data","label":"锚点登记（建议）","path":"M75 500 V384","lx":55,"ly":465,"origin":"补充建议","meaning":"为 SLAM 关联感知 Submap 与历史定位节点提供登记路径。","contract":"建议登记 submap_id、参考时间、T_odom_submap 或可关联历史节点；由 Percep 直送还是 Nav Map 转交、PoseGraph 如何关联尚未定稿。"},
    {"id":"submap-pose","from":"slam","to":"navmap","type":"data","label":"Submap 原点 map pose","path":"M210 365 H280 V435 H435 V500","lx":355,"ly":425,"origin":"用户确认","meaning":"SLAM 提供机制更新每个历史 Submap 原点在 map 坐标系下的 pose。","contract":"建议输出 submap_id、T_map_submap、优化批次 / 版本与有效性；Nav Map 按同一批次重拼接，不能把当前 TF 直接当所有历史原点的校正。"},
    {"id":"nav-map","from":"navmap","to":"map","type":"data","label":"导航地图文件","path":"M390 500 V384","lx":367,"ly":416,"origin":"用户修订","meaning":"Nav Map 输出障碍地图 / 导航地图文件，由 Map Server 与轨迹、拓扑、ID 属性和配置关联保存。","contract":"建议携带资产版本、坐标依据与构建结果；不将 Nav Map 的派生边界视图当作轨迹主副本反写。"},
    {"id":"map-nav","from":"map","to":"navmap","type":"data","label":"文件结果 / 读取","path":"M500 384 V500","lx":531,"ly":393,"origin":"用户修订","meaning":"Map Server 响应导航文件读取，Nav Map 自行加载障碍图 / 导航图；轨迹约束另走明确的资产接口。","contract":"文件与轨迹约束必须属于匹配的地图版本；读取成功不等于 Nav Map 已就绪。"},
    {"id":"slam-map","from":"slam","to":"map","type":"data","label":"SLAM 文件","path":"M210 325 H330","lx":270,"ly":314,"origin":"用户修订","meaning":"SLAM 提交自身序列化地图文件。","contract":"SLAM 决定格式与内容，Map Server 负责存储和文件配套，不进行地图几何对齐。"},
    {"id":"map-slam","from":"map","to":"slam","type":"data","label":"文件结果 / 读取","path":"M330 355 H210","lx":270,"ly":375,"origin":"用户确认","meaning":"响应 SLAM 的文件存取请求，提供结果或对应文件，由 SLAM 自行加载。","contract":"使用匹配会话 / 版本；缺失、损坏或不匹配必须报告，不默认为可用。"},
    {"id":"nav-global","from":"navmap","to":"global","type":"data","label":"global costmap","path":"M510 538 H660","lx":585,"ly":528,"origin":"用户修订","meaning":"Global planner 直接消费 Nav Map 的 global costmap。","contract":"明确地图版本、坐标、代价层融合、膨胀和未知空间策略；不经过 Map Server。"},
    {"id":"nav-local","from":"navmap","to":"local","type":"data","label":"local costmap","path":"M510 562 H610 V650 H1020 V584","lx":790,"ly":642,"origin":"用户修订","meaning":"Local planner 直接消费 Nav Map 提供的以机器人为中心的 local costmap。","contract":"窗口原点随车更新；时间、分辨率、地图朝向与动态观测过期语义需定义。"},
    {"id":"business-cmd","from":"business","to":"decision","type":"command","label":"cmd · 任务请求","path":"M510 65 H660","lx":585,"ly":55,"origin":"手绘关系","meaning":"业务核心提交当前任务与约束。","contract":"建议业务请求绑定目标轨迹 ID、地图 / 配置版本与任务参数；轨迹 ID、草坪 / 通道属性及割草配置由 Business_core 提供。"},
    {"id":"business-state","from":"decision","to":"business","type":"feedback","label":"state / resp","path":"M660 100 H510","lx":585,"ly":123,"origin":"手绘关系","meaning":"决策向业务返回受理、状态与终态。","contract":"受理不等于完成；业务策略和算法调度的边界需细化。"},
    {"id":"decision-slam","from":"decision","to":"slam","type":"command","label":"定位 / 建图请求","path":"M680 124 V145 H270 V305 H210","lx":420,"ly":139,"origin":"用户确认","meaning":"Decision 以 client 方式调度 SLAM 的能力服务。","contract":"具体命令集待定；耗时定位 / 建图异步执行，不阻塞 Decision；回执见服务协议说明。"},
    {"id":"decision-nav","from":"decision","to":"navmap","type":"command","label":"加载 / 构建 / 切换","path":"M700 124 V155 H305 V480 H350 V500","lx":365,"ly":475,"origin":"用户确认","meaning":"Decision 非阻塞请求 Nav Map 加载 Map Server 的指定资产版本，构建 / 更新 costmap 并准备导航。","contract":"建议携带 map_version、目标区域 / 轨迹 ID；等相同请求和版本的就绪回执再启动规划，不阻塞事件循环。"},
    {"id":"decision-map","from":"decision","to":"map","type":"command","label":"处理 / 保存 / 编辑","path":"M710 124 V270 H420 V300","lx":535,"ly":263,"origin":"用户修订","meaning":"建议由 Decision 异步请求 Map Server 处理轨迹、校验拓扑并保存或编辑地图资产；不在 Decision 内进行几何计算。","contract":"建议请求含 request_id、base_version、目标轨迹 ID 与处理意图；合并 / 分割新 ID 由 Business_core 提供，成功返回新版本，旧保存版本不被覆盖。"},
    {"id":"decision-global","from":"decision","to":"global","type":"command","label":"规划请求","path":"M735 124 V500","lx":762,"ly":416,"origin":"手绘关系","meaning":"非阻塞提交全局规划目标。","contract":"服务端快速返回受理，规划结果异步返回；超时、取消与迟到结果隔离为建议。"},
    {"id":"decision-local","from":"decision","to":"local","type":"command","label":"路径下发 / 执行 / 取消","path":"M840 64 H1070 V500","lx":1130,"ly":350,"origin":"用户确认","meaning":"Decision 将 Global 返回的路径交给 Local，并统一调度执行、替换或取消；Local 不直接与 Global 交互。","contract":"建议同一执行请求关联路径与地图版本，明确替换 / 取消语义。发出后继续处理 Anomaly 事件，实际停止通过反馈确认，不同步等待。"},
    {"id":"decision-recovery","from":"decision","to":"recovery","type":"command","label":"恢复授权","path":"M840 100 H940 V740 H750 V780","lx":903,"ly":729,"origin":"手绘关系","meaning":"决策调度有界恢复服务。","contract":"建议先撤销旧控制权并异步确认停止，再授权恢复；次数、距离和时长预算待定。"},
    {"id":"local-motion","from":"local","to":"motion","type":"command","label":"v / ω","path":"M1070 584 V780","lx":1093,"ly":705,"origin":"手绘关系","meaning":"局部执行产生速度请求。","contract":"建议含控制源、时效和任务关联；过期指令不可继续执行。"},
    {"id":"recovery-motion","from":"recovery","to":"motion","type":"command","label":"v / ω","path":"M840 822 H980","lx":910,"ly":813,"origin":"手绘关系","meaning":"恢复动作产生速度请求。","contract":"与 Local planner 互斥；控制权移交和迟到命令拒绝规则待定。"},
    {"id":"motion-motor","from":"motion","to":"motor","type":"command","label":"运动输出","path":"M1160 822 H1280","lx":1220,"ly":813,"origin":"手绘关系","meaning":"最终速度请求进入底盘执行。","contract":"速度限制、底板接口及失联停止机制待核对。"},
    {"id":"slam-anomaly","from":"slam","to":"anomaly","type":"data","label":"定位异常 / 诊断依据","path":"M45 384 H20 V820 H30","lx":132,"ly":753,"origin":"用户确认","meaning":"SLAM 向决策进程的 Anomaly 提供算法异常、定位质量与运动诊断依据。","contract":"具体证据、有效性和时序待定；算法异常不等同硬件故障。"},
    {"id":"percep-anomaly","from":"percep","to":"anomaly","type":"data","label":"感知异常 / 观测质量","path":"M210 550 H235 V822 H210","lx":289,"ly":682,"origin":"用户确认","meaning":"Percep 向决策进程的 Anomaly 提供算法异常和观测质量，用于遮挡、LiDAR 等异常检测。","contract":"跨进程输入；具体证据、时间与有效性，以及检测阈值、去抖、恢复条件待定义。"},
    {"id":"anomaly-decision","from":"anomaly","to":"decision","type":"feedback","label":"统一异常事件","path":"M210 848 H595 V400 H805 V124","lx":486,"ly":841,"origin":"用户确认","meaning":"Anomaly 汇总算法端和硬件端异常，向同属决策模块的 Decision 调度核心输出异常事实，由状态机选择策略。","contract":"建议包含来源、类型、出现 / 恢复、证据、时间与有效性；去抖、优先级、事件洪泛处理待定，同进程也不能阻塞调度。"},
    {"id":"board-anomaly","from":"board","to":"anomaly","type":"feedback","label":"撞板 / 电机 / 刀盘堵转","path":"M1460 82 H1470 V920 H120 V864","lx":1230,"ly":914,"origin":"用户确认","meaning":"底板硬件异常统一进入 Anomaly 检测与整理，再发给 Decision 调度核心。","contract":"需约定信号类型、采样时间、有效性、出现 / 恢复及失联语义；轮速测量仍独立发送 Local planner。"},
    {"id":"wheel-local","from":"board","to":"local","type":"data","label":"轮速","path":"M1370 124 V455 H1160 V520","lx":1280,"ly":446,"origin":"用户确认","meaning":"底板轮速输入 Local planner，用于局部规划和跟踪；此接口不指向 Nav Map。","contract":"定义轮速单位、采样时间、频率、有效性及过期处理；与 TF / costmap 对时，不替代 SLAM odom。"},
    {"id":"map-state","from":"map","to":"decision","type":"feedback","label":"资产结果 / 版本","path":"M490 300 V285 H770 V124","lx":650,"ly":280,"origin":"补充建议","meaning":"Map Server 异步报告轨迹处理、拓扑校验、保存或编辑的结果与版本。","contract":"建议区分受理、处理完成与保存提交成功；提供失败原因、新旧 ID 映射和版本摘要。保存成功不等于 Nav Map 地图已就绪。"},
    {"id":"nav-state","from":"navmap","to":"decision","type":"feedback","label":"导航就绪 / 版本","path":"M510 520 H565 V315 H825 V124","lx":670,"ly":309,"origin":"补充建议","meaning":"Nav Map 回报指定地图版本的加载、构建和切换结果及当前可用性。","contract":"建议携带 request_id 与 map_version；未就绪或版本不匹配不得启动该版本规划。失败时保留仍有效旧视图或进入不可用状态，由 Decision 按策略处理。"},
    {"id":"global-state","from":"global","to":"decision","type":"feedback","label":"几何路径 / 规划结果","path":"M790 500 V124","lx":865,"ly":475,"origin":"用户确认","meaning":"Global planner 将几何路径 / 作业路线和规划结果交回 Decision，不直接发送给 Local planner。","contract":"建议关联任务、请求、路径与地图版本；Decision 核验仍是当前任务后下发 Local，取消后的迟到路径不能触发执行。"},
    {"id":"local-state","from":"local","to":"decision","type":"feedback","label":"进度 / 阻塞 / 停止","path":"M1120 500 V145 H815 V124","lx":1040,"ly":140,"origin":"用户确认","meaning":"Local 将执行进度、阻塞与终态回报 Decision，由 Decision 决定是否请求 Global 重规划；不直接联系 Global。","contract":"停止受理与实际停稳分开；取消等待期间状态机仍处理其他事件。"},
    {"id":"recovery-state","from":"recovery","to":"decision","type":"feedback","label":"恢复结果","path":"M840 850 H965 V130 H830 V124","lx":966,"ly":767,"origin":"补充建议","meaning":"恢复服务报告完成、失败或已取消。","contract":"释放控制权与恢复结果关联，不直接决定业务继续。"},
    {"id":"motor-state","from":"motor","to":"motion","type":"feedback","label":"设备事实","path":"M1280 850 H1160","lx":1220,"ly":874,"origin":"补充建议","meaning":"设备侧提供实际运动、故障或停止反馈。","contract":"真实反馈能力仍需核对，发送零速不代表已停稳。"},
    {"id":"motion-state","from":"motion","to":"local","type":"feedback","label":"执行反馈","path":"M1130 780 V584","lx":1170,"ly":739,"origin":"补充建议","meaning":"向局部执行提供 Motion 的实际执行状态。","contract":"时间、来源、有效性与缺失处理待定。"},
    {"id":"slam-state","from":"slam","to":"decision","type":"feedback","label":"定位 / 建图结果","path":"M210 340 H225 V160 H760 V124","lx":655,"ly":153,"origin":"补充建议","meaning":"SLAM 异步回报定位 / 建图服务结果，实时 TF 不能代替任务终态回执。","contract":"关联请求标识、成功 / 失败 / 取消及原因；Decision 不同步等待 SLAM，超时和迟到结果处理待设计。"},
    {"id":"slam-trajectory","from":"slam","to":"map","type":"data","label":"PoseGraph 轨迹","path":"M120 384 V410 H310 V365 H330","lx":225,"ly":402,"origin":"用户确认","meaning":"SLAM 提供 PoseGraph 轨迹，Map Server 进行平滑、完整性检查和合并 / 分割。","contract":"建议关联建图会话、采样 / 节点标识、坐标与轨迹版本；在明确快照上处理，保存边界不可被后续 SLAM 优化回写。"},
    {"id":"business-map","from":"business","to":"map","type":"data","label":"ID / 属性 / 配置","path":"M365 124 V300","lx":367,"ly":166,"origin":"用户确认","meaning":"Business_core 提供轨迹 ID、草坪 / 通道等属性、割草角度与高度配置，与 Map Server 共同维护地图文件夹。","contract":"ID 唯一性、类型和配置语义以业务侧为准；建议关联版本与编辑请求，避免合并 / 分割后旧 ID、属性或配置错配。"},
    {"id":"map-business","from":"map","to":"business","type":"feedback","label":"版本 / ID 对应","path":"M480 300 V124","lx":491,"ly":251,"origin":"补充建议","meaning":"Map Server 向 Business_core 返回处理 / 保存结果、版本与新旧轨迹对应关系，使业务记录和文件保持一致。","contract":"新轨迹 ID 由 Business_core 提供；缺失属性、悬空引用、合并属性冲突需反馈，不能静默选值或覆盖旧版本。"},
    {"id":"map-constraints","from":"map","to":"navmap","type":"data","label":"轨迹 / 几何约束","path":"M350 384 V470 H365 V500","lx":331,"ly":463,"origin":"补充建议","meaning":"Map Server 按指定版本提供起点、终点、path 及草坪 / 通道等几何相关属性，Nav Map 派生导航约束。","contract":"导航使用的约束须与障碍图坐标和版本一致；拓扑主数据仍归 Map Server。拓扑最终由 Decision 还是 Global planner 用于跨区域路由待讨论，不默认复制到 Nav Map。"}
  ],
  questions: [
    ["待讨论","历史 Submap 与 PoseGraph","已确认 SLAM 需提供历史 Submap 原点的 map pose。如何关联感知 Submap 与 SLAM 节点？注册由谁发起？约束、优化批次、锚点生命周期和 odom 重置如何处理？"],
    ["待细化","双 Submap 与地图融合","两个部分重叠 Submap 的尺寸、切换、完成条件是什么？Nav Map 如何处理重叠贡献、活动子图更新、历史位姿修正和动态障碍残留？"],
    ["已确认","保存冻结与显式编辑","已保存边界轨迹的内容与 map 坐标冻结，SLAM 不得自动改写。合并 / 分割产生新版本并重新校验拓扑；新版本何时切换由调度决定。"],
    ["来源已确认 / 协议待定","业务 ID 与共同维护文件夹","Business_core 提供轨迹 ID、草坪 / 通道属性与角度 / 高度配置。每类文件由谁写、如何提交一致版本、新旧 ID 如何映射、合并属性冲突如何处理仍需定义。建议每类文件唯一写入者，统一提交配套版本。"],
    ["已确认 / 待细化","轮速与局部窗口","已确认底板轮速输入 Local planner，不是 Nav Map。轮速单位、对时、有效性与失效处理，以及局部窗口朝向、分辨率和过期策略仍需细化。"],
    ["待细化","非阻塞与异常策略","状态机如何处理并发事件、取消超时和迟到结果？堵转、打滑、遮挡、LiDAR 异常如何分级、去抖、恢复？各 server 的完成回执和停止事实如何闭环？"],
    ["范围待定","覆盖、沿边、对桩与刀盘","本次重点为定位、地图和调度。建图边界轨迹不等于覆盖历史；全覆盖、沿边、对桩及刀盘能力仍需结合产品范围细化。"],
    ["待细化","轨迹、拓扑与规划的接口","Map Server 保存的 path 是地图资产，不等于 Global planner 的当前规划路线。起终点定义、平滑边界条件、完整性判据、连接方向 / 容差、通道宽度与草坪闭合规则待定；跨区域拓扑由 Decision 还是 Global planner 消费也需明确。"],
    ["已确认 / 细节待定","三个进程与内部异步执行","感知定位：SLAM / Percep；决策：调度核心 / Anomaly / Map Server；规控：Nav Map / Global / Local，Recovery / Motion 暂归规控。Business_core 保持外部业务角色。同进程不等于同步执行，地图处理、异常检测与调度核心的调度隔离、队列和过载处理待细化。"]
  ],
  scenarios: {
    "navigate": {
      "name": "规划与执行",
      "steps": [
        [
          "business-cmd",
          "接收业务任务",
          "业务请求进入 Decision 状态机。"
        ],
        [
          "decision-nav",
          "异步请求地图准备",
          "Decision 异步请求 Nav Map 准备已保存的明确资产版本，发出后继续处理事件。"
        ],
        [
          "nav-state",
          "接收地图就绪事件",
          "核对 Nav Map 返回的请求标识和资产版本；Map Server 保存成功不能代替此回执。"
        ],
        [
          "decision-global",
          "提交规划请求",
          "Planner 以 server 形式执行，Decision 继续接收异常事件。"
        ],
        [
          "nav-global",
          "直接取 global costmap",
          "运行时 costmap 来自 Nav Map，不由 Map Server 提供。"
        ],
        [
          "global-state",
          "规划结果回到 Decision",
          "Global 返回几何路径和结果；建议 Decision 校验当前任务、请求及地图版本，隔离迟到结果。"
        ],
        [
          "decision-local",
          "Decision 下发路径与执行请求",
          "Local 仅接收 Decision 的路径与调度，不与 Global 直接交互；具体路径交接和替换协议待定。"
        ],
        [
          "nav-local",
          "读取中心局部地图",
          "Nav Map 提供以机器人为中心的 local costmap。"
        ],
        [
          "wheel-local",
          "接收底板轮速",
          "Local planner 使用轮速进行局部规划 / 跟踪，需检查时间与有效性。"
        ],
        [
          "local-motion",
          "输出速度请求",
          "Local planner 根据定位、路线和环境生成 v / ω。"
        ],
        [
          "local-state",
          "异步接收执行结果",
          "进度、阻塞或停止事实回到 Decision；如需重规划，由 Decision 再调用 Global。"
        ]
      ]
    },
    "recover": {
      "name": "异常与恢复",
      "steps": [
        [
          "board-anomaly",
          "硬件信号进入 Anomaly",
          "撞板、电机和刀盘堵转等信号先进入 Anomaly；算法异常通过各自输入并行汇入，不要求先发生硬件故障。"
        ],
        [
          "anomaly-decision",
          "统一异常报告给调度核心",
          "Anomaly 保留异常来源与类别，向 Decision 报告；打滑与堵转不会被当作同一事实。"
        ],
        [
          "decision-local",
          "按策略请求停止",
          "此处演示一种候选恢复流程，并非所有异常都执行同一策略。"
        ],
        [
          "local-state",
          "异步确认停止",
          "状态机处于等待状态，但事件循环继续工作；超时策略待定。"
        ],
        [
          "decision-recovery",
          "授权有界恢复",
          "确认执行条件与控制权切换，再调度恢复服务。"
        ],
        [
          "recovery-state",
          "异步接收结果",
          "恢复成功不等于业务完成，失败是否升级由策略决定。"
        ]
      ]
    },
    "mapping": {
      "name": "BEV → 局部地图",
      "steps": [
        [
          "slam-tf",
          "广播坐标关系",
          "所有定位消费者按需订阅；发布者仍是 SLAM。"
        ],
        [
          "slam-percep",
          "提供去畸变点云",
          "Percep 结合图像产生环境观测。"
        ],
        [
          "percep-nav",
          "输出 local BEV OCC",
          "这是实时观测，不是持久化障碍物地图。"
        ],
        [
          "tf-nav",
          "确定局部窗口中心",
          "Nav Map 使用当前机器人位置维护中心窗口，朝向策略待定。"
        ],
        [
          "nav-local",
          "提供 local costmap",
          "转换和地图层维护归 Nav Map，Local planner 直接消费。"
        ]
      ]
    },
    "submap": {
      "name": "Submap → 位姿修正",
      "steps": [
        [
          "tf-percep",
          "只用 odom 累计",
          "Percep 在局部参考下累计，map 修正不注入观测堆叠。"
        ],
        [
          "percep-submap",
          "输出两张部分重叠 Submap",
          "Nav Map 接收子图内容和关联元数据，具体协议待定。"
        ],
        [
          "submap-register",
          "建立历史锚点关联（建议）",
          "提供 submap_id 与历史依据；直送 SLAM 还是转交仍待讨论。"
        ],
        [
          "submap-pose",
          "更新原点的 map pose",
          "SLAM 内部 PoseGraph 类设计尚未确定，向外提供逐 Submap 位姿修正。"
        ],
        [
          "nav-global",
          "更新障碍物地图与 costmap",
          "建议替换旧位姿贡献或重建区域，避免重叠和旧位置重复叠加。"
        ]
      ]
    },
    "files": {
      "name": "轨迹处理 → 导航就绪",
      "steps": [
        [
          "business-map",
          "提供业务 ID、属性和配置",
          "Business_core 提供对应数据；Map Server 不自行猜测草坪 / 通道类型或新业务 ID。"
        ],
        [
          "slam-trajectory",
          "取得 PoseGraph 轨迹快照",
          "SLAM 输出原始轨迹及坐标依据；后续处理不由 Nav Map 承担。"
        ],
        [
          "decision-map",
          "非阻塞请求处理与保存",
          "Map Server 平滑、检查、合并 / 分割并更新拓扑；具体命令格式为建议。"
        ],
        [
          "map-business",
          "对齐编辑后的业务对应",
          "编辑产生新轨迹时反馈新旧对应，请 Business_core 补齐新 ID、属性与配置，之后才可完整提交。"
        ],
        [
          "business-map",
          "补齐新 ID 与属性",
          "新旧对应和冲突处理协议待定；不能沿用已失效的拓扑或业务引用。"
        ],
        [
          "nav-map",
          "配套导航文件就绪",
          "需要持久化的障碍图 / 导航文件由 Nav Map 提供；实际可并行准备，图中顺序仅作示意。"
        ],
        [
          "map-state",
          "接收资产保存结果",
          "成功返回明确新版本；缺少配套文件或 ID 时不能报告整体成功，旧版本继续冻结。"
        ],
        [
          "decision-nav",
          "请求加载同一版本",
          "Decision 收到保存完成后，异步请求 Nav Map 加载该版本。"
        ],
        [
          "map-constraints",
          "读取轨迹几何约束",
          "Nav Map 只读取和投影，不重新平滑轨迹、不接管拓扑主数据。"
        ],
        [
          "map-nav",
          "读取配套导航文件",
          "文件、轨迹约束与坐标依据需匹配版本。"
        ],
        [
          "nav-state",
          "确认导航就绪",
          "区分文件保存成功和 costmap 可用；回执必须匹配请求及版本。"
        ],
        [
          "decision-global",
          "启动规划",
          "同版本导航就绪后再授权规划；过期回执或失败不能放行。"
        ]
      ]
    }
  },
  topics: {
    "main": {
      "name": "系统总览",
      "note": "Global → Decision → Local 统一交接路径；算法与硬件异常 → Anomaly → Decision。Anomaly / Map Server 隶属决策模块，TF 仍供 Percep、Nav Map 和两级 planner 使用。",
      "edges": [
        "sensor-slam",
        "camera-percep",
        "slam-percep",
        "slam-tf",
        "tf-percep",
        "tf-nav",
        "tf-global",
        "tf-local",
        "percep-nav",
        "percep-submap",
        "submap-pose",
        "nav-map",
        "slam-map",
        "nav-global",
        "nav-local",
        "business-cmd",
        "business-state",
        "decision-global",
        "decision-local",
        "decision-recovery",
        "global-state",
        "local-state",
        "local-motion",
        "recovery-motion",
        "motion-motor",
        "percep-anomaly",
        "anomaly-decision",
        "board-anomaly",
        "wheel-local",
        "business-map",
        "slam-trajectory",
        "map-constraints",
        "slam-anomaly"
      ]
    },
    "mapping": {
      "name": "定位与地图",
      "note": "SLAM / Percep 提供定位与观测；Map Server 处理持久化轨迹与拓扑；Nav Map 融合障碍图和几何约束并输出 costmap。",
      "edges": [
        "slam-tf",
        "tf-percep",
        "tf-nav",
        "tf-global",
        "tf-local",
        "slam-percep",
        "percep-nav",
        "percep-submap",
        "submap-register",
        "submap-pose",
        "nav-map",
        "map-nav",
        "slam-map",
        "map-slam",
        "nav-global",
        "nav-local",
        "wheel-local",
        "slam-trajectory",
        "map-constraints"
      ]
    },
    "orchestration": {
      "name": "调度与异常",
      "note": "Decision 是决策模块的调度核心；Anomaly 与 Map Server 是其子模块。两个 planner 无直接交互；底板故障经 Anomaly 上报，轮速仍直接送 Local。",
      "edges": [
        "business-cmd",
        "business-state",
        "decision-slam",
        "decision-nav",
        "decision-map",
        "decision-global",
        "decision-local",
        "decision-recovery",
        "map-state",
        "nav-state",
        "global-state",
        "local-state",
        "recovery-state",
        "slam-anomaly",
        "percep-anomaly",
        "anomaly-decision",
        "board-anomaly",
        "local-motion",
        "recovery-motion",
        "motion-motor",
        "slam-state",
        "business-map",
        "map-business"
      ]
    },
    "assets": {
      "name": "地图协作",
      "note": "Map Server 管轨迹、拓扑和资产版本；Business_core 提供 ID / 属性 / 配置；Decision 调度，Nav Map 构建导航视图。新增交互协议标为建议。",
      "edges": [
        "business-map",
        "map-business",
        "slam-trajectory",
        "decision-map",
        "map-state",
        "decision-nav",
        "map-constraints",
        "nav-map",
        "map-nav",
        "nav-state",
        "nav-global",
        "nav-local"
      ]
    }
  },
  processes: [
    {"id":"perception","name":"感知定位进程","members":["slam","percep","tf"],"note":"SLAM · Percep；TF 是 SLAM 公共接口，Percep 可作为库。"},
    {"id":"decision","name":"决策进程","members":["decision","anomaly","map"],"note":"Decision 调度核心 + Anomaly + Map Server；内部服务仍异步执行。"},
    {"id":"planning","name":"规控进程","members":["navmap","global","local","recovery","motion"],"note":"Nav Map 已确认放规控；Recovery / Motion 暂按规控能力归入。"}
  ]
};
if (typeof module !== 'undefined') module.exports = architecture;
