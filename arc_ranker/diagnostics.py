from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def save_elevation_analysis_figure(
    candidate_id: str,
    name: str,
    metrics: dict[str, Any],
    diagnostic: dict[str, Any],
    output_path: str | Path,
    *,
    webp_quality: int = 68,
) -> Path:
    """Render the terrain diagnostic figure used by the review atlas."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    extent = [diagnostic["lon"][0], diagnostic["lon"][-1], diagnostic["lat"][0], diagnostic["lat"][-1]]
    axes[0].imshow(diagnostic["elevation"], origin="lower", extent=extent, cmap="terrain")
    axes[0].set_title("GEBCO elevation")
    axes[1].imshow(diagnostic["residual"], origin="lower", extent=extent, cmap="RdBu_r")
    axes[1].contour(diagnostic["rho"], levels=[1.0], colors="black", linewidths=0.8, origin="lower", extent=extent)
    axes[1].set_title("Detrended terrain + candidate")
    axes[2].imshow(np.abs(diagnostic["radial_gradient"]), origin="lower", extent=extent, cmap="magma")
    axes[2].contour(diagnostic["rho"], levels=[0.85, 1.15], colors="cyan", linewidths=0.6, origin="lower", extent=extent)
    axes[2].set_title("Radial-gradient evidence")
    for ax in axes:
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
    score = metrics.get("followup_score") or metrics.get("score")
    score_text = f" | score={float(score):.3f}" if score is not None else ""
    display_name = "" if not name or str(name) == str(candidate_id) else f" {name}"
    fig.suptitle(f"{candidate_id}{display_name}{score_text}")
    fig.tight_layout()

    if output.suffix.lower() == ".webp":
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=150)
        buffer.seek(0)
        with Image.open(buffer) as image:
            image.convert("RGB").save(output, "WEBP", quality=webp_quality, method=6)
    else:
        fig.savefig(output, dpi=150)
    plt.close(fig)
    return output
