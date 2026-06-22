# Astrobleme catalogue repair

The original `astroblemes.geojson` remains unchanged. The repair is reproducible from `repair_astrobleme_catalog.py`, dated Wikipedia wikitext snapshots, and Reimold & Koeberl (2014).

## Defects and repair policy

- Forty plain-numeric `diameter_raw` values disagreed with `diameter_km`: 39 were exactly tenfold inflations and Gosses Bluff was 32 km stored as 220 km. All 40 rendered values match the dated 2026-06-21 Wikipedia confirmed-list snapshot. The defect arose from using hidden Wikipedia sort keys as displayed diameters.
- Generated circle geometries for the 40 affected rows were rebuilt from the repaired diameter and preserved centre using 96 geodesic segments.
- Seventy display labels were normalized. Coordinate-template labels are no longer treated as structure identities; genuine multi-coordinate table rows retain a subordinate coordinate label.
- All 253 source rows remain in `astroblemes_repaired.geojson`.
- Four lower-precedence duplicate records are marked `analytical_include=false`: Cerro do Jarau, Rochechouart, Shiyli/Chiyli, and Temimichat/Temimichat Ghallaman. The deduplicated `astroblemes_analysis.geojson` contains 249 records.
- Of 188 Wikipedia-derived records, 184 centres match a coordinate in the dated source snapshots within 5 km (five through coordinate-matched aliases). Four current source rows omit coordinates; their imported historical centres are retained and explicitly labelled.
- Sixty-five African-review records retain table/text provenance from the supplied PDF. No unsupported status promotion was performed.

## Corrected rerun

Command:

```bash
MPLBACKEND=Agg python3 analysis.py \
  --astroblemes catalog_repair/astroblemes_analysis.geojson \
  --output-dir catalog_repair/rerun
```

Seed `20260619`; 1,999 size-label permutations; 9,999 spatial null replicates.

| Result | Defective catalogue | Repaired analytical catalogue |
| --- | ---: | ---: |
| Catalogue records | 253 | 249 |
| Local EID-match flags | 84 | 82 |
| Fitted arc/catalogue diameter multiplier | 5.53 | 9.10 |
| Shifted KS statistic | 0.1623 | 0.0510 |
| Permutation p for residual shape difference | 0.0005 | 0.1450 |
| All-catalogue tail `xmin` | 220 km | 22 km |
| All-catalogue tail PDF exponent | 2.784 | 1.926 |

The corrected result does not reject a common distributional shape after fitting a multiplicative scale. It does not confirm a universal 9.1× or 10× law; the multiplier remains an estimated, catalogue-dependent open hypothesis.

Spatial-centre conclusions are stable: 16 locally EID-matched entries remain within 100 km of an arc centre, with median nearest distance 241.3 km. Corrected longitude-rotation p-values are 0.0147 for the count and 0.0049 for median distance; confidence-label permutation p-values are 0.1275 and 0.2623. Thus proximity exceeds arbitrary longitudinal alignment but still does not distinguish local EID matches from other catalogue entries.

## Outputs

- `astroblemes_repaired.geojson`: row-preserving repaired source catalogue.
- `astroblemes_analysis.geojson`: deduplicated 249-record analytical catalogue.
- `catalogue_repair_audit.csv`: one audit row per original record.
- `catalogue_repair_summary.json`: source hashes and validation counts.
- `rerun/analysis_results.json`: controlling corrected statistics.
- `rerun/fig_size_distributions.*`, `fig_catalogue_maps.*`, and `fig_spatial_nulls.*`: regenerated figures.
- `rerun/table_arc_bins.tex` and `rerun/table_nulls.tex`: regenerated TeX fragments.

## Remaining review items

Current Wikipedia rows omit coordinates for Bajo Hondo, Pantasma, Brushy Creek Feature, and Victoria Island. Their centres should be checked against the dated citations or an archived version before treating centre-level matches as fully source-verified. Local EID-match flags also remain historical compilation fields rather than a live authoritative status reconciliation.
