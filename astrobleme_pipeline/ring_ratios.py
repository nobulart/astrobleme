from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
import pandas as pd

from .config import PipelineConfig
from .geometry import great_circle_distance_km, radius_diameter


def compute_center_offsets(a: pd.Series, b: pd.Series) -> float:
    return great_circle_distance_km(a["lon"], a["lat"], b["lon"], b["lat"])


def compute_radius_ratios(radii: list[float]) -> list[float]:
    ordered = sorted(float(value) for value in radii if pd.notna(value) and value > 0)
    return [ordered[i + 1] / ordered[i] for i in range(len(ordered) - 1)]


def find_near_concentric_candidates(frame: pd.DataFrame, config: PipelineConfig | None = None) -> list[tuple[int, int, float]]:
    cfg = config or PipelineConfig()
    pairs = []
    records = frame.reset_index(drop=True)
    for i in range(len(records)):
        a = records.iloc[i]
        ar, _ = radius_diameter(a.get("radius_km"), a.get("diameter_km"))
        for j in range(i + 1, len(records)):
            b = records.iloc[j]
            br, _ = radius_diameter(b.get("radius_km"), b.get("diameter_km"))
            if not np.isfinite(ar) or not np.isfinite(br) or min(ar, br) <= 0:
                continue
            ratio = max(ar, br) / min(ar, br)
            if ratio < cfg.ring_min_adjacent_ratio:
                continue
            coverage = min(float(a.get("geometry_angular_coverage", 1) or 0), float(b.get("geometry_angular_coverage", 1) or 0))
            if coverage < cfg.ring_min_angular_coverage:
                continue
            distance = compute_center_offsets(a, b)
            if distance <= cfg.ring_center_fraction * min(ar, br):
                pairs.append((i, j, distance))
    return pairs


def cluster_ring_families(frame: pd.DataFrame, config: PipelineConfig | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = config or PipelineConfig()
    records = frame.reset_index(drop=True).copy()
    parent = list(range(len(records)))
    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
    pairs = find_near_concentric_candidates(records, cfg)
    offsets: dict[tuple[int, int], float] = {}
    for i, j, distance in pairs:
        union(i, j); offsets[(i, j)] = distance
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(records)): groups[find(i)].append(i)
    # Connected components can contain an invalid transitive chain (A compatible
    # with C, B compatible with C, but A/B too similar in radius). Refine each
    # component into deterministic complete-link groups whose sorted adjacent
    # radii all satisfy the configured minimum ratio.
    refined_groups: list[list[int]] = []
    for component in sorted(groups.values(), key=lambda value: min(value)):
        ordered = sorted(component, key=lambda index: radius_diameter(records.iloc[index].get("radius_km"), records.iloc[index].get("diameter_km"))[0])
        component_groups: list[list[int]] = []
        for member in ordered:
            placed = False
            for group in component_groups:
                if _valid_complete_family(records, [*group, member], cfg):
                    group.append(member); placed = True; break
            if not placed:
                component_groups.append([member])
        refined_groups.extend(group for group in component_groups if len(group) >= 2)

    families = []
    memberships = []
    family_no = 0
    for members in sorted(refined_groups, key=lambda value: min(value)):
        family_no += 1; family_id = f"ring_family_{family_no:04d}"
        subset = records.iloc[members]
        radii = [radius_diameter(row.get("radius_km"), row.get("diameter_km"))[0] for _, row in subset.iterrows()]
        ratios = compute_radius_ratios(radii)
        member_offsets = [value for (i, j), value in offsets.items() if i in members and j in members]
        nested = min(1.0, 0.5 * min(1.0, len(members) / 3) + 0.5 * (1.0 - min(1.0, np.median(member_offsets) / max(min(radii), 1))))
        families.append({"family_id": family_id, "member_count": len(members),
                         "member_candidate_ids": ";".join(subset["candidate_id"].astype(str)),
                         "center_offset_km_median": float(np.median(member_offsets)) if member_offsets else 0.0,
                         "radius_ratio_sequence": json.dumps([round(x, 4) for x in ratios]),
                         "diameter_range_km": f"{2*min(radii):.3f}-{2*max(radii):.3f}",
                         "nested_geometry_score": nested, "possible_multi_ring_family": len(members) >= 2,
                         "interpretation": "candidate multi-ring geometry; requires geological discrimination"})
        memberships.extend({"candidate_id": records.iloc[i]["candidate_id"], "ring_family_id": family_id} for i in members)
    return pd.DataFrame(families), pd.DataFrame(memberships, columns=["candidate_id", "ring_family_id"])


def _valid_complete_family(records: pd.DataFrame, members: list[int], config: PipelineConfig) -> bool:
    if len(members) < 2:
        return True
    radii = []
    for index in members:
        row = records.iloc[index]
        radius, _ = radius_diameter(row.get("radius_km"), row.get("diameter_km"))
        if not np.isfinite(radius) or radius <= 0 or float(row.get("geometry_angular_coverage", 1) or 0) < config.ring_min_angular_coverage:
            return False
        radii.append(radius)
    if any(ratio < config.ring_min_adjacent_ratio for ratio in compute_radius_ratios(radii)):
        return False
    for pos, left in enumerate(members):
        for right in members[pos + 1:]:
            a, b = records.iloc[left], records.iloc[right]
            ar, _ = radius_diameter(a.get("radius_km"), a.get("diameter_km"))
            br, _ = radius_diameter(b.get("radius_km"), b.get("diameter_km"))
            if compute_center_offsets(a, b) > config.ring_center_fraction * min(ar, br):
                return False
    return True


def plot_ring_family_examples(frame: pd.DataFrame, membership: pd.DataFrame, path: str, max_families: int = 4) -> None:
    if membership.empty: return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    from pathlib import Path
    data = frame.merge(membership, on="candidate_id", how="inner")
    selected = list(data["ring_family_id"].drop_duplicates().head(max_families))
    fig, axes = plt.subplots(1, len(selected), figsize=(4 * len(selected), 4), squeeze=False)
    for ax, family_id in zip(axes[0], selected):
        subset = data[data["ring_family_id"].eq(family_id)]
        lon0, lat0 = subset["lon"].mean(), subset["lat"].mean()
        max_radius = max(float(value) for value in subset["radius_km"])
        for _, row in subset.iterrows():
            radius_deg = float(row["radius_km"]) / 111.2
            ax.add_patch(Circle((float(row["lon"]), float(row["lat"])), radius_deg, fill=False, lw=1.5, alpha=.75))
            ax.plot(row["lon"], row["lat"], ".", ms=3)
        span = max_radius / 111.2 * 1.3
        ax.set(xlim=(lon0-span, lon0+span), ylim=(lat0-span, lat0+span), aspect="equal", title=family_id, xlabel="Longitude", ylabel="Latitude")
    fig.suptitle("Candidate nested arcuate families (schematic radii)"); fig.tight_layout(); target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); fig.savefig(target, dpi=180); plt.close(fig)
