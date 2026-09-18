"""Brain's JSON control protocol and small internal business values."""
from dataclasses import dataclass
from enum import StrEnum
import math


class Module(StrEnum):
    PERCEPTION = "perception"
    MAP_MANAGER = "map_manager"
    PNC = "pnc"


class Mode(StrEnum):
    IDLE = "IDLE"
    MAPPING = "MAPPING"
    WORKING = "WORKING"
    RETURNING = "RETURNING"
    PAUSED = "PAUSED"
    CHARGING = "CHARGING"
    ERROR = "ERROR"


class Phase(StrEnum):
    NONE = "NONE"
    PREPARE = "PREPARE"
    EXECUTE = "EXECUTE"
    COMMIT = "COMMIT"


class Control(StrEnum):
    MANUAL = "MANUAL"
    AUTO_EDGE = "AUTO_EDGE"


class MissionType(StrEnum):
    MANUAL_DRIVE = "MANUAL_DRIVE"
    MAP_REGION = "MAP_REGION"
    MAP_CHANNEL = "MAP_CHANNEL"
    SAVE_MAP = "SAVE_MAP"
    COVER_REGION = "COVER_REGION"
    RETURN_HOME = "RETURN_HOME"


class MissionKind(StrEnum):
    """Whole business tasks, retained only inside brain."""
    MOW = "MOW"
    RETURN_HOME = "RETURN_HOME"


class EventKind(StrEnum):
    """Internal reducer events; public commands are parsed below."""
    START = "START"
    START_MAPPING = "START_MAPPING"
    SELECT_REGION_START = "SELECT_REGION_START"
    START_EDGE_FOLLOW = "START_EDGE_FOLLOW"
    TAKE_OVER = "TAKE_OVER"
    START_CHANNEL = "START_CHANNEL"
    FINISH_CHANNEL = "FINISH_CHANNEL"
    FINISH_MAPPING = "FINISH_MAPPING"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"
    LOW_BATTERY = "LOW_BATTERY"
    BATTERY_OK = "BATTERY_OK"
    RESET = "RESET"


class State(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    STOPPED = "STOPPED"


def identifier(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identifier must be a non-empty string")


def object_fields(data, required, optional=()):
    """Strict fields catch typos instead of silently changing a robot command."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    missing, extra = set(required) - data.keys(), data.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"missing fields: {sorted(missing)}; unknown fields: {sorted(extra)}")


def nonnegative_number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("expected a finite nonnegative number")


@dataclass(frozen=True)
class Mission:
    """Internal complete business task; never serialized as a directive mission."""
    mission_id: str
    kind: MissionKind
    map_id: str
    targets: tuple[str, ...]
    home_id: str = "dock"

    def __post_init__(self):
        for value in (self.mission_id, self.map_id, self.home_id):
            identifier(value)
        if not isinstance(self.kind, MissionKind):
            raise ValueError("invalid task kind")
        if not isinstance(self.targets, tuple) or not self.targets:
            raise ValueError("targets must be a non-empty immutable tuple")
        for target in self.targets:
            identifier(target)
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("duplicate target")
        if self.kind != MissionKind.MOW and len(self.targets) != 1:
            raise ValueError("mapping and return-home require one target")


@dataclass(frozen=True)
class WorkItem:
    """Current algorithm goal; recording identity survives control handover."""
    type: MissionType
    map_id: str
    region_id: str | None = None
    station_id: str | None = None
    channel_id: str | None = None
    control: Control | None = None

    def __post_init__(self):
        identifier(self.map_id)
        if not isinstance(self.type, MissionType):
            raise ValueError("invalid mission type")
        required = {
            MissionType.COVER_REGION: ("region_id",),
            MissionType.RETURN_HOME: ("station_id",),
            MissionType.MAP_REGION: ("region_id", "control"),
            MissionType.MAP_CHANNEL: ("channel_id",),
            MissionType.MANUAL_DRIVE: (),
            MissionType.SAVE_MAP: (),
        }[self.type]
        for field in ("region_id", "station_id", "channel_id", "control"):
            value = getattr(self, field)
            if field in required:
                if field == "control":
                    if not isinstance(value, Control):
                        raise ValueError("MAP_REGION requires MANUAL or AUTO_EDGE control")
                else:
                    identifier(value)
            elif value is not None:
                raise ValueError(f"{self.type} does not accept {field}")

    @property
    def target_id(self):
        return self.region_id or self.station_id or self.channel_id

    def to_dict(self):
        data = {"type": self.type.value, "map_id": self.map_id}
        for field in ("region_id", "station_id", "channel_id", "control"):
            value = getattr(self, field)
            if value is not None:
                data[field] = value.value if isinstance(value, Control) else value
        return data

    @classmethod
    def from_dict(cls, data):
        object_fields(data, ("type", "map_id"), ("region_id", "station_id", "channel_id", "control"))
        return cls(MissionType(data["type"]), data["map_id"], data.get("region_id"),
                   data.get("station_id"), data.get("channel_id"),
                   Control(data["control"]) if "control" in data else None)


@dataclass(frozen=True)
class Directive:
    revision: int
    mode: Mode
    phase: Phase
    mission: WorkItem | None

    def __post_init__(self):
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("invalid directive revision")
        if not isinstance(self.mode, Mode) or not isinstance(self.phase, Phase):
            raise ValueError("invalid mode or phase")
        if self.phase == Phase.NONE:
            if self.mission is not None or self.mode in (Mode.MAPPING, Mode.WORKING, Mode.RETURNING):
                raise ValueError("NONE requires an inactive mode and null mission")
        else:
            if not isinstance(self.mission, WorkItem):
                raise ValueError("active phase requires a mission")
            mode = {MissionType.COVER_REGION: Mode.WORKING,
                    MissionType.RETURN_HOME: Mode.RETURNING}.get(self.mission.type, Mode.MAPPING)
            invalid_commit = self.phase == Phase.COMMIT and self.mission.type not in (
                MissionType.MAP_REGION, MissionType.MAP_CHANNEL, MissionType.SAVE_MAP)
            invalid_save = self.mission.type == MissionType.SAVE_MAP and self.phase != Phase.COMMIT
            if self.mode != mode or invalid_commit or invalid_save:
                raise ValueError("mode/phase does not match mission")

    def to_dict(self):
        return {"revision": self.revision, "mode": self.mode.value, "phase": self.phase.value,
                "mission": self.mission.to_dict() if self.mission else None}

    @classmethod
    def from_dict(cls, data):
        object_fields(data, ("revision", "mode", "phase", "mission"))
        return cls(data["revision"], Mode(data["mode"]), Phase(data["phase"]),
                   WorkItem.from_dict(data["mission"]) if data["mission"] is not None else None)


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: EventKind
    mission: Mission | None = None
    map_id: str | None = None
    target_id: str | None = None

    def __post_init__(self):
        identifier(self.event_id)
        if not isinstance(self.kind, EventKind):
            raise ValueError("invalid event kind")
        if (self.kind == EventKind.START and not isinstance(self.mission, Mission)
                or self.kind != EventKind.START and self.mission is not None):
            raise ValueError("only internal START requires a task")
        if self.kind == EventKind.START_MAPPING:
            identifier(self.map_id)
        elif self.map_id is not None:
            raise ValueError("only START_MAPPING accepts map_id")
        if self.kind in (EventKind.SELECT_REGION_START, EventKind.START_CHANNEL):
            identifier(self.target_id)
        elif self.target_id is not None:
            raise ValueError("unexpected target_id")


@dataclass(frozen=True)
class Status:
    module: Module
    revision: int
    sequence: int
    stamp: float
    state: State
    reason: str = ""
    progress: float | None = None
    signal: str | None = None

    def __post_init__(self):
        if not isinstance(self.module, Module) or not isinstance(self.state, State):
            raise ValueError("invalid status source or state")
        if any(type(x) is not int or x < 0 for x in (self.revision, self.sequence)):
            raise ValueError("revision and sequence must be nonnegative integers")
        nonnegative_number(self.stamp)
        if self.signal not in (None, "REGION_CLOSED"):
            raise ValueError("unsupported status signal")
        if not isinstance(self.reason, str):
            raise ValueError("reason must be a string or null on the wire")
        if self.progress is not None:
            nonnegative_number(self.progress)
            if self.progress > 1:
                raise ValueError("progress must be between 0 and 1")

    def to_dict(self):
        data = {"module": self.module.value, "revision": self.revision, "sequence": self.sequence,
                "stamp": self.stamp, "state": self.state.value, "reason": self.reason or None}
        if self.progress is not None:
            data["progress"] = self.progress
        if self.signal is not None:
            data["signal"] = self.signal
        return data

    @classmethod
    def from_dict(cls, data):
        object_fields(data, ("module", "revision", "sequence", "stamp", "state"), ("reason", "progress", "signal"))
        reason = data.get("reason")
        return cls(Module(data["module"]), data["revision"], data["sequence"], data["stamp"],
                   State(data["state"]), "" if reason is None else reason, data.get("progress"), data.get("signal"))


def command_event(data):
    """Upper-layer JSON intent -> internal task/event; no module-level mode setting."""
    object_fields(data, ("command_id", "type"), ("params",))
    command_id, kind, params = data["command_id"], data["type"], data.get("params", {})
    identifier(command_id)
    identifier(kind)
    task = None
    if kind == "START_MOWING":
        object_fields(params, ("map_id", "region_ids"), ("home_id",))
        if not isinstance(params["region_ids"], list):
            raise ValueError("region_ids must be an array")
        task = Mission(command_id, MissionKind.MOW, params["map_id"], tuple(params["region_ids"]),
                       params.get("home_id", "dock"))
    elif kind == "START_MAPPING":
        object_fields(params, ("map_id",))
        return Event(f"command:{command_id}", EventKind.START_MAPPING, map_id=params["map_id"])
    elif kind in ("SELECT_REGION_START", "START_CHANNEL"):
        field = "region_id" if kind == "SELECT_REGION_START" else "channel_id"
        object_fields(params, (field,))
        return Event(f"command:{command_id}", EventKind(kind), target_id=params[field])
    elif kind == "RETURN_HOME":
        object_fields(params, ("map_id", "station_id"))
        task = Mission(command_id, MissionKind.RETURN_HOME, params["map_id"], (params["station_id"],))
    else:
        object_fields(params, ())
    controls = {"START_EDGE_FOLLOW": EventKind.START_EDGE_FOLLOW, "TAKE_OVER": EventKind.TAKE_OVER,
                "FINISH_CHANNEL": EventKind.FINISH_CHANNEL, "FINISH_MAPPING": EventKind.FINISH_MAPPING, "PAUSE": EventKind.PAUSE,
                "RESUME": EventKind.RESUME, "CANCEL": EventKind.CANCEL, "RESET_ERROR": EventKind.RESET}
    if not task and kind not in controls:
        raise ValueError(f"unsupported command type: {kind}")
    return Event(f"command:{command_id}", EventKind.START if task else controls[kind], task)


def system_event(data):
    object_fields(data, ("event_id", "type"))
    identifier(data["event_id"])
    if data["type"] not in ("LOW_BATTERY", "BATTERY_OK"):
        raise ValueError("unsupported external event type")
    return Event(f"event:{data['event_id']}", EventKind(data["type"]))
