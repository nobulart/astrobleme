from django.contrib import admin
from django.utils import timezone

from .models import CandidateSubmission


@admin.action(description="Move selected candidates to scientific review")
def mark_under_review(modeladmin, request, queryset):
    queryset.update(status=CandidateSubmission.Status.UNDER_REVIEW, moderated_by=request.user, moderated_at=timezone.now())


@admin.action(description="Accept selected candidates into review catalogue")
def mark_accepted(modeladmin, request, queryset):
    queryset.update(status=CandidateSubmission.Status.ACCEPTED, moderated_by=request.user, moderated_at=timezone.now())


@admin.action(description="Reject selected candidates")
def mark_rejected(modeladmin, request, queryset):
    queryset.update(status=CandidateSubmission.Status.REJECTED, moderated_by=request.user, moderated_at=timezone.now())


@admin.register(CandidateSubmission)
class CandidateSubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "intake_score", "baseline_passed", "created_by", "created_at")
    list_filter = ("status", "baseline_passed", "independent_evidence")
    search_fields = ("title", "description", "source_title", "created_by__username")
    readonly_fields = ("intake_score", "baseline_passed", "baseline_checks", "created_at", "updated_at")
    actions = (mark_under_review, mark_accepted, mark_rejected)
