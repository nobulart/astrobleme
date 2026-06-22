from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from .geometry import Candidate, EARTH_RADIUS_KM


@dataclass
class TerrainWindow:
    elevation: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    source_rows: int
    source_cols: int
    stride_y: int
    stride_x: int


class GEBCOGrid:
    """Windowed reader for the regular GEBCO latitude/longitude HDF5 grid."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.handle = h5py.File(self.path, "r")
        self.elevation = self.handle["elevation"]
        self.lat = self.handle["lat"][:]
        self.lon = self.handle["lon"][:]
        if self.lat[0] > self.lat[-1] or self.lon[0] > self.lon[-1]:
            raise ValueError("GEBCO coordinate axes must be ascending")

    def close(self):
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _axis_slice(self, axis: np.ndarray, low: float, high: float):
        start = max(0, int(np.searchsorted(axis, low, side="left")))
        stop = min(len(axis), int(np.searchsorted(axis, high, side="right")))
        return start, max(start + 1, stop)

    def _longitude_parts(self, low: float, high: float):
        if high - low >= 359.99:
            return [(-180.0, 180.0, 0.0)]
        if low < -180.0:
            return [(low + 360.0, 180.0, -360.0), (-180.0, high, 0.0)]
        if high > 180.0:
            return [(low, 180.0, 0.0), (-180.0, high - 360.0, 360.0)]
        return [(low, high, 0.0)]

    def read_candidate(
        self,
        candidate: Candidate,
        roi_factor: float = 1.75,
        max_pixels: int = 512,
    ) -> TerrainWindow:
        angular = min(math.pi - 1e-6, roi_factor * candidate.radius_km / EARTH_RADIUS_KM)
        lat_span = math.degrees(angular)
        low_lat = max(-90.0, candidate.lat - lat_span)
        high_lat = min(90.0, candidate.lat + lat_span)
        if abs(candidate.lat) + lat_span >= 89.9:
            lon_span = 180.0
        else:
            ratio = min(1.0, math.sin(angular) / max(1e-8, math.cos(math.radians(candidate.lat))))
            lon_span = min(180.0, math.degrees(math.asin(ratio)))

        y0, y1 = self._axis_slice(self.lat, low_lat, high_lat)
        source_rows = y1 - y0
        stride_y = max(1, math.ceil(source_rows / max_pixels))
        lat_values = self.lat[y0:y1:stride_y]

        parts = self._longitude_parts(candidate.lon - lon_span, candidate.lon + lon_span)
        source_cols = 0
        part_indices = []
        for low, high, offset in parts:
            x0, x1 = self._axis_slice(self.lon, low, high)
            source_cols += x1 - x0
            part_indices.append((x0, x1, offset))
        stride_x = max(1, math.ceil(source_cols / max_pixels))

        arrays = []
        lon_values = []
        for x0, x1, offset in part_indices:
            arrays.append(self.elevation[y0:y1:stride_y, x0:x1:stride_x].astype(np.float32))
            lon_values.append(self.lon[x0:x1:stride_x] + offset)
        data = np.concatenate(arrays, axis=1) if len(arrays) > 1 else arrays[0]
        lons = np.concatenate(lon_values) if len(lon_values) > 1 else lon_values[0]
        return TerrainWindow(
            elevation=data,
            lon=lons,
            lat=lat_values,
            source_rows=source_rows,
            source_cols=source_cols,
            stride_y=stride_y,
            stride_x=stride_x,
        )
