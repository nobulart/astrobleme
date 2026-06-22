# Astroblemes: An Arcuate Geometry Catalogue of Terrestrial Impact Structures

## Overview

This repository contains code and data supporting the manuscript "Astroblemes: A systematic search for terrestrial impact structures using arcuate geometries". The study identifies potential impact structures by detecting arcuate patterns in terrain morphology that could indicate ring structures from meteorite impacts.

## Key findings (plain-language summary)

- The study analyses **1,318 visually identified arcuate geometries**, conservatively consolidated to **1,292 structure-level units**. These are screening geometries, not confirmed craters or shock boundaries.
- The repaired analytical astrobleme catalogue contains **249 unique records**; **82** carry a historical local Earth Impact Database match flag. The flag has not been reconciled against a live authoritative catalogue.
- EID-matched centres are closer to arc centres than longitude-rotation nulls, but not closer than proposed catalogue entries under confidence-label permutation. This supports spatial association under one null, not geological causation.
- A fitted diameter multiplier of **9.10** gives a non-significant permutation result (**p = 0.145**), so the current data do not establish a universal ring-to-crater scaling law.
- Circular gravity evidence is enriched over matched rotations, while magnetic evidence is not. These are non-diagnostic screening signals: the volcanic Anton Dohrn negative control remains highly ranked.
- The gravity-first extension retains **25 candidates** for review and identifies **26 nested arcuate families**. All require candidate-specific geological testing and accepted material evidence for confirmation.

## Reproducibility

### Prerequisites
```bash
pip install -r requirements.txt
```

Requirements:
- Python 3.9+
- scipy >=1.7.0
- numpy >=1.21.0
- matplotlib >=3.4.0

### Running the Analysis

```bash
# Main analysis script (produces all figures and statistics)
python analysis.py [--arcs arcuate_geometries.geojson] \
                   [--africa african_impact_structures.geojson] \
                   [--astroblemes astroblemes.geojson]

# Arc ranking pipeline
python run_arc_ranker.py --output ranking_output

# Geophysical null tests
python run_geophysical_nulls.py
```

### Output Files Generated
- `analysis_results.json` - Full statistical summary in JSON format
- `fig_*.pdf` and `fig_*.png` - Publication-ready figures
- `table_*.tex` - LaTeX tables for manuscript

## Code Structure

- `arc_ranker/` - Pipeline for ranking arcuate candidates (rank 1,318 features)
- `astrobleme_pipeline/` - Inductive analysis and scoring system
- `catalog_repair/` - Data cleaning and deduplication scripts
- `tests/` - Unit tests for all components
- `analysis.py` - Main statistical analysis script

## Data Availability

The full GeoJSON source datasets exceed GitHub's 100MB limit:
- arcuate_geometries.geojson (5.7MB) - All detected arc patterns
- african_impact_structures.geojson (2.1MB) - African catalogue
- astroblemes.geojson (2.1MB) - Global impact candidates

Processed outputs and smaller subsets are included in this repository.

## Citing This Work

If you use this code or data, please cite:

> Stone, C. (2026). Arcuate Geometries and Terrestrial Impact Structures: An Exploratory Geospatial and Null Model Analysis.

Available at: https://www.academia.edu/169033486

Code repository: https://github.com/nobulart/astrobleme

## License

This work is licensed under a Creative Commons Attribution 4.0 International License.

## Interactive review application

A Railway-ready Django atlas is included under `webapp/`. It provides interactive study layers, registered-user candidate intake, transparent baseline scoring, moderator-controlled promotion, and proxied access to aerial, NASA satellite, GEBCO elevation/TID, NOAA EMAG2 and WGM2012 gravity context. See [DEPLOYMENT.md](DEPLOYMENT.md) for local and Railway deployment instructions for `astro.nobulart.com`.
