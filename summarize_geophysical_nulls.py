#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


METRICS = (
    "tid_artifact_risk",
    "gravity_bouguer_ring_score",
    "gravity_freeair_ring_score",
    "magnetic_ring_score",
)


def rotation_test(observed, nulls, metric, rng, replicates, statistic):
    grouped = nulls.groupby("candidate_id", sort=False)
    complete_ids = [candidate_id for candidate_id, group in grouped if len(group) == nulls.null_index.max() + 1]
    obs = observed.set_index("candidate_id").loc[complete_ids, metric].to_numpy(float)
    matrix = np.vstack([grouped.get_group(candidate_id).sort_values("null_index")[metric] for candidate_id in complete_ids])
    keep = np.isfinite(obs) & np.any(np.isfinite(matrix), axis=1)
    obs, matrix = obs[keep], matrix[keep]
    function = np.nanmean if statistic == "mean" else np.nanmedian
    observed_statistic = float(function(obs))
    simulated = np.empty(replicates)
    for i in range(replicates):
        choices = rng.integers(0, matrix.shape[1], len(matrix))
        simulated[i] = function(matrix[np.arange(len(matrix)), choices])
    return {
        "statistic": statistic,
        "candidate_count": int(len(obs)),
        "observed": observed_statistic,
        "null_mean": float(np.mean(simulated)),
        "null_025": float(np.quantile(simulated, 0.025)),
        "null_975": float(np.quantile(simulated, 0.975)),
        "one_sided_enrichment_p": float((1 + np.count_nonzero(simulated >= observed_statistic)) / (replicates + 1)),
    }


def stratified_concordance(frame, metric, rng, replicates):
    data = frame[["followup_score", "diameter_km", "tid_land_fraction", metric]].dropna().reset_index(drop=True).copy()
    data["domain"] = np.where(data.tid_land_fraction >= 0.8, "land", np.where(data.tid_land_fraction <= 0.2, "ocean", "mixed"))
    data["size_bin"] = pd.qcut(np.log10(data.diameter_km.clip(lower=1e-6)), 10, labels=False, duplicates="drop")
    data["stratum"] = data.domain.astype(str) + "_" + data.size_bin.astype(str)
    observed_rho = float(spearmanr(data.followup_score, data[metric]).statistic)
    values = data[metric].to_numpy().copy()
    groups = [indices.to_numpy() for _, indices in data.groupby("stratum").groups.items()]
    simulated = np.empty(replicates)
    for i in range(replicates):
        shuffled = values.copy()
        for indices in groups:
            shuffled[indices] = rng.permutation(shuffled[indices])
        simulated[i] = spearmanr(data.followup_score, shuffled).statistic
    return {
        "candidate_count": int(len(data)),
        "observed_spearman_rho": observed_rho,
        "null_mean": float(np.mean(simulated)),
        "null_025": float(np.quantile(simulated, 0.025)),
        "null_975": float(np.quantile(simulated, 0.975)),
        "one_sided_positive_concordance_p": float((1 + np.count_nonzero(simulated >= observed_rho)) / (replicates + 1)),
        "strata": "land/ocean/mixed x log-diameter decile",
    }


def run(args):
    observed = pd.read_csv(args.evidence)
    nulls = pd.read_csv(args.null_rows)
    rng = np.random.default_rng(args.seed)
    rotation = {}
    for metric in METRICS:
        rotation[metric] = rotation_test(
            observed, nulls, metric, rng, args.replicates, "mean" if metric == "tid_artifact_risk" else "median"
        )
    concordance = {
        metric: stratified_concordance(observed, metric, rng, args.replicates)
        for metric in METRICS
        if metric != "tid_artifact_risk"
    }
    result = {
        "seed": args.seed,
        "replicates": args.replicates,
        "longitude_rotation": {
            "design": "Preserves latitude and candidate radius and matches GEBCO-TID land/ocean/mixed class; tests enrichment over same-latitude background.",
            "results": rotation,
        },
        "stratified_cross_layer_permutation": {
            "design": "Permutes each geophysical metric among candidates within land/ocean/mixed and log-diameter strata; tests concordance with morphology ranking beyond broad domain and scale.",
            "results": concordance,
        },
        "limits": [
            "The arcuate inventory was selected visually from GEBCO, so gravity enrichment can reflect genuine topographic-gravity coupling in endogenic landforms as well as impacts.",
            "Nineteen rotations yield coarse candidate-level p-values (minimum 0.05); candidate p-values are screening diagnostics, not discovery claims.",
            "Neither null controls detailed tectonic setting, survey-track geometry within a TID class, or spatial autocorrelation between nearby candidates.",
        ],
    }
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    rotation_labels = {
        "tid_artifact_risk": "Longitude rotation & TID artefact-risk mean",
        "gravity_bouguer_ring_score": "Longitude rotation & Bouguer ring-score median",
        "gravity_freeair_ring_score": "Longitude rotation & Free-air ring-score median",
        "magnetic_ring_score": "Longitude rotation & Magnetic ring-score median",
    }
    rows = []
    for metric, label in rotation_labels.items():
        value = rotation[metric]
        rows.append(
            f"{label} & {value['observed']:.4f} & {value['null_mean']:.4f} "
            f"[{value['null_025']:.4f}, {value['null_975']:.4f}] & {value['one_sided_enrichment_p']:.4f}\\\\"
        )
    for metric, label in (
        ("gravity_bouguer_ring_score", "Stratified permutation & Bouguer--morphology Spearman $\\rho$"),
        ("gravity_freeair_ring_score", "Stratified permutation & Free-air--morphology Spearman $\\rho$"),
        ("magnetic_ring_score", "Stratified permutation & Magnetic--morphology Spearman $\\rho$"),
    ):
        value = concordance[metric]
        rows.append(
            f"{label} & {value['observed_spearman_rho']:.4f} & {value['null_mean']:.4f} "
            f"[{value['null_025']:.4f}, {value['null_975']:.4f}] & {value['one_sided_positive_concordance_p']:.4f}\\\\"
        )
    rows[-1] = rows[-1][:-2]
    Path(args.tex_output).write_text("\n".join(rows) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description="Summarize spatial and cross-layer null tests from completed geophysical evidence.")
    p.add_argument("--evidence", default="geophysical_output/arc_ranking_enriched.csv")
    p.add_argument("--null-rows", default="geophysical_output/nulls/longitude_rotation_null_rows.csv")
    p.add_argument("--output", default="geophysical_output/nulls/geophysical_null_results.json")
    p.add_argument("--tex-output", default="geophysical_output/table_geophysical_nulls.tex")
    p.add_argument("--seed", type=int, default=20260621)
    p.add_argument("--replicates", type=int, default=9999)
    return p


if __name__ == "__main__":
    run(parser().parse_args())
