import math

from astrobleme_pipeline.scoring import gravity_first_score, harmonic_mean_available


def test_harmonic_mean_with_missing_values():
    assert harmonic_mean_available([.5, None, float("nan")]) == .5
    assert math.isclose(harmonic_mean_available([.5, 1]), 2 / 3)
    assert harmonic_mean_available([0, 1]) == 0


def test_tid_penalty_reduces_score():
    clean = gravity_first_score(.8, .8, 0)
    risky = gravity_first_score(.8, .8, 1)
    assert clean is not None and risky is not None and clean > risky
    assert math.isclose(clean - risky, .1)

