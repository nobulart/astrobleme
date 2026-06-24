#!/usr/bin/env python3
"""Local automated candidate-analysis worker for astro.nobulart.com.

The Railway app intentionally stays lightweight. This worker is designed to run
on a local machine that has the manuscript repository and large scientific data
sources mounted, then communicate with the deployed app through the analysis API.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import requests


WORKER_VERSION = "0.1.0"


def configure_django(repo_root: Path) -> None:
    webapp = repo_root / "webapp"
    if str(webapp) not in sys.path:
        sys.path.insert(0, str(webapp))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "astroportal.settings")
    import django

    django.setup()


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def request_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    response = requests.request(method, url, headers=headers(token), json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def candidate_object(candidate_payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=candidate_payload["id"],
        title=candidate_payload["title"],
        longitude=float(candidate_payload["longitude"]),
        latitude=float(candidate_payload["latitude"]),
        diameter_km=float(candidate_payload["diameter_km"]),
        geometry=candidate_payload.get("geometry"),
        source_title=candidate_payload.get("source_title", ""),
        source_uri=candidate_payload.get("source_uri", ""),
        source_resolution=candidate_payload.get("source_resolution", ""),
        observed_feature=candidate_payload.get("observed_feature", ""),
        independent_evidence=candidate_payload.get("independent_evidence", []),
        original_trace_available=bool(candidate_payload.get("original_trace_available", False)),
        intake_score=float(candidate_payload.get("intake_score") or 0),
        baseline_checks=candidate_payload.get("baseline_checks") or {},
    )


def collect_artifacts(artifact_root: Path | None, artifact_base_url: str, candidate_id: str) -> list[dict[str, Any]]:
    if not artifact_root or not artifact_root.exists() or not artifact_base_url:
        return []
    matches = sorted(path for path in artifact_root.rglob("*") if path.is_file() and candidate_id in path.name)
    artifacts: list[dict[str, Any]] = []
    for path in matches[:25]:
        relative = path.relative_to(artifact_root).as_posix()
        artifacts.append({
            "kind": "diagnostic_png" if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else "diagnostic_file",
            "title": path.stem.replace("_", " ").replace("-", " "),
            "mime_type": "image/png" if path.suffix.lower() == ".png" else "",
            "storage_backend": "external",
            "url_or_path": f"{artifact_base_url.rstrip('/')}/{relative}",
            "size_bytes": path.stat().st_size,
        })
    return artifacts


def embedded_artifact(path: Path, kind: str, title: str) -> dict[str, Any]:
    content = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "kind": kind,
        "title": title,
        "mime_type": mime_type,
        "storage_backend": "database",
        "url_or_path": "",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def build_success_payload(result: dict[str, Any], job: dict[str, Any], args: argparse.Namespace, elapsed: float, generated_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = job["candidate"]
    metrics = result.get("metrics", {})
    return {
        "status": "succeeded",
        "score": result.get("score"),
        "method_version": result.get("method_version", ""),
        "worker_id": args.worker_id,
        "worker_version": WORKER_VERSION,
        "runtime_seconds": round(elapsed, 3),
        "metrics": metrics,
        "diagnostics": {
            "summary": "Computed by local analysis worker using the study follow-up scorer.",
            "candidate": {
                "id": candidate["id"],
                "title": candidate["title"],
                "longitude": candidate["longitude"],
                "latitude": candidate["latitude"],
                "diameter_km": candidate["diameter_km"],
            },
            "baseline_checks": candidate.get("baseline_checks") or {},
            "geometry": result.get("geometry"),
        },
        "source_fingerprints": {
            "gebco_grid_path": os.environ.get("GEBCO_GRID_PATH", ""),
            "geology_index_path": os.environ.get("GEOLOGY_INDEX_PATH", ""),
            "gebco_tid_grid_path": os.environ.get("GEBCO_TID_GRID_PATH", ""),
            "wgm2012_grid_dir": os.environ.get("WGM2012_GRID_DIR", ""),
            "emag2_cache_dir": os.environ.get("EMAG2_CACHE_DIR", ""),
        },
        "artifacts": generated_artifacts + collect_artifacts(args.artifact_root, args.artifact_base_url, candidate["id"]),
    }


def process_job(job: dict[str, Any], args: argparse.Namespace) -> None:
    from portal.followup import score_candidate

    job_id = job["id"]
    print(f"claiming {job_id} · {job['candidate']['title']}", flush=True)
    claimed = request_json(
        "POST",
        api_url(args.base_url, f"/api/analysis/jobs/{job_id}/claim"),
        args.token,
        {"worker_id": args.worker_id},
    )["job"]
    request_json(
        "POST",
        api_url(args.base_url, f"/api/analysis/jobs/{job_id}/heartbeat"),
        args.token,
        {"worker_id": args.worker_id},
    )
    started = time.monotonic()
    candidate = candidate_object(claimed["candidate"])
    try:
        args.artifact_output_dir.mkdir(parents=True, exist_ok=True)
        diagnostic_path = args.artifact_output_dir / f"{candidate.id}_elevation_diagnostic.webp"
        result = score_candidate(candidate, diagnostic_path=diagnostic_path, include_geophysics=True)
        generated_artifacts = []
        if diagnostic_path.exists():
            generated_artifacts.append(embedded_artifact(diagnostic_path, "elevation_diagnostic", "Elevation analysis diagnostic"))
        payload = build_success_payload(result, claimed, args, time.monotonic() - started, generated_artifacts)
    except FileNotFoundError as exc:
        payload = {
            "status": "source_unavailable",
            "worker_id": args.worker_id,
            "worker_version": WORKER_VERSION,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "error": str(exc),
            "metrics": {"reason": "The local worker could not open one or more required source datasets."},
        }
    except Exception as exc:  # pragma: no cover - deliberately defensive for long-running worker use.
        payload = {
            "status": "failed",
            "worker_id": args.worker_id,
            "worker_version": WORKER_VERSION,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
            "metrics": {"reason": "The local analysis worker raised an unexpected exception."},
        }
    request_json("POST", api_url(args.base_url, f"/api/analysis/jobs/{job_id}/result"), args.token, payload)
    print(f"submitted {job_id} · {payload['status']}", flush=True)


def run(args: argparse.Namespace) -> int:
    configure_django(args.repo_root)
    while True:
        listed = request_json("GET", api_url(args.base_url, f"/api/analysis/jobs?limit={args.limit}"), args.token)
        jobs = listed.get("jobs", [])
        if not jobs:
            print("no queued analysis jobs", flush=True)
            if args.once:
                return 0
            time.sleep(args.interval)
            continue
        for job in jobs:
            try:
                process_job(job, args)
            except requests.HTTPError as exc:
                print(f"api error for {job.get('id')}: {exc}", file=sys.stderr, flush=True)
            except Exception as exc:  # pragma: no cover - keeps daemon alive.
                print(f"worker error for {job.get('id')}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the local astrobleme candidate analysis worker.")
    p.add_argument("--base-url", default=os.environ.get("ASTROBLEME_API_BASE_URL", "https://astro.nobulart.com"), help="Deployed astrobleme app URL.")
    p.add_argument("--token", default=os.environ.get("ANALYSIS_WORKER_TOKEN", ""), help="Bearer token matching Railway ANALYSIS_WORKER_TOKEN.")
    p.add_argument("--worker-id", default=os.environ.get("ASTROBLEME_WORKER_ID", os.uname().nodename), help="Stable worker name recorded on jobs.")
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1], help="Repository root containing webapp/ and arc_ranker/.")
    p.add_argument("--artifact-output-dir", type=Path, default=Path(os.environ.get("ASTROBLEME_ARTIFACT_OUTPUT_DIR", Path(tempfile.gettempdir()) / "astrobleme-analysis-artifacts")), help="Local scratch directory for generated diagnostic figures.")
    p.add_argument("--artifact-root", type=Path, default=None, help="Optional local directory of pre-rendered diagnostic artifacts to expose by URL.")
    p.add_argument("--artifact-base-url", default=os.environ.get("ASTROBLEME_ARTIFACT_BASE_URL", ""), help="Public base URL corresponding to --artifact-root.")
    p.add_argument("--limit", type=int, default=5, help="Maximum jobs to fetch per poll.")
    p.add_argument("--interval", type=int, default=60, help="Seconds between polls when not using --once.")
    p.add_argument("--once", action="store_true", help="Process the current queue once and exit.")
    return p


def main() -> int:
    args = parser().parse_args()
    if not args.token:
        print("ANALYSIS_WORKER_TOKEN or --token is required.", file=sys.stderr)
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
