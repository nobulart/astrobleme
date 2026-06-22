from __future__ import annotations

import math
from collections import Counter

import numpy as np
from scipy.ndimage import gaussian_filter

from .filters import robust_scale
from .geometry import Candidate, EARTH_RADIUS_KM, local_xy_km
from .grids import GridWindow


TID_DIRECT = {10, 11, 12, 13, 14, 15, 16, 17, 44}
TID_MODELLED = {40, 41, 42, 43, 45, 46, 47, 48, 70, 71, 72}


def _geometry(candidate: Candidate, window: GridWindow):
    lon2d, lat2d = np.meshgrid(window.lon, window.lat)
    x, y = local_xy_km(lon2d, lat2d, candidate.lon, candidate.lat)
    rho = np.hypot(x, y) / max(candidate.radius_km, 1e-6)
    theta = np.mod(np.arctan2(x, y), 2 * np.pi)
    return x, y, rho, theta


def _step_km(candidate: Candidate, window: GridWindow):
    if len(window.lat) < 2 or len(window.lon) < 2:
        return math.inf, math.inf
    dy = abs(float(np.median(np.diff(window.lat)))) * math.pi / 180 * EARTH_RADIUS_KM
    dx = (
        abs(float(np.median(np.diff(window.lon))))
        * math.pi
        / 180
        * EARTH_RADIUS_KM
        * max(0.05, math.cos(math.radians(candidate.lat)))
    )
    return max(dy, 1e-6), max(dx, 1e-6)


def score_tid(candidate: Candidate, window: GridWindow) -> dict:
    """Describe acquisition support and possible source-boundary artefacts."""
    tid = np.asarray(window.values)
    _, _, rho, theta = _geometry(candidate, window)
    roi = rho <= 1.55
    annulus = (rho >= 0.85) & (rho <= 1.15)
    background = ((rho >= 0.45) & (rho <= 0.75)) | ((rho >= 1.25) & (rho <= 1.55))
    valid = roi & (tid != 127)
    values = tid[valid].astype(int)
    counts = Counter(values.tolist())
    dominant, dominant_count = counts.most_common(1)[0] if counts else (-1, 0)
    probabilities = np.array(list(counts.values()), dtype=float)
    probabilities /= max(probabilities.sum(), 1.0)
    entropy = float(-np.sum(probabilities * np.log(probabilities)) / np.log(max(len(probabilities), 2)))

    direct = np.isin(tid, list(TID_DIRECT))
    modelled = np.isin(tid, list(TID_MODELLED))
    edge = np.zeros(tid.shape, dtype=bool)
    edge[:, 1:] |= tid[:, 1:] != tid[:, :-1]
    edge[1:, :] |= tid[1:, :] != tid[:-1, :]

    def fraction(mask, subset):
        return float(np.mean(mask[subset])) if np.any(subset) else math.nan

    annulus_edge = fraction(edge, annulus)
    background_edge = fraction(edge, background)
    edge_enrichment = annulus_edge / max(background_edge, 1e-6) if math.isfinite(annulus_edge) else math.nan
    sector_edge = []
    for sector in range(36):
        lo, hi = sector * 2 * np.pi / 36, (sector + 1) * 2 * np.pi / 36
        mask = annulus & (theta >= lo) & (theta < hi)
        sector_edge.append(np.count_nonzero(mask) >= 2 and float(np.mean(edge[mask])) >= 0.25)

    return {
        "tid_valid_fraction": fraction(tid != 127, roi),
        "tid_direct_fraction": fraction(direct, roi),
        "tid_modelled_fraction": fraction(modelled, roi),
        "tid_land_fraction": fraction(tid == 0, roi),
        "tid_unique_flags": len(counts),
        "tid_dominant_flag": dominant,
        "tid_dominant_fraction": dominant_count / max(len(values), 1),
        "tid_normalized_entropy": entropy,
        "tid_annulus_transition_fraction": annulus_edge,
        "tid_background_transition_fraction": background_edge,
        "tid_transition_enrichment": edge_enrichment,
        "tid_transition_angular_coverage": float(np.mean(sector_edge)),
        "tid_artifact_risk": float(np.clip(0.55 * min(edge_enrichment / 3.0, 1.0) + 0.45 * np.mean(sector_edge), 0, 1)),
    }


def score_scalar_ring(candidate: Candidate, window: GridWindow, prefix: str) -> dict:
    """Circular-anisotropy metrics for gravity, magnetics, or sediment grids."""
    z = np.asarray(window.values, dtype=np.float32)
    z[~np.isfinite(z)] = np.nan
    x, y, rho, theta = _geometry(candidate, window)
    roi = rho <= 1.55
    annulus = (rho >= 0.85) & (rho <= 1.15)
    inner = rho <= 0.70
    background = ((rho >= 0.45) & (rho <= 0.75)) | ((rho >= 1.25) & (rho <= 1.55))
    dy, dx = _step_km(candidate, window)
    diameter_pixels = 0.0 if not (math.isfinite(dx) and math.isfinite(dy)) else candidate.diameter_km / math.sqrt(dx * dy)
    valid_fraction = float(np.mean(np.isfinite(z[roi]))) if np.any(roi) else 0.0
    if min(z.shape) < 3 or np.count_nonzero(np.isfinite(z[roi])) < 24:
        return {
            f"{prefix}_valid_fraction": valid_fraction,
            f"{prefix}_diameter_pixels": diameter_pixels,
            f"{prefix}_ring_score": math.nan,
        }
    fill = float(np.nanmedian(z[roi]))
    work = np.where(np.isfinite(z), z, fill)
    sigma = (max(1.0, candidate.radius_km / dy * 0.55), max(1.0, candidate.radius_km / dx * 0.55))
    trend = gaussian_filter(work, sigma=sigma, mode="nearest")
    residual = work - trend
    scale = robust_scale(residual[roi])
    gy = np.gradient(residual, axis=0) / dy
    gx = np.gradient(residual, axis=1) / dx
    radius = np.hypot(x, y)
    erx = np.divide(x, radius, out=np.zeros_like(x), where=radius > 0)
    ery = np.divide(y, radius, out=np.zeros_like(y), where=radius > 0)
    radial = gx * erx + gy * ery
    tangential = -gx * ery + gy * erx
    magnitude = np.hypot(gx, gy)
    anisotropy = (np.abs(radial) - np.abs(tangential)) / (magnitude + 1e-8)
    radial_alignment = float(np.nanmedian(anisotropy[annulus]))
    bg_energy = float(np.nanmedian(np.abs(radial)[background]))
    bg_mad = float(np.nanmedian(np.abs(np.abs(radial)[background] - bg_energy)))
    threshold = bg_energy + 0.5 * bg_mad
    sectors = []
    for sector in range(36):
        lo, hi = sector * 2 * np.pi / 36, (sector + 1) * 2 * np.pi / 36
        mask = annulus & (theta >= lo) & (theta < hi)
        sectors.append(np.count_nonzero(mask) >= 2 and np.nanmedian(np.abs(radial)[mask]) > threshold)
    annular_gradient = float(np.nanmedian(np.abs(radial)[annulus])) / max(bg_energy, 1e-8)
    centre_level = float(np.nanmedian(residual[inner])) / scale
    annulus_level = float(np.nanmedian(residual[annulus])) / scale
    contrast = centre_level - annulus_level
    resolution_quality = float(np.clip((diameter_pixels - 4.0) / 16.0, 0, 1))
    ring_score = valid_fraction * resolution_quality * (
        0.35 * np.clip((radial_alignment + 1) / 2, 0, 1)
        + 0.35 * float(np.mean(sectors))
        + 0.30 * math.tanh(max(0.0, annular_gradient - 1.0))
    )
    return {
        f"{prefix}_valid_fraction": valid_fraction,
        f"{prefix}_diameter_pixels": diameter_pixels,
        f"{prefix}_radial_alignment": radial_alignment,
        f"{prefix}_angular_continuity": float(np.mean(sectors)),
        f"{prefix}_annular_gradient_enrichment": annular_gradient,
        f"{prefix}_central_anomaly_robust": centre_level,
        f"{prefix}_annular_anomaly_robust": annulus_level,
        f"{prefix}_central_annular_contrast": contrast,
        f"{prefix}_ring_score": float(ring_score),
    }
