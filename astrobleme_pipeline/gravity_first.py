from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PipelineConfig
from .io import detect_field
from .scoring import gravity_first_score, harmonic_mean_available, mean_available

LOG = logging.getLogger(__name__)


ALIASES = {
    "id": ["candidate_id", "id", "arc_id"],
    "morphology": ["morphology_score", "followup_score", "follow_up_score", "topography_score"],
    "gravity_consensus": ["gravity_consensus_percentile", "gravity_percentile", "gravity_consensus"],
    "bouguer": ["gravity_bouguer_ring_score_stratified_percentile", "bouguer_ring_percentile", "gravity_bouguer_ring_score", "bouguer_ring_score"],
    "free_air": ["gravity_freeair_ring_score_stratified_percentile", "free_air_ring_percentile", "gravity_freeair_ring_score", "free_air_ring_score"],
    "magnetic": ["magnetic_ring_score_stratified_percentile", "magnetic_percentile", "magnetic_ring_score"],
    "tid": ["tid_artifact_risk", "tid_artefact_risk", "tid_risk"],
    "diameter": ["diameter_km", "structure_diameter_km"],
}


def rank_gravity_first(frame: pd.DataFrame, config: PipelineConfig | None = None) -> tuple[pd.DataFrame, dict[str, str | None]]:
    cfg = config or PipelineConfig()
    fields = {name: detect_field(frame, aliases, name, required=name in {"id", "morphology"})
              for name, aliases in ALIASES.items()}
    result = frame.copy()
    morphology = pd.to_numeric(result[fields["morphology"]], errors="coerce")
    if fields["gravity_consensus"]:
        gravity = pd.to_numeric(result[fields["gravity_consensus"]], errors="coerce")
    else:
        bouguer = result[fields["bouguer"]] if fields["bouguer"] else pd.Series(np.nan, index=result.index)
        free_air = result[fields["free_air"]] if fields["free_air"] else pd.Series(np.nan, index=result.index)
        gravity = pd.DataFrame({"b": bouguer, "f": free_air}).apply(lambda row: mean_available(row), axis=1)
    tid = (pd.to_numeric(result[fields["tid"]], errors="coerce") if fields["tid"]
           else pd.Series(np.nan, index=result.index))
    magnetic = (pd.to_numeric(result[fields["magnetic"]], errors="coerce") if fields["magnetic"]
                else pd.Series(np.nan, index=result.index))
    diameter = (pd.to_numeric(result[fields["diameter"]], errors="coerce") if fields["diameter"]
                else pd.Series(np.nan, index=result.index))
    result["morphology_score_used"] = morphology.clip(0, 1)
    result["gravity_consensus_used"] = gravity.clip(0, 1)
    result["gravity_morphology_agreement"] = [harmonic_mean_available(values) for values in zip(morphology, gravity)]
    result["tid_cleanliness"] = 1.0 - tid.clip(0, 1)
    result["gravity_first_review_score"] = [gravity_first_score(*values) for values in zip(morphology, gravity, tid)]
    result["gravity_strong"] = gravity >= cfg.gravity_strong_threshold
    result["gravity_weak"] = gravity <= cfg.gravity_weak_threshold
    result["magnetic_supporting"] = magnetic >= cfg.magnetic_support_threshold
    result["magnetic_discordant"] = magnetic <= cfg.magnetic_discordant_threshold
    result["tid_risk_high"] = tid > cfg.tid_high_risk_threshold
    result["large_scale_regime"] = diameter >= cfg.large_scale_diameter_km
    result["sub_10km_resolution_warning"] = diameter < cfg.resolution_warning_diameter_km
    result["magnetic_evidence_available"] = magnetic.notna()
    result["gravity_first_score_interpretation"] = "review priority; not impact probability"
    result = result.sort_values(["gravity_first_review_score", fields["id"]], ascending=[False, True], na_position="last")
    result["gravity_first_rank"] = np.arange(1, len(result) + 1)
    return result, fields


def plot_gravity_scatter(frame: pd.DataFrame, path: str | Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    risk = frame["tid_risk_high"].fillna(False)
    ax.scatter(frame["morphology_score_used"], frame["gravity_consensus_used"], c=np.where(risk, "#c44e52", "#4c72b0"),
               alpha=0.55, s=18, linewidths=0)
    ax.set(xlabel="Morphology screening score", ylabel="Gravity consensus", xlim=(0, 1.02), ylim=(0, 1.02),
           title="Gravity-first candidate triage")
    ax.text(0.01, -0.16, "Red: elevated TID/source artefact risk. Screening concordance is non-diagnostic.", transform=ax.transAxes, fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=180)
    plt.close(fig)
