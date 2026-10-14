"""Current-action evidence and external facts; business policy stays in Brain."""
from copy import deepcopy
import math
from types import MappingProxyType

from contracts import EventKind, Module, Phase, State


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

        # roboframe owns component readiness; Brain only observes the requested action.
        status = self._statuses.get(Module.ROBOFRAME)
        requested = d.phase != Phase.NONE
        available = bool(requested and status and not causes
                         and status.state in (State.READY, State.RUNNING, State.SUCCEEDED))
        capabilities = {"current_action": {
            "state": "AVAILABLE" if available else "UNAVAILABLE",
            "reason": None if available else ("INSUFFICIENT_EVIDENCE" if requested else "NOT_REQUESTED"),
            "causes": deepcopy(causes) if requested else [],
        }}
        return {"revision": d.revision, "low_battery": self.low_battery,
                "capabilities": capabilities, "causes": causes,
                "modules": {module.value: {"status": status.to_dict(), "received_at": received,
                    "fresh": 0 <= now - status.stamp <= self.status_timeout,
                    "current": status.revision == d.revision}
                    for module, (status, received) in self._latest.items()}}
