import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .forms import CandidateForm, RegistrationForm
from .models import CandidateSubmission
from .scoring import evaluate_submission

LAYERS = {
    "study-candidates": ("study_results_geojson/arcuate_geometries_study_results.geojson", "Study candidates", "candidate"),
    "repaired-catalogue": ("catalog_repair/astroblemes_analysis.geojson", "Repaired global catalogue", "catalogue"),
    "african-structures": ("african_impact_structures.geojson", "African structures", "africa"),
    "negative-controls": ("data/controls.geojson", "Endogenic controls", "control"),
    "active-faults": ("geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson", "GEM active faults", "fault"),
}


def home(request):
    return render(request, "portal/home.html", {"layers": LAYERS})


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
    form = CandidateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        candidate.created_by = request.user
        candidate.geometry = form.cleaned_data["geometry_text"]
        score, passed, checks = evaluate_submission(form.cleaned_data | {"geometry": candidate.geometry})
        candidate.intake_score = score
        candidate.baseline_passed = passed
        candidate.baseline_checks = checks
        candidate.status = CandidateSubmission.Status.BASELINE_PASSED if passed else CandidateSubmission.Status.BASELINE_FAILED
        candidate.save()
        if passed:
            messages.success(request, "Candidate passed the intake baseline and is now visible as an unreviewed community submission.")
        else:
            messages.warning(request, "Submission saved, but it needs revision before entering the public review queue.")
        return redirect("my_submissions")
    return render(request, "portal/submit.html", {"form": form})


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
    return FileResponse(path.open("rb"), content_type="application/geo+json")


@require_GET
def community_geojson(request):
    public_statuses = [CandidateSubmission.Status.BASELINE_PASSED, CandidateSubmission.Status.UNDER_REVIEW, CandidateSubmission.Status.ACCEPTED]
    features = []
    for c in CandidateSubmission.objects.filter(status__in=public_statuses).select_related("created_by"):
        geometry = c.geometry or {"type": "Point", "coordinates": [c.longitude, c.latitude]}
        features.append({
            "type": "Feature",
            "id": str(c.id),
            "geometry": geometry,
            "properties": {
                "title": c.title,
                "longitude": c.longitude,
                "latitude": c.latitude,
                "diameter_km": c.diameter_km,
                "intake_score": c.intake_score,
                "score_interpretation": "submission completeness and reviewability; not impact probability",
                "status": c.get_status_display(),
                "source_title": c.source_title,
                "observed_feature": c.observed_feature,
                "submitted_by": c.created_by.username,
                "created_at": c.created_at.isoformat(),
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
