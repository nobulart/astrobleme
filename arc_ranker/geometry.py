from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from shapely.geometry import MultiLineString


EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class Candidate:
    index: int
    candidate_id: str
    name: str
    lon: float
    lat: float
    radius_km: float
    diameter_km: float
    relative_radial_mad: float
    angular_coverage: float
    geometry: MultiLineString


def flatten_lines(feature: dict) -> list[list[list[float]]]:
    geometry = feature["geometry"]
    if geometry["type"] == "LineString":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiLineString":
        return geometry["coordinates"]
    raise ValueError(f"Unsupported arc geometry: {geometry['type']}")


def lonlat_to_xyz(points: np.ndarray) -> np.ndarray:
    lon = np.deg2rad(points[:, 0])
    lat = np.deg2rad(points[:, 1])
    return np.column_stack(
        (np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat))
    )


def spherical_candidate(feature: dict, index: int) -> Candidate:
    lines = flatten_lines(feature)
    points = np.asarray([p for line in lines for p in line], dtype=float)
    xyz = lonlat_to_xyz(points)
    centre = xyz.mean(axis=0)
    centre /= np.linalg.norm(centre)
    lon = math.degrees(math.atan2(centre[1], centre[0]))
    lat = math.degrees(math.asin(centre[2]))
    radial = np.arccos(np.clip(xyz @ centre, -1.0, 1.0)) * EARTH_RADIUS_KM
    radius = float(np.median(radial))
    mad = float(np.median(np.abs(radial - radius))) / max(radius, 1e-9)

    # Angular coverage uses bearings of observed vertices around the fitted centre.
    x = np.deg2rad(((points[:, 0] - lon + 180) % 360) - 180) * math.cos(math.radians(lat))
    y = np.deg2rad(points[:, 1] - lat)
    bearings = np.mod(np.arctan2(x, y), 2 * np.pi)
    occupied = np.unique(np.floor(bearings / (2 * np.pi) * 72).astype(int))
    coverage = min(1.0, len(occupied) / 72.0)

    adjusted_lines = []
    for line in lines:
        adjusted = []
        for point_lon, point_lat, *rest in line:
            shifted_lon = point_lon + 360.0 * round((lon - point_lon) / 360.0)
            adjusted.append((shifted_lon, point_lat))
        if len(adjusted) >= 2:
            adjusted_lines.append(adjusted)
    geometry = MultiLineString(adjusted_lines)
    name = feature.get("properties", {}).get("Name") or f"arc_{index:04d}"
    return Candidate(
        index=index,
        candidate_id=f"arc_{index:04d}",
        name=str(name),
        lon=lon,
        lat=lat,
        radius_km=radius,
        diameter_km=2.0 * radius,
        relative_radial_mad=mad,
        angular_coverage=coverage,
        geometry=geometry,
    )


def local_xy_km(lon: np.ndarray, lat: np.ndarray, centre_lon: float, centre_lat: float):
    dlon = np.deg2rad(((lon - centre_lon + 180.0) % 360.0) - 180.0)
    dlat = np.deg2rad(lat - centre_lat)
    x = EARTH_RADIUS_KM * dlon * math.cos(math.radians(centre_lat))
    y = EARTH_RADIUS_KM * dlat
    return x, y
