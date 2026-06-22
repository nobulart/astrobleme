#!/usr/bin/env python3
"""Consolidate repeat arc picks and add independent active-fault controls.

The output is a review catalogue, not an impact-probability model.  Arc picks are
merged only when their centres and radii are mutually compatible.  Nearby but
different-scale rings are retained and linked as possible nested structures.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform
from shapely.strtree import STRtree

EARTH_KM = 6371.0088
TIER_ORDER = {"A_cross_layer": 0, "B_gravity_supported": 1, "C_morphology": 2, "D_background": 3}


def haversine_km(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def compatible(a, b, centre_fraction, ratio_low, ratio_high):
    ratio = a.radius_km / b.radius_km
    d = haversine_km(a.lon, a.lat, b.lon, b.lat)
    return ratio_low <= ratio <= ratio_high and d <= centre_fraction * min(a.radius_km, b.radius_km)


def consolidate(df, centre_fraction=.25, ratio_low=.67, ratio_high=1.5):
    """Score-ordered complete-link clustering; prevents transitive chain merges."""
    work = df.sort_values(["followup_score", "candidate_id"], ascending=[False, True])
    clusters = []
    for row in work.itertuples():
        choices = []
        for i, members in enumerate(clusters):
            if all(compatible(row, other, centre_fraction, ratio_low, ratio_high) for other in members):
                rep = members[0]
                choices.append((haversine_km(row.lon, row.lat, rep.lon, rep.lat) / min(row.radius_km, rep.radius_km), i))
        if choices:
            clusters[min(choices)[1]].append(row)
        else:
            clusters.append([row])
    clusters.sort(key=lambda x: (-x[0].followup_score, x[0].candidate_id))
    return clusters


def load_faults(path):
    obj = json.loads(path.read_text())
    geoms, props = [], []
    for f in obj["features"]:
        g = shape(f["geometry"])
        if not g.is_empty:
            geoms.append(g); props.append(f.get("properties", {}))
    return geoms, props


def local_transformers(lon, lat):
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs")
    fwd = Transformer.from_crs("EPSG:4326", local, always_xy=True).transform
    return fwd


def fault_metrics(lon, lat, radius_km, tree, geoms, props):
    # Progressively widen the geographic search; 60 degrees records sparse-coverage cases.
    idx = np.array([], dtype=int)
    used_deg = None
    for deg in (2, 5, 10, 20, 40, 60):
        q = Point(lon, lat).buffer(deg)
        idx = np.asarray(tree.query(q), dtype=int)
        if len(idx):
            used_deg = deg; break
    if not len(idx):
        return {"active_fault_coverage": 0, "nearest_active_fault_km": np.nan,
                "nearest_active_fault_name": None, "fault_length_within_radius_km": np.nan,
                "fault_intersects_candidate": 0, "fault_search_degrees": 60}
    fwd = local_transformers(lon, lat)
    centre = Point(0, 0)
    projected = [transform(fwd, geoms[int(i)]) for i in idx]
    distances = [centre.distance(g) / 1000 for g in projected]
    j = int(np.argmin(distances))
    disk = centre.buffer(radius_km * 1000)
    length = sum(g.intersection(disk).length for g in projected) / 1000
    p = props[int(idx[j])]
    return {"active_fault_coverage": 1, "nearest_active_fault_km": distances[j],
            "nearest_active_fault_name": p.get("name") or p.get("fz_name"),
            "nearest_active_fault_slip_type": p.get("slip_type"),
            "fault_length_within_radius_km": length,
            "fault_intersects_candidate": int(length > 0), "fault_search_degrees": used_deg}


def matched_fault_null(structures, iterations=9999, seed=954, return_draws=False):
    """Match A/B structures to C/D controls by domain, size and absolute latitude."""
    x = structures.copy()
    x["radius_bin"] = pd.qcut(x.radius_km.rank(method="first"), 5, labels=False)
    x["latitude_bin"] = pd.qcut(x.lat.abs().rank(method="first"), 4, labels=False)
    high_tiers = ["A_cross_layer", "B_gravity_supported"]
    cases = x[x.review_tier.isin(high_tiers)]
    controls = x[~x.review_tier.isin(high_tiers)]
    pools = []
    for c in cases.itertuples():
        pool = controls[(controls.domain == c.domain) & (controls.radius_bin == c.radius_bin) &
                        (controls.latitude_bin == c.latitude_bin)]
        if len(pool) < 3:
            pool = controls[(controls.domain == c.domain) & (controls.radius_bin == c.radius_bin)]
        if len(pool) < 3:
            pool = controls[controls.domain == c.domain]
        pools.append(pool)
    rng = np.random.default_rng(seed)
    null_intersection, null_log_ratio = np.empty(iterations), np.empty(iterations)
    for i in range(iterations):
        sample = pd.DataFrame([p.iloc[rng.integers(len(p))] for p in pools])
        null_intersection[i] = sample.fault_intersects_candidate.mean()
        null_log_ratio[i] = np.median(np.log1p(sample.active_fault_proximity_ratio))
    obs_i = cases.fault_intersects_candidate.mean()
    obs_r = np.median(np.log1p(cases.active_fault_proximity_ratio))
    result = {"case_definition": "review tiers A and B", "case_count": int(len(cases)),
        "matching": "domain x radius quintile x absolute-latitude quartile; documented relaxation if sparse",
        "iterations": iterations, "observed_fault_intersection_fraction": obs_i,
        "null_mean_fault_intersection_fraction": float(null_intersection.mean()),
        "fault_intersection_enrichment_p": float((1 + np.sum(null_intersection >= obs_i)) / (iterations + 1)),
        "observed_median_log1p_fault_proximity_ratio": float(obs_r),
        "null_mean_median_log1p_fault_proximity_ratio": float(null_log_ratio.mean()),
        "closer_fault_proximity_p": float((1 + np.sum(null_log_ratio <= obs_r)) / (iterations + 1))}
    if return_draws:
        draws = pd.DataFrame({"replicate": np.arange(1, iterations + 1),
                              "fault_intersection_fraction": null_intersection,
                              "median_log1p_fault_proximity_ratio": null_log_ratio})
        return result, draws
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arcs", default="geophysical_output/arc_ranking_enriched.csv")
    ap.add_argument("--tiers", default="geophysical_output/geophysical_review_priority.csv")
    ap.add_argument("--faults", default="geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson")
    ap.add_argument("--out", default="structure_output")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.arcs).merge(pd.read_csv(args.tiers)[["candidate_id", "review_tier", "domain"]], on="candidate_id", how="left")

    settings = {"strict": (.15, .80, 1.25), "default": (.25, .67, 1.50), "lenient": (.35, .50, 2.00)}
    sensitivity, default_clusters = [], None
    for name, pars in settings.items():
        cs = consolidate(df, *pars)
        sensitivity.append({"setting": name, "centre_fraction": pars[0], "radius_ratio_low": pars[1],
                            "radius_ratio_high": pars[2], "structure_count": len(cs),
                            "multi_pick_structures": sum(len(c) > 1 for c in cs),
                            "candidates_consolidated": len(df) - len(cs)})
        if name == "default": default_clusters = cs
    pd.DataFrame(sensitivity).to_csv(out / "consolidation_sensitivity.csv", index=False)

    candidate_rows, structure_rows = [], []
    for n, members in enumerate(default_clusters, 1):
        sid = f"structure_{n:04d}"; rep = members[0]
        member_ids = sorted(m.candidate_id for m in members)
        weights = np.array([max(m.followup_score, .001) for m in members])
        lons = np.unwrap(np.radians([m.lon for m in members]))
        lon = math.degrees(np.average(lons, weights=weights)); lon = ((lon + 180) % 360) - 180
        lat = np.average([m.lat for m in members], weights=weights)
        radii = [m.radius_km for m in members]
        tiers = [m.review_tier for m in members]
        best_tier = min(tiers, key=lambda x: TIER_ORDER.get(x, 99))
        structure_rows.append({"structure_id": sid, "representative_candidate_id": rep.candidate_id,
            "representative_name": rep.name, "lon": lon, "lat": lat, "radius_km": float(np.median(radii)),
            "diameter_km": float(2*np.median(radii)), "member_count": len(members),
            "member_candidate_ids": ";".join(member_ids), "radius_min_km": min(radii), "radius_max_km": max(radii),
            "followup_score": rep.followup_score, "review_tier": best_tier, "domain": rep.domain,
            "geology_independence": rep.geology_independence,
            "geology_boundary_coincidence": rep.geology_boundary_coincidence,
            "geology_nearby_types": rep.geology_nearby_types,
            "tid_artifact_risk": rep.tid_artifact_risk})
        candidate_rows.extend({"candidate_id": m.candidate_id, "structure_id": sid,
                               "is_representative": int(m.candidate_id == rep.candidate_id)} for m in members)

    structures = pd.DataFrame(structure_rows)
    geoms, props = load_faults(Path(args.faults)); tree = STRtree(geoms)
    metrics = [fault_metrics(r.lon, r.lat, r.radius_km, tree, geoms, props) for r in structures.itertuples()]
    structures = pd.concat([structures, pd.DataFrame(metrics)], axis=1)
    # Explicit contextual flags; neither changes followup_score nor asserts origin.
    structures["active_fault_proximity_ratio"] = structures.nearest_active_fault_km / structures.radius_km
    structures["fault_control_flag"] = np.where(structures.fault_intersects_candidate.eq(1), "intersects_active_fault",
        np.where(structures.active_fault_proximity_ratio.le(1), "near_active_fault", "no_mapped_active_fault_within_radius"))
    structures.insert(0, "structure_review_rank", structures.followup_score.rank(method="first", ascending=False).astype(int))
    structures = structures.sort_values("structure_review_rank")
    structures.to_csv(out / "structure_ranking.csv", index=False)
    pd.DataFrame(candidate_rows).to_csv(out / "candidate_to_structure.csv", index=False)
    features = [{"type": "Feature", "geometry": mapping(Point(r.lon, r.lat)),
                 "properties": {k: (None if pd.isna(v) else v) for k, v in r._asdict().items()}}
                for r in structures.itertuples(index=False)]
    (out / "structure_ranking.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))
    fault_null, fault_draws = matched_fault_null(structures, return_draws=True)
    fault_draws.to_csv(out / "fault_matched_null_draws.csv", index=False)
    (out / "fault_matched_null.json").write_text(json.dumps(fault_null, indent=2))
    summary = {"input_candidates": len(df), "default_structures": len(structures),
               "multi_pick_structures": int((structures.member_count > 1).sum()),
               "candidates_consolidated": int(len(df)-len(structures)),
               "fault_intersections": int(structures.fault_intersects_candidate.sum()),
               "source_fault_features": len(geoms), "fault_matched_null": fault_null,
               "sensitivity": sensitivity}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    (out / "README.md").write_text("""# Structure-level review catalogue\n\nArc picks are merged with score-ordered complete-link clustering when every pair has centre separation <= 0.25 times the smaller radius and radius ratio 0.67--1.50. This conservative rule avoids merging broad footprint overlaps and preserves different-scale nested rings. Strict and lenient sensitivity results are supplied. GEM harmonized active-fault metrics are independent geological controls and do not alter `followup_score`; absence of a mapped fault is not evidence of impact origin. Macrostrat enrichment is deferred until a reproducibly cached API response is available.\n""")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
