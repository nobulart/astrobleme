from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

CAUTION = "> These outputs are candidate-screening products only. Circular morphology, gravity anomalies, and spatial coincidence are non-diagnostic. Impact confirmation requires accepted shock metamorphic, meteoritic, or projectile-derived geochemical evidence."


def write_summary_report(path: str | Path, *, inputs_used: list[str], skipped: list[str], shortlist: pd.DataFrame,
                         controls: pd.DataFrame, control_library: pd.DataFrame, rings: pd.DataFrame,
                         preservation: pd.DataFrame, regional: pd.DataFrame, planetary: pd.DataFrame,
                         packet_ids: list[str], metadata: dict[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    leaders = _markdown_table(shortlist[[c for c in ["gravity_first_rank", "candidate_id", "gravity_first_review_score", "gravity_strong", "tid_risk_high"] if c in shortlist]].head(10))
    text = f"""# Inductive astrobleme screening summary

{CAUTION}

## Inputs used

{_items(inputs_used)}

## Inputs missing or skipped

{_items(skipped) if skipped else '- None'}

## Gravity-first shortlist

{leaders}

The gravity-first review score is a transparent review priority, not an impact probability. Configuration: `{metadata}`.

## Negative-control warnings

Matched {len(controls)} candidate rows; {int(controls.get('control_similarity_warning', pd.Series(dtype=bool)).sum())} carry a proximity or similarity warning. A warning prompts endogenic modelling and is not automatic exclusion.

The comparator library contains {len(control_library)} controls: {', '.join(control_library.get('negative_control_name', pd.Series(dtype=str)).dropna().astype(str)) if not control_library.empty else 'none available'}. It remains a small, regionally uneven library rather than an exhaustive endogenic reference set.

## Candidate ring families

{len(rings)} candidate nested arcuate families were identified under the configured center, radius-ratio, and angular-coverage rules.

## Preservation-state predictions

{_markdown_table(preservation.get('preservation_state', pd.Series(dtype=str)).value_counts().rename_axis('state').reset_index(name='count')) if not preservation.empty else 'No predictions generated.'}

## Regional clusters

{regional.get('regional_family_id', pd.Series(dtype=str)).nunique()} proximity families were assigned. Cluster membership does not establish candidate independence or common origin.

## Planetary geometric comparison

{_planetary_summary(planetary)}

## Highest-priority field-review packets

{_items(packet_ids)}

## Methodological cautions

- Morphology, gravity, magnetics, geology, and controls remain separate evidence channels.
- Magnetic support is optional and is flagged separately.
- Ring ratios are candidate-specific; no universal crater-to-ring multiplier is assumed.
- Missing inputs are recorded rather than silently converted into negative evidence.
- Diagnostic confirmation remains outside the scope of this pipeline.
"""
    target.write_text(text)


def _items(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- None"


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join("---" for _ in columns) + "|"
    rows = []
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            if pd.isna(value): cells.append("")
            elif isinstance(value, float): cells.append(f"{value:.4f}")
            else: cells.append(str(value).replace("|", "\\|"))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator, *rows])


def _planetary_summary(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No planetary comparison rows were available."
    counts = frame.groupby(["source", "body"], dropna=False).size().rename("rows").reset_index()
    return (_markdown_table(counts) +
            "\n\nPlanetary rows are geometric comparators only. Ring-ratio or diameter overlap does not imply common origin, "
            "and the Martian table is an explicitly incomplete historical subset.")
