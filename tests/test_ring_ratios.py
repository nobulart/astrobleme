import pandas as pd

from astrobleme_pipeline.config import PipelineConfig
from astrobleme_pipeline.ring_ratios import cluster_ring_families, compute_radius_ratios


def test_radius_ratio_sequence():
    assert compute_radius_ratios([30, 10, 20]) == [2, 1.5]


def test_ring_family_clustering_synthetic():
    frame = pd.DataFrame([
        {"candidate_id": "a", "lon": 0, "lat": 0, "radius_km": 10, "diameter_km": 20, "geometry_angular_coverage": .8},
        {"candidate_id": "b", "lon": .005, "lat": 0, "radius_km": 15, "diameter_km": 30, "geometry_angular_coverage": .8},
        {"candidate_id": "c", "lon": 20, "lat": 20, "radius_km": 30, "diameter_km": 60, "geometry_angular_coverage": .8},
    ])
    families, membership = cluster_ring_families(frame, PipelineConfig(ring_min_adjacent_ratio=1.2))
    assert len(families) == 1
    assert set(membership.candidate_id) == {"a", "b"}


def test_transitive_chain_cannot_bypass_adjacent_ratio_threshold():
    frame = pd.DataFrame([
        {"candidate_id": "a", "lon": 0, "lat": 0, "radius_km": 10.0, "diameter_km": 20.0, "geometry_angular_coverage": .8},
        {"candidate_id": "b", "lon": 0, "lat": 0, "radius_km": 10.7, "diameter_km": 21.4, "geometry_angular_coverage": .8},
        {"candidate_id": "c", "lon": 0, "lat": 0, "radius_km": 13.9, "diameter_km": 27.8, "geometry_angular_coverage": .8},
    ])
    families, membership = cluster_ring_families(frame, PipelineConfig(ring_min_adjacent_ratio=1.2))
    assert len(families) == 1
    assert set(membership.candidate_id) == {"a", "c"}
    ratios = compute_radius_ratios([10.0, 13.9])
    assert min(ratios) >= 1.2
