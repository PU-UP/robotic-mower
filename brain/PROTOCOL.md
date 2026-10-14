# Brain 输入输出协议 · 单一 roboframe 原型

2026-10-14。本文对应 contracts.py 和 Python 仿真，供验证业务边界；不锁定真实 roboframe/Foundation 的生产协议。旧三来源反馈及 EDGE_REGION/COVER_REGION 不再支持，调用方与场景需一起迁移。

## 入口和输出

`Brain.receive(kind, payload, now)` 接受 command、event、status，返回：

| 输出 | 含义 |
| --- | --- |
| directive | 新指令对象；没有新输出时 null |
| command_result | 本次命令受理回执；非命令输入时 null |
| brain_status | 处理后的业务状态快照 |

`tick(now)` 用于没有消息时检查超时，返回 Directive 或 None。now 必须单调且有限。输出快照与内部可变状态隔离。

## directive：当前目标

```json
{
  "revision": 4,
  "task_id": "work-1",
  "mode": "WORKING",
  "phase": "EXECUTE",
  "mission": {"type": "MOW_REGION", "map_id": "garden", "target_id": "region-2", "control": "AUTO"}
}
```

五个顶层字段必填。mission 为固定四字段 WorkItem，不包含完整目标序列；task_id 是所属业务任务或建图会话身份，用于关联原作业记录。revision 是指令版本，不是任务身份；暂停、回充、复位重试会改变 revision，恢复原作业时 task_id 保持不变。回充使用另一份任务身份。

| type | target_id | control | mode |
| --- | --- | --- | --- |
| UNDOCK | 桩ID | AUTO | MAPPING |
| MAP_RETURN_CHANNEL | 回归通道ID | MANUAL | MAPPING |
| MANUAL_DRIVE | null | MANUAL | MAPPING |
| MAP_REGION | 区域ID | MANUAL/AUTO | MAPPING |
| MAP_CHANNEL | 通道ID | MANUAL | MAPPING |
| SAVE_MAP | null | NONE | MAPPING |
| MOW_REGION | 区域ID | AUTO | WORKING |
| RETURN_HOME | 桩ID | AUTO | RETURNING |

PREPARE 等待 roboframe 本版本 READY；EXECUTE 执行当前目标；COMMIT 仅用于区域、通道、整图提交，SAVE_MAP 必须使用 COMMIT。NONE 仅用于 IDLE/PAUSED/CHARGING/ERROR，此时 mission 和 task_id 均为 null，内部暂停上下文仍保留。

控制与模式按类型严格校验。新动作、控制意图切换或恢复使用新 revision；旧成功不可确认新版本。区域内沿边/覆盖切换不再要求 Brain 发布新任务。

## roboframe status

```json
{
  "module": "roboframe",
  "revision": 4,
  "sequence": 18,
  "stamp": 12.3,
  "state": "RUNNING",
  "reason": null,
  "progress": 0.35
}
```

module/revision/sequence/stamp/state 必填；reason/progress/signal 可选。module 只接受 roboframe。revision/sequence 为非负整数，stamp 为有限非负数，progress 为 0 到 1；未知字段拒绝。signal 目前只支持 REGION_CLOSED。

| state | 语义 |
| --- | --- |
| READY | roboframe 已汇总当前任务准备条件，Brain 才可下发 EXECUTE |
| RUNNING | 当前任务仍在执行，包括等待设备确认 |
| SUCCEEDED | 当前请求整体完成；MOW_REGION 为整区域完成，RETURN_HOME 包含设备侧充电确认，COMMIT 为提交完成 |
| BLOCKED/FAILED/REJECTED | 受阻、失败或拒绝；由业务阶段判断后果 |
| STOPPED | 当前任务分支已停止执行；不单独证明车轮或刀盘已经物理停转，设备实际状态仍需独立反馈 |

刀盘命令已发不等于 RUNNING 已确认，地图/视觉到桩不等于充电已确认。未知设备事实不能转成成功。区域闭合只触发提交，不能当提交成功。progress 是诊断信息，Brain 不据它推进目标，也不把它当持久化覆盖记录。

过滤条件：revision 一致；stamp 不早于当前指令下发、不过期且不超前；同版本 sequence 递增且 stamp 不倒退。新版本清确认缓存，历史诊断不作新版本证据。先检查旧截止时间再接受新反馈；活动任务超过超时阈值则锁存故障，迟到的新鲜心跳不能补救。默认阈值 1 秒，等于阈值仍有效。

## 上层 command 与事实 event

```json
{"command_id":"work-1","type":"START_MOWING","params":{"map_id":"garden","region_ids":["region-1","region-2"],"home_id":"dock"}}
```

| 命令 | params |
| --- | --- |
| START_MOWING | map_id、非空且不重复的 region_ids；home_id 可选，默认 dock |
| START_MAPPING | map_id |
| SELECT_REGION_START | region_id |
| START_CHANNEL | channel_id |
| RETURN_HOME | map_id、station_id |
| START_EDGE_FOLLOW、TAKE_OVER、FINISH_CHANNEL、FINISH_MAPPING、PAUSE、RESUME、CANCEL、RESET_ERROR | 空对象或省略 params |

command_id 和各 ID 必须是非空字符串。用户任务身份来自开始命令的 command_id；自动回充使用避开既有任务身份的新 ID，并同样登记为已使用。同会话中任何已使用任务身份都不能重新开始另一份任务。

外部电量事实单独使用 event：

```json
{"event_id":"battery-low-1","type":"LOW_BATTERY"}
```

仅支持 LOW_BATTERY/BATTERY_OK；不接受以 event 冒充用户暂停。原型尚未验证设备事实来源或采样时效。

command_result 包含 command_id、state（ACCEPTED/REJECTED）、revision、reason、message。ACCEPTED 只表示受理，不代表执行、停车或完成；reason 可为 INVALID_COMMAND、NOT_ALLOWED、ID_CONFLICT。相同 ID 和内容返回原回执；同 ID 不同内容拒绝，且重复命令仍检查超时。结构错误但有合法 command_id 时返回 INVALID_COMMAND；缺少有效命令关联 ID、无效 status/event 或非法时间抛出 ValueError。

## brain_status 与当前策略

保留 revision、mode、phase、business_mode、fault_latched、reason；task/suspended_task 显示任务身份、当前区域、已完成区域和总数；mapping 显示会话、当前动作、暂存对象 ID 和最近对象结果；last_task_result 显示最近完整任务结果。

mission_state/suspended_mission/last_mission_result 包含 task_id、type、target_id、attempt、lifecycle、stage、action_phase、action、retry_pending；结果额外含 result/reason。type 为 MAPPING/MOW_REGION/RETURN_HOME。建图 stage 见状态机；割草为 MOW_REGION，回充为 RETURN_AND_CHARGE。暂停保持内部 action_phase，线上输出 NONE。

modules 仅含 roboframe 当前版本反馈或 null。health 包含 revision、low_battery、capabilities.current_action、causes 和 modules 诊断缓存；诊断缓存带 received_at/fresh/current。AVAILABLE 只表示当前任务有有效 READY/RUNNING/SUCCEEDED 证据，不等于许可；没有任务或证据不足为 UNAVAILABLE，原因区分 NOT_REQUESTED/INSUFFICIENT_EVIDENCE。不再列出内部 navigation/mapping 等依赖能力。

区域 SUCCEEDED 推进一次 cursor；最后一个区域完成才产生任务完成结果。低电保存原 Task，回充后 BATTERY_OK 只恢复上下文，显式 RESUME 才重启。失败锁存后先 RESET_ERROR 再 RESUME，新 attempt 不修改旧 FAILED 结果。取消结果独立为 cancelled。

建图起点及最终连通校验拒绝可返回等待用户修正；其他失败或超时进入 ERROR。COMMIT 期间普通暂停/取消拒绝，低电等待本次提交或校验结果后暂停；最终整图保存成功可回 IDLE。

## 尚未接入

SSM 系统许可和强制中断、Foundation 实际设备反馈、Brain 启动前的有效在桩/地图事实、跨重启身份、提交结果查询、可靠网络与持久化均未实现。仿真内存作业记录只验证续作归属，不承诺实机覆盖精度或停车安全。
