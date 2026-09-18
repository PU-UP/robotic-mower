"""Mapping session ownership, handover, closure, and channel-origin constraints."""
from pathlib import Path
import unittest

from brain import Brain
from contracts import Module, Phase, State, Status
from map_manager import BusinessMap, Entity
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
        self.command("SELECT_REGION_START", region_id="r1")
        self.ready()

    def close_region(self, module=Module.MAP_MANAGER):
        self.feedback(module, State.RUNNING, signal="REGION_CLOSED")
        self.assertEqual(self.brain.directive.phase, Phase.COMMIT)
        self.feedback(Module.MAP_MANAGER, State.SUCCEEDED)
        self.ready()

    def test_takeover_reuses_region_and_waits_for_fresh_module_readiness(self):
        self.start_region()
        self.command("START_EDGE_FOLLOW")
        self.ready()
        old_revision = self.brain.directive.revision
        result = self.command("TAKE_OVER")
        self.assertEqual(result["directive"]["mission"], {
            "type": "MAP_REGION", "map_id": "new", "region_id": "r1", "control": "MANUAL"})
        self.feedback(Module.MAP_MANAGER, State.RUNNING, revision=old_revision, signal="REGION_CLOSED")
        self.assertEqual(self.brain.directive.phase, Phase.PREPARE)
        self.feedback(Module.PERCEPTION)
        self.feedback(Module.MAP_MANAGER)
        self.assertEqual(self.brain.directive.phase, Phase.PREPARE)
        self.feedback(Module.PNC)
        self.assertEqual(self.brain.directive.phase, Phase.EXECUTE)
        self.command("START_EDGE_FOLLOW")
        self.ready()
        self.assertEqual(self.brain.directive.mission.region_id, "r1")
        self.assertEqual(self.brain.mapping.regions, [])

    def test_either_detector_can_close_but_only_map_commit_completes_region(self):
        for detector in (Module.PERCEPTION, Module.MAP_MANAGER):
            with self.subTest(detector=detector):
                self.setUp()
                self.start_region()
                revision = self.brain.directive.revision
                self.feedback(Module.PNC, State.SUCCEEDED, signal="REGION_CLOSED")
                self.assertEqual(self.brain.directive.phase, Phase.EXECUTE)
                self.feedback(detector, State.RUNNING, signal="REGION_CLOSED")
                self.assertEqual(self.brain.mapping.regions, [])
                self.feedback(Module.PERCEPTION, State.SUCCEEDED)
                self.assertEqual(self.brain.mapping.regions, [])
                self.feedback(Module.MAP_MANAGER, State.SUCCEEDED)
                self.feedback(detector, State.RUNNING, signal="REGION_CLOSED", revision=revision)
                self.assertEqual(self.brain.mapping.regions, ["r1"])
                self.assertEqual(self.brain.directive.mode, "MAPPING")
                self.assertEqual(self.brain.directive.mission.type, "MANUAL_DRIVE")

    def test_wrong_stage_commands_and_unrelated_closure_cannot_end_mapping(self):
        self.command("START_MAPPING", map_id="new")
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
        self.feedback(Module.PERCEPTION, State.RUNNING, signal="REGION_CLOSED")
        self.assertEqual(self.brain.directive.mission.type, "MAP_CHANNEL")
        self.assertEqual(self.brain.directive.phase, Phase.EXECUTE)

    def test_invalid_channel_start_returns_to_manual_without_recording_completion(self):
        self.start_region()
        self.close_region()
        self.command("START_CHANNEL", channel_id="c1")
        old_revision = self.brain.directive.revision
        self.feedback(Module.MAP_MANAGER, State.REJECTED, reason="CHANNEL_START_OUTSIDE_REGION")
        self.assertEqual(self.brain.directive.mission.type, "MANUAL_DRIVE")
        self.assertEqual(self.brain.mapping.channels, [])
        self.assertEqual(self.brain.mapping.last_result["result"], "rejected")
        self.feedback(Module.MAP_MANAGER, State.SUCCEEDED, revision=old_revision)
        self.ready()
        self.command("START_CHANNEL", channel_id="c1")
        self.ready()
        self.command("FINISH_CHANNEL")
        self.feedback(Module.MAP_MANAGER, State.SUCCEEDED)
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
        self.feedback(Module.PNC, State.SUCCEEDED)
        self.assertEqual(self.brain.directive.mode, "MAPPING")
        self.feedback(Module.MAP_MANAGER, State.SUCCEEDED)
        self.assertEqual(self.brain.directive.mode, "IDLE")
        self.assertEqual(self.brain.status()["last_task_result"]["regions"], ["r1"])

    def test_user_flow_records_takeover_but_excludes_transit_poses(self):
        result = run_script(Path(__file__).with_name("scenarios") / "mapping_session.json")
        self.assertTrue(all(c["passed"] for c in result["checks"]))
        entities = {e["entity_id"]: e for e in result["business_map"]["entities"]}
        self.assertEqual(set(entities), {"region-1", "region-2", "channel-1"})
        self.assertEqual(entities["region-1"]["points"], ((0, 0), (4, 0), (4, 4), (0, 4)))
        channel = entities["channel-1"]
        self.assertEqual(channel["start_region_id"], "region-1")
        self.assertEqual(channel["points"], ((2, 2), (4, 2), (7, 2), (9, 2)))
        self.assertEqual(result["business_map"]["revision"], 3)
        manual_frames = [f for f in result["frames"] if 1.6 <= f["time"] <= 1.7]
        self.assertTrue(manual_frames)
        self.assertTrue(all(f["modules"]["pnc"]["control"] == "MANUAL" for f in manual_frames))
        self.assertTrue(all(f["modules"]["pnc"]["control"] == "STOPPED" for f in result["frames"]
                            if f["modules"]["pnc"]["revision"] == f["brain"]["directive"]["revision"]
                            and f["brain"]["directive"]["phase"] == "PREPARE"))

    def test_channel_origin_uses_polygon_not_bounding_box(self):
        world = BusinessMap("map", 1, "slam", "map", (
            Entity("r", "region", ((0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4))),))
        self.assertEqual(world.region_at(0.5, 3), "r")
        self.assertEqual(world.region_at(0, 0), "r")
        self.assertIsNone(world.region_at(3, 3))
        self.assertIsNone(world.region_at(8, 8))


if __name__ == "__main__":
    unittest.main()
