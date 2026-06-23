"""Allowlisted, non-caching proxies for remote study-context map services."""

from __future__ import annotations

import datetime as dt
import math
import re
import requests
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

MAX_RASTER_BYTES = 8 * 1024 * 1024
TIMEOUT = (4, 20)
HTTP = requests.Session()
HTTP.mount("https://", requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=32, max_retries=1))

TILE_SOURCES = {
    "aerial": {
        "label": "Esri World Imagery",
        "kind": "imagery",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 18,
        "attribution": "Esri, Maxar, Earthstar Geographics and contributors",
        "source_url": "https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9",
    },
    "dark": {
        "label": "CARTO Dark Matter basemap",
        "kind": "basemap",
        "url": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "max_zoom": 18,
        "attribution": "© OpenStreetMap contributors, © CARTO",
        "source_url": "https://carto.com/basemaps/",
    },
    "labels": {
        "label": "CARTO labels and roads overlay",
        "kind": "basemap-overlay",
        "url": "https://a.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}.png",
        "max_zoom": 18,
        "attribution": "© OpenStreetMap contributors, © CARTO",
        "source_url": "https://carto.com/basemaps/",
    },
    "magnetic": {
        "label": "NOAA EMAG2v3 magnetic anomaly",
        "kind": "geophysics",
        "url": "https://tiles.arcgis.com/tiles/C8EMgrsFcRFL6LrL/arcgis/rest/services/EMAG2v3_color_relief_webmercator/MapServer/tile/{z}/{y}/{x}",
        "max_zoom": 8,
        "attribution": "NOAA National Centers for Environmental Information",
        "source_url": "https://www.ncei.noaa.gov/products/earth-magnetic-model-anomaly-grid-2",
    },
    "satellite": {
        "label": "NASA MODIS Terra corrected reflectance",
        "kind": "imagery",
        "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
        "max_zoom": 9,
        "attribution": "NASA EOSDIS GIBS",
        "source_url": "https://nasa-gibs.github.io/gibs-api-docs/",
        "dated": True,
    },
    "gravity-bouguer": {
        "label": "WGM2012 Bouguer gravity",
        "kind": "geophysics-geographic-tiles",
        "url": "https://portal.gplates.org/get_tile/?name=WGM2012_Bouguer_ponc&z={z}&x={x}&y={y}&fmt=png",
        "max_zoom": 6,
        "attribution": "BGI and EarthByte/GPlates",
        "source_url": "https://www.earthbyte.org/interactive-virtual-gravity-globe-based-on-bgis-global-gravity-grids-by-bonvalot-et-al-2012/",
    },
    "gravity-isostatic": {
        "label": "WGM2012 isostatic gravity",
        "kind": "geophysics-geographic-tiles",
        "url": "https://portal.gplates.org/get_tile/?name=WGM2012_Isostatic_ponc&z={z}&x={x}&y={y}&fmt=png",
        "max_zoom": 6,
        "attribution": "BGI and EarthByte/GPlates",
        "source_url": "https://www.earthbyte.org/interactive-virtual-gravity-globe-based-on-bgis-global-gravity-grids-by-bonvalot-et-al-2012/",
    },
}

WMS_SOURCES = {
    "gebco-elevation": {
        "label": "GEBCO latest shaded elevation/bathymetry",
        "url": "https://wms.gebco.net/mapserv",
        "layer": "gebco_latest",
        "attribution": "GEBCO Compilation Group",
        "source_url": "https://www.gebco.net/data-products/gebco-web-services/web-map-service",
    },
    "gebco-tid": {
        "label": "GEBCO Type Identifier grid",
        "url": "https://wms.gebco.net/mapserv",
        "layer": "gebco_latest_tid",
        "attribution": "GEBCO Compilation Group",
        "source_url": "https://www.gebco.net/data-products/gebco-web-services/web-map-service",
    },
}


def _no_store(response: HttpResponse, *, browser_seconds: int = 1800) -> HttpResponse:
    # Railway never stores upstream payloads; a short browser cache limits provider load.
    response["Cache-Control"] = f"private, max-age={browser_seconds}, stale-if-error=86400"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Astrobleme-Proxy"] = "allowlisted-no-server-cache"
    return response


def _fetch_image(url: str, params: dict | None = None) -> HttpResponse:
    try:
        upstream = HTTP.get(url, params=params, timeout=TIMEOUT, stream=True, headers={"User-Agent": "AstroblemeReviewAtlas/1.0"})
        upstream.raise_for_status()
        content_type = upstream.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type not in {"image/png", "image/jpeg", "image/webp"}:
            return JsonResponse({"error": "Remote map service returned a non-image response."}, status=502)
        payload = bytearray()
        for chunk in upstream.iter_content(64 * 1024):
            payload.extend(chunk)
            if len(payload) > MAX_RASTER_BYTES:
                return JsonResponse({"error": "Remote map response exceeded the safety limit."}, status=502)
        return _no_store(HttpResponse(bytes(payload), content_type=content_type))
    except requests.RequestException:
        return JsonResponse({"error": "Remote map service is temporarily unavailable."}, status=502)


def _tile_coordinates(z: int, x: int, y: int, source: dict) -> bool:
    if not 0 <= z <= source["max_zoom"]:
        return False
    width = 2 ** (z + 1) if source.get("kind") == "geophysics-geographic-tiles" else 2**z
    return 0 <= x < width and 0 <= y < 2**z


@require_GET
def tile(request, slug: str, z: int, x: int, y: int):
    source = TILE_SOURCES.get(slug)
    if not source or not _tile_coordinates(z, x, y, source):
        raise Http404
    if slug not in {"aerial", "satellite", "dark", "labels"} and not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication is required for study context overlays."}, status=403)
    values = {"z": z, "x": x, "y": y}
    if source.get("dated"):
        raw_date = request.GET.get("date", "")
        try:
            selected = dt.date.fromisoformat(raw_date)
        except ValueError:
            return JsonResponse({"error": "A valid ISO imagery date is required."}, status=400)
        if selected > dt.date.today() or selected < dt.date(2000, 2, 24):
            return JsonResponse({"error": "Imagery date is outside the supported MODIS record."}, status=400)
        values["date"] = selected.isoformat()
    return _fetch_image(source["url"].format(**values))


def _valid_bbox(value: str) -> bool:
    try:
        coords = [float(v) for v in value.split(",")]
    except ValueError:
        return False
    return len(coords) == 4 and all(math.isfinite(v) and abs(v) <= 30_000_000 for v in coords)


@login_required
@require_GET
def wms(request, slug: str):
    source = WMS_SOURCES.get(slug)
    if not source:
        raise Http404
    bbox = request.GET.get("bbox", "")
    if not _valid_bbox(bbox):
        return JsonResponse({"error": "Invalid WMS bounding box."}, status=400)
    try:
        width, height = int(request.GET.get("width", 256)), int(request.GET.get("height", 256))
    except ValueError:
        return JsonResponse({"error": "Invalid WMS image dimensions."}, status=400)
    if not (1 <= width <= 512 and 1 <= height <= 512):
        return JsonResponse({"error": "WMS image dimensions exceed the safety limit."}, status=400)
    crs = request.GET.get("srs") or request.GET.get("crs") or "EPSG:3857"
    if crs.upper() not in {"EPSG:3857", "EPSG:4326"}:
        return JsonResponse({"error": "Unsupported WMS coordinate reference system."}, status=400)
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetMap",
        "layers": source["layer"], "styles": "", "format": "image/png",
        "transparent": "true", "srs": crs.upper(), "bbox": bbox,
        "width": width, "height": height,
    }
    return _fetch_image(source["url"], params=params)


@login_required
@require_GET
def gravity_sample(request):
    try:
        lon, lat = float(request.GET["lon"]), float(request.GET["lat"])
    except (KeyError, ValueError):
        return JsonResponse({"error": "Valid longitude and latitude are required."}, status=400)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return JsonResponse({"error": "Coordinates are outside WGS84 bounds."}, status=400)
    results = {}
    for key, raster_name in {
        "bouguer": "WGM2012_Bouguer_ponc",
        "isostatic": "WGM2012_Isostatic_ponc",
    }.items():
        try:
            upstream = HTTP.get(
                "https://gws.gplates.org/raster/query",
                params={"lon": f"{lon:.5f}", "lat": f"{lat:.5f}", "raster_name": raster_name},
                timeout=TIMEOUT,
                headers={"User-Agent": "AstroblemeReviewAtlas/1.0"},
            )
            upstream.raise_for_status()
            raw = upstream.text.strip()
            results[key] = float(raw) if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", raw) else raw[:80]
        except (requests.RequestException, ValueError):
            results[key] = None
    response = JsonResponse({
        "longitude": lon, "latitude": lat, "values_mgal": results,
        "source": "WGM2012 via EarthByte/GPlates Web Service",
        "source_url": "https://www.earthbyte.org/interactive-virtual-gravity-globe-based-on-bgis-global-gravity-grids-by-bonvalot-et-al-2012/",
        "interpretation": "Context only; gravity anomalies are non-diagnostic and require candidate-specific modelling.",
    })
    response["Cache-Control"] = "private, max-age=300"
    return response


@login_required
@require_GET
def metadata(request):
    return JsonResponse({
        "tiles": {slug: {k: v for k, v in source.items() if k not in {"url"}} for slug, source in TILE_SOURCES.items()},
        "wms": {slug: {k: v for k, v in source.items() if k not in {"url", "layer"}} for slug, source in WMS_SOURCES.items()},
        "gravity": {
            "label": "WGM2012 gravity point inspector", "attribution": "BGI and EarthByte/GPlates",
            "source_url": "https://www.earthbyte.org/interactive-virtual-gravity-globe-based-on-bgis-global-gravity-grids-by-bonvalot-et-al-2012/",
        },
        "proxy_policy": "Allowlisted pass-through; no server-side raster cache or arbitrary upstream URLs.",
    })
