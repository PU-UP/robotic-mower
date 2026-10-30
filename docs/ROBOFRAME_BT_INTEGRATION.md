# roboframe demo 与 BT 接入验收

日期：2026-10-14。实际代码工作区：WSL Ubuntu-22.04 的 `/home/watermango/work/roboframe`。
当时的完整设计位于该仓库 `docs/behavior-tree.md`；本文记录与本 Brain 仓库相关的历史接入结论。

2026-10-30 复核：当前 roboframe 工作区 HEAD 为 `21586e2`，该设计文件及 `build-bt/` 已不存在。下列测试结果为首轮验收记录，本次未重新验证；原始验收提交号未记录，复现前需找回对应源码版本，不能直接在当前主分支执行下列命令。

本文保留首轮建图 BT 验收。后续已纠正 BT 的目录/契约归属，并接入 Planner、Controller 和导航任务；后续验收见 [导航 demo](ROBOFRAME_NAVIGATION_DEMO.md)。下文“尚未接入导航”是首轮验证边界。

## 已实现

先构建当前 demo_robot，跑通 data/intel-lab 的全量 tf 回放，再在产品 integration 中接入最小 C++14 BT：

```text
Memory Sequence
  Collect  等待 FINISH，算法持续采集处理
  Drain    等待 FINISH 边界内的异步结果
  Freeze   冻结本次任务地图；没有有效地图则失败
```

实现为产品内 Sequence 与回调叶节点，没有新增第三方依赖。RUNNING 保留当前节点，SUCCESS 进入下一节点，
FAILURE 短路，Halt 清理当前运行节点且复位。它不是 BehaviorTree.CPP 或通用 BT SDK；复杂分支与编辑需求出现后再替换。

integration 在原控制 owner 上 Tick/Halt，保持原 BEGIN/FINISH/CANCEL 和 stdio v4 协议。
FINISH 同步固定输入边界，Poll 在异步结果到达后推进树；不会把 FINISH 之后的输入算入冻结地图。
CANCEL 只取消任务结果归属，持续定位、子图和实时地图仍运行。
STOP/RESET 沿原生命周期关闭输入、取消计算、停止组件；旧 session/generation 结果不能污染新任务。
首轮增加的 `mapping_tree_status()` 查询已在后续设计中移除，外部改为只读取任务状态；内部仍保留 stderr `[mapping-bt]` 日志。

## 验证结果

- 接入前原有 25 项测试通过；两份数据 SHA-256 校验通过。
- 接入后 27 项测试通过，新增 BT 语义及真实 integration 测试，覆盖完成、失败、取消、迟到结果和停止重启。
- 前后均跑完 13,631 帧扫描/里程计与 910 次修正。第 12,267 帧结束建图任务，其中 12,099 帧有效；最初 168 帧因缺少全局定位跳过全局放置，仍生成局部子图。
- 任务结束后，后续 1,364 帧继续更新实时地图。前后 final.rfgrid、live.rfgrid 逐字节相同；冻结、IPC 查询、保存和重载校验通过。
- `tests/build_isolation_test.py` 全部通过：六组件独立构建/测试/安装、纯包与混合构建、产品选择隔离、公开契约与协议适配隔离、28 个安装头独立编译；结果保存在 `build-bt/build-isolation.log`。

实际产物位于 roboframe：

- `build-bt/baseline-full/`：接入前回放。
- `build-bt/bt-full/replay.html`：BT 回放，可查看地图与轨迹。
- `build-bt/bt-full/summary.json`：帧数、任务统计与资源记录。
- `build-bt/bt-full/mapping-stderr.log`：Collect → Drain → SUCCESS 的运行记录。
- `build-bt/ctest.log`：27 项测试结果。

复现时在 roboframe 根目录运行，输出目录必须尚不存在：

```sh
cmake -S . -B build-bt -DROBOFRAME_PRODUCT=demo_robot -DCMAKE_BUILD_TYPE=Release
cmake --build build-bt -j4
ctest --test-dir build-bt --output-on-failure
python3 tools/mapping/replay.py --dataset tf --scans 0 --finish-after 12267 \
  --binary build-bt/robot_runtime --output build-bt/bt-run
```

## 接口设计结论

**当前 integration/component 边界足够承载已验证的异步建图 BT，SDK 和六个组件无需修改。**
既有 typed 接线、ExecutionChannel、任务标签、运行代次和不可变地图可以直接复用；
组件不需要认识 BT，BT 也不应接管高频传感器链路或长期地图记录。

| 接入方向 | 尚需补齐/验证 |
|---|---|
| Brain | 业务 task_id 与运行/session 标识区分、请求去重、恢复与超时；当前 Python Brain 尚未连接实际 roboframe |
| Planner/Controller | 真实任务的请求/进度/结果/取消契约，停止确认、位姿有效期、控制周期；本次没有导航闭环 |
| Coverage/Blade/对桩 | 真实能力与设备事实，不能将请求成功等同于切割、在桩或充电成功 |
| 实时运行 | 保存、加载、大地图编码和历史重建的执行隔离；真实算法的协作取消时限 |

本次没有接在线 SLAM、实机或 ARM；录制修正轨迹与离线分批回放不能作为运动闭环或实时性能证明。
