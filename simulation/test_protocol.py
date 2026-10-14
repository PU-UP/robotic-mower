"""Executable examples for the public wire format and scripted test bench."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from brain import Brain
from contracts import Directive, Status, WorkItem, MissionType, Control, Module, Mode, Phase
from simulation.scripted import run_script


class ProtocolTests(unittest.TestCase):
    def command(self):
        return {"command_id": "cmd-1", "type": "START_MOWING",
                "params": {"map_id": "garden", "region_ids": ["region-1", "region-2"]}}

    def test_user_directive_roundtrip_has_exact_fields(self):
        data = {"task_id": "work-1", "revision": 8, "mode": "WORKING", "phase": "EXECUTE",
                "mission": {"type": "MOW_REGION", "map_id": "garden", "target_id": "region-2", "control": "AUTO"}}
        self.assertEqual(json.loads(json.dumps(Directive.from_dict(data).to_dict())), data)
        data["mission"]["mission_id"] = "should-not-leak"
        with self.assertRaises(ValueError):
            Directive.from_dict(data)

    def test_all_missions_share_fixed_fields_and_validate_target_control(self):
        cases = [
            ("UNDOCK", "dock", ("AUTO",)),
            ("MAP_RETURN_CHANNEL", "return-channel", ("MANUAL",)),
            ("MANUAL_DRIVE", None, ("MANUAL",)),
            ("MAP_REGION", "new-region", ("MANUAL", "AUTO")),
            ("MAP_CHANNEL", "new-channel", ("MANUAL",)),
            ("SAVE_MAP", None, ("NONE",)),
            ("MOW_REGION", "region-1", ("AUTO",)),
            ("RETURN_HOME", "dock", ("AUTO",)),
        ]
        self.assertEqual({kind for kind, _, _ in cases}, {kind.value for kind in MissionType})
        for kind, target, controls in cases:
            for control in Control:
                data = {"type": kind, "map_id": "garden", "target_id": target, "control": control.value}
                with self.subTest(type=kind, control=control):
                    if control.value not in controls:
                        with self.assertRaises(ValueError):
                            WorkItem.from_dict(data)
                        continue
                    self.assertEqual(WorkItem.from_dict(data).to_dict(), data)
                    for field in data:
                        missing = {k: v for k, v in data.items() if k != field}
                        with self.assertRaises(ValueError):
                            WorkItem.from_dict(missing)
                    for invalid_target in ([None, "", 1] if target else ["unexpected-target"]):
                        with self.assertRaises(ValueError):
                            WorkItem.from_dict({**data, "target_id": invalid_target})
                    for old_field in ("region_id", "channel_id", "station_id"):
                        with self.assertRaises(ValueError):
                            WorkItem.from_dict({**data, old_field: target})
                    for invalid_control in (None, "AUTO_EDGE", "unknown"):
                        with self.assertRaises(ValueError):
                            WorkItem.from_dict({**data, "control": invalid_control})
        stopped = {"revision": 10, "mode": "IDLE", "phase": "NONE", "mission": None, "task_id": None}
        self.assertEqual(Directive.from_dict(stopped).to_dict(), stopped)

    def test_control_stops_during_prepare_and_inactive_phases(self):
        from simulation.doubles import RoboframeDouble, garden
        runtime = RoboframeDouble(garden())
        item = WorkItem(MissionType.MOW_REGION, "garden", "region-1", Control.AUTO)
        position = (0, 0)
        runtime.configure(Directive(1, Mode.WORKING, Phase.PREPARE, item, "work"), 0)
        runtime.step(0, runtime.observe(0, position))
        self.assertEqual(runtime.control, "STOPPED")
        self.assertEqual(runtime.motion_target(.1, position), position)
        runtime.configure(Directive(2, Mode.WORKING, Phase.EXECUTE, item, "work"), .1)
        runtime.step(.1, runtime.observe(.1, position))
        self.assertEqual(runtime.control, "AUTO_GOAL")
        runtime.configure(Directive(3, Mode.PAUSED, Phase.NONE, None), .2)
        runtime.step(.2, runtime.observe(.2, position))
        self.assertEqual(runtime.control, "STOPPED")
        self.assertFalse(runtime.blade_requested)

    def test_status_has_optional_progress_and_machine_readable_reason(self):
        data = {"module": "roboframe", "revision": 4, "sequence": 18, "stamp": 12.3,
                "state": "RUNNING", "progress": 0.35, "reason": None}
        self.assertEqual(Status.from_dict(data).to_dict(), data)
        for old_source in ("perception", "map_manager", "pnc"):
            with self.subTest(source=old_source), self.assertRaises(ValueError):
                Status.from_dict({**data, "module": old_source})
        for value in (-1, 1.1, float("nan"), True, "0.3"):
            with self.subTest(progress=value), self.assertRaises(ValueError):
                Status.from_dict({**data, "progress": value})

    def test_command_ack_is_stable_but_does_not_mean_task_complete(self):
        brain = Brain()
        first = brain.receive("command", self.command(), 0)
        self.assertEqual(first["command_result"]["state"], "ACCEPTED")
        self.assertIsNone(first["brain_status"]["last_task_result"])
        self.assertEqual(first["directive"]["mission"], {
            "type": "MOW_REGION", "map_id": "garden", "target_id": "region-1", "control": "AUTO"})
        brain.receive("command", {"command_id": "pause", "type": "PAUSE"}, 0.1)
        duplicate = brain.receive("command", self.command(), 0.2)
        self.assertEqual(duplicate["command_result"], first["command_result"])
        self.assertIsNone(duplicate["directive"])
        self.assertEqual(duplicate["brain_status"]["mode"], "PAUSED")
        conflict = brain.receive("command", {"command_id": "cmd-1", "type": "CANCEL"}, 0.3)
        self.assertEqual(conflict["command_result"]["reason"], "ID_CONFLICT")

    def test_input_is_detached_and_invalid_commands_cannot_change_brain(self):
        brain = Brain()
        data = self.command()
        brain.receive("command", data, 0)
        data["params"]["region_ids"].clear()
        self.assertEqual(brain.task.mission.targets, ("region-1", "region-2"))
        before = brain.directive
        for invalid in (
            {"command_id": "bad", "type": "START_MOWING", "params": {"map_id": "garden", "region_ids": []}},
            {"command_id": "bad", "type": "SET_MODE", "params": {"mode": "WORKING"}},
            {"command_id": "bad", "type": "PAUSE", "unexpected": 1},
        ):
            response = brain.receive("command", invalid, 0.1)
            self.assertEqual(response["command_result"]["reason"], "INVALID_COMMAND")
            self.assertEqual(brain.directive, before)

    def test_mapping_home_commands_and_system_events_have_separate_shapes(self):
        examples = [
            ({"command_id": "map", "type": "START_MAPPING", "params": {"map_id": "new"}},
             {"type": "UNDOCK", "map_id": "new", "target_id": "dock", "control": "AUTO"}),
            ({"command_id": "home", "type": "RETURN_HOME", "params": {"map_id": "garden", "station_id": "dock"}},
             {"type": "RETURN_HOME", "map_id": "garden", "target_id": "dock", "control": "AUTO"}),
        ]
        for command, mission in examples:
            with self.subTest(command=command):
                self.assertEqual(Brain().receive("command", command, 0)["directive"]["mission"], mission)
        brain = Brain()
        brain.receive("event", {"event_id": "cmd-1", "type": "LOW_BATTERY"}, 0)
        response = brain.receive("command", self.command(), 0.1)
        self.assertEqual(response["command_result"]["reason"], "NOT_ALLOWED")
        self.assertTrue(response["brain_status"]["reason"] is None)
        with self.assertRaises(ValueError):
            brain.receive("event", {"event_id": "wrong", "type": "PAUSE"}, 0.2)

    def test_module_rejection_faults_without_completing_task(self):
        brain = Brain()
        brain.receive("command", self.command(), 0)
        response = brain.receive("status", {"module": "roboframe", "revision": 1, "sequence": 1,
            "stamp": 0.1, "state": "REJECTED", "reason": "MAP_NOT_FOUND"}, 0.1)
        self.assertEqual(response["directive"]["mode"], "ERROR")
        self.assertEqual(response["brain_status"]["task"]["completed_targets"], [])

    def test_script_examples_are_reproducible_and_exact_user_sample_is_emitted(self):
        for path in Path(__file__).with_name("scenarios").glob("*.json"):
            with self.subTest(script=path.name):
                first = run_script(path)
                self.assertEqual(first, run_script(path))
                self.assertTrue(all(c["passed"] for c in first["checks"]), first["checks"])
                if path.stem == "cover_regions":
                    emitted = next(e["payload"] for e in first["events"]
                                   if e["action"] == "mode_mission" and e["revision"] == 4)
                    self.assertEqual(emitted, {"task_id": "work-1", "revision": 4, "mode": "WORKING", "phase": "EXECUTE",
                        "mission": {"type": "MOW_REGION", "map_id": "garden", "target_id": "region-2", "control": "AUTO"}})

    def test_script_failures_are_real_checks_and_bad_timeline_is_rejected(self):
        spec = {"name": "test", "description": "test", "feedback": "auto", "duration": 1,
                "steps": [{"at": 0.1, "expect": {"directive": {"mode": "WORKING"}}}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "case.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            self.assertFalse(run_script(path)["checks"][0]["passed"])
            broken = deepcopy(spec)
            broken["steps"].append({"at": 0, "expect": {"directive": {"mode": "IDLE"}}})
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_script(path)


if __name__ == "__main__":
    unittest.main()
