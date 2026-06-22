from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


class Crust1Sampler:
    """Nearest-cell CRUST1.0 context; resolution is too coarse for ring scoring."""

    def __init__(self, directory: str | Path):
        directory = Path(directory)
        self._files = {}
        self._variables = {}
        for kind in ("rho", "vp", "vs"):
            path = next(directory.glob(f"CRUST1.0-{kind}*.nc"))
            handle = netcdf_file(path, "r", mmap=False)
            self._files[kind] = handle
            self._variables[kind] = handle.variables
        base = self._variables["rho"]
        self.lat = np.asarray(base["latitude"][:], dtype=float)
        self.lon = np.asarray(base["longitude"][:], dtype=float)

    def close(self):
        for handle in self._files.values():
            handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _index(self, lon: float, lat: float):
        wrapped = ((lon + 180.0) % 360.0) - 180.0
        return int(np.argmin(abs(self.lon - wrapped))), int(np.argmin(abs(self.lat - lat)))

    def sample(self, lon: float, lat: float) -> dict:
        ix, iy = self._index(lon, lat)
        rho = self._variables["rho"]
        vp = self._variables["vp"]
        sediment_thickness = sum(
            float(rho[f"{layer}_sediments_thickness"][iy, ix]) for layer in ("upper", "middle", "lower")
        )
        crust_thickness = sum(
            float(rho[f"{layer}_crust_thickness"][iy, ix]) for layer in ("upper", "middle", "lower")
        )
        return {
            "crust1_cell_lon": float(self.lon[ix]),
            "crust1_cell_lat": float(self.lat[iy]),
            "crust1_water_thickness_km": float(rho["water_thickness"][iy, ix]),
            "crust1_sediment_thickness_km": sediment_thickness,
            "crust1_crust_thickness_km": crust_thickness,
            "crust1_upper_crust_density": float(rho["upper_crust_rho"][iy, ix]),
            "crust1_lower_crust_density": float(rho["lower_crust_rho"][iy, ix]),
            "crust1_upper_crust_vp": float(vp["upper_crust_vp"][iy, ix]),
            "crust1_lower_crust_vp": float(vp["lower_crust_vp"][iy, ix]),
            "crust1_context_only": 1,
        }

