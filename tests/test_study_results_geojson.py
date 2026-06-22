import json
import unittest
from pathlib import Path


class StudyResultsGeoJSONTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(Path("arcuate_geometries.geojson").read_text())
        cls.result = json.loads(Path("study_results_geojson/arcuate_geometries_study_results.geojson").read_text())

    def test_row_preserving_and_geometry_preserving(self):
        self.assertEqual(len(self.result["features"]), len(self.source["features"]))
        for source, result in zip(self.source["features"], self.result["features"]):
            self.assertEqual(source["geometry"], result["geometry"])

    def test_ids_and_source_indices_are_unique(self):
        props = [f["properties"] for f in self.result["features"]]
        self.assertEqual(len({p["candidate_id"] for p in props}), 1318)
        self.assertEqual({p["source_index"] for p in props}, set(range(1318)))

    def test_manual_fields_are_empty(self):
        for f in self.result["features"]:
            p = f["properties"]
            self.assertFalse(p["manual_capture_complete"])
            self.assertIsNone(p["manual_interpreter"])
            self.assertIsNone(p["manual_geologic_unit"])
            self.assertIsNone(p["manual_shock_evidence"])

    def test_structure_membership_is_complete(self):
        for f in self.result["features"]:
            p = f["properties"]
            self.assertTrue(p["structure_id"].startswith("structure_"))
            self.assertGreaterEqual(p["structure_member_count"], 1)


if __name__ == "__main__":
    unittest.main()
