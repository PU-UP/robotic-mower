"""Business execution state, independent of the wire mode and control revision."""
from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import StrEnum

from contracts import Control, EventKind, Mission, MissionKind, MissionType, Phase, State, WorkItem


class BusinessMode(StrEnum):
    IDLE = "IDLE"
    MAPPING = "MAPPING"
    WORKING = "WORKING"
    RETURN_TO_CHARGE = "RETURN_TO_CHARGE"
    CHARGING = "CHARGING"


class Lifecycle(StrEnum):
    PREPARE = "PREPARE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class MissionExecution:
    task_id: str
    kind: str
    action: WorkItem
    lifecycle: Lifecycle = Lifecycle.PREPARE
    action_phase: Phase = Phase.PREPARE
    attempt: int = 1
    retry_pending: bool = False

    @property
    def stage(self):
        if self.action.type == MissionType.SAVE_MAP:
            return "SAVE_MAP"
        if self.action_phase == Phase.COMMIT:
            return "COMMIT_OBJECT"
        return {MissionType.UNDOCK: "UNDOCK", MissionType.MAP_RETURN_CHANNEL: "RECORD_RETURN_CHANNEL",
                MissionType.MANUAL_DRIVE: "WAIT_START", MissionType.MAP_REGION: "BUILD_BOUNDARY",
                MissionType.MAP_CHANNEL: "BUILD_CHANNEL", MissionType.MOW_REGION: "MOW_REGION",
                MissionType.RETURN_HOME: "RETURN_AND_CHARGE"}[self.action.type]

    def set_action(self, action, phase=Phase.PREPARE):
        if self.lifecycle not in (Lifecycle.PREPARE, Lifecycle.RUNNING):
            raise ValueError("action change requires an active Mission")
        self.action, self.action_phase = action, phase

    def activate(self):
        if self.lifecycle not in (Lifecycle.PREPARE, Lifecycle.RUNNING):
            raise ValueError("activation requires an active Mission")
        self.lifecycle, self.action_phase = Lifecycle.RUNNING, Phase.EXECUTE

    def pause(self):
        if self.lifecycle not in (Lifecycle.PREPARE, Lifecycle.RUNNING, Lifecycle.PAUSED):
            raise ValueError("cannot pause a terminal Mission")
        self.lifecycle = Lifecycle.PAUSED

    def resume(self):
        retry = self.lifecycle == Lifecycle.FAILED and self.retry_pending
        if self.lifecycle != Lifecycle.PAUSED and not retry:
            raise ValueError("no paused Mission or acknowledged failure to resume")
        phase = Phase.COMMIT if self.action_phase == Phase.COMMIT else Phase.PREPARE
        # A failed attempt remains terminal; a resumed attempt is a separate value.
        return replace(self, lifecycle=Lifecycle.RUNNING if phase == Phase.COMMIT else Lifecycle.PREPARE,
                       action_phase=phase, attempt=self.attempt + int(retry), retry_pending=False)

    def finish(self, successful):
        if self.lifecycle not in (Lifecycle.PREPARE, Lifecycle.RUNNING, Lifecycle.PAUSED):
            raise ValueError("Mission is already terminal")
        if successful and self.lifecycle != Lifecycle.RUNNING:
            raise ValueError("only a running Mission can succeed")
        self.lifecycle = Lifecycle.SUCCESS if successful else Lifecycle.FAILED

    def view(self):
        return {"task_id": self.task_id, "type": self.kind, "target_id": self.action.target_id,
                "attempt": self.attempt, "lifecycle": self.lifecycle.value, "stage": self.stage,
                "action_phase": self.action_phase.value, "action": self.action.to_dict(),
                "retry_pending": self.retry_pending}


@dataclass
class Task:
    mission: Mission
    cursor: int = 0
    execution: MissionExecution = field(init=False)

    def __post_init__(self):
        self.start_target()

    def start_target(self):
        m = self.mission
        kind = MissionType.MOW_REGION if m.kind == MissionKind.MOW else MissionType.RETURN_HOME
        action = WorkItem(kind, m.map_id, m.targets[self.cursor], Control.AUTO)
        self.execution = MissionExecution(self.mission.mission_id, action.type.value, action)


@dataclass
class MappingSession:
    session_id: str
    map_id: str
    regions: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    last_result: dict | None = None
    execution: MissionExecution = field(init=False)

    def __post_init__(self):
        self.execution = MissionExecution(self.session_id, "MAPPING",
            WorkItem(MissionType.UNDOCK, self.map_id, "dock", Control.AUTO))

    @property
    def current(self):
        return self.execution.action

    @property
    def phase(self):
        return self.execution.action_phase

    def manual_action(self):
        return WorkItem(MissionType.MANUAL_DRIVE, self.map_id, None, Control.MANUAL)

    def view(self):
        return {"session_id": self.session_id, "map_id": self.map_id,
                "regions": list(self.regions), "channels": list(self.channels),
                "current": self.current.to_dict(), "last_result": deepcopy(self.last_result)}

    def command(self, event):
        if self.execution.lifecycle != Lifecycle.RUNNING or self.phase != Phase.EXECUTE:
            raise ValueError("mapping command requires an executing mapping session")
        kind, current = event.kind, self.current
        if kind in (EventKind.SELECT_REGION_START, EventKind.START_CHANNEL):
            first_start = (kind == EventKind.SELECT_REGION_START
                           and current.type == MissionType.MAP_RETURN_CHANNEL and not self.regions)
            if current.type != MissionType.MANUAL_DRIVE and not first_start:
                raise ValueError("finish the current mapping object first")
            if event.target_id in self.regions + self.channels + ["dock", "return-channel"]:
                raise ValueError("mapping object ID already exists")
            if kind == EventKind.START_CHANNEL and not self.regions:
                raise ValueError("a channel requires an existing region")
            action_type = MissionType.MAP_CHANNEL if kind == EventKind.START_CHANNEL else MissionType.MAP_REGION
            self.execution.set_action(WorkItem(action_type, self.map_id, event.target_id, Control.MANUAL))
        elif kind in (EventKind.START_EDGE_FOLLOW, EventKind.TAKE_OVER):
            expected = Control.MANUAL if kind == EventKind.START_EDGE_FOLLOW else Control.AUTO
            if current.type != MissionType.MAP_REGION or current.control != expected:
                raise ValueError("edge control change requires the matching active region control")
            self.execution.set_action(replace(current, control=Control.AUTO if expected == Control.MANUAL else Control.MANUAL))
        elif kind == EventKind.FINISH_CHANNEL:
            if current.type != MissionType.MAP_CHANNEL:
                raise ValueError("no channel is being recorded")
            self.execution.set_action(current, Phase.COMMIT)
        elif kind == EventKind.FINISH_MAPPING:
            if current.type != MissionType.MANUAL_DRIVE:
                raise ValueError("finish the current region or channel before saving the map")
            if not self.regions:
                raise ValueError("cannot save a map without a completed region")
            self.execution.set_action(WorkItem(MissionType.SAVE_MAP, self.map_id, None, Control.NONE), Phase.COMMIT)
        else:
            raise ValueError("unsupported mapping command")

    def recover_rejection(self, status):
        if status.state != State.REJECTED:
            return False
        channel_start = (self.phase == Phase.PREPARE and self.current.type == MissionType.MAP_CHANNEL
                         and status.reason == "CHANNEL_START_OUTSIDE_REGION")
        topology = (self.phase == Phase.COMMIT and self.current.type == MissionType.SAVE_MAP
                    and status.reason in ("CHANNEL_NOT_CONNECTED", "REGION_NOT_REACHABLE",
                                          "RETURN_CHANNEL_REQUIRED", "RETURN_CHANNEL_NOT_CONNECTED"))
        if not channel_start and not topology:
            return False
        self.last_result = {"type": self.current.type.value, "target_id": self.current.target_id,
                            "result": "rejected", "reason": status.reason}
        self.execution.set_action(self.manual_action())
        return True

    def feedback(self, status):
        current = self.current
        if (current.type == MissionType.UNDOCK and self.phase == Phase.EXECUTE
                and status.state == State.SUCCEEDED):
            self.execution.set_action(WorkItem(MissionType.MAP_RETURN_CHANNEL, self.map_id,
                                              "return-channel", Control.MANUAL))
            return True
        if (self.phase == Phase.EXECUTE and current.type == MissionType.MAP_REGION
                and status.state in (State.RUNNING, State.SUCCEEDED) and status.signal == "REGION_CLOSED"):
            self.execution.set_action(current, Phase.COMMIT)
            return True
        if self.phase != Phase.COMMIT or status.state != State.SUCCEEDED:
            return False
        if current.type == MissionType.SAVE_MAP:
            self.execution.finish(True)
        else:
            collection = self.regions if current.type == MissionType.MAP_REGION else self.channels
            collection.append(current.target_id)
            self.last_result = {"type": current.type.value, "target_id": current.target_id, "result": "completed"}
            self.execution.set_action(self.manual_action())
        return True
