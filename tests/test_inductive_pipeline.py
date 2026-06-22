import pandas as pd

from astrobleme_pipeline.config import PipelineConfig
from astrobleme_pipeline.gravity_first import rank_gravity_first
from astrobleme_pipeline.negative_controls import match_negative_controls, standardize_control_schema
from astrobleme_pipeline.preservation import predict_preservation_state


def test_robust_aliases_and_gravity_ranking():
    frame = pd.DataFrame([
        {"candidate_id": "a", "follow_up_score": .9, "bouguer_ring_score": .8, "free_air_ring_score": .6, "tid_artefact_risk": .1, "diameter_km": 20},
        {"candidate_id": "b", "follow_up_score": .7, "bouguer_ring_score": .4, "free_air_ring_score": .4, "tid_artefact_risk": .1, "diameter_km": 20},
    ])
    ranked, fields = rank_gravity_first(frame)
    assert fields["morphology"] == "follow_up_score"
    assert ranked.iloc[0].candidate_id == "a"
    assert ranked.iloc[0].gravity_first_score_interpretation.endswith("not impact probability")


def test_negative_control_distance_matching():
    candidates = pd.DataFrame([{"candidate_id": "a", "lon": 0, "lat": 0, "radius_km": 10}])
    controls = pd.DataFrame([{"negative_control_id": "v", "negative_control_class": "caldera", "lon": .1, "lat": 0, "radius_km": 5}])
    matches = match_negative_controls(candidates, controls, PipelineConfig())
    assert matches.iloc[0].nearest_negative_control_class == "caldera"
    assert 11 < matches.iloc[0].nearest_negative_control_distance_km < 12
    assert bool(matches.iloc[0].overlapping_negative_control)


def test_preservation_rules():
    buried = predict_preservation_state({"domain": "ocean", "diameter_km": 50, "crust1_sediment_thickness_km": 2})
    assert buried["preservation_state"] == "buried_sedimentary"
    assert buried["drilling_required"]
    large = predict_preservation_state({"domain": "land", "diameter_km": 1200})
    assert large["preservation_state"] == "large_scale_regime_uncertain"


def test_consolidated_control_schema_is_extensible():
    raw = pd.DataFrame([{"Name": "Test Ring", "Type": "Volcanic", "Description": "Alkaline ring complex"}])
    geometry = {"type": "Polygon", "coordinates": [[[0.1, 0], [0, 0.1], [-0.1, 0], [0, -0.1], [0.1, 0]]]}
    result = standardize_control_schema(raw, [geometry], "control")
    assert result.iloc[0].negative_control_id == "control_test_ring"
    assert result.iloc[0].negative_control_class == "ring_complex"
    assert result.iloc[0].diameter_km > 20


def test_distant_size_match_is_not_a_control_warning():
    candidates = pd.DataFrame([{"candidate_id": "a", "lon": 0, "lat": 0, "radius_km": 10, "diameter_km": 20}])
    controls = pd.DataFrame([{"negative_control_id": "v", "negative_control_class": "ring_complex", "lon": 50, "lat": 0, "radius_km": 10, "diameter_km": 20}])
    match = match_negative_controls(candidates, controls).iloc[0]
    assert match.control_similarity_score == 1
    assert not bool(match.control_similarity_nearby)
    assert not bool(match.control_similarity_warning)
