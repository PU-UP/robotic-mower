"""Current-action evidence and external facts; business policy stays in Brain."""
from copy import deepcopy
import math
from types import MappingProxyType

from contracts import Control, EventKind, MissionType, Module, Phase, State


class HealthEventManager:
    def __init__(self, status_timeout=1.0):
        if not math.isfinite(status_timeout) or status_timeout <= 0:
            raise ValueError("status_timeout must be positive and finite")
        self.status_timeout = status_timeout
        self.directive = None
        self.issued_at = 0.0
        self._statuses = {}
        self._latest = {}
        self._events = {}
        self.low_battery = False

    @property
    def statuses(self):
        return MappingProxyType(self._statuses)

    def begin(self, directive, now):
        self.directive, self.issued_at = directive, now
        self._statuses.clear()

    def accept(self, status, now):
        previous = self._statuses.get(status.module)
        if (status.revision != self.directive.revision or status.stamp < self.issued_at
                or not 0 <= now - status.stamp <= self.status_timeout
                or (previous and (status.sequence <= previous.sequence or status.stamp < previous.stamp))):
            return False
        self._statuses[status.module] = status
        self._latest[status.module] = (status, now)
        return True

    def expired(self, now):
        if self.directive.phase == Phase.NONE:
            return []
        return [module for module in Module if now - (
            self._statuses[module].stamp if module in self._statuses else self.issued_at
        ) > self.status_timeout]

    def ready(self, now):
        return not self.expired(now) and all(
            module in self._statuses and self._statuses[module].state == State.READY
            for module in Module)

    def previous_event(self, event):
        previous = self._events.get(event.event_id)
        if previous is None:
            return None
        if previous[0] == event:
            return deepcopy(previous[1])
        return {"event_id": event.event_id, "accepted": False,
                "reason": "event_id reused", "revision": self.directive.revision}

    def observe_event(self, event):
        if event.kind == EventKind.LOW_BATTERY:
            self.low_battery = True
        elif event.kind == EventKind.BATTERY_OK:
            self.low_battery = False

    def remember_event(self, event, result):
        self._events[event.event_id] = (event, deepcopy(result))

    def snapshot(self, now):
        """Capabilities apply only to the current action, never to hypothetical work."""
        d = self.directive
        causes = []
        for module in Module:
            status = self._statuses.get(module)
            reason = None
            if status is None:
                reason = "STATUS_TIMEOUT" if module in self.expired(now) else "NO_CURRENT_STATUS"
            elif now - status.stamp > self.status_timeout:
                reason = "STATUS_TIMEOUT"
            elif status.state in (State.FAILED, State.BLOCKED, State.REJECTED):
                reason = status.reason or status.state.value
            if reason:
                causes.append({"module": module.value, "reason": reason,
                               "revision": d.revision,
                               "stamp": status.stamp if status else None})

        requested = set()
        if d.mission:
            if d.phase == Phase.COMMIT:
                requested.add("map_commit")
            else:
                requested.add("manual_drive" if d.mission.control == Control.MANUAL else "navigation")
                if d.mission.type in (MissionType.MAP_REGION, MissionType.MAP_CHANNEL):
                    requested.add("mapping")
        dependencies = {
            "navigation": tuple(Module), "manual_drive": tuple(Module),
            "mapping": (Module.PERCEPTION, Module.MAP_MANAGER),
            "map_commit": (Module.MAP_MANAGER,),
        }
        capabilities = {}
        for name, modules in dependencies.items():
            available = name in requested and all(
                module in self._statuses
                and 0 <= now - self._statuses[module].stamp <= self.status_timeout
                and self._statuses[module].state in (State.READY, State.RUNNING, State.SUCCEEDED)
                for module in modules)
            capabilities[name] = {
                "state": "AVAILABLE" if available else "UNAVAILABLE",
                "reason": None if available else ("INSUFFICIENT_EVIDENCE" if name in requested else "NOT_REQUESTED"),
                "causes": [dict(c) for c in causes if c["module"] in modules] if name in requested else [],
            }
        return {"revision": d.revision, "low_battery": self.low_battery,
                "capabilities": capabilities, "causes": causes,
                "modules": {module.value: {"status": status.to_dict(), "received_at": received,
                    "fresh": 0 <= now - status.stamp <= self.status_timeout,
                    "current": status.revision == d.revision}
                    for module, (status, received) in self._latest.items()}}
