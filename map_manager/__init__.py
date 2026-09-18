"""Business-map products, separate from perception's SLAM map."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    entity_id: str
    kind: str
    points: tuple[tuple[float, float], ...]
    start_region_id: str | None = None


@dataclass(frozen=True)
class BusinessMap:
    map_id: str
    revision: int
    slam_map_id: str
    frame_id: str
    entities: tuple[Entity, ...]

    def find(self, entity_id):
        return next((entity for entity in self.entities if entity.entity_id == entity_id), None)

    def region_at(self, x, y):
        """Point-in-polygon for simple business regions; boundary counts as inside."""
        for entity in self.entities:
            if entity.kind != "region" or len(entity.points) < 3:
                continue
            inside = False
            for (ax, ay), (bx, by) in zip(entity.points, entity.points[1:] + entity.points[:1]):
                cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
                if abs(cross) < 1e-9 and min(ax, bx) <= x <= max(ax, bx) and min(ay, by) <= y <= max(ay, by):
                    return entity.entity_id
                if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                    inside = not inside
            if inside:
                return entity.entity_id
        return None
