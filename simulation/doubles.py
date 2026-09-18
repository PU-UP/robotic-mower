"""Algorithm substitutes: scripted world poses, simple geometry, no real motion control."""
import math

from contracts import Control, Directive, MissionType, Module, Mode, Phase, State, Status
from map_manager import BusinessMap, Entity
from perception import Observation
from pnc import PlanningInput


def garden():
    return BusinessMap("garden", 1, "slam-garden", "map", (
        Entity("region-1", "region", ((0, 0), (4, 0), (4, 4), (0, 4))),
        Entity("region-2", "region", ((5, 0), (9, 0), (9, 4), (5, 4))),
        Entity("dock", "charging_station", ((0, 0),)),
    ))


class AlgorithmDouble:
    def __init__(self, module, business_map=None):
        self.module = module
        self.directive = Directive(0, Mode.IDLE, Phase.NONE, None)
        self.state, self.reason, self.signal = State.STOPPED, "", None
        self.sequence = 0
        self.started = self.progress = 0.0
        self.fault, self.silent = "", False
        self.control = "STOPPED"
        self.business_map = business_map
        self.working_map = None
        self.draft_id, self.start_region_id = None, None
        self.trace = []

    def configure(self, directive, now):
        if directive.revision <= self.directive.revision:
            return
        self.directive = directive
        self.started, self.progress = now, 0.0
        self.state, self.reason, self.signal = State.STOPPED, "", None
        self.control = "STOPPED"
        if directive.phase != Phase.NONE:
            self.state = State.READY
        if self.module != Module.MAP_MANAGER:
            return
        item = directive.mission
        if directive.mode == Mode.IDLE:
            self.working_map, self.draft_id, self.trace = None, None, []
        elif item and item.type == MissionType.MANUAL_DRIVE:
            self.draft_id, self.trace, self.start_region_id = None, [], None
        elif item and item.type in (MissionType.MAP_REGION, MissionType.MAP_CHANNEL):
            identity = (item.map_id, item.type, item.target_id)
            if identity != self.draft_id:
                self.draft_id, self.trace, self.start_region_id = identity, [], None
            # Same region, new revision/control: retain start and collected boundary.

    def observe(self, now, position=(0, 0)):
        item = self.directive.mission
        map_id = item.map_id if item else "garden"
        return Observation(now, f"slam-{map_id}", "map", *position, not bool(self.fault))

    def _mapping(self, now, observation):
        d, item = self.directive, self.directive.mission
        if self.working_map is None:
            if self.business_map and self.business_map.map_id == item.map_id:
                self.state, self.reason = State.REJECTED, "MAP_ALREADY_EXISTS"
                return
            self.working_map = BusinessMap(item.map_id, 0, f"slam-{item.map_id}", "map", ())
        if (not observation or not observation.localized or not 0 <= now - observation.stamp <= 0.5
                or (observation.slam_map_id, observation.frame_id) !=
                   (self.working_map.slam_map_id, self.working_map.frame_id)):
            self.state, self.reason = State.BLOCKED, "LOCALIZATION_UNAVAILABLE"
            return
        if item.type == MissionType.MANUAL_DRIVE:
            self.state = State.READY
            return
        if item.type == MissionType.SAVE_MAP:
            self.business_map = self.working_map
            self.state = State.SUCCEEDED
            return
        point = (observation.x, observation.y)
        if not self.trace:
            if item.type == MissionType.MAP_CHANNEL:
                self.start_region_id = self.working_map.region_at(*point)
                if self.start_region_id is None:
                    self.state, self.reason = State.REJECTED, "CHANNEL_START_OUTSIDE_REGION"
                    return
            self.trace = [point]  # Capture once; PREPARE/EXECUTE and takeover never reset it.
        if d.phase == Phase.PREPARE:
            self.state = State.READY
            return
        if d.phase == Phase.EXECUTE:
            if self.trace[-1] != point:
                self.trace.append(point)
            self.state = State.RUNNING
            # Mock closure requires departure and a nonzero polygon, not merely being at the start.
            if item.type == MissionType.MAP_REGION and len(self.trace) >= 4:
                area = abs(sum(ax * by - bx * ay for (ax, ay), (bx, by) in
                               zip(self.trace, self.trace[1:] + self.trace[:1]))) / 2
                if math.dist(point, self.trace[0]) <= 0.15 and area >= 0.25:
                    self.signal = "REGION_CLOSED"
            return
        if item.type == MissionType.MAP_CHANNEL and self.trace[-1] != point:
            self.trace.append(point)
        # Idempotent in-memory object commit, including retries after an uncertain ACK.
        if self.working_map.find(item.target_id):
            self.state = State.SUCCEEDED
            return
        if item.type == MissionType.MAP_REGION:
            if len(self.trace) < 4 or math.dist(self.trace[0], self.trace[-1]) > 0.15:
                self.state, self.reason = State.FAILED, "TRACE_NOT_CLOSED"
                return
            entity = Entity(item.region_id, "region", tuple(self.trace[:-1]))
        else:
            if len(self.trace) < 2:
                self.state, self.reason = State.FAILED, "CHANNEL_TOO_SHORT"
                return
            entity = Entity(item.channel_id, "channel", tuple(self.trace), self.start_region_id)
        world = self.working_map
        self.working_map = BusinessMap(world.map_id, world.revision + 1, world.slam_map_id,
                                       world.frame_id, world.entities + (entity,))
        self.state = State.SUCCEEDED

    def step(self, now, observation=None, business_map=None):
        d, item = self.directive, self.directive.mission
        self.signal, self.control = None, "STOPPED"
        if d.phase == Phase.NONE:
            self.state = State.STOPPED
            return
        if self.fault:
            self.state, self.reason = State.FAILED, self.fault
            return
        if self.module == Module.PERCEPTION:
            self.state = State.READY if d.phase == Phase.PREPARE else State.RUNNING
            return
        if self.module == Module.MAP_MANAGER:
            if d.mode == Mode.MAPPING:
                self._mapping(now, observation)
            elif (self.business_map is None or item.map_id != self.business_map.map_id
                    or self.business_map.find(item.target_id) is None):
                self.state, self.reason = State.REJECTED, "MAP_OR_TARGET_UNAVAILABLE"
            else:
                self.state = State.READY
            return
        if d.mode == Mode.MAPPING:
            if d.phase == Phase.PREPARE:
                self.state = State.READY
            elif d.phase == Phase.COMMIT:
                self.state = State.STOPPED
            elif observation and observation.localized and 0 <= now - observation.stamp <= 0.5:
                self.control = item.control.value if item.type == MissionType.MAP_REGION else "MANUAL"
                self.state = State.RUNNING
            else:
                self.state, self.reason = State.BLOCKED, "LOCALIZATION_UNAVAILABLE"
            return
        ready = observation is not None and business_map is not None and PlanningInput(
            item, observation, business_map).ready(now)
        if not ready:
            self.state, self.reason = State.BLOCKED, "PLANNING_INPUT_INVALID"
            return
        if d.phase == Phase.PREPARE:
            self.state = State.READY
            return
        self.control = "AUTO_GOAL"
        self.progress = min(1.0, max(0.0, (now - self.started) / 0.8))
        self.state = State.SUCCEEDED if self.progress >= 1 else State.RUNNING

    def status(self, now):
        self.sequence += 1
        progress = self.progress if self.module == Module.PNC and self.directive.mode in (
            Mode.WORKING, Mode.RETURNING) and self.directive.phase == Phase.EXECUTE else None
        return Status(self.module, self.directive.revision, self.sequence, now, self.state,
                      self.reason, progress, self.signal)
