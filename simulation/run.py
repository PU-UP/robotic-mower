"""SimPy virtual time, explicit control/status links, separate task fixtures."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path

import simpy

from brain import Brain
from contracts import Directive, Status, Event, EventKind, Mission, MissionKind, Module, Mode, Phase, MissionType
from simulation.doubles import RoboframeDouble, garden, DOCK_POSITION, DOCK_EXIT
from simulation.report import write_report


class Simulation:
    def __init__(self, *, mapped=True, feedback="auto", automatic_devices=True):
        if feedback not in ("auto", "scripted"):
            raise ValueError("feedback must be auto or scripted")
        self.feedback = feedback
        self.env = simpy.Environment()
        self.brain = Brain()
        self.runtime = RoboframeDouble(garden() if mapped else None)
        self.automatic_devices = automatic_devices
        self.device_charging = False
        self.events, self.frames = [], []
        self.observation = None
        self.position = DOCK_POSITION
        self.data_enabled = True
        self.env.process(self._run())

    def record(self, source, action, **fields):
        self.events.append({"time": round(self.env.now, 4), "source": source, "action": action, **fields})

    def dispatch(self, directive):
        if directive is None:
            return
        self.record("brain", "mode_mission", **directive.to_dict(), payload=directive.to_dict(), target="roboframe", reason=self.brain.reason,
                    brain_after=self.brain.view())
        self.env.process(self._command(self.runtime, directive))

    def _command(self, module, directive):
        yield self.env.timeout(0.01)
        module.configure(Directive.from_dict(json.loads(json.dumps(directive.to_dict()))), self.env.now)

    def _status(self, status, delay=0.01):
        yield self.env.timeout(delay)
        self.receive("status", status.to_dict())

    def receive(self, kind, payload):
        payload = json.loads(json.dumps(payload, allow_nan=False))
        source = payload.get("module", "external") if kind == "status" else "external"
        self.record(source, kind, target="brain", payload=payload)
        delivery = self.events[-1]
        delivery["brain_before"] = self.brain.view()
        result = self.brain.receive(kind, payload, self.env.now)
        delivery["brain_after"] = self.brain.view()
        if result["directive"]:
            self.dispatch(Directive.from_dict(result["directive"]))
        if result["command_result"]:
            self.record("brain", "command_result", target="external", payload=result["command_result"],
                        brain_after=self.brain.view())
        return result

    def inject(self, event):
        """Convenience for existing fixtures; all delivery uses the public JSON API."""
        if event.kind in (EventKind.LOW_BATTERY, EventKind.BATTERY_OK):
            return self.receive("event", {"event_id": event.event_id, "type": event.kind.value})
        if event.kind == EventKind.START:
            task = event.mission
            if task.kind == MissionKind.MOW:
                kind, params = "START_MOWING", {"map_id": task.map_id,
                    "region_ids": list(task.targets), "home_id": task.home_id}
            else:
                kind, params = "RETURN_HOME", {"map_id": task.map_id, "station_id": task.targets[0]}
            return self.receive("command", {"command_id": task.mission_id, "type": kind, "params": params})
        kind = "RESET_ERROR" if event.kind == EventKind.RESET else event.kind.value
        return self.receive("command", {"command_id": event.event_id, "type": kind})

    def _run(self):
        while True:
            now = self.env.now
            runtime = self.runtime
            if self.feedback == "auto":
                if self.automatic_devices:
                    runtime.blade_state = "RUNNING" if runtime.blade_requested else "STOPPED"
                self.position = runtime.motion_target(now, self.position)
                if self.automatic_devices:
                    # Contact persists in the simulated device after the task ends.
                    at_dock = math.dist(self.position, DOCK_POSITION) < 1e-6
                    self.device_charging = at_dock and (self.device_charging or runtime.control == "DOCK")
                    runtime.charging = self.device_charging
            if self.data_enabled:
                self.observation = runtime.observe(now, self.position)
            if self.feedback == "auto":
                runtime.step(now, self.observation)
                if not runtime.silent:
                    self.env.process(self._status(runtime.status(now)))
            before_tick = self.brain.view()
            tick_output = self.brain.tick(now)
            if tick_output:
                self.record("clock", "tick", target="brain", payload={"now": now},
                            brain_before=before_tick, brain_after=self.brain.view())
            self.dispatch(tick_output)
            observed_map = runtime.working_map or runtime.business_map
            self.frames.append({"time": round(now, 4), "brain": self.brain.view(),
                "position": list(self.position), "trace": list(runtime.trace),
                "map": asdict(observed_map) if observed_map else None,
                "modules": {"roboframe": {"state": runtime.state if self.feedback == "auto" else (
                    self.brain.statuses[Module.ROBOFRAME].state if Module.ROBOFRAME in self.brain.statuses else "UNKNOWN"),
                    "revision": runtime.directive.revision, "progress": runtime.progress,
                    "reason": runtime.reason, "control": runtime.control, "route": runtime.route,
                    "stage": runtime.stage, "blade_state": runtime.blade_state, "charging": runtime.charging,
                    "coverage": [{"task_id": key[0], "map_id": key[1], "target_id": key[2], "segments": list(segments)}
                                 for key, segments in runtime.coverage.items()]}}})
            yield self.env.timeout(0.1)

    def until(self, when):
        self.env.run(until=when)


def mowing(mission_id="mow-1"):
    return Mission(mission_id, MissionKind.MOW, "garden", ("region-1", "region-2"))


SCENARIOS = {
    "mowing": "独立割草：brain 逐个下发目标，只接收当前目标结果",
    "pause_resume": "暂停续作：保留已完成目标，重新准备被打断的目标",
    "return_home": "独立回充：设备确认充电 → CHARGING → 电量恢复",
    "low_battery": "低电抢占：brain 保存割草任务，回充后显式续作",
    "fault_recovery": "定位故障：ERROR 锁存 → RESET → 显式 RESUME",
    "status_timeout": "模块失联：即使没有状态消息，超时也进入 ERROR",
    "stale_input": "定位数据中断：roboframe 内部停止，brain 根据 BLOCKED 进入 ERROR",
    "cancel": "取消任务：清空业务上下文，下层停止执行",
}


def run_scenario(name):
    if name == "mapping":
        from simulation.scripted import run_script
        return run_script(Path(__file__).with_name("scenarios") / "mapping_session.json")
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario: {name}")
    sim = Simulation(mapped=name != "mapping")
    checks = []

    def check(label, condition):
        checks.append({"name": label, "passed": bool(condition)})

    def event(at, kind, mission=None):
        if at > sim.env.now:
            sim.until(at)
        sim.inject(Event(f"{name}:{at}:{kind}", kind, mission))

    if name == "return_home":
        sim.position = (9.0, 2.0)  # Return through the ordinary channel and return channel.
        event(0, EventKind.START, Mission("home-1", MissionKind.RETURN_HOME, "garden", ("dock",)))
        sim.until(1.4)
        check("到站后等待充电完成事件", sim.brain.directive.mode == Mode.CHARGING)
        event(1.5, EventKind.BATTERY_OK)
        sim.until(1.8)
        check("无挂起任务时回到 IDLE", sim.brain.directive.mode == Mode.IDLE)
    else:
        event(0, EventKind.START, mowing())
        if name == "pause_resume":
            event(2.25, EventKind.PAUSE)
            sim.until(2.7)
            check("暂停不丢失第一个目标的完成记录", sim.brain.task.cursor == 1
                  and sim.runtime.state == "STOPPED")
            event(2.8, EventKind.RESUME)
        elif name == "low_battery":
            event(2.25, EventKind.LOW_BATTERY)
            sim.until(3.5)
            check("回充期间业务进度归 brain 保存", sim.brain.directive.mode == Mode.CHARGING
                  and sim.brain.suspended.cursor == 1)
            event(3.6, EventKind.BATTERY_OK)
            check("充好电后不自动恢复运动", sim.brain.directive.mode == Mode.PAUSED)
            event(3.8, EventKind.RESUME)
        elif name == "fault_recovery":
            sim.until(0.4)
            sim.runtime.fault = "localization lost"
            sim.until(0.7)
            check("定位异常进入 ERROR", sim.brain.directive.mode == Mode.ERROR)
            sim.runtime.fault = ""
            sim.until(1.0)
            check("正常状态不会自动解除 ERROR", sim.brain.directive.mode == Mode.ERROR)
            event(1.1, EventKind.RESET)
            event(1.2, EventKind.RESUME)
        elif name == "status_timeout":
            sim.runtime.silent = True
            sim.until(1.4)
            check("准备阶段无 ACK 不开始执行", not any(
                e["action"] == "mode_mission" and e["phase"] == Phase.EXECUTE for e in sim.events))
            check("失联触发超时", sim.brain.directive.mode == Mode.ERROR
                  and "timeout" in sim.brain.reason)
        elif name == "stale_input":
            sim.until(0.3)
            sim.data_enabled = False
            sim.until(1.1)
            check("数据过期阻止完成当前目标", sim.brain.directive.mode == Mode.ERROR
                  and sim.brain.task.cursor == 0)
        elif name == "cancel":
            event(0.4, EventKind.CANCEL)
            sim.until(0.8)
            check("取消后清空任务并停止", sim.brain.task is None
                  and sim.brain.directive.mode == Mode.IDLE
                  and sim.runtime.state == "STOPPED")
        sim.until(8)
        if name in ("mowing", "pause_resume", "low_battery", "fault_recovery"):
            check("割草任务完成", {"mission_id": "mow-1", "result": "completed"} in sim.brain.history
                  and sim.brain.directive.mode == Mode.IDLE)
    check("brain 只接收外部事件和roboframe status", all(
        e["action"] in ("command", "event", "command_result", "status", "mode_mission", "tick") for e in sim.events))
    check("所有外部事件被明确接受", all(e["payload"]["state"] == "ACCEPTED" for e in sim.events if e["action"] == "command_result"))
    return {"scenario": name, "description": SCENARIOS[name], "checks": checks,
            "frames": sim.frames, "events": sim.events, "final": sim.brain.view()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--scenario", choices=["all", "mapping", *SCENARIOS])
    selection.add_argument("--script", type=Path, help="run a JSON interaction scenario")
    parser.add_argument("--output", type=Path, default=Path("simulation/output"))
    args = parser.parse_args()
    from simulation.scripted import run_script
    if args.script:
        results = [run_script(args.script)]
    elif args.scenario and args.scenario != "all":
        results = [run_scenario(args.scenario)]
    else:
        results = [run_scenario(name) for name in SCENARIOS]
        results.extend(run_script(path) for path in sorted(Path(__file__).with_name("scenarios").glob("*.json")))
    args.output.mkdir(parents=True, exist_ok=True)
    for result in results:
        folder = args.output / result["scenario"]
        folder.mkdir(exist_ok=True)
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n"
                                                    for e in result["events"]), encoding="utf-8")
        write_report([result], folder / "report.html")
    write_report(results, args.output / "report.html")
    failed = sum(not check["passed"] for result in results for check in result["checks"])
    print(f"{len(results)} scenarios; {failed} failed checks; report: {args.output / 'report.html'}")
    return int(failed > 0)
