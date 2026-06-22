from django.urls import path

from . import raster, views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("submit/", views.submit_candidate, name="submit_candidate"),
    path("my-submissions/", views.my_submissions, name="my_submissions"),
    path("api/layers/<slug:slug>.geojson", views.layer_geojson, name="layer_geojson"),
    path("api/community.geojson", views.community_geojson, name="community_geojson"),
    path("api/raster/metadata.json", raster.metadata, name="raster_metadata"),
    path("api/raster/tiles/<slug:slug>/<int:z>/<int:x>/<int:y>", raster.tile, name="raster_tile"),
    path("api/raster/wms/<slug:slug>", raster.wms, name="raster_wms"),
    path("api/raster/gravity-sample", raster.gravity_sample, name="gravity_sample"),
    path("health/", views.health, name="health"),
]
