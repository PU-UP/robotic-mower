# Brain

Brain 管业务任务、区域顺序、暂停、低电回充和恢复决策，当前只对接单一 roboframe 任务入口。原三进程协议已移除；实际 WSL roboframe 尚未接入，本仓库用替身验证职责边界。

- [设计与职责](DESIGN.md)：Brain 状态机与 roboframe 内部 BT 的分工。
- [状态机基线](STATE_MACHINES.md)：当前可达转换、恢复条件与缺口。
- [原型协议](PROTOCOL.md)：命令、事件、directive、roboframe status 与回执。
- [建图流程](MAPPING.md)：退桩、回归通道、区域与通道、接管和保存。

`Brain.receive(kind, payload, now)` 接收 command/event/status，返回 directive/command_result/brain_status。`Brain.tick(now)` 在没有消息时检查超时。内部入口 handle 接收 Event 或 Status，不接收算法数据。

实现分为 Brain 的业务调度和统一输出、HealthEventManager 的证据过滤和去重、MissionExecution/MappingSession 的生命周期与建图业务阶段。Brain 不增加算法执行 BT；区域内动作归 roboframe。

暂停与回充后的作业使用原 task_id；Brain 保留区域级进度，空间覆盖记录归 roboframe。回充成功需 roboframe 确认设备充电事实，不能只以导航到站报告成功。这些协议语义已有替身测试，真实设备能力仍待核实。

运行 `python -m simulation` 生成总回放，或用 `--script simulation/scenarios/mission_lifecycle.json` 查看独立生命周期验收。
