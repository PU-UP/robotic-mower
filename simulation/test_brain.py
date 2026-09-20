"""Business invariants, delayed messages, and independent task acceptance."""
from dataclasses import fields, replace
import unittest

from brain import Brain
from contracts import Event, EventKind, Mission, MissionKind, Module, Mode, Phase, State, Status, WorkItem
from simulation.run import SCENARIOS, Simulation, mowing, run_scenario


class BrainTests(unittest.TestCase):
    def start(self, mission=None):
        brain = Brain()
        brain.handle(Event("start", EventKind.START, mission or mowing()), 0)
        return brain

    def ready(self, brain, now=0.1):
        revision = brain.directive.revision
        for module in Module:
            brain.handle(Status(module, revision, 1, now, State.READY), now)

    def test_all_three_ready_before_execution(self):
        brain = self.start()
        for module in (Module.PERCEPTION, Module.PNC):
            brain.handle(Status(module, 1, 1, 0, State.READY), 0)
        self.assertEqual(brain.directive.phase, Phase.PREPARE)
        brain.handle(Status(Module.MAP_MANAGER, 1, 1, 0, State.READY), 0)
        self.assertEqual(brain.directive.phase, Phase.EXECUTE)
        self.assertEqual(brain.directive.mission.target_id, "region-1")
        self.assertNotIn("targets", {field.name for field in fields(WorkItem)})

    def test_old_completion_cannot_advance_paused_or_new_work(self):
        brain = self.start()
        self.ready(brain)
        old = Status(Module.PNC, brain.directive.revision, 2, 0.2, State.SUCCEEDED)
        brain.handle(Event("pause", EventKind.PAUSE), 0.2)
        brain.handle(old, 0.3)
        self.assertEqual(brain.task.cursor, 0)
        brain.handle(Event("resume", EventKind.RESUME), 0.4)
        self.ready(brain, 0.5)
        brain.handle(old, 0.6)
        self.assertEqual(brain.task.cursor, 0)

    def test_completion_is_counted_once_and_only_by_owner(self):
        brain = self.start()
        self.ready(brain)
        revision = brain.directive.revision
        brain.handle(Status(Module.MAP_MANAGER, revision, 2, 0.2, State.SUCCEEDED), 0.2)
        self.assertEqual(brain.task.cursor, 0)
        done = Status(Module.PNC, revision, 2, 0.2, State.SUCCEEDED)
        brain.handle(done, 0.2)
        brain.handle(done, 0.3)
        self.assertEqual(brain.task.cursor, 1)
        self.assertEqual(brain.directive.mission.target_id, "region-2")

    def test_duplicate_and_conflicting_event_ids(self):
        brain = Brain()
        start = Event("same", EventKind.START, mowing())
        brain.handle(start, 0)
        brain.handle(start, 0.1)
        self.assertEqual(brain.directive.revision, 1)
        brain.handle(Event("same", EventKind.CANCEL), 0.2)
        self.assertFalse(brain.last_result["accepted"])
        self.assertIsNotNone(brain.task)

    def test_illegal_events_do_not_mutate_task(self):
        for kind in (EventKind.RESUME, EventKind.FINISH_MAPPING, EventKind.RESET):
            with self.subTest(kind=kind):
                brain = self.start()
                before = brain.directive
                brain.handle(Event("bad", kind), 0)
                self.assertFalse(brain.last_result["accepted"])
                self.assertEqual(before, brain.directive)

    def test_status_sequence_stamp_and_revision_reject_old_feedback(self):
        brain = self.start()
        status = Status(Module.PERCEPTION, 1, 4, 0.2, State.READY)
        brain.handle(status, 0.2)
        for bad in (replace(status, sequence=3, state=State.FAILED),
                    replace(status, revision=0, sequence=5, state=State.FAILED),
                    replace(status, stamp=5, sequence=5, state=State.FAILED),
                    replace(status, stamp=0.1, sequence=5, state=State.FAILED)):
            brain.handle(bad, 0.3)
        self.assertEqual(brain.statuses[Module.PERCEPTION], status)

    def test_dead_peer_prevents_execution_when_final_ack_arrives(self):
        brain = self.start()
        for module in (Module.PERCEPTION, Module.MAP_MANAGER):
            brain.handle(Status(module, 1, 1, 0, State.READY), 0)
        brain.handle(Status(Module.PNC, 1, 1, 1.1, State.READY), 1.1)
        self.assertEqual(brain.directive.mode, Mode.ERROR)

    def test_fault_is_latched_and_recovery_requires_readiness(self):
        brain = self.start()
        self.ready(brain)
        brain.handle(Status(Module.PERCEPTION, 2, 2, 0.2, State.FAILED, "lost"), 0.2)
        self.assertEqual(brain.directive.mode, Mode.ERROR)
        brain.handle(Event("resume", EventKind.RESUME), 0.3)
        self.assertFalse(brain.last_result["accepted"])
        brain.handle(Event("reset", EventKind.RESET), 0.4)
        self.assertEqual(brain.directive.mode, Mode.PAUSED)
        brain.handle(Event("resume2", EventKind.RESUME), 0.5)
        self.assertEqual(brain.directive.phase, Phase.PREPARE)

    def test_stale_message_does_not_extend_deadline(self):
        brain = self.start()
        brain.handle(Status(Module.PERCEPTION, 1, 1, 0, State.READY), 0.9)
        brain.tick(1.01)
        self.assertEqual(brain.directive.mode, Mode.ERROR)
        self.assertIn("timeout", brain.reason)

    def test_repeated_low_battery_preserves_original_task(self):
        brain = self.start()
        brain.handle(Event("low1", EventKind.LOW_BATTERY), 0.1)
        saved = brain.suspended
        brain.handle(Event("low2", EventKind.LOW_BATTERY), 0.2)
        self.assertIs(brain.suspended, saved)
        self.assertEqual(brain.task.mission.kind, MissionKind.RETURN_HOME)
        brain.handle(Event("cancel", EventKind.CANCEL), 0.3)
        self.assertIsNone(brain.task)
        self.assertIsNone(brain.suspended)
        brain.handle(Event("new", EventKind.START, mowing("new")), 0.4)
        self.assertFalse(brain.last_result["accepted"])

    def test_pnc_recreation_has_no_history_dependency(self):
        from simulation.doubles import AlgorithmDouble
        sim = Simulation()
        sim.inject(Event("start", EventKind.START, mowing()))
        sim.until(1.25)
        sim.inject(Event("pause", EventKind.PAUSE))
        sim.until(1.5)
        self.assertEqual(sim.brain.task.cursor, 1)
        sim.modules[Module.PNC] = AlgorithmDouble(Module.PNC)
        sim.inject(Event("resume", EventKind.RESUME))
        sim.until(3)
        self.assertEqual(sim.brain.directive.mode, Mode.IDLE)
        self.assertIn({"mission_id": "mow-1", "result": "completed"}, sim.brain.history)

    def test_map_identity_and_alignment_gate_current_planning(self):
        from perception import Observation
        from pnc import PlanningInput
        from simulation.doubles import garden
        brain = self.start()
        world = garden()
        obs = Observation(0, "slam-garden", "map", 0, 0, True)
        inputs = PlanningInput(brain.directive.mission, obs, world)
        self.assertTrue(inputs.ready(0.2))
        self.assertFalse(inputs.ready(1))
        self.assertFalse(replace(inputs, observation=replace(obs, slam_map_id="other")).ready(0))
        self.assertFalse(replace(inputs, business_map=replace(world, map_id="other")).ready(0))

    def test_invalid_contracts_fail_at_boundary(self):
        with self.assertRaises(ValueError):
            mowing(" ")
        with self.assertRaises(ValueError):
            Mission("id", MissionKind.MOW, "garden", ("a", "a"))
        with self.assertRaises(ValueError):
            Event("bad", EventKind.PAUSE, "unexpected")
        with self.assertRaises(TypeError):
            Brain().handle({"geometry": []}, 0)


class ScenarioTests(unittest.TestCase):
    def test_replay_snapshots_capture_each_decision_without_future_state(self):
        sim = Simulation()
        sim.receive("command", {"command_id": "mapping", "type": "START_MAPPING",
                                "params": {"map_id": "new"}})
        delivery, directive, acknowledgement = sim.events
        self.assertEqual(delivery["brain_before"]["directive"]["mode"], "IDLE")
        self.assertEqual(delivery["brain_after"]["directive"]["mode"], "MAPPING")
        self.assertEqual(directive["brain_after"]["directive"], directive["payload"])
        self.assertEqual(acknowledgement["brain_after"], delivery["brain_after"])
        sim.receive("command", {"command_id": "pause", "type": "PAUSE"})
        self.assertEqual(sim.events[-1]["brain_after"]["directive"]["mode"], "PAUSED")
        self.assertEqual(delivery["brain_after"]["directive"]["mode"], "MAPPING")
        delivery["brain_after"]["public_status"]["mapping"]["regions"].append("changed")
        self.assertEqual(directive["brain_after"]["public_status"]["mapping"]["regions"], [])
        self.assertEqual(sim.brain.mapping.regions, [])

    def test_independent_scenarios_are_reproducible_and_pass_acceptance(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                first, second = run_scenario(name), run_scenario(name)
                self.assertEqual(first, second)
                self.assertTrue(all(c["passed"] for c in first["checks"]), first["checks"])


if __name__ == "__main__":
    unittest.main()
