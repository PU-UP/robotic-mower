"""Business state machine. Inputs: Event / Status. Output: mode + current mission."""
from dataclasses import asdict
from copy import deepcopy
import math

from brain.health import HealthEventManager
from brain.mission import BusinessMode, Lifecycle, MappingSession, Task

from contracts import Directive, Event, EventKind, Mission, MissionKind, Module, Mode, Phase, State, Status, MissionType, command_event, system_event, identifier


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
        self.business_mode = BusinessMode.IDLE
        self.fault_latched = False
        self.mission_results = []

    @property
    def execution(self):
        owner = self.mapping or self.task
        return owner.execution if owner else None

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
        """Upper-layer business observation; spatial work records remain in roboframe."""
        def task_status(task):
            if task is None:
                return None
            return {"task_id": task.mission.mission_id, "type": task.mission.kind.value,
                    "completed_targets": list(task.mission.targets[:task.cursor]),
                    "total_targets": len(task.mission.targets),
                    "current_target": task.mission.targets[task.cursor]}
        last = deepcopy(self.history[-1]) if self.history else None
        return {"revision": self.directive.revision, "mode": self.directive.mode.value,
                "business_mode": self.business_mode.value,
                "mission_state": self.execution.view() if self.execution else None,
                "suspended_mission": self.suspended.execution.view() if self.suspended else None,
                "last_mission_result": deepcopy(self.mission_results[-1]) if self.mission_results else None,
                "fault_latched": self.fault_latched,
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

    def _publish(self, reason=""):
        """One-way projection: business state is authoritative, wire state is output."""
        self.reason = reason
        execution = self.execution
        mode = {BusinessMode.RETURN_TO_CHARGE: Mode.RETURNING}.get(self.business_mode)
        if mode is None:
            mode = Mode(self.business_mode.value)
        phase, item = Phase.NONE, None
        if self.fault_latched:
            mode = Mode.ERROR
        elif execution and (execution.lifecycle == Lifecycle.PAUSED or execution.retry_pending):
            mode = Mode.PAUSED
        elif execution and execution.lifecycle == Lifecycle.FAILED:
            mode = Mode.ERROR
        elif execution:
            phase, item = execution.action_phase, execution.action
        self.directive = Directive(self.directive.revision + 1, mode, phase, item, execution.task_id if item else None)
        self.health.begin(self.directive, self.now)
        return self.directive

    def _record_execution(self, result, execution=None, reason=""):
        execution = execution or self.execution
        if execution:
            self.mission_results.append({**execution.view(), "result": result, "reason": reason or None})

    def _fail(self, reason):
        self.fault_latched = True
        if self.execution and self.execution.lifecycle not in (Lifecycle.FAILED, Lifecycle.SUCCESS):
            self.execution.finish(False)
            self._record_execution("failed", reason=reason)
        return self._publish(reason)

    def _finish(self):
        mission = self.task.mission
        self.history.append({"mission_id": mission.mission_id, "result": "completed"})
        self.task = None
        self.business_mode = BusinessMode.CHARGING if mission.kind == MissionKind.RETURN_HOME else BusinessMode.IDLE
        return self._publish()

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
        kind, mode, execution = event.kind, self.business_mode, self.execution
        if kind == EventKind.RESET:
            if not self.fault_latched:
                raise ValueError("RESET requires a latched fault")
            self.fault_latched = False
            if execution and execution.lifecycle == Lifecycle.FAILED:
                execution.retry_pending = True
            return self._publish()
        if kind == EventKind.LOW_BATTERY:
            if self.fault_latched or mode in (BusinessMode.IDLE, BusinessMode.CHARGING, BusinessMode.RETURN_TO_CHARGE):
                return None
            if self.mapping:
                if execution.action_phase == Phase.COMMIT:
                    return None
                if execution.lifecycle != Lifecycle.FAILED:
                    execution.pause()
                return self._publish("low battery")
            if execution.lifecycle != Lifecycle.FAILED:
                execution.pause()
            self.suspended = self.task
            m = self.task.mission
            base_id = return_id = f"return:{event.event_id}"
            suffix = 0
            while return_id in self.used_missions:
                suffix += 1
                return_id = f"{base_id}:{suffix}"
            self.used_missions.add(return_id)
            self.task = Task(Mission(return_id, MissionKind.RETURN_HOME,
                                     m.map_id, (m.home_id,), m.home_id))
            self.business_mode = BusinessMode.RETURN_TO_CHARGE
            return self._publish()
        if kind == EventKind.BATTERY_OK:
            if mode == BusinessMode.CHARGING and not self.fault_latched:
                self.task, self.suspended = self.suspended, None
                self.business_mode = BusinessMode.WORKING if self.task else BusinessMode.IDLE
                return self._publish("charged; explicit RESUME required" if self.task else "")
            return None
        if self.fault_latched:
            raise ValueError("fault is latched; RESET first")
        if kind in (EventKind.START, EventKind.START_MAPPING):
            if mode != BusinessMode.IDLE or self.task or self.mapping or self.suspended:
                raise ValueError("START requires IDLE without a suspended task")
            returning = kind == EventKind.START and event.mission.kind == MissionKind.RETURN_HOME
            if self.low_battery and not returning:
                raise ValueError("battery is low")
            task_id = event.mission.mission_id if kind == EventKind.START else event.event_id.removeprefix("command:")
            if task_id in self.used_missions:
                raise ValueError("task ID already used in this session")
            self.used_missions.add(task_id)
            if kind == EventKind.START_MAPPING:
                self.mapping = MappingSession(task_id, event.map_id)
                self.business_mode = BusinessMode.MAPPING
            else:
                self.task = Task(event.mission)
                self.business_mode = BusinessMode.RETURN_TO_CHARGE if returning else BusinessMode.WORKING
            return self._publish()
        if kind == EventKind.PAUSE:
            if not execution or execution.lifecycle not in (Lifecycle.PREPARE, Lifecycle.RUNNING):
                raise ValueError("no active task to pause")
            if execution.action_phase == Phase.COMMIT:
                raise ValueError("map commit must finish before pausing")
            execution.pause()
            return self._publish("user pause")
        if kind == EventKind.RESUME:
            if not execution:
                raise ValueError("no paused task to resume")
            if self.low_battery and mode != BusinessMode.RETURN_TO_CHARGE:
                raise ValueError("battery is low")
            owner = self.mapping or self.task
            owner.execution = execution.resume()
            return self._publish()
        if kind == EventKind.CANCEL:
            if execution and execution.action_phase == Phase.COMMIT and not execution.retry_pending:
                raise ValueError("map commit must finish before cancelling")
            for task in (self.task, self.suspended):
                if task:
                    self.history.append({"mission_id": task.mission.mission_id, "result": "cancelled"})
                    self._record_execution("cancelled", task.execution)
            if self.mapping:
                self.history.append({"mission_id": self.mapping.session_id, "result": "cancelled"})
                self._record_execution("cancelled")
            self.task = self.mapping = self.suspended = None
            self.business_mode = BusinessMode.IDLE
            return self._publish()
        if not self.mapping:
            raise ValueError("mapping command requires an executing mapping session")
        self.mapping.command(event)
        return self._publish()

    def _status(self, status):
        if not self.health.accept(status, self.now):
            return None
        execution = self.execution
        if (self.fault_latched or not execution
                or execution.lifecycle not in (Lifecycle.PREPARE, Lifecycle.RUNNING)):
            return None
        if self.mapping and self.mapping.recover_rejection(status):
            if self.low_battery:
                execution.pause()
            return self._publish(status.reason)
        if status.state in (State.FAILED, State.BLOCKED, State.REJECTED):
            return self._fail(f"{status.module}: {status.reason or status.state}")
        if execution.action_phase == Phase.PREPARE:
            if self.health.ready(self.now):
                execution.activate()
                return self._publish()
            return None
        if self.mapping:
            if not self.mapping.feedback(status):
                return None
            if execution.lifecycle == Lifecycle.SUCCESS:
                self._record_execution("completed")
                self.history.append({"mission_id": self.mapping.session_id, "result": "completed",
                    "map_id": self.mapping.map_id, "regions": list(self.mapping.regions),
                    "channels": list(self.mapping.channels)})
                self.mapping = None
                self.business_mode = BusinessMode.IDLE
            elif self.low_battery and execution.action_phase != Phase.COMMIT:
                execution.pause()
                return self._publish("low battery")
            return self._publish()
        if status.state != State.SUCCEEDED:
            return None
        execution.finish(True)
        self._record_execution("completed")
        self.task.cursor += 1
        if self.task.cursor == len(self.task.mission.targets):
            return self._finish()
        self.task.start_target()
        return self._publish()

    def tick(self, now):
        """Clock input is supplied by the host, including when all modules are silent."""
        self._clock(now)
        expired = self.health.expired(now)
        if expired:
            return self._fail(f"{expired[0]}: status timeout")
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
