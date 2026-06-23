import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import connection, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import CandidateForm, RegistrationForm
from .followup import circle_geometry, score_candidate
from .models import CandidateReview, CandidateSubmission, UserMapPreference
from .scoring import evaluate_submission

LAYERS = {
    "study-candidates": ("study_results_geojson/arcuate_geometries_study_results.geojson", "Study candidates", "candidate"),
    "repaired-catalogue": ("catalog_repair/astroblemes_analysis.geojson", "Repaired global catalogue", "catalogue"),
    "african-structures": ("african_impact_structures.geojson", "African structures", "africa"),
    "negative-controls": ("data/controls.geojson", "Endogenic controls", "control"),
    "active-faults": ("geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson", "GEM active faults", "fault"),
}

DEFAULT_MAP_PREFERENCES = {
    "center": [5, 15],
    "zoom": 2,
    "layers": ["study-candidates", "my-candidates"],
    "basemap": "aerial",
    "labels": True,
    "rasters": [],
    "rasterOpacity": 68,
    "satelliteDate": "",
    "candidateDraft": None,
    "scoreField": "followup_score",
    "palette": "turbo",
    "drawingMethod": "center-radius",
}
PREFERENCE_LAYERS = {*LAYERS, "my-candidates", "other-candidates", "community"}
PREFERENCE_BASEMAPS = {"street", "aerial", "satellite", "dark"}
PREFERENCE_RASTERS = {"gebco-elevation", "gebco-tid", "magnetic"}
PREFERENCE_SCORE_FIELDS = {"followup_score", "structure_followup_score", "gravity_consensus_percentile", "magnetic_ring_score_stratified_percentile", "data_quality", "intake_score", "diameter_km"}
PREFERENCE_PALETTES = {"turbo", "viridis", "plasma", "inferno", "magma", "cividis", "rdbu"}
PREFERENCE_DRAWING_METHODS = {"center-radius", "rim-to-rim", "point-diameter"}
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
        preference = UserMapPreference.objects.filter(user=request.user).first()
        if preference and preference.settings.get("candidateDraft"):
            preference.settings = {**preference.settings, "candidateDraft": None}
            preference.save(update_fields=["settings", "updated_at"])
        if passed:
            messages.success(request, "Candidate passed the intake baseline and is now visible as an unreviewed community submission.")
        else:
            messages.warning(request, "Submission saved, but it needs revision before entering the public review queue.")
        return redirect("my_submissions")
    return render(request, "portal/submit.html", {"form": form})


@login_required
def edit_candidate(request, candidate_id):
    candidate = get_object_or_404(CandidateSubmission, pk=candidate_id, created_by=request.user)
    if not candidate.is_editable_by_owner:
        messages.warning(request, "This candidate is locked because scientific review has started or a decision has been recorded.")
        return redirect("my_submissions")
    initial = {"geometry_text": json.dumps(candidate.geometry) if candidate.geometry else ""}
    form = CandidateForm(request.POST or None, instance=candidate, initial=initial)
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        passed = _evaluate_and_save(candidate, form)
        if passed:
            messages.success(request, "Candidate updated, rescored, and retained in the unreviewed queue.")
        else:
            messages.warning(request, "Candidate updated and rescored, but it still needs revision before public review.")
        return redirect("my_submissions")
    return render(request, "portal/submit.html", {"form": form, "editing": True, "candidate": candidate})


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
    response = FileResponse(path.open("rb"), content_type="application/geo+json")
    if request.GET.get("download") == "1":
        response["Content-Disposition"] = f'attachment; filename="{slug}.geojson"'
    return response


@require_GET
def community_geojson(request):
    queryset = CandidateSubmission.objects.filter(status__in=PUBLIC_CANDIDATE_STATUSES).select_related("created_by")
    return _candidate_collection(queryset, request.GET.get("download") == "1")


@login_required
@require_GET
def my_candidates_geojson(request):
    return _candidate_collection(CandidateSubmission.objects.filter(created_by=request.user).select_related("created_by"), request.GET.get("download") == "1")


@login_required
@require_GET
def other_candidates_geojson(request):
    queryset = CandidateSubmission.objects.filter(status__in=PUBLIC_CANDIDATE_STATUSES).exclude(created_by=request.user).select_related("created_by")
    return _candidate_collection(queryset, request.GET.get("download") == "1")


def _candidate_collection(queryset, download=False):
    features = []
    for candidate in queryset:
        geometry = candidate.geometry or {"type": "Point", "coordinates": [candidate.longitude, candidate.latitude]}
        features.append({
            "type": "Feature",
            "id": str(candidate.id),
            "geometry": geometry,
            "properties": {
                "title": candidate.title,
                "longitude": candidate.longitude,
                "latitude": candidate.latitude,
                "diameter_km": candidate.diameter_km,
                "intake_score": candidate.intake_score,
                "followup_score": candidate.followup_score,
                "followup_status": candidate.followup_status,
                "data_quality": candidate.followup_metrics.get("data_quality"),
                "review_status": candidate.status,
                "score_interpretation": "submission completeness and reviewability; not impact probability",
                "status": candidate.get_status_display(),
                "source_title": candidate.source_title,
                "observed_feature": candidate.observed_feature,
                "submitted_by": candidate.created_by.username,
                "created_at": candidate.created_at.isoformat(),
            },
        })
    response = JsonResponse({"type": "FeatureCollection", "features": features})
    response["Content-Disposition"] = f'{"attachment" if download else "inline"}; filename="candidates.geojson"'
    return response


def help_page(request):
    return render(request, "portal/help.html")


@login_required
def globe(request):
    return render(request, "portal/globe.html", {"cesium_ion_token": settings.CESIUM_ION_TOKEN})


@user_passes_test(lambda user: user.is_staff)
def review_queue(request):
    submissions = CandidateSubmission.objects.exclude(status=CandidateSubmission.Status.BASELINE_FAILED).select_related("created_by", "moderated_by").prefetch_related("reviews")
    return render(request, "portal/review_queue.html", {"submissions": submissions, "status_choices": CandidateSubmission.Status.choices})


@user_passes_test(lambda user: user.is_staff)
@require_POST
def review_candidate(request, candidate_id):
    allowed = {value for value, _ in CandidateSubmission.Status.choices}
    target = request.POST.get("status")
    if target not in allowed:
        messages.error(request, "Choose a valid review status.")
        return redirect("review_queue")
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
    if score_field not in PREFERENCE_SCORE_FIELDS or palette not in PREFERENCE_PALETTES or drawing_method not in PREFERENCE_DRAWING_METHODS:
        raise ValueError
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
