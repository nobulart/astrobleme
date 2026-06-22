from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CAUTION = "This is a screening candidate only. No impact origin is inferred without diagnostic shock, meteoritic, or geochemical evidence."


def _clean(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)): return None
    if isinstance(value, np.generic): return value.item()
    return value


def build_packet(row: pd.Series) -> dict[str, Any]:
    cid = str(row.get("candidate_id"))
    alternatives = ["tectonic or inherited structural fabric"]
    domain = str(row.get("domain", "unknown"))
    if domain in {"ocean", "mixed"}: alternatives += ["volcanic seamount or intrusive complex", "sedimentary or passive-margin structure"]
    else: alternatives += ["intrusive/ring complex", "erosional or sedimentary basin geometry"]
    if row.get("control_similarity_warning"): alternatives.insert(0, f"analogue of nearby {row.get('nearest_negative_control_class')}")
    evidence = {
        "morphology": row.get("morphology_score_used"), "gravity": row.get("gravity_consensus_used"),
        "magnetics": row.get("magnetic_ring_score_stratified_percentile", row.get("magnetic_percentile")),
        "TID/source artefact risk": row.get("tid_artifact_risk", row.get("tid_artefact_risk")),
        "active-fault context": row.get("structure_fault_control_flag", row.get("fault_control_flag")),
    }
    falsification = ["Model plausible volcanic, intrusive, tectonic, and sedimentary alternatives against the same observations.",
                     "Reject an impact interpretation if mapped relationships establish an endogenic structure.",
                     "Require independently verified diagnostic shock or projectile-derived evidence for confirmation."]
    return {"candidate_id": cid, "location": {"longitude": row.get("lon"), "latitude": row.get("lat")},
            "diameter_km": row.get("diameter_km"), "radius_km": row.get("radius_km"), "domain": domain,
            "gravity_first_review_score": row.get("gravity_first_review_score"), "evidence_channels": evidence,
            "negative_control": {"class": row.get("nearest_negative_control_class"), "distance_km": row.get("nearest_negative_control_distance_km"),
                                 "warning": row.get("control_similarity_warning")},
            "regional_family": row.get("regional_family_id"), "ring_family": row.get("ring_family_id"),
            "preservation_state": row.get("preservation_state"), "preservation_follow_up": row.get("recommended_follow_up"),
            "most_likely_non_impact_alternatives": alternatives,
            "impact_supporting_evidence_to_seek": ["diagnostic shock metamorphism in geological context", "impact melt or breccia with defensible field relations", "meteoritic or projectile-derived geochemical signature"],
            "falsification_tests": falsification, "recommended_next_data_acquisition": row.get("recommended_follow_up"),
            "confidence_caution_statement": CAUTION}


def packet_markdown(packet: dict[str, Any]) -> str:
    ev = packet["evidence_channels"]
    evidence_rows = "\n".join(f"| {key} | {_fmt(value)} | Screening evidence; non-diagnostic in isolation |" for key, value in ev.items())
    alternatives = "\n".join(f"- {value}" for value in packet["most_likely_non_impact_alternatives"])
    support = "\n".join(f"{i}. {value}" for i, value in enumerate(packet["impact_supporting_evidence_to_seek"], 1))
    falsification = "\n".join(f"- {value}" for value in packet["falsification_tests"])
    nc = packet["negative_control"]
    return f"""# Candidate {packet['candidate_id']} review packet

## Screening summary

Location: {_fmt(packet['location']['latitude'])}, {_fmt(packet['location']['longitude'])}; diameter: {_fmt(packet['diameter_km'])} km; domain: {packet['domain']}. Gravity-first review score: {_fmt(packet['gravity_first_review_score'])}.

## Why this candidate is interesting

Morphology and independent gravity screening can be reviewed together. Ring family: {_fmt(packet['ring_family'])}; regional family: {_fmt(packet['regional_family'])}.

## Why this may be non-impact

Nearest negative control: {_fmt(nc['class'])} at {_fmt(nc['distance_km'])} km. A match or proximity flag requires endogenic modelling; it is not an automatic rejection.

{alternatives}

## Evidence channels

| Channel | Result | Interpretation |
|---|---:|---|
{evidence_rows}

## Preservation-state prediction

{_fmt(packet['preservation_state'])}. {packet.get('preservation_follow_up') or 'Context is insufficient for a specific preservation prediction.'}

## Field or data follow-up

{support}

## Falsification tests

{falsification}

## Current interpretation

{packet['confidence_caution_statement']}
"""


def write_candidate_packets(frame: pd.DataFrame, directory: str | Path, top_n: int = 25) -> list[Path]:
    root = Path(directory); root.mkdir(parents=True, exist_ok=True); written = []
    for _, row in frame.head(top_n).iterrows():
        packet = {key: _clean(value) if not isinstance(value, dict) and not isinstance(value, list) else value for key, value in build_packet(row).items()}
        packet = json.loads(json.dumps(packet, default=_clean, allow_nan=False))
        stem = str(packet["candidate_id"]); md = root / f"{stem}_packet.md"; js = root / f"{stem}_packet.json"
        md.write_text(packet_markdown(packet)); js.write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n"); written.extend([md, js])
    return written


def _fmt(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)): return "not available"
    return f"{value:.3f}" if isinstance(value, float) else str(value)

