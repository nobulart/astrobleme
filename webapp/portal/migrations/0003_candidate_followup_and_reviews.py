from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0002_usermappreference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="candidatesubmission", name="followup_score", field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name="candidatesubmission", name="followup_status", field=models.CharField(choices=[("not_scored", "Not scored"), ("scored", "Scored with study method"), ("source_unavailable", "Scientific source data unavailable"), ("failed", "Scoring failed")], default="not_scored", max_length=32)),
        migrations.AddField(model_name="candidatesubmission", name="followup_metrics", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="candidatesubmission", name="followup_method_version", field=models.CharField(blank=True, max_length=80)),
        migrations.CreateModel(
            name="CandidateReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(choices=[("baseline_failed", "Needs revision"), ("baseline_passed", "Baseline passed - unreviewed"), ("under_review", "Under review"), ("accepted", "Accepted into review catalogue"), ("rejected", "Rejected")], max_length=32)),
                ("to_status", models.CharField(choices=[("baseline_failed", "Needs revision"), ("baseline_passed", "Baseline passed - unreviewed"), ("under_review", "Under review"), ("accepted", "Accepted into review catalogue"), ("rejected", "Rejected")], max_length=32)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("candidate", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reviews", to="portal.candidatesubmission")),
                ("reviewer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="candidate_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
