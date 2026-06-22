# Arcuate-geometry study results GeoJSON

`arcuate_geometries_study_results.geojson` contains 1,318 row-preserving features, one for every original geometry in `arcuate_geometries.geojson`.

Candidate-level morphology, geology, GEBCO TID, gravity, magnetic, sediment and CRUST1 fields retain their established pipeline names. Operational review fields are joined by `candidate_id`. Consolidation and GEM active-fault controls are repeated with a `structure_` prefix and must be interpreted at structure grain. Fields beginning `manual_` are deliberately `null` until captured, except `manual_capture_complete=false`.

Scores rank follow-up priority and are not impact probabilities. Circular morphology and geophysical concordance are not diagnostic of impact. See `arcuate_geometries_study_results_schema.json` for the field dictionary.

Regenerate with:

```bash
python3 build_study_results_geojson.py
```
