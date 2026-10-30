# 历史设计与实验记录

这些资料保留架构讨论的演进依据；历史结论不自动成为当前要求。持续维护的设计入口是 [系统职责参考](../../SYSTEM_DESIGN.md) 和 [roboframe 参考架构](../ROBOFRAME_ARCHITECTURE_BASELINE.md)，首款产品见 [rlcp 基线](../RLCP_BASELINE.md)。

- [Server 架构 V1](MOWER_SERVER_ARCHITECTURE_V1.md)：早期职责划分。
- [算法架构 V2](MOWER_ALGORITHM_ARCHITECTURE_V2.md)：算法、数据流及部署讨论。
- [Brain 原型设计](BRAIN_PROTOTYPE_DESIGN.md)：已退役原型的业务职责、状态与数据归属讨论；不继续维护旧协议与代码。
- [原型重构记录](../BRAIN_ROBOFRAME_REFACTOR.md)：2026-10-14 的迁移和替身验收记录。
- [建图 BT 验收](../ROBOFRAME_BT_INTEGRATION.md)、[导航 demo 验收](../ROBOFRAME_NAVIGATION_DEMO.md)：独立 roboframe 工作区的历史实验，不代表产品验收。

2026-10-30 保留 V1/V2 供追溯；移除旧 Python 原型和与公司现状无关的团队人数配置。原型完整代码、协议、场景和测试仍可在 Git 提交 `9ba6387` 中查阅。新参考结论更新当前架构文档，旧稿保持历史语境。
