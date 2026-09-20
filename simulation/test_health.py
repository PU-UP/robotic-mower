"""Health facts are testable without the business state machine or algorithms."""
from dataclasses import replace
import unittest

from brain import Brain
from brain.health import HealthEventManager
from contracts import Control, Directive, Event, EventKind, MissionType, Module, Mode, Phase, State, Status, WorkItem


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.health = HealthEventManager()
        self.directive = Directive(1, Mode.WORKING, Phase.PREPARE,
            WorkItem(MissionType.COVER_REGION, "garden", "r1", Control.AUTO))
        self.health.begin(self.directive, 0)

    def test_feedback_filter_and_new_revision_barrier(self):
        status = Status(Module.PERCEPTION, 1, 2, 0.2, State.READY)
        self.assertTrue(self.health.accept(status, 0.2))
        for invalid in (status, replace(status, sequence=1), replace(status, revision=0),
                        replace(status, sequence=3, stamp=0.1), replace(status, stamp=2)):
            with self.subTest(invalid=invalid):
                self.assertFalse(self.health.accept(invalid, 0.3))
        self.assertFalse(self.health.ready(0.3))
        for module in (Module.MAP_MANAGER, Module.PNC):
            self.health.accept(replace(status, module=module), 0.3)
        self.assertTrue(self.health.ready(0.3))
        self.health.begin(replace(self.directive, revision=2), 0.4)
        self.assertFalse(self.health.ready(0.4))
        snapshot = self.health.snapshot(0.4)
        self.assertFalse(snapshot["modules"]["perception"]["current"])
        self.assertEqual(snapshot["capabilities"]["navigation"]["state"], "UNAVAILABLE")
        with self.assertRaises(TypeError):
            self.health.statuses[Module.PNC] = status

    def test_capabilities_keep_map_commit_independent_and_preserve_evidence(self):
        self.health.begin(Directive(2, Mode.MAPPING, Phase.COMMIT,
            WorkItem(MissionType.SAVE_MAP, "garden", None, Control.NONE)), 0)
        for module, state, reason in (
            (Module.PERCEPTION, State.FAILED, "LOCALIZATION_LOST"),
            (Module.MAP_MANAGER, State.RUNNING, ""),
            (Module.PNC, State.BLOCKED, "CONTROL_BLOCKED"),
        ):
            self.health.accept(Status(module, 2, 1, 0.1, state, reason), 0.1)
        snapshot = self.health.snapshot(0.1)
        self.assertEqual(snapshot["capabilities"]["map_commit"]["state"], "AVAILABLE")
        self.assertEqual(snapshot["capabilities"]["navigation"]["state"], "UNAVAILABLE")
        self.assertEqual({c["reason"] for c in snapshot["causes"]},
                         {"LOCALIZATION_LOST", "CONTROL_BLOCKED"})
        snapshot["modules"]["perception"]["status"]["reason"] = "changed"
        self.assertEqual(self.health.snapshot(0.1)["modules"]["perception"]["status"]["reason"],
                         "LOCALIZATION_LOST")
        self.assertEqual(self.health.snapshot(1.2)["capabilities"]["map_commit"]["state"], "UNAVAILABLE")

    def test_event_replay_cannot_mutate_original_result(self):
        event = Event("battery", EventKind.LOW_BATTERY)
        self.health.observe_event(event)
        self.health.remember_event(event, {"accepted": True, "revision": 1})
        replay = self.health.previous_event(event)
        replay["accepted"] = False
        self.assertTrue(self.health.previous_event(event)["accepted"])
        self.assertEqual(self.health.previous_event(Event("battery", EventKind.BATTERY_OK))["reason"],
                         "event_id reused")
        self.assertTrue(self.health.low_battery)


class HealthIntegrationTests(unittest.TestCase):
    def start(self):
        brain = Brain()
        command = {"command_id": "start", "type": "START_MOWING",
                   "params": {"map_id": "garden", "region_ids": ["r1"]}}
        brain.receive("command", command, 0)
        return brain, command

    def test_late_fresh_heartbeat_cannot_erase_timeout_without_tick(self):
        brain, _ = self.start()
        # Only perception expires; other peers remain fresh.
        for module in Module:
            stamp = 0 if module == Module.PERCEPTION else 0.5
            brain.receive("status", Status(module, 1, 1, stamp, State.RUNNING).to_dict(), 0.5)
        result = brain.receive("status", Status(Module.PERCEPTION, 1, 2, 1.01, State.READY).to_dict(), 1.01)
        self.assertEqual(result["directive"]["mode"], "ERROR")
        self.assertIn("perception: status timeout", brain.reason)

    def test_timeout_boundary_and_duplicate_command_still_checks_deadline(self):
        brain, command = self.start()
        self.assertIsNone(brain.tick(1))
        result = brain.receive("command", command, 1.01)
        self.assertEqual(result["directive"]["mode"], "ERROR")
        self.assertEqual(result["command_result"]["revision"], 1)
        self.assertEqual(result["command_result"]["state"], "ACCEPTED")
        self.assertEqual(brain.task.cursor, 0)

    def test_command_cannot_hide_new_timeout_or_reset_it_in_same_step(self):
        for command_type in ("PAUSE", "CANCEL", "RESET_ERROR"):
            with self.subTest(command_type=command_type):
                brain, _ = self.start()
                result = brain.receive("command", {"command_id": "late", "type": command_type}, 1.01)
                self.assertEqual(result["directive"]["mode"], "ERROR")
                self.assertEqual(result["command_result"]["state"], "REJECTED")
                self.assertIsNotNone(brain.task)

    def test_snapshots_and_command_ack_are_detached(self):
        brain, command = self.start()
        result = brain.receive("command", command, 0.1)
        result["command_result"]["state"] = "changed"
        view = brain.view()
        view["last_event"]["accepted"] = False
        self.assertTrue(brain.last_result["accepted"])
        self.assertEqual(brain.last_command_result["state"], "ACCEPTED")
        self.assertEqual(brain.receive("command", command, 0.2)["command_result"]["state"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
