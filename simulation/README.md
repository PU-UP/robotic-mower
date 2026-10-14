# Brain 交互仿真环境

使用现有 SimPy 虚拟时间和离线报告。brain 实际运行；算法通过替身或脚本反馈模拟。现在所有场景都经过 JSON command / event / status 接口，directive 也经过 JSON 序列化与解析后交给模块。

## 运行

在项目根目录运行，Python 3.11+，唯一第三方依赖是 requirements.txt 中的 SimPy：

```powershell
# 全部示例与原有任务回归
.\.venv\Scripts\python.exe -m simulation

# 按 JSON 脚本验证指定交互
.\.venv\Scripts\python.exe -m simulation --script simulation/scenarios/cover_regions.json
.\.venv\Scripts\python.exe -m simulation --script simulation/scenarios/pause_and_timeout.json

# 单个自动算法替身场景
.\.venv\Scripts\python.exe -m simulation --scenario mapping

# 协议、状态机与脚本回归
.\.venv\Scripts\python.exe -m unittest discover -s simulation -p "test_*.py" -v
```

默认输出 `output/report.html`；各场景另有 `report.html / result.json / events.jsonl`。`--output` 可指定目录。验收失败返回非零退出码。默认扫描 scenarios 下的 JSON 文件，因此后续添加一个任务脚本就会加入全部场景运行。

## 查看交互回放

页面默认打开 **Brain 内部**，可用顶部按钮切换到 **进程交互**；两种视角共用同一条时间线。内部视图展示 Health 能力与来源证据、真实业务 Mode 与原型协议模式、Mission 生命周期/业务阶段/尝试次数、已完成与挂起进度、就绪条件和动作输出。Brain不增加算法行为树；页面不显示虚构的真实BT运行状态。

`mission_lifecycle.json` 独立验收暂停保留业务 Mode、FAILED 终态、复位等待重试、attempt 递增、跨目标推进和取消结果。可在总回放选择“Mission 生命周期 · 暂停与故障重试”，观察同一任务内部状态的变化。

每次输入在仿真记录中保存 brain_before / brain_after；下发指令与命令回执也保存当时的 brain_after。内部视图在输入步骤显示该输入处理后的真实快照，进程交互视图仍按交付顺序展示后续下发消息。环境步骤沿用此前最近快照，不用未来采样推测当前状态。可展开查看本次输入与完整 Brain 快照。

打开 output/report.html 选择全部场景；保持使用总报告，不用单场景报告替换它。

回放按消息到达顺序逐步展示：用户在上方，brain 居中，单一 roboframe 在下方。节点位置不变，每步只改变中文消息内容、状态和高亮箭头。顶部并排展示中文说明和本步完整 JSON（directive、status 或上层输入），消息区高度固定，长消息在区内滚动。蓝色表示 brain 下发任务，绿色表示输入或返回。上一步 / 下一步、键盘左右键和进度条均可定位；跳转菜单可直接选择接管、区域闭环、通道起点校验等关键动作，自动播放可调整节奏。

重复状态心跳和仅有进度数值变化的消息合并展示，完整历史仍保留在默认折叠的技术详情中。模块卡片沿用已有 STOPPED、READY、RUNNING、SUCCEEDED、BLOCKED、FAILED、REJECTED 基本状态，显示最近一次观测，不随新 directive 清空；未观测到状态时显示未知。brain 对当前版本的就绪确认独立统计，闭环 signal 作为消息展示，不混入模块状态。本轮不扩展各算法模块的内部状态机。界面按原始事件顺序重建当前指令，即使同一时间发生多条消息，也不会提前显示后续决策。地图是当前时刻或更早的采样，用于辅助理解位置和草稿；不代表算法模块间每条高频数据传输。

## 两种反馈方式

`feedback: "auto"`：一个 RoboframeDouble 自动准备、运行和反馈。区域内导航、沿边与覆盖由替身协调；固定作业线段须同时有实际模拟运动和刀盘 RUNNING 反馈才计入，停刀未确认不能完成区域。导航抵达后进入对桩阶段，设备事实确认充电才完成回充。自动环境默认提供模拟设备反馈；这些不代表实机能力。

`feedback: "scripted"`：关闭自动状态反馈，完全按步骤发送模块 status，适合逐条定义业务交互、等待条件、消息延迟、重复完成和超时。脚本不直接修改 brain，不注入最终 mode；所有业务转换仍由 brain 决定。

## 场景格式

```json
{
  "name": "my_business",
  "description": "这里填写业务目标与待验证交互",
  "feedback": "auto",
  "mapped": true,
  "duration": 4,
  "steps": [
    {"at": 0, "command": {"command_id": "work-1", "type": "START_MOWING", "params": {"map_id": "garden", "region_ids": ["region-1"]}}},
    {"at": 0.3, "label": "已开始执行当前目标", "expect": {"directive": {"mode": "WORKING", "phase": "EXECUTE"}}},
    {"at": 3, "label": "任务完成", "expect": {"brain_status": {"mode": "IDLE", "last_task_result": {"task_id": "work-1", "result": "completed"}}}}
  ]
}
```

每一步按 at 排序，只包含以下动作之一：

| 动作 | 内容 |
| --- | --- |
| command | [协议](../brain/PROTOCOL.md)中的上层指令 |
| event | 外部事实事件，如 LOW_BATTERY |
| status | 完整模块反馈；stamp 为产生时刻，revision 明确指向所响应指令 |
| world | 模拟世界位姿，例如 {"position":[4,0]}，与其他动作互斥 |
| fault | 自动替身故障，如 `{"module":"roboframe","reason":"LOCALIZATION_LOST"}` 或 `{"module":"roboframe","silent":true}` |
| expect | 检查 directive / command_result / brain_status 的指定字段，未写字段不参与匹配 |

status 步骤可额外带 `delay`，默认 0.01 秒；可用较长延迟制造乱序。command/event 在步骤时刻送达 brain。清除故障用 reason 空字符串；恢复反馈用 silent=false。fault 用于 auto 模式；scripted 模式直接安排 FAILED/BLOCKED/REJECTED 或停止发状态。

期望检查允许部分对象匹配，数组按完整内容匹配。至少需要一个 expect；失败会在报告中保留 expected 与 actual。step 必须早于 duration，避免最后一步尚未交付却提前结束。若要观察一条 status 的结果，expect 应安排在其交付时间之后。

world 步骤提供 position: [x,y] 给 roboframe 替身，不把坐标交给 brain；用于模拟转场、沿边和采集。mapping_session.json 是完整业务，--scenario mapping 为便捷入口。

`mapped: true`（默认）提供 garden，含 region-1 / region-2 / dock；`false` 从空业务地图开始。每份脚本都有独立 Brain 和 roboframe 替身实例，无前序运行依赖。

## 后续迭代

你提供业务目的、触发条件和希望的交互后：先写一个场景与期望，补入 brain 业务转换，再调整相应模块反馈；新协议字段确有需要才增加。现有 START/暂停/回充规则只是示例策略，不作为未讨论业务的既定要求。

原有自动示例继续覆盖割草、暂停续作、回充、低电抢占、故障恢复、status 超时、感知过期和取消。JSON 示例验证协议形状、异步交互、故障恢复和完整多对象建图。地图与采集轨迹可在逐帧数据中查看。

仿真不验证 SLAM、几何算法、地图可靠保存、物理运动或实机安全。无跨进程时钟、可靠重传或重启恢复；控制/状态默认延迟 0.01 秒、循环周期 0.1 秒是仿真假设。

## 统一地图约束

全部已建图场景共用充电站 → 回归通道 → 区域1 → 普通通道 → 区域2的连通底图。首次建图从站位出发，自动后退1.5米，再遥控到首区起点；该遥控轨迹保存为回归通道。普通通道两端必须分别位于两个不同区域，全部区域必须从站点可达，保存前统一校验。

mapping_session 验证完整正向流程；mapping_disconnected 故意遗漏通道末端，验证拒绝保存并保留会话。所有原有作业、回充、暂停、低电、故障与 Mission 生命周期场景继续保留在总报告。

自动退桩按每步位移更新定位，完成以实际模拟位置为准；其他转场沿通道折线按0.8秒虚拟时长插值，只验证路径连接与业务交互，不模拟真实速度、覆盖轨迹或避障。脚本反馈模式仍由场景显式提供状态。


## 内部状态图验收

Brain内部视角上方展示固定Mode图和随业务变化的Mission阶段图，另用生命周期状态带标出暂停、失败和执行尝试。绿色节点为当前状态，橙色边框为本步转换前节点，粗线为本步转换；“曾到达”按当前执行单元/尝试隔离，不等于完成。阶段图只展示已实现规则；phase作为动作握手收进详情。

每步的决策证据使用实际输入及其brain_before/brain_after，不读取后续帧。下发与回执步骤标为“最近决策”，无转换、过期反馈、失败后复位均不会生成虚构转换。tick导致的超时有独立记录。图上的条件标签是静态规则说明，快照变化是运行证据，不是额外决策引擎。

生成全部报告后可运行 `node simulation/test_report_state.cjs`，使用本机Node标准库验收所有场景的回放模型，以及闭合、准备确认、失败重试、时钟超时、过期反馈和取消的显示语义。报告本身仍为离线HTML，不依赖Node或网络资源。

## 原型迁移与能力替身

旧产品包中的 BusinessMap/Entity、Observation、PlanningInput 分别迁到 world.py、observation.py、planning.py，保留地图连通、曲线通道、定位新鲜度和参考一致性校验。它们是测试数据模型，不是三个服务，也不直接与 Brain 通信。

CoverageManager 的最小替身是 runtime.coverage：按任务、地图、区域保存已确认线段，独立于环境地图。暂停和回充后保留；Planner 替身依据剩余线段继续。线段只是固定测试样本，不代表真实有效面积、割幅、时间同步、SLAM历史修正或持久化方案。新任务不继承旧覆盖，已割区域仍能通行。

`Simulation(automatic_devices=False)` 可关闭自动设备反馈；默认刀盘 UNKNOWN、充电未知。test_runtime 显式注入事实，验证未知不被当作成功、普通经过不计切割、回充续作保留原记录。真实 BladeComponent、Foundation接口和对桩感知均未实现。

自动环境单独保存模拟充电接触事实：进入对桩并建立接触后保持充电，结束回充任务或收到 BATTERY_OK 不会清掉接触；实际模拟位置离桩后才清除。关闭自动反馈时完全使用测试注入的设备事实。任务状态 STOPPED 只表示执行分支已停止，不能把它当作刀盘或车轮物理停转确认。
