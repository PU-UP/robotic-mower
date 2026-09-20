# brain

brain 管理完整业务逻辑：任务顺序、已完成进度、暂停、抢占、恢复和错误策略。算法同层的数据不穿过 brain。

目标架构见 [Brain 设计：分层状态机 + 按需行为树](DESIGN.md)：Mode 管大业务，Mission 管生命周期与业务阶段，复杂阶段按需使用行为树；独立的 Health / Event Manager 整理模块状态、能力与异常原因。文档包含现有协议的兼容映射与分步迁移方案，运行代码尚未完成该改造。

本轮以 [输入输出协议](PROTOCOL.md) 为准。directive 已按用户提出的结构收敛：

```json
{
  "revision": 4,
  "mode": "WORKING",
  "phase": "EXECUTE",
  "mission": {"type": "COVER_REGION", "map_id": "garden", "target_id": "region-2", "control": "AUTO"}
}
```

入口：`Brain.receive(kind, payload, now)`，kind 为 `command / event / status`。输出集合为 `directive / command_result / brain_status`，便于仿真或未来通信适配器分别发布。`Brain.tick(now)` 负责没有消息时检查状态超时。

`Brain.handle(Event | Status, now)` 是内部状态机入口；内部完整 Mission 和 Task 不作为下层接口。WorkItem 是当前目标的值类型，经 `to_dict()` 序列化为精简 mission。

现有状态机保留为可运行示例，业务尚未定稿。后续每个任务按以下顺序推进：明确上层意图与完成条件 → 三模块职责 → 正常/异常交互脚本 → 修改 brain 规则 → 验证。具体边界与当前简化见协议末尾。

可以先阅读 [两区域协议示例](../simulation/scenarios/cover_regions.json)：它会在 revision 4 产生上面的完整 directive。再看 [暂停/迟到反馈/超时示例](../simulation/scenarios/pause_and_timeout.json)。

首个明确业务已实现：[建图业务 01：两个区域与一条通道](MAPPING.md)。START_MAPPING 只接收 map_id；区域选择、沿边、接管、通道和最终保存是会话内独立交互。
