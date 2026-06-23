from django.contrib import admin, messages
from django.utils import timezone

from .analysis_queue import enqueue_candidate_analysis
from .models import CandidateAnalysisArtifact, CandidateAnalysisJob, CandidateAnalysisRun, CandidateReview, CandidateSubmission


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


@admin.action(description="Queue selected candidates for automated analysis")
def queue_analysis(modeladmin, request, queryset):
    queued = 0
    for candidate in queryset:
        job = enqueue_candidate_analysis(candidate, CandidateAnalysisJob.Reason.REVIEWER_RETRY, force=True)
        if job:
            queued += 1
    modeladmin.message_user(request, f"Queued {queued} candidate(s) for automated analysis.", messages.SUCCESS)


@admin.register(CandidateSubmission)
class CandidateSubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "followup_score", "followup_status", "intake_score", "created_by", "created_at")
    list_filter = ("status", "followup_status", "baseline_passed", "independent_evidence")
    search_fields = ("title", "description", "source_title", "created_by__username")
    readonly_fields = ("intake_score", "followup_score", "followup_status", "followup_metrics", "followup_method_version", "baseline_passed", "baseline_checks", "created_at", "updated_at")
    actions = (mark_under_review, mark_accepted, mark_rejected, queue_analysis)


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


@admin.register(CandidateAnalysisJob)
class CandidateAnalysisJobAdmin(admin.ModelAdmin):
    list_display = ("candidate", "status", "requested_reason", "priority", "claimed_by", "attempt_count", "created_at", "updated_at")
    list_filter = ("status", "requested_reason", "created_at")
    search_fields = ("candidate__title", "claimed_by", "last_error")
    readonly_fields = ("candidate", "status", "requested_reason", "priority", "claimed_by", "claimed_at", "lease_expires_at", "attempt_count", "last_error", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False


class CandidateAnalysisArtifactInline(admin.TabularInline):
    model = CandidateAnalysisArtifact
    extra = 0
    readonly_fields = ("kind", "title", "mime_type", "storage_backend", "url_or_path", "sha256", "size_bytes", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CandidateAnalysisRun)
class CandidateAnalysisRunAdmin(admin.ModelAdmin):
    list_display = ("candidate", "status", "score", "score_percentile", "review_tier", "method_version", "worker_id", "created_at")
    list_filter = ("status", "method_version", "created_at")
    search_fields = ("candidate__title", "worker_id", "worker_version")
    readonly_fields = ("candidate", "job", "status", "score", "score_percentile", "review_tier", "method_version", "worker_id", "worker_version", "metrics", "diagnostics", "source_fingerprints", "runtime_seconds", "created_at")
    inlines = (CandidateAnalysisArtifactInline,)

    def has_add_permission(self, request):
        return False


@admin.register(CandidateAnalysisArtifact)
class CandidateAnalysisArtifactAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "analysis_run", "mime_type", "storage_backend", "created_at")
    list_filter = ("kind", "storage_backend", "created_at")
    search_fields = ("title", "url_or_path", "analysis_run__candidate__title")
    readonly_fields = ("analysis_run", "kind", "title", "mime_type", "storage_backend", "url_or_path", "sha256", "size_bytes", "created_at")

    def has_add_permission(self, request):
        return False
