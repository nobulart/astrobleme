from __future__ import annotations

import math
from collections.abc import Iterable


def bounded(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return min(1.0, max(0.0, number))


def mean_available(values: Iterable[object]) -> float | None:
    valid = [x for value in values if (x := bounded(value)) is not None]
    return sum(valid) / len(valid) if valid else None


def harmonic_mean_available(values: Iterable[object]) -> float | None:
    valid = [x for value in values if (x := bounded(value)) is not None]
    if not valid:
        return None
    if any(value == 0 for value in valid):
        return 0.0
    return len(valid) / sum(1.0 / value for value in valid)


def gravity_first_score(morphology: object, gravity: object, tid_risk: object) -> float | None:
    components = [(0.45, bounded(morphology)), (0.45, bounded(gravity))]
    risk = bounded(tid_risk)
    components.append((0.10, None if risk is None else 1.0 - risk))
    available = [(weight, value) for weight, value in components if value is not None]
    if not available:
        return None
    total_weight = sum(weight for weight, _ in available)
    return sum(weight * value for weight, value in available) / total_weight

