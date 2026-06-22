# Inductive astrobleme screening summary

> These outputs are candidate-screening products only. Circular morphology, gravity anomalies, and spatial coincidence are non-diagnostic. Impact confirmation requires accepted shock metamorphic, meteoritic, or projectile-derived geochemical evidence.

## Inputs used

- study_results_geojson/arcuate_geometries_study_results.geojson
- /Users/craig/ECDO/papers/astrobleme/data/controls.geojson

## Inputs missing or skipped

- None

## Gravity-first shortlist

| gravity_first_rank | candidate_id | gravity_first_review_score | gravity_strong | tid_risk_high |
|---|---|---|---|---|
| 1 | arc_0371 | 0.9169 | True | False |
| 2 | arc_0674 | 0.8910 | True | False |
| 3 | arc_0687 | 0.8897 | True | False |
| 4 | arc_1088 | 0.8895 | True | False |
| 5 | arc_1105 | 0.8875 | True | False |
| 6 | arc_0795 | 0.8861 | True | False |
| 7 | arc_0437 | 0.8829 | True | False |
| 8 | arc_0697 | 0.8747 | True | False |
| 9 | arc_0605 | 0.8727 | True | False |
| 10 | arc_0899 | 0.8713 | True | False |

The gravity-first review score is a transparent review priority, not an impact probability. Configuration: `{'gravity_strong_threshold': 0.75, 'gravity_weak_threshold': 0.25, 'magnetic_support_threshold': 0.75, 'magnetic_discordant_threshold': 0.25, 'tid_high_risk_threshold': 0.25, 'large_scale_diameter_km': 1000.0, 'resolution_warning_diameter_km': 10.0, 'ring_center_fraction': 0.25, 'ring_min_adjacent_ratio': 1.2, 'ring_min_angular_coverage': 0.35, 'regional_distance_km': 500.0, 'control_overlap_radius_fraction': 1.0, 'control_similarity_max_distance_km': 250.0, 'random_seed': 42}`.

## Negative-control warnings

Matched 25 candidate rows; 1 carry a proximity or similarity warning. A warning prompts endogenic modelling and is not automatic exclusion.

The comparator library contains 6 controls: Richat, Jabal Arkanu, Djebel Uweinat, Brandberg/Messum, Pilanesberg, Anton Dohrn Seamount. It remains a small, regionally uneven library rather than an exhaustive endogenic reference set.

## Candidate ring families

26 candidate nested arcuate families were identified under the configured center, radius-ratio, and angular-coverage rules.

## Preservation-state predictions

| state | count |
|---|---|
| buried_sedimentary | 12 |
| eroded_exposed | 8 |
| oceanic_volcanic_or_margin_confounded | 4 |
| fresh_or_shallow | 1 |

## Regional clusters

20 proximity families were assigned. Cluster membership does not establish candidate independence or common origin.

## Planetary geometric comparison

| source | body | rows |
|---|---|---|
| lunar_multiring_basins.csv | Moon | 11 |
| martian_basins.csv | Mars | 3 |
| terrestrial_screening | Earth | 26 |

Planetary rows are geometric comparators only. Ring-ratio or diameter overlap does not imply common origin, and the Martian table is an explicitly incomplete historical subset.

## Highest-priority field-review packets

- arc_0371
- arc_0674
- arc_0687
- arc_1088
- arc_1105
- arc_0795
- arc_0437
- arc_0697
- arc_0605
- arc_0899
- arc_0892
- arc_0444
- arc_1214
- arc_0404
- arc_0370
- arc_0896
- arc_1103
- arc_0547
- arc_0865
- arc_0232
- arc_0886
- arc_0852
- arc_0593
- arc_0576
- arc_0710

## Methodological cautions

- Morphology, gravity, magnetics, geology, and controls remain separate evidence channels.
- Magnetic support is optional and is flagged separately.
- Ring ratios are candidate-specific; no universal crater-to-ring multiplier is assumed.
- Missing inputs are recorded rather than silently converted into negative evidence.
- Diagnostic confirmation remains outside the scope of this pipeline.
