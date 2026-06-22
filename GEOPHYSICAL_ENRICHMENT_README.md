# Geophysical and acquisition-quality enrichment

This layer adds independent follow-up evidence to all 1,318 visually identified arcuate geometries. It does **not** replace or modify `followup_score`, and none of its scores is an impact probability.

## Inputs and roles

- GEBCO 2026 TID: direct-versus-modelled support, source heterogeneity, and candidate-ring/source-transition alignment.
- WGM2012 Bouguer, free-air, isostatic, and disturbance gravity: circular radial-gradient continuity and central/annular anomaly contrasts.
- EMAG2 v3: the same circular-anisotropy measures for the column-6 magnetic anomaly upward-continued to a continuous 4 km altitude. The accompanying `EMAG2_readme.txt` confirms the column definition and units (nT).
- GlobSed v3: contextual central/annular sediment-thickness patterns; valid principally offshore.
- CRUST1.0: nearest 1-degree crust and sediment context. It is explicitly too coarse for candidate-scale ring evidence.

Circular evidence is measured in a candidate-centred local frame. Each scalar layer is detrended at a scale proportional to candidate radius; radial-versus-tangential gradient alignment, angular continuity, annular gradient enrichment, and central/annular contrast are retained as separate columns. A resolution- and coverage-weighted `*_ring_score` supports screening only.

## Reproduce

```bash
python3 build_emag2_cache.py
python3 enrich_arc_ranking.py
python3 run_geophysical_nulls.py
python3 summarize_geophysical_nulls.py
python3 build_geophysical_shortlist.py
python3 -m unittest discover -s tests -v
```

The EMAG2 conversion creates a 223 MB random-access cache under `geophysical_cache/emag2`; it does not alter the 4 GB source CSV.

## Null designs

1. **Domain-matched longitude rotations.** Nineteen null locations per candidate preserve latitude and radius and match GEBCO-TID land/ocean/mixed class. A 9,999-replicate global resampling tests whether observed evidence exceeds the same-latitude background.
2. **Stratified cross-layer permutations.** Geophysical scores are permuted among candidates within land/ocean/mixed and log-diameter-decile strata. A 9,999-replicate test asks whether geophysics agrees with the independent morphology ranking beyond broad domain and scale.

Seed: `20260621`. Complete longitude-rotation sets were obtained for 1,285/1,318 candidates; mixed coastal/source cells account for incomplete matches. Candidate-level p-values have minimum 0.05 and are not suitable for discovery claims or unqualified multiple-testing inference.

## Current global results

| Test | Observed | Null expectation or 95% interval | One-sided p |
| --- | ---: | ---: | ---: |
| TID artefact-risk mean | 0.1137 | mean 0.1219; 0.1174–0.1266 | 0.9998 |
| Bouguer ring-score median | 0.3017 | mean 0.2706; 0.2663–0.2747 | 0.0001 |
| Free-air ring-score median | 0.3262 | mean 0.2792; 0.2746–0.2840 | 0.0001 |
| Magnetic ring-score median | 0.2897 | mean 0.2866; 0.2812–0.2922 | 0.1268 |

Morphology-ranking concordance remained positive for Bouguer gravity (Spearman rho 0.1727, stratified permutation p 0.0001) and free-air gravity (rho 0.1584, p 0.0001), but not magnetic evidence (rho -0.0173, p 0.0717).

These results establish gravity/topography concordance in the visually selected inventory, not impact origin. Because GEBCO morphology and gravity covary for volcanic edifices, basins, margins, and other endogenic structures, geological controls and labelled negative controls remain necessary. Anton Dohrn (`arc_0370`) is an instructive high-scoring volcanic negative control.

## Outputs

- `geophysical_output/geophysical_evidence.csv`: new evidence only, one row per arc.
- `geophysical_output/arc_ranking_enriched.csv`: existing ranking columns plus evidence; the original ranking is unchanged.
- `geophysical_output/evidence_summary.json`: source fingerprints and interpretation policy.
- `geophysical_output/nulls/longitude_rotation_null_rows.csv`: 24,861 accepted null rows.
- `geophysical_output/nulls/candidate_null_pvalues.csv`: coarse candidate screening diagnostics.
- `geophysical_output/nulls/geophysical_null_results.json`: controlling global null summary.
- `geophysical_output/geophysical_review_priority.csv`: transparent A–D review tiers. Tier A requires morphology score ≥0.75, both Bouguer and free-air evidence at or above the within-domain/size-stratum 75th percentile, and TID artefact risk ≤0.25. These are operational thresholds, not significance classes.

Current counts are 26 Tier A, 6 Tier B, 50 Tier C, and 1,236 background rows. Anton Dohrn is Tier A, demonstrating why a tier means “review this cross-layer signal” rather than “likely impact.”

Macrostrat, a valid raw GEM active-fault dataset, and actual Landsat pixels remain future enrichment channels. The local GEM files currently contain saved HTML rather than GIS features, and the Landsat directory contains scene metadata rather than imagery.
