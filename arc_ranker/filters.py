from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter

from .geometry import Candidate, EARTH_RADIUS_KM, local_xy_km
from .gebco import TerrainWindow


def robust_scale(array: np.ndarray) -> float:
    q25, q75 = np.nanpercentile(array, [25, 75])
    return max(float(q75 - q25), float(np.nanstd(array)) * 0.25, 1e-6)


def _radial_energy_curve(rho, energy, bins=np.linspace(0.35, 1.55, 61)):
    centres = (bins[:-1] + bins[1:]) / 2
    values = np.full(len(centres), np.nan)
    for i in range(len(centres)):
        mask = (rho >= bins[i]) & (rho < bins[i + 1])
        if np.count_nonzero(mask) >= 8:
            values[i] = np.nanmedian(energy[mask])
    return centres, values


def score_terrain(candidate: Candidate, window: TerrainWindow) -> tuple[dict, dict]:
    z = np.asarray(window.elevation, dtype=np.float32)
    lon2d, lat2d = np.meshgrid(window.lon, window.lat)
    x, y = local_xy_km(lon2d, lat2d, candidate.lon, candidate.lat)
    radius = max(candidate.radius_km, 1e-6)
    rho = np.hypot(x, y) / radius
    annulus = (rho >= 0.85) & (rho <= 1.15)
    background = ((rho >= 0.45) & (rho <= 0.78)) | ((rho >= 1.22) & (rho <= 1.55))
    roi = rho <= 1.65

    lat_step_km = max(1e-6, abs(float(np.median(np.diff(window.lat)))) * math.pi / 180 * EARTH_RADIUS_KM)
    lon_step_km = max(
        1e-6,
        abs(float(np.median(np.diff(window.lon))))
        * math.pi
        / 180
        * EARTH_RADIUS_KM
        * max(0.05, math.cos(math.radians(candidate.lat))),
    )
    radius_px_y = radius / lat_step_km
    radius_px_x = radius / lon_step_km
    sigma = (max(1.0, radius_px_y * 0.35), max(1.0, radius_px_x * 0.35))
    trend = gaussian_filter(z, sigma=sigma, mode="nearest")
    residual = z - trend
    scale = robust_scale(residual[roi])

    gy = np.gradient(residual, axis=0) / lat_step_km
    gx = np.gradient(residual, axis=1) / lon_step_km
    magnitude = np.hypot(gx, gy)
    erx = np.divide(x, np.hypot(x, y), out=np.zeros_like(x), where=np.hypot(x, y) > 0)
    ery = np.divide(y, np.hypot(x, y), out=np.zeros_like(y), where=np.hypot(x, y) > 0)
    radial = gx * erx + gy * ery
    tangential = -gx * ery + gy * erx
    anisotropy = (np.abs(radial) - np.abs(tangential)) / (magnitude + 1e-8)
    radial_alignment = float(np.nanmedian(anisotropy[annulus])) if np.any(annulus) else -1.0

    centres, curve = _radial_energy_curve(rho, np.abs(radial))
    valid_curve = curve[np.isfinite(curve)]
    ring_band = np.abs(centres - 1.0) <= 0.12
    ring_energy = float(np.nanmax(curve[ring_band])) if np.any(np.isfinite(curve[ring_band])) else 0.0
    hough_percentile = float(np.mean(valid_curve <= ring_energy)) if len(valid_curve) else 0.0
    if len(valid_curve):
        best_index = int(np.nanargmax(curve))
        best_radius = float(centres[best_index])
    else:
        best_radius = math.nan
    radius_offset = abs(best_radius - 1.0) if math.isfinite(best_radius) else 1.0
    radius_match = math.exp(-((radius_offset / 0.16) ** 2))

    theta = np.mod(np.arctan2(x, y), 2 * np.pi)
    sector_supported = []
    bg_global = float(np.nanmedian(np.abs(radial)[background])) if np.any(background) else 0.0
    bg_mad = float(np.nanmedian(np.abs(np.abs(radial)[background] - bg_global))) if np.any(background) else 0.0
    threshold = bg_global + 0.5 * bg_mad
    for sector in range(72):
        lo, hi = sector * 2 * np.pi / 72, (sector + 1) * 2 * np.pi / 72
        mask = annulus & (theta >= lo) & (theta < hi)
        sector_supported.append(np.count_nonzero(mask) >= 3 and np.nanmedian(np.abs(radial)[mask]) > threshold)
    angular_continuity = float(np.mean(sector_supported))

    annular_level = float(np.nanmedian(residual[annulus])) if np.any(annulus) else 0.0
    inner = (rho >= 0.58) & (rho <= 0.78)
    outer = (rho >= 1.22) & (rho <= 1.42)
    neighbour_level = 0.5 * (float(np.nanmedian(residual[inner])) + float(np.nanmedian(residual[outer])))
    annular_relief = abs(annular_level - neighbour_level) / scale
    relief_score = math.tanh(annular_relief)

    shift_values = [-0.10, 0.0, 0.10]
    centre_trials = []
    for sx in shift_values:
        for sy in shift_values:
            shifted_rho = np.hypot(x - sx * radius, y - sy * radius) / radius
            mask = (shifted_rho >= 0.88) & (shifted_rho <= 1.12)
            centre_trials.append((float(np.nanmedian(np.abs(radial)[mask])), sx, sy))
    _, best_sx, best_sy = max(centre_trials)
    centre_shift = math.hypot(best_sx, best_sy)
    centre_match = math.exp(-((centre_shift / 0.14) ** 2))

    native_resolution = math.sqrt(lat_step_km * lon_step_km) / math.sqrt(window.stride_x * window.stride_y)
    native_diameter_pixels = candidate.diameter_km / max(native_resolution, 1e-6)
    resolution_quality = float(np.clip((native_diameter_pixels - 8.0) / 32.0, 0.0, 1.0))
    valid_fraction = float(np.mean(np.isfinite(z[roi]))) if np.any(roi) else 0.0
    data_quality = resolution_quality * valid_fraction

    alignment_score = float(np.clip((radial_alignment + 1.0) / 2.0, 0.0, 1.0))
    topo_score_raw = (
        0.24 * alignment_score
        + 0.22 * hough_percentile
        + 0.18 * angular_continuity
        + 0.14 * radius_match
        + 0.12 * centre_match
        + 0.10 * relief_score
    )
    topography_score = data_quality * topo_score_raw

    metrics = {
        "topography_score": topography_score,
        "topography_score_unweighted": topo_score_raw,
        "data_quality": data_quality,
        "native_diameter_pixels": native_diameter_pixels,
        "radial_alignment": radial_alignment,
        "hough_percentile": hough_percentile,
        "angular_continuity": angular_continuity,
        "best_radius_ratio": best_radius,
        "radius_match": radius_match,
        "centre_shift_ratio": centre_shift,
        "centre_match": centre_match,
        "annular_relief_normalized": annular_relief,
        "relief_score": relief_score,
        "terrain_iqr_m": scale,
        "sample_rows": int(z.shape[0]),
        "sample_cols": int(z.shape[1]),
        "source_stride_y": int(window.stride_y),
        "source_stride_x": int(window.stride_x),
    }
    diagnostic = {
        "elevation": z,
        "residual": residual,
        "rho": rho,
        "radial_gradient": radial,
        "lon": window.lon,
        "lat": window.lat,
    }
    return metrics, diagnostic
