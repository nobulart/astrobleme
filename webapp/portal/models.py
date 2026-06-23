import uuid

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PortalConfiguration(models.Model):
    baseline_score_threshold = models.FloatField(default=0.55, validators=[MinValueValidator(0), MaxValueValidator(1)])
    min_description_chars = models.PositiveSmallIntegerField(default=80, validators=[MinValueValidator(0)])
    min_endogenic_alternative_chars = models.PositiveSmallIntegerField(default=20, validators=[MinValueValidator(0)])
    min_source_title_chars = models.PositiveSmallIntegerField(default=8, validators=[MinValueValidator(0)])
    min_observed_feature_chars = models.PositiveSmallIntegerField(default=8, validators=[MinValueValidator(0)])
    min_diameter_km = models.FloatField(default=10, validators=[MinValueValidator(0.1), MaxValueValidator(10000)])
    max_diameter_km = models.FloatField(default=5000, validators=[MinValueValidator(0.1), MaxValueValidator(10000)])
    duplicate_distance_fraction = models.FloatField(default=0.25, validators=[MinValueValidator(0), MaxValueValidator(1)])
    duplicate_min_distance_km = models.FloatField(default=5, validators=[MinValueValidator(0)])
    require_terms_confirmed = models.BooleanField(default=True)
    require_unique_study_candidate = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Review configuration"
        verbose_name_plural = "Review configuration"

    def __str__(self):
        return "Review configuration"

    @classmethod
    def current(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


class CandidateSubmission(models.Model):
    class FollowupStatus(models.TextChoices):
        NOT_SCORED = "not_scored", "Not scored"
        SCORED = "scored", "Scored with study method"
        SOURCE_UNAVAILABLE = "source_unavailable", "Scientific source data unavailable"
        FAILED = "failed", "Scoring failed"

    class Status(models.TextChoices):
        BASELINE_FAILED = "baseline_failed", "Needs revision"
        BASELINE_PASSED = "baseline_passed", "Baseline passed - unreviewed"
        UNDER_REVIEW = "under_review", "Under review"
        ACCEPTED = "accepted", "Accepted into review catalogue"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="candidate_submissions")
    title = models.CharField(max_length=120)
    description = models.TextField()
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    diameter_km = models.FloatField(validators=[MinValueValidator(0.1), MaxValueValidator(10000)])
    geometry = models.JSONField(null=True, blank=True)
    source_title = models.CharField(max_length=240)
    source_uri = models.URLField(max_length=500, blank=True)
    source_resolution = models.CharField(max_length=120, blank=True)
    observed_feature = models.CharField(max_length=240)
    endogenic_alternative = models.TextField()
    independent_evidence = models.JSONField(default=list, blank=True)
    original_trace_available = models.BooleanField(default=False)
    terms_confirmed = models.BooleanField(default=False)
    intake_score = models.FloatField(default=0)
    followup_score = models.FloatField(null=True, blank=True)
    followup_status = models.CharField(max_length=32, choices=FollowupStatus.choices, default=FollowupStatus.NOT_SCORED)
    followup_metrics = models.JSONField(default=dict, blank=True)
    followup_method_version = models.CharField(max_length=80, blank=True)
    baseline_passed = models.BooleanField(default=False)
    baseline_checks = models.JSONField(default=dict)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.BASELINE_FAILED)
    moderator_notes = models.TextField(blank=True)
    moderated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="moderated_candidates")
    moderated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-intake_score", "-created_at"]
        indexes = [models.Index(fields=["status", "intake_score"], name="portal_cand_status_4ed21e_idx")]

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def is_editable_by_owner(self):
        return self.status in {self.Status.BASELINE_FAILED, self.Status.BASELINE_PASSED}


class UserMapPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="map_preference")
    settings = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Map preferences for {self.user.username}"


class CandidateReview(models.Model):
    candidate = models.ForeignKey(CandidateSubmission, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="candidate_reviews")
    from_status = models.CharField(max_length=32, choices=CandidateSubmission.Status.choices)
    to_status = models.CharField(max_length=32, choices=CandidateSubmission.Status.choices)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.candidate} → {self.get_to_status_display()}"


class CandidateAnalysisJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        CLAIMED = "claimed", "Claimed by worker"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class Reason(models.TextChoices):
        NEW_SUBMISSION = "new_submission", "New submission"
        USER_EDIT = "user_edit", "User edit"
        REVIEWER_RETRY = "reviewer_retry", "Reviewer retry"
        METHOD_UPGRADE = "method_upgrade", "Method upgrade"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(CandidateSubmission, on_delete=models.CASCADE, related_name="analysis_jobs")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED)
    requested_reason = models.CharField(max_length=32, choices=Reason.choices, default=Reason.NEW_SUBMISSION)
    priority = models.PositiveSmallIntegerField(default=50)
    claimed_by = models.CharField(max_length=120, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "created_at"]
        indexes = [
            models.Index(fields=["status", "-priority", "created_at"], name="portal_job_queue_2bd42c_idx"),
            models.Index(fields=["lease_expires_at"], name="portal_job_lease_b8f6ac_idx"),
        ]

    def __str__(self):
        return f"{self.candidate.title} analysis job ({self.status})"


class CandidateAnalysisRun(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        SOURCE_UNAVAILABLE = "source_unavailable", "Source unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(CandidateSubmission, on_delete=models.CASCADE, related_name="analysis_runs")
    job = models.ForeignKey(CandidateAnalysisJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="runs")
    status = models.CharField(max_length=32, choices=Status.choices)
    score = models.FloatField(null=True, blank=True)
    score_percentile = models.FloatField(null=True, blank=True)
    review_tier = models.CharField(max_length=80, blank=True)
    method_version = models.CharField(max_length=120, blank=True)
    worker_id = models.CharField(max_length=120, blank=True)
    worker_version = models.CharField(max_length=120, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)
    source_fingerprints = models.JSONField(default=dict, blank=True)
    runtime_seconds = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["candidate", "-created_at"], name="p_run_cand_5fd2f7_idx"),
            models.Index(fields=["status", "-created_at"], name="p_run_status_2d96ab_idx"),
        ]

    def __str__(self):
        return f"{self.candidate.title} analysis run ({self.status})"


class CandidateAnalysisArtifact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis_run = models.ForeignKey(CandidateAnalysisRun, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    mime_type = models.CharField(max_length=120, blank=True)
    storage_backend = models.CharField(max_length=40, default="external")
    url_or_path = models.CharField(max_length=1000)
    sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "title"]

    def __str__(self):
        return f"{self.title} ({self.kind})"
