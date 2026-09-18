# map_manager

负责业务地图的创建、编辑、版本、保存与发布。这里不是 SLAM 模块。当前包只定义 BusinessMap / Entity，内存建图行为由仿真替身提供。

- 输入：brain 的 mode/当前 mission，perception 的定位/SLAM map ID，未来地图编辑数据。
- 输出给 brain：status；完成业务地图提交后才能报告 SUCCEEDED。
- 输出给 pnc：业务地图及定位参考关系。
- 长期数据：区域、边界、通道、禁区、岛、充电站等；不保存割草任务的业务进度。

当前用 map_id / revision / slam_map_id / frame_id 声明参考关系。ID 对齐不等于坐标变换；第一版只接受同坐标系，换图、SLAM 重置及真实坐标变换需单独设计和验证。

草稿记录、几何校验、可靠持久化和编辑事务是下一个建图任务的实现范围，当前不预建增量同步、候选晋升或地图传输框架。
