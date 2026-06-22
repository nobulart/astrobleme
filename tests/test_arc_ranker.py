import unittest

import numpy as np

from arc_ranker.filters import score_terrain
from arc_ranker.evidence import score_scalar_ring, score_tid
from arc_ranker.gebco import TerrainWindow
from arc_ranker.grids import GridWindow
from arc_ranker.geometry import Candidate
from shapely.geometry import MultiLineString


class CircularFilterTests(unittest.TestCase):
    def candidate(self):
        theta = np.linspace(0, 2 * np.pi, 97)
        line = [(np.cos(t), np.sin(t)) for t in theta]
        return Candidate(0, "synthetic", "synthetic", 0.0, 0.0, 100.0, 200.0, 0.0, 1.0, MultiLineString([line]))

    def window(self, ring=True):
        axis = np.linspace(-1.75, 1.75, 401)
        lon, lat = np.meshgrid(axis, axis)
        # At the equator one degree is approximately 111.2 km.
        rho = np.hypot(lon * 111.2, lat * 111.2) / 100.0
        elevation = np.zeros_like(rho)
        if ring:
            elevation += 300 * np.exp(-0.5 * ((rho - 1.0) / 0.055) ** 2)
        elevation += 20 * lon + 10 * lat
        return TerrainWindow(elevation.astype(np.float32), axis, axis, 401, 401, 1, 1)

    def test_ring_scores_above_plane(self):
        ring, _ = score_terrain(self.candidate(), self.window(True))
        plane, _ = score_terrain(self.candidate(), self.window(False))
        self.assertGreater(ring["topography_score_unweighted"], plane["topography_score_unweighted"] + 0.15)
        self.assertLess(abs(ring["best_radius_ratio"] - 1.0), 0.12)
        self.assertGreater(ring["angular_continuity"], 0.8)

    def test_scalar_ring_evidence_exceeds_plane(self):
        terrain = self.window(True)
        ring_window = GridWindow(terrain.elevation, terrain.lon, terrain.lat, 401, 401)
        plane = self.window(False)
        plane_window = GridWindow(plane.elevation, plane.lon, plane.lat, 401, 401)
        ring = score_scalar_ring(self.candidate(), ring_window, "test")
        flat = score_scalar_ring(self.candidate(), plane_window, "test")
        self.assertGreater(ring["test_ring_score"], flat["test_ring_score"] + 0.1)
        self.assertGreater(ring["test_angular_continuity"], 0.8)

    def test_tid_transition_alignment_is_detected(self):
        axis = np.linspace(-1.75, 1.75, 401)
        lon, lat = np.meshgrid(axis, axis)
        rho = np.hypot(lon * 111.2, lat * 111.2) / 100.0
        tid = np.full(rho.shape, 11, dtype=np.int8)
        tid[rho >= 1.0] = 40
        metrics = score_tid(self.candidate(), GridWindow(tid, axis, axis, 401, 401))
        self.assertGreater(metrics["tid_transition_enrichment"], 2.0)
        self.assertGreater(metrics["tid_artifact_risk"], 0.4)


if __name__ == "__main__":
    unittest.main()
