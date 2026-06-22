#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd


ROWS = 5400
COLS = 10800


def run(args):
    source = Path(args.source)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    target = np.lib.format.open_memmap(output / "emag2_anomaly.npy", mode="w+", dtype="float32", shape=(ROWS, COLS))
    offset = 0
    started = time.time()
    for chunk_number, chunk in enumerate(
        pd.read_csv(source, header=None, usecols=[5], dtype={5: "float32"}, chunksize=args.chunk_rows), 1
    ):
        values = chunk.iloc[:, 0].to_numpy(dtype=np.float32, copy=False)
        end = offset + len(values)
        if end > ROWS * COLS:
            raise ValueError("EMAG2 CSV contains more rows than the documented 10800 x 5400 grid")
        target.reshape(-1)[offset:end] = values
        offset = end
        print(f"Converted {offset:,}/{ROWS * COLS:,} rows in {time.time() - started:.1f}s", flush=True)
    target.flush()
    if offset != ROWS * COLS:
        raise ValueError(f"Expected {ROWS * COLS:,} rows, found {offset:,}")
    np.save(output / "emag2_lon.npy", np.arange(COLS, dtype=float) / 30.0 + 1.0 / 60.0)
    np.save(output / "emag2_lat.npy", np.arange(ROWS, dtype=float) / 30.0 - 90.0 + 1.0 / 60.0)
    metadata = {
        "source": str(source),
        "source_bytes": source.stat().st_size,
        "shape": [ROWS, COLS],
        "value_column_zero_based": 5,
        "interpretation": "EMAG2 v3 column 6: magnetic anomaly upward-continued to a continuous 4 km altitude (nT), as documented in EMAG2_readme.txt. Sea-level anomaly, source code and error columns remain outside this cache.",
        "elapsed_seconds": time.time() - started,
    }
    (output / "emag2_cache.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def parser():
    p = argparse.ArgumentParser(description="Convert the sequential EMAG2 CSV anomaly column into a random-access Numpy grid.")
    p.add_argument("--source", default="/Users/craig/ECDO/GIS/EMAG2_V3_20170530.csv")
    p.add_argument("--output", default="geophysical_cache/emag2")
    p.add_argument("--chunk-rows", type=int, default=1_000_000)
    return p


if __name__ == "__main__":
    run(parser().parse_args())
