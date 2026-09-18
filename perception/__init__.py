"""Perception data plane. SLAM maps remain internal to this module."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    stamp: float
    slam_map_id: str
    frame_id: str
    x: float
    y: float
    localized: bool
    obstacles: tuple[tuple[float, float], ...] = ()
