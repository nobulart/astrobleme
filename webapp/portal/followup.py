"""Exact candidate follow-up scoring from the study pipeline."""

from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

from django.conf import settings

METHOD_VERSION = "paper-2026-topography-geology-v1"


def circle_geometry(longitude: float, latitude: float, diameter_km: float, vertices: int = 72) -> dict:
    radius = diameter_km / 2.0
    angular = radius / 6371.0088
    lat1, lon1 = math.radians(latitude), math.radians(longitude)
    coordinates = []
    for index in range(vertices + 1):
        bearing = 2 * math.pi * index / vertices
        lat2 = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(bearing))
        lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(angular) * math.cos(lat1), math.cos(angular) - math.sin(lat1) * math.sin(lat2))
        coordinates.append([((math.degrees(lon2) + 180) % 360) - 180, math.degrees(lat2)])
    return {"type": "LineString", "coordinates": coordinates}


def _pipeline_imports():
    root = str(Path(settings.PROJECT_ROOT))
    if root not in sys.path:
        sys.path.insert(0, root)
    from arc_ranker.diagnostics import save_elevation_analysis_figure
    from arc_ranker.filters import score_terrain
    from arc_ranker.gebco import GEBCOGrid
    from arc_ranker.geology import GeologyIndex
    from arc_ranker.geometry import spherical_candidate
    return save_elevation_analysis_figure, score_terrain, GEBCOGrid, GeologyIndex, spherical_candidate


@lru_cache(maxsize=2)
def _geology_index(path: str):
    _, _, _, GeologyIndex, _ = _pipeline_imports()
    return GeologyIndex(path)


def score_candidate(candidate, diagnostic_path: str | Path | None = None, include_geophysics: bool = False) -> dict:
    """Return the paper's no-imagery follow-up score and component metrics."""
    grid_path = Path(settings.GEBCO_GRID_PATH)
    geology_path = Path(settings.GEOLOGY_INDEX_PATH)
    if not grid_path.is_file():
        raise FileNotFoundError("GEBCO numerical grid is not mounted")
    if not geology_path.is_file():
        raise FileNotFoundError("geological province index is not mounted")

    geometry = candidate.geometry or circle_geometry(candidate.longitude, candidate.latitude, candidate.diameter_km)
    if geometry.get("type") == "Polygon":
        geometry = {"type": "LineString", "coordinates": geometry["coordinates"][0]}
    feature = {"type": "Feature", "properties": {"Name": candidate.title}, "geometry": geometry}
    save_elevation_analysis_figure, score_terrain, GEBCOGrid, _, spherical_candidate = _pipeline_imports()
    fitted = spherical_candidate(feature, 0)
    with GEBCOGrid(grid_path) as grid:
        terrain, diagnostic = score_terrain(fitted, grid.read_candidate(fitted))
    geology = _geology_index(str(geology_path)).score(fitted)
    followup = terrain["data_quality"] * (
        0.78 * terrain["topography_score_unweighted"] + 0.22 * geology["geology_independence"]
    )
    metrics = {
        **{key: _json_number(value) for key, value in terrain.items()},
        **{key: _json_number(value) for key, value in geology.items()},
        "fitted_longitude": round(fitted.lon, 6),
        "fitted_latitude": round(fitted.lat, 6),
        "fitted_diameter_km": round(fitted.diameter_km, 3),
        "formula": "data_quality × (0.78 × topography_score_unweighted + 0.22 × geology_independence)",
    }
    score = round(float(followup), 6)
    metrics["followup_score"] = score
    geophysical_sources_available = False
    if include_geophysics:
        try:
            from .geophysics import score_geophysics

            geophysical = score_geophysics(fitted, followup_score=score)
            geophysical_sources_available = any(
                geophysical.get(key) is not None
                for key in (
                    "gravity_bouguer_ring_score",
                    "gravity_freeair_ring_score",
                    "gravity_consensus_percentile",
                    "magnetic_ring_score",
                    "magnetic_ring_score_stratified_percentile",
                )
            )
            metrics.update(geophysical)
        except FileNotFoundError:
            metrics["geophysical_reason"] = "Required geophysical screening grids are not mounted."
    if diagnostic_path:
        save_elevation_analysis_figure(str(candidate.id), candidate.title, metrics, diagnostic, diagnostic_path)
    method_version = f"{METHOD_VERSION}+geophysics-v1" if geophysical_sources_available else METHOD_VERSION
    return {"score": score, "metrics": metrics, "method_version": method_version, "geometry": geometry}


def _json_number(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
