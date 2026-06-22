#!/usr/bin/env python3
"""Build manuscript-ready figures for structure consolidation and fault controls."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

OUT = Path("figure_suite")
OUT.mkdir(exist_ok=True)

TOKENS = {"surface": "#FCFCFD", "panel": "#FFFFFF", "ink": "#1F2430",
          "muted": "#6F768A", "grid": "#E6E8F0", "axis": "#D7DBE7"}
BLUE = {"xlight": "#EAF1FE", "light": "#CEDFFE", "base": "#A3BEFA", "mid": "#5477C4", "dark": "#2E4780"}
GOLD = {"xlight": "#FFF4C2", "light": "#FFEA8F", "base": "#FFE15B", "mid": "#B8A037", "dark": "#736422"}
ORANGE = {"xlight": "#FFEDDE", "light": "#FFBDA1", "base": "#F0986E", "mid": "#CC6F47", "dark": "#804126"}
PINK = {"xlight": "#FCDAD6", "light": "#F5BACC", "base": "#F390CA", "mid": "#BD569B", "dark": "#8A3A6F"}
NEUTRAL = {"xlight": "#F4F5F7", "light": "#E2E5EA", "base": "#C5CAD3", "mid": "#7A828F", "dark": "#464C55"}


def use_theme():
    sns.set_theme(style="whitegrid", rc={
        "figure.facecolor": TOKENS["surface"], "savefig.facecolor": TOKENS["surface"],
        "axes.facecolor": TOKENS["panel"], "axes.edgecolor": TOKENS["axis"],
        "axes.labelcolor": TOKENS["ink"], "grid.color": TOKENS["grid"],
        "grid.linewidth": .8, "font.family": "sans-serif",
        "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial"],
        "axes.spines.top": False, "axes.spines.right": False})


def header(fig, title, subtitle, left=.08, title_y=.975, subtitle_y=None):
    wrapped_title = textwrap.fill(title, 78)
    title_lines = wrapped_title.count("\n") + 1
    if subtitle_y is None:
        subtitle_y = title_y - .052 * title_lines
    fig.text(left, title_y, wrapped_title, ha="left", va="top", fontsize=15,
             fontweight="semibold", color=TOKENS["ink"], linespacing=1.08)
    fig.text(left, subtitle_y, textwrap.fill(subtitle, 120), ha="left", va="top", fontsize=9.5,
             color=TOKENS["muted"], linespacing=1.18)


def save(fig, stem):
    fig.savefig(OUT / f"{stem}.png", dpi=260, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def consolidation_figure():
    s = pd.read_csv("structure_output/consolidation_sensitivity.csv")
    order = ["strict", "default", "lenient"]
    s["setting"] = pd.Categorical(s.setting, order, ordered=True); s = s.sort_values("setting")
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.4), gridspec_kw={"width_ratios": [1.05, 1]})
    fig.subplots_adjust(top=.76, wspace=.30, left=.08, right=.97, bottom=.16)
    header(fig, "Conservative consolidation removes few arc picks",
           "Complete-link clustering is stable across strict, default and lenient centre/scale thresholds; input n = 1,318 picks.")

    ax = axes[0]
    sns.lineplot(data=s, x="setting", y="structure_count", marker="o", markersize=8,
                 color=BLUE["base"], linewidth=1.5, ax=ax)
    ax.axhline(1318, color=NEUTRAL["dark"], linestyle="--", linewidth=1)
    ax.text(2.03, 1318, "Input picks  1,318", va="center", ha="right", fontsize=8.5, color=NEUTRAL["dark"])
    for x, y in enumerate(s.structure_count):
        ax.text(x, y-2.3, f"{y:,}", ha="center", va="top", fontsize=9, color=BLUE["dark"])
    ax.set_ylim(1268, 1324); ax.set_xlabel("Threshold setting"); ax.set_ylabel("Structure-level units")
    ax.set_title("A  Structure count", loc="left", fontsize=11, fontweight="semibold")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10)); ax.grid(axis="x", visible=False)

    long = s.melt(id_vars="setting", value_vars=["multi_pick_structures", "candidates_consolidated"],
                  var_name="measure", value_name="count")
    labels = {"multi_pick_structures": "Multi-pick structures", "candidates_consolidated": "Picks consolidated"}
    long["measure"] = long.measure.map(labels)
    ax = axes[1]
    sns.barplot(data=long, x="setting", y="count", hue="measure", ax=ax,
                palette={"Multi-pick structures": GOLD["base"], "Picks consolidated": BLUE["base"]},
                edgecolor=NEUTRAL["dark"], linewidth=.7)
    for c in ax.containers: ax.bar_label(c, fmt="%d", padding=3, fontsize=8.5)
    ax.set_ylim(0, 45); ax.set_xlabel("Threshold setting"); ax.set_ylabel("Count")
    ax.set_title("B  What changes", loc="left", fontsize=11, fontweight="semibold")
    ax.legend(loc="upper left", frameon=False, fontsize=8.5); ax.grid(axis="x", visible=False)
    save(fig, "fig_structure_consolidation")


def _fault_segments():
    obj = json.loads(Path("geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson").read_text())
    for f in obj["features"]:
        g = f.get("geometry") or {}; coords = g.get("coordinates", [])
        lines = coords if g.get("type") == "MultiLineString" else [coords]
        for line in lines:
            if len(line) >= 2:
                a = np.asarray(line, dtype=float)
                # Split traces crossing the dateline to avoid horizontal artefacts.
                breaks = np.where(np.abs(np.diff(a[:, 0])) > 180)[0] + 1
                for part in np.split(a, breaks):
                    if len(part) >= 2: yield part


def global_map_figure():
    d = pd.read_csv("structure_output/structure_ranking.csv")
    hi = d[d.review_tier.isin(["A_cross_layer", "B_gravity_supported"])]
    multi = d[d.member_count > 1]
    fig, ax = plt.subplots(figsize=(13, 6.8)); fig.subplots_adjust(top=.70, left=.06, right=.98, bottom=.12)
    header(fig, "The structure catalogue is global; mapped active faults are an uneven control layer",
           "All 1,292 consolidated units are shown. GEM traces emphasize neotectonic continental coverage and should not be read as a complete global fault inventory.", left=.06)
    for seg in _fault_segments(): ax.plot(seg[:, 0], seg[:, 1], color=ORANGE["light"], linewidth=.28, alpha=.45, zorder=1)
    ax.scatter(d.lon, d.lat, s=6, color=NEUTRAL["base"], alpha=.55, linewidths=0, zorder=2)
    a = hi[hi.review_tier.eq("A_cross_layer")]; b = hi[hi.review_tier.eq("B_gravity_supported")]
    ax.scatter(a.lon, a.lat, s=38, color=BLUE["base"], edgecolor=BLUE["dark"], linewidth=.7, zorder=4)
    ax.scatter(b.lon, b.lat, s=40, facecolor=GOLD["base"], edgecolor=GOLD["dark"], marker="s", linewidth=.7, zorder=4)
    ax.scatter(multi.lon, multi.lat, s=62, facecolor="none", edgecolor=PINK["dark"], marker="D", linewidth=1, zorder=5)
    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90); ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.set_xticks(np.arange(-180, 181, 60)); ax.set_yticks(np.arange(-90, 91, 30)); ax.grid(linestyle=":")
    ax.legend(handles=[Line2D([], [], color=ORANGE["light"], lw=2, label="GEM active-fault traces"),
                       Line2D([], [], marker="o", color="none", markerfacecolor=NEUTRAL["base"], markeredgecolor="none", label="Tier C/D structure"),
                       Line2D([], [], marker="o", color="none", markerfacecolor=BLUE["base"], markeredgecolor=BLUE["dark"], label="Tier A"),
                       Line2D([], [], marker="s", color="none", markerfacecolor=GOLD["base"], markeredgecolor=GOLD["dark"], label="Tier B"),
                       Line2D([], [], marker="D", color="none", markerfacecolor="none", markeredgecolor=PINK["dark"], label="Multi-pick unit")],
              loc="lower center", bbox_to_anchor=(.5, 1.01), ncol=5, frameon=False, fontsize=8.5)
    save(fig, "fig_structure_global_map")


def fault_null_figure():
    draws = pd.read_csv("structure_output/fault_matched_null_draws.csv")
    result = json.loads(Path("structure_output/fault_matched_null.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.5)); fig.subplots_adjust(top=.68, wspace=.28, left=.08, right=.97, bottom=.17)
    header(fig, "High-priority structures are not unusually associated with mapped active faults",
           "Matched null: 32 Tier A/B cases, 9,999 resamples; controls matched by domain, radius quintile and absolute-latitude quartile.")
    specs = [
        ("fault_intersection_fraction", result["observed_fault_intersection_fraction"],
         "A  Fault intersections", "Fraction intersecting a mapped fault", result["fault_intersection_enrichment_p"], ">="),
        ("median_log1p_fault_proximity_ratio", result["observed_median_log1p_fault_proximity_ratio"],
         "B  Radius-normalized proximity", "Median log(1 + nearest-fault distance / radius)", result["closer_fault_proximity_p"], "<=")]
    for ax, (col, obs, title, xlabel, p, direction) in zip(axes, specs):
        sns.histplot(draws[col], bins=32, stat="density", color=BLUE["light"], edgecolor=BLUE["dark"], linewidth=.45, ax=ax)
        ax.axvline(obs, color=ORANGE["dark"], linewidth=1.5)
        ax.text(.98, .94, f"Observed  {obs:.3f}\nEmpirical p  {p:.4f}", transform=ax.transAxes,
                ha="right", va="top", fontsize=9, color=TOKENS["ink"],
                bbox=dict(boxstyle="round,pad=.35", facecolor=TOKENS["panel"], edgecolor=TOKENS["axis"]))
        ax.set_title(title, loc="left", fontsize=11, fontweight="semibold"); ax.set_xlabel(xlabel); ax.set_ylabel("Null density")
        ax.grid(axis="x", visible=False)
    fig.legend(handles=[Patch(facecolor=BLUE["light"], edgecolor=BLUE["dark"], label="Matched-null distribution"),
                        Line2D([], [], color=ORANGE["dark"], lw=1.5, label="Observed Tier A/B statistic")],
               loc="upper left", bbox_to_anchor=(.075, .765), ncol=2, frameon=False, fontsize=8.5)
    save(fig, "fig_fault_matched_nulls")


def geophysical_category_comparison_figure():
    results = json.loads(Path("geophysical_output/nulls/geophysical_null_results.json").read_text())
    rotation = results["longitude_rotation"]["results"]
    concordance = results["stratified_cross_layer_permutation"]["results"]
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.8), gridspec_kw={"width_ratios": [1.05, 1]})
    fig.subplots_adjust(top=.70, wspace=.44, left=.18, right=.96, bottom=.17)
    header(fig, "Comparative geophysical evidence across matched null designs",
           "Observed statistics versus 95% null intervals; 9,999 replicates, seed 20260621. Absolute score magnitudes are not directly comparable across channels.")

    def draw_panel(ax, rows, xlim, title, xlabel):
        y = np.arange(len(rows))[::-1]
        for yi, row in zip(y, rows):
            family = GOLD if row["gravity"] else BLUE
            ax.hlines(yi, row["low"], row["high"], color=NEUTRAL["mid"], linewidth=2.0, zorder=1)
            ax.scatter(row["null"], yi, s=34, facecolor=TOKENS["panel"], edgecolor=NEUTRAL["dark"], linewidth=.9, zorder=2)
            ax.scatter(row["observed"], yi, s=68, marker="D" if row["gravity"] else "o",
                       facecolor=family["base"], edgecolor=family["dark"], linewidth=1.0, zorder=3)
            ax.text(xlim[1], yi, f"p={row['p']:.4f}", ha="right", va="center", fontsize=8.5,
                    color=family["dark"] if row["gravity"] else TOKENS["muted"])
        ax.set_yticks(y, [r["label"] for r in rows]); ax.set_xlim(*xlim); ax.set_ylim(-.65, len(rows)-.35)
        ax.set_title(title, loc="left", fontsize=11, fontweight="semibold"); ax.set_xlabel(xlabel); ax.set_ylabel("")
        ax.grid(axis="y", visible=False); ax.axvline(0, color=TOKENS["axis"], linewidth=.8)

    rows_a = []
    labels_a = [("tid_artifact_risk", "TID artefact risk  (lower is cleaner)", False),
                ("gravity_bouguer_ring_score", "Bouguer gravity", True),
                ("gravity_freeair_ring_score", "Free-air gravity", True),
                ("magnetic_ring_score", "Magnetic anomaly", False)]
    for key, label, gravity in labels_a:
        r = rotation[key]
        rows_a.append({"label": label, "gravity": gravity, "observed": r["observed"], "null": r["null_mean"],
                       "low": r["null_025"], "high": r["null_975"], "p": r["one_sided_enrichment_p"]})
    draw_panel(axes[0], rows_a, (.09, .35), "A  Domain-matched longitude rotations", "Observed / null screening statistic")

    rows_b = []
    labels_b = [("gravity_bouguer_ring_score", "Bouguer gravity", True),
                ("gravity_freeair_ring_score", "Free-air gravity", True),
                ("magnetic_ring_score", "Magnetic anomaly", False)]
    for key, label, gravity in labels_b:
        r = concordance[key]
        rows_b.append({"label": label, "gravity": gravity, "observed": r["observed_spearman_rho"], "null": r["null_mean"],
                       "low": r["null_025"], "high": r["null_975"], "p": r["one_sided_positive_concordance_p"]})
    draw_panel(axes[1], rows_b, (-.10, .22), "B  Scale/domain-stratified concordance", "Morphology-geophysics Spearman rho")

    fig.legend(handles=[Line2D([], [], marker="D", color="none", markerfacecolor=GOLD["base"], markeredgecolor=GOLD["dark"], label="Observed gravity"),
                        Line2D([], [], marker="o", color="none", markerfacecolor=BLUE["base"], markeredgecolor=BLUE["dark"], label="Observed comparison channel"),
                        Line2D([], [], marker="o", color=NEUTRAL["mid"], markerfacecolor=TOKENS["panel"], markeredgecolor=NEUTRAL["dark"], label="Null mean and 95% interval")],
               loc="upper left", bbox_to_anchor=(.175, .775), ncol=3, frameon=False, fontsize=8.5)
    save(fig, "fig_geophysical_category_comparison")


def evidence_matrix_figure():
    structures = pd.read_csv("structure_output/structure_ranking.csv")
    review = pd.read_csv("geophysical_output/geophysical_review_priority.csv")
    cols = ["candidate_id", "gravity_consensus_percentile", "magnetic_ring_score_stratified_percentile"]
    d = structures.merge(review[cols], left_on="representative_candidate_id", right_on="candidate_id", how="left")
    d["Morphology"] = d.followup_score.rank(pct=True)
    d["Gravity"] = d.gravity_consensus_percentile
    d["Magnetics"] = d.magnetic_ring_score_stratified_percentile
    d["TID cleanliness"] = 1 - d.tid_artifact_risk
    # A high value means closer to an active fault, i.e. stronger tectonic-control context.
    d["Fault proximity"] = d.groupby("domain").active_fault_proximity_ratio.rank(pct=True, ascending=False)
    d["Boundary independence"] = d.geology_independence
    hi = d[d.review_tier.isin(["A_cross_layer", "B_gravity_supported"])].copy()
    hi["tier_order"] = hi.review_tier.map({"A_cross_layer": 0, "B_gravity_supported": 1})
    hi = hi.sort_values(["tier_order", "followup_score"], ascending=[True, False])
    labels = hi.representative_candidate_id.copy()
    labels = labels.where(labels.ne("arc_0370"), labels + "  Anton Dohrn")
    matrix_cols = ["Morphology", "Gravity", "Magnetics", "TID cleanliness", "Boundary independence", "Fault proximity"]
    mat = hi.set_index(labels)[matrix_cols]
    fig, ax = plt.subplots(figsize=(11.2, 10.5)); fig.subplots_adjust(top=.83, left=.24, right=.94, bottom=.12)
    header(fig, "Tier A/B structures have heterogeneous cross-layer profiles",
           "Cell values are screening percentiles or 0-1 heuristics, not impact probabilities. Higher fault proximity means closer to mapped active faults; n = 32 structures.", left=.10)
    cmap = sns.light_palette(BLUE["dark"], as_cmap=True)
    sns.heatmap(mat, cmap=cmap, vmin=0, vmax=1, linewidths=.45, linecolor=TOKENS["panel"],
                cbar_kws={"label": "Relative screening value", "shrink": .72}, ax=ax)
    ax.set_xlabel(""); ax.set_ylabel(""); ax.tick_params(axis="x", rotation=25, labelsize=9); ax.tick_params(axis="y", labelsize=8.5)
    # Separate operational tiers without adding another color scale.
    n_a = int((hi.review_tier == "A_cross_layer").sum())
    ax.axhline(n_a, color=ORANGE["dark"], linewidth=1.5)
    ax.text(-.19, 1 - n_a/(2*len(hi)), "Tier A", transform=ax.transAxes, rotation=90, ha="center", va="center", fontsize=9, color=BLUE["dark"])
    ax.text(-.19, (len(hi)-n_a)/(2*len(hi)), "Tier B", transform=ax.transAxes, rotation=90, ha="center", va="center", fontsize=9, color=GOLD["dark"])
    save(fig, "fig_cross_layer_evidence_matrix")


def write_chart_map():
    (OUT / "README.md").write_text("""# New-results figure suite\n\n| Figure | Analytical question | Form | Controlling sources |\n|---|---|---|---|\n| `fig_structure_consolidation` | Is the structure count sensitive to merge thresholds? | Line plus grouped comparison bars | `structure_output/consolidation_sensitivity.csv` |\n| `fig_structure_global_map` | Where are consolidated structures, high tiers, repeat picks and mapped active faults? | Global point/line map | `structure_ranking.csv`; GEM harmonized GeoJSON |\n| `fig_fault_matched_nulls` | Are Tier A/B structures unusually intersecting or close to mapped active faults? | Two empirical null histograms | `fault_matched_null_draws.csv`; `fault_matched_null.json` |\n| `fig_cross_layer_evidence_matrix` | Do high-priority structures share one cross-layer evidence profile? | Heatmap | Structure ranking plus geophysical review table |\n| `fig_geophysical_category_comparison` | Which geophysical channels separate from matched nulls across both designs? | Faceted dot and null interval comparison | `geophysical_null_results.json` |\n\nAll scores are screening values, not impact probabilities. GEM active-fault coverage is incomplete and especially limited offshore. PNG and vector PDF versions are generated by `build_structure_figures.py`.\n\n## Suggested placement\n\n- Main text: `fig_geophysical_category_comparison`, `fig_structure_consolidation` and `fig_fault_matched_nulls`.\n- Main text or extended results: `fig_cross_layer_evidence_matrix`.\n- Supplementary/context figure: `fig_structure_global_map`, because its apparent fault coverage is strongly shaped by GEM's uneven geographic completeness.\n""")


def main():
    use_theme()
    consolidation_figure(); global_map_figure(); fault_null_figure(); geophysical_category_comparison_figure(); evidence_matrix_figure(); write_chart_map()
    print(f"Wrote five PNG/PDF figure pairs to {OUT}")


if __name__ == "__main__": main()
