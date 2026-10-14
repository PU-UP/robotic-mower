"""Independent lifecycle and business modes, observed through the public protocol."""
from copy import deepcopy
import unittest

from brain import Brain
from brain.mission import Lifecycle, MissionExecution
from contracts import Control, MissionType, Module, Phase, State, Status, WorkItem


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.now, self.sequence = 0.0, 0

    def command(self, kind, **params):
        self.sequence += 1
        return self.brain.receive("command", {"command_id": str(self.sequence), "type": kind, "params": params}, self.now)

    def event(self, kind):
        self.sequence += 1
        return self.brain.receive("event", {"event_id": str(self.sequence), "type": kind}, self.now)

    def feedback(self, module, state=State.READY, **kwargs):
        self.sequence += 1
        self.now += 0.01
        return self.brain.receive("status", Status(module, self.brain.directive.revision,
            self.sequence, self.now, state, **kwargs).to_dict(), self.now)

    def ready(self):
        for module in Module:
            self.feedback(module)

    def state(self):
        return self.brain.status()

    def start_work(self):
        self.command("START_MOWING", map_id="garden", region_ids=["a", "b"])
        self.ready()

    def test_pause_preserves_mode_and_resume_requires_fresh_readiness(self):
        self.start_work()
        self.command("PAUSE")
        self.assertEqual(self.state()["business_mode"], "WORKING")
        self.assertEqual(self.state()["mode"], "PAUSED")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "PAUSED")
        self.assertEqual(self.state()["mission_state"]["stage"], "MOW_REGION")
        self.command("RESUME")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "PREPARE")
        self.assertEqual(self.state()["mission_state"]["attempt"], 1)
        self.ready()
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "RUNNING")

    def test_mapping_action_preparation_does_not_restart_mission(self):
        self.command("START_MAPPING", map_id="new")
        self.assertEqual(self.state()["mission_state"]["stage"], "UNDOCK")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.command("SELECT_REGION_START", region_id="r1")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "RUNNING")
        self.assertEqual(self.state()["mission_state"]["stage"], "BUILD_BOUNDARY")
        self.assertEqual(self.state()["phase"], "PREPARE")
        self.ready()
        self.command("START_EDGE_FOLLOW")
        self.ready()
        self.command("TAKE_OVER")
        self.assertEqual(self.state()["mission_state"]["attempt"], 1)
        self.assertEqual(self.state()["mission_state"]["action"]["control"], "MANUAL")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED")
        self.assertEqual(self.state()["mission_state"]["stage"], "COMMIT_OBJECT")
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.state()["mission_state"]["stage"], "WAIT_START")
        self.assertIsNone(self.state()["last_mission_result"])
        self.ready()
        self.command("FINISH_MAPPING")
        self.assertEqual(self.state()["mission_state"]["stage"], "SAVE_MAP")
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.state()["business_mode"], "IDLE")
        self.assertIsNone(self.state()["mission_state"])
        self.assertEqual(self.state()["last_mission_result"]["lifecycle"], "SUCCESS")

    def test_fault_attempt_is_terminal_and_reset_does_not_start_retry(self):
        self.start_work()
        original = self.brain.execution
        self.feedback(Module.ROBOFRAME, State.FAILED, reason="LOCALIZATION_LOST")
        failure = deepcopy(self.state()["last_mission_result"])
        self.assertTrue(self.state()["fault_latched"])
        self.assertEqual(self.state()["business_mode"], "WORKING")
        self.assertEqual(original.lifecycle, Lifecycle.FAILED)
        self.assertEqual(self.command("RESUME")["command_result"]["state"], "REJECTED")
        self.command("RESET_ERROR")
        self.assertFalse(self.state()["fault_latched"])
        self.assertEqual(self.state()["mode"], "PAUSED")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "FAILED")
        self.assertTrue(self.state()["mission_state"]["retry_pending"])
        self.command("RESUME")
        self.assertIsNot(self.brain.execution, original)
        self.assertEqual(original.lifecycle, Lifecycle.FAILED)
        self.assertEqual(self.state()["mission_state"]["attempt"], 2)
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "PREPARE")
        self.assertEqual(self.state()["last_mission_result"], failure)
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.state()["last_mission_result"]["attempt"], 2)
        self.assertEqual(self.state()["mission_state"]["target_id"], "b")
        self.assertEqual(self.state()["mission_state"]["attempt"], 1)
        self.assertEqual(self.state()["task"]["completed_targets"], ["a"])

    def test_low_battery_switches_mode_and_preserves_suspended_execution(self):
        self.start_work()
        self.event("LOW_BATTERY")
        self.assertEqual(self.state()["business_mode"], "RETURN_TO_CHARGE")
        self.assertEqual(self.state()["mode"], "RETURNING")
        self.assertEqual(self.state()["suspended_mission"]["lifecycle"], "PAUSED")
        saved = deepcopy(self.state()["suspended_mission"])
        self.event("LOW_BATTERY")
        self.assertEqual(self.state()["suspended_mission"], saved)
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.state()["business_mode"], "CHARGING")
        self.event("BATTERY_OK")
        self.assertEqual(self.state()["business_mode"], "WORKING")
        self.assertEqual(self.state()["mission_state"], saved)
        self.assertEqual(self.state()["mode"], "PAUSED")
        self.command("RESUME")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "PREPARE")

    def test_low_battery_after_reset_preserves_failed_attempt_for_later_retry(self):
        self.start_work()
        self.feedback(Module.ROBOFRAME, State.FAILED)
        self.command("RESET_ERROR")
        self.event("LOW_BATTERY")
        self.assertEqual(self.state()["business_mode"], "RETURN_TO_CHARGE")
        self.assertEqual(self.state()["suspended_mission"]["lifecycle"], "FAILED")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.event("BATTERY_OK")
        self.assertEqual(self.state()["mode"], "PAUSED")
        self.command("RESUME")
        self.assertEqual(self.state()["mission_state"]["attempt"], 2)

    def test_automatic_return_has_a_unique_reserved_task_id(self):
        # User IDs are opaque; a user may already occupy the generated base name.
        original_id = "return:event:low"
        self.brain.receive("command", {"command_id": original_id, "type": "START_MOWING",
            "params": {"map_id": "garden", "region_ids": ["a"]}}, self.now)
        self.brain.receive("event", {"event_id": "low", "type": "LOW_BATTERY"}, self.now)
        return_id = self.brain.directive.task_id
        self.assertNotEqual(return_id, original_id)
        self.assertEqual(self.state()["suspended_task"]["task_id"], original_id)
        self.assertIn(return_id, self.brain.used_missions)
        self.command("CANCEL")
        self.event("BATTERY_OK")
        result = self.brain.receive("command", {"command_id": return_id, "type": "START_MOWING",
            "params": {"map_id": "garden", "region_ids": ["a"]}}, self.now)
        self.assertEqual(result["command_result"]["state"], "REJECTED")
        self.assertIsNone(self.brain.task)

    def test_cancel_is_a_result_not_a_successful_execution(self):
        self.start_work()
        self.command("CANCEL")
        state = self.state()
        self.assertEqual(state["business_mode"], "IDLE")
        self.assertIsNone(state["mission_state"])
        self.assertEqual(state["last_mission_result"]["result"], "cancelled")
        self.assertNotEqual(state["last_mission_result"]["lifecycle"], "SUCCESS")
        state["last_mission_result"]["action"]["target_id"] = "changed"
        self.assertEqual(self.state()["last_mission_result"]["target_id"], "a")

    def test_mapping_pause_preserves_stage_and_rejects_stage_commands(self):
        self.command("START_MAPPING", map_id="new")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.command("SELECT_REGION_START", region_id="r1")
        self.ready()
        self.command("PAUSE")
        before = deepcopy(self.state()["mission_state"])
        self.assertEqual(self.state()["business_mode"], "MAPPING")
        self.assertEqual(self.command("START_EDGE_FOLLOW")["command_result"]["state"], "REJECTED")
        self.assertEqual(self.state()["mission_state"], before)
        self.command("RESUME")
        self.assertEqual(self.state()["mission_state"]["stage"], "BUILD_BOUNDARY")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "PREPARE")

    def test_commit_retry_keeps_stage_and_old_attempt_cannot_complete_it(self):
        self.command("START_MAPPING", map_id="new")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.command("SELECT_REGION_START", region_id="r1")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED")
        old_revision = self.brain.directive.revision
        self.feedback(Module.ROBOFRAME, State.FAILED, reason="SAVE_FAILED")
        self.command("RESET_ERROR")
        self.command("RESUME")
        self.assertEqual(self.state()["mission_state"]["attempt"], 2)
        self.assertEqual(self.state()["mission_state"]["stage"], "COMMIT_OBJECT")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "RUNNING")
        self.brain.receive("status", Status(Module.ROBOFRAME, old_revision, 100,
            self.now, State.SUCCEEDED).to_dict(), self.now)
        self.assertEqual(self.brain.mapping.regions, [])
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.brain.mapping.regions, ["r1"])
        self.assertEqual(self.state()["mission_state"]["stage"], "WAIT_START")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "RUNNING")

    def test_low_battery_save_rejection_preserves_session_without_reopening_motion(self):
        self.command("START_MAPPING", map_id="new")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.command("SELECT_REGION_START", region_id="r1")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED")
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.command("FINISH_MAPPING")
        self.event("LOW_BATTERY")
        self.feedback(Module.ROBOFRAME, State.REJECTED, reason="CHANNEL_NOT_CONNECTED")
        state = self.state()
        self.assertEqual(state["business_mode"], "MAPPING")
        self.assertEqual(state["mission_state"]["lifecycle"], "PAUSED")
        self.assertEqual(state["mission_state"]["stage"], "WAIT_START")
        self.assertEqual(state["mapping"]["regions"], ["r1"])
        self.assertEqual(state["mapping"]["last_result"]["reason"], "CHANNEL_NOT_CONNECTED")
        self.assertFalse(state["fault_latched"])
        self.assertIsNone(self.brain.directive.mission)
        self.assertEqual(self.command("RESUME")["command_result"]["state"], "REJECTED")
        self.event("BATTERY_OK")
        self.assertEqual(self.state()["mission_state"]["lifecycle"], "PAUSED")
        self.command("RESUME")
        self.assertEqual(self.state()["phase"], "PREPARE")
        self.assertEqual(self.state()["mission_state"]["attempt"], 1)

    def test_interruptions_preserve_region_and_stable_task_id(self):
        for interruption in ("pause", "low_battery", "fault"):
            with self.subTest(interruption=interruption):
                self.setUp()
                self.start_work()
                self.assertEqual(self.state()["mission_state"]["type"], "MOW_REGION")
                task_id = self.brain.directive.task_id
                self.assertEqual(self.state()["task"]["completed_targets"], [])
                if interruption == "pause":
                    self.command("PAUSE")
                elif interruption == "low_battery":
                    self.event("LOW_BATTERY")
                    self.assertEqual(self.state()["suspended_mission"]["type"], "MOW_REGION")
                    self.ready()
                    self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
                    self.event("BATTERY_OK")
                else:
                    self.feedback(Module.ROBOFRAME, State.FAILED, reason="BLOCKED")
                    self.command("RESET_ERROR")
                self.command("RESUME")
                self.assertEqual(self.brain.directive.task_id, task_id)
                current = self.state()["mission_state"]
                self.assertEqual((current["type"], current["target_id"]), ("MOW_REGION", "a"))
                self.assertEqual(current["attempt"], 2 if interruption == "fault" else 1)
                self.ready()
                self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
                self.assertEqual(self.state()["task"]["completed_targets"], ["a"])
                self.assertEqual(self.state()["mission_state"]["type"], "MOW_REGION")
                self.assertEqual(self.state()["mission_state"]["target_id"], "b")
                edge_results = [r for r in self.brain.mission_results if r["type"] == "MOW_REGION" and r["result"] == "completed"]
                self.assertEqual(len(edge_results), 1)

    def test_standalone_lifecycle_rejects_illegal_terminal_transitions(self):
        execution = MissionExecution("task", "MOW_REGION",
            WorkItem(MissionType.MOW_REGION, "map", "r1", Control.AUTO))
        with self.assertRaises(ValueError):
            execution.finish(True)
        execution.activate()
        execution.finish(True)
        for action in (execution.pause, execution.resume, execution.activate, lambda: execution.finish(False)):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(execution.lifecycle, Lifecycle.SUCCESS)


if __name__ == "__main__":
    unittest.main()
