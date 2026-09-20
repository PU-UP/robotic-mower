"""Business state machine. Inputs: Event / Status. Output: mode + current mission."""
from dataclasses import asdict, dataclass, field, replace
from copy import deepcopy
import math

from brain.health import HealthEventManager

from contracts import Directive, Event, EventKind, Mission, MissionKind, Module, Mode, Phase, State, Status, WorkItem, MissionType, command_event, system_event, identifier, Control


@dataclass
class Task:
    mission: Mission
    cursor: int = 0

    def current(self):
        m = self.mission
        kind = {MissionKind.MOW: MissionType.COVER_REGION,
                MissionKind.RETURN_HOME: MissionType.RETURN_HOME}[m.kind]
        return WorkItem(kind, m.map_id, m.targets[self.cursor], Control.AUTO)


@dataclass
class MappingSession:
    session_id: str
    map_id: str
    current: WorkItem
    regions: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    phase: Phase = Phase.PREPARE
    last_result: dict | None = None

    def view(self):
        return {"session_id": self.session_id, "map_id": self.map_id,
                "regions": list(self.regions), "channels": list(self.channels),
                "current": self.current.to_dict(), "last_result": deepcopy(self.last_result)}


class Brain:
    def __init__(self, status_timeout=1.0):
        self.health = HealthEventManager(status_timeout)
        self.directive = Directive(0, Mode.IDLE, Phase.NONE, None)
        self.health.begin(self.directive, 0.0)
        self.task = None
        self.mapping = None
        self.suspended = None
        self.history = []
        self.used_missions = set()
        self.reason = ""
        self.last_result = None
        self.last_command_result = None
        self.now = 0.0

    @property
    def statuses(self):
        return self.health.statuses

    @property
    def low_battery(self):
        return self.health.low_battery


    def receive(self, kind, payload, now):
        """JSON API: command / event / status in; independent output messages out."""
        self._clock(now)
        acknowledgement = None
        if kind == "command":
            if not isinstance(payload, dict):
                raise ValueError("command must be a JSON object")
            identifier(payload.get("command_id"))
            try:
                event = command_event(payload)
            except ValueError as error:
                directive = self.tick(now)
                acknowledgement = {"command_id": payload["command_id"], "state": "REJECTED",
                    "revision": self.directive.revision, "reason": "INVALID_COMMAND", "message": str(error)}
            else:
                directive = self.handle(event, now)
                result = self.last_result
                acknowledgement = {"command_id": payload["command_id"],
                    "state": "ACCEPTED" if result["accepted"] else "REJECTED",
                    "revision": result["revision"],
                    "reason": None if result["accepted"] else (
                        "ID_CONFLICT" if result["reason"] == "event_id reused" else "NOT_ALLOWED"),
                    "message": result["reason"]}
            self.last_command_result = acknowledgement
        elif kind == "event":
            directive = self.handle(system_event(payload), now)
        elif kind == "status":
            directive = self.handle(Status.from_dict(payload), now)
        else:
            raise ValueError(f"unsupported input channel: {kind}")
        return {"directive": directive.to_dict() if directive else None,
                "command_result": deepcopy(acknowledgement), "brain_status": self.status()}

    def status(self):
        """Upper-layer observation; task IDs never leak into algorithm directives."""
        def task_status(task):
            if task is None:
                return None
            return {"task_id": task.mission.mission_id, "type": task.mission.kind.value,
                    "completed_targets": list(task.mission.targets[:task.cursor]),
                    "total_targets": len(task.mission.targets),
                    "current_target": task.mission.targets[task.cursor]}
        last = deepcopy(self.history[-1]) if self.history else None
        return {"revision": self.directive.revision, "mode": self.directive.mode.value,
                "phase": self.directive.phase.value, "task": task_status(self.task),
                "mapping": self.mapping.view() if self.mapping else None,
                "suspended_task": task_status(self.suspended),
                "last_task_result": {"task_id": last["mission_id"], **{key: value for key, value in last.items() if key != "mission_id"}} if last else None,
                "reason": self.reason or None, "health": self.health.snapshot(self.now),
                "modules": {module.value: self.statuses[module].to_dict() if module in self.statuses else None
                            for module in Module}}

    def _clock(self, now):
        if not math.isfinite(now) or now < self.now:
            raise ValueError("brain requires monotonic finite time")
        self.now = now

    def _issue(self, mode, phase=Phase.NONE, reason=""):
        self.reason = reason
        # Paused/faulted algorithms receive no executable mission or hidden checkpoint.
        item = self.task.current() if self.task and phase != Phase.NONE else None
        if self.mapping and mode == Mode.MAPPING:
            item = self.mapping.current
            self.mapping.phase = phase
        self.directive = Directive(self.directive.revision + 1, mode, phase, item)
        self.health.begin(self.directive, self.now)
        return self.directive

    def _prepare(self):
        if self.mapping:
            phase = Phase.COMMIT if self.mapping.phase == Phase.COMMIT else Phase.PREPARE
            return self._issue(Mode.MAPPING, phase)
        mode = {MissionKind.MOW: Mode.WORKING, MissionKind.RETURN_HOME: Mode.RETURNING}[self.task.mission.kind]
        return self._issue(mode, Phase.PREPARE)

    def _finish(self):
        mission = self.task.mission
        self.history.append({"mission_id": mission.mission_id, "result": "completed"})
        self.task = None
        return self._issue(Mode.CHARGING if mission.kind == MissionKind.RETURN_HOME else Mode.IDLE)

    def handle(self, message, now):
        self._clock(now)
        if not isinstance(message, (Event, Status)):
            raise TypeError("brain accepts only Event or Status")
        timeout = self.tick(now)
        if isinstance(message, Status):
            return timeout or self._status(message)
        previous = self.health.previous_event(message)
        if previous is not None:
            self.last_result = previous
            return timeout
        try:
            if timeout and message.kind not in (EventKind.LOW_BATTERY, EventKind.BATTERY_OK):
                raise ValueError("status timeout; fault must be acknowledged by a subsequent RESET")
            self.health.observe_event(message)
            output = self._event(message)
            result = {"event_id": message.event_id, "accepted": True, "reason": "", "revision": self.directive.revision}
        except ValueError as error:
            output = None
            result = {"event_id": message.event_id, "accepted": False, "reason": str(error), "revision": self.directive.revision}
        self.last_result = result
        self.health.remember_event(message, result)
        return output or timeout

    def _event(self, event):
        kind, mode = event.kind, self.directive.mode
        if kind in (EventKind.START_MAPPING, EventKind.SELECT_REGION_START, EventKind.START_EDGE_FOLLOW,
                    EventKind.TAKE_OVER, EventKind.START_CHANNEL, EventKind.FINISH_CHANNEL,
                    EventKind.FINISH_MAPPING):
            return self._mapping_command(event)
        if kind == EventKind.START:
            if mode != Mode.IDLE or self.task or self.suspended:
                raise ValueError("START requires IDLE without a suspended task")
            if event.mission.mission_id in self.used_missions:
                raise ValueError("mission_id already used in this session")
            if self.low_battery and event.mission.kind != MissionKind.RETURN_HOME:
                raise ValueError("battery is low")
            self.used_missions.add(event.mission.mission_id)
            self.task = Task(event.mission)
            return self._prepare()
        if kind == EventKind.PAUSE:
            if mode not in (Mode.MAPPING, Mode.WORKING, Mode.RETURNING):
                raise ValueError("no active task to pause")
            if self.directive.phase == Phase.COMMIT:
                raise ValueError("map commit must finish before pausing")
            return self._issue(Mode.PAUSED, reason="user pause")
        if kind == EventKind.RESUME:
            if mode != Mode.PAUSED or not (self.task or self.mapping):
                raise ValueError("no paused task to resume")
            if self.low_battery and (self.mapping or self.task.mission.kind != MissionKind.RETURN_HOME):
                raise ValueError("battery is low")
            return self._prepare()
        if kind == EventKind.CANCEL:
            if mode == Mode.ERROR:
                raise ValueError("fault is latched; RESET first")
            if self.directive.phase == Phase.COMMIT:
                raise ValueError("map commit must finish before cancelling")
            for task in (self.task, self.suspended):
                if task:
                    self.history.append({"mission_id": task.mission.mission_id, "result": "cancelled"})
            if self.mapping:
                self.history.append({"mission_id": self.mapping.session_id, "result": "cancelled"})
                self.mapping = None
            self.task = self.suspended = None
            return self._issue(Mode.IDLE)
        if kind == EventKind.LOW_BATTERY:
            if mode in (Mode.IDLE, Mode.ERROR, Mode.CHARGING, Mode.RETURNING):
                return None
            if self.mapping:
                if self.directive.phase == Phase.COMMIT:
                    return None
                return self._issue(Mode.PAUSED, reason="low battery")
            if self.task.mission.kind == MissionKind.MOW:
                self.suspended = self.task
                m = self.task.mission
                self.task = Task(Mission(f"return:{event.event_id}", MissionKind.RETURN_HOME,
                                         m.map_id, (m.home_id,), m.home_id))
                return self._prepare()
            if self.directive.phase == Phase.COMMIT:
                return None  # Finish atomic map commit; battery latch prevents the next job.
            return self._issue(Mode.PAUSED, reason="low battery")
        if kind == EventKind.BATTERY_OK:
            if mode == Mode.CHARGING:
                self.task, self.suspended = self.suspended, None
                return self._issue(Mode.PAUSED if self.task else Mode.IDLE,
                                   reason="charged; explicit RESUME required" if self.task else "")
            return None
        if kind == EventKind.RESET:
            if mode != Mode.ERROR:
                raise ValueError("RESET requires ERROR")
            # Reset only unlatches the fault. Resume runs the readiness barrier again.
            return self._issue(Mode.PAUSED if self.task or self.mapping else Mode.IDLE)
        raise ValueError("unsupported event")


    def _mapping_manual(self, reason=""):
        self.mapping.current = WorkItem(MissionType.MANUAL_DRIVE, self.mapping.map_id, None, Control.MANUAL)
        return self._issue(Mode.MAPPING, Phase.PREPARE, reason)

    def _mapping_command(self, event):
        kind = event.kind
        if kind == EventKind.START_MAPPING:
            if self.directive.mode != Mode.IDLE or self.task or self.mapping or self.suspended:
                raise ValueError("START_MAPPING requires IDLE")
            if self.low_battery:
                raise ValueError("battery is low")
            session_id = event.event_id.removeprefix("command:")
            if session_id in self.used_missions:
                raise ValueError("session_id already used")
            self.used_missions.add(session_id)
            self.mapping = MappingSession(session_id, event.map_id,
                                          WorkItem(MissionType.MANUAL_DRIVE, event.map_id, None, Control.MANUAL))
            return self._prepare()
        if not self.mapping or self.directive.mode != Mode.MAPPING or self.directive.phase != Phase.EXECUTE:
            raise ValueError("mapping command requires an executing mapping session")
        current = self.mapping.current
        if kind in (EventKind.SELECT_REGION_START, EventKind.START_CHANNEL):
            if current.type != MissionType.MANUAL_DRIVE:
                raise ValueError("finish the current mapping object first")
            if event.target_id in self.mapping.regions + self.mapping.channels:
                raise ValueError("mapping object ID already exists")
            if kind == EventKind.START_CHANNEL:
                if not self.mapping.regions:
                    raise ValueError("a channel requires an existing region")
                self.mapping.current = WorkItem(MissionType.MAP_CHANNEL, self.mapping.map_id,
                                                target_id=event.target_id, control=Control.MANUAL)
            else:
                self.mapping.current = WorkItem(MissionType.MAP_REGION, self.mapping.map_id,
                                                target_id=event.target_id, control=Control.MANUAL)
            return self._issue(Mode.MAPPING, Phase.PREPARE)
        if kind in (EventKind.START_EDGE_FOLLOW, EventKind.TAKE_OVER):
            expected = Control.MANUAL if kind == EventKind.START_EDGE_FOLLOW else Control.AUTO
            if current.type != MissionType.MAP_REGION or current.control != expected:
                raise ValueError("edge control change requires the matching active region control")
            control = Control.AUTO if expected == Control.MANUAL else Control.MANUAL
            self.mapping.current = replace(current, control=control)
            return self._issue(Mode.MAPPING, Phase.PREPARE)
        if kind == EventKind.FINISH_CHANNEL:
            if current.type != MissionType.MAP_CHANNEL:
                raise ValueError("no channel is being recorded")
            return self._issue(Mode.MAPPING, Phase.COMMIT)
        if kind == EventKind.FINISH_MAPPING:
            if current.type != MissionType.MANUAL_DRIVE:
                raise ValueError("finish the current region or channel before saving the map")
            if not self.mapping.regions:
                raise ValueError("cannot save a map without a completed region")
            self.mapping.current = WorkItem(MissionType.SAVE_MAP, self.mapping.map_id, None, Control.NONE)
            return self._issue(Mode.MAPPING, Phase.COMMIT)
        raise ValueError("unsupported mapping command")

    def _mapping_feedback(self, status):
        current = self.mapping.current
        if (self.directive.phase == Phase.EXECUTE and current.type == MissionType.MAP_REGION
                and status.module in (Module.PERCEPTION, Module.MAP_MANAGER)
                and status.state in (State.RUNNING, State.SUCCEEDED)
                and status.signal == "REGION_CLOSED"):
            return self._issue(Mode.MAPPING, Phase.COMMIT)
        if (self.directive.phase != Phase.COMMIT or status.module != Module.MAP_MANAGER
                or status.state != State.SUCCEEDED):
            return None
        if current.type == MissionType.SAVE_MAP:
            self.history.append({"mission_id": self.mapping.session_id, "result": "completed",
                                 "map_id": self.mapping.map_id, "regions": list(self.mapping.regions),
                                 "channels": list(self.mapping.channels)})
            self.mapping = None
            return self._issue(Mode.IDLE)
        collection = self.mapping.regions if current.type == MissionType.MAP_REGION else self.mapping.channels
        collection.append(current.target_id)
        self.mapping.last_result = {"type": current.type.value, "target_id": current.target_id,
                                    "result": "completed"}
        if self.low_battery:
            self.mapping.current = WorkItem(MissionType.MANUAL_DRIVE, self.mapping.map_id, None, Control.MANUAL)
            self.mapping.phase = Phase.PREPARE
            return self._issue(Mode.PAUSED, reason="low battery")
        return self._mapping_manual()

    def _status(self, status):
        d = self.directive
        if not self.health.accept(status, self.now):
            return None
        if d.phase == Phase.NONE:
            return None
        if (self.mapping and d.phase == Phase.PREPARE
                and self.mapping.current.type == MissionType.MAP_CHANNEL
                and status.module == Module.MAP_MANAGER and status.state == State.REJECTED
                and status.reason == "CHANNEL_START_OUTSIDE_REGION"):
            self.mapping.last_result = {"type": "MAP_CHANNEL", "target_id": self.mapping.current.target_id,
                                        "result": "rejected", "reason": status.reason}
            return self._mapping_manual(status.reason)
        if status.state in (State.FAILED, State.BLOCKED, State.REJECTED):
            return self._issue(Mode.ERROR, reason=f"{status.module}: {status.reason or status.state}")
        if d.phase == Phase.PREPARE:
            if self.health.ready(self.now):
                return self._issue(d.mode, Phase.EXECUTE)
            return None
        if self.mapping:
            return self._mapping_feedback(status)
        owner = Module.PNC
        if status.module != owner or status.state != State.SUCCEEDED:
            return None
        self.task.cursor += 1
        if self.task.cursor == len(self.task.mission.targets):
            return self._finish()
        return self._prepare()

    def tick(self, now):
        """Clock input is supplied by the host, including when all modules are silent."""
        self._clock(now)
        expired = self.health.expired(now)
        if expired:
            return self._issue(Mode.ERROR, reason=f"{expired[0]}: status timeout")
        return None

    def view(self):
        def task_view(task):
            return None if task is None else {"mission": asdict(task.mission),
                                               "completed": list(task.mission.targets[:task.cursor]),
                                               "current": task.mission.targets[task.cursor]}
        return {"directive": self.directive.to_dict(), "task": task_view(self.task),
                "suspended": task_view(self.suspended), "reason": self.reason,
                "low_battery": self.low_battery, "history": deepcopy(self.history),
                "last_event": deepcopy(self.last_result), "public_status": self.status()}
