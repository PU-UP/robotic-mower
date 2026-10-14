"""Boundary checks for the runtime substitute, not real algorithm validation."""
from copy import deepcopy
import unittest

from contracts import Mode
from simulation.run import Simulation


class RuntimeTests(unittest.TestCase):
    def command(self, sim, kind, command_id, **params):
        return sim.receive("command", {"command_id": command_id, "type": kind, "params": params})

    def start(self, *, automatic_devices=True, task_id="work"):
        sim = Simulation(automatic_devices=automatic_devices)
        self.command(sim, "START_MOWING", task_id, map_id="garden", region_ids=["region-1"])
        return sim

    def test_unknown_blade_feedback_does_not_create_coverage(self):
        sim = self.start(automatic_devices=False)
        sim.until(2)
        self.assertTrue(sim.runtime.blade_requested)
        self.assertEqual(sim.runtime.blade_state, "UNKNOWN")
        self.assertEqual(sim.runtime.coverage, {})
        self.assertEqual(sim.brain.directive.mode, Mode.WORKING)
        sim.runtime.blade_state = "RUNNING"
        sim.until(4)
        self.assertTrue(sim.runtime.coverage)
        self.assertEqual(sim.brain.directive.mode, Mode.WORKING)  # Stop still unconfirmed.
        sim.runtime.blade_state = "STOPPED"
        sim.until(4.3)
        self.assertEqual(sim.brain.directive.mode, Mode.IDLE)

    def test_motion_without_confirmed_cutting_does_not_count(self):
        sim = self.start(automatic_devices=False)
        sim.until(1.2)
        _, start, end = sim.runtime.remaining()[0]
        sim.position = start
        sim.until(1.4)
        sim.position = end
        sim.until(1.6)
        self.assertEqual(sim.runtime.coverage, {})
        # A newly received RUNNING value cannot retrospectively confirm that movement.
        sim.runtime.blade_state = "RUNNING"
        sim.until(1.7)
        self.assertEqual(sim.runtime.coverage, {})

    def test_arrival_is_not_charging_confirmation(self):
        sim = Simulation(automatic_devices=False)
        sim.position = (9, 2)
        self.command(sim, "RETURN_HOME", "home", map_id="garden", station_id="dock")
        sim.until(2)
        self.assertEqual(sim.runtime.stage, "DOCK")
        self.assertIsNone(sim.runtime.charging)
        self.assertEqual(sim.brain.directive.mode, Mode.RETURNING)
        sim.runtime.charging = False
        sim.until(2.2)
        self.assertEqual(sim.brain.directive.mode, Mode.RETURNING)
        sim.runtime.charging = True
        sim.until(2.4)
        self.assertEqual(sim.brain.directive.mode, Mode.CHARGING)

    def test_device_charging_outlives_the_return_execution(self):
        sim = Simulation()
        sim.position = (9, 2)
        self.command(sim, "RETURN_HOME", "home", map_id="garden", station_id="dock")
        sim.until(2)
        self.assertEqual(sim.brain.directive.mode, Mode.CHARGING)
        self.assertTrue(sim.runtime.charging)
        # Ending the business wait does not disconnect the physical charger.
        sim.receive("event", {"event_id": "charged", "type": "BATTERY_OK"})
        sim.until(2.3)
        self.assertEqual(sim.brain.directive.mode, Mode.IDLE)
        self.assertTrue(sim.runtime.charging)
        self.command(sim, "START_MOWING", "work", map_id="garden", region_ids=["region-1"])
        sim.until(2.8)
        self.assertFalse(sim.runtime.charging)

    def test_wrong_target_kind_is_rejected_without_crashing(self):
        sim = Simulation()
        self.command(sim, "START_MOWING", "bad", map_id="garden", region_ids=["dock"])
        sim.until(.4)
        self.assertEqual(sim.brain.directive.mode, Mode.ERROR)
        self.assertIn("TARGET_KIND_INVALID", sim.brain.reason)

    def test_blade_failure_does_not_complete_region(self):
        sim = self.start(automatic_devices=False)
        sim.until(1.2)
        sim.runtime.blade_state = "FAILED"
        sim.until(1.5)
        self.assertEqual(sim.brain.directive.mode, Mode.ERROR)
        self.assertEqual(sim.brain.task.cursor, 0)
        self.assertEqual(sim.runtime.coverage, {})
        self.assertFalse(sim.runtime.blade_requested)

    def test_pause_does_not_fabricate_a_blade_stop_confirmation(self):
        for feedback in ("UNKNOWN", "RUNNING"):
            with self.subTest(feedback=feedback):
                sim = self.start(automatic_devices=False)
                sim.until(1.2)
                sim.runtime.blade_state = feedback
                self.command(sim, "PAUSE", "pause")
                sim.until(1.5)
                self.assertEqual(sim.runtime.state, "STOPPED")
                self.assertFalse(sim.runtime.blade_requested)
                self.assertEqual(sim.runtime.blade_state, feedback)
                self.assertEqual(sim.runtime.coverage, {})

    def test_charge_resume_keeps_original_spatial_records(self):
        sim = self.start()
        sim.until(1.55)
        saved = deepcopy(sim.runtime.coverage)
        self.assertTrue(saved)
        sim.receive("event", {"event_id": "low", "type": "LOW_BATTERY"})
        sim.until(3)
        self.assertEqual(sim.brain.directive.mode, Mode.CHARGING)
        self.assertEqual(sim.runtime.coverage, saved)
        sim.receive("event", {"event_id": "charged", "type": "BATTERY_OK"})
        self.assertEqual(sim.brain.directive.mode, Mode.PAUSED)
        self.command(sim, "RESUME", "resume")
        self.assertEqual(sim.brain.directive.task_id, "work")
        sim.until(6)
        self.assertEqual(sim.brain.directive.mode, Mode.IDLE)
        for key, segments in saved.items():
            self.assertEqual(sim.runtime.coverage[key][:len(segments)], segments)
            self.assertEqual(len(sim.runtime.coverage[key]), len(set(sim.runtime.coverage[key])))

    def test_new_task_does_not_inherit_coverage_or_modify_environment_map(self):
        sim = self.start()
        world = sim.runtime.business_map
        sim.until(3)
        self.assertEqual(sim.brain.directive.mode, Mode.IDLE)
        old = deepcopy(sim.runtime.coverage)
        self.command(sim, "START_MOWING", "new", map_id="garden", region_ids=["region-1"])
        sim.until(3.2)
        self.assertEqual(len(sim.runtime.remaining()), 6)
        self.assertEqual(sim.runtime.coverage, old)
        self.assertEqual(sim.runtime.business_map, world)
        self.assertIsNotNone(world.route((0, 0), "region-1"))
        sim.until(6)
        self.assertEqual(sim.brain.directive.mode, Mode.IDLE)
        self.assertEqual(len(sim.runtime.coverage[("new", "garden", "region-1")]), 6)


if __name__ == "__main__":
    unittest.main()
