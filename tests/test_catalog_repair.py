import json
import math
import unittest
from pathlib import Path

from repair_astrobleme_catalog import haversine, normalize, parse_plain_numeric, parse_wiki_tables


ROOT = Path(__file__).resolve().parents[1]


class CatalogueRepairTests(unittest.TestCase):
    def test_confirmed_snapshot_uses_rendered_diameter_not_sort_key(self):
        rows = parse_wiki_tables(ROOT / "catalog_repair/sources/wikipedia_confirmed_2026-06-21.wiki")
        by_name = {normalize(row["name"]): row for row in rows}
        self.assertEqual(by_name[normalize("Gosses Bluff")]["diameter_km"], 32.0)
        self.assertEqual(by_name[normalize("Acraman")]["diameter_km"], 90.0)

    def test_repaired_catalogue_resolves_all_plain_numeric_conflicts(self):
        data = json.loads((ROOT / "catalog_repair/astroblemes_repaired.geojson").read_text())
        conflicts = []
        for feature in data["features"]:
            props = feature["properties"]
            raw = parse_plain_numeric(props.get("diameter_raw"))
            if raw is not None and not math.isclose(raw, float(props["diameter_km"]), rel_tol=1e-9):
                conflicts.append(props["catalogue_record_id"])
        self.assertEqual(conflicts, [])

    def test_analytical_catalogue_excludes_only_resolved_duplicates(self):
        repaired = json.loads((ROOT / "catalog_repair/astroblemes_repaired.geojson").read_text())
        analytical = json.loads((ROOT / "catalog_repair/astroblemes_analysis.geojson").read_text())
        excluded = [f for f in repaired["features"] if not f["properties"]["analytical_include"]]
        self.assertEqual(len(repaired["features"]), 253)
        self.assertEqual(len(analytical["features"]), 249)
        self.assertEqual(len(excluded), 4)
        self.assertTrue(all(f["properties"]["duplicate_of_record_id"] for f in excluded))

    def test_rebuilt_circle_matches_repaired_diameter(self):
        data = json.loads((ROOT / "catalog_repair/astroblemes_repaired.geojson").read_text())
        acraman = next(f for f in data["features"] if f["properties"]["name"] == "Acraman")
        props = acraman["properties"]
        lon, lat = acraman["geometry"]["coordinates"][0][0]
        radius = haversine(props["center_lat"], props["center_lon"], lat, lon)
        self.assertAlmostEqual(2 * radius, props["diameter_km"], places=3)


if __name__ == "__main__":
    unittest.main()
