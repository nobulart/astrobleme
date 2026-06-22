#!/usr/bin/env python3
"""Build compact, provenance-rich planetary comparison tables from local sources.

Transcribed ring measurements are intentionally limited to clearly legible published
tables. They are geometric comparison data, not evidence for terrestrial origin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


GRAIL_LUNAR_MULTIRING = [
    # name, certainty, main, main lat/lon, intermediate, lat/lon, inner, lat/lon, depression, lat/lon
    ("Hertzsprung", "probable", 571, 1.92, 230.94, 408, 2.22, 231.13, 256, 2.00, 231.22, 108, 2.04, 231.22),
    ("Humboldtianum", "possible", 618, 57.27, 82.01, 463, 57.30, 83.00, 322, 57.75, 82.84, 197, 57.80, 82.71),
    ("Mendel-Rydberg", "certain", 650, -49.53, 266.08, 485, -49.67, 265.56, 325, -49.69, 265.47, 203, -49.91, 265.67),
    ("Coulomb-Sarton", "possible", 672, 51.26, 236.93, 401, 51.20, 236.99, 315, 51.24, 237.48, 158, 51.16, 237.41),
    ("Humorum", "probable", 816, -23.69, 320.86, 569, -23.89, 320.74, 441, -24.28, 320.62, 322, -23.92, 320.67),
    ("Smythii", "possible", 878, -2.51, 86.92, 484, -1.92, 87.25, None, None, None, 375, -1.71, 87.36),
    ("Nectaris", "certain", 885, -15.61, 35.13, 623, -15.39, 34.39, 440, -15.44, 34.33, 270, -15.43, 34.01),
    ("Serenitatis", "possible", 923, 26.46, 19.24, 661, 26.48, 18.85, 416, 25.19, 18.81, None, None, None),
    ("Orientale", "certain", 937, -20.10, 265.14, 639, -19.44, 265.32, 481, -19.01, 265.31, 341, -19.01, 265.54),
    ("Crisium", "probable", 1076, 17.27, 59.64, 809, 17.29, 59.79, 505, 16.81, 58.41, 364, 16.92, 58.50),
    ("Imbrium", "probable", 1321, 36.51, 341.85, 1012, 37.87, 340.74, 676, 37.26, 341.34, None, None, None),
]

# Clearly legible classical basin rows from Pike & Spudis (1987), Table I.
# Bracket/parenthesis confidence notation is preserved separately. These old outer
# ring interpretations should not be treated as a modern consensus catalogue.
PIKE_SPUDIS_MARS = [
    ("Argyre", -50.0, 317.0, [410, 630, 800, 1100, 1360, 1900], "possible;certain;certain;probable;probable;probable"),
    ("Isidis", 13.0, 88.0, [700, 1500, 3000, 3800], "certain;certain;certain;possible"),
    ("Hellas", -41.0, 65.0, [840, 1200, 1700, 2200, 3100, 4400, 5500], "probable;probable;probable;certain;certain;certain;possible"),
]


def ratios(diameters: list[float]) -> list[float]:
    ordered = sorted(float(value) for value in diameters if value is not None and value > 0)
    return [round(ordered[index + 1] / ordered[index], 6) for index in range(len(ordered) - 1)]


def build_lunar_multiring() -> pd.DataFrame:
    columns = ["name", "certainty", "main_ring_diameter_km", "main_ring_lat", "main_ring_lon_e",
               "intermediate_ring_diameter_km", "intermediate_ring_lat", "intermediate_ring_lon_e",
               "inner_ring_diameter_km", "inner_ring_lat", "inner_ring_lon_e",
               "inner_depression_diameter_km", "inner_depression_lat", "inner_depression_lon_e"]
    frame = pd.DataFrame(GRAIL_LUNAR_MULTIRING, columns=columns)
    ring_columns = ["inner_depression_diameter_km", "inner_ring_diameter_km",
                    "intermediate_ring_diameter_km", "main_ring_diameter_km"]
    frame["object"] = frame["name"]
    frame["diameter_km"] = frame["main_ring_diameter_km"]
    frame["ring_diameters_km"] = frame[ring_columns].apply(lambda row: json.dumps(sorted(float(v) for v in row.dropna())), axis=1)
    frame["ring_ratios"] = frame[ring_columns].apply(lambda row: json.dumps(ratios(list(row.dropna()))), axis=1)
    frame["number_of_nested_rings"] = frame[ring_columns].notna().sum(axis=1)
    frame["body"] = "Moon"
    frame["source_table"] = "Neumann et al. (2015), supplementary Tables S2-S3"
    frame["source_doi"] = "10.1126/sciadv.1500852"
    frame["interpretation"] = "published lunar multiring geometry; confidence field must be retained"
    return frame


def build_martian_basins() -> pd.DataFrame:
    rows = []
    for name, lat, lon_e, ring_diameters, confidence in PIKE_SPUDIS_MARS:
        ordered = sorted(ring_diameters)
        rows.append({"object": name, "body": "Mars", "lat": lat, "lon_e": lon_e,
                     "diameter_km": max(ordered), "ring_diameters_km": json.dumps(ordered),
                     "ring_ratios": json.dumps(ratios(ordered)), "number_of_nested_rings": len(ordered),
                     "ring_confidence_inner_to_outer": confidence,
                     "source_table": "Pike and Spudis (1987), Table I",
                     "source_doi": "10.1007/BF00054060",
                     "interpretation": "historical mapped ring interpretation; outer rings may be uncertain and names/limits may be superseded",
                     "selection_scope": "three clearly legible classical named basins; not a complete Martian crater catalogue"})
    return pd.DataFrame(rows)


def build_lunar_large(source: Path, minimum_km: float = 200.0) -> pd.DataFrame:
    chunks = []
    use = ["CRATER_ID", "LAT_CIRC_IMG", "LON_CIRC_IMG", "DIAM_CIRC_IMG", "DIAM_CIRC_SD_IMG", "ARC_IMG", "PTS_RIM_IMG"]
    for chunk in pd.read_csv(source, usecols=use, chunksize=100_000):
        chunks.append(chunk[pd.to_numeric(chunk["DIAM_CIRC_IMG"], errors="coerce") >= minimum_km])
    frame = pd.concat(chunks, ignore_index=True).rename(columns={
        "CRATER_ID": "crater_id", "LAT_CIRC_IMG": "lat", "LON_CIRC_IMG": "lon_e",
        "DIAM_CIRC_IMG": "diameter_km", "DIAM_CIRC_SD_IMG": "diameter_sd_km",
        "ARC_IMG": "mapped_arc_fraction", "PTS_RIM_IMG": "rim_point_count"})
    frame["body"] = "Moon"
    frame["source_doi"] = "10.17189/0arb-tg89"
    frame["catalogue_scope"] = f"Robbins 2018 lunar crater catalogue subset diameter >= {minimum_km:g} km; not a multiring classification"
    return frame.sort_values("diameter_km", ascending=False)


def build_venus(source: Path) -> pd.DataFrame:
    raw = pd.read_csv(source, header=None, usecols=[0, 1, 2, 3], names=["name", "lat", "lon_e", "diameter_km"])
    raw["name"] = raw["name"].astype("string").str.strip().replace("", pd.NA)
    raw["body"] = "Venus"
    raw["catalogue_scope"] = "USGS Venus crater database; named and unnamed entries; no ring classification in supplied table"
    return raw.sort_values("diameter_km", ascending=False)


def fingerprint(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def run(args: argparse.Namespace) -> None:
    source = Path(args.data); target = Path(args.output); target.mkdir(parents=True, exist_ok=True)
    lunar_multiring = build_lunar_multiring(); mars = build_martian_basins()
    lunar_large = build_lunar_large(source / "lunar_crater_database_robbins_2018.csv", args.minimum_lunar_km)
    venus = build_venus(source / "venus-craters.csv")
    lunar_multiring.to_csv(target / "lunar_multiring_basins.csv", index=False)
    mars.to_csv(target / "martian_basins.csv", index=False)
    lunar_large.to_csv(target / "lunar_large_craters.csv", index=False)
    venus.to_csv(target / "venus_craters.csv", index=False)
    source_files = sorted(source.glob("*"))
    manifest = {
        "purpose": "planetary geometry comparison only; terrestrial origin must not be inferred from scale or ring-ratio similarity",
        "outputs": {"lunar_multiring_basins.csv": len(lunar_multiring), "martian_basins.csv": len(mars),
                    "lunar_large_craters.csv": len(lunar_large), "venus_craters.csv": len(venus)},
        "source_files": [fingerprint(path) for path in source_files if path.is_file()],
        "limitations": ["Mars global crater catalogue data were not present; the downloaded PDF is its methods paper.",
                        "Martian ring rows are a deliberately small historical comparison subset.",
                        "Robbins lunar large-crater rows are not automatically multiring basins.",
                        "GRAIL possible/probable/certain classifications are preserved and must not be collapsed."],
    }
    (target / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["outputs"], indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Normalize locally supplied planetary crater and basin sources.")
    result.add_argument("--data", default="data"); result.add_argument("--output", default="planetary")
    result.add_argument("--minimum-lunar-km", type=float, default=200.0)
    return result


if __name__ == "__main__": run(parser().parse_args())
