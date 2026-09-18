"""A timeline of JSON inputs and expected outputs; business rules stay in brain."""
import json
import math
from dataclasses import asdict
from pathlib import Path
import re

from contracts import Module, Status, nonnegative_number, object_fields
from simulation.run import Simulation


def matches(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and matches(actual[key], value)
                                               for key, value in expected.items())
    return actual == expected


def run_script(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    object_fields(spec, ("name", "description", "duration", "feedback", "steps"), ("mapped",))
    if not isinstance(spec["name"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", spec["name"]):
        raise ValueError("scenario name must be a safe filename")
    nonnegative_number(spec["duration"])
    if not isinstance(spec["steps"], list) or not spec["steps"]:
        raise ValueError("steps must be a non-empty array")
    if not isinstance(spec.get("mapped", True), bool):
        raise ValueError("mapped must be a boolean")
    previous = 0
    for step in spec["steps"]:
        object_fields(step, ("at",), ("command", "event", "status", "fault", "world", "expect", "delay", "label"))
        nonnegative_number(step["at"])
        if not previous <= step["at"] < spec["duration"]:
            raise ValueError("steps must be chronological and earlier than duration")
        previous = step["at"]
        if sum(key in step for key in ("command", "event", "status", "fault", "world", "expect")) != 1:
            raise ValueError("each step requires exactly one input or expectation")
        if "delay" in step:
            nonnegative_number(step["delay"])
            if "status" not in step:
                raise ValueError("delay only applies to status delivery")
        if "expect" in step:
            object_fields(step["expect"], (), ("directive", "brain_status", "command_result"))
            if not step["expect"] or any(not isinstance(v, dict) or not v for v in step["expect"].values()):
                raise ValueError("expect requires non-empty output objects")
    if not any("expect" in step for step in spec["steps"]):
        raise ValueError("scenario needs at least one expectation")
    sim = Simulation(mapped=spec.get("mapped", True), feedback=spec["feedback"])
    checks = []
    for step in spec["steps"]:
        if step["at"] > sim.env.now:
            sim.until(step["at"])
        if "command" in step:
            sim.receive("command", step["command"])
        elif "event" in step:
            sim.receive("event", step["event"])
        elif "status" in step:
            sim.env.process(sim._status(Status.from_dict(step["status"]), step.get("delay", 0.01)))
        elif "world" in step:
            object_fields(step["world"], ("position",))
            position = step["world"]["position"]
            if (not isinstance(position, list) or len(position) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in position)):
                raise ValueError("world position must contain two finite coordinates")
            sim.position = tuple(position)
            sim.record("world", "position", target="perception", payload=step["world"])
        elif "fault" in step:
            fault = step["fault"]
            object_fields(fault, ("module",), ("reason", "silent"))
            module = sim.modules[Module(fault["module"])]
            if "reason" in fault:
                if not isinstance(fault["reason"], str):
                    raise ValueError("fault reason must be a string (empty string clears it)")
                module.fault = fault["reason"]
            if "silent" in fault:
                if not isinstance(fault["silent"], bool):
                    raise ValueError("silent must be a boolean")
                module.silent = fault["silent"]
            sim.record("scenario", "fault", payload=fault)
        else:
            actual = {"directive": sim.brain.directive.to_dict(), "brain_status": sim.brain.status(),
                      "command_result": sim.brain.last_command_result}
            checks.append({"name": step.get("label", f"t={step['at']} output matches"),
                           "passed": matches(actual, step["expect"]), "expected": step["expect"],
                           "actual": {key: actual[key] for key in step["expect"]}})
    sim.until(spec["duration"])
    return {"scenario": spec["name"], "description": spec["description"], "checks": checks,
            "frames": sim.frames, "events": sim.events, "final": sim.brain.view(),
            "business_map": asdict(sim.modules[Module.MAP_MANAGER].business_map)
                if sim.modules[Module.MAP_MANAGER].business_map else None}
