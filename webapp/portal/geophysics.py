"""Runtime geophysical screening for submitted candidates."""

from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from django.conf import settings


GRAVITY_GRID_FILES = {
    "gravity_bouguer": "WGM2012_Bouguer_ponc_2min.grd",
    "gravity_freeair": "WGM2012_Freeair_ponc_2min.grd",
    "gravity_isostatic": "WGM2012_Isostatic_ponc_2min.grd",
    "gravity_disturbance": "WGM2012_Disturbance_ponc_2min.grd",
}
REFERENCE_METRICS = [
    "gravity_bouguer_ring_score",
    "gravity_freeair_ring_score",
    "magnetic_ring_score",
]


def _imports():
    root = str(Path(settings.PROJECT_ROOT))
    if root not in sys.path:
        sys.path.insert(0, root)
    from arc_ranker.evidence import score_scalar_ring, score_tid
    from arc_ranker.grids import NpyRegularGrid, RegularGrid
    return score_scalar_ring, score_tid, NpyRegularGrid, RegularGrid


def score_geophysics(candidate, *, followup_score: float | None = None, roi_factor: float | None = None, max_pixels: int | None = None) -> dict:
    """Return gravity, magnetic, and source-quality screening metrics.

    Percentiles are ranked against the bundled study-candidate distribution so
    submitted candidates are displayed on the same scale as the manuscript set.
    """
    score_scalar_ring, score_tid, NpyRegularGrid, RegularGrid = _imports()
    roi_factor = roi_factor if roi_factor is not None else settings.GEOPHYSICAL_ROI_FACTOR
    max_pixels = max_pixels if max_pixels is not None else settings.GEOPHYSICAL_MAX_PIXELS
    metrics: dict[str, float | str | None] = {}
    sources = []
    try:
        tid_path = Path(settings.GEBCO_TID_GRID_PATH)
        if tid_path.is_file():
            tid = RegularGrid(tid_path, "tid")
            sources.append(tid)
            metrics.update(score_tid(candidate, tid.read_candidate(candidate, roi_factor, max_pixels)))

        wgm_dir = Path(settings.WGM2012_GRID_DIR)
        for prefix, filename in GRAVITY_GRID_FILES.items():
            path = wgm_dir / filename
            if path.is_file():
                grid = RegularGrid(path, "z", "x", "y")
                sources.append(grid)
                metrics.update(score_scalar_ring(candidate, grid.read_candidate(candidate, roi_factor, max_pixels), prefix))

        emag = Path(settings.EMAG2_CACHE_DIR)
        if all((emag / name).is_file() for name in ("emag2_anomaly.npy", "emag2_lon.npy", "emag2_lat.npy")):
            magnetic = NpyRegularGrid(emag / "emag2_anomaly.npy", emag / "emag2_lon.npy", emag / "emag2_lat.npy")
            sources.append(magnetic)
            metrics.update(score_scalar_ring(candidate, magnetic.read_candidate(candidate, roi_factor, max_pixels), "magnetic"))
    finally:
        for source in sources:
            source.close()

    metrics = {key: _json_number(value) for key, value in metrics.items()}
    if followup_score is not None:
        metrics["followup_score"] = followup_score
    metrics.update(_percentiles(candidate, metrics))
    metrics.update(_review_tier(metrics))
    return metrics


def _percentiles(candidate, metrics: dict) -> dict:
    reference = _reference_distribution(str(settings.GEOPHYSICAL_REFERENCE_GEOJSON))
    domain = _domain(metrics.get("tid_land_fraction"))
    decile = _diameter_decile(reference["diameter_edges"], candidate.diameter_km)
    result = {"domain": domain, "diameter_decile": decile}
    gravity_percentiles = []
    for metric in REFERENCE_METRICS:
        value = metrics.get(metric)
        if value is None:
            continue
        percentile = _rank_percentile(reference["by_stratum"].get((domain, decile, metric), []), value)
        if percentile is None:
            percentile = _rank_percentile(reference["global"].get(metric, []), value)
        key = f"{metric}_stratified_percentile"
        result[key] = percentile
        if metric in {"gravity_bouguer_ring_score", "gravity_freeair_ring_score"} and percentile is not None:
            gravity_percentiles.append(percentile)
    if gravity_percentiles:
        result["gravity_consensus_percentile"] = sum(gravity_percentiles) / len(gravity_percentiles)
        result["gravity_both_strong"] = min(gravity_percentiles) >= 0.75
    return result


def _review_tier(metrics: dict) -> dict:
    score = metrics.get("followup_score")
    gravity = metrics.get("gravity_consensus_percentile")
    artifact_risk = metrics.get("tid_artifact_risk")
    gravity_both = bool(metrics.get("gravity_both_strong"))
    if score is None or score < 0.75:
        tier = "D_background"
    elif gravity is not None and gravity >= 0.75 and artifact_risk is not None and artifact_risk <= 0.35:
        tier = "B_gravity_supported"
    else:
        tier = "C_morphology"
    if score is not None and score >= 0.75 and gravity_both and artifact_risk is not None and artifact_risk <= 0.25:
        tier = "A_cross_layer"
    return {"review_tier": tier}


@lru_cache(maxsize=2)
def _reference_distribution(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [feature.get("properties", {}) for feature in payload.get("features", [])]
    logs = sorted(math.log10(float(row["diameter_km"])) for row in rows if _finite(row.get("diameter_km")) and float(row["diameter_km"]) > 0)
    edges = [float(np.quantile(logs, q)) for q in np.linspace(0.1, 0.9, 9)] if logs else []
    by_stratum: dict[tuple[str, int, str], list[float]] = {}
    global_values: dict[str, list[float]] = {metric: [] for metric in REFERENCE_METRICS}
    for row in rows:
        domain = str(row.get("domain") or _domain(row.get("tid_land_fraction")))
        decile = _diameter_decile(edges, row.get("diameter_km"))
        for metric in REFERENCE_METRICS:
            value = row.get(metric)
            if not _finite(value):
                continue
            value = float(value)
            global_values.setdefault(metric, []).append(value)
            by_stratum.setdefault((domain, decile, metric), []).append(value)
    return {
        "diameter_edges": edges,
        "by_stratum": {key: sorted(values) for key, values in by_stratum.items()},
        "global": {key: sorted(values) for key, values in global_values.items()},
    }


def _domain(tid_land_fraction) -> str:
    if not _finite(tid_land_fraction):
        return "mixed"
    value = float(tid_land_fraction)
    if value >= 0.8:
        return "land"
    if value <= 0.2:
        return "ocean"
    return "mixed"


def _diameter_decile(edges: list[float], diameter_km) -> int:
    if not edges or not _finite(diameter_km) or float(diameter_km) <= 0:
        return 0
    value = math.log10(float(diameter_km))
    return int(np.searchsorted(edges, value, side="right"))


def _rank_percentile(values: list[float], value) -> float | None:
    if not values or not _finite(value):
        return None
    return sum(item <= float(value) for item in values) / len(values)


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _json_number(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
