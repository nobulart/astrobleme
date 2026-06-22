import unittest
from types import SimpleNamespace

from consolidate_structures_and_faults import compatible, consolidate, haversine_km
import pandas as pd


class TestConsolidation(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(haversine_km(0, 0, 1, 0), 111.195, places=2)

    def test_compatible_requires_scale_and_centre(self):
        a = SimpleNamespace(lon=0, lat=0, radius_km=100)
        self.assertTrue(compatible(a, SimpleNamespace(lon=.1, lat=0, radius_km=90), .25, .67, 1.5))
        self.assertFalse(compatible(a, SimpleNamespace(lon=.1, lat=0, radius_km=40), .25, .67, 1.5))
        self.assertFalse(compatible(a, SimpleNamespace(lon=1, lat=0, radius_km=90), .25, .67, 1.5))

    def test_complete_link_prevents_chain_merge(self):
        df = pd.DataFrame([
            dict(candidate_id="a", lon=0, lat=0, radius_km=100, followup_score=.9),
            dict(candidate_id="b", lon=.15, lat=0, radius_km=100, followup_score=.8),
            dict(candidate_id="c", lon=.30, lat=0, radius_km=100, followup_score=.7),
        ])
        clusters = consolidate(df, .25, .67, 1.5)
        self.assertEqual([len(x) for x in clusters], [2, 1])


if __name__ == "__main__": unittest.main()
