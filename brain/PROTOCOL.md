# Brain 输入输出协议 · 当前草案

本轮固定消息形状和可运行的协议约束；具体业务策略仍由后续任务逐项确定。`contracts.py` 实现字段校验与解析，`Brain.receive(kind, payload, now)` 是 JSON 入口。

```text
上层 command ──┐                 ┌── directive → perception / map_manager / pnc
外部 event ────┼──→ brain ────────┼── command_result → 上层
模块 status ───┘                 └── brain_status → 上层
```

`kind` 是通道名，不需要再放进消息 JSON。返回值包含 `directive / command_result / brain_status` 三项，是本地调用的输出集合；实际发送时分别送对应通道。没有新 directive 或没有 command ACK 时，对应项为 null。`brain_status` 是当前快照。

## 1. Brain → 模块：directive

```json
{
  "revision": 4,
  "mode": "WORKING",
  "phase": "EXECUTE",
  "mission": {
    "type": "COVER_REGION",
    "map_id": "garden",
    "target_id": "region-2",
    "control": "AUTO"
  }
}
```

| 字段 | 语义 |
| --- | --- |
| revision | Brain 每次改变 mode、phase 或当前 mission 时递增；是控制指令版本，不是地图版本 |
| mode | 当前期望的业务模式 |
| phase | 当前 mission 的执行阶段 |
| mission | 当前具体目标及最少参数；没有可执行任务时为 null |

同一份 directive 发给三个模块。模块根据 mode / phase / mission.type 执行自己的职责。同版本重复交付不重启执行，旧版本丢弃。

模式：`IDLE / MAPPING / WORKING / RETURNING / PAUSED / CHARGING / ERROR`。

阶段：`PREPARE` 准备但不开始任务；`EXECUTE` 执行当前目标；`COMMIT` 提交建图结果；`NONE` 无可执行目标。`phase` 表达目标阶段，不是额外的命令队列。

当前 mission（建图流程见 [建图业务 01](MAPPING.md)）：

所有非 null 的 mission 必须包含四个字段：type、map_id、target_id、control。字段不可省略；无具体操作对象时 target_id 明确为 null。map_id 始终是非空业务地图 ID，target_id 的对象类型由 type 确定，建图时允许指向正在创建的对象。

| type | target_id | control | 当前 mode |
| --- | --- | --- | --- |
| COVER_REGION | 区域 ID | AUTO | WORKING |
| MANUAL_DRIVE | null | MANUAL | MAPPING |
| MAP_REGION | 区域 ID | MANUAL / AUTO | MAPPING |
| MAP_CHANNEL | 通道 ID | MANUAL | MAPPING |
| SAVE_MAP | null | NONE；仅 COMMIT 阶段 | MAPPING |
| RETURN_HOME | 充电站 ID | AUTO | RETURNING |

control 表示任务的控制方式，只有 EXECUTE 阶段允许运动；PREPARE / COMMIT 阶段 PNC 保持停止。AUTO 的具体行为由 type 决定：MAP_REGION 自动沿边、COVER_REGION 覆盖、RETURN_HOME 回充。接管与恢复只切换当前区域的 MANUAL / AUTO，保留 map_id、target_id 和采集上下文。

三个模块共用 contracts.py 的解析与合法组合校验。旧 mission 中的 region_id / channel_id / station_id 和 AUTO_EDGE 不再接受；上层 command 参数仍保留原有业务名称，由 brain 转为统一 mission。无当前任务时仍为 mission: null。


任务 ID、完整目标列表、游标、历史进度只留在 brain。directive 不携带它们。地图版本、定位参考关系与几何在同层数据接口中管理，不混入控制指令版本。

暂停示例：`{"revision":5,"mode":"PAUSED","phase":"NONE","mission":null}`。这表达停止意图；实际是否已停仍以模块的 status 为准。

## 2. 模块 → Brain：status

```json
{
  "module": "pnc",
  "revision": 4,
  "sequence": 18,
  "stamp": 12.3,
  "state": "RUNNING",
  "progress": 0.35,
  "reason": null
}
```

| 字段 | 语义 |
| --- | --- |
| module | perception / map_manager / pnc |
| revision | 正在反馈的 directive 版本；即使拒绝指令，也填写被拒绝版本 |
| sequence | 同一模块、同一 revision 内递增，过滤重复和倒序状态 |
| stamp | 状态产生时刻；仿真用单调秒，不因晚到而刷新 |
| state | 下面定义的统一执行状态 |
| progress | 可选，0～1，仅当前目标的参考进度；不代表整个业务任务的进度 |
| signal | 可选；当前 REGION_CLOSED 表示检测到当前区域回到起点，不等于已保存 |
| reason | 可选/null；失败或阻塞时使用稳定原因码，如 LOCALIZATION_LOST、MAP_NOT_FOUND |

| state | 含义 |
| --- | --- |
| READY | 已应用此版本，当前阶段要求的输入和资源已准备好 |
| RUNNING | 正在执行此版本对应职责；PREPARE 中也可表示尚在准备 |
| SUCCEEDED | 此版本的有限任务已完成；必须由该任务的负责模块报告 |
| BLOCKED | 暂时无法继续；负责执行的模块已采取本地停止措施 |
| FAILED | 已开始的操作执行失败 |
| REJECTED | 无法接受此指令，例如目标不存在或不支持该 mission |
| STOPPED | 此版本下已停止任务执行；不等于进程退出 |

三模块共用 envelope，**不要求它们同一时刻返回相同 state**：

| 当前交互 | perception | map_manager | pnc |
| --- | --- | --- | --- |
| PREPARE | 定位/感知资源就绪后 READY | 业务地图/目标可用或草稿就绪后 READY | 当前输入就绪且尚未执行时 READY |
| 覆盖 EXECUTE | RUNNING，维持感知定位 | READY，提供可用业务地图 | RUNNING + 可选 progress，完成后 SUCCEEDED |
| 遥控转场 EXECUTE | RUNNING，提供定位 | READY，不采集 | RUNNING，允许遥控 |
| 区域/通道采集 EXECUTE | RUNNING，可报告 REGION_CLOSED | RUNNING，记录草稿，区域可报告 REGION_CLOSED | RUNNING，按 mission 执行自动沿边或遥控 |
| 建图 COMMIT | RUNNING | 提交成功后 SUCCEEDED | STOPPED |
| 暂停/取消/错误停止 | 当前替身报告 STOPPED | 当前替身报告 STOPPED | 实际停止后 STOPPED |

持续提供感知不意味着整个覆盖任务完成，perception 的 SUCCEEDED 不能结束覆盖。当前覆盖/回充的完成方为 pnc，建图提交的完成方为 map_manager。

status 只汇报结果/事实，不要求 brain 采取某项未来决策。位姿、障碍物、地图、轨迹、执行历史均不放入 status。后续若业务确实需要新的摘要字段，再按任务加入。

状态变化立即报告，执行期间周期报告。此仿真周期 0.1 秒，超时 1 秒；这些不是实机指标。revision 不匹配、stamp 过期/来自未来、sequence 重复或倒序的状态不推进业务。

每次合法输入处理前与独立 tick 都检查已发生的超时，超时边界为 elapsed > timeout。截止时间之后的新心跳不能覆盖旧时间戳来补救超时。首次发现超时的同次普通命令会被拒绝并下发 ERROR，需要后续新的 RESET_ERROR 请求解除锁存；重复命令仍返回原 ACK，同时可产生独立的超时 ERROR 指令。

## 3. 上层 → Brain：command

上层表达业务意图，不直接设置 mode / phase，不直接命令三个算法模块。

```json
{
  "command_id": "work-1",
  "type": "START_MOWING",
  "params": {
    "map_id": "garden",
    "region_ids": ["region-1", "region-2"]
  }
}
```

| type | params | 当前示例语义 |
| --- | --- | --- |
| START_MOWING | map_id, region_ids；可选 home_id（仿真默认 dock） | 请求完成这些区域；顺序暂按请求排列 |
| START_MAPPING | map_id | 开始整次建图会话，先遥控转场 |
| SELECT_REGION_START | region_id | 记录新区域的起点 |
| START_EDGE_FOLLOW | 无 | 开始/继续当前区域的自动沿边 |
| TAKE_OVER | 无 | 临时遥控接管当前区域，保留起点和草稿 |
| START_CHANNEL | channel_id | 校验起点在已有区域内后遥控采集通道 |
| FINISH_CHANNEL | 无 | 结束并提交当前通道 |
| FINISH_MAPPING | 无 | 所有对象已结束后，保存并结束整次建图 |
| RETURN_HOME | map_id, station_id | 请求前往该充电站 |
| PAUSE | 无 | 暂停当前业务 |
| RESUME | 无 | 请求恢复，具体从哪里继续由 brain 决定 |
| CANCEL | 无 | 请求取消当前及挂起业务 |
| RESET_ERROR | 无 | 请求解除错误锁存，不自动恢复运动 |

无参数的命令可省略 params，或写 `{}`。例如 `{"command_id":"pause-1","type":"PAUSE"}`。

command_id 非空，会话内标识一次请求。合法命令同 ID、同语义重发时返回原来的受理结果，不重复执行；同 ID 改内容返回 ID_CONFLICT。格式不合法的消息返回 INVALID_COMMAND，不进入业务事件记录；缺少有效 command_id 时入口直接报错，因为无法关联 ACK。

当前 START 类命令接受后，以 command_id 作为内部 task_id，省去另一个必须由上层生成的 ID。任务完成/取消仍按 task_id 对应到最初请求。

## 4. 外部 → Brain：event

```json
{"event_id":"battery-7","type":"LOW_BATTERY"}
```

目前只有 `LOW_BATTERY / BATTERY_OK` 两个事实事件。指令与事实分开：用户要求暂停是 command；电量达到阈值是 event。event_id 按会话去重，与 command_id 的命名空间分开。当前按交付顺序处理事实；真实跨源排序、事件新鲜度待接入实际来源时确定。

## 5. Brain → 上层：受理结果与业务状态

command_result 是命令受理回执：

```json
{
  "command_id": "work-1",
  "state": "ACCEPTED",
  "revision": 1,
  "reason": null,
  "message": ""
}
```

拒绝时 state 为 REJECTED，reason 为 `INVALID_COMMAND / NOT_ALLOWED / ID_CONFLICT`，message 说明原因。revision 是原命令处理时的控制版本；重复命令返回原版本，不能用它覆盖更新的状态。

**ACCEPTED 仅表示 brain 接受此业务请求，不代表三个模块准备完成、机器人已停，或任务已完成。**

brain_status 是向上提供的当前业务快照：

```json
{
  "revision": 4,
  "mode": "WORKING",
  "phase": "EXECUTE",
  "task": {
    "task_id": "work-1",
    "type": "MOW",
    "completed_targets": ["region-1"],
    "total_targets": 2,
    "current_target": "region-2"
  },
  "suspended_task": null,
  "last_task_result": null,
  "reason": null,
  "modules": {"perception": null, "map_manager": null, "pnc": null}
}
```

建图期间另有 mapping 摘要：session_id、map_id、已完成 regions/channels、current 与 last_result。区域完成只更新会话；最终保存完成后 last_task_result 记录整个会话及其对象列表。

modules 保存各模块**当前 revision 下已收到的有效 status**；null 表示还没有本版本反馈，不表示故障。上例是新 revision 发出、反馈尚未到达时的合法快照。

新增 `health` 观测字段，由 Health / Event Manager 生成，现有字段保留：

| 字段 | 含义 |
| --- | --- |
| revision / low_battery | 当前控制版本与去重后的电量事实 |
| capabilities | navigation、manual_drive、mapping、map_commit 各自的 state、reason、causes |
| causes | 当前版本的证据不足、过期或模块失败原因，包含 module、reason、revision、stamp |
| modules | 各模块最后被接受的 status、received_at、fresh、current；没有历史时不包含该模块 |

能力结论目前为 AVAILABLE / UNAVAILABLE，只针对当前 Action。未请求的能力为 UNAVAILABLE / NOT_REQUESTED；缺少有效依赖证据为 UNAVAILABLE / INSUFFICIENT_EVIDENCE。不会推断未请求能力或 DEGRADED。导航与手动控制依赖三模块；建图能力依赖 perception 与 map_manager；提交能力单独依赖 map_manager。模块有效状态为 READY / RUNNING / SUCCEEDED，STOPPED 不构成能力可用证据。AVAILABLE 不代替准备阶段的三方 READY 确认，也不直接授权执行；当前 Brain 的故障锁存规则仍然生效。

health.modules 可保留上一版本诊断证据，current=false 的记录不用于当前准备或完成判断。当前没有足够证据进行跨模块根因推断，保留各模块原因。所有返回快照与内部可变数据隔离。

任务完成后 task 为 null，last_task_result 变为 `{"task_id":"work-1","result":"completed"}`；取消则为 cancelled。暂停/错误中保留 task，低电抢占时原任务进入 suspended_task。完整业务历史目前只在 brain 与仿真观察数据中保存，last_task_result 只是最近一个结果，不是可靠事件订阅服务。

## 6. 目前示例策略，后续按业务迭代

- 三方 READY 后发 EXECUTE；只有当前目标负责模块的 SUCCEEDED 推进任务。
- BLOCKED / FAILED / REJECTED 或状态超时通常进入 ERROR；RESET_ERROR 后再显式 RESUME。通道准备中 map_manager 拒绝 CHANNEL_START_OUTSIDE_REGION 时，返回遥控转场并保留会话，允许重试。
- 暂停保留已完成目标；当前未完成区域重新执行，不是轨迹级续作。
- 低电抢占覆盖任务去回充，电量恢复后等待显式续作。
- 普通暂停/取消不打断地图 COMMIT；真实提交 ACK 丢失的幂等查询尚未实现。
- 区域/通道 COMMIT 期间低电，成功提交后只记录一次对象进度，进入 PAUSED；电量恢复后仍需显式 RESUME，恢复目标为遥控转场。最终 SAVE_MAP 成功则结束会话并 IDLE。

这些用于验证接口，不提前确定最终业务政策。例如“阻塞是否重试”“主动回充是否抢占”“启动需哪些模块 READY”，由你提供业务后在 brain 中修改，并在独立 JSON 场景中增加正常/异常期望。

当前仅单 brain 会话，revision 无跨重启 epoch；无可靠网络、进程崩溃恢复、实机时钟同步或物理停车保证。接入实机前必须补齐对应机制。
