from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PipelineConfig:
    gravity_strong_threshold: float = 0.75
    gravity_weak_threshold: float = 0.25
    magnetic_support_threshold: float = 0.75
    magnetic_discordant_threshold: float = 0.25
    tid_high_risk_threshold: float = 0.25
    large_scale_diameter_km: float = 1000.0
    resolution_warning_diameter_km: float = 10.0
    ring_center_fraction: float = 0.25
    ring_min_adjacent_ratio: float = 1.2
    ring_min_angular_coverage: float = 0.35
    regional_distance_km: float = 500.0
    control_overlap_radius_fraction: float = 1.0
    control_similarity_max_distance_km: float = 250.0
    random_seed: int = 42

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> "PipelineConfig":
        if not path:
            return cls()
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Configuration file not found: {source}")
        values = yaml.safe_load(source.read_text()) or {}
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")
        return cls(**values)

    def metadata(self) -> dict[str, Any]:
        return asdict(self)
