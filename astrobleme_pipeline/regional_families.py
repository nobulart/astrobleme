from __future__ import annotations

from collections import defaultdict

import pandas as pd

from .config import PipelineConfig
from .geometry import great_circle_distance_km


def cluster_by_geographic_proximity(frame: pd.DataFrame, config: PipelineConfig | None = None) -> pd.DataFrame:
    cfg = config or PipelineConfig(); records = frame.reset_index(drop=True); parent = list(range(len(records)))
    def find(x: int) -> int:
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a: int, b: int) -> None:
        a, b = find(a), find(b)
        if a != b: parent[b] = a
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            if great_circle_distance_km(records.iloc[i]["lon"], records.iloc[i]["lat"], records.iloc[j]["lon"], records.iloc[j]["lat"]) <= cfg.regional_distance_km:
                union(i, j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(records)): groups[find(i)].append(i)
    ordered = sorted(groups.values(), key=lambda group: min(group))
    mapping = {}
    for number, members in enumerate(ordered, 1):
        family = f"regional_family_{number:04d}"
        for member in members: mapping[member] = (family, len(members))
    return pd.DataFrame({"candidate_id": records["candidate_id"],
                         "regional_family_id": [mapping[i][0] for i in range(len(records))],
                         "regional_family_member_count": [mapping[i][1] for i in range(len(records))]})


def detect_overlapping_large_candidates(frame: pd.DataFrame) -> set[str]:
    flagged: set[str] = set(); records = frame.reset_index(drop=True)
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records.iloc[i], records.iloc[j]
            if pd.isna(a.get("radius_km")) or pd.isna(b.get("radius_km")): continue
            distance = great_circle_distance_km(a["lon"], a["lat"], b["lon"], b["lat"])
            if distance <= float(a["radius_km"]) + float(b["radius_km"]):
                flagged.update([str(a["candidate_id"]), str(b["candidate_id"])])
    return flagged


def assign_regional_context(frame: pd.DataFrame, config: PipelineConfig | None = None) -> pd.DataFrame:
    result = cluster_by_geographic_proximity(frame, config)
    overlap = detect_overlapping_large_candidates(frame)
    result["overlapping_large_candidate"] = result["candidate_id"].astype(str).isin(overlap)
    result["regional_context_flag"] = "geographic cluster; test shared tectonic/volcanic fabric and selection bias"
    result.loc[result["regional_family_member_count"] == 1, "regional_context_flag"] = "geographically isolated at configured scale"
    result["special_regional_case"] = None
    result.loc[result["candidate_id"].eq("arc_0370"), "special_regional_case"] = "North Atlantic / Anton Dohrn known volcanic control"
    result.loc[result["candidate_id"].isin(["arc_0752", "arc_0753"]), "special_regional_case"] = "arc_0752 / arc_0753 overlapping pair"
    result.loc[result["candidate_id"].eq("arc_0650"), "special_regional_case"] = "arc_0650 large-scale case"
    return result


def plot_regional_map(frame: pd.DataFrame, regional: pd.DataFrame, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pathlib import Path
    data = frame.merge(regional, on="candidate_id", how="left"); target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 5.5)); size = data["regional_family_member_count"].clip(1, 30) + 5
    ax.scatter(data["lon"], data["lat"], c=data["regional_family_member_count"], s=size, cmap="viridis", alpha=.55)
    ax.set(xlim=(-180, 180), ylim=(-90, 90), xlabel="Longitude", ylabel="Latitude", title="Regional proximity families")
    fig.tight_layout(); fig.savefig(target, dpi=180); plt.close(fig)

