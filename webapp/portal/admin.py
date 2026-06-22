from django.contrib import admin
from django.utils import timezone

from .models import CandidateReview, CandidateSubmission


def _change_status(request, queryset, status):
    for candidate in queryset:
        previous = candidate.status
        candidate.status = status
        candidate.moderated_by = request.user
        candidate.moderated_at = timezone.now()
        candidate.save()
        CandidateReview.objects.create(candidate=candidate, reviewer=request.user, from_status=previous, to_status=status, note="Status changed using Django administration.")


@admin.action(description="Move selected candidates to scientific review")
def mark_under_review(modeladmin, request, queryset):
    _change_status(request, queryset, CandidateSubmission.Status.UNDER_REVIEW)


@admin.action(description="Accept selected candidates into review catalogue")
def mark_accepted(modeladmin, request, queryset):
    _change_status(request, queryset, CandidateSubmission.Status.ACCEPTED)


@admin.action(description="Reject selected candidates")
def mark_rejected(modeladmin, request, queryset):
    _change_status(request, queryset, CandidateSubmission.Status.REJECTED)


@admin.register(CandidateSubmission)
class CandidateSubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "followup_score", "followup_status", "intake_score", "created_by", "created_at")
    list_filter = ("status", "followup_status", "baseline_passed", "independent_evidence")
    search_fields = ("title", "description", "source_title", "created_by__username")
    readonly_fields = ("intake_score", "followup_score", "followup_status", "followup_metrics", "followup_method_version", "baseline_passed", "baseline_checks", "created_at", "updated_at")
    actions = (mark_under_review, mark_accepted, mark_rejected)


@admin.register(CandidateReview)
class CandidateReviewAdmin(admin.ModelAdmin):
    list_display = ("candidate", "from_status", "to_status", "reviewer", "created_at")
    list_filter = ("to_status", "created_at")
    search_fields = ("candidate__title", "reviewer__username", "note")
    readonly_fields = ("candidate", "reviewer", "from_status", "to_status", "note", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
