"""Current planning inputs. No business history or next-task selection."""
from dataclasses import dataclass

from contracts import WorkItem
from map_manager import BusinessMap
from perception import Observation


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
                and world.find(m.target_id) is not None)
