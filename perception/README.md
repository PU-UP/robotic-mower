# perception

负责感知、定位以及内部 SLAM 数据。当前包只定义不可变 Observation，真实算法由后续独立任务补齐，仿真替身位于 simulation。

- 输入：brain 的 mode/当前 mission，传感器数据。
- 输出给 brain：status（准备、运行、故障等）。
- 输出给 map_manager：定位、SLAM map ID、坐标系，用于业务地图记录与对齐。
- 输出给 pnc：定位、当前局部环境；带采样时间，不因转发而刷新。

不保存业务任务历史，不生成业务区域地图，不选择下一项任务。SLAM 地图与业务地图即使 ID 有对应关系，也不是同一种地图。
