import base64
import json
import tempfile
from types import SimpleNamespace

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.http import HttpResponse
from unittest.mock import Mock, patch

from .followup import circle_geometry, score_candidate
from .models import CandidateAnalysisArtifact, CandidateAnalysisJob, CandidateAnalysisRun, CandidateReview, CandidateSubmission, PortalConfiguration, UserMapPreference
from .scoring import evaluate_submission


VALID = {
    "title": "North Basin annular ridge",
    "description": "A partial annular ridge is visible across several quadrants and remains coherent across the cited terrain source.",
    "longitude": 10.0,
    "latitude": 10.0,
    "diameter_km": 65.0,
    "source_title": "Regional terrain mosaic 2025",
    "source_uri": "https://example.org/source",
    "source_resolution": "30 m",
    "observed_feature": "Partial annular ridge and drainage deflection",
    "endogenic_alternative": "A buried intrusive complex or caldera is a plausible alternative.",
    "independent_evidence": ["gravity", "geology"],
    "original_trace_available": False,
    "terms_confirmed": True,
}


class IntakeScoringTests(TestCase):
    def test_circle_geometry_is_closed_and_dense(self):
        geometry = circle_geometry(20, -30, 100)
        self.assertEqual(geometry["type"], "LineString")
        self.assertEqual(len(geometry["coordinates"]), 73)
        self.assertEqual(geometry["coordinates"][0], geometry["coordinates"][-1])

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist", GEBCO_GRID_PATH="/missing/gebco.nc", GEOLOGY_INDEX_PATH="/missing/geology.kml")
    def test_complete_submission_passes(self):
        from .scoring import study_centres
        study_centres.cache_clear()
        score, passed, checks = evaluate_submission(VALID)
        self.assertTrue(passed)
        self.assertGreaterEqual(score, 0.55)
        self.assertIn("scientific_note", checks)

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist", GEBCO_GRID_PATH="/missing/gebco.nc", GEOLOGY_INDEX_PATH="/missing/geology.kml")
    def test_configurable_baseline_threshold_can_block_submission(self):
        PortalConfiguration.objects.create(pk=1, baseline_score_threshold=0.9)
        score, passed, checks = evaluate_submission(VALID)
        self.assertEqual(score, 0.85)
        self.assertFalse(passed)
        self.assertFalse(checks["intake_threshold"])
        self.assertEqual(checks["configuration"]["baseline_score_threshold"], 0.9)

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist", GEBCO_GRID_PATH="/missing/gebco.nc", GEOLOGY_INDEX_PATH="/missing/geology.kml")
    def test_configurable_text_lengths_can_relax_baseline_gates(self):
        PortalConfiguration.objects.create(
            pk=1,
            baseline_score_threshold=0.5,
            min_description_chars=1,
            min_endogenic_alternative_chars=1,
        )
        data = VALID | {"description": "x", "endogenic_alternative": "x"}
        score, passed, checks = evaluate_submission(data)
        self.assertEqual(score, 0.85)
        self.assertTrue(passed)
        self.assertTrue(checks["description_complete"])
        self.assertTrue(checks["alternative_considered"])

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist")
    def test_short_undocumented_submission_fails(self):
        from .scoring import study_centres
        study_centres.cache_clear()
        data = VALID | {"description": "A circle.", "source_title": "", "endogenic_alternative": "unknown"}
        score, passed, checks = evaluate_submission(data)
        self.assertFalse(passed)
        self.assertFalse(checks["description_complete"])

    def test_followup_scoring_can_merge_worker_geophysics(self):
        def fake_pipeline_imports():
            def save_figure(*_args, **_kwargs):
                return None

            def score_terrain(_candidate, _window):
                return {
                    "data_quality": 1.0,
                    "topography_score_unweighted": 0.5,
                    "radial_alignment": 0.1,
                    "hough_percentile": 0.2,
                    "angular_continuity": 0.3,
                    "radius_match": 0.4,
                    "centre_match": 0.5,
                    "relief_score": 0.6,
                }, {}

            class FakeGrid:
                def __init__(self, *_args, **_kwargs):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    pass

                def read_candidate(self, _candidate):
                    return None

            def spherical_candidate(_feature, _index):
                return SimpleNamespace(lon=10, lat=10, diameter_km=65)

            return save_figure, score_terrain, FakeGrid, None, spherical_candidate

        candidate = SimpleNamespace(id="candidate-1", title="Worker candidate", longitude=10, latitude=10, diameter_km=65, geometry=None)
        with tempfile.NamedTemporaryFile() as grid, tempfile.NamedTemporaryFile() as geology:
            with override_settings(GEBCO_GRID_PATH=grid.name, GEOLOGY_INDEX_PATH=geology.name):
                with patch("portal.followup._pipeline_imports", fake_pipeline_imports), patch("portal.followup._geology_index") as geology_index, patch("portal.geophysics.score_geophysics") as geophysics:
                    geology_index.return_value.score.return_value = {"geology_independence": 1.0}
                    geophysics.return_value = {
                        "gravity_consensus_percentile": 0.91,
                        "magnetic_ring_score_stratified_percentile": 0.82,
                        "review_tier": "B_gravity_supported",
                    }
                    result = score_candidate(candidate, include_geophysics=True)
        self.assertEqual(result["score"], 0.61)
        self.assertEqual(result["metrics"]["gravity_consensus_percentile"], 0.91)
        self.assertEqual(result["metrics"]["magnetic_ring_score_stratified_percentile"], 0.82)
        self.assertEqual(result["metrics"]["review_tier"], "B_gravity_supported")
        self.assertTrue(result["method_version"].endswith("+geophysics-v1"))


class PortalViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reviewer", "reviewer@example.org", "long-test-password")

    def test_home_and_health_are_public(self):
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Esri aerial imagery")
        self.assertContains(home, "Dark map")
        self.assertContains(home, "Labels and roads overlay")
        self.assertContains(home, "NASA MODIS satellite")
        self.assertContains(home, "Registered reviewers can compare live elevation")
        self.assertNotContains(home, "Analysis status")
        self.assertNotContains(home, "GEBCO source identifier")
        self.assertNotContains(home, "Inspect WGM2012 gravity")
        self.assertEqual(self.client.get(reverse("health")).json(), {"status": "ok", "database": "ok"})

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True)
    def test_health_is_not_redirected_to_https(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)

    def test_submission_requires_login(self):
        response = self.client.get(reverse("submit_candidate"))
        self.assertEqual(response.status_code, 302)

    def test_map_click_query_prefills_submission_review(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("submit_candidate"), {
            "latitude": "-28.125", "longitude": "24.75", "diameter_km": "140",
            "title": "Candidate near -28.13, 24.75", "source_title": "Esri World Imagery",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="-28.125"')
        self.assertContains(response, 'value="24.75"')
        self.assertContains(response, 'value="140.0"')
        self.assertContains(response, "Candidate near -28.13, 24.75")
        self.assertContains(response, "Esri World Imagery")
        self.assertContains(response, "Estimated centre longitude")
        self.assertContains(response, "This is not a final or transient crater diameter")
        self.assertContains(response, "Best non-impact alternative")

    def test_community_api_excludes_failed_records(self):
        CandidateSubmission.objects.create(
            created_by=self.user, title="Private failed item", description="x", longitude=1, latitude=1,
            diameter_km=5, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_FAILED,
        )
        self.assertEqual(self.client.get(reverse("community_geojson")).json()["features"], [])

    def test_candidate_library_scopes_own_and_other_users(self):
        other = User.objects.create_user("other", "other@example.org", "long-test-password")
        own = CandidateSubmission.objects.create(
            created_by=self.user, title="Own private draft", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_FAILED,
        )
        public_other = CandidateSubmission.objects.create(
            created_by=other, title="Other public candidate", description="x", longitude=2, latitude=2,
            diameter_km=30, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        CandidateSubmission.objects.create(
            created_by=other, title="Other private draft", description="x", longitude=3, latitude=3,
            diameter_km=40, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_FAILED,
        )
        self.client.force_login(self.user)
        mine = self.client.get(reverse("my_candidates_geojson")).json()["features"]
        others = self.client.get(reverse("other_candidates_geojson")).json()["features"]
        self.assertEqual([feature["id"] for feature in mine], [str(own.id)])
        self.assertEqual([feature["id"] for feature in others], [str(public_other.id)])

    def test_map_preferences_are_saved_and_reset(self):
        self.client.force_login(self.user)
        payload = {
            "center": [-25.2, 28.1], "zoom": 7,
            "layers": ["my-candidates", "other-candidates"], "basemap": "dark", "labels": False,
            "rasters": ["magnetic"], "rasterOpacity": 54, "satelliteDate": "2026-06-20",
            "candidateDraft": {"latitude": -25.1, "longitude": 28.2, "diameterKm": 80},
            "layerStyles": {"my-candidates": {"lineStyle": "dotted", "lineWidth": 3.5}},
        }
        saved = self.client.post(reverse("map_preferences"), json.dumps(payload), content_type="application/json")
        self.assertEqual(saved.status_code, 200)
        settings = UserMapPreference.objects.get(user=self.user).settings
        self.assertEqual(settings["basemap"], "dark")
        self.assertFalse(settings["labels"])
        self.assertEqual(settings["layerStyles"]["my-candidates"], {"lineStyle": "dotted", "lineWidth": 3.5})
        home = self.client.get(reverse("home"))
        self.assertContains(home, '"diameterKm": 80.0')
        reset = self.client.post(reverse("map_preferences"), json.dumps({"reset": True}), content_type="application/json")
        self.assertEqual(reset.status_code, 200)
        self.assertFalse(UserMapPreference.objects.filter(user=self.user).exists())

    def test_authenticated_home_includes_analysis_status_sidebar(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Analysis status")
        self.assertContains(response, reverse("analysis_status"))

    def test_admin_exposes_review_configuration(self):
        staff = User.objects.create_superuser("staff", "staff@example.org", "long-test-password")
        self.client.force_login(staff)
        response = self.client.get(reverse("admin:portal_portalconfiguration_add"))
        self.assertContains(response, "Baseline score threshold")
        self.assertContains(response, "Min description chars")
        self.assertContains(response, "Duplicate distance fraction")

    def test_analysis_status_endpoint_reports_personal_progress(self):
        candidate = CandidateSubmission.objects.create(
            created_by=self.user,
            title="Progress candidate",
            description=VALID["description"],
            longitude=VALID["longitude"],
            latitude=VALID["latitude"],
            diameter_km=VALID["diameter_km"],
            source_title=VALID["source_title"],
            observed_feature=VALID["observed_feature"],
            endogenic_alternative=VALID["endogenic_alternative"],
            intake_score=0.88,
            baseline_passed=True,
            status=CandidateSubmission.Status.BASELINE_PASSED,
            followup_status=CandidateSubmission.FollowupStatus.SCORED,
            followup_score=0.8123,
            followup_metrics={"score_percentile": 96.5, "data_quality": 0.89, "diagnostics": {"summary": "Strong annular signal."}},
        )
        CandidateAnalysisJob.objects.create(candidate=candidate, status=CandidateAnalysisJob.Status.SUCCEEDED)
        CandidateAnalysisRun.objects.create(candidate=candidate, status=CandidateAnalysisRun.Status.SUCCEEDED, score=0.8123)
        self.assertEqual(self.client.get(reverse("analysis_status")).status_code, 302)
        self.client.force_login(self.user)
        payload = self.client.get(reverse("analysis_status")).json()
        self.assertEqual(payload["totals"]["baseline_passed"], 1)
        self.assertEqual(payload["totals"]["finished"], 1)
        self.assertEqual(payload["totals"]["progress_percent"], 100)
        self.assertEqual(payload["followup"]["scored"], 1)
        self.assertEqual(payload["jobs"]["succeeded"], 1)
        self.assertEqual(payload["runs"]["succeeded"], 1)
        self.assertEqual(payload["recent"][0]["title"], "Progress candidate")
        self.assertEqual(payload["recent"][0]["state_label"], "Scored with study method")

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist", GEBCO_GRID_PATH="/missing/gebco.nc", GEOLOGY_INDEX_PATH="/missing/geology.kml")
    def test_authenticated_submission_is_scored_and_published(self):
        from .scoring import study_centres
        study_centres.cache_clear()
        self.client.force_login(self.user)
        UserMapPreference.objects.create(user=self.user, settings={"candidateDraft": {"latitude": 10, "longitude": 10, "diameterKm": 65}})
        response = self.client.post(reverse("submit_candidate"), VALID)
        self.assertRedirects(response, reverse("my_submissions"))
        item = CandidateSubmission.objects.get(title=VALID["title"])
        self.assertTrue(item.baseline_passed)
        self.assertEqual(item.status, CandidateSubmission.Status.BASELINE_PASSED)
        self.assertEqual(item.followup_status, CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(item.geometry["type"], "LineString")
        job = CandidateAnalysisJob.objects.get(candidate=item)
        self.assertEqual(job.status, CandidateAnalysisJob.Status.QUEUED)
        self.assertEqual(job.requested_reason, CandidateAnalysisJob.Reason.NEW_SUBMISSION)
        self.assertIsNone(UserMapPreference.objects.get(user=self.user).settings["candidateDraft"])
        public = self.client.get(reverse("community_geojson")).json()
        self.assertEqual(len(public["features"]), 1)

    def test_help_and_authenticated_globe_are_available(self):
        help_response = self.client.get(reverse("help"))
        self.assertContains(help_response, "data quality ×")
        self.assertContains(help_response, "Review configuration")
        self.assertContains(help_response, "Automated analysis")
        self.assertContains(help_response, "Intake score threshold: 0.55")
        self.assertEqual(self.client.get(reverse("globe")).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(reverse("globe"))
        self.assertContains(response, "WGM2012 Bouguer gravity")
        self.assertContains(response, "View mode")
        self.assertContains(response, "Columbus")

    def test_submission_page_documents_current_review_configuration(self):
        PortalConfiguration.objects.create(pk=1, baseline_score_threshold=0.4, min_description_chars=12)
        self.client.force_login(self.user)
        response = self.client.get(reverse("submit_candidate"))
        self.assertContains(response, "Current baseline")
        self.assertContains(response, "What makes a useful submission")
        self.assertContains(response, "rationale ≥12 chars")
        self.assertContains(response, "intake score ≥0.40")

    def test_staff_review_is_audited(self):
        staff = User.objects.create_user("staff", "staff@example.org", "long-test-password", is_staff=True)
        item = CandidateSubmission.objects.create(created_by=self.user, title="Review me", description="x", longitude=1, latitude=1, diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x", status=CandidateSubmission.Status.BASELINE_PASSED)
        self.client.force_login(staff)
        response = self.client.post(reverse("review_candidate", args=[item.id]), {"status": CandidateSubmission.Status.UNDER_REVIEW, "note": "Worth checking"})
        self.assertRedirects(response, reverse("review_queue"))
        item.refresh_from_db()
        self.assertEqual(item.status, CandidateSubmission.Status.UNDER_REVIEW)
        self.assertEqual(CandidateReview.objects.get(candidate=item).note, "Worth checking")

    def test_staff_geojson_exposes_popup_candidate_actions(self):
        staff = User.objects.create_user("staff", "staff@example.org", "long-test-password", is_staff=True)
        item = CandidateSubmission.objects.create(
            created_by=self.user, title="Popup controlled", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        self.client.force_login(staff)
        feature = self.client.get(reverse("other_candidates_geojson")).json()["features"][0]
        actions = feature["properties"]["actions"]
        self.assertEqual(feature["id"], str(item.id))
        self.assertIn(reverse("edit_candidate", args=[item.id]), actions["edit_url"])
        self.assertIn(reverse("candidate_status_api", args=[item.id]), actions["status_url"])
        self.assertIn(reverse("candidate_delete_api", args=[item.id]), actions["delete_url"])
        self.assertIn({"value": CandidateSubmission.Status.ACCEPTED, "label": "Accepted into review catalogue"}, actions["status_choices"])

    def test_permissioned_user_can_change_status_from_popup_api(self):
        reviewer = User.objects.create_user("status_editor", "status@example.org", "long-test-password")
        reviewer.user_permissions.add(Permission.objects.get(codename="change_candidatesubmission"))
        item = CandidateSubmission.objects.create(
            created_by=self.user, title="Status target", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        self.client.force_login(reviewer)
        response = self.client.post(
            reverse("candidate_status_api", args=[item.id]),
            json.dumps({"status": CandidateSubmission.Status.ACCEPTED, "note": "Popup review"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, CandidateSubmission.Status.ACCEPTED)
        self.assertEqual(item.moderator_notes, "Popup review")
        self.assertEqual(CandidateReview.objects.get(candidate=item).reviewer, reviewer)
        self.assertEqual(response.json()["properties"]["status"], "Accepted into review catalogue")

    def test_delete_permission_can_delete_candidate_from_popup_api(self):
        deleter = User.objects.create_user("candidate_deleter", "delete@example.org", "long-test-password")
        deleter.user_permissions.add(Permission.objects.get(codename="delete_candidatesubmission"))
        item = CandidateSubmission.objects.create(
            created_by=self.user, title="Delete target", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        self.client.force_login(deleter)
        response = self.client.post(reverse("candidate_delete_api", args=[item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CandidateSubmission.objects.filter(pk=item.id).exists())

    def test_unprivileged_user_cannot_use_popup_status_api(self):
        item = CandidateSubmission.objects.create(
            created_by=self.user, title="Protected", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("candidate_status_api", args=[item.id]), {"status": CandidateSubmission.Status.ACCEPTED})
        self.assertEqual(response.status_code, 403)

    def test_review_queue_filters_and_searches_candidates(self):
        staff = User.objects.create_user("staff", "staff@example.org", "long-test-password", is_staff=True)
        CandidateSubmission.objects.create(
            created_by=self.user,
            title="Visible arc",
            description="x",
            longitude=1,
            latitude=1,
            diameter_km=20,
            source_title="Regional mosaic",
            observed_feature="Annular ridge",
            endogenic_alternative="x",
            status=CandidateSubmission.Status.UNDER_REVIEW,
            followup_status=CandidateSubmission.FollowupStatus.SCORED,
            followup_score=0.62,
        )
        CandidateSubmission.objects.create(
            created_by=self.user,
            title="Accepted basin",
            description="x",
            longitude=2,
            latitude=2,
            diameter_km=40,
            source_title="Another mosaic",
            observed_feature="Gravity dome",
            endogenic_alternative="x",
            status=CandidateSubmission.Status.ACCEPTED,
            followup_status=CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE,
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("review_queue"), {"status": CandidateSubmission.Status.UNDER_REVIEW, "q": "arc"})
        self.assertContains(response, "Visible arc")
        self.assertNotContains(response, "Accepted basin")
        self.assertContains(response, "Queue analysis")
        self.assertContains(response, "Analysis diagnostics")
        self.assertContains(response, "Review status is the catalogue decision")
        self.assertContains(response, "key alternative considered")

    def test_review_queue_can_force_queue_analysis(self):
        staff = User.objects.create_user("staff", "staff@example.org", "long-test-password", is_staff=True)
        item = CandidateSubmission.objects.create(
            created_by=self.user,
            title="Needs worker",
            description="x",
            longitude=1,
            latitude=1,
            diameter_km=20,
            source_title="Regional mosaic",
            observed_feature="Annular ridge",
            endogenic_alternative="x",
            baseline_passed=False,
            status=CandidateSubmission.Status.ACCEPTED,
        )
        self.client.force_login(staff)
        response = self.client.post(reverse("review_candidate", args=[item.id]), {
            "action": "queue_analysis",
            "next": reverse("review_queue") + "?status=accepted",
        })
        self.assertRedirects(response, reverse("review_queue") + "?status=accepted", fetch_redirect_response=False)
        job = CandidateAnalysisJob.objects.get(candidate=item)
        self.assertEqual(job.status, CandidateAnalysisJob.Status.QUEUED)
        self.assertEqual(job.requested_reason, CandidateAnalysisJob.Reason.REVIEWER_RETRY)

    def test_staff_admin_action_force_queues_baseline_failed_candidate(self):
        staff = User.objects.create_superuser("staff", "staff@example.org", "long-test-password")
        item = CandidateSubmission.objects.create(
            created_by=self.user,
            title="Accepted but short",
            description="x",
            longitude=1,
            latitude=1,
            diameter_km=20,
            source_title="x",
            observed_feature="x",
            endogenic_alternative="x",
            baseline_passed=False,
            status=CandidateSubmission.Status.ACCEPTED,
        )
        self.client.force_login(staff)
        response = self.client.post(reverse("admin:portal_candidatesubmission_changelist"), {
            "action": "queue_analysis",
            "_selected_action": [str(item.id)],
        }, follow=True)
        self.assertContains(response, "Queued 1 candidate(s) for automated analysis.")
        job = CandidateAnalysisJob.objects.get(candidate=item)
        self.assertEqual(job.status, CandidateAnalysisJob.Status.QUEUED)
        self.assertEqual(job.requested_reason, CandidateAnalysisJob.Reason.REVIEWER_RETRY)

    def test_geojson_download_sets_attachment_header(self):
        response = self.client.get(reverse("layer_geojson", args=["negative-controls"]), {"download": "1"})
        self.assertIn("attachment", response["Content-Disposition"])

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist", GEBCO_GRID_PATH="/missing/gebco.nc", GEOLOGY_INDEX_PATH="/missing/geology.kml")
    def test_owner_can_edit_and_rescore_pending_candidate(self):
        item = CandidateSubmission.objects.create(
            created_by=self.user, title="Pending draft", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_FAILED,
        )
        self.client.force_login(self.user)
        page = self.client.get(reverse("edit_candidate", args=[item.id]))
        self.assertContains(page, "Re-evaluate and save changes")
        response = self.client.post(reverse("edit_candidate", args=[item.id]), VALID | {"title": "Improved pending candidate"})
        self.assertRedirects(response, reverse("my_submissions"))
        item.refresh_from_db()
        self.assertEqual(item.title, "Improved pending candidate")
        self.assertTrue(item.baseline_passed)
        self.assertEqual(item.status, CandidateSubmission.Status.BASELINE_PASSED)
        self.assertEqual(item.followup_status, CandidateSubmission.FollowupStatus.SOURCE_UNAVAILABLE)
        job = CandidateAnalysisJob.objects.get(candidate=item)
        self.assertEqual(job.requested_reason, CandidateAnalysisJob.Reason.USER_EDIT)

    def test_other_users_cannot_edit_candidate(self):
        other = User.objects.create_user("candidate_owner", "owner@example.org", "long-test-password")
        item = CandidateSubmission.objects.create(
            created_by=other, title="Not yours", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("edit_candidate", args=[item.id])).status_code, 404)

    def test_candidate_is_locked_after_review_starts(self):
        item = CandidateSubmission.objects.create(
            created_by=self.user, title="Locked candidate", description="x", longitude=1, latitude=1,
            diameter_km=20, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.UNDER_REVIEW,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_candidate", args=[item.id]))
        self.assertRedirects(response, reverse("my_submissions"))
        self.assertEqual(CandidateSubmission.objects.get(pk=item.id).title, "Locked candidate")


class AnalysisApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("candidate_owner", "owner@example.org", "long-test-password")
        self.candidate = CandidateSubmission.objects.create(
            created_by=self.user,
            title="Worker target",
            description=VALID["description"],
            longitude=VALID["longitude"],
            latitude=VALID["latitude"],
            diameter_km=VALID["diameter_km"],
            geometry=circle_geometry(VALID["longitude"], VALID["latitude"], VALID["diameter_km"]),
            source_title=VALID["source_title"],
            source_uri=VALID["source_uri"],
            source_resolution=VALID["source_resolution"],
            observed_feature=VALID["observed_feature"],
            endogenic_alternative=VALID["endogenic_alternative"],
            independent_evidence=VALID["independent_evidence"],
            original_trace_available=False,
            terms_confirmed=True,
            intake_score=0.92,
            baseline_passed=True,
            status=CandidateSubmission.Status.BASELINE_PASSED,
        )
        self.job = CandidateAnalysisJob.objects.create(candidate=self.candidate)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": "Bearer worker-secret"}

    @override_settings(ANALYSIS_WORKER_TOKEN="worker-secret")
    def test_worker_can_list_and_claim_jobs(self):
        blocked = self.client.get(reverse("analysis_jobs"))
        self.assertEqual(blocked.status_code, 403)
        listed = self.client.get(reverse("analysis_jobs"), **self._auth())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["jobs"][0]["candidate"]["id"], str(self.candidate.id))
        claimed = self.client.post(
            reverse("analysis_job_claim", args=[self.job.id]),
            json.dumps({"worker_id": "local-ranker-1"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(claimed.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CandidateAnalysisJob.Status.CLAIMED)
        self.assertEqual(self.job.claimed_by, "local-ranker-1")
        self.assertEqual(self.job.attempt_count, 1)
        self.assertIsNotNone(self.job.lease_expires_at)

    @override_settings(ANALYSIS_WORKER_TOKEN="worker-secret")
    def test_worker_heartbeat_marks_job_running(self):
        self.job.status = CandidateAnalysisJob.Status.CLAIMED
        self.job.claimed_by = "local-ranker-1"
        self.job.save()
        response = self.client.post(
            reverse("analysis_job_heartbeat", args=[self.job.id]),
            json.dumps({"worker_id": "local-ranker-1"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CandidateAnalysisJob.Status.RUNNING)
        self.assertIsNotNone(self.job.lease_expires_at)

    @override_settings(ANALYSIS_WORKER_TOKEN="worker-secret")
    def test_worker_result_updates_candidate_and_records_artifacts(self):
        response = self.client.post(
            reverse("analysis_job_result", args=[self.job.id]),
            json.dumps({
                "status": "succeeded",
                "score": 0.812345,
                "score_percentile": 96.5,
                "review_tier": "high-priority",
                "method_version": "arc-ranker-local-2026.06",
                "worker_id": "local-ranker-1",
                "worker_version": "0.1.0",
                "runtime_seconds": 42.7,
                "metrics": {
                    "data_quality": 0.89,
                    "gravity_consensus_percentile": 93.2,
                    "magnetic_ring_score_stratified_percentile": 81.4,
                },
                "diagnostics": {"summary": "Strong annular signal in merged diagnostics."},
                "source_fingerprints": {"ranking_output": "sha256:abc"},
                "artifacts": [{
                    "kind": "elevation_diagnostic",
                    "title": "Elevation analysis diagnostic",
                    "mime_type": "image/webp",
                    "content_base64": base64.b64encode(b"RIFFtestWEBP").decode("ascii"),
                }],
            }),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()
        self.candidate.refresh_from_db()
        run = CandidateAnalysisRun.objects.get(candidate=self.candidate)
        artifact = CandidateAnalysisArtifact.objects.get(analysis_run=run)
        self.assertEqual(self.job.status, CandidateAnalysisJob.Status.SUCCEEDED)
        self.assertEqual(self.candidate.followup_status, CandidateSubmission.FollowupStatus.SCORED)
        self.assertEqual(self.candidate.followup_score, 0.812345)
        self.assertEqual(self.candidate.followup_method_version, "arc-ranker-local-2026.06")
        self.assertEqual(self.candidate.followup_metrics["score_percentile"], 96.5)
        self.assertIn("/api/analysis/artifacts/", self.candidate.followup_metrics["diagnostic_figure_url"])
        self.assertEqual(self.candidate.followup_metrics["diagnostics"]["summary"], "Strong annular signal in merged diagnostics.")
        self.assertEqual(run.worker_id, "local-ranker-1")
        self.assertEqual(artifact.kind, "elevation_diagnostic")
        self.assertEqual(artifact.storage_backend, "database")
        artifact_response = self.client.get(artifact.url_or_path)
        self.assertEqual(artifact_response.status_code, 200)
        self.assertEqual(artifact_response["Content-Type"], "image/webp")
        self.assertEqual(artifact_response.content, b"RIFFtestWEBP")
        self.client.force_login(self.user)
        feature = self.client.get(reverse("my_candidates_geojson")).json()["features"][0]
        self.assertIn("/api/analysis/artifacts/", feature["properties"]["diagnostic_figure_url"])
        self.assertIn("score_breakdown", feature["properties"])
        self.assertEqual(feature["properties"]["gravity_consensus_percentile"], 93.2)
        self.assertEqual(feature["properties"]["magnetic_ring_score_stratified_percentile"], 81.4)


class RasterProxyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("raster_reviewer", "raster@example.org", "long-test-password")

    def test_remote_sources_require_registration(self):
        response = self.client.get(reverse("raster_metadata"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    @patch("portal.raster._fetch_image")
    def test_public_aerial_basemap_tile_uses_allowlisted_esri_url(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"jpg", content_type="image/jpeg")
        response = self.client.get(reverse("raster_tile", args=["aerial", 2, 1, 1]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(fetch_image.call_args.args[0].startswith("https://server.arcgisonline.com/"))

    @patch("portal.raster._fetch_image")
    def test_public_dark_basemap_tile_uses_allowlisted_carto_url(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"png", content_type="image/png")
        response = self.client.get(reverse("raster_tile", args=["dark", 2, 1, 1]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(fetch_image.call_args.args[0].startswith("https://a.basemaps.cartocdn.com/"))

    @patch("portal.raster._fetch_image")
    def test_public_labels_overlay_uses_allowlisted_carto_url(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"png", content_type="image/png")
        response = self.client.get(reverse("raster_tile", args=["labels", 2, 1, 1]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("/light_only_labels/", fetch_image.call_args.args[0])

    def test_study_context_tiles_still_require_registration(self):
        response = self.client.get(reverse("raster_tile", args=["magnetic", 2, 1, 1]))
        self.assertEqual(response.status_code, 403)

    def test_registered_home_includes_remote_mapping_controls(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Esri aerial imagery")
        self.assertContains(response, "Dark map")
        self.assertContains(response, "GEBCO source identifier")
        self.assertContains(response, "Inspect WGM2012 gravity")
        self.assertContains(response, "Mark a candidate on the map")
        self.assertContains(response, "My candidate library")
        self.assertContains(response, "Other reviewers' candidates")
        self.assertContains(response, "Capture an observed arcuate trace")

    def test_metadata_exposes_no_upstream_proxy_urls(self):
        self.client.force_login(self.user)
        payload = self.client.get(reverse("raster_metadata")).json()
        self.assertIn("magnetic", payload["tiles"])
        self.assertIn("gravity-bouguer", payload["tiles"])
        self.assertNotIn("url", payload["tiles"]["magnetic"])
        self.assertIn("no server-side raster cache", payload["proxy_policy"])

    @patch("portal.raster._fetch_image")
    def test_magnetic_tile_uses_allowlisted_noaa_url(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"png", content_type="image/png")
        self.client.force_login(self.user)
        response = self.client.get(reverse("raster_tile", args=["magnetic", 2, 1, 1]))
        self.assertEqual(response.status_code, 200)
        upstream = fetch_image.call_args.args[0]
        self.assertTrue(upstream.startswith("https://tiles.arcgis.com/"))
        self.assertNotIn("http://", upstream)

    @patch("portal.raster._fetch_image")
    def test_gravity_tiles_use_allowlisted_gplates_endpoint(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"png", content_type="image/png")
        self.client.force_login(self.user)
        response = self.client.get(reverse("raster_tile", args=["gravity-bouguer", 2, 1, 1]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("portal.gplates.org/get_tile/", fetch_image.call_args.args[0])

    @patch("portal.raster._fetch_image")
    def test_gravity_tiles_accept_geographic_eastern_hemisphere_x_range(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"png", content_type="image/png")
        self.client.force_login(self.user)
        response = self.client.get(reverse("raster_tile", args=["gravity-bouguer", 2, 5, 1]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("x=5", fetch_image.call_args.args[0])

    @patch("portal.raster._fetch_image")
    def test_wms_overrides_user_layers_and_rejects_large_images(self, fetch_image):
        fetch_image.return_value = HttpResponse(b"png", content_type="image/png")
        self.client.force_login(self.user)
        ok = self.client.get(reverse("raster_wms", args=["gebco-elevation"]), {
            "bbox": "-1000000,-1000000,1000000,1000000", "width": "256", "height": "256",
            "layers": "untrusted", "srs": "EPSG:3857",
        })
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(fetch_image.call_args.kwargs["params"]["layers"], "gebco_latest")
        too_large = self.client.get(reverse("raster_wms", args=["gebco-elevation"]), {
            "bbox": "-1,-1,1,1", "width": "2048", "height": "2048",
        })
        self.assertEqual(too_large.status_code, 400)

    def test_invalid_or_future_satellite_dates_are_rejected(self):
        self.client.force_login(self.user)
        url = reverse("raster_tile", args=["satellite", 2, 1, 1])
        self.assertEqual(self.client.get(url, {"date": "not-a-date"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"date": "2999-01-01"}).status_code, 400)

    @patch("portal.raster.HTTP.get")
    def test_gravity_sample_returns_both_context_fields(self, requests_get):
        first, second = Mock(), Mock()
        first.text, second.text = "12.5", "-3.25"
        first.raise_for_status.return_value = second.raise_for_status.return_value = None
        requests_get.side_effect = [first, second]
        self.client.force_login(self.user)
        response = self.client.get(reverse("gravity_sample"), {"lon": "15", "lat": "-30"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["values_mgal"], {"bouguer": 12.5, "isostatic": -3.25})
