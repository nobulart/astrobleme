#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from arc_ranker.evidence import score_scalar_ring, score_tid
from arc_ranker.grids import NpyRegularGrid, RegularGrid
from enrich_arc_ranking import DEFAULT_TID, DEFAULT_WGM, load_candidates, write_csv


METRICS = (
    "tid_artifact_risk",
    "gravity_bouguer_ring_score",
    "gravity_freeair_ring_score",
    "magnetic_ring_score",
)


def numeric_rows(path):
    result = {}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            parsed = {"candidate_id": row["candidate_id"]}
            for key, value in row.items():
                if value not in {"", None}:
                    try:
                        parsed[key] = float(value)
                    except ValueError:
                        parsed[key] = value
            result[row["candidate_id"]] = parsed
    return result


def domain(land_fraction):
    if land_fraction >= 0.8:
        return "land"
    if land_fraction <= 0.2:
        return "ocean"
    return "mixed"


def candidate_p(observed, null_values):
    valid = np.asarray([x for x in null_values if math.isfinite(x)], dtype=float)
    if not math.isfinite(observed) or not len(valid):
        return math.nan
    return float((1 + np.count_nonzero(valid >= observed)) / (len(valid) + 1))


def global_test(observed, null_matrix, rng, replicates):
    observed = np.asarray(observed, dtype=float)
    null_matrix = np.asarray(null_matrix, dtype=float)
    keep = np.isfinite(observed) & np.any(np.isfinite(null_matrix), axis=1)
    observed = observed[keep]
    null_matrix = null_matrix[keep]
    statistic = float(np.nanmedian(observed))
    sampled = np.empty(replicates)
    for i in range(replicates):
        choices = rng.integers(0, null_matrix.shape[1], size=len(null_matrix))
        values = null_matrix[np.arange(len(null_matrix)), choices]
        sampled[i] = np.nanmedian(values)
    return {
        "candidate_count": int(len(observed)),
        "observed_median": statistic,
        "null_median_mean": float(np.nanmean(sampled)),
        "null_median_025": float(np.nanquantile(sampled, 0.025)),
        "null_median_975": float(np.nanquantile(sampled, 0.975)),
        "one_sided_enrichment_p": float((1 + np.count_nonzero(sampled >= statistic)) / (replicates + 1)),
    }


def run(args):
    candidates = load_candidates(args.arcs)
    observed_rows = numeric_rows(args.evidence)
    if args.limit is not None:
        candidates = candidates[: args.limit]
    rng = np.random.default_rng(args.seed)
    sources = {
        "tid": RegularGrid(args.tid, "tid"),
        "bouguer": RegularGrid(Path(args.wgm) / "WGM2012_Bouguer_ponc_2min.grd", "z", "x", "y"),
        "freeair": RegularGrid(Path(args.wgm) / "WGM2012_Freeair_ponc_2min.grd", "z", "x", "y"),
    }
    emag = Path(args.emag_cache)
    if (emag / "emag2_anomaly.npy").exists():
        sources["magnetic"] = NpyRegularGrid(
            emag / "emag2_anomaly.npy", emag / "emag2_lon.npy", emag / "emag2_lat.npy"
        )
    null_rows = []
    started = time.time()
    try:
        for position, candidate in enumerate(candidates, 1):
            observed = observed_rows[candidate.candidate_id]
            target_domain = domain(observed["tid_land_fraction"])
            accepted = 0
            attempts = 0
            while accepted < args.nulls_per_candidate and attempts < args.nulls_per_candidate * 30:
                attempts += 1
                lon = float(rng.uniform(-180.0, 180.0))
                null_candidate = replace(candidate, lon=lon)
                tid = score_tid(null_candidate, sources["tid"].read_candidate(null_candidate, args.roi_factor, args.max_pixels))
                if domain(tid["tid_land_fraction"]) != target_domain:
                    continue
                row = {
                    "candidate_id": candidate.candidate_id,
                    "null_index": accepted,
                    "null_lon": lon,
                    "lat": candidate.lat,
                    "diameter_km": candidate.diameter_km,
                    "domain": target_domain,
                    **tid,
                }
                row.update(score_scalar_ring(null_candidate, sources["bouguer"].read_candidate(null_candidate, args.roi_factor, args.max_pixels), "gravity_bouguer"))
                row.update(score_scalar_ring(null_candidate, sources["freeair"].read_candidate(null_candidate, args.roi_factor, args.max_pixels), "gravity_freeair"))
                if "magnetic" in sources:
                    row.update(score_scalar_ring(null_candidate, sources["magnetic"].read_candidate(null_candidate, args.roi_factor, args.max_pixels), "magnetic"))
                null_rows.append(row)
                accepted += 1
            if accepted < args.nulls_per_candidate:
                print(f"Warning: {candidate.candidate_id} accepted {accepted}/{args.nulls_per_candidate} domain-matched nulls")
            if position % 25 == 0 or position == len(candidates):
                print(f"Nulls {position}/{len(candidates)} in {time.time() - started:.1f}s", flush=True)
    finally:
        for source in sources.values():
            source.close()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "longitude_rotation_null_rows.csv", null_rows)
    grouped = {}
    for row in null_rows:
        grouped.setdefault(row["candidate_id"], []).append(row)
    candidate_results = []
    for candidate in candidates:
        observed = observed_rows[candidate.candidate_id]
        nulls = grouped.get(candidate.candidate_id, [])
        result = {"candidate_id": candidate.candidate_id, "null_count": len(nulls)}
        for metric in METRICS:
            result[f"observed_{metric}"] = observed.get(metric, math.nan)
            result[f"null_p_{metric}"] = candidate_p(observed.get(metric, math.nan), [row.get(metric, math.nan) for row in nulls])
        candidate_results.append(result)
    write_csv(output / "candidate_null_pvalues.csv", candidate_results)

    global_results = {}
    complete = [candidate for candidate in candidates if len(grouped.get(candidate.candidate_id, [])) == args.nulls_per_candidate]
    available_metrics = [metric for metric in METRICS if any(metric in row for row in null_rows)]
    for metric in available_metrics:
        observed = [observed_rows[c.candidate_id].get(metric, math.nan) for c in complete]
        matrix = [[row.get(metric, math.nan) for row in grouped[c.candidate_id]] for c in complete]
        global_results[metric] = global_test(observed, matrix, rng, args.global_replicates)
    summary = {
        "null": "Longitude rotation preserving candidate latitude and radius; null locations are matched to land/ocean/mixed class using GEBCO TID land fraction.",
        "seed": args.seed,
        "nulls_per_candidate": args.nulls_per_candidate,
        "global_replicates": args.global_replicates,
        "candidate_count": len(candidates),
        "complete_candidate_count": len(complete),
        "results": global_results,
        "interpretation": "One-sided tests assess enrichment relative to the spatial background. Candidate p-values are screening diagnostics and are not FDR-adjusted impact probabilities.",
    }
    (output / "longitude_rotation_null_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description="Run domain-matched longitude-rotation nulls for acquisition and geophysical ring evidence.")
    p.add_argument("--arcs", default="arcuate_geometries.geojson")
    p.add_argument("--evidence", default="geophysical_output/geophysical_evidence.csv")
    p.add_argument("--output", default="geophysical_output/nulls")
    p.add_argument("--tid", default=DEFAULT_TID)
    p.add_argument("--wgm", default=DEFAULT_WGM)
    p.add_argument("--emag-cache", default="geophysical_cache/emag2")
    p.add_argument("--nulls-per-candidate", type=int, default=19)
    p.add_argument("--global-replicates", type=int, default=9999)
    p.add_argument("--seed", type=int, default=20260621)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--roi-factor", type=float, default=1.75)
    p.add_argument("--max-pixels", type=int, default=256)
    return p


if __name__ == "__main__":
    run(parser().parse_args())
