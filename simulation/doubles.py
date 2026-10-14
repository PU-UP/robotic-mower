"""Algorithm substitutes: scripted world poses, simple geometry, no real motion control."""
import math
from dataclasses import replace

from contracts import Control, Directive, MissionType, Module, Mode, Phase, State, Status
from simulation.world import BusinessMap, Entity, UNDOCK_DISTANCE
from simulation.observation import Observation
from simulation.planning import PlanningInput


DOCK_POSITION = (-3.5, 0.0)
DOCK_EXIT = (-2.0, 0.0)  # The fixture dock faces -x; reversing moves in +x.


def garden():
    return BusinessMap("garden", 1, "slam-garden", "map", (
        Entity("region-1", "region", ((0, 0), (4, 0), (4, 4), (0, 4))),
        Entity("region-2", "region", ((8, 0), (12, 0), (12, 4), (8, 4))),
        Entity("dock", "charging_station", (DOCK_POSITION,), exit_point=DOCK_EXIT, heading=math.pi),
        Entity("return-channel", "return_channel", (DOCK_EXIT, (0, 0)),
               end_region_id="region-1", station_id="dock"),
        Entity("channel-1", "channel", ((2, 2), (4, 2), (7, 2), (9, 2)), "region-1", "region-2"),
    ))


class RoboframeDouble:
    def __init__(self, business_map=None):
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
        self.return_trace = []
        self.route = None
        self.stage = "STOPPED"
        self.coverage = {}
        self.blade_requested = False
        self.blade_state = "UNKNOWN"
        self.charging = None
        self.previous_position = None
        self.previous_blade_state = "UNKNOWN"

    def configure(self, directive, now):
        if directive.revision <= self.directive.revision:
            return
        previous = self.directive
        if (previous.mission, previous.task_id) != (directive.mission, directive.task_id):
            self.route = None
        self.directive = directive
        self.started, self.progress = now, 0.0
        self.stage = "NAVIGATE"
        self.previous_position = None
        self.previous_blade_state = "UNKNOWN"
        self.blade_requested = False
        self.state, self.reason, self.signal = State.STOPPED, "", None
        self.control = "STOPPED"
        if directive.phase != Phase.NONE:
            self.state = State.READY
        item = directive.mission
        if directive.mode == Mode.IDLE:
            self.working_map, self.draft_id, self.trace = None, None, []
            self.return_trace = []
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
            if item.type != MissionType.UNDOCK or not observation or math.dist(
                    (observation.x, observation.y), DOCK_POSITION) > 0.05:
                self.state, self.reason = State.REJECTED, "MAPPING_MUST_START_AT_DOCK"
                return
            self.working_map = BusinessMap(item.map_id, 0, f"slam-{item.map_id}", "map", (
                Entity("dock", "charging_station", (DOCK_POSITION,), exit_point=DOCK_EXIT, heading=math.pi),))
        if (not observation or not observation.localized or not 0 <= now - observation.stamp <= 0.5
                or (observation.slam_map_id, observation.frame_id) !=
                   (self.working_map.slam_map_id, self.working_map.frame_id)):
            self.state, self.reason = State.BLOCKED, "LOCALIZATION_UNAVAILABLE"
            return
        if item.type == MissionType.MANUAL_DRIVE:
            self.state = State.READY
            return
        point = (observation.x, observation.y)
        if item.type == MissionType.UNDOCK:
            self.state = State.READY
            return
        if item.type == MissionType.MAP_RETURN_CHANNEL:
            if not self.return_trace:
                if math.dist(point, DOCK_EXIT) > 1e-6:
                    self.state, self.reason = State.REJECTED, "UNDOCK_INCOMPLETE"
                    return
                self.return_trace = [point]
            if d.phase == Phase.EXECUTE and self.return_trace[-1] != point:
                self.return_trace.append(point)
            self.trace = list(self.return_trace)
            self.state = State.READY if d.phase == Phase.PREPARE else State.RUNNING
            return
        if item.type == MissionType.SAVE_MAP:
            world = self.working_map.connect_channels()
            error = world.topology_error()
            if error:
                self.state, self.reason = State.REJECTED, error
                return
            self.business_map = self.working_map = world
            self.state = State.SUCCEEDED
            return
        if item.type == MissionType.MAP_REGION and not self.working_map.find("return-channel"):
            points = list(self.return_trace)
            if not points:
                self.state, self.reason = State.REJECTED, "RETURN_CHANNEL_REQUIRED"
                return
            if points[-1] != point:
                points.append(point)
            if len(points) < 2:
                self.state, self.reason = State.REJECTED, "RETURN_CHANNEL_TOO_SHORT"
                return
            # The same observation ends the return channel and starts the first region.
            self.working_map = replace(self.working_map, entities=self.working_map.entities + (
                Entity("return-channel", "return_channel", tuple(points),
                       end_region_id=item.target_id, station_id="dock"),))
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
            entity = Entity(item.target_id, "region", tuple(self.trace[:-1]))
        else:
            if len(self.trace) < 2:
                self.state, self.reason = State.FAILED, "CHANNEL_TOO_SHORT"
                return
            entity = Entity(item.target_id, "channel", tuple(self.trace), self.start_region_id)
        world = self.working_map
        self.working_map = BusinessMap(world.map_id, world.revision + 1, world.slam_map_id,
                                       world.frame_id, world.entities + (entity,)).connect_channels()
        self.state = State.SUCCEEDED

    def work_segments(self):
        item = self.directive.mission
        points = self.business_map.find(item.target_id).points
        # shortcut: boundary and two chords, not area coverage; replace for algorithm validation.
        return [("EDGE", a, b) for a, b in zip(points, points[1:] + points[:1])] + [
            ("COVER", points[0], points[len(points)//2]),
            ("COVER", points[1], points[(len(points)//2 + 1) % len(points)])]

    def remaining(self):
        item = self.directive.mission
        key = (self.directive.task_id, item.map_id, item.target_id)
        recorded = self.coverage.get(key, [])
        return [segment for segment in self.work_segments() if segment not in recorded]

    def motion_target(self, now, position):
        """Fixture motion demand; device facts are provided separately by the world."""
        if self.fault or self.state in (State.FAILED, State.BLOCKED, State.REJECTED):
            return position
        d = self.directive
        if d.phase != Phase.EXECUTE:
            return position
        if d.mission.type == MissionType.UNDOCK:
            distance = math.dist(position, DOCK_EXIT)
            fraction = 1.0 if distance <= 0.15 + 1e-9 else 0.15 / distance
            return tuple(a + (b-a)*fraction for a, b in zip(position, DOCK_EXIT))
        if self.stage in ("EDGE", "COVER") and self.blade_state == "RUNNING":
            remaining = self.remaining()
            if remaining:
                _, start, end = remaining[0]
                return end if position == start else start
        if self.stage == "NAVIGATE" and self.route:
            fraction = min(1.0, max(0.0, (now-self.started)/0.8))
            distance = sum(math.dist(a, b) for a, b in zip(self.route, self.route[1:])) * fraction
            for a, b in zip(self.route, self.route[1:]):
                length = math.dist(a, b)
                if distance <= length:
                    return tuple(x+(y-x)*distance/length for x, y in zip(a, b)) if length else b
                distance -= length
            return self.route[-1]
        return position

    def step(self, now, observation=None):
        d, item = self.directive, self.directive.mission
        previous = self.previous_position
        cutting = (self.stage in ("EDGE", "COVER") and self.blade_requested
                   and self.previous_blade_state == "RUNNING" and self.blade_state == "RUNNING")
        self.previous_blade_state = self.blade_state
        self.previous_position = (observation.x, observation.y) if observation else None
        self.signal, self.control, self.reason = None, "STOPPED", ""
        self.blade_requested = False
        if d.phase == Phase.NONE:
            self.state, self.stage = State.STOPPED, "STOPPED"
            return
        if self.fault:
            self.state, self.reason = State.FAILED, self.fault
            return
        if d.mode == Mode.MAPPING:
            self._mapping(now, observation)
            if self.state in (State.FAILED, State.BLOCKED, State.REJECTED) or d.phase != Phase.EXECUTE:
                return
            if item.type == MissionType.UNDOCK:
                self.control = "AUTO_REVERSE"
                self.progress = min(1.0, math.dist(self.previous_position, DOCK_POSITION) / UNDOCK_DISTANCE)
                self.state = State.SUCCEEDED if math.dist(self.previous_position, DOCK_EXIT) < 1e-6 else State.RUNNING
            else:
                self.control = "AUTO_EDGE" if item.type == MissionType.MAP_REGION and item.control == Control.AUTO else item.control.value
                self.state = State.RUNNING
            return
        world = self.business_map
        if world and world.topology_error():
            self.state, self.reason = State.REJECTED, world.topology_error()
            return
        inputs = PlanningInput(item, observation, world) if observation and world else None
        if inputs is None or not inputs.ready(now):
            self.state, self.reason = State.BLOCKED, "PLANNING_INPUT_INVALID"
            return
        target = world.find(item.target_id)
        expected_kind = "region" if item.type == MissionType.MOW_REGION else "charging_station"
        if target.kind != expected_kind or (expected_kind == "region" and len(target.points) < 3):
            self.state, self.reason = State.REJECTED, "TARGET_KIND_INVALID"
            return
        if d.phase == Phase.PREPARE:
            self.route = inputs.route(now)
            self.state = State.READY
            return
        if self.route is None:
            self.route = inputs.route(now)
        self.state = State.RUNNING
        if self.stage == "NAVIGATE":
            self.control = "AUTO_GOAL"
            if now - self.started < 0.8 or math.dist(self.previous_position, self.route[-1]) > 1e-6:
                return
            self.stage = "DOCK" if item.type == MissionType.RETURN_HOME else "EDGE"
        if item.type == MissionType.RETURN_HOME:
            self.control = "DOCK"
            # Device confirmation, not arrival at the stored station pose, completes return.
            if self.charging is True:
                self.state, self.progress = State.SUCCEEDED, 1.0
            return
        self.blade_requested = True
        if self.blade_state == "FAILED":
            self.blade_requested = False
            self.state, self.reason = State.FAILED, "BLADE_FAILED"
            return
        remaining = self.remaining()
        if remaining and cutting:
            segment = remaining[0]
            if previous == segment[1] and self.previous_position == segment[2]:
                key = (d.task_id, item.map_id, item.target_id)
                self.coverage.setdefault(key, []).append(segment)
                remaining = self.remaining()
        self.progress = 1 - len(remaining) / len(self.work_segments())
        if not remaining:
            self.blade_requested = False
            # Completion also waits for an actual stop acknowledgement.
            if self.blade_state == "STOPPED":
                self.state = State.SUCCEEDED
            return
        self.stage = remaining[0][0]
        self.control = "AUTO_" + self.stage if self.blade_state == "RUNNING" else "WAIT_BLADE"

    def status(self, now):
        self.sequence += 1
        progress = self.progress if self.directive.mode in (Mode.WORKING, Mode.RETURNING) and self.directive.phase == Phase.EXECUTE else None
        return Status(Module.ROBOFRAME, self.directive.revision, self.sequence, now, self.state,
                      self.reason, progress, self.signal)
