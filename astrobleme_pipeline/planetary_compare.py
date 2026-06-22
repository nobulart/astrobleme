from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def compare_planetary(ring_families: pd.DataFrame, sources: list[str | Path]) -> pd.DataFrame:
    rows = []
    for source in sources:
        path = Path(source)
        if not path.exists():
            LOG.warning("Planetary comparison input absent: %s", path); continue
        data = pd.read_csv(path)
        for _, item in data.iterrows():
            object_name = item.get("object", item.get("name", item.get("basin", "unknown")))
            rows.append({"source": path.name, "object": object_name,
                         "body": item.get("body"), "certainty": item.get("certainty"),
                         "diameter_km": item.get("diameter_km"), "ring_ratios": item.get("ring_ratios"),
                         "comparison_interpretation": "geometric comparison only; size similarity does not imply common origin"})
    for _, family in ring_families.iterrows():
        rows.append({"source": "terrestrial_screening", "object": family["family_id"], "body": "Earth",
                     "certainty": "screening geometry only",
                     "diameter_km": str(family["diameter_range_km"]).split("-")[-1],
                     "ring_ratios": family["radius_ratio_sequence"],
                     "comparison_interpretation": "candidate nested geometry; requires geological discrimination"})
    return pd.DataFrame(rows)


def plot_planetary_sizes(comparison: pd.DataFrame, path: str | Path) -> None:
    if comparison.empty: return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    values = pd.to_numeric(comparison["diameter_km"], errors="coerce")
    fig, ax = plt.subplots(figsize=(8, 5));
    for source, indexes in comparison.groupby("source").groups.items():
        sample = values.loc[indexes].dropna(); ax.hist(np.log10(sample), alpha=.45, label=source) if len(sample) else None
    ax.set(xlabel="log10 diameter (km)", ylabel="Count", title="Geometric scale comparison"); ax.legend(); fig.tight_layout(); fig.savefig(target, dpi=180); plt.close(fig)
