// Logical architecture; confirmed responsibilities and proposed protocols remain distinct.
const architecture = {
  modules: [
    {"id":"sensors","name":"Sensors","cn":"定位传感器","x":30,"y":30,"kind":"external","tag":"系统输入","summary":"提供激光、IMU 与里程计原始观测。","owns":"原始观测与采样时间；驱动归属不在本图展开。","parts":[["LiDAR","点云与采样时刻。"],["IMU / Odom","惯性与轮式里程计观测。"]],"boundary":"坐标外参、时间同步和观测有效性必须在接口中定义。","role":"外部输入 / 输出"},
    {"id":"camera","name":"Camera","cn":"视觉输入","x":30,"y":650,"kind":"external","tag":"系统输入","summary":"向 Percep 提供图像。","owns":"图像观测及标定信息。","parts":[["图像输入","图像、时间戳与相机标定信息。"]],"boundary":"不把图像识别结果直接当成可执行运动指令。","role":"外部输入 / 输出"},
    {"id":"business","name":"Business Core","cn":"业务核心","x":330,"y":40,"kind":"business","tag":"手绘模块","summary":"表达业务任务与约束，接收算法任务状态。","owns":"建议：业务任务生命周期、区域顺序、暂停与恢复策略。","parts":[["任务意图","向决策模块提供当前任务、目标与业务约束。"],["业务策略","候选：割草、回充、建图等任务切换与中断策略。"],["业务状态","汇总受理、执行、完成和失败；不把命令受理当作任务完成。"]],"boundary":"向 Decision 提交业务意图；建图 ID、任务 ID 与地图资产 ID 的归属及映射待讨论，不由 Map Server 隐式决定。","role":"业务入口"},
    {"id":"decision","name":"Decision","cn":"非阻塞调度 · 状态机","x":660,"y":40,"kind":"control","tag":"用户确认","summary":"作为算法服务的 client，以状态机调度各 server；任何时候不得被服务调用、等待或文件 I/O 阻塞。","owns":"调度状态与策略选择；具体业务模式边界、事件优先级和恢复规则仍待细化。","parts":[["状态机与调度 · 已确认","根据业务任务、执行反馈、底板信号和算法异常推进状态并选择策略。"],["异步服务调用 · 已确认方向","发起请求后继续处理事件；服务端以进度、结果或事件回报，决策不等待耗时操作结束。"],["请求生命周期 · 建议","区分受理与完成；关联请求 ID，设置超时、取消及迟到结果隔离。"],["异常策略 · 已确认职责","接收底板 / 堵转信号及算法异常；停止、重规划、恢复或上报的具体规则待讨论。"]],"boundary":"Server 是逻辑服务角色，不要求独立进程或同步 RPC。长任务、重试、取消等待均不能阻塞决策事件循环；队列上限、事件优先级、看门狗和停止路径需细化。","role":"Client · 异步调度"},
    {"id":"slam","name":"SLAM","cn":"定位 · TF · 历史位姿","x":30,"y":300,"kind":"sense","tag":"用户确认","summary":"提供 base_link → odom → map 的 TF，并提供更新历史 Submap 原点在 map 坐标系下位姿的机制。","owns":"坐标关系、定位状态、内部地图与历史锚点的 map 位姿；内部 PoseGraph 结构待设计。","parts":[["定位 / 建图与去畸变","消费定位传感器数据，为 Percep 输出去畸变点云。"],["TF 发布 · 已确认","向各模块提供 base_link → odom → map 坐标关系；初期可广播。"],["历史 Submap 位姿 · 已确认需求","支持按 Submap 标识更新原点在 map 系下的 pose；不能只提供当前机器人 TF。"],["PoseGraph 类内部能力 · 待设计","约束来源、节点选择、Submap 关联、优化触发与历史保留方式尚未定稿。"],["地图文件服务协作","序列化 / 解析自有地图资产；通过 Map Server 保存、定位和读取对应文件。"]],"boundary":"SLAM 内部优化方法未定。本图仅确认向外提供 TF 与历史 Submap 位姿更新的能力；不强制复制 Cartographer 的具体实现。","role":"Server · 能力服务"},
    {"id":"percep","name":"Percep","cn":"Local BEV · 重叠 Submap","x":30,"y":500,"kind":"sense","tag":"用户确认","summary":"输出实时 local BEV OCC，并用 odom 累计多帧观测，形成两张部分重叠的 Submap 送给 Nav Map。","owns":"感知观测、Submap 局部内容及其 odom 构建依据；历史 map 位姿由 SLAM 提供。","parts":[["Local BEV OCC · 已确认","输出局部鸟瞰占用观测，服务 Nav Map 的动态局部地图层。"],["Odom 累计 · 已确认","多帧感知只依据 odom 叠加，不把 map 修正注入正在构建的感知内容。"],["重叠双 Submap · 已确认","采用用户所述类似 Cartographer 的部分重叠设计；尺寸、切换与完成条件待细化。"],["Submap 关联元数据 · 建议","提供稳定标识、参考时刻、局部坐标与 odom 锚点；注册到 SLAM 的具体协议待讨论。"],["观测质量输出","为强绑定的异常检测提供感知结果和质量依据。"]],"boundary":"Percep 可作为 SLAM 库。Submap 内容坐标与原点在 map 下的位姿是不同数据；位姿优化不要求重新以 map 坐标堆叠感知观测。","role":"Server · 能力服务"},
    {"id":"navmap","name":"Nav Map","cn":"多层地图 · Costmap","x":330,"y":500,"kind":"map","tag":"用户确认","summary":"管理局部动态层、可保存障碍物地图和建图边界轨迹，并直接向 Global / Local planner 提供 costmap。","owns":"地图层内容、构建 / 融合状态、规划 costmap 与保存的边界轨迹；业务 ID 归属待讨论。","parts":[["局部动态层 · 已确认","将 local BEV OCC 转成 local costmap；窗口随机器人移动，机器人始终位于局部地图中心。"],["障碍物地图层 · 已确认","以多帧 Submap 堆叠构建可保存的障碍物地图，使用 SLAM 更新的原点 map pose。"],["优化后的地图更新 · 建议","按 Submap ID 替换位姿贡献或重建受影响区域；避免把重叠区或旧位姿反复累加。"],["边界轨迹层 · 已确认","记录建图阶段机器人的边界轨迹；保存后轨迹内容及其 map 坐标均冻结，后续 SLAM 优化不得修改。"],["Costmap 服务 · 已确认","Global / Local planner 均直接从此取对应 costmap；层融合、膨胀和未知空间策略待细化。"],["文件与建图上下文","自己序列化 / 解析地图，通过 Map Server 存取文件；建图业务 ID 的所有者与映射待讨论。"]],"boundary":"局部窗口朝向、动态信息衰减与层融合仍待细化。轮速输入属于 Local planner，不接入本图的 Nav Map。已保存边界及其 map 坐标冻结；建议保持保存地图参考系身份稳定，让后续定位和障碍物更新对齐该参考。边界轨迹不是覆盖历史。","role":"Server · 能力服务"},
    {"id":"map","name":"Map Server","cn":"文件保存 · 配套管理","x":330,"y":300,"kind":"map","tag":"用户修订","summary":"保存、定位、读取和删除 SLAM / Nav Map 的配套地图文件；不生成、修改、融合或使用地图内容。","owns":"文件位置、存取结果及配套资产清单；清单与版本机制为建议，业务 ID 归属待讨论。","parts":[["保存与读取 · 已确认","存储两个地图模块提供的文件，为 SLAM / Nav Map 返回对应位置或文件。"],["配套对齐 · 已确认方向","保持两侧地图文件的对应关系；这里是文件版本配套，不承担地图配准或几何计算。"],["删除操作 · 已确认","提供文件删除服务；在用资产保护、授权与失败处理待定义。"],["一致发布 · 建议","采用配套清单与完整性标记；两侧文件齐备后才暴露可加载版本，部分失败可被识别。"]],"boundary":"Map Server 不向 planner 提供运行时 costmap，也不解析地图做算法计算。SLAM / Nav Map 自己负责内容；文件保存完成不等于已加载可用。","role":"Server · 文件服务"},
    {"id":"global","name":"Global planner","cn":"全局规划","x":660,"y":500,"kind":"plan","tag":"路径语义已确认","summary":"消费 Nav Map 的 global costmap 与 SLAM TF，按异步请求生成几何路径 / 作业路线。","owns":"当前规划请求及对应几何路线。","parts":[["目标处理","解释目标点或区域约束；覆盖规划是否包含在内待确认。"],["路线求解","生成几何路径 / 作业路线，由 Local planner 生成可执行运动。"],["结果反馈","建议返回成功、无解、取消及失败原因。"]],"boundary":"不从 Map Server 读取运行时 costmap。路径交给 Local planner 执行，覆盖历史归属尚未确定；请求受理与规划完成分开反馈。","role":"Server · 全局规划"},
    {"id":"local","name":"Local planner","cn":"局部规划与跟踪","x":980,"y":500,"kind":"plan","tag":"手绘模块","summary":"消费 Nav Map 的 local costmap、全局路线、SLAM TF 和底板轮速，生成可执行运动。","owns":"当前路径的局部执行状态与速度候选。","parts":[["局部规划","依据环境与机器人约束进行局部避障。"],["路径跟踪","将路线转换为 v / ω；跟踪器的实际归属待核对。"],["轮速输入 · 已确认","接收底板轮速用于局部规划 / 跟踪；采样时刻、单位、时效和失效处理需定义。"],["执行反馈","建议返回进度、到达、阻塞、失败和停止结果。"]],"boundary":"与 Recovery 互斥输出运动请求；轮速用于局部规划 / 跟踪，不替代 SLAM 的权威 odom / TF。服务执行不得阻塞 Decision。","role":"Server · 局部执行"},
    {"id":"recovery","name":"Recovery","cn":"恢复动作","x":660,"y":780,"kind":"control","tag":"手绘模块","summary":"在决策授权范围内执行有限的恢复动作。","owns":"单次恢复动作的执行状态与结果。","parts":[["恢复执行","实现候选脱困动作，具体动作集待定义。"],["有界退出","建议限制时长、距离和重试次数，支持取消。"],["结果报告","向决策反馈成功、失败或已停止。"]],"boundary":"恢复也必须服从系统停止与运动许可；不独立决定业务恢复或重新开始割草。","role":"Server · 能力服务"},
    {"id":"motion","name":"Motion","cn":"运动执行","x":980,"y":780,"kind":"act","tag":"手绘模块","summary":"接收 v / ω，将运动请求落实到电机接口。","owns":"最终运动输出、当前控制来源与执行有效性（建议）。","parts":[["命令接入","接入 Local planner / Recovery 的速度请求。"],["运动约束","建议统一检查控制权、命令时效、速度限制与系统许可。"],["底盘执行","输出电机请求并解释设备反馈；闭环所在层待核对。"]],"boundary":"建议在最终执行入口保证单一有效命令源；具体仲裁实现位置待定。发送零速不等于已停稳。","role":"Server · 能力服务"},
    {"id":"motor","name":"Motor","cn":"底盘 / 电机","x":1280,"y":780,"kind":"external","tag":"硬件边界","summary":"执行运动输出，并提供可用的设备事实。","owns":"真实轮速、故障和停止状态等设备事实；反馈能力待核实。","parts":[["驱动执行","接收底盘侧运动请求。"],["设备反馈","反馈实际运动与故障；不以命令值代替测量值。"]],"boundary":"本图不展开驱动、刀盘与硬件安全设计；并不表示整机可以省略这些能力。","role":"外部输入 / 输出"},
    {"id":"tf","name":"TF 广播","cn":"base_link → odom → map","x":30,"y":165,"kind":"sense","role":"SLAM 公共输出 · 非独立服务","tag":"用户确认","summary":"SLAM 提供的公共定位接口，各模块按需订阅；图中独立画出只是为了清晰表达广播关系。","owns":"权威发布者是 SLAM；这不是新增的 TF 算法模块或独立进程。","parts":[["坐标链 · 已确认","提供 base_link → odom → map；图中文字表达坐标转换链，父子边与矩阵方向必须在协议里明确。"],["按需广播 · 已确认方向","向各定位消费者分发；代表连线绘出 Percep、Nav Map 和两级 planner，其他模块也可订阅。"],["时间与有效性 · 建议","携带采样时间、source / target frame 和有效性；查询时间不匹配时不得默认为有效。"]],"boundary":"当前 TF 不能代替历史 Submap 的逐项 map pose。Percep 累计只消费 odom 关系；Nav Map 负责把 Submap 放到 map 系。"},
    {"id":"anomaly","name":"Anomaly Detection","cn":"算法异常检测","x":30,"y":780,"kind":"control","role":"Server / Events · 异常事实","tag":"用户新增","summary":"与 SLAM / Percep 强绑定，检测打滑、相机遮挡和激光雷达算法侧异常，向 Decision 输出异常事实。","owns":"异常检测状态、证据及事件有效性；任务处置策略归 Decision。","parts":[["打滑检测 · 已确认范围","结合定位 / 感知质量及可用运动观测；是否直连底板轮速待讨论。"],["相机遮挡 · 已确认范围","基于感知观测质量产生遮挡事件；恢复判据待定义。"],["LiDAR 算法侧异常 · 已确认范围","识别算法可判断的点云或定位异常，与硬件直接上报的故障区分。"],["异常事件生命周期 · 建议","上报出现、持续、恢复，带来源、时间、有效性和证据；去抖与阈值待定。"]],"boundary":"强绑定是依赖关系，尚不等于独立进程。打滑不等于堵转；检测模块给事实，Decision 决定业务处置，执行侧仍要履行既有停止约束。"},
    {"id":"board","name":"Baseboard","cn":"底板信号 · 堵转 · 轮速","x":1280,"y":40,"kind":"external","role":"硬件事件 / 测量输入","tag":"用户新增","summary":"向 Decision 提供底板或堵转信号，向 Local planner 提供轮速测量。","owns":"底板原始信号、轮速测量及其采样时间；底板信号的具体种类待列举。","parts":[["底板 / 堵转信号 · 已确认","作为类似传感器的事件输入送入决策模块，由决策制定策略。"],["轮速 · 已确认消费者","轮速提供给 Local planner 用于规划 / 跟踪；不把原始轮速等同于完整 odom。"]],"boundary":"信号电平、触发 / 恢复事件、失联与有效性需约定。图中 Motor 表示执行对象，Baseboard 表示信号来源，不断言它们是两块硬件。"}
  ],
  edges: [
    {"id":"sensor-slam","from":"sensors","to":"slam","type":"data","label":"LiDAR · IMU · Odom","path":"M30 72 H12 V342 H30","lx":100,"ly":280,"origin":"手绘关系","meaning":"原始定位观测进入 SLAM。","contract":"采样时间、标定、单位、观测有效性和同步策略需约定。"},
    {"id":"camera-percep","from":"camera","to":"percep","type":"data","label":"图像","path":"M120 650 V584","lx":145,"ly":625,"origin":"手绘关系","meaning":"相机观测进入 Percep。","contract":"图像时间、标定、格式与对时容差。"},
    {"id":"slam-percep","from":"slam","to":"percep","type":"data","label":"去畸变点云","path":"M120 384 V500","lx":160,"ly":430,"origin":"手绘关系","meaning":"提供用于环境感知的点云。","contract":"参考时刻、坐标系和观测有效性。"},
    {"id":"slam-tf","from":"slam","to":"tf","type":"data","label":"TF 发布","path":"M170 300 V249","lx":199,"ly":275,"origin":"用户确认","meaning":"SLAM 是 base_link → odom → map 公共坐标关系的发布者。","contract":"明确变换方向、采样时间、有效性、更新频率；各模块按需订阅。"},
    {"id":"tf-percep","from":"tf","to":"percep","type":"data","label":"仅 odom","path":"M210 222 H248 V478 H170 V500","lx":258,"ly":477,"origin":"用户确认","meaning":"Percep 仅依据 odom 进行多帧累计，不用 map 位姿修正感知内容。","contract":"建议固定 Submap 局部坐标；odom 重置或时间断裂需切换会话，具体规则待讨论。"},
    {"id":"tf-nav","from":"tf","to":"navmap","type":"data","label":"TF / 当前定位","path":"M210 207 H560 V470 H460 V500","lx":437,"ly":199,"origin":"用户确认","meaning":"提供机器人在 odom / map 中的定位与坐标关联，用于地图、中心窗口和建图边界轨迹。","contract":"建议检查时间与有效性；历史 Submap 校正仍走专用位姿更新接口。"},
    {"id":"tf-global","from":"tf","to":"global","type":"data","label":"TF 按需订阅","path":"M210 180 H900 V455 H800 V500","lx":814,"ly":173,"origin":"用户确认","meaning":"Global planner 从公共 TF 获取当前定位。","contract":"路径与地图坐标版本一致；失效或跳变后的重规划策略待定义。"},
    {"id":"tf-local","from":"tf","to":"local","type":"data","label":"TF 按需订阅","path":"M210 239 H1135 V500","lx":1055,"ly":232,"origin":"用户确认","meaning":"Local planner 从公共 TF 获取实时定位。","contract":"不得把广播收到等同有效；时间滞后和定位失效处理待定。"},
    {"id":"percep-nav","from":"percep","to":"navmap","type":"data","label":"local BEV OCC","path":"M210 520 H330","lx":270,"ly":510,"origin":"用户确认","meaning":"实时 BEV OCC 进入 Nav Map 的局部动态层。","contract":"坐标系、范围、分辨率、未知语义和观测时间；Nav Map 生成以机器人为中心的 local costmap。"},
    {"id":"percep-submap","from":"percep","to":"navmap","type":"data","label":"重叠 Submap","path":"M210 564 H330","lx":270,"ly":589,"origin":"用户确认","meaning":"多帧累计、两张部分重叠的 Submap 供 Nav Map 堆叠障碍物地图。","contract":"建议携带 submap_id、局部内容、odom 锚点、参考时刻、内容版本与 active / finished 状态；具体 schema 待讨论。"},
    {"id":"submap-register","from":"percep","to":"slam","type":"data","label":"锚点登记（建议）","path":"M75 500 V384","lx":55,"ly":465,"origin":"补充建议","meaning":"为 SLAM 关联感知 Submap 与历史定位节点提供登记路径。","contract":"建议登记 submap_id、参考时间、T_odom_submap 或可关联历史节点；由 Percep 直送还是 Nav Map 转交、PoseGraph 如何关联尚未定稿。"},
    {"id":"submap-pose","from":"slam","to":"navmap","type":"data","label":"Submap 原点 map pose","path":"M210 365 H280 V435 H435 V500","lx":355,"ly":425,"origin":"用户确认","meaning":"SLAM 提供机制更新每个历史 Submap 原点在 map 坐标系下的 pose。","contract":"建议输出 submap_id、T_map_submap、优化批次 / 版本与有效性；Nav Map 按同一批次重拼接，不能把当前 TF 直接当所有历史原点的校正。"},
    {"id":"nav-map","from":"navmap","to":"map","type":"data","label":"保存导航文件","path":"M390 500 V384","lx":367,"ly":416,"origin":"用户修订","meaning":"Nav Map 序列化自己的地图层并交由 Map Server 保存文件。","contract":"建议保存障碍物、边界轨迹和必要重建元数据；配套版本、文件完整性和提交结果需明确。Map Server 不修改内容。"},
    {"id":"map-nav","from":"map","to":"navmap","type":"data","label":"文件结果 / 读取","path":"M500 384 V500","lx":531,"ly":393,"origin":"用户修订","meaning":"响应 Nav Map 的保存 / 读取等请求，返回操作结果、文件位置或文件，由 Nav Map 自行解析。","contract":"按配套资产清单读取；文件存在、读取完成和地图就绪是不同状态。"},
    {"id":"slam-map","from":"slam","to":"map","type":"data","label":"SLAM 文件","path":"M210 325 H330","lx":270,"ly":314,"origin":"用户修订","meaning":"SLAM 提交自身序列化地图文件。","contract":"SLAM 决定格式与内容，Map Server 负责存储和文件配套，不进行地图几何对齐。"},
    {"id":"map-slam","from":"map","to":"slam","type":"data","label":"文件结果 / 读取","path":"M330 355 H210","lx":270,"ly":375,"origin":"用户确认","meaning":"响应 SLAM 的文件存取请求，提供结果或对应文件，由 SLAM 自行加载。","contract":"使用匹配会话 / 版本；缺失、损坏或不匹配必须报告，不默认为可用。"},
    {"id":"nav-global","from":"navmap","to":"global","type":"data","label":"global costmap","path":"M510 538 H660","lx":585,"ly":528,"origin":"用户修订","meaning":"Global planner 直接消费 Nav Map 的 global costmap。","contract":"明确地图版本、坐标、代价层融合、膨胀和未知空间策略；不经过 Map Server。"},
    {"id":"nav-local","from":"navmap","to":"local","type":"data","label":"local costmap","path":"M510 562 H610 V650 H1020 V584","lx":790,"ly":642,"origin":"用户修订","meaning":"Local planner 直接消费 Nav Map 提供的以机器人为中心的 local costmap。","contract":"窗口原点随车更新；时间、分辨率、地图朝向与动态观测过期语义需定义。"},
    {"id":"business-cmd","from":"business","to":"decision","type":"command","label":"cmd · 任务请求","path":"M510 65 H660","lx":585,"ly":55,"origin":"手绘关系","meaning":"业务核心提交当前任务与约束。","contract":"建议任务 / 请求关联、受理 / 拒绝语义；建图业务 ID 归属待讨论。"},
    {"id":"business-state","from":"decision","to":"business","type":"feedback","label":"state / resp","path":"M660 100 H510","lx":585,"ly":123,"origin":"手绘关系","meaning":"决策向业务返回受理、状态与终态。","contract":"受理不等于完成；业务策略和算法调度的边界需细化。"},
    {"id":"decision-slam","from":"decision","to":"slam","type":"command","label":"定位 / 建图请求","path":"M680 124 V145 H270 V305 H210","lx":420,"ly":139,"origin":"用户确认","meaning":"Decision 以 client 方式调度 SLAM 的能力服务。","contract":"具体命令集待定；耗时定位 / 建图异步执行，不阻塞 Decision；回执见服务协议说明。"},
    {"id":"decision-nav","from":"decision","to":"navmap","type":"command","label":"建图 / 加载 / 保存","path":"M700 124 V155 H305 V480 H350 V500","lx":365,"ly":475,"origin":"用户确认","meaning":"Decision 调度 Nav Map 的地图服务与建图流程。","contract":"建议建图会话包含轨迹采集边界；保存、加载、取消均需异步结果，具体状态和 ID 归属待讨论。"},
    {"id":"decision-map","from":"decision","to":"map","type":"command","label":"文件操作 / 删除","path":"M710 124 V270 H420 V300","lx":535,"ly":263,"origin":"用户修订","meaning":"调度 Map Server 的文件操作；不请求它执行算法地图融合。","contract":"操作受理、文件完成分离；删除范围、在用文件保护和两侧配套失败处理待定义。"},
    {"id":"decision-global","from":"decision","to":"global","type":"command","label":"规划请求","path":"M735 124 V500","lx":762,"ly":416,"origin":"手绘关系","meaning":"非阻塞提交全局规划目标。","contract":"服务端快速返回受理，规划结果异步返回；超时、取消与迟到结果隔离为建议。"},
    {"id":"decision-local","from":"decision","to":"local","type":"command","label":"执行 / 取消","path":"M840 64 H1070 V500","lx":1090,"ly":352,"origin":"手绘关系","meaning":"决策授权局部执行或请求取消。","contract":"发出后继续处理底板 / 异常事件；实际停止确认通过反馈驱动状态迁移，不同步等待。"},
    {"id":"decision-recovery","from":"decision","to":"recovery","type":"command","label":"恢复授权","path":"M840 100 H940 V740 H750 V780","lx":903,"ly":729,"origin":"手绘关系","meaning":"决策调度有界恢复服务。","contract":"建议先撤销旧控制权并异步确认停止，再授权恢复；次数、距离和时长预算待定。"},
    {"id":"global-local","from":"global","to":"local","type":"data","label":"路径 / 路线","path":"M840 538 H980","lx":910,"ly":528,"origin":"用户确认","meaning":"Global planner 提供几何路径 / 作业路线，Local planner 生成可执行运动。","contract":"路径标识、坐标、地图版本和路线替换规则。"},
    {"id":"local-motion","from":"local","to":"motion","type":"command","label":"v / ω","path":"M1070 584 V780","lx":1093,"ly":705,"origin":"手绘关系","meaning":"局部执行产生速度请求。","contract":"建议含控制源、时效和任务关联；过期指令不可继续执行。"},
    {"id":"recovery-motion","from":"recovery","to":"motion","type":"command","label":"v / ω","path":"M840 822 H980","lx":910,"ly":813,"origin":"手绘关系","meaning":"恢复动作产生速度请求。","contract":"与 Local planner 互斥；控制权移交和迟到命令拒绝规则待定。"},
    {"id":"motion-motor","from":"motion","to":"motor","type":"command","label":"运动输出","path":"M1160 822 H1280","lx":1220,"ly":813,"origin":"手绘关系","meaning":"最终速度请求进入底盘执行。","contract":"速度限制、底板接口及失联停止机制待核对。"},
    {"id":"slam-anomaly","from":"slam","to":"anomaly","type":"data","label":"定位质量 / 运动依据","path":"M45 384 H20 V820 H30","lx":132,"ly":753,"origin":"用户确认","meaning":"异常检测强依赖 SLAM 的定位质量、运动估计与算法诊断。","contract":"具体证据、有效性和时序待定；算法异常不等同硬件故障。"},
    {"id":"percep-anomaly","from":"percep","to":"anomaly","type":"data","label":"感知质量 / 观测","path":"M210 550 H235 V822 H210","lx":289,"ly":682,"origin":"用户确认","meaning":"异常检测消费 Percep 观测质量，识别遮挡等异常。","contract":"检测阈值、去抖与事件恢复条件待定义；部署位置与 Percep / SLAM 绑定方式待讨论。"},
    {"id":"anomaly-decision","from":"anomaly","to":"decision","type":"feedback","label":"打滑 / 遮挡 / LiDAR 异常","path":"M210 848 H595 V400 H805 V124","lx":486,"ly":841,"origin":"用户确认","meaning":"算法侧异常事实发往 Decision，由状态机决定策略。","contract":"建议事件来源、类型、出现 / 恢复、证据、时间和有效性；打滑与堵转分别处理，异常洪泛时也不能阻塞决策。"},
    {"id":"board-decision","from":"board","to":"decision","type":"feedback","label":"底板 / 堵转信号","path":"M1280 82 H840","lx":1085,"ly":72,"origin":"用户确认","meaning":"底板信号作为事件输入直接交给 Decision，触发相应策略。","contract":"需列举信号类型、触发和恢复条件；采用事件 / 缓存，避免决策同步读取硬件。"},
    {"id":"wheel-local","from":"board","to":"local","type":"data","label":"轮速","path":"M1370 124 V455 H1160 V520","lx":1280,"ly":446,"origin":"用户确认","meaning":"底板轮速输入 Local planner，用于局部规划和跟踪；此接口不指向 Nav Map。","contract":"定义轮速单位、采样时间、频率、有效性及过期处理；与 TF / costmap 对时，不替代 SLAM odom。"},
    {"id":"map-state","from":"map","to":"decision","type":"feedback","label":"文件操作结果","path":"M490 300 V285 H770 V124","lx":650,"ly":280,"origin":"补充建议","meaning":"Map Server 异步回报文件操作完成或失败。","contract":"结果含请求关联与配套文件完整性；不报告地图语义可用或定位成功。"},
    {"id":"nav-state","from":"navmap","to":"decision","type":"feedback","label":"地图就绪 / 保存结果","path":"M510 520 H565 V315 H825 V124","lx":670,"ly":309,"origin":"补充建议","meaning":"Nav Map 报告加载就绪、建图或保存结果。","contract":"读到文件不等于地图就绪；说明采纳的地图 / 位姿版本及失败原因。"},
    {"id":"global-state","from":"global","to":"decision","type":"feedback","label":"规划结果","path":"M790 500 V124","lx":835,"ly":475,"origin":"补充建议","meaning":"异步回报规划成功、无解、取消。","contract":"请求关联、终态和迟到结果处理；不得用同步等待代替事件回报。"},
    {"id":"local-state","from":"local","to":"decision","type":"feedback","label":"进度 / 阻塞 / 停止","path":"M1120 500 V145 H815 V124","lx":1040,"ly":140,"origin":"补充建议","meaning":"异步回报局部执行进度和终态。","contract":"停止受理与实际停稳分开；取消等待期间状态机仍处理其他事件。"},
    {"id":"recovery-state","from":"recovery","to":"decision","type":"feedback","label":"恢复结果","path":"M840 850 H965 V130 H830 V124","lx":966,"ly":767,"origin":"补充建议","meaning":"恢复服务报告完成、失败或已取消。","contract":"释放控制权与恢复结果关联，不直接决定业务继续。"},
    {"id":"motor-state","from":"motor","to":"motion","type":"feedback","label":"设备事实","path":"M1280 850 H1160","lx":1220,"ly":874,"origin":"补充建议","meaning":"设备侧提供实际运动、故障或停止反馈。","contract":"真实反馈能力仍需核对，发送零速不代表已停稳。"},
    {"id":"motion-state","from":"motion","to":"local","type":"feedback","label":"执行反馈","path":"M1130 780 V584","lx":1170,"ly":739,"origin":"补充建议","meaning":"向局部执行提供 Motion 的实际执行状态。","contract":"时间、来源、有效性与缺失处理待定。"},
    {"id":"slam-state","from":"slam","to":"decision","type":"feedback","label":"定位 / 建图结果","path":"M210 340 H225 V160 H760 V124","lx":655,"ly":153,"origin":"补充建议","meaning":"SLAM 异步回报定位 / 建图服务结果，实时 TF 不能代替任务终态回执。","contract":"关联请求标识、成功 / 失败 / 取消及原因；Decision 不同步等待 SLAM，超时和迟到结果处理待设计。"}
  ],
  questions: [
    ["待讨论","历史 Submap 与 PoseGraph","已确认 SLAM 需提供历史 Submap 原点的 map pose。如何关联感知 Submap 与 SLAM 节点？注册由谁发起？约束、优化批次、锚点生命周期和 odom 重置如何处理？"],
    ["待细化","双 Submap 与地图融合","两个部分重叠 Submap 的尺寸、切换、完成条件是什么？Nav Map 如何处理重叠贡献、活动子图更新、历史位姿修正和动态障碍残留？"],
    ["已确认","保存后的边界轨迹","轨迹保存后内容与 map 坐标均冻结，后续 SLAM 优化不得修改。建议保持保存地图参考系身份稳定；障碍物地图更新不能重写边界层。"],
    ["待讨论","建图 ID 与文件配套","业务建图 ID、地图资产 ID、Submap ID、优化批次需区分。谁创建、谁持有？如何保证 SLAM / Nav Map 两套文件属于同一次提交，而不让 Map Server 接管业务逻辑？"],
    ["已确认 / 待细化","轮速与局部窗口","已确认底板轮速输入 Local planner，不是 Nav Map。轮速单位、对时、有效性与失效处理，以及局部窗口朝向、分辨率和过期策略仍需细化。"],
    ["待细化","非阻塞与异常策略","状态机如何处理并发事件、取消超时和迟到结果？堵转、打滑、遮挡、LiDAR 异常如何分级、去抖、恢复？各 server 的完成回执和停止事实如何闭环？"],
    ["范围待定","覆盖、沿边、对桩与刀盘","本次重点为定位、地图和调度。建图边界轨迹不等于覆盖历史；全覆盖、沿边、对桩及刀盘能力仍需结合产品范围细化。"]
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
          "Decision 发出请求即返回事件处理，不同步等待加载。"
        ],
        [
          "nav-state",
          "接收地图就绪事件",
          "文件读取与地图就绪由 Nav Map 区分，异步反馈为建议协议。"
        ],
        [
          "decision-global",
          "提交规划请求",
          "Planner 以 server 形式执行，Decision 继续接收异常事件。"
        ],
        [
          "nav-global",
          "直接取 global costmap",
          "运行时地图来自 Nav Map，不来自文件服务器。"
        ],
        [
          "global-local",
          "交付几何路线",
          "Global 输出路线，Local 生成可执行运动。"
        ],
        [
          "decision-local",
          "授权执行",
          "授权与路线到达是两个条件，具体关联协议待定。"
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
          "到达、阻塞或停止事实驱动状态迁移。"
        ]
      ]
    },
    "recover": {
      "name": "异常与恢复",
      "steps": [
        [
          "board-decision",
          "底板 / 堵转事件进入",
          "作为独立硬件事件，不能被同步服务调用挡住。"
        ],
        [
          "anomaly-decision",
          "算法异常进入",
          "打滑、遮挡、LiDAR 异常有独立来源与证据，不等同堵转。"
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
      "name": "保存与重新加载",
      "steps": [
        [
          "decision-nav",
          "结束建图并请求保存",
          "已确认保存后边界轨迹内容及其 map 坐标冻结，后续 SLAM 优化不得改写；文件提交协议仍为建议。"
        ],
        [
          "nav-map",
          "保存 Nav Map 文件",
          "Nav Map 负责内容，Map Server 只存储。"
        ],
        [
          "slam-map",
          "保存配套 SLAM 文件",
          "此处按顺序展示，实际两侧可并行；不能把部分成功当完整版本。"
        ],
        [
          "map-state",
          "返回文件操作结果",
          "建议文件配套齐备后确认完成；决策全程异步。"
        ],
        [
          "map-nav",
          "Nav Map 自行读取加载",
          "从对应文件位置读取，自己解析地图。"
        ],
        [
          "map-slam",
          "SLAM 自行读取加载",
          "加载配套 SLAM 资产；缺失或版本不符要明确失败。"
        ],
        [
          "nav-state",
          "报告运行时地图就绪",
          "文件存在不等于加载完成或地图可用。"
        ]
      ]
    }
  },
  topics: {
    "main": {
      "name": "系统总览",
      "note": "SLAM TF 供 Percep、Nav Map、Global planner 和 Local planner 使用；Percep 累计 Submap 只使用 odom 关系。Server 是逻辑角色。",
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
        "global-local",
        "local-motion",
        "recovery-motion",
        "motion-motor",
        "percep-anomaly",
        "anomaly-decision",
        "board-decision",
        "wheel-local"
      ]
    },
    "mapping": {
      "name": "定位与地图",
      "note": "实时 TF、仅用 odom 的感知累计、历史 Submap map pose、Nav Map 运行时供图与 Map Server 文件存储分别表达。",
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
        "wheel-local"
      ]
    },
    "orchestration": {
      "name": "调度与异常",
      "note": "Decision 为非阻塞 client；各能力服务异步执行。Server 同时可以发布数据流，client / server 不强制同步 RPC。",
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
        "board-decision",
        "local-motion",
        "recovery-motion",
        "motion-motor",
        "slam-state"
      ]
    }
  }
};
if (typeof module !== 'undefined') module.exports = architecture;
