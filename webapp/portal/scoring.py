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


def closest_study_candidate(longitude, latitude, diameter_km):
    closest = None
    for candidate_id, lon, lat, diameter in study_centres():
        distance = haversine_km(longitude, latitude, lon, lat)
        threshold = max(5.0, 0.25 * min(diameter_km, diameter))
        if distance <= threshold and (closest is None or distance < closest[1]):
            closest = (candidate_id, distance)
    return closest


def evaluate_submission(data):
    evidence = set(data.get("independent_evidence") or []) & INDEPENDENT_EVIDENCE_TYPES
    description = (data.get("description") or "").strip()
    alternative = (data.get("endogenic_alternative") or "").strip()
    source_title = (data.get("source_title") or "").strip()
    observed_feature = (data.get("observed_feature") or "").strip()
    diameter = float(data.get("diameter_km") or 0)
    longitude = float(data.get("longitude") or 0)
    latitude = float(data.get("latitude") or 0)
    geometry = data.get("geometry")

    duplicate = closest_study_candidate(longitude, latitude, diameter) if diameter > 0 else None
    checks = {
        "valid_location": -180 <= longitude <= 180 and -90 <= latitude <= 90,
        "reviewable_scale": 10 <= diameter <= 5000,
        "description_complete": len(description) >= 80,
        "source_identified": len(source_title) >= 8,
        "feature_identified": len(observed_feature) >= 8,
        "alternative_considered": len(alternative) >= 20,
        "terms_confirmed": bool(data.get("terms_confirmed")),
        "not_duplicate_of_study_candidate": duplicate is None,
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
    passed = all(value is True for value in required) and score >= 0.55
    checks["intake_threshold"] = score >= 0.55
    checks["scientific_note"] = "Intake score measures submission completeness and reviewability; it is not the study follow-up score or an impact probability."
    return score, passed, checks
