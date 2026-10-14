"""Mapping session ownership, handover, closure, and channel-origin constraints."""
from pathlib import Path
import unittest

from brain import Brain
from contracts import Module, Phase, State, Status
from simulation.world import BusinessMap, Entity
from simulation.scripted import run_script


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.now = 0
        self.counter = 0

    def command(self, kind, **params):
        self.now += 0.02
        self.counter += 1
        return self.brain.receive("command", {"command_id": f"cmd-{self.counter}", "type": kind,
                                              "params": params}, self.now)

    def feedback(self, module, state=State.READY, *, signal=None, revision=None, reason=""):
        self.now += 0.02
        self.counter += 1
        status = Status(module, self.brain.directive.revision if revision is None else revision,
                        self.counter, self.now, state, reason, signal=signal)
        return self.brain.receive("status", status.to_dict(), self.now)

    def ready(self):
        for module in Module:
            self.feedback(module)

    def start_region(self):
        self.command("START_MAPPING", map_id="new")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.command("SELECT_REGION_START", region_id="r1")
        self.ready()

    def close_region(self, module=Module.ROBOFRAME):
        self.feedback(module, State.RUNNING, signal="REGION_CLOSED")
        self.assertEqual(self.brain.directive.phase, Phase.COMMIT)
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()

    def test_takeover_reuses_region_and_waits_for_fresh_module_readiness(self):
        self.start_region()
        self.command("START_EDGE_FOLLOW")
        self.ready()
        old_revision = self.brain.directive.revision
        result = self.command("TAKE_OVER")
        self.assertEqual(result["directive"]["mission"], {
            "type": "MAP_REGION", "map_id": "new", "target_id": "r1", "control": "MANUAL"})
        self.feedback(Module.ROBOFRAME, State.RUNNING, revision=old_revision, signal="REGION_CLOSED")
        self.assertEqual(self.brain.directive.phase, Phase.PREPARE)
        self.feedback(Module.ROBOFRAME)
        self.assertEqual(self.brain.directive.phase, Phase.EXECUTE)
        self.command("START_EDGE_FOLLOW")
        self.ready()
        self.assertEqual(self.brain.directive.mission.target_id, "r1")
        self.assertEqual(self.brain.mapping.regions, [])

    def test_closure_requires_separate_commit_confirmation(self):
        self.start_region()
        revision = self.brain.directive.revision
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.brain.directive.phase, Phase.EXECUTE)
        self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED")
        self.assertEqual(self.brain.mapping.regions, [])
        self.assertEqual(self.brain.directive.phase, Phase.COMMIT)
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED, revision=revision)
        self.assertEqual(self.brain.mapping.regions, [])
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED", revision=revision)
        self.assertEqual(self.brain.mapping.regions, ["r1"])
        self.assertEqual(self.brain.directive.mission.type, "MANUAL_DRIVE")

    def test_wrong_stage_commands_and_unrelated_closure_cannot_end_mapping(self):
        self.command("START_MAPPING", map_id="new")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        for kind, params in (("FINISH_MAPPING", {}), ("START_CHANNEL", {"channel_id": "c1"}),
                             ("TAKE_OVER", {}), ("START_EDGE_FOLLOW", {})):
            before = self.brain.directive
            self.assertEqual(self.command(kind, **params)["command_result"]["state"], "REJECTED")
            self.assertEqual(before, self.brain.directive)
        self.command("SELECT_REGION_START", region_id="r1")
        self.ready()
        self.assertEqual(self.command("FINISH_MAPPING")["command_result"]["state"], "REJECTED")
        self.close_region()
        self.command("START_CHANNEL", channel_id="c1")
        self.ready()
        self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED")
        self.assertEqual(self.brain.directive.mission.type, "MAP_CHANNEL")
        self.assertEqual(self.brain.directive.phase, Phase.EXECUTE)

    def test_invalid_channel_start_returns_to_manual_without_recording_completion(self):
        self.start_region()
        self.close_region()
        self.command("START_CHANNEL", channel_id="c1")
        old_revision = self.brain.directive.revision
        self.feedback(Module.ROBOFRAME, State.REJECTED, reason="CHANNEL_START_OUTSIDE_REGION")
        self.assertEqual(self.brain.directive.mission.type, "MANUAL_DRIVE")
        self.assertEqual(self.brain.mapping.channels, [])
        self.assertEqual(self.brain.mapping.last_result["result"], "rejected")
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED, revision=old_revision)
        self.ready()
        self.command("START_CHANNEL", channel_id="c1")
        self.ready()
        self.command("FINISH_CHANNEL")
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.ready()
        self.assertEqual(self.brain.mapping.channels, ["c1"])

    def test_final_save_ack_is_required_and_commit_cannot_be_interrupted(self):
        self.start_region()
        self.close_region()
        self.command("FINISH_MAPPING")
        self.assertEqual(self.brain.directive.mission.type, "SAVE_MAP")
        for kind in ("CANCEL", "PAUSE", "SELECT_REGION_START"):
            params = {"region_id": "r2"} if kind == "SELECT_REGION_START" else {}
            self.assertEqual(self.command(kind, **params)["command_result"]["state"], "REJECTED")
        self.feedback(Module.ROBOFRAME, State.RUNNING)
        self.assertEqual(self.brain.directive.mode, "MAPPING")
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.brain.directive.mode, "IDLE")
        self.assertEqual(self.brain.status()["last_task_result"]["regions"], ["r1"])

    def test_user_flow_records_takeover_but_excludes_transit_poses(self):
        result = run_script(Path(__file__).with_name("scenarios") / "mapping_session.json")
        self.assertTrue(all(c["passed"] for c in result["checks"]))
        entities = {e["entity_id"]: e for e in result["business_map"]["entities"]}
        self.assertEqual(set(entities), {"dock", "return-channel", "region-1", "region-2", "channel-1"})
        self.assertEqual(entities["region-1"]["points"], ((0, 0), (4, 0), (4, 4), (0, 4)))
        channel = entities["channel-1"]
        self.assertEqual(channel["start_region_id"], "region-1")
        self.assertEqual(channel["points"], ((2, 2), (4, 2), (7, 2), (9, 2)))
        self.assertEqual(result["business_map"]["revision"], 3)
        manual_frames = [f for f in result["frames"] if 2.8 <= f["time"] <= 2.9]
        self.assertTrue(manual_frames)
        self.assertTrue(all(f["modules"]["roboframe"]["control"] == "MANUAL" for f in manual_frames))
        self.assertTrue(all(f["modules"]["roboframe"]["control"] == "STOPPED" for f in result["frames"]
                            if f["modules"]["roboframe"]["revision"] == f["brain"]["directive"]["revision"]
                            and f["brain"]["directive"]["phase"] == "PREPARE"))

    def test_low_battery_during_object_commit_pauses_after_counting_once(self):
        for kind in ("region", "channel"):
            with self.subTest(kind=kind):
                self.setUp()
                self.start_region()
                if kind == "region":
                    self.feedback(Module.ROBOFRAME, State.RUNNING, signal="REGION_CLOSED")
                else:
                    self.close_region()
                    self.command("START_CHANNEL", channel_id="c1")
                    self.ready()
                    self.command("FINISH_CHANNEL")
                revision = self.brain.directive.revision
                self.brain.receive("event", {"event_id": "low", "type": "LOW_BATTERY"}, self.now)
                self.assertEqual(self.brain.directive.phase, Phase.COMMIT)
                self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
                self.feedback(Module.ROBOFRAME, State.SUCCEEDED, revision=revision)
                self.assertEqual(self.brain.directive.mode, "PAUSED")
                self.assertIsNone(self.brain.directive.mission)
                self.assertEqual(self.brain.mapping.regions, ["r1"])
                self.assertEqual(self.brain.mapping.channels, ["c1"] if kind == "channel" else [])
                self.assertEqual(self.command("RESUME")["command_result"]["state"], "REJECTED")
                self.brain.receive("event", {"event_id": "charged", "type": "BATTERY_OK"}, self.now)
                self.assertEqual(self.brain.directive.mode, "PAUSED")
                self.command("RESUME")
                self.assertEqual(self.brain.directive.phase, Phase.PREPARE)
                self.assertEqual(self.brain.directive.mission.type, "MANUAL_DRIVE")

    def test_mapping_result_and_history_snapshots_are_detached(self):
        self.start_region()
        self.close_region()
        self.brain.status()["mapping"]["last_result"]["result"] = "changed"
        self.assertEqual(self.brain.mapping.last_result["result"], "completed")
        self.command("FINISH_MAPPING")
        self.brain.receive("event", {"event_id": "low", "type": "LOW_BATTERY"}, self.now)
        self.feedback(Module.ROBOFRAME, State.SUCCEEDED)
        self.assertEqual(self.brain.directive.mode, "IDLE")
        self.brain.status()["last_task_result"]["regions"].clear()
        self.brain.view()["history"][-1]["regions"].clear()
        self.assertEqual(self.brain.history[-1]["regions"], ["r1"])

    def test_channel_origin_uses_polygon_not_bounding_box(self):
        world = BusinessMap("map", 1, "slam", "map", (
            Entity("r", "region", ((0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4))),))
        self.assertEqual(world.region_at(0.5, 3), "r")
        self.assertEqual(world.region_at(0, 0), "r")
        self.assertIsNone(world.region_at(3, 3))
        self.assertIsNone(world.region_at(8, 8))


if __name__ == "__main__":
    unittest.main()
