from django.db import migrations


def queue_source_unavailable_candidates(apps, schema_editor):
    CandidateSubmission = apps.get_model("portal", "CandidateSubmission")
    CandidateAnalysisJob = apps.get_model("portal", "CandidateAnalysisJob")

    existing_candidate_ids = set(
        CandidateAnalysisJob.objects.exclude(status="cancelled").values_list("candidate_id", flat=True)
    )
    candidates = CandidateSubmission.objects.filter(followup_status="source_unavailable").exclude(
        id__in=existing_candidate_ids
    )
    CandidateAnalysisJob.objects.bulk_create([
        CandidateAnalysisJob(
            candidate_id=candidate.id,
            requested_reason="reviewer_retry",
            priority=50,
        )
        for candidate in candidates
    ])


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0004_candidate_analysis_pipeline"),
    ]

    operations = [
        migrations.RunPython(queue_source_unavailable_candidates, migrations.RunPython.noop),
    ]
