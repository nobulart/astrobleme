import math

from astrobleme_pipeline.geometry import geometry_radius_km, great_circle_distance_km, radius_diameter


def test_great_circle_distance_one_degree_equator():
    assert 111.0 < great_circle_distance_km(0, 0, 1, 0) < 111.5
    assert great_circle_distance_km(0, 0, 0, 0) == 0


def test_radius_diameter_handling():
    assert radius_diameter(radius_km=5) == (5, 10)
    assert radius_diameter(diameter_km=20) == (10, 20)
    radius, diameter = radius_diameter()
    assert math.isnan(radius) and math.isnan(diameter)


def test_polygon_radius_is_geodesic():
    geometry = {"type": "Polygon", "coordinates": [[[0.1, 0], [0, 0.1], [-0.1, 0], [0, -0.1], [0.1, 0]]]}
    assert 11 < geometry_radius_km(geometry, 0, 0) < 12
