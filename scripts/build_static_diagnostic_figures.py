#!/usr/bin/env python3
"""Build web-bundled elevation diagnostic figures for study candidates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arc_ranker.diagnostics import save_elevation_analysis_figure
from arc_ranker.filters import score_terrain
from arc_ranker.gebco import GEBCOGrid
from arc_ranker.geometry import spherical_candidate


def load_candidates(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [spherical_candidate(feature, index) for index, feature in enumerate(data["features"])]


def clean_value(value: str):
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    if not math.isfinite(number):
        return None
    return number


def metrics_by_candidate(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["candidate_id"]: {key: clean_value(value) for key, value in row.items()} for row in csv.DictReader(handle)}


def run(args: argparse.Namespace) -> int:
    candidates = load_candidates(args.arcs)
    if args.candidate_ids:
        wanted = {item.strip() for item in args.candidate_ids.split(",") if item.strip()}
        candidates = [candidate for candidate in candidates if candidate.candidate_id in wanted]
    metrics = metrics_by_candidate(args.ranking)
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.time()
    built = 0
    with GEBCOGrid(args.gebco) as grid:
        for index, candidate in enumerate(candidates, 1):
            output = args.output / f"{candidate.candidate_id}.webp"
            if args.skip_existing and output.exists():
                continue
            window = grid.read_candidate(candidate, roi_factor=args.roi_factor, max_pixels=args.max_pixels)
            terrain_metrics, diagnostic = score_terrain(candidate, window)
            figure_metrics = metrics.get(candidate.candidate_id, terrain_metrics)
            save_elevation_analysis_figure(candidate.candidate_id, candidate.name, figure_metrics, diagnostic, output, webp_quality=args.quality)
            built += 1
            if built % 25 == 0 or index == len(candidates):
                elapsed = time.time() - start
                print(f"Built {built} diagnostic figures ({index}/{len(candidates)} scanned) in {elapsed:.1f}s", flush=True)
    print(f"Built {built} diagnostic figures in {time.time() - start:.1f}s", flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arcs", type=Path, default=ROOT / "study_results_geojson" / "arcuate_geometries_study_results.geojson")
    p.add_argument("--ranking", type=Path, default=ROOT / "ranking_output" / "arc_ranking.csv")
    p.add_argument("--gebco", type=Path, default=Path(os.environ.get("GEBCO_GRID_PATH", "/Users/craig/ECDO/GIS/GEBCO_2026_sub_ice/GEBCO_2026_sub_ice.nc")))
    p.add_argument("--output", type=Path, default=ROOT / "webapp" / "static" / "portal" / "diagnostics" / "study")
    p.add_argument("--candidate-ids", default="")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--roi-factor", type=float, default=1.75)
    p.add_argument("--max-pixels", type=int, default=512)
    p.add_argument("--quality", type=int, default=68)
    return p


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
