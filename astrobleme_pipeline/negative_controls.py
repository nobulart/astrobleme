from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PipelineConfig
from .geometry import geometry_center, geometry_radius_km, great_circle_distance_km
from .io import load_geojson

LOG = logging.getLogger(__name__)

CLASS_BY_FILE = {
    "calderas": "caldera", "seamounts": "volcanic_seamount", "ring_complexes": "ring_complex",
    "diapirs": "diapir", "sedimentary_basins": "sedimentary_basin", "salt_structures": "salt_structure",
    "tectonic_arcs": "tectonic_arc", "intrusive_complexes": "intrusive_complex",
}


def _slug(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return text or "unnamed_control"


def infer_control_class(source_type: object, description: object, filename_class: str) -> str:
    text = f"{source_type or ''} {description or ''}".lower()
    checks = [("seamount", "volcanic_seamount"), ("caldera", "caldera"),
              ("salt", "salt_structure"), ("diapir", "diapir"),
              ("sedimentary basin", "sedimentary_basin"), ("tectonic arc", "tectonic_arc"),
              ("intrusive", "intrusive_complex"), ("igneous complex", "intrusive_complex"),
              ("ring complex", "ring_complex"), ("dome", "ring_complex")]
    for term, control_class in checks:
        if term in text:
            return control_class
    if "volcan" in text:
        return "intrusive_complex"
    return filename_class


def standardize_control_schema(frame: pd.DataFrame, geometries: list[dict], control_class: str) -> pd.DataFrame:
    result = frame.copy()
    names = result.get("name", result.get("Name", result.get("negative_control_name", result.get("candidate_id"))))
    source_types = result.get("source_control_type", result.get("Type", pd.Series([None] * len(result), index=result.index)))
    descriptions = result.get("control_description", result.get("Description", pd.Series([None] * len(result), index=result.index)))
    if names is None:
        names = pd.Series([f"{control_class}_{i:04d}" for i in range(len(result))], index=result.index)
    result["negative_control_name"] = names
    result["source_control_type"] = source_types
    result["control_description"] = descriptions
    if "negative_control_class" not in result:
        result["negative_control_class"] = [infer_control_class(t, d, control_class) for t, d in zip(source_types, descriptions)]
    if "negative_control_id" not in result:
        result["negative_control_id"] = [f"control_{_slug(value)}" for value in names]
    result["known_endogenic_negative_control"] = True
    if "lon" not in result or "lat" not in result:
        centers = [geometry_center(item) for item in geometries]
        result["lon"] = [item[0] for item in centers]
        result["lat"] = [item[1] for item in centers]
    if "radius_km" not in result:
        if "diameter_km" in result:
            result["radius_km"] = pd.to_numeric(result["diameter_km"], errors="coerce") / 2.0
        else:
            result["radius_km"] = [geometry_radius_km(item, lon, lat) for item, lon, lat in zip(geometries, result["lon"], result["lat"])]
    if "diameter_km" not in result:
        result["diameter_km"] = pd.to_numeric(result["radius_km"], errors="coerce") * 2.0
    return result


def load_negative_controls(directory: str | Path, additional_sources: list[str | Path] | None = None) -> tuple[pd.DataFrame, list[str]]:
    root = Path(directory)
    frames: list[pd.DataFrame] = []
    used: list[str] = []
    if not root.exists() and not additional_sources:
        LOG.warning("Negative-control directory absent: %s", root)
        return pd.DataFrame(), used
    sources = list(sorted(root.glob("*.geojson"))) if root.exists() else []
    sources.extend(Path(item) for item in (additional_sources or []) if Path(item).exists())
    seen: set[Path] = set()
    for source in sources:
        source = source.resolve()
        if source in seen:
            continue
        seen.add(source)
        raw, geometries, _ = load_geojson(source)
        control_class = CLASS_BY_FILE.get(source.stem, source.stem.rstrip("s"))
        frames.append(standardize_control_schema(raw, geometries, control_class))
        used.append(str(source))
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), used


def add_anton_dohrn_control(controls: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    if "candidate_id" not in candidates:
        return controls
    anton = candidates[candidates["candidate_id"].astype(str).eq("arc_0370")].copy()
    if anton.empty:
        return controls
    anton["negative_control_id"] = "anton_dohrn_arc_0370"
    anton["negative_control_name"] = "Anton Dohrn Seamount"
    anton["negative_control_class"] = "volcanic_seamount"
    anton["source_control_type"] = "known volcanic seamount"
    anton["control_description"] = "Mandatory volcanic negative control identified in the study."
    anton["known_endogenic_negative_control"] = True
    anton["known_volcanic_negative_control"] = True
    keep = [column for column in ["negative_control_id", "negative_control_name", "negative_control_class",
                                  "source_control_type", "control_description", "known_endogenic_negative_control",
                                  "known_volcanic_negative_control", "lon", "lat", "radius_km", "diameter_km"] if column in anton]
    return pd.concat([controls, anton[keep]], ignore_index=True, sort=False)


def nearest_control_distance(candidate: pd.Series, controls: pd.DataFrame) -> tuple[int | None, float | None]:
    if controls.empty or pd.isna(candidate.get("lon")) or pd.isna(candidate.get("lat")):
        return None, None
    distances = controls.apply(lambda row: great_circle_distance_km(candidate["lon"], candidate["lat"], row["lon"], row["lat"]), axis=1)
    index = int(distances.idxmin())
    return index, float(distances.loc[index])


def candidate_control_similarity(candidate: pd.Series, control: pd.Series) -> float | None:
    values = []
    for field in ("diameter_km", "morphology_score_used", "gravity_consensus_used"):
        a, b = candidate.get(field), control.get(field)
        if pd.notna(a) and pd.notna(b) and max(abs(float(a)), abs(float(b))) > 0:
            values.append(min(abs(float(a)), abs(float(b))) / max(abs(float(a)), abs(float(b))))
    return float(np.mean(values)) if values else None


def candidate_control_similarity_channels(candidate: pd.Series, control: pd.Series) -> int:
    return sum(pd.notna(candidate.get(field)) and pd.notna(control.get(field))
               for field in ("diameter_km", "morphology_score_used", "gravity_consensus_used"))


def match_negative_controls(candidates: pd.DataFrame, controls: pd.DataFrame,
                            config: PipelineConfig | None = None) -> pd.DataFrame:
    cfg = config or PipelineConfig()
    rows = []
    for _, candidate in candidates.iterrows():
        index, distance = nearest_control_distance(candidate, controls)
        control = controls.loc[index] if index is not None else None
        candidate_radius = candidate.get("radius_km", candidate.get("diameter_km", np.nan) / 2.0)
        control_radius = control.get("radius_km", 0.0) if control is not None else 0.0
        overlap = bool(distance is not None and pd.notna(candidate_radius) and distance <= cfg.control_overlap_radius_fraction * (float(candidate_radius) + float(control_radius or 0)))
        similarity = candidate_control_similarity(candidate, control) if control is not None else None
        similarity_channels = candidate_control_similarity_channels(candidate, control) if control is not None else 0
        proximity_limit = cfg.control_similarity_max_distance_km
        if pd.notna(candidate_radius) and control is not None and pd.notna(control_radius):
            proximity_limit = max(proximity_limit, 2.0 * (float(candidate_radius) + float(control_radius)))
        similarity_nearby = bool(distance is not None and distance <= proximity_limit)
        rows.append({
            "candidate_id": candidate.get("candidate_id"),
            "nearest_negative_control_id": control.get("negative_control_id") if control is not None else None,
            "nearest_negative_control_class": control.get("negative_control_class") if control is not None else None,
            "nearest_negative_control_distance_km": distance,
            "overlapping_negative_control": overlap,
            "control_similarity_score": similarity,
            "control_similarity_channels_used": similarity_channels,
            "control_similarity_nearby": similarity_nearby,
            "control_similarity_warning": bool(overlap or (similarity_nearby and similarity is not None and similarity >= 0.75)),
            "known_volcanic_negative_control": bool(candidate.get("candidate_id") == "arc_0370"),
            "control_interpretation": "requires endogenic modelling before impact interpretation" if control is not None else "no control library available",
        })
    return pd.DataFrame(rows)


def plot_controls_map(candidates: pd.DataFrame, controls: pd.DataFrame, path: str | Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.scatter(candidates["lon"], candidates["lat"], s=10, alpha=.45, label="Candidates")
    if not controls.empty:
        ax.scatter(controls["lon"], controls["lat"], marker="x", s=36, color="#c44e52", label="Negative controls")
    ax.set(xlabel="Longitude", ylabel="Latitude", title="Candidates and known endogenic controls", xlim=(-180, 180), ylim=(-90, 90))
    ax.legend(loc="lower left"); fig.tight_layout(); fig.savefig(target, dpi=180); plt.close(fig)
