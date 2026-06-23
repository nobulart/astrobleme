import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0003_candidate_followup_and_reviews"),
    ]

    operations = [
        migrations.CreateModel(
            name="CandidateAnalysisJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("claimed", "Claimed by worker"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="queued", max_length=24)),
                ("requested_reason", models.CharField(choices=[("new_submission", "New submission"), ("user_edit", "User edit"), ("reviewer_retry", "Reviewer retry"), ("method_upgrade", "Method upgrade")], default="new_submission", max_length=32)),
                ("priority", models.PositiveSmallIntegerField(default=50)),
                ("claimed_by", models.CharField(blank=True, max_length=120)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analysis_jobs", to="portal.candidatesubmission")),
            ],
            options={
                "ordering": ["-priority", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="CandidateAnalysisRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("succeeded", "Succeeded"), ("failed", "Failed"), ("source_unavailable", "Source unavailable")], max_length=32)),
                ("score", models.FloatField(blank=True, null=True)),
                ("score_percentile", models.FloatField(blank=True, null=True)),
                ("review_tier", models.CharField(blank=True, max_length=80)),
                ("method_version", models.CharField(blank=True, max_length=120)),
                ("worker_id", models.CharField(blank=True, max_length=120)),
                ("worker_version", models.CharField(blank=True, max_length=120)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("diagnostics", models.JSONField(blank=True, default=dict)),
                ("source_fingerprints", models.JSONField(blank=True, default=dict)),
                ("runtime_seconds", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analysis_runs", to="portal.candidatesubmission")),
                ("job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="runs", to="portal.candidateanalysisjob")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CandidateAnalysisArtifact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(max_length=80)),
                ("title", models.CharField(max_length=200)),
                ("mime_type", models.CharField(blank=True, max_length=120)),
                ("storage_backend", models.CharField(default="external", max_length=40)),
                ("url_or_path", models.CharField(max_length=1000)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("size_bytes", models.PositiveBigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("analysis_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="artifacts", to="portal.candidateanalysisrun")),
            ],
            options={
                "ordering": ["kind", "title"],
            },
        ),
        migrations.AddIndex(
            model_name="candidateanalysisjob",
            index=models.Index(fields=["status", "-priority", "created_at"], name="portal_job_queue_2bd42c_idx"),
        ),
        migrations.AddIndex(
            model_name="candidateanalysisjob",
            index=models.Index(fields=["lease_expires_at"], name="portal_job_lease_b8f6ac_idx"),
        ),
        migrations.AddIndex(
            model_name="candidateanalysisrun",
            index=models.Index(fields=["candidate", "-created_at"], name="p_run_cand_5fd2f7_idx"),
        ),
        migrations.AddIndex(
            model_name="candidateanalysisrun",
            index=models.Index(fields=["status", "-created_at"], name="p_run_status_2d96ab_idx"),
        ),
    ]
