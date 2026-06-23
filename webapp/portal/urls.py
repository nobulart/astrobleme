from django.urls import path

from . import analysis_api, raster, views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("submit/", views.submit_candidate, name="submit_candidate"),
    path("my-submissions/<uuid:candidate_id>/edit/", views.edit_candidate, name="edit_candidate"),
    path("my-submissions/", views.my_submissions, name="my_submissions"),
    path("help/", views.help_page, name="help"),
    path("globe/", views.globe, name="globe"),
    path("review/", views.review_queue, name="review_queue"),
    path("review/<uuid:candidate_id>/", views.review_candidate, name="review_candidate"),
    path("api/layers/<slug:slug>.geojson", views.layer_geojson, name="layer_geojson"),
    path("api/community.geojson", views.community_geojson, name="community_geojson"),
    path("api/my-candidates.geojson", views.my_candidates_geojson, name="my_candidates_geojson"),
    path("api/other-candidates.geojson", views.other_candidates_geojson, name="other_candidates_geojson"),
    path("api/map-preferences", views.map_preferences, name="map_preferences"),
    path("api/analysis/status", views.analysis_status, name="analysis_status"),
    path("api/analysis/jobs", analysis_api.list_jobs, name="analysis_jobs"),
    path("api/analysis/jobs/<uuid:job_id>/claim", analysis_api.claim_job, name="analysis_job_claim"),
    path("api/analysis/jobs/<uuid:job_id>/heartbeat", analysis_api.heartbeat_job, name="analysis_job_heartbeat"),
    path("api/analysis/jobs/<uuid:job_id>/result", analysis_api.submit_result, name="analysis_job_result"),
    path("api/analysis/artifacts/<uuid:artifact_id>", views.analysis_artifact, name="analysis_artifact"),
    path("api/raster/metadata.json", raster.metadata, name="raster_metadata"),
    path("api/raster/tiles/<slug:slug>/<int:z>/<int:x>/<int:y>", raster.tile, name="raster_tile"),
    path("api/raster/wms/<slug:slug>", raster.wms, name="raster_wms"),
    path("api/raster/gravity-sample", raster.gravity_sample, name="gravity_sample"),
    path("health/", views.health, name="health"),
]
