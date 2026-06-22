from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.http import HttpResponse
from unittest.mock import Mock, patch

from .models import CandidateSubmission
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
    @override_settings(PROJECT_ROOT="/path/that/does/not/exist")
    def test_complete_submission_passes(self):
        from .scoring import study_centres
        study_centres.cache_clear()
        score, passed, checks = evaluate_submission(VALID)
        self.assertTrue(passed)
        self.assertGreaterEqual(score, 0.55)
        self.assertIn("scientific_note", checks)

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist")
    def test_short_undocumented_submission_fails(self):
        from .scoring import study_centres
        study_centres.cache_clear()
        data = VALID | {"description": "A circle.", "source_title": "", "endogenic_alternative": "unknown"}
        score, passed, checks = evaluate_submission(data)
        self.assertFalse(passed)
        self.assertFalse(checks["description_complete"])


class PortalViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reviewer", "reviewer@example.org", "long-test-password")

    def test_home_and_health_are_public(self):
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Registered reviewers can compare live aerial")
        self.assertEqual(self.client.get(reverse("health")).json(), {"status": "ok", "database": "ok"})

    def test_submission_requires_login(self):
        response = self.client.get(reverse("submit_candidate"))
        self.assertEqual(response.status_code, 302)

    def test_community_api_excludes_failed_records(self):
        CandidateSubmission.objects.create(
            created_by=self.user, title="Private failed item", description="x", longitude=1, latitude=1,
            diameter_km=5, source_title="x", observed_feature="x", endogenic_alternative="x",
            status=CandidateSubmission.Status.BASELINE_FAILED,
        )
        self.assertEqual(self.client.get(reverse("community_geojson")).json()["features"], [])

    @override_settings(PROJECT_ROOT="/path/that/does/not/exist")
    def test_authenticated_submission_is_scored_and_published(self):
        from .scoring import study_centres
        study_centres.cache_clear()
        self.client.force_login(self.user)
        response = self.client.post(reverse("submit_candidate"), VALID)
        self.assertRedirects(response, reverse("my_submissions"))
        item = CandidateSubmission.objects.get(title=VALID["title"])
        self.assertTrue(item.baseline_passed)
        self.assertEqual(item.status, CandidateSubmission.Status.BASELINE_PASSED)
        public = self.client.get(reverse("community_geojson")).json()
        self.assertEqual(len(public["features"]), 1)


class RasterProxyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("raster_reviewer", "raster@example.org", "long-test-password")

    def test_remote_sources_require_registration(self):
        response = self.client.get(reverse("raster_metadata"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_registered_home_includes_remote_mapping_controls(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Esri aerial imagery")
        self.assertContains(response, "GEBCO source identifier")
        self.assertContains(response, "Inspect WGM2012 gravity")

    def test_metadata_exposes_no_upstream_proxy_urls(self):
        self.client.force_login(self.user)
        payload = self.client.get(reverse("raster_metadata")).json()
        self.assertIn("magnetic", payload["tiles"])
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
