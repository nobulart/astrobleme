from .models import CandidateAnalysisJob, CandidateSubmission


ACTIVE_JOB_STATUSES = [
    CandidateAnalysisJob.Status.QUEUED,
    CandidateAnalysisJob.Status.CLAIMED,
    CandidateAnalysisJob.Status.RUNNING,
]


def enqueue_candidate_analysis(candidate, reason):
    CandidateAnalysisJob.objects.filter(candidate=candidate, status__in=ACTIVE_JOB_STATUSES).update(
        status=CandidateAnalysisJob.Status.CANCELLED,
        last_error="Superseded by a newer candidate state.",
    )
    if not candidate.baseline_passed or candidate.status == CandidateSubmission.Status.BASELINE_FAILED:
        return None
    return CandidateAnalysisJob.objects.create(candidate=candidate, requested_reason=reason)
