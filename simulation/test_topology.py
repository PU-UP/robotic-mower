"""Dock departure, return-channel capture and connected region transfers."""
from dataclasses import replace
from pathlib import Path
import math
import unittest

from contracts import Directive, MissionType, Module, Mode, Phase, Control, State, WorkItem
from simulation.world import BusinessMap, Entity, UNDOCK_DISTANCE
from simulation.planning import PlanningInput
from simulation.doubles import RoboframeDouble, DOCK_POSITION, DOCK_EXIT, garden
from simulation.run import Simulation, run_scenario
from simulation.scripted import run_script


class TopologyTests(unittest.TestCase):
    def test_fixture_routes_use_both_channel_kinds_in_both_directions(self):
        world = garden()
        self.assertIsNone(world.topology_error())
        outward = world.route(DOCK_POSITION, "region-2")
        self.assertEqual(outward, (DOCK_POSITION, DOCK_EXIT, (0, 0), (2, 2), (4, 2), (7, 2), (9, 2)))
        homeward = world.route((9, 2), "dock")
        self.assertEqual(homeward, tuple(reversed(outward)))
        self.assertIsNotNone(world.route((6, 2), "dock"))
        self.assertIsNone(world.route((6, 9), "dock"))

    def test_invalid_topologies_cannot_be_used_for_planning(self):
        world = garden()
        variants = {
            "RETURN_CHANNEL_REQUIRED": tuple(e for e in world.entities if e.kind != "return_channel"),
            "CHANNEL_NOT_CONNECTED": tuple(replace(e, points=((2, 2), (3, 3)), end_region_id="region-1")
                if e.kind == "channel" else e for e in world.entities),
            "REGION_NOT_REACHABLE": world.entities + (Entity("isolated", "region", ((20, 0), (24, 0), (24, 4), (20, 4))),),
            "RETURN_CHANNEL_NOT_CONNECTED": tuple(replace(e, exit_point=(-2.5, 0))
                if e.kind == "charging_station" else e for e in world.entities),
        }
        observation = RoboframeDouble().observe(0, DOCK_POSITION)
        action = WorkItem(MissionType.MOW_REGION, "garden", "region-2", Control.AUTO)
        for error, entities in variants.items():
            with self.subTest(error=error):
                invalid = replace(world, entities=entities)
                self.assertEqual(invalid.topology_error(), error)
                self.assertFalse(PlanningInput(action, observation, invalid).ready(0))
        wrong_direction = replace(world, entities=tuple(replace(e, heading=0)
            if e.kind == "charging_station" else e for e in world.entities))
        self.assertEqual(wrong_direction.topology_error(), "RETURN_CHANNEL_NOT_CONNECTED")

    def test_draft_channel_resolves_only_after_far_region_exists(self):
        world = garden()
        draft = replace(world, entities=tuple(e for e in world.entities if e.entity_id != "region-2")).connect_channels()
        self.assertIsNone(draft.find("channel-1").end_region_id)
        self.assertEqual(draft.topology_error(), "CHANNEL_NOT_CONNECTED")
        finished = replace(draft, entities=draft.entities + (world.find("region-2"),)).connect_channels()
        self.assertEqual(finished.find("channel-1").end_region_id, "region-2")
        self.assertIsNone(finished.topology_error())

    def test_first_mapping_requires_dock_then_measured_reverse_distance(self):
        sim = Simulation(mapped=False)
        sim.receive("command", {"command_id": "map", "type": "START_MAPPING", "params": {"map_id": "new"}})
        sim.until(0.7)
        self.assertEqual(sim.brain.directive.mission.type, MissionType.UNDOCK)
        self.assertLess(math.dist(DOCK_POSITION, sim.position), UNDOCK_DISTANCE)
        self.assertEqual(sim.receive("command", {"command_id": "early", "type": "SELECT_REGION_START",
            "params": {"region_id": "r1"}})["command_result"]["state"], "REJECTED")
        sim.until(1.4)
        self.assertEqual(sim.brain.directive.mission.type, MissionType.MAP_RETURN_CHANNEL)
        self.assertAlmostEqual(math.dist(DOCK_POSITION, sim.position), 1.5)
        self.assertAlmostEqual(math.dist(DOCK_EXIT, sim.position), 0)
        self.assertEqual(sim.brain.mapping.regions, [])
        bad = Simulation(mapped=False)
        bad.position = (5, 5)
        bad.receive("command", {"command_id": "map", "type": "START_MAPPING", "params": {"map_id": "new"}})
        bad.until(0.3)
        self.assertEqual(bad.brain.directive.mode, Mode.ERROR)
        self.assertIn("MAPPING_MUST_START_AT_DOCK", bad.brain.reason)

    def test_complete_mapping_shares_first_start_and_connects_far_end(self):
        result = run_scenario("mapping")
        self.assertTrue(all(c["passed"] for c in result["checks"]))
        entities = {e["entity_id"]: e for e in result["business_map"]["entities"]}
        returned = entities["return-channel"]
        self.assertEqual(returned["points"], (DOCK_EXIT, (-1, 0), (0, 0)))
        self.assertEqual(returned["points"][-1], entities["region-1"]["points"][0])
        self.assertEqual(returned["station_id"], "dock")
        self.assertEqual(returned["end_region_id"], "region-1")
        channel = entities["channel-1"]
        self.assertEqual((channel["start_region_id"], channel["end_region_id"]), ("region-1", "region-2"))
        mapped = result["business_map"]
        world = BusinessMap(mapped["map_id"], mapped["revision"], mapped["slam_map_id"], mapped["frame_id"],
                            tuple(Entity(**e) for e in mapped["entities"]))
        self.assertIsNone(world.topology_error())
        self.assertEqual(world.region_at(*channel["points"][-1]), "region-2")

    def test_disconnected_mapping_cannot_be_saved_and_keeps_editable_session(self):
        result = run_script(Path(__file__).with_name("scenarios") / "mapping_disconnected.json")
        self.assertTrue(all(c["passed"] for c in result["checks"]), result["checks"])
        self.assertIsNone(result["business_map"])
        self.assertEqual(result["final"]["directive"]["mode"], "MAPPING")
        self.assertIsNotNone(result["final"]["public_status"]["mapping"])

    def test_work_and_return_replay_move_through_connected_channels(self):
        for scenario in ("mowing", "return_home", "low_battery", "pause_resume"):
            with self.subTest(scenario=scenario):
                result = run_scenario(scenario)
                self.assertTrue(all(c["passed"] for c in result["checks"]))
                routes = [f["modules"]["roboframe"]["route"] for f in result["frames"] if f["modules"]["roboframe"]["route"]]
                self.assertTrue(any((7, 2) in route for route in routes))
                self.assertTrue(any(DOCK_EXIT in route for route in routes))


if __name__ == "__main__":
    unittest.main()
