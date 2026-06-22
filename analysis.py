#!/usr/bin/env python3
"""Reproducible analysis for the astrobleme manuscript.

The script reads the three GeoJSON sources, deduplicates the African catalogue
at the named-structure level, estimates spherical centres and diameters for the
arcuate geometries, runs distributional and spatial null tests, and writes the
figures/tables consumed by astrobleme.tex.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import ks_2samp


ROOT = Path(__file__).resolve().parent
EARTH_RADIUS_KM = 6371.0088
SEED = 20260619
N_NULL = 9999


def load_features(filename: str | Path) -> list[dict]:
    path = Path(filename)
    if not path.is_absolute():
        path = ROOT / path
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["features"]


def flatten_multilines(geometry: dict) -> np.ndarray:
    return np.asarray(
        [point for line in geometry["coordinates"] for point in line],
        dtype=float,
    )


def lonlat_to_xyz(lon_deg: np.ndarray, lat_deg: np.ndarray) -> np.ndarray:
    lon = np.deg2rad(lon_deg)
    lat = np.deg2rad(lat_deg)
    return np.column_stack(
        (np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat))
    )


def xyz_to_lonlat(xyz: np.ndarray) -> tuple[float, float]:
    xyz = xyz / np.linalg.norm(xyz)
    return (
        float(np.rad2deg(np.arctan2(xyz[1], xyz[0]))),
        float(np.rad2deg(np.arcsin(xyz[2]))),
    )


def angular_distance_matrix(
    lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray
) -> np.ndarray:
    xyz1 = lonlat_to_xyz(np.asarray(lon1), np.asarray(lat1))
    xyz2 = lonlat_to_xyz(np.asarray(lon2), np.asarray(lat2))
    return np.arccos(np.clip(xyz1 @ xyz2.T, -1.0, 1.0)) * EARTH_RADIUS_KM


def arc_metrics(feature: dict) -> dict:
    points = flatten_multilines(feature["geometry"])
    xyz = lonlat_to_xyz(points[:, 0], points[:, 1])
    centre_xyz = xyz.mean(axis=0)
    centre_xyz /= np.linalg.norm(centre_xyz)
    centre_lon, centre_lat = xyz_to_lonlat(centre_xyz)
    radial_km = (
        np.arccos(np.clip(xyz @ centre_xyz, -1.0, 1.0)) * EARTH_RADIUS_KM
    )
    radius = float(np.median(radial_km))
    mad = float(np.median(np.abs(radial_km - radius)))
    return {
        "name": feature["properties"].get("Name") or "unnamed",
        "lon": centre_lon,
        "lat": centre_lat,
        "diameter_km": 2.0 * radius,
        "relative_radial_mad": mad / radius if radius else math.nan,
        "vertices": int(len(points)),
    }


def african_structures(features: list[dict]) -> list[dict]:
    """Collapse centre/circle rendering geometries to one named structure."""
    grouped: dict[str, list[dict]] = {}
    for feature in features:
        grouped.setdefault(feature["properties"]["name"], []).append(feature)
    records = []
    for name, group in grouped.items():
        centre = next(
            (f for f in group if f["properties"].get("geometry_role") == "center"),
            group[0],
        )
        props = centre["properties"]
        if centre["geometry"]["type"] == "Point":
            lon, lat = centre["geometry"]["coordinates"]
        else:
            coords = np.asarray(centre["geometry"]["coordinates"][0], dtype=float)
            xyz = lonlat_to_xyz(coords[:, 0], coords[:, 1]).mean(axis=0)
            lon, lat = xyz_to_lonlat(xyz)
        dmin = props.get("diameter_min_km")
        dmax = props.get("diameter_max_km")
        diameter = None if dmin is None or dmax is None else (dmin + dmax) / 2.0
        records.append(
            {
                "name": name,
                "lon": float(lon),
                "lat": float(lat),
                "diameter_km": diameter,
                "status": props["status"],
                "table": props["table"],
            }
        )
    return records


def astrobleme_records(features: list[dict]) -> list[dict]:
    return [
        {
            "name": f["properties"]["display_name"],
            "lon": float(f["properties"]["center_lon"]),
            "lat": float(f["properties"]["center_lat"]),
            "diameter_km": float(f["properties"]["diameter_km"]),
            "eid_match": bool(f["properties"]["earth_impact_database_match"]),
            "source": f["properties"]["source"],
        }
        for f in features
    ]


def best_log_scale(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return scale s minimizing KS(x, s*y), and the minimized KS statistic."""
    lx, ly = np.log(np.asarray(x)), np.log(np.asarray(y))

    def objective(delta: float) -> float:
        return float(ks_2samp(lx, ly + delta, method="asymp").statistic)

    guess = float(np.median(lx) - np.median(ly))
    result = minimize_scalar(
        objective, bounds=(guess - 5.0, guess + 5.0), method="bounded"
    )
    return float(np.exp(result.x)), float(result.fun)


def shifted_ks_permutation(
    x: np.ndarray, y: np.ndarray, rng: np.random.Generator, n: int
) -> tuple[float, float, np.ndarray]:
    scale, observed = best_log_scale(x, y)
    pooled = np.concatenate((x, y))
    nx = len(x)
    null = np.empty(n)
    for i in range(n):
        perm = rng.permutation(pooled)
        _, null[i] = best_log_scale(perm[:nx], perm[nx:])
    # Large KS means that shapes differ more than arbitrary relabellings of
    # observations from a common distribution, even after fitting a shift.
    p_difference = (1 + np.count_nonzero(null >= observed)) / (n + 1)
    return scale, observed, p_difference


def power_law_tail(values: np.ndarray, min_tail: int = 25) -> dict:
    """Select xmin by KS and estimate a continuous Pareto tail by MLE."""
    values = np.sort(np.asarray(values, dtype=float))
    candidates = np.unique(values)[: max(1, len(values) - min_tail + 1)]
    best = None
    for xmin in candidates:
        tail = values[values >= xmin]
        if len(tail) < min_tail or np.any(tail < xmin) or np.all(tail == xmin):
            continue
        alpha = 1.0 + len(tail) / np.log(tail / xmin).sum()
        empirical = np.arange(1, len(tail) + 1) / len(tail)
        model = 1.0 - (tail / xmin) ** (1.0 - alpha)
        ks = float(np.max(np.abs(empirical - model)))
        candidate = (ks, float(xmin), float(alpha), int(len(tail)))
        if best is None or candidate < best:
            best = candidate
    if best is None:
        return {"xmin": math.nan, "alpha_pdf": math.nan, "alpha_cumulative": math.nan, "n": 0, "ks": math.nan}
    ks, xmin, alpha, tail_n = best
    return {
        "xmin": xmin,
        "alpha_pdf": alpha,
        "alpha_cumulative": -(alpha - 1.0),
        "n": tail_n,
        "ks": ks,
    }


def spatial_nulls(
    arcs: list[dict], astros: list[dict], rng: np.random.Generator, n: int
) -> dict:
    arc_lon = np.array([r["lon"] for r in arcs])
    arc_lat = np.array([r["lat"] for r in arcs])
    astro_lon = np.array([r["lon"] for r in astros])
    astro_lat = np.array([r["lat"] for r in astros])
    eid = np.array([r["eid_match"] for r in astros], dtype=bool)

    observed_nearest = angular_distance_matrix(
        astro_lon, astro_lat, arc_lon, arc_lat
    ).min(axis=1)
    observed_count = int(np.count_nonzero(observed_nearest[eid] <= 100.0))
    observed_median = float(np.median(observed_nearest[eid]))

    longitude_counts = np.empty(n, dtype=int)
    longitude_medians = np.empty(n)
    for i, offset in enumerate(rng.uniform(-180.0, 180.0, n)):
        shifted_lon = ((astro_lon[eid] + offset + 180.0) % 360.0) - 180.0
        nearest = angular_distance_matrix(
            shifted_lon, astro_lat[eid], arc_lon, arc_lat
        ).min(axis=1)
        longitude_counts[i] = np.count_nonzero(nearest <= 100.0)
        longitude_medians[i] = np.median(nearest)

    # Confidence-label permutation controls for the shared geographic sampling
    # footprint of confirmed and proposed entries in the astrobleme catalogue.
    label_counts = np.empty(n, dtype=int)
    label_medians = np.empty(n)
    n_eid = int(eid.sum())
    for i in range(n):
        chosen = rng.choice(len(astros), n_eid, replace=False)
        label_counts[i] = np.count_nonzero(observed_nearest[chosen] <= 100.0)
        label_medians[i] = np.median(observed_nearest[chosen])

    return {
        "nearest_km": observed_nearest,
        "observed_count_100km": observed_count,
        "observed_median_km": observed_median,
        "longitude_counts": longitude_counts,
        "longitude_medians": longitude_medians,
        "longitude_p_count": (1 + np.count_nonzero(longitude_counts >= observed_count)) / (n + 1),
        "longitude_p_median": (1 + np.count_nonzero(longitude_medians <= observed_median)) / (n + 1),
        "label_counts": label_counts,
        "label_medians": label_medians,
        "label_p_count": (1 + np.count_nonzero(label_counts >= observed_count)) / (n + 1),
        "label_p_median": (1 + np.count_nonzero(label_medians <= observed_median)) / (n + 1),
    }


def save_size_figure(arcs: list[dict], africa: list[dict], astros: list[dict], output_dir: Path = ROOT) -> None:
    groups = {
        "Arcuate geometries": np.array([r["diameter_km"] for r in arcs]),
        "All astrobleme entries": np.array([r["diameter_km"] for r in astros]),
        "EID-matched astroblemes": np.array([r["diameter_km"] for r in astros if r["eid_match"]]),
        "Confirmed African structures": np.array(
            [r["diameter_km"] for r in africa if r["status"] == "confirmed" and r["diameter_km"]]
        ),
    }
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    styles = ["-", "--", "-.", ":"]
    for (label, values), style in zip(groups.items(), styles):
        values = np.sort(values)
        survival = np.arange(len(values), 0, -1) / len(values)
        ax.step(values, survival, where="post", label=f"{label} ($n={len(values)}$)", linestyle=style, linewidth=2)
    ax.set(xscale="log", yscale="log", xlabel="Diameter (km)", ylabel="Fraction with diameter ≥ D")
    ax.grid(True, which="both", alpha=0.2)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(output_dir / "fig_size_distributions.pdf")
    fig.savefig(output_dir / "fig_size_distributions.png", dpi=220)
    plt.close(fig)


def save_map_figure(arcs_raw: list[dict], africa: list[dict], astros: list[dict], output_dir: Path = ROOT) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 7.3), sharex=True, sharey=True)
    ax = axes[0]
    for feature in arcs_raw:
        for line in feature["geometry"]["coordinates"]:
            p = np.asarray(line)
            jumps = np.where(np.abs(np.diff(p[:, 0])) > 180)[0] + 1
            for segment in np.split(p, jumps):
                ax.plot(segment[:, 0], segment[:, 1], color="#9b2226", alpha=0.24, linewidth=0.35)
    ax.set_title("Arcuate geometries (n=1,318)", loc="left")

    ax = axes[1]
    proposed = [r for r in astros if not r["eid_match"]]
    matched = [r for r in astros if r["eid_match"]]
    ax.scatter([r["lon"] for r in proposed], [r["lat"] for r in proposed], s=10, c="#ca6702", alpha=0.5, label="Other astrobleme entries")
    ax.scatter([r["lon"] for r in matched], [r["lat"] for r in matched], s=18, c="#005f73", alpha=0.8, label="EID-matched entries")
    confirmed_africa = [r for r in africa if r["status"] == "confirmed"]
    ax.scatter([r["lon"] for r in confirmed_africa], [r["lat"] for r in confirmed_africa], s=42, facecolors="none", edgecolors="#0a9396", linewidths=1.2, label="Confirmed African structures")
    ax.set_title("Catalogue centres by confidence class", loc="left")
    ax.legend(frameon=False, ncol=3, fontsize=8, loc="lower center")

    for ax in axes:
        ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        ax.set_xticks(np.arange(-180, 181, 60)); ax.set_yticks(np.arange(-90, 91, 30))
        ax.grid(True, alpha=0.2); ax.set_ylabel("Latitude (°)")
    axes[-1].set_xlabel("Longitude (°)")
    fig.tight_layout()
    fig.savefig(output_dir / "fig_catalogue_maps.pdf")
    fig.savefig(output_dir / "fig_catalogue_maps.png", dpi=220)
    plt.close(fig)


def save_null_figure(spatial: dict, output_dir: Path = ROOT) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.8))
    axes[0].hist(spatial["longitude_counts"], bins=np.arange(spatial["longitude_counts"].min() - 0.5, spatial["longitude_counts"].max() + 1.5), color="#94d2bd", edgecolor="white")
    axes[0].axvline(spatial["observed_count_100km"], color="#9b2226", linewidth=2, label="Observed")
    axes[0].set(xlabel="EID matches ≤100 km from an arc centre", ylabel="Longitude-rotation nulls")
    axes[0].legend(frameon=False)

    axes[1].hist(spatial["label_counts"], bins=np.arange(spatial["label_counts"].min() - 0.5, spatial["label_counts"].max() + 1.5), color="#e9d8a6", edgecolor="white")
    axes[1].axvline(spatial["observed_count_100km"], color="#9b2226", linewidth=2, label="Observed")
    axes[1].set(xlabel="Selected entries ≤100 km from an arc centre", ylabel="Confidence-label permutations")
    axes[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "fig_spatial_nulls.pdf")
    fig.savefig(output_dir / "fig_spatial_nulls.png", dpi=220)
    plt.close(fig)


def fmt_p(p: float) -> str:
    return "$<0.001$" if p < 0.001 else f"${p:.3f}$"


def write_tables(summary: dict, arc_diameters: np.ndarray, output_dir: Path = ROOT) -> None:
    bins = [(0, 100), (100, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 10000), (10000, np.inf)]
    labels = ["0--100", "100--250", "250--500", "500--1000", "1000--2000", "2000--5000", "5000--10\\,000", "$>10\\,000$"]
    rows = []
    for label, (low, high) in zip(labels, bins):
        count = int(np.count_nonzero((arc_diameters >= low) & (arc_diameters < high)))
        rows.append(f"{label} & {count} & {100 * count / len(arc_diameters):.1f}\\\\")
    rows[-1] = rows[-1][:-2]
    (output_dir / "table_arc_bins.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")

    s = summary["spatial_nulls"]
    null_rows = [
        f"Longitude rotation & Count within 100 km & {s['observed_count_100km']} & {s['longitude_null_count_median']:.0f} [{s['longitude_null_count_q025']:.0f}, {s['longitude_null_count_q975']:.0f}] & {fmt_p(s['longitude_p_count'])}\\\\",
        f"Longitude rotation & Median nearest distance (km) & {s['observed_median_km']:.1f} & {s['longitude_null_median_median']:.1f} [{s['longitude_null_median_q025']:.1f}, {s['longitude_null_median_q975']:.1f}] & {fmt_p(s['longitude_p_median'])}\\\\",
        f"Confidence-label permutation & Count within 100 km & {s['observed_count_100km']} & {s['label_null_count_median']:.0f} [{s['label_null_count_q025']:.0f}, {s['label_null_count_q975']:.0f}] & {fmt_p(s['label_p_count'])}\\\\",
        f"Confidence-label permutation & Median nearest distance (km) & {s['observed_median_km']:.1f} & {s['label_null_median_median']:.1f} [{s['label_null_median_q025']:.1f}, {s['label_null_median_q975']:.1f}] & {fmt_p(s['label_p_median'])}\\\\",
    ]
    null_rows[-1] = null_rows[-1][:-2]
    (output_dir / "table_nulls.tex").write_text("\n".join(null_rows) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arcs", default="arcuate_geometries.geojson")
    p.add_argument("--africa", default="african_impact_structures.geojson")
    p.add_argument("--astroblemes", default="astroblemes.geojson")
    p.add_argument("--output-dir", default=str(ROOT))
    return p


def main(args=None) -> None:
    args = args or parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    arcs_raw = load_features(args.arcs)
    africa_raw = load_features(args.africa)
    astros_raw = load_features(args.astroblemes)

    arcs = [arc_metrics(f) for f in arcs_raw]
    africa = african_structures(africa_raw)
    astros = astrobleme_records(astros_raw)
    arc_diameters = np.array([r["diameter_km"] for r in arcs])
    astro_diameters = np.array([r["diameter_km"] for r in astros])
    eid_diameters = np.array([r["diameter_km"] for r in astros if r["eid_match"]])

    scale, shifted_ks, shifted_p = shifted_ks_permutation(
        arc_diameters, astro_diameters, rng, 1999
    )
    spatial = spatial_nulls(arcs, astros, rng, N_NULL)

    q = lambda a, x: float(np.quantile(a, x))
    summary = {
        "seed": SEED,
        "features": {
            "arc_geometries": len(arcs_raw),
            "arc_unique_names": len({r["name"] for r in arcs}),
            "african_geometries": len(africa_raw),
            "african_named_structures": len(africa),
            "african_confirmed": sum(r["status"] == "confirmed" for r in africa),
            "african_proposed": sum(r["status"] == "proposed_unconfirmed" for r in africa),
            "african_discarded": sum(r["status"] == "discarded" for r in africa),
            "astrobleme_entries": len(astros),
            "astrobleme_eid_matches": int(sum(r["eid_match"] for r in astros)),
        },
        "arcs": {
            "diameter_median_km": q(arc_diameters, 0.5),
            "diameter_q025_km": q(arc_diameters, 0.025),
            "diameter_q975_km": q(arc_diameters, 0.975),
            "diameter_max_km": float(arc_diameters.max()),
            "relative_radial_mad_median": q(np.array([r["relative_radial_mad"] for r in arcs]), 0.5),
        },
        "power_law_tails": {
            "arcs": power_law_tail(arc_diameters),
            "all_astroblemes": power_law_tail(astro_diameters),
            "eid_matches": power_law_tail(eid_diameters),
        },
        "shifted_size_comparison": {
            "best_scale": scale,
            "ks": shifted_ks,
            "permutation_p_difference": shifted_p,
            "interpretation": "Upper-tail permutation p for a difference in distributional shape after fitting a multiplicative scale.",
        },
        "spatial_nulls": {
            "n": N_NULL,
            "observed_count_100km": spatial["observed_count_100km"],
            "observed_median_km": spatial["observed_median_km"],
            "longitude_null_count_median": q(spatial["longitude_counts"], 0.5),
            "longitude_null_count_q025": q(spatial["longitude_counts"], 0.025),
            "longitude_null_count_q975": q(spatial["longitude_counts"], 0.975),
            "longitude_null_median_median": q(spatial["longitude_medians"], 0.5),
            "longitude_null_median_q025": q(spatial["longitude_medians"], 0.025),
            "longitude_null_median_q975": q(spatial["longitude_medians"], 0.975),
            "longitude_p_count": spatial["longitude_p_count"],
            "longitude_p_median": spatial["longitude_p_median"],
            "label_null_count_median": q(spatial["label_counts"], 0.5),
            "label_null_count_q025": q(spatial["label_counts"], 0.025),
            "label_null_count_q975": q(spatial["label_counts"], 0.975),
            "label_null_median_median": q(spatial["label_medians"], 0.5),
            "label_null_median_q025": q(spatial["label_medians"], 0.025),
            "label_null_median_q975": q(spatial["label_medians"], 0.975),
            "label_p_count": spatial["label_p_count"],
            "label_p_median": spatial["label_p_median"],
        },
    }
    summary["inputs"] = {
        "arcs": str(Path(args.arcs)),
        "africa": str(Path(args.africa)),
        "astroblemes": str(Path(args.astroblemes)),
    }
    (output_dir / "analysis_results.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    write_tables(summary, arc_diameters, output_dir)
    save_size_figure(arcs, africa, astros, output_dir)
    save_map_figure(arcs_raw, africa, astros, output_dir)
    save_null_figure(spatial, output_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
