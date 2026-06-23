from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path

import numpy as np

from .diagnostics import save_elevation_analysis_figure
from .filters import score_terrain
from .gebco import GEBCOGrid
from .geology import GeologyIndex
from .geometry import spherical_candidate
from .imagery import score_normalized_patch, write_stac_request_manifest


DEFAULT_GEBCO = "/Users/craig/ECDO/GIS/GEBCO_2026_sub_ice/GEBCO_2026_sub_ice.nc"
DEFAULT_GEOLOGY = "/Users/craig/ECDO/GIS/global_gprv.kml"


def load_candidates(path: str | Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [spherical_candidate(feature, i) for i, feature in enumerate(data["features"])]


def combined_score(metrics: dict) -> float:
    # Interpretable provisional score. It is explicitly a follow-up score, not
    # a probability of impact, and should later be replaced by calibrated weights.
    topo = metrics["topography_score_unweighted"]
    geology = metrics["geology_independence"]
    imagery = metrics.get("imagery_score")
    if imagery is None or not math.isfinite(imagery):
        evidence = 0.78 * topo + 0.22 * geology
    else:
        evidence = 0.58 * topo + 0.22 * geology + 0.20 * imagery
    return float(metrics["data_quality"] * evidence)


def json_clean(value):
    if isinstance(value, dict):
        return {key: json_clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_clean(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def save_diagnostic(candidate, metrics, diagnostic, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    save_elevation_analysis_figure(candidate.candidate_id, candidate.name, metrics, diagnostic, output_dir / f"{candidate.candidate_id}.png")
    np.savez_compressed(
        output_dir / f"{candidate.candidate_id}.npz",
        elevation=diagnostic["elevation"],
        residual=diagnostic["residual"],
        rho=diagnostic["rho"],
        radial_gradient=diagnostic["radial_gradient"],
        metrics=json.dumps(metrics),
    )


def write_outputs(rows: list[dict], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda row: row["followup_score"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    fields = sorted({key for row in rows for key in row})
    with (output_dir / "arc_ranking.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    features = []
    for row in rows:
        props = {k: v for k, v in row.items() if k not in {"lon", "lat"}}
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                "properties": props,
            }
        )
    (output_dir / "arc_ranking.geojson").write_text(
        json.dumps(json_clean({"type": "FeatureCollection", "features": features}), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    summary = {
        "candidate_count": len(rows),
        "score_quantiles": {
            str(q): float(np.quantile([r["followup_score"] for r in rows], q))
            for q in [0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1]
        },
        "top_20": [
            {k: row[k] for k in ["rank", "candidate_id", "name", "followup_score", "diameter_km", "data_quality"]}
            for row in rows[:20]
        ],
        "interpretation": "Follow-up priority only; not a probability of impact.",
    }
    (output_dir / "ranking_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def rows_from_csv(path: str | Path) -> list[dict]:
    rows = []
    text_fields = {"candidate_id", "name", "geology_nearby_types", "imagery_path"}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for source in csv.DictReader(handle):
            row = {}
            for key, value in source.items():
                if key in text_fields:
                    row[key] = value
                elif value == "":
                    row[key] = None
                else:
                    try:
                        number = float(value)
                        row[key] = number
                    except ValueError:
                        row[key] = value
            rows.append(row)
    return rows


def run(args):
    if args.finalize_csv:
        write_outputs(rows_from_csv(args.finalize_csv), Path(args.output))
        return
    candidates = load_candidates(args.arcs)
    if args.candidate_ids:
        selected_ids = {value.strip() for value in args.candidate_ids.split(",") if value.strip()}
        candidates = [candidate for candidate in candidates if candidate.candidate_id in selected_ids]
    if args.start:
        candidates = candidates[args.start :]
    if args.limit is not None:
        candidates = candidates[: args.limit]
    geology = GeologyIndex(args.geology)
    rows = []
    diagnostics = []
    start = time.time()
    with GEBCOGrid(args.gebco) as grid:
        for position, candidate in enumerate(candidates, 1):
            window = grid.read_candidate(candidate, roi_factor=args.roi_factor, max_pixels=args.max_pixels)
            terrain_metrics, diagnostic = score_terrain(candidate, window)
            metrics = {
                "candidate_id": candidate.candidate_id,
                "source_index": candidate.index,
                "name": candidate.name,
                "lon": candidate.lon,
                "lat": candidate.lat,
                "radius_km": candidate.radius_km,
                "diameter_km": candidate.diameter_km,
                "geometry_relative_radial_mad": candidate.relative_radial_mad,
                "geometry_angular_coverage": candidate.angular_coverage,
                **terrain_metrics,
                **geology.score(candidate),
            }
            if args.imagery_dir:
                patch = Path(args.imagery_dir) / f"{candidate.candidate_id}.png"
                if patch.exists():
                    metrics.update(score_normalized_patch(patch))
            metrics["followup_score"] = combined_score(metrics)
            rows.append(metrics)
            diagnostics.append((candidate, metrics, diagnostic))
            if position % 25 == 0 or position == len(candidates):
                elapsed = time.time() - start
                print(f"Processed {position}/{len(candidates)} candidates in {elapsed:.1f}s", flush=True)

    output_dir = Path(args.output)
    write_outputs(rows, output_dir)
    if args.diagnostics > 0:
        selected = sorted(diagnostics, key=lambda item: item[1]["followup_score"], reverse=True)[: args.diagnostics]
        for candidate, metrics, diagnostic in selected:
            save_diagnostic(candidate, metrics, diagnostic, output_dir / "diagnostics")
    write_stac_request_manifest(candidates, output_dir / "sentinel2_stac_requests.json")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arcs", default="arcuate_geometries.geojson")
    p.add_argument("--gebco", default=DEFAULT_GEBCO)
    p.add_argument("--geology", default=DEFAULT_GEOLOGY)
    p.add_argument("--output", default="ranking_output")
    p.add_argument("--imagery-dir", default=None)
    p.add_argument("--candidate-ids", default=None, help="Comma-separated candidate ids to process")
    p.add_argument("--finalize-csv", default=None, help="Rebuild GeoJSON and summary from an existing ranking CSV")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--roi-factor", type=float, default=1.75)
    p.add_argument("--max-pixels", type=int, default=512)
    p.add_argument("--diagnostics", type=int, default=20)
    return p


def main():
    run(parser().parse_args())


if __name__ == "__main__":
    main()
