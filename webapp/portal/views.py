import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection, transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .analysis_queue import enqueue_candidate_analysis
from .forms import CandidateForm, RegistrationForm
from .followup import circle_geometry, score_candidate
from .models import CandidateAnalysisArtifact, CandidateAnalysisJob, CandidateAnalysisRun, CandidateReview, CandidateSubmission, PortalConfiguration, UserMapPreference
from .scoring import evaluate_submission

LAYERS = {
    "study-candidates": ("study_results_geojson/arcuate_geometries_study_results.geojson", "Study candidates", "candidate"),
    "repaired-catalogue": ("catalog_repair/astroblemes_analysis.geojson", "Global catalogue", "catalogue"),
    "african-structures": ("african_impact_structures.geojson", "African structures", "africa"),
    "negative-controls": ("data/controls.geojson", "Endogenic controls", "control"),
    "active-faults": ("geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson", "GEM active faults", "fault"),
}

DEFAULT_LAYER_STYLES = {
    "study-candidates": {"lineStyle": "dotted", "lineWidth": 1.5},
    "repaired-catalogue": {"lineStyle": "dotted", "lineWidth": 1.5},
    "african-structures": {"lineStyle": "dotted", "lineWidth": 1.5},
    "negative-controls": {"lineStyle": "solid", "lineWidth": 1.5},
    "active-faults": {"lineStyle": "solid", "lineWidth": 1.5},
    "my-candidates": {"lineStyle": "solid", "lineWidth": 1.5},
    "other-candidates": {"lineStyle": "dashed", "lineWidth": 1.5},
    "community": {"lineStyle": "solid", "lineWidth": 1.5},
}

DEFAULT_MAP_PREFERENCES = {
    "center": [5, 15],
    "zoom": 2,
    "layers": ["study-candidates", "repaired-catalogue", "african-structures", "my-candidates"],
    "basemap": "aerial",
    "labels": True,
    "rasters": [],
    "rasterOpacity": 68,
    "satelliteDate": "",
    "candidateDraft": None,
    "scoreField": "followup_score",
    "palette": "turbo",
    "drawingMethod": "center-radius",
    "detailMode": "popup",
    "layerStyles": DEFAULT_LAYER_STYLES,
}
PREFERENCE_LAYERS = {*LAYERS, "my-candidates", "other-candidates", "community"}
PREFERENCE_BASEMAPS = {"street", "aerial", "satellite", "dark"}
PREFERENCE_RASTERS = {"gebco-elevation", "gebco-tid", "magnetic"}
PREFERENCE_SCORE_FIELDS = {"followup_score", "structure_followup_score", "gravity_consensus_percentile", "magnetic_ring_score_stratified_percentile", "data_quality", "intake_score", "diameter_km"}
PREFERENCE_PALETTES = {"turbo", "viridis", "plasma", "inferno", "magma", "cividis", "rdbu"}
PREFERENCE_DRAWING_METHODS = {"center-radius", "rim-to-rim", "point-diameter"}
PREFERENCE_DETAIL_MODES = {"popup", "sidebar"}
PREFERENCE_LAYER_LINE_STYLES = {"solid", "dashed", "dotted"}
STYLE_METRIC_FIELDS = (
    "structure_followup_score",
    "gravity_consensus_percentile",
    "magnetic_ring_score_stratified_percentile",
    "data_quality",
)
PUBLIC_CANDIDATE_STATUSES = [
    CandidateSubmission.Status.BASELINE_PASSED,
    CandidateSubmission.Status.UNDER_REVIEW,
    CandidateSubmission.Status.ACCEPTED,
]


def home(request):
    preferences = DEFAULT_MAP_PREFERENCES.copy()
    if request.user.is_authenticated:
        saved = UserMapPreference.objects.filter(user=request.user).values_list("settings", flat=True).first()
        if saved:
            preferences.update(saved)
    return render(request, "portal/home.html", {"layers": LAYERS, "map_preferences": preferences})


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("submit_candidate")
    return render(request, "registration/register.html", {"form": form})


@login_required
def submit_candidate(request):
    initial = {}
    if request.method == "GET":
        for field, minimum, maximum in (("latitude", -90, 90), ("longitude", -180, 180), ("diameter_km", 0.1, 10000)):
            try:
                value = float(request.GET.get(field, ""))
            except (TypeError, ValueError):
                continue
            if minimum <= value <= maximum:
                initial[field] = value
        for field, limit in (("title", 120), ("source_title", 240), ("source_uri", 500), ("source_resolution", 120)):
            value = request.GET.get(field, "").strip()
            if value:
                initial[field] = value[:limit]
    form = CandidateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        candidate.created_by = request.user
        passed = _evaluate_and_save(candidate, form)
        enqueue_candidate_analysis(candidate, CandidateAnalysisJob.Reason.NEW_SUBMISSION)
        preference = UserMapPreference.objects.filter(user=request.user).first()
        if preference and preference.settings.get("candidateDraft"):
            preference.settings = {**preference.settings, "candidateDraft": None}
            preference.save(update_fields=["settings", "updated_at"])
        if passed:
            messages.success(request, "Candidate passed the intake baseline and is now visible as an unreviewed community submission.")
        else:
            messages.warning(request, "Submission saved, but it needs revision before entering the public review queue.")
        return redirect("my_submissions")
    return render(request, "portal/submit.html", {"form": form, "review_config": PortalConfiguration.current()})


@login_required
def edit_candidate(request, candidate_id):
    candidate = get_object_or_404(CandidateSubmission, pk=candidate_id)
    owner_can_edit = candidate.created_by_id == request.user.id and candidate.is_editable_by_owner
    privileged_edit = _can_change_candidates(request.user)
    if not (owner_can_edit or privileged_edit):
        if candidate.created_by_id == request.user.id:
            messages.warning(request, "This candidate is locked because scientific review has started or a decision has been recorded.")
            return redirect("my_submissions")
        raise Http404
    if candidate.created_by_id == request.user.id and not candidate.is_editable_by_owner and not privileged_edit:
        messages.warning(request, "This candidate is locked because scientific review has started or a decision has been recorded.")
        return redirect("my_submissions")
    initial = {"geometry_text": json.dumps(candidate.geometry) if candidate.geometry else ""}
    form = CandidateForm(request.POST or None, instance=candidate, initial=initial)
    if request.method == "POST" and form.is_valid():
        previous_status = candidate.status
        previous_moderator = candidate.moderated_by
        previous_moderated_at = candidate.moderated_at
        candidate = form.save(commit=False)
        passed = _evaluate_and_save(candidate, form)
        if privileged_edit and previous_status not in {CandidateSubmission.Status.BASELINE_FAILED, CandidateSubmission.Status.BASELINE_PASSED}:
            candidate.status = previous_status
            candidate.moderated_by = previous_moderator
            candidate.moderated_at = previous_moderated_at
            candidate.save(update_fields=["status", "moderated_by", "moderated_at", "updated_at"])
        enqueue_candidate_analysis(candidate, CandidateAnalysisJob.Reason.USER_EDIT)
        if passed:
            messages.success(request, "Candidate updated, rescored, and retained in the unreviewed queue.")
        else:
            messages.warning(request, "Candidate updated and rescored, but it still needs revision before public review.")
        return redirect("my_submissions")
    return render(request, "portal/submit.html", {"form": form, "editing": True, "candidate": candidate, "review_config": PortalConfiguration.current()})


def _evaluate_and_save(candidate, form):
    candidate.geometry = form.cleaned_data["geometry_text"] or circle_geometry(candidate.longitude, candidate.latitude, candidate.diameter_km)
    score, passed, checks = evaluate_submission(form.cleaned_data | {"geometry": candidate.geometry})
    candidate.intake_score = score
    candidate.baseline_passed = passed
    candidate.baseline_checks = checks
    candidate.status = CandidateSubmission.Status.BASELINE_PASSED if passed else CandidateSubmission.Status.BASELINE_FAILED
    candidate.followup_score = None
    candidate.followup_method_version = ""
    try:
        result = score_candidate(candidate)
        candidate.followup_score = result["score"]
        candidate.followup_metrics = result["metrics"]
        candidate.followup_method_version = result["method_version"]
        candidate.followup_status = CandidateSubmission.FollowupStatus.SCORED
        candidate.geometry = result["geometry"]
    except FileNotFoundError:
        candidate.followup_status = CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE
        candidate.followup_metrics = {"reason": "Required numerical study sources are not mounted on this deployment."}
    except Exception:
        candidate.followup_status = CandidateSubmission.FollowupStatus.FAILED
        candidate.followup_metrics = {"reason": "The scientific scorer could not complete; a reviewer can retry it."}
    candidate.save()
    return passed


@login_required
def my_submissions(request):
    return render(request, "portal/my_submissions.html", {"submissions": request.user.candidate_submissions.all()})


@require_GET
def layer_geojson(request, slug):
    if slug not in LAYERS:
        raise Http404
    relative, _, _ = LAYERS[slug]
    path = (settings.PROJECT_ROOT / relative).resolve()
    if settings.PROJECT_ROOT.resolve() not in path.parents or not path.exists():
        raise Http404
    if slug == "study-candidates":
        return _study_candidate_collection(path, request.GET.get("download") == "1")
    response = FileResponse(path.open("rb"), content_type="application/geo+json")
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = f'attachment; filename="{slug}.geojson"'
    return response


@require_GET
def community_geojson(request):
    queryset = CandidateSubmission.objects.filter(status__in=PUBLIC_CANDIDATE_STATUSES).select_related("created_by")
    return _candidate_collection(queryset, request, request.GET.get("download") == "1")


@login_required
@require_GET
def my_candidates_geojson(request):
    return _candidate_collection(CandidateSubmission.objects.filter(created_by=request.user).select_related("created_by"), request, request.GET.get("download") == "1")


@login_required
@require_GET
def other_candidates_geojson(request):
    queryset = CandidateSubmission.objects.filter(status__in=PUBLIC_CANDIDATE_STATUSES).exclude(created_by=request.user).select_related("created_by")
    return _candidate_collection(queryset, request, request.GET.get("download") == "1")


@lru_cache(maxsize=1)
def _ranking_diagnostic_ids():
    static_root = settings.BASE_DIR / "static" / "portal" / "diagnostics" / "study"
    return frozenset(path.stem for path in static_root.glob("*.webp"))


def _study_candidate_collection(path, download=False):
    data = json.loads(path.read_text(encoding="utf-8"))
    diagnostic_ids = _ranking_diagnostic_ids()
    for feature in data.get("features", []):
        properties = feature.setdefault("properties", {})
        candidate_id = properties.get("candidate_id")
        if candidate_id in diagnostic_ids:
            properties["diagnostic_figure_url"] = static(f"portal/diagnostics/study/{candidate_id}.webp")
            properties["diagnostic_figure_title"] = "Elevation analysis diagnostic"
        properties["score_breakdown"] = _score_breakdown(properties)
    response = JsonResponse(data)
    response["Content-Type"] = "application/geo+json"
    if download:
        response["Content-Disposition"] = 'attachment; filename="study-candidates.geojson"'
    return response


def _candidate_collection(queryset, request, download=False):
    features = []
    queryset = queryset.prefetch_related("analysis_runs__artifacts")
    for candidate in queryset:
        geometry = candidate.geometry or {"type": "Point", "coordinates": [candidate.longitude, candidate.latitude]}
        features.append({
            "type": "Feature",
            "id": str(candidate.id),
            "geometry": geometry,
            "properties": _candidate_properties(candidate, request),
        })
    response = JsonResponse({"type": "FeatureCollection", "features": features})
    response["Content-Disposition"] = f'{"attachment" if download else "inline"}; filename="candidates.geojson"'
    return response


def _candidate_diagnostic_url(candidate):
    runs = sorted(candidate.analysis_runs.all(), key=lambda run: run.created_at, reverse=True)
    for run in runs:
        artifacts = sorted(run.artifacts.all(), key=lambda artifact: artifact.created_at, reverse=True)
        for artifact in artifacts:
            if artifact.kind in {"elevation_diagnostic", "diagnostic_png", "diagnostic_figure"}:
                return artifact.url_or_path
    return ""


def _candidate_properties(candidate, request):
    metrics = candidate.followup_metrics or {}
    artifact_url = metrics.get("diagnostic_figure_url") or _candidate_diagnostic_url(candidate)
    properties = {
        "candidate_uuid": str(candidate.id),
        "title": candidate.title,
        "longitude": candidate.longitude,
        "latitude": candidate.latitude,
        "diameter_km": candidate.diameter_km,
        "intake_score": candidate.intake_score,
        "followup_score": candidate.followup_score,
        "followup_status": candidate.followup_status,
        "score_percentile": metrics.get("score_percentile"),
        "review_tier": metrics.get("review_tier"),
        "score_breakdown": _score_breakdown(metrics),
        "diagnostic_figure_url": artifact_url,
        "diagnostic_figure_title": "Elevation analysis diagnostic" if artifact_url else "",
        "diagnostic_summary": (metrics.get("diagnostics") or {}).get("summary") if isinstance(metrics.get("diagnostics"), dict) else metrics.get("reason", ""),
        "review_status": candidate.status,
        "score_interpretation": "submission completeness and reviewability; not impact probability",
        "status": candidate.get_status_display(),
        "source_title": candidate.source_title,
        "observed_feature": candidate.observed_feature,
        "submitted_by": candidate.created_by.username,
        "created_at": candidate.created_at.isoformat(),
    }
    properties.update(_style_metric_properties(metrics))
    actions = _candidate_action_properties(candidate, request.user)
    if actions:
        properties["actions"] = actions
    return properties


def _candidate_action_properties(candidate, user):
    if not user.is_authenticated:
        return {}
    actions = {}
    if _can_edit_candidate(candidate, user):
        actions["edit_url"] = reverse("edit_candidate", args=[candidate.id])
    if _can_change_candidates(user):
        actions["status_url"] = reverse("candidate_status_api", args=[candidate.id])
        actions["status_choices"] = [{"value": value, "label": label} for value, label in CandidateSubmission.Status.choices]
    if _can_delete_candidates(user):
        actions["delete_url"] = reverse("candidate_delete_api", args=[candidate.id])
    return actions


def _can_change_candidates(user):
    return bool(user.is_authenticated and (user.is_staff or user.has_perm("portal.change_candidatesubmission")))


def _can_delete_candidates(user):
    return bool(user.is_authenticated and (user.is_staff or user.has_perm("portal.delete_candidatesubmission")))


def _can_edit_candidate(candidate, user):
    return (candidate.created_by_id == user.id and candidate.is_editable_by_owner) or _can_change_candidates(user)


def _style_metric_properties(metrics):
    return {
        field: metrics[field]
        for field in STYLE_METRIC_FIELDS
        if metrics.get(field) is not None and metrics.get(field) != ""
    }


def _score_breakdown(metrics):
    fields = [
        ("followup_score", "Follow-up score"),
        ("data_quality", "Data quality"),
        ("topography_score_unweighted", "Topography"),
        ("radial_alignment", "Radial alignment"),
        ("hough_percentile", "Annular peak"),
        ("angular_continuity", "Angular continuity"),
        ("radius_match", "Radius match"),
        ("centre_match", "Centre match"),
        ("relief_score", "Relief"),
        ("geology_independence", "Geology independence"),
        ("gravity_consensus_percentile", "Gravity percentile"),
        ("magnetic_ring_score_stratified_percentile", "Magnetic percentile"),
    ]
    breakdown = []
    for key, label in fields:
        value = metrics.get(key)
        if value is not None and value != "":
            breakdown.append({"key": key, "label": label, "value": value})
    return breakdown


@login_required
@require_POST
def candidate_status_api(request, candidate_id):
    if not _can_change_candidates(request.user):
        return JsonResponse({"error": "You do not have permission to change candidate status."}, status=403)
    payload = _request_payload(request)
    allowed = {value for value, _ in CandidateSubmission.Status.choices}
    target = str(payload.get("status", "")).strip()
    if target not in allowed:
        return JsonResponse({"error": "Choose a valid review status."}, status=400)
    note = str(payload.get("note", "")).strip()
    with transaction.atomic():
        candidate = get_object_or_404(CandidateSubmission.objects.select_for_update().select_related("created_by"), pk=candidate_id)
        previous = candidate.status
        candidate.status = target
        candidate.moderator_notes = note
        candidate.moderated_by = request.user
        candidate.moderated_at = timezone.now()
        candidate.save(update_fields=["status", "moderator_notes", "moderated_by", "moderated_at", "updated_at"])
        CandidateReview.objects.create(candidate=candidate, reviewer=request.user, from_status=previous, to_status=target, note=note)
    return JsonResponse({"properties": _candidate_properties(candidate, request)})


@login_required
@require_POST
def candidate_delete_api(request, candidate_id):
    if not _can_delete_candidates(request.user):
        return JsonResponse({"error": "You do not have permission to delete candidates."}, status=403)
    candidate = get_object_or_404(CandidateSubmission, pk=candidate_id)
    title = candidate.title
    candidate.delete()
    return JsonResponse({"deleted": True, "title": title, "id": str(candidate_id)})


def _request_payload(request):
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return request.POST


@require_GET
def analysis_artifact(request, artifact_id):
    artifact = get_object_or_404(CandidateAnalysisArtifact.objects.select_related("analysis_run__candidate"), pk=artifact_id)
    candidate = artifact.analysis_run.candidate
    public = candidate.status in PUBLIC_CANDIDATE_STATUSES
    owner = request.user.is_authenticated and candidate.created_by_id == request.user.id
    if not public and not owner and not request.user.is_staff:
        raise Http404
    if not artifact.content:
        if artifact.url_or_path.startswith(("http://", "https://", "/")):
            return redirect(artifact.url_or_path)
        raise Http404
    response = HttpResponse(bytes(artifact.content), content_type=artifact.mime_type or "application/octet-stream")
    response["Cache-Control"] = "public, max-age=86400"
    if artifact.size_bytes:
        response["Content-Length"] = str(artifact.size_bytes)
    return response


def help_page(request):
    return render(request, "portal/help.html", {"review_config": PortalConfiguration.current()})


@login_required
@require_GET
def analysis_status(request):
    candidates = CandidateSubmission.objects.filter(created_by=request.user)
    jobs = CandidateAnalysisJob.objects.filter(candidate__created_by=request.user)
    runs = CandidateAnalysisRun.objects.filter(candidate__created_by=request.user)
    followup_counts = Counter(candidates.values_list("followup_status", flat=True))
    job_counts = Counter(jobs.values_list("status", flat=True))
    run_counts = Counter(runs.values_list("status", flat=True))
    baseline_total = candidates.filter(baseline_passed=True).count()
    finished_total = sum(followup_counts[status] for status in [
        CandidateSubmission.FollowupStatus.SCORED,
        CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE,
        CandidateSubmission.FollowupStatus.FAILED,
    ])
    active_statuses = {
        CandidateAnalysisJob.Status.QUEUED,
        CandidateAnalysisJob.Status.CLAIMED,
        CandidateAnalysisJob.Status.RUNNING,
    }

    recent = []
    for candidate in candidates.order_by("-updated_at")[:6]:
        latest_job = candidate.analysis_jobs.order_by("-updated_at").first()
        latest_run = candidate.analysis_runs.order_by("-created_at").first()
        if latest_job and latest_job.status in active_statuses:
            state = latest_job.status
            state_label = latest_job.get_status_display()
        else:
            state = candidate.followup_status
            state_label = candidate.get_followup_status_display()
        metrics = candidate.followup_metrics or {}
        diagnostics = metrics.get("diagnostics") if isinstance(metrics.get("diagnostics"), dict) else {}
        recent.append({
            "id": str(candidate.id),
            "title": candidate.title,
            "state": state,
            "state_label": state_label,
            "candidate_status": candidate.get_status_display(),
            "job_status": latest_job.status if latest_job else None,
            "job_status_label": latest_job.get_status_display() if latest_job else "",
            "run_status": latest_run.status if latest_run else None,
            "run_status_label": latest_run.get_status_display() if latest_run else "",
            "score": candidate.followup_score,
            "score_percentile": metrics.get("score_percentile"),
            "data_quality": metrics.get("data_quality"),
            "summary": diagnostics.get("summary") or metrics.get("reason") or "",
            "updated_at": candidate.updated_at.isoformat(),
        })

    payload = {
        "totals": {
            "candidates": candidates.count(),
            "baseline_passed": baseline_total,
            "finished": finished_total,
            "progress_percent": round((finished_total / baseline_total) * 100) if baseline_total else 0,
        },
        "followup": {
            "scored": followup_counts[CandidateSubmission.FollowupStatus.SCORED],
            "not_scored": followup_counts[CandidateSubmission.FollowupStatus.NOT_SCORED],
            "source_unavailable": followup_counts[CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE],
            "failed": followup_counts[CandidateSubmission.FollowupStatus.FAILED],
        },
        "jobs": {
            "queued": job_counts[CandidateAnalysisJob.Status.QUEUED],
            "claimed": job_counts[CandidateAnalysisJob.Status.CLAIMED],
            "running": job_counts[CandidateAnalysisJob.Status.RUNNING],
            "succeeded": job_counts[CandidateAnalysisJob.Status.SUCCEEDED],
            "failed": job_counts[CandidateAnalysisJob.Status.FAILED],
            "cancelled": job_counts[CandidateAnalysisJob.Status.CANCELLED],
        },
        "runs": {
            "succeeded": run_counts[CandidateAnalysisRun.Status.SUCCEEDED],
            "source_unavailable": run_counts[CandidateAnalysisRun.Status.SOURCE_UNAVAILABLE],
            "failed": run_counts[CandidateAnalysisRun.Status.FAILED],
        },
        "recent": recent,
        "updated_at": timezone.now().isoformat(),
    }
    if request.user.is_staff:
        all_jobs = Counter(CandidateAnalysisJob.objects.values_list("status", flat=True))
        payload["staff_queue"] = {
            "queued": all_jobs[CandidateAnalysisJob.Status.QUEUED],
            "claimed": all_jobs[CandidateAnalysisJob.Status.CLAIMED],
            "running": all_jobs[CandidateAnalysisJob.Status.RUNNING],
            "failed": all_jobs[CandidateAnalysisJob.Status.FAILED],
        }
    return JsonResponse(payload)


@login_required
def globe(request):
    return render(request, "portal/globe.html", {"cesium_ion_token": settings.CESIUM_ION_TOKEN})


@user_passes_test(lambda user: user.is_staff)
def review_queue(request):
    base = CandidateSubmission.objects.exclude(status=CandidateSubmission.Status.BASELINE_FAILED)
    status_filter = request.GET.get("status", "").strip()
    followup_filter = request.GET.get("followup", "").strip()
    search = request.GET.get("q", "").strip()
    active_statuses = {
        CandidateAnalysisJob.Status.QUEUED,
        CandidateAnalysisJob.Status.CLAIMED,
        CandidateAnalysisJob.Status.RUNNING,
    }

    submissions = base
    if status_filter in {value for value, _ in CandidateSubmission.Status.choices}:
        submissions = submissions.filter(status=status_filter)
    else:
        status_filter = ""
    if followup_filter in {value for value, _ in CandidateSubmission.FollowupStatus.choices}:
        submissions = submissions.filter(followup_status=followup_filter)
    else:
        followup_filter = ""
    if search:
        submissions = submissions.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(source_title__icontains=search)
            | Q(observed_feature__icontains=search)
            | Q(created_by__username__icontains=search)
        )

    submissions = list(submissions.select_related("created_by", "moderated_by").prefetch_related(
        "reviews",
        Prefetch("analysis_jobs", queryset=CandidateAnalysisJob.objects.order_by("-updated_at")),
        Prefetch("analysis_runs", queryset=CandidateAnalysisRun.objects.order_by("-created_at")),
    ))
    for item in submissions:
        analysis_jobs = list(item.analysis_jobs.all())
        analysis_runs = list(item.analysis_runs.all())
        item.latest_job = analysis_jobs[0] if analysis_jobs else None
        item.latest_run = analysis_runs[0] if analysis_runs else None

    status_counts = Counter(base.values_list("status", flat=True))
    followup_counts = Counter(base.values_list("followup_status", flat=True))
    job_counts = Counter(CandidateAnalysisJob.objects.values_list("status", flat=True))
    summary = {
        "total": base.count(),
        "showing": len(submissions),
        "unreviewed": status_counts[CandidateSubmission.Status.BASELINE_PASSED],
        "under_review": status_counts[CandidateSubmission.Status.UNDER_REVIEW],
        "accepted": status_counts[CandidateSubmission.Status.ACCEPTED],
        "rejected": status_counts[CandidateSubmission.Status.REJECTED],
        "scored": followup_counts[CandidateSubmission.FollowupStatus.SCORED],
        "attention": followup_counts[CandidateSubmission.FollowupStatus.FAILED] + followup_counts[CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE],
        "active_jobs": sum(job_counts[status] for status in active_statuses),
        "failed_jobs": job_counts[CandidateAnalysisJob.Status.FAILED],
    }
    context = {
        "submissions": submissions,
        "summary": summary,
        "status_choices": [choice for choice in CandidateSubmission.Status.choices if choice[0] != CandidateSubmission.Status.BASELINE_FAILED],
        "followup_choices": CandidateSubmission.FollowupStatus.choices,
        "filters": {"status": status_filter, "followup": followup_filter, "q": search},
        "review_config": PortalConfiguration.current(),
    }
    return render(request, "portal/review_queue.html", context)


@user_passes_test(lambda user: user.is_staff)
@require_POST
def review_candidate(request, candidate_id):
    if request.POST.get("action") == "queue_analysis":
        with transaction.atomic():
            candidate = CandidateSubmission.objects.select_for_update().get(pk=candidate_id)
            enqueue_candidate_analysis(candidate, CandidateAnalysisJob.Reason.REVIEWER_RETRY, force=True)
        messages.success(request, f"Queued automated analysis for {candidate.title}.")
        return _review_queue_redirect(request)

    allowed = {value for value, _ in CandidateSubmission.Status.choices}
    target = request.POST.get("status")
    if target not in allowed:
        messages.error(request, "Choose a valid review status.")
        return _review_queue_redirect(request)
    with transaction.atomic():
        candidate = get_object_or_404(CandidateSubmission.objects.select_for_update(), pk=candidate_id)
        previous = candidate.status
        candidate.status = target
        candidate.moderator_notes = request.POST.get("note", "").strip()
        candidate.moderated_by = request.user
        candidate.moderated_at = timezone.now()
        candidate.save()
        CandidateReview.objects.create(candidate=candidate, reviewer=request.user, from_status=previous, to_status=target, note=candidate.moderator_notes)
    messages.success(request, f"Review status updated for {candidate.title}.")
    return _review_queue_redirect(request)


def _review_queue_redirect(request):
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("review_queue")


@login_required
@require_POST
def map_preferences(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid map preferences."}, status=400)
    if payload.get("reset") is True:
        UserMapPreference.objects.filter(user=request.user).delete()
        return JsonResponse({"settings": DEFAULT_MAP_PREFERENCES})
    try:
        settings = _clean_map_preferences(payload)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return JsonResponse({"error": "Invalid map preferences."}, status=400)
    UserMapPreference.objects.update_or_create(user=request.user, defaults={"settings": settings})
    return JsonResponse({"settings": settings})


def _clean_map_preferences(payload):
    center = payload.get("center", DEFAULT_MAP_PREFERENCES["center"])
    latitude, longitude = float(center[0]), float(center[1])
    if not -90 <= latitude <= 90:
        raise ValueError
    longitude = ((longitude + 180) % 360) - 180
    zoom = max(1, min(18, int(payload.get("zoom", 2))))
    opacity = max(10, min(100, int(payload.get("rasterOpacity", 68))))
    layers = [item for item in payload.get("layers", []) if item in PREFERENCE_LAYERS]
    rasters = [item for item in payload.get("rasters", []) if item in PREFERENCE_RASTERS]
    basemap = payload.get("basemap", "street")
    if basemap not in PREFERENCE_BASEMAPS:
        basemap = DEFAULT_MAP_PREFERENCES["basemap"]
    labels = bool(payload.get("labels", DEFAULT_MAP_PREFERENCES["labels"]))
    satellite_date = str(payload.get("satelliteDate", ""))[:10]
    score_field = payload.get("scoreField", DEFAULT_MAP_PREFERENCES["scoreField"])
    palette = payload.get("palette", DEFAULT_MAP_PREFERENCES["palette"])
    drawing_method = payload.get("drawingMethod", DEFAULT_MAP_PREFERENCES["drawingMethod"])
    detail_mode = payload.get("detailMode", DEFAULT_MAP_PREFERENCES["detailMode"])
    if (
        score_field not in PREFERENCE_SCORE_FIELDS
        or palette not in PREFERENCE_PALETTES
        or drawing_method not in PREFERENCE_DRAWING_METHODS
        or detail_mode not in PREFERENCE_DETAIL_MODES
    ):
        raise ValueError
    layer_styles = {}
    for slug, style in (payload.get("layerStyles") or {}).items():
        if slug not in PREFERENCE_LAYERS or not isinstance(style, dict):
            continue
        line_style = style.get("lineStyle", "solid")
        if line_style not in PREFERENCE_LAYER_LINE_STYLES:
            line_style = "solid"
        line_width = max(1, min(8, float(style.get("lineWidth", 2))))
        layer_styles[slug] = {"lineStyle": line_style, "lineWidth": round(line_width, 1)}
    draft = payload.get("candidateDraft")
    clean_draft = None
    if draft:
        draft_latitude = float(draft["latitude"])
        draft_longitude = float(draft["longitude"])
        draft_diameter = float(draft["diameterKm"])
        if not (-90 <= draft_latitude <= 90 and -180 <= draft_longitude <= 180 and 0.1 <= draft_diameter <= 10000):
            raise ValueError
        clean_draft = {
            "latitude": round(draft_latitude, 6),
            "longitude": round(draft_longitude, 6),
            "diameterKm": round(draft_diameter, 2),
        }
    return {
        "center": [round(latitude, 6), round(longitude, 6)],
        "zoom": zoom,
        "layers": list(dict.fromkeys(layers)),
        "basemap": basemap,
        "labels": labels,
        "rasters": list(dict.fromkeys(rasters)),
        "rasterOpacity": opacity,
        "satelliteDate": satellite_date,
        "candidateDraft": clean_draft,
        "scoreField": score_field,
        "palette": palette,
        "drawingMethod": drawing_method,
        "detailMode": detail_mode,
        "layerStyles": layer_styles,
    }


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
