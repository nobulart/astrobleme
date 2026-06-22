#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path


EARTH_RADIUS_KM = 6371.0088
DUPLICATE_EXCLUSIONS = {
    45: (46, "Possible-list Cerro do Jarau duplicates the confirmed-list record."),
    102: (101, "Possible-list Rochechouart record duplicates the confirmed-list record."),
    118: (116, "Possible-list Shiyli record duplicates the confirmed-list Chiyli record."),
    129: (240, "Wikipedia Temimichat duplicates the more explicit Reimold & Koeberl Temimichat Ghallaman record."),
}


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def clean_wiki_name(cell):
    match = re.search(r"\[\[([^\]]+)\]\]", cell)
    if match:
        parts = match.group(1).split("|")
        return re.sub(r"<.*?>", "", parts[-1]).strip()
    return re.sub(r"\{\{.*?\}\}|<.*?>", "", cell).strip()


def visible_sort_value(cell):
    match = re.search(r"\{\{\s*sort\s*\|[^|{}]*\|([^{}]+)\}\}", cell, re.I)
    return match.group(1).strip() if match else cell


def parse_number(text):
    text = visible_sort_value(str(text)).replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def parse_plain_numeric(text):
    text = str(text).strip().replace(",", "")
    return float(text) if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text) else None


def parse_wiki_tables(path):
    rows = []
    current = None
    in_table = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("{| ") or line.startswith("{|"):
            in_table = True
        elif in_table and line.startswith("|-"):
            if current:
                rows.append(current)
            current = []
        elif in_table and line.startswith("|}"):
            if current:
                rows.append(current)
            current = None
            in_table = False
        elif in_table and current is not None and line.startswith("|") and not line.startswith("||"):
            current.append(line[1:].strip())
    parsed = []
    for cells in rows:
        if len(cells) < 4:
            continue
        name = clean_wiki_name(cells[0])
        diameter = parse_number(cells[3])
        coordinates = []
        for cell in cells:
            for match in re.finditer(r"\{\{\s*coord\s*\|(.+?)\}\}", cell, re.I):
                coordinate = parse_coord(match.group(1))
                if coordinate:
                    coordinates.append(coordinate)
        if name:
            parsed.append({"name": name, "diameter_km": diameter, "coordinates": coordinates, "cells": cells})
    return parsed


def parse_coord(arguments):
    parts = [part.strip() for part in arguments.split("|")]
    positional = [part for part in parts if "=" not in part and part.upper() not in {"N", "S", "E", "W"}]
    directions = [(i, part.upper()) for i, part in enumerate(parts) if part.upper() in {"N", "S", "E", "W"}]
    if len(directions) < 2:
        return None
    try:
        lat_dir_index, lat_dir = directions[0]
        lon_dir_index, lon_dir = directions[1]
        lat_values = [float(x) for x in parts[:lat_dir_index] if re.fullmatch(r"\d+(?:\.\d+)?", x)]
        lon_values = [float(x) for x in parts[lat_dir_index + 1 : lon_dir_index] if re.fullmatch(r"\d+(?:\.\d+)?", x)]
        def decimal(values, direction):
            value = values[0] + (values[1] / 60 if len(values) > 1 else 0) + (values[2] / 3600 if len(values) > 2 else 0)
            return -value if direction in {"S", "W"} else value
        return decimal(lat_values, lat_dir), decimal(lon_values, lon_dir)
    except (ValueError, IndexError):
        return None


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def circle_geometry(lon, lat, diameter_km, vertices=96):
    angular = diameter_km / 2 / EARTH_RADIUS_KM
    phi1, lam1 = math.radians(lat), math.radians(lon)
    points = []
    for i in range(vertices + 1):
        bearing = 2 * math.pi * i / vertices
        phi2 = math.asin(math.sin(phi1) * math.cos(angular) + math.cos(phi1) * math.sin(angular) * math.cos(bearing))
        lam2 = lam1 + math.atan2(
            math.sin(bearing) * math.sin(angular) * math.cos(phi1),
            math.cos(angular) - math.sin(phi1) * math.sin(phi2),
        )
        point_lon = (math.degrees(lam2) + 180) % 360 - 180
        points.append([round(point_lon, 7), round(math.degrees(phi2), 7)])
    return {"type": "MultiLineString", "coordinates": [points]}


def source_match(props, wiki_rows):
    candidates = wiki_rows.get(normalize(props["name"]), [])
    if not candidates:
        nearest = []
        for row in wiki_rows.get("__all__", []):
            for lat, lon in row["coordinates"]:
                nearest.append((haversine(props["center_lat"], props["center_lon"], lat, lon), row))
        if nearest:
            distance, row = min(nearest, key=lambda item: item[0])
            if distance <= 5:
                return row, "verified_by_coordinate_alias_within_5_km", distance
        return None, "not_found_in_2026_snapshot", None
    local_diameter = parse_number(props.get("diameter_raw"))
    candidates.sort(key=lambda row: abs((row["diameter_km"] or math.inf) - (local_diameter or 0)))
    row = candidates[0]
    distances = [
        haversine(props["center_lat"], props["center_lon"], lat, lon) for lat, lon in row["coordinates"]
    ]
    distance = min(distances) if distances else None
    coordinate_status = "verified_within_5_km" if distance is not None and distance <= 5 else (
        "source_has_no_coordinate" if distance is None else "coordinate_review_required"
    )
    return row, coordinate_status, distance


def fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest}


def run(args):
    original = json.loads(Path(args.input).read_text(encoding="utf-8"))
    repaired = deepcopy(original)
    confirmed = parse_wiki_tables(args.confirmed_snapshot)
    possible = parse_wiki_tables(args.possible_snapshot)
    wiki_maps = {
        "Wikipedia confirmed impact structures": defaultdict(list),
        "Wikipedia possible impact structures": defaultdict(list),
    }
    for row in confirmed:
        wiki_maps["Wikipedia confirmed impact structures"][normalize(row["name"])].append(row)
        wiki_maps["Wikipedia confirmed impact structures"]["__all__"].append(row)
    for row in possible:
        wiki_maps["Wikipedia possible impact structures"][normalize(row["name"])].append(row)
        wiki_maps["Wikipedia possible impact structures"]["__all__"].append(row)

    source_row_counts = Counter(
        (f["properties"].get("source_url"), f["properties"].get("source_table_index"), f["properties"]["name"])
        for f in repaired["features"]
    )
    global_name_counts = Counter(f["properties"]["name"] for f in repaired["features"])
    audit = []
    for index, feature in enumerate(repaired["features"]):
        props = feature["properties"]
        old_diameter = float(props["diameter_km"])
        rendered_diameter = parse_plain_numeric(props.get("diameter_raw"))
        diameter_changed = rendered_diameter is not None and not math.isclose(rendered_diameter, old_diameter, rel_tol=1e-9, abs_tol=1e-9)
        source_row = None
        coordinate_status = "pdf_source_preserved"
        coordinate_distance = None
        source_diameter = None
        if props["source"] in wiki_maps:
            source_row, coordinate_status, coordinate_distance = source_match(props, wiki_maps[props["source"]])
            source_diameter = source_row["diameter_km"] if source_row else None
        diameter_verified = source_diameter is not None and rendered_diameter is not None and math.isclose(
            source_diameter, rendered_diameter, rel_tol=1e-9, abs_tol=1e-9
        )
        if diameter_changed:
            props["diameter_km_original"] = old_diameter
            props["diameter_km"] = rendered_diameter
            props["diameter_repair_status"] = "verified_against_2026_wikipedia_snapshot" if diameter_verified else "repaired_from_preserved_rendered_value"
            feature["geometry"] = circle_geometry(
                float(props["center_lon"]), float(props["center_lat"]), rendered_diameter, int(props.get("circle_vertices", 96))
            )
        else:
            props["diameter_repair_status"] = "unchanged"

        old_display = props.get("display_name", props["name"])
        row_key = (props.get("source_url"), props.get("source_table_index"), props["name"])
        if source_row_counts[row_key] > 1 and props.get("coordinate_title"):
            display = f"{props['name']} — {props['coordinate_title']}"
        elif global_name_counts[props["name"]] > 1:
            display = f"{props['name']} — {props.get('location') or props.get('country')}"
        else:
            display = props["name"]
        if display != old_display:
            props["display_name_original"] = old_display
            props["display_name"] = display
        props["catalogue_record_id"] = f"astro_{index:04d}"
        props["coordinate_audit_status"] = coordinate_status
        if coordinate_distance is not None:
            props["coordinate_source_distance_km"] = round(coordinate_distance, 3)
        props["analytical_include"] = index not in DUPLICATE_EXCLUSIONS
        props["duplicate_of_record_id"] = (
            f"astro_{DUPLICATE_EXCLUSIONS[index][0]:04d}" if index in DUPLICATE_EXCLUSIONS else None
        )
        props["duplicate_resolution_note"] = DUPLICATE_EXCLUSIONS[index][1] if index in DUPLICATE_EXCLUSIONS else None
        props["catalogue_repair_version"] = "2026-06-21"
        audit.append({
            "record_id": props["catalogue_record_id"],
            "source_index": index,
            "name": props["name"],
            "source": props["source"],
            "old_display_name": old_display,
            "repaired_display_name": display,
            "old_diameter_km": old_diameter,
            "rendered_diameter_raw": props.get("diameter_raw"),
            "repaired_diameter_km": props["diameter_km"],
            "diameter_changed": diameter_changed,
            "diameter_source_verified": diameter_verified,
            "coordinate_status": coordinate_status,
            "coordinate_source_distance_km": coordinate_distance,
            "analytical_include": props["analytical_include"],
            "duplicate_of_record_id": props["duplicate_of_record_id"],
            "duplicate_resolution_note": props["duplicate_resolution_note"],
        })

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "astroblemes_repaired.geojson").write_text(json.dumps(repaired, indent=2) + "\n", encoding="utf-8")
    analytical = deepcopy(repaired)
    analytical["features"] = [f for f in analytical["features"] if f["properties"]["analytical_include"]]
    (output / "astroblemes_analysis.geojson").write_text(json.dumps(analytical, indent=2) + "\n", encoding="utf-8")
    with (output / "catalogue_repair_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    summary = {
        "original_records": len(original["features"]),
        "repaired_records": len(repaired["features"]),
        "analytical_unique_records": len(analytical["features"]),
        "diameters_changed": sum(row["diameter_changed"] for row in audit),
        "changed_diameters_verified_against_2026_wikipedia": sum(row["diameter_changed"] and row["diameter_source_verified"] for row in audit),
        "display_names_changed": sum(row["old_display_name"] != row["repaired_display_name"] for row in audit),
        "coordinates_verified_within_5_km": sum(row["coordinate_status"] == "verified_within_5_km" for row in audit),
        "coordinates_verified_by_alias_within_5_km": sum(row["coordinate_status"] == "verified_by_coordinate_alias_within_5_km" for row in audit),
        "wikipedia_coordinates_requiring_review": sum(row["coordinate_status"] == "coordinate_review_required" for row in audit),
        "duplicate_records_excluded": len(DUPLICATE_EXCLUSIONS),
        "policy": "Original catalogue is unchanged. Row-preserving repaired and deduplicated analytical catalogues are separate outputs.",
        "source_fingerprints": [
            fingerprint(args.input), fingerprint(args.confirmed_snapshot), fingerprint(args.possible_snapshot), fingerprint(args.africa_pdf)
        ],
    }
    (output / "catalogue_repair_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def parser():
    p = argparse.ArgumentParser(description="Repair imported diameters and identities while preserving complete provenance.")
    p.add_argument("--input", default="astroblemes.geojson")
    p.add_argument("--confirmed-snapshot", default="catalog_repair/sources/wikipedia_confirmed_2026-06-21.wiki")
    p.add_argument("--possible-snapshot", default="catalog_repair/sources/wikipedia_possible_2026-06-21.wiki")
    p.add_argument("--africa-pdf", default="/Users/craig/ECDO/RAG/Impact structures in Africa.pdf")
    p.add_argument("--output-dir", default="catalog_repair")
    return p


if __name__ == "__main__":
    run(parser().parse_args())
