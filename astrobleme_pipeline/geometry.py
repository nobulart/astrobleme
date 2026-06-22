from __future__ import annotations

import math
from typing import Any

from pyproj import Geod
from shapely.geometry import shape

GEOD = Geod(ellps="WGS84")


def great_circle_distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return abs(GEOD.inv(float(lon1), float(lat1), float(lon2), float(lat2))[2]) / 1000.0


def radius_diameter(radius_km: Any = None, diameter_km: Any = None) -> tuple[float, float]:
    radius = _finite(radius_km)
    diameter = _finite(diameter_km)
    if radius is None and diameter is None:
        return math.nan, math.nan
    if radius is None:
        radius = diameter / 2.0
    if diameter is None:
        diameter = radius * 2.0
    return float(radius), float(diameter)


def geometry_center(geometry: dict[str, Any] | None) -> tuple[float, float]:
    if not geometry:
        return math.nan, math.nan
    point = shape(geometry).centroid
    return float(point.x), float(point.y)


def geometry_radius_km(geometry: dict[str, Any] | None, lon: float | None = None,
                       lat: float | None = None) -> float:
    """Maximum geodesic distance from a geometry centroid to its vertices."""
    if not geometry:
        return math.nan
    if lon is None or lat is None:
        lon, lat = geometry_center(geometry)
    distances = [great_circle_distance_km(lon, lat, x, y) for x, y in _coordinate_pairs(geometry.get("coordinates"))]
    return max(distances) if distances else math.nan


def _coordinate_pairs(value: Any):
    if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        yield float(value[0]), float(value[1])
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _coordinate_pairs(item)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None
