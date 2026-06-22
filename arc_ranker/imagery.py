from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def score_normalized_patch(path: str | Path) -> dict:
    """Score an optional candidate-centred image patch.

    Patches must be square, centred on the candidate, and cover +/-1.75 radii.
    This makes imagery scoring independent of the imagery provider.
    """
    path = Path(path)
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Could not read imagery patch: {path}")
    if image.ndim == 3:
        gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    gray = cv2.resize(gray.astype(np.float32), (512, 512), interpolation=cv2.INTER_AREA)
    gray = (gray - np.nanpercentile(gray, 2)) / max(1e-6, np.nanpercentile(gray, 98) - np.nanpercentile(gray, 2))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    yy, xx = np.indices(gray.shape)
    x = xx - 255.5
    y = 255.5 - yy
    radius_px = 512 / (2 * 1.75)
    rho = np.hypot(x, y) / radius_px
    erx = x / np.maximum(np.hypot(x, y), 1e-6)
    ery = y / np.maximum(np.hypot(x, y), 1e-6)
    radial = np.abs(gx * erx + gy * ery)
    annulus = (rho >= 0.85) & (rho <= 1.15)
    background = ((rho >= 0.45) & (rho <= 0.75)) | ((rho >= 1.25) & (rho <= 1.55))
    ring = float(np.nanmedian(radial[annulus]))
    bg = float(np.nanmedian(radial[background]))
    ratio = ring / max(bg, 1e-6)
    score = float(np.clip((ratio - 0.8) / 1.5, 0.0, 1.0))
    return {"imagery_score": score, "imagery_ring_edge_ratio": ratio, "imagery_path": str(path)}


def write_stac_request_manifest(candidates, output: str | Path, collection="sentinel-2-l2a"):
    """Write reproducible Planetary Computer STAC request bodies without downloading imagery."""
    requests = []
    for candidate in candidates:
        span = min(15.0, 1.75 * candidate.radius_km / 111.2)
        requests.append(
            {
                "candidate_id": candidate.candidate_id,
                "collection": collection,
                "bbox": [candidate.lon - span, candidate.lat - span, candidate.lon + span, candidate.lat + span],
                "datetime": "2020-01-01/2026-12-31",
                "query": {"eo:cloud_cover": {"lt": 20}},
            }
        )
    Path(output).write_text(json.dumps(requests, indent=2) + "\n", encoding="utf-8")
