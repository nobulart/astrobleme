from __future__ import annotations

import html
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "ranking_output" / "arc_ranking.csv"
OUTPUT = ROOT / "results_review"
CHARTS = OUTPUT / "charts"

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
    "blue": "#A3BEFA",
    "blue_dark": "#2E4780",
    "gold": "#FFE15B",
    "gold_dark": "#736422",
    "orange": "#F0986E",
}


def setup_style() -> None:
    sns.set_theme(style="whitegrid")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "axes.titlecolor": TOKENS["ink"],
            "xtick.color": TOKENS["muted"],
            "ytick.color": TOKENS["muted"],
            "grid.color": TOKENS["grid"],
            "figure.facecolor": TOKENS["surface"],
            "axes.facecolor": TOKENS["panel"],
        }
    )


def header(fig, title: str, subtitle: str) -> None:
    fig.text(0.08, 0.965, title, ha="left", va="top", fontsize=17, weight="bold", color=TOKENS["ink"])
    fig.text(0.08, 0.915, subtitle, ha="left", va="top", fontsize=10, color=TOKENS["muted"])


def save(fig, name: str) -> None:
    fig.savefig(CHARTS / name, dpi=180, bbox_inches="tight", facecolor=TOKENS["surface"])
    plt.close(fig)


def score_distribution(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.8))
    sns.histplot(df, x="followup_score", bins=np.linspace(0, 0.92, 38), color=TOKENS["blue"], edgecolor=TOKENS["blue_dark"], ax=ax)
    for value, label in [(0.70, "233 ≥ 0.70"), (0.75, "82 ≥ 0.75"), (0.80, "19 ≥ 0.80")]:
        ax.axvline(value, color=TOKENS["gold_dark"], linestyle="--", linewidth=1)
        ax.text(value + 0.006, ax.get_ylim()[1] * (0.88 - (value - 0.70) * 1.4), label, color=TOKENS["gold_dark"], fontsize=9)
    ax.set(xlabel="Follow-up score", ylabel="Candidates")
    sns.despine(ax=ax)
    header(fig, "Distribution of follow-up scores", "All 1,318 candidates; cut-offs are operational triage bands, not statistical significance thresholds")
    fig.subplots_adjust(top=0.82, left=0.08, right=0.98, bottom=0.13)
    save(fig, "score_distribution.png")


def top_candidates(df: pd.DataFrame) -> None:
    top = df.head(15).sort_values("followup_score")
    labels = [f"{cid}  ({diameter:.0f} km)" for cid, diameter in zip(top.candidate_id, top.diameter_km)]
    fig, ax = plt.subplots(figsize=(10, 7.2))
    bars = ax.barh(labels, top.followup_score, color=TOKENS["blue"], edgecolor=TOKENS["blue_dark"], linewidth=0.8)
    ax.set_xlim(0.72, 0.91)
    ax.set(xlabel="Follow-up score", ylabel="")
    ax.grid(axis="y", visible=False)
    for bar, value in zip(bars, top.followup_score):
        ax.text(value + 0.002, bar.get_y() + bar.get_height() / 2, f"{value:.3f}", va="center", fontsize=9, color=TOKENS["ink"])
    sns.despine(ax=ax)
    header(fig, "Highest-ranked candidates", "Top 15 candidates; diameter shown in parentheses")
    fig.subplots_adjust(top=0.86, left=0.23, right=0.96, bottom=0.10)
    save(fig, "top_candidates.png")


def score_by_diameter(df: pd.DataFrame) -> None:
    bins = [0, 10, 25, 50, 100, 250, np.inf]
    labels = ["<10", "10–25", "25–50", "50–100", "100–250", "≥250"]
    plot = df.assign(diameter_band=pd.cut(df.diameter_km, bins=bins, labels=labels, right=False))
    fig, ax = plt.subplots(figsize=(10, 5.8))
    sns.boxplot(data=plot, x="diameter_band", y="followup_score", color=TOKENS["blue"], fliersize=1.5, linewidth=0.9, ax=ax)
    counts = plot.groupby("diameter_band", observed=True).size()
    for i, label in enumerate(labels):
        ax.text(i, 0.88, f"n={counts.get(label, 0)}", ha="center", fontsize=9, color=TOKENS["muted"])
    ax.set(xlabel="Candidate diameter (km)", ylabel="Follow-up score", ylim=(0, 0.92))
    sns.despine(ax=ax)
    header(fig, "Score reliability changes sharply below 10 km", "GEBCO 15-arcsecond resolution and the pipeline quality gate suppress the smallest candidates")
    fig.subplots_adjust(top=0.82, left=0.08, right=0.98, bottom=0.13)
    save(fig, "score_by_diameter.png")


def score_drivers(df: pd.DataFrame) -> pd.Series:
    fields = {
        "topography_score_unweighted": "Composite topography",
        "hough_percentile": "Annular peak percentile",
        "radius_match": "Radius agreement",
        "angular_continuity": "Angular continuity",
        "centre_match": "Centre agreement",
        "data_quality": "Data quality",
        "geology_independence": "Geology independence",
        "relief_score": "Annular relief",
        "radial_alignment": "Radial alignment",
    }
    corr = df[list(fields) + ["followup_score"]].corr(method="spearman")["followup_score"].drop("followup_score")
    corr.index = [fields[x] for x in corr.index]
    corr = corr.sort_values()
    fig, ax = plt.subplots(figsize=(10, 6.0))
    bars = ax.barh(corr.index, corr.values, color=TOKENS["blue"], edgecolor=TOKENS["blue_dark"], linewidth=0.8)
    ax.set(xlabel="Spearman correlation with follow-up score", ylabel="", xlim=(0, 0.92))
    ax.grid(axis="y", visible=False)
    for bar, value in zip(bars, corr.values):
        ax.text(value + 0.015, bar.get_y() + bar.get_height() / 2, f"{value:.2f}", va="center", fontsize=9)
    sns.despine(ax=ax)
    header(fig, "The score is principally a topographic-circularity ranking", "Associations are partly mechanical because these fields are inputs to the composite score")
    fig.subplots_adjust(top=0.84, left=0.27, right=0.96, bottom=0.12)
    save(fig, "score_drivers.png")
    return corr.sort_values(ascending=False)


def build_table(df: pd.DataFrame) -> str:
    rows = []
    for row in df.head(20).itertuples():
        geology = "independent" if row.geology_boundary_coincidence == 0 else f"{row.geology_boundary_coincidence:.2f} overlap"
        rows.append(
            "<tr>"
            f"<td>{int(row.rank)}</td><td>{html.escape(row.candidate_id)}</td>"
            f"<td>{row.lat:.3f}, {row.lon:.3f}</td><td>{row.diameter_km:.1f}</td>"
            f"<td><strong>{row.followup_score:.3f}</strong></td><td>{row.topography_score_unweighted:.3f}</td>"
            f"<td>{geology}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def write_report(df: pd.DataFrame, correlations: pd.Series) -> None:
    q = df.followup_score.quantile([0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
    top20_no_boundary = int((df.head(20).geology_boundary_coincidence == 0).sum())
    poor_quality = int((df.data_quality < 0.999999).sum())
    html_report = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review of the arcuate-geometry ranking</title>
<style>
body{{font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;margin:0;background:#faf8f5;color:#171411}}
main{{max-width:980px;margin:0 auto;padding:42px 22px 72px}}header,section{{margin-bottom:36px}}
h1,h2{{line-height:1.16;margin:0 0 14px}}h1{{font-size:2.25rem}}h2{{font-size:1.45rem}}
p,li{{line-height:1.62}}a{{color:#2e4780}}figure{{margin:22px 0}}figure img{{width:100%;height:auto;border-radius:10px;background:white}}
figcaption,.small{{color:#5f5750;font-size:.9rem}}.summary{{padding:22px 24px;background:#f1ece4;border:1px solid #ddd1c2;border-radius:18px}}
.summary ul{{margin:0;padding-left:22px}}.summary li+li{{margin-top:10px}}.callout{{padding:17px 20px;background:#fff4c2;border-left:5px solid #b8a037;border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:.88rem;background:white}}th,td{{padding:9px 8px;border-bottom:1px solid #e6e0d8;text-align:right}}th{{background:#f3efe9;position:sticky;top:0}}th:nth-child(2),td:nth-child(2),th:nth-child(7),td:nth-child(7){{text-align:left}}
.table-wrap{{overflow-x:auto}}code{{background:#eee8e0;padding:.1rem .3rem;border-radius:4px}}
</style></head><body><main data-report-audience="product stakeholders">
<header data-contract-section="title"><h1>Review of the arcuate-geometry ranking</h1><p class="small">Full GEBCO and geological-boundary run · 1,318 visually identified geometries · reviewed June 20, 2026</p></header>

<section class="summary" data-contract-section="executive-summary"><h2>Executive Summary</h2><ul>
<li><strong>The pipeline has produced a useful triage ranking, not a catalogue of impact structures.</strong> Nineteen candidates score at least 0.80, 82 at least 0.75, and 233 at least 0.70. These bands are convenient workload cut-offs; they are not calibrated probabilities or p-values.</li>
<li><strong>The highest scores primarily identify coherent circular topography.</strong> The score correlates most strongly with the composite topography term (Spearman ρ={correlations['Composite topography']:.2f}), annular peak percentile ({correlations['Annular peak percentile']:.2f}), and radius agreement ({correlations['Radius agreement']:.2f}). Geological independence is a weaker discriminator ({correlations['Geology independence']:.2f}).</li>
<li><strong>At least one conspicuous high-ranking cluster has a known non-impact explanation.</strong> arc_0370 at 57.43°N, 11.12°W coincides with the circular volcanic Anton Dohrn Seamount; nearby leading candidates occupy the Rockall Trough seamount province. This is a valuable empirical false-positive control.</li>
<li><strong>The next defensible step is calibration.</strong> Imagery has not yet contributed to any score, and randomized spatial nulls, labelled positive controls, false-discovery rates, and morphology-specific endogenic controls have not yet been run.</li>
</ul></section>

<section data-contract-section="key-findings"><h2>A manageable high-priority tail emerges</h2>
<p>The distribution is broad but concentrated around a median of {q.loc[0.5]:.3f}. The 95th percentile is {q.loc[0.95]:.3f} and the 99th percentile {q.loc[0.99]:.3f}. Reviewing the 82 candidates above 0.75 is therefore a practical first-pass workload; narrowing directly to the 19 above 0.80 risks overinterpreting arbitrary score precision.</p>
<figure><img src="charts/score_distribution.png" alt="Histogram of candidate scores"><figcaption>Scores are follow-up priorities. No null-derived significance threshold is currently available.</figcaption></figure>
</section>

<section><h2>The leaders are strong circular landforms—but not necessarily impacts</h2>
<p>The top candidate, arc_0373, scores 0.895 at an inferred diameter of 67.2 km. arc_0370, also in the top ten, lies at the published centre of Anton Dohrn Seamount, described by the <a href="https://jncc.gov.uk/our-work/anton-dohrn-seamount-mpa/">JNCC</a> as an extinct volcano. The <a href="https://webapps.bgs.ac.uk/memoirs/docs/B06844.html">British Geological Survey</a> identifies multiple volcanic centres in this same Rockall Basin region. This demonstrates that the detector is successfully finding real circular geomorphology while also admitting predictable volcanic false positives.</p>
<figure><img src="charts/top_candidates.png" alt="Ranked bars for the top candidates"><figcaption>Top 15 candidates by the corrected, authoritative CSV scoring pass.</figcaption></figure>
<div class="table-wrap"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Centre</th><th>Diameter km</th><th>Score</th><th>Topo.</th><th>Geology</th></tr></thead><tbody>{build_table(df)}</tbody></table></div>
</section>

<section><h2>The score is dominated by circularity evidence and resolution</h2>
<p>The ranking formula uses 78% topographic evidence and 22% geological independence, then multiplies the result by data quality. Within the topographic term, annular peak location, angular continuity, radius agreement, centre agreement, radial alignment, and relief are combined. Consequently, correlations with the final score are descriptive of score construction—not independent scientific validation.</p>
<figure><img src="charts/score_drivers.png" alt="Bar chart of score component correlations"><figcaption>Spearman correlations across all 1,318 candidates; these inputs are not statistically independent.</figcaption></figure>
<p>Geology has a modest effect: 643 candidates intersect mapped province boundaries, compared with 675 that do not. Their median scores are 0.560 and 0.603 respectively. {top20_no_boundary} of the top 20 have zero mapped boundary coincidence, partly because full independence receives the complete 22% geology contribution.</p>
</section>

<section><h2>Sub-10 km candidates cannot be judged fairly from this run</h2>
<p>The 48 candidates below 10 km diameter have a median score of only {df.loc[df.diameter_km.lt(10), 'followup_score'].median():.3f}, versus roughly 0.59–0.61 in the larger size bands. This is mainly a resolution and quality-gating effect, not evidence that small structures are intrinsically less plausible. In total, {poor_quality} candidates have data quality below one and eight are driven to zero.</p>
<figure><img src="charts/score_by_diameter.png" alt="Box plots of scores by diameter"><figcaption>Scores grouped by inferred candidate diameter. Small-crater evaluation needs higher-resolution elevation data.</figcaption></figure>
</section>

<section data-contract-section="recommended-next-steps"><h2>Recommended Next Steps</h2><ol>
<li><strong>Deduplicate spatially before field prioritisation.</strong> Thirteen overlapping pairs occur within the top 100, including near-identical candidate pairs. Consolidate these into structure-level clusters so one landform cannot consume several review slots.</li>
<li><strong>Run empirical nulls before interpreting the upper tail.</strong> Randomly translate/rotate each arc within matched latitude, relief and land/ocean strata; use circularly shifted annuli and radius-scrambled controls; then report empirical p-values and false-discovery-rate adjusted q-values.</li>
<li><strong>Create labelled control sets.</strong> Include confirmed impacts as positives and volcanoes, calderas, seamounts, salt structures, tectonic basins, coastal embayments and bathymetric acquisition artefacts as explicit negatives. Anton Dohrn and the Rockall Trough seamounts should be mandatory controls.</li>
<li><strong>Add imagery and independent geophysics.</strong> Score cloud-controlled optical composites where meaningful, but use gravity, magnetics and higher-resolution DEM/bathymetry as stronger discriminants. Refit weights only after blinded labels exist.</li>
<li><strong>Review the top 82 in two stages.</strong> First eliminate known endogenic structures and data artefacts; then subject the surviving topography-independent candidates to detailed geological review.</li>
</ol></section>

<section data-contract-section="further-questions"><h2>Further Questions</h2><ul>
<li>How many of the visually identified arcs were intentionally drawn around known impacts, volcanoes or other controls?</li>
<li>Should very large candidates (hundreds to thousands of kilometres) be analysed separately from crater-scale structures?</li>
<li>Are geological province boundaries the correct negative evidence, or should faults, lithological contacts and circular intrusions be represented independently?</li>
<li>What minimum posterior evidence would justify inclusion in the manuscript: morphology alone, or morphology plus an independent geophysical anomaly?</li>
</ul></section>

<section data-contract-section="caveats-and-assumptions"><h2>Caveats and Assumptions</h2><div class="callout">
<p><strong>The ranking is provisional.</strong> It lacks imagery measurements, empirical null distributions and calibrated labels. The score’s decimals should not be read as measurement precision. GEBCO’s heterogeneous source coverage can also imprint survey artefacts, especially offshore. The current geological term rewards distance from broad province boundaries but does not test detailed local stratigraphy or structure. Finally, the visual-source geometries nearly all have complete angular coverage, so the run evaluates preselected near-circles rather than testing whether arbitrary natural linework is circular.</p>
</div></section>
</main></body></html>"""
    (OUTPUT / "report.html").write_text(html_report, encoding="utf-8")


def write_notes(df: pd.DataFrame, correlations: pd.Series) -> None:
    notes = {
        "authoritative_input": str(INPUT),
        "row_count": len(df),
        "score_formula": "data_quality * (0.78 * topography_score_unweighted + 0.22 * geology_independence)",
        "imagery_included": "imagery_score" in df.columns,
        "score_quantiles": {str(k): float(v) for k, v in df.followup_score.quantile([0, .25, .5, .75, .9, .95, .99, 1]).items()},
        "threshold_counts": {str(t): int((df.followup_score >= t).sum()) for t in [.70, .75, .80, .85]},
        "spearman_correlations": {str(k): float(v) for k, v in correlations.items()},
        "chart_map": [
            {"section": "High-priority tail", "family": "Distribution", "type": "Histogram", "asset": "charts/score_distribution.png"},
            {"section": "Leaders", "family": "Comparison & Ranking", "type": "Ranked horizontal bars", "asset": "charts/top_candidates.png"},
            {"section": "Score construction", "family": "Comparison & Ranking", "type": "Horizontal bars", "asset": "charts/score_drivers.png"},
            {"section": "Resolution", "family": "Distribution", "type": "Box plot", "asset": "charts/score_by_diameter.png"},
        ],
        "known_limitations": [
            "No empirical null distribution or FDR calibration",
            "No imagery_score column in completed ranking",
            "Topographic circularity is not impact specificity",
            "Small candidates are resolution-limited",
            "Spatially overlapping candidates have not been consolidated",
        ],
    }
    (OUTPUT / "source_notes.json").write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    df = pd.read_csv(INPUT).sort_values("rank").reset_index(drop=True)
    assert len(df) == 1318
    assert df.candidate_id.is_unique
    assert df.followup_score.is_monotonic_decreasing
    setup_style()
    score_distribution(df)
    top_candidates(df)
    score_by_diameter(df)
    correlations = score_drivers(df)
    write_report(df, correlations)
    write_notes(df, correlations)
    print(f"Wrote {OUTPUT / 'report.html'}")


if __name__ == "__main__":
    main()
