#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def run(args):
    frame = pd.read_csv(args.input)
    frame["domain"] = np.where(
        frame.tid_land_fraction >= 0.8, "land", np.where(frame.tid_land_fraction <= 0.2, "ocean", "mixed")
    )
    frame["diameter_decile"] = pd.qcut(
        np.log10(frame.diameter_km.clip(lower=1e-6)), 10, labels=False, duplicates="drop"
    )
    strata = [frame.domain, frame.diameter_decile]
    for metric in ("gravity_bouguer_ring_score", "gravity_freeair_ring_score", "magnetic_ring_score"):
        frame[f"{metric}_stratified_percentile"] = frame.groupby(strata, dropna=False)[metric].rank(pct=True)
    gravity_percentiles = [
        "gravity_bouguer_ring_score_stratified_percentile",
        "gravity_freeair_ring_score_stratified_percentile",
    ]
    frame["gravity_consensus_percentile"] = frame[gravity_percentiles].mean(axis=1)
    frame["gravity_both_strong"] = frame[gravity_percentiles].min(axis=1) >= 0.75
    frame["tid_low_artifact_risk"] = frame.tid_artifact_risk <= 0.25
    frame["review_tier"] = "D_background"
    frame.loc[frame.followup_score >= 0.75, "review_tier"] = "C_morphology"
    frame.loc[
        (frame.followup_score >= 0.75)
        & (frame.gravity_consensus_percentile >= 0.75)
        & (frame.tid_artifact_risk <= 0.35),
        "review_tier",
    ] = "B_gravity_supported"
    frame.loc[
        (frame.followup_score >= 0.75) & frame.gravity_both_strong & frame.tid_low_artifact_risk,
        "review_tier",
    ] = "A_cross_layer"
    order = {"A_cross_layer": 0, "B_gravity_supported": 1, "C_morphology": 2, "D_background": 3}
    frame["review_tier_order"] = frame.review_tier.map(order)
    frame = frame.sort_values(
        ["review_tier_order", "followup_score", "gravity_consensus_percentile"], ascending=[True, False, False]
    )
    frame["geophysical_review_rank"] = np.arange(1, len(frame) + 1)
    columns = [
        "geophysical_review_rank", "review_tier", "candidate_id", "name", "lon", "lat", "diameter_km",
        "followup_score", "rank", "data_quality", "domain", "tid_artifact_risk", "tid_direct_fraction",
        "gravity_bouguer_ring_score", "gravity_freeair_ring_score", "gravity_consensus_percentile",
        "magnetic_ring_score", "magnetic_ring_score_stratified_percentile", "sediment_ring_score",
        "geology_independence", "geology_boundary_coincidence", "geology_boundary_crossings", "geology_nearby_types",
    ]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    frame[columns].to_csv(args.output, index=False)
    counts = frame.review_tier.value_counts().reindex(order).fillna(0).astype(int)
    print(counts.to_string())


def parser():
    p = argparse.ArgumentParser(description="Build transparent review tiers from morphology, TID quality, and gravity concordance.")
    p.add_argument("--input", default="geophysical_output/arc_ranking_enriched.csv")
    p.add_argument("--output", default="geophysical_output/geophysical_review_priority.csv")
    return p


if __name__ == "__main__":
    run(parser().parse_args())
