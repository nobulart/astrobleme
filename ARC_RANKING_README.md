# Arcuate candidate ranking pipeline

This implementation ranks the 1,318 visually identified arcuate geometries for follow-up using GEBCO terrain morphology and coincidence with global geological-province boundaries. Scores are candidate-screening evidence, not probabilities of impact.

## Run

```bash
MPLBACKEND=Agg python3 run_arc_ranker.py --output ranking_output
```

Pilot run:

```bash
MPLBACKEND=Agg python3 run_arc_ranker.py --limit 25 --output ranking_pilot
```

## Outputs

- `arc_ranking.csv`: sortable evidence table.
- `arc_ranking.geojson`: QGIS-ready candidate centres and metrics.
- `ranking_summary.json`: score distribution and top candidates.
- `sentinel2_stac_requests.json`: reproducible imagery-query manifest.
- `diagnostics/`: plots and compressed terrain arrays for the highest-ranked candidates.

## Score components

- GEBCO resolution/data quality.
- Radial-gradient anisotropy.
- Constrained Hough-like radial peak strength.
- Angular continuity.
- Agreement with the annotated radius and centre.
- Annular relief after regional detrending.
- Penalty for coincidence with geological-province boundaries.
- Optional imagery ring-edge score for normalized candidate-centred PNG patches.

The provisional weights are deliberately transparent in `combined_score()`. They must be calibrated with confirmed impacts and matched endogenic controls before inferential use.

## Imagery convention

Optional PNG patches must be square, centred on the candidate and span ±1.75 candidate radii. Name them `arc_0000.png`, `arc_0001.png`, and so on, and pass `--imagery-dir`.

The STAC manifest targets the public `sentinel-2-l2a` collection. Downloading and mosaicking are kept separate because global imagery retrieval is large and requires explicit decisions about season, cloud masking, spectral bands and storage.

## YOLOLens integration

The diagnostic `.npz` files provide candidate-centred elevation, detrended elevation, radial-gradient and radius arrays suitable for preparing terrestrial training channels. Reuse YOLOLens's overlapping-tile inference and QGIS export, but retrain an arc/segmentation head on terrestrial examples. Do not apply the lunar weights or hard-coded lunar elevation normalization directly.

## Important limitations

- GEBCO spacing is 15 arc-seconds, but effective source resolution and accuracy vary spatially.
- The supplied dataset does not include GEBCO's source-identifier grid, so interpolation artefacts cannot yet be penalized.
- `global_gprv.kml` contains generalized provinces, not detailed faults or stratigraphy.
- Circular terrain morphology and boundary independence are prioritization evidence only.
