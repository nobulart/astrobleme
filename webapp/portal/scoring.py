import json
import math
from functools import lru_cache
from pathlib import Path

from django.conf import settings

EARTH_RADIUS_KM = 6371.0088
INDEPENDENT_EVIDENCE_TYPES = {"gravity", "magnetic", "geology", "seismic", "field", "petrography", "geochemistry"}


def haversine_km(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def study_centres():
    path = Path(settings.PROJECT_ROOT) / "study_results_geojson" / "arcuate_geometries_study_results.geojson"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    centres = []
    for feature in data.get("features", []):
        p = feature.get("properties") or {}
        if all(p.get(k) is not None for k in ("lon", "lat", "diameter_km")):
            centres.append((str(p.get("candidate_id")), float(p["lon"]), float(p["lat"]), float(p["diameter_km"])))
    return centres


def closest_study_candidate(longitude, latitude, diameter_km, *, distance_fraction=0.25, min_distance_km=5.0):
    closest = None
    for candidate_id, lon, lat, diameter in study_centres():
        distance = haversine_km(longitude, latitude, lon, lat)
        threshold = max(min_distance_km, distance_fraction * min(diameter_km, diameter))
        if distance <= threshold and (closest is None or distance < closest[1]):
            closest = (candidate_id, distance)
    return closest


def evaluate_submission(data):
    from .models import PortalConfiguration

    config = PortalConfiguration.current()
    evidence = set(data.get("independent_evidence") or []) & INDEPENDENT_EVIDENCE_TYPES
    description = (data.get("description") or "").strip()
    alternative = (data.get("endogenic_alternative") or "").strip()
    source_title = (data.get("source_title") or "").strip()
    observed_feature = (data.get("observed_feature") or "").strip()
    diameter = float(data.get("diameter_km") or 0)
    longitude = float(data.get("longitude") or 0)
    latitude = float(data.get("latitude") or 0)
    geometry = data.get("geometry")

    duplicate = closest_study_candidate(
        longitude,
        latitude,
        diameter,
        distance_fraction=config.duplicate_distance_fraction,
        min_distance_km=config.duplicate_min_distance_km,
    ) if diameter > 0 else None
    checks = {
        "valid_location": -180 <= longitude <= 180 and -90 <= latitude <= 90,
        "reviewable_scale": config.min_diameter_km <= diameter <= config.max_diameter_km,
        "description_complete": len(description) >= config.min_description_chars,
        "source_identified": len(source_title) >= config.min_source_title_chars,
        "feature_identified": len(observed_feature) >= config.min_observed_feature_chars,
        "alternative_considered": len(alternative) >= config.min_endogenic_alternative_chars,
        "terms_confirmed": not config.require_terms_confirmed or bool(data.get("terms_confirmed")),
        "not_duplicate_of_study_candidate": not config.require_unique_study_candidate or duplicate is None,
    }
    if duplicate:
        checks["possible_duplicate"] = {"candidate_id": duplicate[0], "distance_km": round(duplicate[1], 2)}

    score = 0.0
    score += 0.20 if checks["source_identified"] else 0
    score += 0.15 if checks["description_complete"] else 0
    score += 0.15 if checks["alternative_considered"] else 0
    score += 0.10 if checks["feature_identified"] else 0
    score += 0.10 if data.get("source_uri") else 0
    score += 0.10 if data.get("source_resolution") else 0
    score += 0.10 if data.get("original_trace_available") and geometry else 0
    score += min(0.10, 0.025 * len(evidence))
    score = round(score, 3)

    required = [value for key, value in checks.items() if key != "possible_duplicate"]
    passed = all(value is True for value in required) and score >= config.baseline_score_threshold
    checks["intake_threshold"] = score >= config.baseline_score_threshold
    checks["configuration"] = {
        "baseline_score_threshold": config.baseline_score_threshold,
        "min_description_chars": config.min_description_chars,
        "min_endogenic_alternative_chars": config.min_endogenic_alternative_chars,
        "min_source_title_chars": config.min_source_title_chars,
        "min_observed_feature_chars": config.min_observed_feature_chars,
        "min_diameter_km": config.min_diameter_km,
        "max_diameter_km": config.max_diameter_km,
        "duplicate_distance_fraction": config.duplicate_distance_fraction,
        "duplicate_min_distance_km": config.duplicate_min_distance_km,
        "require_terms_confirmed": config.require_terms_confirmed,
        "require_unique_study_candidate": config.require_unique_study_candidate,
    }
    checks["scientific_note"] = "Intake score measures submission completeness and reviewability; it is not the study follow-up score or an impact probability."
    return score, passed, checks
