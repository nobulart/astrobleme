import uuid

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
