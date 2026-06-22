#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from arc_ranker.crust import Crust1Sampler
from arc_ranker.evidence import score_scalar_ring, score_tid
from arc_ranker.geometry import spherical_candidate
from arc_ranker.grids import NpyRegularGrid, RegularGrid


DEFAULT_TID = "/Users/craig/ECDO/GIS/gebco_2026_tid/GEBCO_2026_TID.nc"
DEFAULT_WGM = "/Users/craig/ECDO/GIS/WGM2012"
DEFAULT_GLOBSED = "/Users/craig/ECDO/GIS/globsed/1.1/data/0-data/GlobSed/GlobSed_package3/GlobSed-v3.nc"
DEFAULT_CRUST = "/Users/craig/ECDO/GIS/CRUST"


def load_candidates(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [spherical_candidate(feature, i) for i, feature in enumerate(data["features"])]


def rows_from_csv(path):
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
                        row[key] = float(value)
                    except ValueError:
                        row[key] = value
            rows.append(row)
    return rows


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


def fingerprint(path: Path):
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
    return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256_first_mib": digest.hexdigest()}


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def open_sources(args):
    sources = {
        "tid": RegularGrid(args.tid, "tid"),
        "gravity_bouguer": RegularGrid(Path(args.wgm) / "WGM2012_Bouguer_ponc_2min.grd", "z", "x", "y"),
        "gravity_freeair": RegularGrid(Path(args.wgm) / "WGM2012_Freeair_ponc_2min.grd", "z", "x", "y"),
        "gravity_isostatic": RegularGrid(Path(args.wgm) / "WGM2012_Isostatic_ponc_2min.grd", "z", "x", "y"),
        "gravity_disturbance": RegularGrid(Path(args.wgm) / "WGM2012_Disturbance_ponc_2min.grd", "z", "x", "y"),
        "sediment": RegularGrid(args.globsed, "z"),
        "crust": Crust1Sampler(args.crust),
    }
    emag = Path(args.emag_cache)
    if (emag / "emag2_anomaly.npy").exists():
        sources["magnetic"] = NpyRegularGrid(
            emag / "emag2_anomaly.npy", emag / "emag2_lon.npy", emag / "emag2_lat.npy"
        )
    return sources


def close_sources(sources):
    for source in sources.values():
        source.close()


def run(args):
    candidates = load_candidates(args.arcs)
    base_rows = {row["candidate_id"]: row for row in rows_from_csv(args.ranking)}
    if args.candidate_ids:
        wanted = {value.strip() for value in args.candidate_ids.split(",") if value.strip()}
        candidates = [candidate for candidate in candidates if candidate.candidate_id in wanted]
    if args.limit is not None:
        candidates = candidates[: args.limit]

    sources = open_sources(args)
    evidence_rows, merged_rows = [], []
    started = time.time()
    try:
        for position, candidate in enumerate(candidates, 1):
            evidence = {
                "candidate_id": candidate.candidate_id,
                "source_index": candidate.index,
                "lon": candidate.lon,
                "lat": candidate.lat,
                "diameter_km": candidate.diameter_km,
            }
            evidence.update(score_tid(candidate, sources["tid"].read_candidate(candidate, args.roi_factor, args.max_pixels)))
            for name in ("gravity_bouguer", "gravity_freeair", "gravity_isostatic", "gravity_disturbance"):
                window = sources[name].read_candidate(candidate, args.roi_factor, args.max_pixels)
                evidence.update(score_scalar_ring(candidate, window, name))
            if "magnetic" in sources:
                evidence.update(score_scalar_ring(candidate, sources["magnetic"].read_candidate(candidate, args.roi_factor, args.max_pixels), "magnetic"))
            evidence.update(score_scalar_ring(candidate, sources["sediment"].read_candidate(candidate, args.roi_factor, args.max_pixels), "sediment"))
            evidence.update(sources["crust"].sample(candidate.lon, candidate.lat))
            evidence_rows.append(evidence)
            merged = dict(base_rows.get(candidate.candidate_id, {}))
            merged.update(evidence)
            merged_rows.append(merged)
            if position % 25 == 0 or position == len(candidates):
                print(f"Enriched {position}/{len(candidates)} in {time.time() - started:.1f}s", flush=True)
    finally:
        close_sources(sources)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "geophysical_evidence.csv", evidence_rows)
    write_csv(output / "arc_ranking_enriched.csv", merged_rows)
    source_paths = [
        Path(args.tid),
        *sorted(Path(args.wgm).glob("*.grd")),
        Path(args.globsed),
        *sorted(Path(args.crust).glob("*.nc")),
    ]
    if (Path(args.emag_cache) / "emag2_anomaly.npy").exists():
        source_paths.extend(sorted(Path(args.emag_cache).glob("*")))
    summary = {
        "candidate_count": len(evidence_rows),
        "elapsed_seconds": time.time() - started,
        "score_policy": "Evidence channels are retained separately; the existing followup_score is not modified.",
        "source_fingerprints": [fingerprint(path) for path in source_paths],
        "metric_notes": {
            "tid_artifact_risk": "Heuristic source-transition alignment, not a calibrated artefact probability.",
            "gravity_*_ring_score": "Resolution-weighted circular-anisotropy evidence, not an impact probability.",
            "magnetic_ring_score": "Resolution-weighted EMAG2 v3 column-6 anomaly evidence upward-continued to 4 km altitude; not an impact probability.",
            "sediment_ring_score": "Contextual circular sediment pattern; causation is unspecified.",
            "crust1_*": "Nearest 1-degree contextual cell; not candidate-scale evidence.",
        },
    }
    (output / "evidence_summary.json").write_text(json.dumps(json_clean(summary), indent=2) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description="Add local acquisition-quality and geophysical evidence to the arc ranking.")
    p.add_argument("--arcs", default="arcuate_geometries.geojson")
    p.add_argument("--ranking", default="ranking_output/arc_ranking.csv")
    p.add_argument("--output", default="geophysical_output")
    p.add_argument("--tid", default=DEFAULT_TID)
    p.add_argument("--wgm", default=DEFAULT_WGM)
    p.add_argument("--globsed", default=DEFAULT_GLOBSED)
    p.add_argument("--crust", default=DEFAULT_CRUST)
    p.add_argument("--emag-cache", default="geophysical_cache/emag2")
    p.add_argument("--candidate-ids", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--roi-factor", type=float, default=1.75)
    p.add_argument("--max-pixels", type=int, default=384)
    return p


if __name__ == "__main__":
    run(parser().parse_args())
