#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from astrobleme_pipeline.io import write_csv
from astrobleme_pipeline.negative_controls import load_negative_controls

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--input", default="negative_controls")
    parser.add_argument("--consolidated", default="data/controls.geojson")
    parser.add_argument("--output", default="outputs/tables/negative_control_library.csv")
    args = parser.parse_args(); frame, _ = load_negative_controls(args.input, [args.consolidated]); write_csv(frame, args.output)
