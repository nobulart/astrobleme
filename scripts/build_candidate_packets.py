#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pandas as pd
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from astrobleme_pipeline.field_packets import write_candidate_packets

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--input", required=True); parser.add_argument("--output", required=True); parser.add_argument("--top-n", type=int, default=25)
    args = parser.parse_args(); write_candidate_packets(pd.read_csv(args.input), args.output, args.top_n)

