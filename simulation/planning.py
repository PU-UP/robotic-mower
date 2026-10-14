"""Current planning inputs. No business history or next-task selection."""
from dataclasses import dataclass

from contracts import WorkItem
from simulation.world import BusinessMap
from simulation.observation import Observation


@dataclass(frozen=True)
class PlanningInput:
    mission: WorkItem
    observation: Observation
    business_map: BusinessMap

    def ready(self, now, max_age=0.5):
        m, p, world = self.mission, self.observation, self.business_map
        return (p.localized and 0 <= now - p.stamp <= max_age
                and m.map_id == world.map_id
                and (p.slam_map_id, p.frame_id) == (world.slam_map_id, world.frame_id)
                and world.find(m.target_id) is not None
                and world.route((p.x, p.y), m.target_id) is not None)

    def route(self, now):
        return self.business_map.route((self.observation.x, self.observation.y), self.mission.target_id) if self.ready(now) else None
