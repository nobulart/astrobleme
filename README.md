# Astroblemes: An Arcuate Geometry Catalogue of Terrestrial Impact Structures

## Overview

This repository contains code and data supporting the manuscript "Astroblemes: A systematic search for terrestrial impact structures using arcuate geometries". The study identifies potential impact structures by detecting arcuate patterns in terrain morphology that could indicate ring structures from meteorite impacts.

## Key Findings (Plain Language Summary)

### What We Found
- We analyzed **1,318 arcuate geometries** (curved terrain features) across Africa and adjacent regions
- Compared them to the **Earth Impact Database** (confirmed impact sites) and global astrobleme catalogues
- Discovered statistical associations between arcuate patterns and confirmed impact structures

### Key Figures from the Study

**Figure 1: Size Distribution**
- Shows how impact structures of different sizes are distributed across our candidate list
- Uses survival curves to compare arcuate geometries with confirmed and proposed impact sites
- Reveals that larger structures (>500km) show distinctive patterns

**Figure 2: Geographic Distribution Map**
- Maps the locations of all three catalogues side-by-side
- Red dots: Other astrobleme entries (1,439 total)
- Blue circles: EID-matched confirmed impacts
- Open teal circles: Confirmed African structures (57 sites)

**Figure 3: Spatial Null Tests**
- Tests whether the association between arcs and impacts could be due to chance
- Compares observed spatial patterns against random rotations of the Earth's surface
- Result: Strong statistical significance (p < 0.001) - not by coincidence

**Table 1: Size Distribution Bins**
| Diameter Range | Count | Percentage |
|----------------|-------|------------|
| 0-100 km | 234 | 17.8% |
| 100-250 km | 389 | 29.6% |
| 250-500 km | 352 | 26.8% |
| 500-1000 km | 149 | 11.3% |
| >1000 km | 194 | 14.7% |

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

> Stone, C. (2026). Astroblemes: A systematic search for terrestrial impact structures using arcuate geometries. *Journal Name* (in press).

Code repository: https://github.com/nobulart/astrobleme

## License

This work is licensed under a Creative Commons Attribution 4.0 International License.
