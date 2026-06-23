import json
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import CandidateAnalysisArtifact, CandidateAnalysisJob, CandidateAnalysisRun, CandidateSubmission


def _unauthorized(message="Analysis worker token is missing or invalid."):
    return JsonResponse({"error": message}, status=403)


def _worker_authorized(request):
    configured = getattr(settings, "ANALYSIS_WORKER_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not configured or not supplied.startswith("Bearer "):
        return False
    return constant_time_compare(supplied.removeprefix("Bearer ").strip(), configured)


def worker_token_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not _worker_authorized(request):
            return _unauthorized()
        return view_func(request, *args, **kwargs)

    return wrapped


def _json_payload(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid JSON payload."}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({"error": "JSON payload must be an object."}, status=400)
    return data, None


def _candidate_payload(candidate):
    return {
        "id": str(candidate.id),
        "title": candidate.title,
        "description": candidate.description,
        "longitude": candidate.longitude,
        "latitude": candidate.latitude,
        "diameter_km": candidate.diameter_km,
        "geometry": candidate.geometry,
        "source_title": candidate.source_title,
        "source_uri": candidate.source_uri,
        "source_resolution": candidate.source_resolution,
        "observed_feature": candidate.observed_feature,
        "endogenic_alternative": candidate.endogenic_alternative,
        "independent_evidence": candidate.independent_evidence,
        "original_trace_available": candidate.original_trace_available,
        "intake_score": candidate.intake_score,
        "baseline_checks": candidate.baseline_checks,
        "status": candidate.status,
        "created_at": candidate.created_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }


def _job_payload(job, include_candidate=True):
    payload = {
        "id": str(job.id),
        "status": job.status,
        "requested_reason": job.requested_reason,
        "priority": job.priority,
        "attempt_count": job.attempt_count,
        "claimed_by": job.claimed_by,
        "claimed_at": job.claimed_at.isoformat() if job.claimed_at else None,
        "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
    if include_candidate:
        payload["candidate"] = _candidate_payload(job.candidate)
    return payload


def _lease_expiry():
    return timezone.now() + timedelta(seconds=getattr(settings, "ANALYSIS_JOB_LEASE_SECONDS", 1800))


def _claimable_filter(queryset):
    now = timezone.now()
    return queryset.filter(status=CandidateAnalysisJob.Status.QUEUED) | queryset.filter(
        status__in=[CandidateAnalysisJob.Status.CLAIMED, CandidateAnalysisJob.Status.RUNNING],
        lease_expires_at__lt=now,
    )


@require_GET
@worker_token_required
def list_jobs(request):
    try:
        limit = min(max(int(request.GET.get("limit", "20")), 1), 100)
    except ValueError:
        return JsonResponse({"error": "limit must be an integer."}, status=400)
    jobs = _claimable_filter(CandidateAnalysisJob.objects.select_related("candidate")).order_by("-priority", "created_at")[:limit]
    return JsonResponse({"jobs": [_job_payload(job) for job in jobs]})


@csrf_exempt
@require_POST
@worker_token_required
def claim_job(request, job_id):
    payload, error = _json_payload(request)
    if error:
        return error
    worker_id = str(payload.get("worker_id", "")).strip()[:120]
    if not worker_id:
        return JsonResponse({"error": "worker_id is required."}, status=400)
    with transaction.atomic():
        queryset = CandidateAnalysisJob.objects.select_for_update().select_related("candidate").filter(pk=job_id)
        job = _claimable_filter(queryset).first()
        if not job:
            return JsonResponse({"error": "Job is not claimable."}, status=409)
        job.status = CandidateAnalysisJob.Status.CLAIMED
        job.claimed_by = worker_id
        job.claimed_at = timezone.now()
        job.lease_expires_at = _lease_expiry()
        job.attempt_count += 1
        job.last_error = ""
        job.save(update_fields=["status", "claimed_by", "claimed_at", "lease_expires_at", "attempt_count", "last_error", "updated_at"])
    return JsonResponse({"job": _job_payload(job)})


@csrf_exempt
@require_POST
@worker_token_required
def heartbeat_job(request, job_id):
    payload, error = _json_payload(request)
    if error:
        return error
    worker_id = str(payload.get("worker_id", "")).strip()[:120]
    with transaction.atomic():
        job = CandidateAnalysisJob.objects.select_for_update().filter(pk=job_id).first()
        if not job:
            return JsonResponse({"error": "Job not found."}, status=404)
        if worker_id and job.claimed_by and worker_id != job.claimed_by:
            return JsonResponse({"error": "Job is claimed by a different worker."}, status=409)
        if job.status in {CandidateAnalysisJob.Status.SUCCEEDED, CandidateAnalysisJob.Status.FAILED, CandidateAnalysisJob.Status.CANCELLED}:
            return JsonResponse({"error": "Job is already terminal."}, status=409)
        job.status = CandidateAnalysisJob.Status.RUNNING
        job.lease_expires_at = _lease_expiry()
        job.save(update_fields=["status", "lease_expires_at", "updated_at"])
    return JsonResponse({"job": _job_payload(job, include_candidate=False)})


@csrf_exempt
@require_POST
@worker_token_required
def submit_result(request, job_id):
    payload, error = _json_payload(request)
    if error:
        return error
    status = str(payload.get("status", "")).strip()
    if status not in {value for value, _ in CandidateAnalysisRun.Status.choices}:
        return JsonResponse({"error": "status must be succeeded, failed, or source_unavailable."}, status=400)
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    source_fingerprints = payload.get("source_fingerprints") if isinstance(payload.get("source_fingerprints"), dict) else {}
    with transaction.atomic():
        job = CandidateAnalysisJob.objects.select_for_update().select_related("candidate").filter(pk=job_id).first()
        if not job:
            return JsonResponse({"error": "Job not found."}, status=404)
        if job.status == CandidateAnalysisJob.Status.CANCELLED:
            return JsonResponse({"error": "Job has been cancelled."}, status=409)
        candidate = job.candidate
        run = CandidateAnalysisRun.objects.create(
            candidate=candidate,
            job=job,
            status=status,
            score=payload.get("score"),
            score_percentile=payload.get("score_percentile"),
            review_tier=str(payload.get("review_tier", ""))[:80],
            method_version=str(payload.get("method_version", ""))[:120],
            worker_id=str(payload.get("worker_id", ""))[:120],
            worker_version=str(payload.get("worker_version", ""))[:120],
            metrics=metrics,
            diagnostics=diagnostics,
            source_fingerprints=source_fingerprints,
            runtime_seconds=payload.get("runtime_seconds"),
        )
        artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
        for artifact in artifacts[:25]:
            if not isinstance(artifact, dict) or not artifact.get("url_or_path"):
                continue
            CandidateAnalysisArtifact.objects.create(
                analysis_run=run,
                kind=str(artifact.get("kind", "diagnostic"))[:80],
                title=str(artifact.get("title", artifact.get("kind", "Diagnostic artifact")))[:200],
                mime_type=str(artifact.get("mime_type", ""))[:120],
                storage_backend=str(artifact.get("storage_backend", "external"))[:40],
                url_or_path=str(artifact["url_or_path"])[:1000],
                sha256=str(artifact.get("sha256", ""))[:64],
                size_bytes=artifact.get("size_bytes"),
            )
        if status == CandidateAnalysisRun.Status.SUCCEEDED:
            job.status = CandidateAnalysisJob.Status.SUCCEEDED
            candidate.followup_status = CandidateSubmission.FollowupStatus.SCORED
            candidate.followup_score = run.score
            candidate.followup_method_version = run.method_version
            candidate.followup_metrics = metrics | {
                "score_percentile": run.score_percentile,
                "review_tier": run.review_tier,
                "diagnostics": diagnostics,
                "source_fingerprints": source_fingerprints,
                "analysis_run_id": str(run.id),
            }
        elif status == CandidateAnalysisRun.Status.SOURCE_UNAVAILABLE:
            job.status = CandidateAnalysisJob.Status.FAILED
            job.last_error = str(payload.get("error", "Required scientific sources were unavailable."))[:2000]
            candidate.followup_status = CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE
            candidate.followup_metrics = metrics | {
                "reason": job.last_error,
                "analysis_run_id": str(run.id),
            }
        else:
            job.status = CandidateAnalysisJob.Status.FAILED
            job.last_error = str(payload.get("error", "Analysis worker failed."))[:2000]
            candidate.followup_status = CandidateSubmission.FollowupStatus.FAILED
            candidate.followup_metrics = metrics | {
                "reason": job.last_error,
                "analysis_run_id": str(run.id),
            }
        candidate.save(update_fields=["followup_score", "followup_status", "followup_metrics", "followup_method_version", "updated_at"])
        job.lease_expires_at = None
        job.save(update_fields=["status", "last_error", "lease_expires_at", "updated_at"])
    return JsonResponse({"job": _job_payload(job, include_candidate=False), "analysis_run_id": str(run.id)})
