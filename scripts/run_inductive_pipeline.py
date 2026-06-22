#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astrobleme_pipeline.config import PipelineConfig
from astrobleme_pipeline.field_packets import write_candidate_packets
from astrobleme_pipeline.gravity_first import plot_gravity_scatter, rank_gravity_first
from astrobleme_pipeline.io import load_geojson, write_csv, write_geojson
from astrobleme_pipeline.negative_controls import add_anton_dohrn_control, load_negative_controls, match_negative_controls, plot_controls_map
from astrobleme_pipeline.planetary_compare import compare_planetary, plot_planetary_sizes
from astrobleme_pipeline.preservation import predict_all
from astrobleme_pipeline.regional_families import assign_regional_context, plot_regional_map
from astrobleme_pipeline.report import write_summary_report
from astrobleme_pipeline.ring_ratios import cluster_ring_families, plot_ring_family_examples

LOG = logging.getLogger("inductive_pipeline")


def run(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = PipelineConfig.from_yaml(args.config)
    output = Path(args.output); inputs_used = [str(args.input)]; skipped: list[str] = []
    candidates, geometries, _ = load_geojson(args.input)
    geometry_by_id = dict(zip(candidates["candidate_id"].astype(str), geometries))
    ranked, fields = rank_gravity_first(candidates, cfg)
    ranked_for_plot = ranked.copy()
    diameter_field = fields.get("diameter")
    if diameter_field:
        ranked = ranked[pd.to_numeric(ranked[diameter_field], errors="coerce") >= args.min_diameter_km]
    if args.max_tid_risk is not None and fields.get("tid"):
        risk = pd.to_numeric(ranked[fields["tid"]], errors="coerce")
        ranked = ranked[risk.isna() | (risk <= args.max_tid_risk)]
    shortlist = ranked.head(args.top_n).copy()
    write_csv(shortlist, output / "tables/gravity_first_shortlist.csv")
    if args.write_geojson:
        write_geojson(shortlist, [geometry_by_id.get(str(cid)) for cid in shortlist["candidate_id"]],
                      output / "inductive_shortlists/gravity_first_shortlist.geojson",
                      {"score": "gravity_first_review_score; review priority, not impact probability", "config": cfg.metadata()})
    if args.write_figures:
        plot_gravity_scatter(ranked_for_plot, output / "figures/gravity_first_scatter.png")

    if args.skip_negative_controls:
        controls = pd.DataFrame(); skipped.append("negative controls: explicitly skipped")
    else:
        controls, control_sources = load_negative_controls(ROOT / "negative_controls", [ROOT / "data/controls.geojson"])
        controls = add_anton_dohrn_control(controls, candidates)
        write_csv(controls, output / "tables/negative_control_library.csv")
        if control_sources: inputs_used.extend(control_sources)
        else: skipped.append("negative_controls/*.geojson absent; built-in Anton Dohrn control retained")
    control_matches = match_negative_controls(shortlist, controls, cfg)
    write_csv(control_matches, output / "tables/negative_control_matches.csv")
    if args.write_figures: plot_controls_map(shortlist, controls, output / "figures/candidate_vs_controls_map.png")

    ring_source = candidates
    families, ring_membership = cluster_ring_families(ring_source, cfg)
    write_csv(families, output / "tables/ring_families.csv")
    if args.write_figures: plot_ring_family_examples(ring_source, ring_membership, output / "figures/ring_family_examples.png")
    if args.write_geojson and not ring_membership.empty:
        ring_features = ring_source.merge(ring_membership, on="candidate_id", how="inner")
        write_geojson(ring_features, [geometry_by_id.get(str(cid)) for cid in ring_features["candidate_id"]],
                      output / "inductive_shortlists/ring_families.geojson", {"interpretation": "candidate nested geometry; not an impact ring system"})

    preservation = predict_all(shortlist); write_csv(preservation, output / "tables/preservation_predictions.csv")
    regional = assign_regional_context(shortlist, cfg); write_csv(regional, output / "tables/regional_families.csv")
    if args.write_figures: plot_regional_map(shortlist, regional, output / "figures/regional_family_map.png")

    merged = shortlist.merge(control_matches, on="candidate_id", how="left").merge(preservation, on="candidate_id", how="left").merge(regional, on="candidate_id", how="left")
    if not ring_membership.empty: merged = merged.merge(ring_membership, on="candidate_id", how="left")
    packet_ids: list[str] = []
    if args.write_packets:
        packet_dir = output / f"candidate_packets/top_{min(args.top_n, len(merged))}"
        write_candidate_packets(merged, packet_dir, args.top_n); packet_ids = merged.head(args.top_n)["candidate_id"].astype(str).tolist()
    else: skipped.append("field-review packets: --write-packets not requested")

    comparison = pd.DataFrame()
    if args.skip_planetary:
        skipped.append("planetary comparison: explicitly skipped")
    else:
        planetary_sources = [ROOT / "planetary/lunar_multiring_basins.csv", ROOT / "planetary/martian_basins.csv"]
        comparison = compare_planetary(families, planetary_sources)
        if not any(source.exists() for source in planetary_sources): skipped.append("planetary CSV inputs absent")
        write_csv(comparison, output / "tables/planetary_comparison.csv")
        if args.write_figures: plot_planetary_sizes(comparison, output / "figures/planetary_size_comparison.png")
    write_summary_report(output / "reports/inductive_pipeline_summary.md", inputs_used=inputs_used, skipped=skipped,
                         shortlist=shortlist, controls=control_matches, control_library=controls, rings=families,
                         preservation=preservation, regional=regional, planetary=comparison,
                         packet_ids=packet_ids, metadata=cfg.metadata())
    LOG.info("Completed conservative screening run: %d shortlisted candidates, %d ring families", len(shortlist), len(families))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run conservative inductive candidate screening (not impact classification).")
    p.add_argument("--config"); p.add_argument("--input", default="study_results_geojson/arcuate_geometries_study_results.geojson")
    p.add_argument("--output", default="outputs"); p.add_argument("--skip-negative-controls", action="store_true")
    p.add_argument("--skip-planetary", action="store_true"); p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--min-diameter-km", type=float, default=10); p.add_argument("--max-tid-risk", type=float, default=.25)
    p.add_argument("--write-geojson", action="store_true"); p.add_argument("--write-figures", action="store_true")
    p.add_argument("--write-packets", action="store_true"); return p


if __name__ == "__main__": run(parser().parse_args())
