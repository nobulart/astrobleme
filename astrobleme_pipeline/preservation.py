from __future__ import annotations

from typing import Any

import pandas as pd


def predict_preservation_state(candidate: pd.Series | dict[str, Any]) -> dict[str, Any]:
    get = candidate.get
    domain = str(get("domain", "") or "").lower()
    diameter = pd.to_numeric(pd.Series([get("diameter_km")]), errors="coerce").iloc[0]
    sediment = pd.to_numeric(pd.Series([get("crust1_sediment_thickness_km", get("sediment_thickness_km"))]), errors="coerce").iloc[0]
    gravity = pd.to_numeric(pd.Series([get("gravity_consensus_used", get("gravity_consensus_percentile"))]), errors="coerce").iloc[0]
    if pd.notna(diameter) and diameter > 1000:
        state = "large_scale_regime_uncertain"
    elif domain == "ocean" and (pd.isna(sediment) or sediment < 1):
        state = "oceanic_volcanic_or_margin_confounded"
    elif domain in {"ocean", "mixed"} and pd.notna(sediment) and sediment >= 1:
        state = "buried_sedimentary"
    elif domain == "land" and pd.notna(sediment) and sediment >= 1:
        state = "buried_sedimentary"
    elif domain == "land" and pd.notna(diameter) and diameter >= 20:
        state = "eroded_exposed"
    elif domain == "land":
        state = "fresh_or_shallow"
    else:
        state = "insufficient_context"
    buried = state == "buried_sedimentary"
    large = state == "large_scale_regime_uncertain"
    exposed = state in {"eroded_exposed", "fresh_or_shallow", "deeply_eroded"}
    return {
        "preservation_state": state,
        "central_uplift_possible": bool(pd.notna(diameter) and diameter >= 4 and not large),
        "annular_faulting_possible": bool(pd.notna(diameter) and diameter >= 10),
        "breccia_pseudotachylite_target": exposed,
        "shocked_quartz_pdf_target": exposed and domain == "land",
        "impact_melt_target": exposed or buried,
        "projectile_geochemistry_plausible": state in {"fresh_or_shallow", "buried_sedimentary"},
        "drilling_required": buried,
        "gravity_seismic_modelling_priority": bool(buried or large or domain in {"ocean", "mixed"} or (pd.notna(gravity) and gravity >= .75)),
        "recommended_follow_up": _recommend(state, domain, diameter, gravity),
        "preservation_caution": "rule-based prediction; geological mapping and age constraints required",
    }


def _recommend(state: str, domain: str, diameter: float, gravity: float) -> str:
    if state == "large_scale_regime_uncertain": return "separate scale-regime validation and lithospheric gravity/seismic modelling"
    if state == "buried_sedimentary": return "seismic and gravity modelling, then archived core or targeted drilling"
    if domain == "ocean": return "bathymetric, seismic, gravity, and volcanic-chain modelling before sampling"
    if domain == "land" and pd.notna(diameter) and diameter > 20 and pd.notna(gravity) and gravity >= .75:
        return "mapped structural transects plus archived sample and core search"
    if domain == "land": return "field mapping, petrography, and targeted structural sampling"
    return "acquire geological, sediment, and crustal context before genetic interpretation"


def predict_all(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"candidate_id": row.get("candidate_id"), **predict_preservation_state(row)} for _, row in frame.iterrows()])

