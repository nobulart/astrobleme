# Astrobleme Review Atlas

The `webapp/` directory contains a Railway-ready Django application for exploring the study datasets and accepting registered-user candidate submissions. The production hostname is `astro.nobulart.com`.

## Scientific boundary

The portal keeps two concepts separate:

- `followup_score` is the manuscript's uncalibrated study review-priority score. It is not an impact probability.
- New submissions receive `followup_score` from the same numerical GEBCO/topography and geological-independence method when the required scientific files are mounted.
- `intake_score` separately measures whether a community submission is complete and reviewable.

Baseline-passing community records are labelled **unreviewed**. Only moderators can promote them into the review catalogue. Confirmation still requires accepted geological evidence.

## Local run

```bash
python3 -m venv .venv-app
source .venv-app/bin/activate
pip install -r webapp/requirements.txt
cd webapp
DEBUG=true python manage.py migrate
DEBUG=true python manage.py createsuperuser
GEBCO_GRID_PATH=/path/to/GEBCO_2026_sub_ice.nc \
GEOLOGY_INDEX_PATH=/path/to/global_gprv.kml \
DEBUG=true python manage.py runserver
```

The app reads study layers from the repository root by default. Set `ASTROBLEME_DATA_ROOT` if the app and data are separated.

## Remote geospatial services

Registered users can compare study vectors against remote raster context without storing those rasters in Railway:

| Tool | Provider | Delivery |
| --- | --- | --- |
| Aerial imagery | Esri World Imagery | Allowlisted XYZ proxy |
| Dated satellite imagery | NASA EOSDIS GIBS MODIS Terra | Allowlisted WMTS tile proxy |
| Elevation/bathymetry | GEBCO latest grid | Restricted WMS proxy |
| Bathymetric source quality | GEBCO Type Identifier grid | Restricted WMS proxy |
| Magnetic anomaly | NOAA NCEI EMAG2v3 | Allowlisted ArcGIS tile proxy |
| Bouguer and isostatic gravity | WGM2012 via EarthByte/GPlates | Click-to-query proxy plus native geographic tiles in the Cesium globe |

The proxy accepts only named providers and validated tile/WMS parameters. It does not accept arbitrary URLs and has no server-side raster cache. Provider attribution remains visible on the map. Remote layers are contextual screening evidence, not impact confirmation.

## Railway deployment

1. Create a Railway project from this repository.
2. Add a PostgreSQL service. Railway supplies `DATABASE_URL` to the app service when linked.
3. Set `SECRET_KEY` to a long random value. The container refuses to start without it.
4. Confirm the linked PostgreSQL service exposes `DATABASE_URL`. The container refuses to start without it.
5. `astro.nobulart.com`, Railway hostnames and `healthcheck.railway.app` are included in the application defaults. If overriding `ALLOWED_HOSTS`, retain all three.
6. `https://astro.nobulart.com` is included in the CSRF defaults. If overriding `CSRF_TRUSTED_ORIGINS`, retain that full origin.
7. Deploy. The Docker entrypoint applies migrations and starts Gunicorn on Railway's injected `PORT`.
8. Create the first moderator account with Railway's service shell: `cd webapp && python manage.py createsuperuser`.
9. In the web service's Public Networking settings, add `astro.nobulart.com`. Add both the CNAME and TXT records Railway provides to the `nobulart.com` DNS zone; Railway will issue TLS after verification.
10. Keep the configured health check at `/health/`. It verifies both Django and the database and accepts Railway's `healthcheck.railway.app` hostname.

### Exact follow-up scoring data

The visual GEBCO WMS is not a numerical scoring input. To calculate the manuscript score immediately in production, attach a Railway persistent volume at `/data` and place these read-only files on it:

- `/data/GEBCO_2026_sub_ice.nc` — the GEBCO 2026 sub-ice numerical grid;
- `/data/global_gprv.kml` — the geological-province index used by the study.

The application opens only the candidate-sized GEBCO window and never copies the grid into PostgreSQL. If either file is absent, submission still succeeds, but the record is explicitly marked `source_unavailable` for a later retry; no map-image surrogate is used. The large GEBCO grid should remain on a volume or future range-readable scientific data service, not in Git or the Docker image.

Optional variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_CONCURRENCY` | `2` | Gunicorn workers |
| `WEB_THREADS` | `4` | Threads per worker for concurrent remote raster requests |
| `DEBUG` | `false` | Development diagnostics; keep false in production |
| `ASTROBLEME_DATA_ROOT` | `/app` | Root containing the GeoJSON study outputs |
| `RAILWAY_PUBLIC_DOMAIN` | supplied by Railway | Automatically added to allowed hosts and trusted HTTPS origins |
| `GEBCO_GRID_PATH` | `/data/GEBCO_2026_sub_ice.nc` | Numerical terrain grid required for exact follow-up scoring |
| `GEOLOGY_INDEX_PATH` | `/data/global_gprv.kml` | Geological-province index required for exact follow-up scoring |
| `CESIUM_ION_TOKEN` | empty | Optional Cesium World Terrain; WGM2012 gravity and the ellipsoid globe work without it |

Required variables are `SECRET_KEY` and `DATABASE_URL`. `PORT` and `RAILWAY_PUBLIC_DOMAIN` are supplied by Railway.

If Cloudflare proxies `astro.nobulart.com`, Railway currently requires Cloudflare SSL/TLS mode **Full**. Use the exact CNAME and TXT records shown in Railway and wait for domain verification before testing HTTPS.

## Data lifecycle

Study files remain immutable application inputs and are served as named read-only layers. Community submissions live in PostgreSQL. Promotion does not rewrite `study_results_geojson`; a future curated export should preserve contributor, moderation, source, score-version and review-history provenance.

The Docker image copies only the files required by the application, excluding manuscript PDFs, caches and large analytical source files. For higher traffic, move the 15 MB study GeoJSON and active-fault layer to object storage, PostGIS or vector tiles. The current raster services already remain remote and are streamed on demand.
