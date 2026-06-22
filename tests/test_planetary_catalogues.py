import importlib.util
from pathlib import Path


def _module():
    path = Path("scripts/build_planetary_catalogues.py")
    spec = importlib.util.spec_from_file_location("build_planetary_catalogues", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_grail_transcription_shape_and_orientale_values():
    frame = _module().build_lunar_multiring()
    assert len(frame) == 11
    orientale = frame.set_index("name").loc["Orientale"]
    assert orientale["main_ring_diameter_km"] == 937
    assert orientale["number_of_nested_rings"] == 4
    assert orientale["certainty"] == "certain"


def test_mars_subset_is_explicitly_incomplete():
    frame = _module().build_martian_basins()
    assert set(frame["object"]) == {"Argyre", "Isidis", "Hellas"}
    assert frame["selection_scope"].str.contains("not a complete").all()


def test_ring_ratios_are_adjacent_sorted_diameters():
    assert _module().ratios([400, 100, 200]) == [2.0, 2.0]
