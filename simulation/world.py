"""Simulation map geometry; no product service or reliable storage."""
from dataclasses import dataclass, replace
from collections import deque
import math

UNDOCK_DISTANCE = 1.5


@dataclass(frozen=True)
class Entity:
    entity_id: str
    kind: str
    points: tuple[tuple[float, float], ...]
    start_region_id: str | None = None
    end_region_id: str | None = None
    station_id: str | None = None
    exit_point: tuple[float, float] | None = None
    heading: float | None = None


@dataclass(frozen=True)
class BusinessMap:
    map_id: str
    revision: int
    slam_map_id: str
    frame_id: str
    entities: tuple[Entity, ...]

    def find(self, entity_id):
        return next((entity for entity in self.entities if entity.entity_id == entity_id), None)

    def region_at(self, x, y, exclude=None):
        """Point-in-polygon for simple business regions; boundary counts as inside."""
        for entity in self.entities:
            if entity.kind != "region" or len(entity.points) < 3 or entity.entity_id == exclude:
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

    def connect_channels(self):
        """Resolve endpoints only when region polygons exist; drafts may remain pending."""
        entities = []
        for entity in self.entities:
            if entity.kind in ("channel", "return_channel") and entity.points:
                start = self.region_at(*entity.points[0]) if entity.kind == "channel" else None
                end = self.region_at(*entity.points[-1], exclude=start)
                entity = replace(entity, start_region_id=start, end_region_id=end)
            entities.append(entity)
        return replace(self, entities=tuple(entities))

    def topology_error(self):
        ids = [e.entity_id for e in self.entities]
        if len(set(ids)) != len(ids):
            return "DUPLICATE_MAP_ID"
        regions = [e for e in self.entities if e.kind == "region"]
        docks = [e for e in self.entities if e.kind == "charging_station"]
        returns = [e for e in self.entities if e.kind == "return_channel"]
        if not regions or len(docks) != 1 or len(returns) != 1:
            return "RETURN_CHANNEL_REQUIRED"
        dock, channel = docks[0], returns[0]
        if (not dock.points or dock.exit_point is None or dock.heading is None or not math.isfinite(dock.heading) or not math.isclose(
                math.dist(dock.points[0], dock.exit_point), UNDOCK_DISTANCE, abs_tol=1e-6)
                or math.dist(dock.exit_point, (dock.points[0][0] - UNDOCK_DISTANCE*math.cos(dock.heading),
                                             dock.points[0][1] - UNDOCK_DISTANCE*math.sin(dock.heading))) > 1e-6
                or len(channel.points) < 2 or channel.station_id != dock.entity_id
                or math.dist(channel.points[0], dock.exit_point) > 1e-6
                or channel.end_region_id != regions[0].entity_id
                or self.region_at(*channel.points[-1]) != regions[0].entity_id):
            return "RETURN_CHANNEL_NOT_CONNECTED"
        for entity in self.entities:
            if entity.kind != "channel":
                continue
            if (len(entity.points) < 2 or not entity.start_region_id or not entity.end_region_id
                    or entity.start_region_id == entity.end_region_id
                    or self.region_at(*entity.points[0]) != entity.start_region_id
                    or self.region_at(*entity.points[-1], exclude=entity.start_region_id) != entity.end_region_id):
                return "CHANNEL_NOT_CONNECTED"
        if any(self.edge_path(dock.entity_id, r.entity_id) is None for r in regions):
            return "REGION_NOT_REACHABLE"
        return None

    def edge_path(self, start, target):
        queue = deque([(start, [])])
        seen = {start}
        while queue:
            node, path = queue.popleft()
            if node == target:
                return path
            for e in self.entities:
                if e.kind not in ("channel", "return_channel"):
                    continue
                a, b = e.station_id or e.start_region_id, e.end_region_id
                if not a or not b:
                    continue
                other = b if node == a else a if node == b else None
                if other and other not in seen:
                    seen.add(other)
                    queue.append((other, path + [(e, node == a)]))
        return None

    def route(self, point, target):
        """A schematic channel route; in-region geometry belongs to real roboframe planners."""
        if self.topology_error():
            return None
        start = self.region_at(*point)
        if start is None:
            start = next((e.entity_id for e in self.entities if e.kind == "charging_station"
                          and math.dist(point, e.points[0]) <= 0.15), None)
        if start is None:
            # A restart on a channel must rejoin that channel, not cut across the map.
            for e in self.entities:
                if e.kind not in ("channel", "return_channel"):
                    continue
                points = e.points
                if e.station_id:
                    points = self.find(e.station_id).points + points
                for i, (a, b) in enumerate(zip(points, points[1:])):
                    length = math.dist(a, b)
                    if length and abs(math.dist(a, point) + math.dist(point, b) - length) < 1e-6:
                        rest = self.edge_path(e.end_region_id, target)
                        if rest is not None:
                            return self._route_points([point, *points[i+1:]], rest)
            return None
        path = self.edge_path(start, target)
        return None if path is None else self._route_points([point], path)

    def _route_points(self, points, path):
        for edge, forward in path:
            segment = edge.points
            if edge.station_id:
                segment = self.find(edge.station_id).points + segment
            for point in segment if forward else reversed(segment):
                if point != points[-1]:
                    points.append(point)
        return tuple(points)
