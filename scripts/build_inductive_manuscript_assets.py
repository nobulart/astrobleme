#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd


def tex(value: object) -> str:
    return str(value).replace("_", r"\_").replace("&", r"\&")


def tex_label(value: object) -> str:
    return tex(str(value).replace("_", " "))


def parse_ratios(value: object) -> list[float]:
    try:
        return [float(item) for item in ast.literal_eval(str(value))]
    except (ValueError, SyntaxError, TypeError):
        return []


def build(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    shortlist = pd.read_csv(input_dir / "gravity_first_shortlist.csv")
    preservation = pd.read_csv(input_dir / "preservation_predictions.csv")
    controls = pd.read_csv(input_dir / "negative_control_library.csv")
    matches = pd.read_csv(input_dir / "negative_control_matches.csv")
    rings = pd.read_csv(input_dir / "ring_families.csv")
    regional = pd.read_csv(input_dir / "regional_families.csv")
    planetary = pd.read_csv(input_dir / "planetary_comparison.csv")

    merged = shortlist.merge(preservation[["candidate_id", "preservation_state"]], on="candidate_id", how="left")
    rows = []
    for _, item in merged.head(10).iterrows():
        rows.append(
            rf"\texttt{{{tex(item.candidate_id)}}} & {item.diameter_km:.1f} & {tex(item.domain)} & "
            rf"{item.morphology_score_used:.3f} & {item.gravity_consensus_used:.3f} & "
            rf"{item.magnetic_ring_score_stratified_percentile:.3f} & {item.gravity_first_review_score:.3f} & "
            rf"{tex_label(item.preservation_state)} \\" 
        )
    (output_dir / "manuscript_gravity_shortlist.tex").write_text("\n".join(rows) + "\n")

    control_rows = []
    for _, item in controls.sort_values("negative_control_name").iterrows():
        control_rows.append(
            rf"{tex(item.negative_control_name)} & {tex_label(item.negative_control_class)} & "
            rf"{item.lat:.3f} & {item.lon:.3f} & {item.diameter_km:.1f} \\" 
        )
    (output_dir / "manuscript_control_library.tex").write_text("\n".join(control_rows) + "\n")

    preservation_rows = [rf"{tex_label(state)} & {count} \\" for state, count in preservation.preservation_state.value_counts().items()]
    (output_dir / "manuscript_preservation.tex").write_text("\n".join(preservation_rows) + "\n")

    terrestrial_ratios = sum((parse_ratios(value) for value in rings.radius_ratio_sequence), [])
    comparison_rows = []
    groups = [
        ("Terrestrial candidate families", len(rings), terrestrial_ratios,
         [float(str(value).split("-")[-1]) for value in rings.diameter_range_km]),
        ("Published lunar multiring basins", int((planetary.source == "lunar_multiring_basins.csv").sum()),
         sum((parse_ratios(value) for value in planetary.loc[planetary.source == "lunar_multiring_basins.csv", "ring_ratios"]), []),
         pd.to_numeric(planetary.loc[planetary.source == "lunar_multiring_basins.csv", "diameter_km"], errors="coerce").dropna().tolist()),
        ("Historical Martian subset", int((planetary.source == "martian_basins.csv").sum()),
         sum((parse_ratios(value) for value in planetary.loc[planetary.source == "martian_basins.csv", "ring_ratios"]), []),
         pd.to_numeric(planetary.loc[planetary.source == "martian_basins.csv", "diameter_km"], errors="coerce").dropna().tolist()),
    ]
    for label, count, ratios, diameters in groups:
        q25, median, q75 = np.quantile(ratios, [.25, .5, .75])
        comparison_rows.append(
            rf"{label} & {count} & {len(ratios)} & {median:.3f} & {q25:.3f}--{q75:.3f} & "
            rf"{min(diameters):.0f}--{max(diameters):.0f} \\" 
        )
    (output_dir / "manuscript_planetary_comparison.tex").write_text("\n".join(comparison_rows) + "\n")

    summary = {
        "shortlist_n": len(shortlist),
        "shortlist_score_min": shortlist.gravity_first_review_score.min(),
        "shortlist_score_median": shortlist.gravity_first_review_score.median(),
        "shortlist_score_max": shortlist.gravity_first_review_score.max(),
        "land_n": int((shortlist.domain == "land").sum()),
        "ocean_n": int((shortlist.domain == "ocean").sum()),
        "magnetic_support_n": int(shortlist.magnetic_supporting.sum()),
        "magnetic_discordant_n": int(shortlist.magnetic_discordant.sum()),
        "control_n": len(controls),
        "control_warning_n": int(matches.control_similarity_warning.sum()),
        "ring_family_n": len(rings),
        "ring_member_n": int(rings.member_count.sum()),
        "ring_pair_n": int((rings.member_count == 2).sum()),
        "ring_triple_n": int((rings.member_count == 3).sum()),
        "regional_family_n": regional.regional_family_id.nunique(),
        "regional_clustered_n": int((regional.regional_family_member_count > 1).sum()),
    }
    macro_names = {
        "shortlist_n": "InductiveShortlistN", "shortlist_score_min": "InductiveScoreMin",
        "shortlist_score_median": "InductiveScoreMedian", "shortlist_score_max": "InductiveScoreMax",
        "land_n": "InductiveLandN", "ocean_n": "InductiveOceanN", "magnetic_support_n": "InductiveMagneticSupportN",
        "magnetic_discordant_n": "InductiveMagneticDiscordantN", "control_n": "InductiveControlN",
        "control_warning_n": "InductiveControlWarningN", "ring_family_n": "InductiveRingFamilyN",
        "ring_member_n": "InductiveRingMemberN", "ring_pair_n": "InductiveRingPairN",
        "ring_triple_n": "InductiveRingTripleN", "regional_family_n": "InductiveRegionalFamilyN",
        "regional_clustered_n": "InductiveRegionalClusteredN",
    }
    macro_lines = []
    for key, value in summary.items():
        rendered = f"{value:.3f}" if isinstance(value, float) else str(value)
        macro_lines.append(rf"\newcommand{{\{macro_names[key]}}}{{{rendered}}}")
    (output_dir / "manuscript_inductive_macros.tex").write_text("\n".join(macro_lines) + "\n")


if __name__ == "__main__":
    build(Path("outputs/tables"), Path("outputs/tables"))
