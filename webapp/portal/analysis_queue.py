from .models import CandidateAnalysisJob, CandidateSubmission


ACTIVE_JOB_STATUSES = [
    CandidateAnalysisJob.Status.QUEUED,
    CandidateAnalysisJob.Status.CLAIMED,
    CandidateAnalysisJob.Status.RUNNING,
]


def enqueue_candidate_analysis(candidate, reason, *, force=False):
    CandidateAnalysisJob.objects.filter(candidate=candidate, status__in=ACTIVE_JOB_STATUSES).update(
        status=CandidateAnalysisJob.Status.CANCELLED,
        last_error="Superseded by a newer candidate state.",
    )
    if not force and (not candidate.baseline_passed or candidate.status == CandidateSubmission.Status.BASELINE_FAILED):
        return None
    return CandidateAnalysisJob.objects.create(candidate=candidate, requested_reason=reason)
