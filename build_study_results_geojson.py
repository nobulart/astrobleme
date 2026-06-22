#!/usr/bin/env python3
"""Build a row-preserving GeoJSON handoff for all arcuate study records."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA_VERSION = "1.0.0"

MANUAL_FIELDS = {
    "manual_capture_complete": ("boolean", "True only after the required manual review fields have been checked."),
    "manual_review_status": ("string", "Pending, in_review, complete, deferred or rejected."),
    "manual_interpreter": ("string", "Name or identifier of the person completing the review."),
    "manual_review_date": ("date", "Review date in ISO YYYY-MM-DD format."),
    "manual_source_type": ("string", "Original evidence type, such as GEBCO, aerial imagery, geological map or publication."),
    "manual_source_title": ("string", "Human-readable title of the source inspected."),
    "manual_source_uri": ("string", "Stable URL, DOI, catalogue identifier or local source reference."),
    "manual_source_accessed_date": ("date", "Date the source was accessed, ISO YYYY-MM-DD."),
    "manual_source_scale_or_resolution": ("string", "Map scale or raster/imagery spatial resolution."),
    "manual_imagery_provider": ("string", "Aerial or satellite imagery provider."),
    "manual_imagery_scene_id": ("string", "Scene, tile or acquisition identifier."),
    "manual_imagery_acquisition_date": ("date", "Imagery acquisition date, ISO YYYY-MM-DD where known."),
    "manual_imagery_resolution_m": ("number", "Imagery ground-sample distance in metres."),
    "manual_original_trace_available": ("boolean", "Whether the unbuffered/original observed trace is available."),
    "manual_original_trace_reference": ("string", "File, layer or feature identifier for the original trace."),
    "manual_trace_confidence": ("string", "Interpreter confidence in the observed arcuate trace."),
    "manual_angular_extent_degrees": ("number", "Manually verified angular extent of the observed arc."),
    "manual_feature_class": ("string", "Observed feature class, e.g. scarp, ridge, drainage, coastline, contact or artefact."),
    "manual_geologic_unit": ("string", "Mapped geological unit at or around the candidate."),
    "manual_lithology": ("string", "Dominant mapped or observed lithology."),
    "manual_stratigraphic_age": ("string", "Mapped geological or stratigraphic age."),
    "manual_structural_setting": ("string", "Tectonic, basin, volcanic, cratonic or other structural setting."),
    "manual_geological_boundary_description": ("string", "Description of relevant contacts, faults or province boundaries."),
    "manual_endogenic_alternative": ("string", "Best-supported non-impact explanation, if any."),
    "manual_candidate_interpretation": ("string", "Current geological interpretation without implying confirmation."),
    "manual_inclusion_reason": ("string", "Original or retrospective reason the geometry belongs in the inventory."),
    "manual_exclusion_reason": ("string", "Reason for exclusion or deprioritisation, if applicable."),
    "manual_outcrop_accessibility": ("string", "Accessibility of relevant outcrop, core or sampling locations."),
    "manual_field_priority": ("string", "Manual field-follow-up priority, using a documented local vocabulary."),
    "manual_field_checked": ("boolean", "Whether field, core or archived-sample evidence has been checked."),
    "manual_shock_evidence": ("string", "Observed diagnostic shock evidence, explicitly including negative or absent results."),
    "manual_sample_or_core_reference": ("string", "Sample, borehole, core, thin-section or archive reference."),
    "manual_citation": ("string", "Primary citation supporting the manual interpretation."),
    "manual_validation_notes": ("string", "QA notes, disagreements or uncertainty requiring resolution."),
    "manual_notes": ("string", "Additional free-text notes."),
}

STRUCTURE_FIELDS = [
    "structure_review_rank", "representative_candidate_id", "representative_name", "lon", "lat",
    "radius_km", "diameter_km", "member_count", "member_candidate_ids", "radius_min_km",
    "radius_max_km", "followup_score", "review_tier", "domain", "geology_independence",
    "geology_boundary_coincidence", "geology_nearby_types", "tid_artifact_risk",
    "active_fault_coverage", "nearest_active_fault_km", "nearest_active_fault_name",
    "nearest_active_fault_slip_type", "fault_length_within_radius_km", "fault_intersects_candidate",
    "fault_search_degrees", "active_fault_proximity_ratio", "fault_control_flag",
]


def clean(value):
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")


def row_dict(row):
    return {k: clean(v) for k, v in row.to_dict().items()}


def inferred_type(values):
    nonnull = [v for v in values if v is not None]
    if not nonnull:
        return "null"
    types = {"boolean" if isinstance(v, bool) else "integer" if isinstance(v, int) else
             "number" if isinstance(v, float) else "string" if isinstance(v, str) else "object" for v in nonnull}
    if types <= {"integer", "number"}:
        return "number"
    return next(iter(types)) if len(types) == 1 else "mixed"


def fingerprint(path):
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return {"path": str(p), "sha256": h.hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="arcuate_geometries.geojson")
    ap.add_argument("--enriched", default="geophysical_output/arc_ranking_enriched.csv")
    ap.add_argument("--review", default="geophysical_output/geophysical_review_priority.csv")
    ap.add_argument("--membership", default="structure_output/candidate_to_structure.csv")
    ap.add_argument("--structures", default="structure_output/structure_ranking.csv")
    ap.add_argument("--outdir", default="study_results_geojson")
    args = ap.parse_args()

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    source = json.loads(Path(args.source).read_text())
    enriched = pd.read_csv(args.enriched).sort_values("source_index")
    review = pd.read_csv(args.review).set_index("candidate_id", drop=False)
    membership = pd.read_csv(args.membership).set_index("candidate_id", drop=False)
    structures = pd.read_csv(args.structures).set_index("structure_id", drop=False)

    n = len(source["features"])
    expected = set(range(n))
    actual = set(enriched.source_index.astype(int))
    if len(enriched) != n or actual != expected or enriched.candidate_id.nunique() != n:
        raise ValueError("Candidate ranking does not map one-to-one to source feature order")
    if not set(enriched.candidate_id).issubset(review.index) or not set(enriched.candidate_id).issubset(membership.index):
        raise ValueError("Review or structure membership table is missing candidates")

    review_extra = [c for c in review.columns if c not in enriched.columns or c in
                    {"geophysical_review_rank", "review_tier", "domain", "gravity_consensus_percentile",
                     "magnetic_ring_score_stratified_percentile"}]
    features = []
    for candidate in enriched.itertuples(index=False):
        e = row_dict(pd.Series(candidate._asdict()))
        cid, source_index = e["candidate_id"], int(e["source_index"])
        original = source["features"][source_index]
        props = {
            "schema_version": SCHEMA_VERSION,
            "record_grain": "one original arcuate geometry",
            "candidate_id": cid,
            "source_index": source_index,
            "source_name": clean((original.get("properties") or {}).get("Name")),
            "source_description": clean((original.get("properties") or {}).get("Description")),
            "source_geometry_type_original": clean((original.get("properties") or {}).get("source_geometry_type")),
            "score_interpretation": "follow-up priority; not impact probability",
            "geometry_interpretation": "visually identified arcuate geometry; not a confirmed crater or shock boundary",
            "geophysics_interpretation": "screening concordance; circular anomalies are physically plausible but non-diagnostic",
        }
        # Retain every candidate-level metric under its established pipeline name.
        props.update(e)
        r = row_dict(review.loc[cid])
        for field in review_extra:
            props[field] = r[field]
        m = row_dict(membership.loc[cid])
        sid = m["structure_id"]
        props["structure_id"] = sid
        props["structure_is_representative"] = m["is_representative"]
        s = row_dict(structures.loc[sid])
        for field in STRUCTURE_FIELDS:
            props[f"structure_{field}"] = s[field]
        for field in MANUAL_FIELDS:
            props[field] = False if field == "manual_capture_complete" else None
        features.append({"type": "Feature", "id": cid, "geometry": copy.deepcopy(original["geometry"]),
                         "properties": props})

    collection = {
        "type": "FeatureCollection",
        "name": "arcuate_geometries_study_results",
        "schema_version": SCHEMA_VERSION,
        "generated_date": date.today().isoformat(),
        "record_grain": "one feature per original arcuate geometry",
        "feature_count": len(features),
        "manual_fields_are_null_until_reviewed": True,
        "source_files": [fingerprint(args.source), fingerprint(args.enriched), fingerprint(args.review),
                         fingerprint(args.membership), fingerprint(args.structures)],
        "interpretive_limits": [
            "followup scores are review priorities, not impact probabilities",
            "circular morphology and geophysical concordance are non-diagnostic",
            "structure-prefixed fields have consolidated-structure grain",
            "mapped active-fault absence does not exclude tectonic control",
        ],
        "features": features,
    }
    output = outdir / "arcuate_geometries_study_results.geojson"
    output.write_text(json.dumps(collection, ensure_ascii=False, allow_nan=False, separators=(",", ":")))

    all_fields = list(features[0]["properties"])
    dictionary = []
    for field in all_fields:
        values = [f["properties"].get(field) for f in features]
        if field in MANUAL_FIELDS:
            category, description, dtype = "manual_capture", MANUAL_FIELDS[field][1], MANUAL_FIELDS[field][0]
        elif field.startswith("structure_"):
            category, description, dtype = "structure_level", "Structure-level field repeated for each member candidate.", inferred_type(values)
        elif field.startswith("gravity_") or field.startswith("magnetic_") or field.startswith("sediment_") or field.startswith("tid_") or field.startswith("crust1_"):
            category, description, dtype = "geophysical_screening", "Derived candidate-level screening metric; see manuscript methods.", inferred_type(values)
        elif field.startswith("geology_"):
            category, description, dtype = "geological_context", "Derived candidate-level geological context metric.", inferred_type(values)
        else:
            category, description, dtype = "candidate_or_provenance", "Candidate-level result or source/provenance field.", inferred_type(values)
        dictionary.append({"field": field, "type": dtype, "nullable": any(v is None for v in values),
                           "category": category, "description": description})
    schema = {"schema_version": SCHEMA_VERSION, "feature_count": len(features), "field_count": len(all_fields),
              "geometry_type": "MultiLineString", "crs": "RFC 7946 WGS84 longitude/latitude",
              "field_dictionary": dictionary}
    (outdir / "arcuate_geometries_study_results_schema.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, allow_nan=False))
    (outdir / "README.md").write_text(f"""# Arcuate-geometry study results GeoJSON

`arcuate_geometries_study_results.geojson` contains {len(features):,} row-preserving features, one for every original geometry in `arcuate_geometries.geojson`.

Candidate-level morphology, geology, GEBCO TID, gravity, magnetic, sediment and CRUST1 fields retain their established pipeline names. Operational review fields are joined by `candidate_id`. Consolidation and GEM active-fault controls are repeated with a `structure_` prefix and must be interpreted at structure grain. Fields beginning `manual_` are deliberately `null` until captured, except `manual_capture_complete=false`.

Scores rank follow-up priority and are not impact probabilities. Circular morphology and geophysical concordance are not diagnostic of impact. See `arcuate_geometries_study_results_schema.json` for the field dictionary.

Regenerate with:

```bash
python3 build_study_results_geojson.py
```
""")
    print(json.dumps({"output": str(output), "features": len(features), "fields": len(all_fields),
                      "manual_fields": len(MANUAL_FIELDS), "bytes": output.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
