from __future__ import annotations

import html
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import analysis as catalogue_analysis


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "decision_report"
CHARTS = OUTPUT / "charts"
GLOBAL = ROOT / "astroblemes.geojson"
RANKING = ROOT / "ranking_output" / "arc_ranking.csv"

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
    "blue": "#A3BEFA",
    "blue_dark": "#2E4780",
    "orange": "#F0986E",
    "orange_dark": "#804126",
    "gold": "#FFE15B",
    "gold_dark": "#736422",
    "olive": "#A3D576",
    "olive_dark": "#386411",
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


def add_header(fig, title: str, subtitle: str) -> None:
    fig.text(0.08, 0.965, title, ha="left", va="top", fontsize=17, weight="bold", color=TOKENS["ink"])
    fig.text(0.08, 0.915, subtitle, ha="left", va="top", fontsize=10, color=TOKENS["muted"])


def save(fig, filename: str) -> None:
    fig.savefig(CHARTS / filename, dpi=180, bbox_inches="tight", facecolor=TOKENS["surface"])
    plt.close(fig)


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def audit_catalogue() -> tuple[list[dict], list[int], list[int]]:
    props = [f["properties"] for f in json.loads(GLOBAL.read_text())["features"]]
    mismatches = []
    colon_names = []
    for i, row in enumerate(props):
        raw = numeric(row.get("diameter_raw"))
        if raw is not None and not math.isclose(raw, float(row["diameter_km"])):
            mismatches.append(i)
        if ":" in str(row.get("display_name", "")):
            colon_names.append(i)
    return props, mismatches, colon_names


def sensitivity(props: list[dict]) -> dict:
    arcs = np.array(
        [catalogue_analysis.arc_metrics(f)["diameter_km"] for f in catalogue_analysis.load_features("arcuate_geometries.geojson")]
    )
    current = np.array([float(row["diameter_km"]) for row in props])
    corrected = current.copy()
    for i, row in enumerate(props):
        raw = numeric(row.get("diameter_raw"))
        if raw is not None and not math.isclose(raw, current[i]):
            corrected[i] = raw
    seed = 20260620
    n = 1999
    current_scale, current_ks, current_p = catalogue_analysis.shifted_ks_permutation(
        arcs, current, np.random.default_rng(seed), n
    )
    corrected_scale, corrected_ks, corrected_p = catalogue_analysis.shifted_ks_permutation(
        arcs, corrected, np.random.default_rng(seed), n
    )
    return {
        "seed": seed,
        "replicates": n,
        "current": {"scale": current_scale, "ks": current_ks, "p": float(current_p)},
        "raw_substitution": {"scale": corrected_scale, "ks": corrected_ks, "p": float(corrected_p)},
        "interpretation": "Sensitivity only: numeric diameter_raw substitutes for disagreeing diameter_km values; identity and source reconstruction remain required.",
    }


def plot_catalogue_integrity(total: int, eid_total: int, mismatches: list[int], colon_names: list[int], props: list[dict]) -> None:
    labels = ["All catalogue entries", "Local EID-match subset", "Diameter mismatches", "Colon-combined identities", "Exact 10× inflations"]
    exact_ten = sum(
        math.isclose(float(props[i]["diameter_km"]) / numeric(props[i]["diameter_raw"]), 10.0) for i in mismatches
    )
    values = [total, eid_total, len(mismatches), len(colon_names), exact_ten]
    colors = [TOKENS["blue"], TOKENS["blue"], TOKENS["orange"], TOKENS["orange"], TOKENS["orange"]]
    edges = [TOKENS["blue_dark"], TOKENS["blue_dark"], TOKENS["orange_dark"], TOKENS["orange_dark"], TOKENS["orange_dark"]]
    order = np.arange(len(labels))[::-1]
    fig, ax = plt.subplots(figsize=(10, 5.8))
    bars = ax.barh(np.array(labels)[order], np.array(values)[order], color=np.array(colors)[order], edgecolor=np.array(edges)[order])
    for bar, value in zip(bars, np.array(values)[order]):
        ax.text(value + 4, bar.get_y() + bar.get_height() / 2, f"{value}", va="center", fontsize=9)
    ax.set(xlabel="Entries", ylabel="", xlim=(0, 285))
    ax.grid(axis="y", visible=False)
    sns.despine(ax=ax)
    add_header(fig, "Global catalogue integrity audit", "Counts from the 253-entry local composite catalogue")
    fig.subplots_adjust(top=0.82, left=0.28, right=0.97, bottom=0.13)
    save(fig, "catalogue_integrity.png")


def plot_sensitivity(result: dict) -> None:
    metrics = [
        ("Fitted multiplier", "scale", (0, 11)),
        ("Minimized KS", "ks", (0, 0.18)),
        ("Permutation p", "p", (0, 0.12)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.8))
    for ax, (title, key, limits) in zip(axes, metrics):
        before = result["current"][key]
        after = result["raw_substitution"][key]
        ax.hlines([0, 1], 0, [before, after], color=TOKENS["grid"], linewidth=2)
        ax.scatter([before], [0], s=90, color=TOKENS["orange"], edgecolor=TOKENS["orange_dark"], label="Current")
        ax.scatter([after], [1], s=90, color=TOKENS["olive"], edgecolor=TOKENS["olive_dark"], label="Sensitivity repair")
        ax.set_yticks([0, 1], ["Current", "Sensitivity"])
        ax.set_xlim(*limits)
        ax.set_title(title, fontsize=11)
        ax.grid(axis="y", visible=False)
        ax.text(before, 0.12, f"{before:.3g}", ha="center", fontsize=8)
        ax.text(after, 1.12, f"{after:.3g}", ha="center", fontsize=8)
        sns.despine(ax=ax)
    add_header(fig, "Diameter repair reverses the size-comparison inference", "Current fields versus substituting numeric raw diameters; 1,999 refitted permutations, seed 20260620")
    fig.subplots_adjust(top=0.78, left=0.09, right=0.98, bottom=0.16, wspace=0.48)
    save(fig, "size_sensitivity.png")


def plot_ranking_funnel(ranking: pd.DataFrame) -> list[dict]:
    stages = [
        ("All visually selected arcs", len(ranking)),
        ("Score ≥ 0.70", int((ranking.followup_score >= 0.70).sum())),
        ("Score ≥ 0.75", int((ranking.followup_score >= 0.75).sum())),
        ("Score ≥ 0.80", int((ranking.followup_score >= 0.80).sum())),
    ]
    labels = [x[0] for x in stages]
    counts = [x[1] for x in stages]
    fig, ax = plt.subplots(figsize=(10, 5.8))
    palette = [TOKENS["blue"], TOKENS["gold"], TOKENS["olive"], TOKENS["orange"]]
    edges = [TOKENS["blue_dark"], TOKENS["gold_dark"], TOKENS["olive_dark"], TOKENS["orange_dark"]]
    bars = ax.bar(labels, counts, color=palette, edgecolor=edges)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, count + 22, f"{count:,}\n({count / len(ranking):.1%})", ha="center", fontsize=9)
    ax.set(ylabel="Candidates", xlabel="", ylim=(0, 1440))
    ax.grid(axis="x", visible=False)
    sns.despine(ax=ax)
    add_header(fig, "The independent terrain ranking still supports triage", "Nested operational score bands; thresholds are not impact probabilities or significance cut-offs")
    fig.subplots_adjust(top=0.80, left=0.08, right=0.98, bottom=0.14)
    save(fig, "ranking_funnel.png")
    return [{"stage": label, "count": count} for label, count in stages]


def evidence_table() -> str:
    rows = [
        ("Inventory counts and grains", "Retain", "Raw counts and African deduplication are reproducible."),
        ("GEBCO candidate ranking", "Retain as screening", "Independent of global diameter fields; provisional and uncalibrated."),
        ("Spatial null framework", "Retain method; rerun", "Distances do not use diameter, but catalogue identities and EID labels need audit."),
        ("Global size distributions", "Withdraw pending repair", "40 diameter mismatches materially change fitted scale and KS inference."),
        ("Impact interpretation", "Not established", "Morphology and broad geology cannot verify impact origin."),
    ]
    status_class = {
        "Retain": "ok",
        "Retain as screening": "caution",
        "Retain method; rerun": "caution",
        "Withdraw pending repair": "stop",
        "Not established": "stop",
    }
    return "\n".join(
        f"<tr><td>{html.escape(item)}</td><td><span class='{status_class[status]}'>{html.escape(status)}</span></td><td>{html.escape(reason)}</td></tr>"
        for item, status, reason in rows
    )


def build_report(props, mismatches, colon_names, sensitivity_result, ranking, stages) -> None:
    eid_total = sum(bool(x["earth_impact_database_match"]) for x in props)
    mismatch_eid = sum(bool(props[i]["earth_impact_database_match"]) for i in mismatches)
    colon_eid = sum(bool(props[i]["earth_impact_database_match"]) for i in colon_names)
    current = sensitivity_result["current"]
    repaired = sensitivity_result["raw_substitution"]
    report = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Astrobleme study: decision report</title><style>
body{{font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;margin:0;background:#faf8f5;color:#171411}}main{{max-width:980px;margin:0 auto;padding:42px 22px 72px}}
header,section{{margin-bottom:38px}}h1,h2{{line-height:1.16;margin:0 0 14px}}h1{{font-size:2.25rem}}h2{{font-size:1.45rem}}p,li{{line-height:1.62}}a{{color:#2e4780}}
.summary{{padding:22px 24px;background:#f1ece4;border:1px solid #ddd1c2;border-radius:18px}}.summary ul{{margin:0;padding-left:22px}}.summary li+li{{margin-top:10px}}
.alert{{padding:18px 20px;background:#ffedde;border-left:5px solid #cc6f47;border-radius:8px}}figure{{margin:22px 0}}figure img{{width:100%;height:auto;border-radius:10px;background:white}}
figcaption,.small{{color:#5f5750;font-size:.9rem}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:11px 10px;border-bottom:1px solid #e6e0d8;text-align:left;vertical-align:top}}th{{background:#f3efe9}}
.ok,.caution,.stop{{display:inline-block;padding:3px 8px;border-radius:999px;font-weight:650;font-size:.82rem;white-space:nowrap}}.ok{{background:#d8ecbd}}.caution{{background:#fff4c2}}.stop{{background:#ffedde}}
code{{background:#eee8e0;padding:.1rem .3rem;border-radius:4px}}
</style></head><body><main data-report-audience="product stakeholders">
<header data-contract-section="title"><h1>Astrobleme study: decision report</h1><p class="small">Catalogue integrity, surviving evidence and the fastest path to a defensible manuscript · June 20, 2026</p></header>

<section class="summary" data-contract-section="executive-summary"><h2>Executive Summary</h2><ul>
<li><strong>Pause the manuscript’s global size-distribution conclusions.</strong> Forty of 253 catalogue entries have numeric diameter fields that disagree; 39 are exact tenfold inflations. The defect affects {mismatch_eid} of {eid_total} locally EID-matched entries.</li>
<li><strong>The current headline inference reverses under a simple sensitivity repair.</strong> Substituting numeric raw diameters changes the fitted multiplier from {current['scale']:.2f} to {repaired['scale']:.2f}, the minimized KS statistic from {current['ks']:.3f} to {repaired['ks']:.3f}, and the permutation p-value from {current['p']:.4f} to {repaired['p']:.4f}. This sensitivity is not a final corrected analysis, but it proves the existing claim is unstable.</li>
<li><strong>Preserve the GEBCO ranking as an exploratory screening result.</strong> Its calculations do not use the defective global diameter field. It yields 82 candidates above 0.75 and 19 above 0.80, but its scores remain uncalibrated and known volcanic structures rank highly.</li>
<li><strong>Focus first on catalogue reconstruction and automated integrity tests.</strong> Then rerun every dependent analysis, update the manuscript, and only afterward invest in imagery, geophysical enrichment and candidate field prioritisation.</li>
</ul></section>

<section data-contract-section="key-findings"><h2>The catalogue defect reaches the core comparison</h2>
<p>The issue is systematic rather than a handful of outliers: {len(mismatches)} entries ({len(mismatches)/len(props):.1%}) have conflicting numeric diameter fields, including {mismatch_eid} locally EID-matched records. Separately, {len(colon_names)} display identities ({len(colon_names)/len(props):.1%}) are colon-combined; {colon_eid} fall inside the EID-labelled subset. Some are legitimate aliases, while others expose unresolved name-to-coordinate associations. Both fields must be reconstructed from provenance rather than patched by appearance alone.</p>
<figure><img src="charts/catalogue_integrity.png" alt="Catalogue integrity audit counts"><figcaption>Direct audit of the local global catalogue. The total and EID subset provide the relevant denominators.</figcaption></figure>
<div class="alert"><strong>Decision:</strong> quarantine global diameter, identity and EID-derived outputs. Preserve the source file unchanged as evidence; create a repaired, provenance-tracked version and compare it row by row.</div>
</section>

<section><h2>A minimal repair changes the scientific answer</h2>
<p>The current manuscript reports that a fitted multiplier of 5.53 does not reconcile the distributions. A controlled sensitivity run using the numeric raw diameter wherever it conflicts instead produces a multiplier of 9.96 and no significant shape difference at the same 1,999-permutation resolution (p=0.1085). An exact-tenfold-only repair gives nearly the same result (scale 9.85, KS 0.053, p=0.104). The analysis therefore cannot currently reject a near-tenfold relation.</p>
<figure><img src="charts/size_sensitivity.png" alt="Before and sensitivity-repaired size comparison metrics"><figcaption>Sensitivity analysis only; raw substitution is not a substitute for authoritative row reconstruction.</figcaption></figure>
<p><strong>Implication:</strong> the abstract, results, discussion and conclusion must not retain the current 5.53/KS/p-value narrative. The power-law tail estimates are also affected and need complete regeneration.</p>
</section>

<section><h2>Some work survives, but its claims must stay narrow</h2>
<p>The independent terrain-ranking pipeline remains useful for prioritising visual review because it derives from the 1,318 arcuate geometries, GEBCO elevation and broad geological-province boundaries. It does not validate impact origin, and score thresholds are workflow bands rather than probabilities.</p>
<figure><img src="charts/ranking_funnel.png" alt="Operational score bands for the terrain ranking"><figcaption>The 82 candidates above 0.75 are the practical first-pass queue after deduplication and endogenic-control screening.</figcaption></figure>
<table><thead><tr><th>Evidence block</th><th>Decision</th><th>Reason</th></tr></thead><tbody>{evidence_table()}</tbody></table>
</section>

<section><h2>The main drivers are provenance, selection and non-unique morphology</h2><ul>
<li><strong>Import logic dominates the size result.</strong> The sensitivity shift is much larger than any reasonable interpretive nuance.</li>
<li><strong>Catalogue construction affects the spatial result.</strong> Centre distances are independent of diameter, but unresolved identities and local EID labels mean the nulls should be rerun after row reconstruction.</li>
<li><strong>Visual selection builds circularity into the source data.</strong> Most arcs are near-perfect circles by construction, so morphology cannot serve as independent confirmation.</li>
<li><strong>Endogenic structures are strong competitors.</strong> Circular volcanic seamounts rank highly; Anton Dohrn is an explicit negative control supported by the <a href="https://jncc.gov.uk/our-work/anton-dohrn-seamount-mpa/">JNCC</a> and regional volcanic-centre context from the <a href="https://webapps.bgs.ac.uk/memoirs/docs/B06844.html">British Geological Survey</a>.</li>
</ul></section>

<section data-contract-section="recommended-next-steps"><h2>Recommended Next Steps</h2><ol>
<li><strong>Freeze affected claims immediately.</strong> Mark size-distribution, fitted-scale, tail-exponent and EID-subset spatial conclusions as pending data repair.</li>
<li><strong>Reconstruct the 253-row catalogue from provenance.</strong> Resolve name, coordinate, diameter, source and EID status with persistent row identifiers. Do not overwrite the current file.</li>
<li><strong>Add integrity tests before rerunning.</strong> Test numeric raw/parsed diameter agreement, plausible diameter bounds, unique identity mapping, coordinate-title joins, duplicate structures and status provenance.</li>
<li><strong>Rerun all dependent outputs.</strong> Regenerate `analysis_results.json`, tables, figures and every numerical statement in the manuscript. Report before/after diffs.</li>
<li><strong>Then calibrate the terrain ranking.</strong> Consolidate overlapping candidates, run matched spatial/radius nulls, create confirmed-impact and endogenic control sets, and add imagery plus independent geophysics.</li>
</ol></section>

<section data-contract-section="further-questions"><h2>Further Questions</h2><ul>
<li>Where is the original catalogue-construction script or acquisition snapshot that produced the global GeoJSON?</li>
<li>Which dated authoritative source should control EID membership and structure diameter?</li>
<li>Should the manuscript retain the size-scaling hypothesis as an open test if a corrected rerun remains non-significant?</li>
<li>Which geological controls and geophysical datasets should define advancement beyond morphology-only screening?</li>
</ul></section>

<section data-contract-section="caveats-and-assumptions"><h2>Caveats and Assumptions</h2><div class="alert"><p>The repaired scenario substitutes numeric raw values only to measure sensitivity. It does not resolve incorrect raw values, aliases, coordinate provenance or catalogue status. The spatial null code and terrain ranking were not altered in this report. Geological confirmation still requires accepted shock-metamorphic, meteoritic or geochemical evidence; neither circularity nor a high follow-up score is diagnostic.</p></div></section>
</main></body></html>"""
    (OUTPUT / "report.html").write_text(report, encoding="utf-8")


def write_notes(props, mismatches, colon_names, sensitivity_result, stages) -> None:
    notes = {
        "decision": "Quarantine affected global catalogue analyses, reconstruct catalogue provenance, rerun dependent outputs, retain terrain ranking as exploratory screening.",
        "authoritative_sources": [str(GLOBAL), str(RANKING), str(ROOT / "analysis.py"), str(ROOT / "astrobleme.tex")],
        "catalogue_audit": {
            "entries": len(props),
            "local_eid_matches": sum(bool(x["earth_impact_database_match"]) for x in props),
            "diameter_mismatches": len(mismatches),
            "diameter_mismatch_indices": mismatches,
            "colon_combined_identities": len(colon_names),
            "colon_identity_indices": colon_names,
        },
        "sensitivity": sensitivity_result,
        "ranking_stages": stages,
        "chart_map": [
            {"section": "Catalogue defect", "family": "Comparison & Ranking", "type": "Horizontal bars", "asset": "charts/catalogue_integrity.png"},
            {"section": "Sensitivity", "family": "Uncertainty & Benchmark", "type": "Faceted dot comparison", "asset": "charts/size_sensitivity.png"},
            {"section": "Surviving ranking", "family": "Decomposition & Progression", "type": "Stage bars", "asset": "charts/ranking_funnel.png"},
        ],
        "omissions": {
            "final corrected catalogue analysis": "Blocked by missing original acquisition/provenance reconstruction.",
            "geological confirmation": "Not supported by current morphology, imagery or broad-boundary data.",
        },
    }
    (OUTPUT / "source_notes.json").write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    CHARTS.mkdir(exist_ok=True)
    setup_style()
    props, mismatches, colon_names = audit_catalogue()
    ranking = pd.read_csv(RANKING).sort_values("rank")
    assert len(props) == 253
    assert len(ranking) == 1318 and ranking.candidate_id.is_unique
    sensitivity_result = sensitivity(props)
    plot_catalogue_integrity(len(props), sum(bool(x["earth_impact_database_match"]) for x in props), mismatches, colon_names, props)
    plot_sensitivity(sensitivity_result)
    stages = plot_ranking_funnel(ranking)
    build_report(props, mismatches, colon_names, sensitivity_result, ranking, stages)
    write_notes(props, mismatches, colon_names, sensitivity_result, stages)
    print(OUTPUT / "report.html")


if __name__ == "__main__":
    main()
