import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name="CandidateSubmission",
        fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("title", models.CharField(max_length=120)),
            ("description", models.TextField()),
            ("longitude", models.FloatField(validators=[django.core.validators.MinValueValidator(-180), django.core.validators.MaxValueValidator(180)])),
            ("latitude", models.FloatField(validators=[django.core.validators.MinValueValidator(-90), django.core.validators.MaxValueValidator(90)])),
            ("diameter_km", models.FloatField(validators=[django.core.validators.MinValueValidator(0.1), django.core.validators.MaxValueValidator(10000)])),
            ("geometry", models.JSONField(blank=True, null=True)),
            ("source_title", models.CharField(max_length=240)),
            ("source_uri", models.URLField(blank=True, max_length=500)),
            ("source_resolution", models.CharField(blank=True, max_length=120)),
            ("observed_feature", models.CharField(max_length=240)),
            ("endogenic_alternative", models.TextField()),
            ("independent_evidence", models.JSONField(blank=True, default=list)),
            ("original_trace_available", models.BooleanField(default=False)),
            ("terms_confirmed", models.BooleanField(default=False)),
            ("intake_score", models.FloatField(default=0)),
            ("baseline_passed", models.BooleanField(default=False)),
            ("baseline_checks", models.JSONField(default=dict)),
            ("status", models.CharField(choices=[("baseline_failed", "Needs revision"), ("baseline_passed", "Baseline passed - unreviewed"), ("under_review", "Under review"), ("accepted", "Accepted into review catalogue"), ("rejected", "Rejected")], default="baseline_failed", max_length=32)),
            ("moderator_notes", models.TextField(blank=True)),
            ("moderated_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="candidate_submissions", to=settings.AUTH_USER_MODEL)),
            ("moderated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="moderated_candidates", to=settings.AUTH_USER_MODEL)),
        ],
        options={"ordering": ["-intake_score", "-created_at"]},
    ), migrations.AddIndex(
        model_name="candidatesubmission",
        index=models.Index(fields=["status", "intake_score"], name="portal_cand_status_4ed21e_idx"),
    )]
