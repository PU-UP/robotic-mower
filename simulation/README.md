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

打开 output/report.html 选择场景，或直接打开 output/mapping_session/report.html 查看建图流程。

回放按消息到达顺序逐步展示：用户在上方，brain 居中，perception、map_manager、pnc 并排在下方。节点位置不变，每步只改变中文消息内容、状态和高亮箭头。顶部并排展示中文说明和本步完整 JSON（directive、status 或上层输入），消息区高度固定，长消息在区内滚动。蓝色表示 brain 下发任务，绿色表示输入或返回。上一步 / 下一步、键盘左右键和进度条均可定位；跳转菜单可直接选择接管、区域闭环、通道起点校验等关键动作，自动播放可调整节奏。

重复状态心跳和仅有进度数值变化的消息合并展示，完整历史仍保留在默认折叠的技术详情中。模块卡片沿用已有 STOPPED、READY、RUNNING、SUCCEEDED、BLOCKED、FAILED、REJECTED 基本状态，显示最近一次观测，不随新 directive 清空；未观测到状态时显示未知。brain 对当前版本的就绪确认独立统计，闭环 signal 作为消息展示，不混入模块状态。本轮不扩展各算法模块的内部状态机。界面按原始事件顺序重建当前指令，即使同一时间发生多条消息，也不会提前显示后续决策。地图是当前时刻或更早的采样，用于辅助理解位置和草稿；不代表算法模块间每条高频数据传输。

## 两种反馈方式

`feedback: "auto"`：三个算法替身自动准备、运行和反馈，适合业务完整链路。覆盖/回充用定时完成回执，建图用脚本矩形，不模拟真实算法。

`feedback: "scripted"`：关闭自动状态反馈，完全按步骤发送模块 status，适合逐条定义业务交互、等待条件、消息延迟、重复完成和超时。脚本不直接修改 brain，不注入最终 mode；所有业务转换仍由 brain 决定。

## 场景格式

```json
{
  "name": "my_business",
  "description": "这里填写业务目标与待验证交互",
  "feedback": "auto",
  "mapped": true,
  "duration": 2,
  "steps": [
    {"at": 0, "command": {"command_id": "work-1", "type": "START_MOWING", "params": {"map_id": "garden", "region_ids": ["region-1"]}}},
    {"at": 0.3, "label": "已开始执行当前目标", "expect": {"directive": {"mode": "WORKING", "phase": "EXECUTE"}}},
    {"at": 1.5, "label": "任务完成", "expect": {"brain_status": {"mode": "IDLE", "last_task_result": {"task_id": "work-1", "result": "completed"}}}}
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
| fault | 自动替身故障，如 `{"module":"perception","reason":"LOCALIZATION_LOST"}` 或 `{"module":"map_manager","silent":true}` |
| expect | 检查 directive / command_result / brain_status 的指定字段，未写字段不参与匹配 |

status 步骤可额外带 `delay`，默认 0.01 秒；可用较长延迟制造乱序。command/event 在步骤时刻送达 brain。清除故障用 reason 空字符串；恢复反馈用 silent=false。fault 用于 auto 模式；scripted 模式直接安排 FAILED/BLOCKED/REJECTED 或停止发状态。

期望检查允许部分对象匹配，数组按完整内容匹配。至少需要一个 expect；失败会在报告中保留 expected 与 actual。step 必须早于 duration，避免最后一步尚未交付却提前结束。若要观察一条 status 的结果，expect 应安排在其交付时间之后。

world 步骤提供 position: [x,y] 给感知替身，不把坐标交给 brain；用于模拟转场、沿边和采集。mapping_session.json 是完整业务，--scenario mapping 为便捷入口。

`mapped: true`（默认）提供 garden，含 region-1 / region-2 / dock；`false` 从空业务地图开始。每份脚本都有独立 brain 和模块实例，无前序运行依赖。

## 后续迭代

你提供业务目的、触发条件和希望的交互后：先写一个场景与期望，补入 brain 业务转换，再调整相应模块反馈；新协议字段确有需要才增加。现有 START/暂停/回充规则只是示例策略，不作为未讨论业务的既定要求。

原有自动示例继续覆盖割草、暂停续作、回充、低电抢占、故障恢复、status 超时、感知过期和取消。JSON 示例验证协议形状、异步交互、故障恢复和完整多对象建图。地图与采集轨迹可在逐帧数据中查看。

仿真不验证 SLAM、几何算法、地图可靠保存、物理运动或实机安全。无跨进程时钟、可靠重传或重启恢复；控制/状态默认延迟 0.01 秒、循环周期 0.1 秒是仿真假设。
