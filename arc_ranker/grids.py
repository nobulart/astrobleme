from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
from scipy.io import netcdf_file

from .geometry import Candidate, EARTH_RADIUS_KM


@dataclass
class GridWindow:
    values: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    source_rows: int
    source_cols: int
    stride_y: int = 1
    stride_x: int = 1


class RegularGrid:
    """Windowed reader for ascending, global latitude/longitude grids.

    NetCDF3 (including GMT ``.grd``) and HDF5/NetCDF4 files are supported.
    The reader keeps the source open and reads only candidate-centred windows.
    """

    def __init__(
        self,
        path: str | Path,
        variable: str,
        lon_name: str = "lon",
        lat_name: str = "lat",
        backend: str = "auto",
    ):
        self.path = Path(path)
        self._backend = backend
        self._handle = None
        if backend in {"auto", "hdf5"}:
            try:
                self._handle = h5py.File(self.path, "r")
                self._backend = "hdf5"
                self.values = self._handle[variable]
                self.lon = np.asarray(self._handle[lon_name][:], dtype=float)
                self.lat = np.asarray(self._handle[lat_name][:], dtype=float)
            except OSError:
                if backend == "hdf5":
                    raise
                self._handle = None
        if self._handle is None:
            self._handle = netcdf_file(self.path, "r", mmap=True)
            self._backend = "netcdf3"
            self.values = self._handle.variables[variable]
            self.lon = np.array(self._handle.variables[lon_name][:], dtype=float, copy=True)
            self.lat = np.array(self._handle.variables[lat_name][:], dtype=float, copy=True)
        if self.lon[0] > self.lon[-1] or self.lat[0] > self.lat[-1]:
            raise ValueError(f"Grid axes must be ascending: {self.path}")

    def close(self):
        if self._handle is not None:
            self.values = None
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def _axis_slice(axis: np.ndarray, low: float, high: float):
        start = max(0, int(np.searchsorted(axis, low, side="left")))
        stop = min(len(axis), int(np.searchsorted(axis, high, side="right")))
        return start, max(start + 1, stop)

    def _longitude_parts(self, low: float, high: float):
        if high - low >= 359.99:
            return [(float(self.lon[0]), float(self.lon[-1]), 0.0)]
        if self.lon[0] >= 0:
            centre = ((low + high) / 2.0) % 360.0
            half = (high - low) / 2.0
            low, high = centre - half, centre + half
            if low < 0.0:
                return [(low + 360.0, 360.0, -360.0), (0.0, high, 0.0)]
            if high > 360.0:
                return [(low, 360.0, 0.0), (0.0, high - 360.0, 360.0)]
            return [(low, high, 0.0)]
        if low < -180.0:
            return [(low + 360.0, 180.0, -360.0), (-180.0, high, 0.0)]
        if high > 180.0:
            return [(low, 180.0, 0.0), (-180.0, high - 360.0, 360.0)]
        return [(low, high, 0.0)]

    def _read(self, y_slice: slice, x_slice: slice) -> np.ndarray:
        return np.array(self.values[y_slice, x_slice], copy=True)

    def read_candidate(
        self,
        candidate: Candidate,
        roi_factor: float = 1.75,
        max_pixels: int = 512,
    ) -> GridWindow:
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
        part_indices = []
        source_cols = 0
        for low, high, offset in parts:
            x0, x1 = self._axis_slice(self.lon, low, high)
            source_cols += x1 - x0
            part_indices.append((x0, x1, offset))
        stride_x = max(1, math.ceil(source_cols / max_pixels))

        arrays, longitudes = [], []
        for x0, x1, offset in part_indices:
            arrays.append(self._read(slice(y0, y1, stride_y), slice(x0, x1, stride_x)))
            longitudes.append(self.lon[x0:x1:stride_x] + offset)
        values = np.concatenate(arrays, axis=1) if len(arrays) > 1 else arrays[0]
        lon_values = np.concatenate(longitudes) if len(longitudes) > 1 else longitudes[0]
        return GridWindow(values, lon_values, lat_values, source_rows, source_cols, stride_y, stride_x)


class NpyRegularGrid(RegularGrid):
    """Memory-mapped regular grid produced by a local conversion step."""

    def __init__(self, values_path: str | Path, lon_path: str | Path, lat_path: str | Path):
        self.path = Path(values_path)
        self._backend = "npy"
        self._handle = None
        self.values = np.load(values_path, mmap_mode="r")
        self.lon = np.load(lon_path)
        self.lat = np.load(lat_path)
        if self.values.shape != (len(self.lat), len(self.lon)):
            raise ValueError("Numpy grid shape does not match coordinate axes")

    def close(self):
        self.values = None
