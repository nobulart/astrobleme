from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def load_geojson(path: str | Path) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    source = Path(path)
    payload = json.loads(source.read_text())
    features = payload.get("features", [])
    rows: list[dict[str, Any]] = []
    geometries: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        props = dict(feature.get("properties") or {})
        props.setdefault("candidate_id", feature.get("id") or f"candidate_{index:04d}")
        rows.append(props)
        geometries.append(feature.get("geometry"))
    LOG.info("Loaded %d features from %s", len(rows), source)
    return pd.DataFrame(rows), geometries, payload


def _json_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def write_geojson(frame: pd.DataFrame, geometries: Iterable[dict[str, Any] | None], path: str | Path,
                  metadata: dict[str, Any] | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for (_, row), geometry in zip(frame.iterrows(), geometries):
        props = {str(k): _json_value(v) for k, v in row.items()}
        features.append({"type": "Feature", "id": props.get("candidate_id"), "geometry": geometry,
                         "properties": props})
    payload: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if metadata:
        payload["metadata"] = metadata
    target.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def write_csv(frame: pd.DataFrame, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)


def detect_field(frame: pd.DataFrame, aliases: Iterable[str], label: str, required: bool = False) -> str | None:
    normalized = {str(column).lower().replace("-", "_"): str(column) for column in frame.columns}
    for alias in aliases:
        key = alias.lower().replace("-", "_")
        if key in normalized:
            chosen = normalized[key]
            LOG.info("Field '%s': using '%s'", label, chosen)
            return chosen
    terms = [alias.lower().replace("_", "") for alias in aliases]
    for column in frame.columns:
        compact = str(column).lower().replace("_", "")
        if any(term in compact for term in terms):
            LOG.warning("Field '%s': fuzzy-matched '%s'", label, column)
            return str(column)
    if required:
        raise ValueError(f"No field found for {label}; tried {list(aliases)}")
    LOG.warning("Field '%s' unavailable; dependent evidence will be marked missing", label)
    return None

