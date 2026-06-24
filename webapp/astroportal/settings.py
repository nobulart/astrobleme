import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = Path(os.environ.get("ASTROBLEME_DATA_ROOT", BASE_DIR.parent))
GEBCO_GRID_PATH = os.environ.get("GEBCO_GRID_PATH", "/data/GEBCO_2026_sub_ice.nc")
GEOLOGY_INDEX_PATH = os.environ.get("GEOLOGY_INDEX_PATH", "/data/global_gprv.kml")
GEBCO_TID_GRID_PATH = os.environ.get("GEBCO_TID_GRID_PATH", "/Users/craig/ECDO/GIS/gebco_2026_tid/GEBCO_2026_TID.nc")
WGM2012_GRID_DIR = os.environ.get("WGM2012_GRID_DIR", "/Users/craig/ECDO/GIS/WGM2012")
EMAG2_CACHE_DIR = os.environ.get("EMAG2_CACHE_DIR", str(PROJECT_ROOT / "geophysical_cache" / "emag2"))
GEOPHYSICAL_REFERENCE_GEOJSON = os.environ.get("GEOPHYSICAL_REFERENCE_GEOJSON", str(PROJECT_ROOT / "study_results_geojson" / "arcuate_geometries_study_results.geojson"))
GEOPHYSICAL_ROI_FACTOR = float(os.environ.get("GEOPHYSICAL_ROI_FACTOR", "1.75"))
GEOPHYSICAL_MAX_PIXELS = int(os.environ.get("GEOPHYSICAL_MAX_PIXELS", "384"))
CESIUM_ION_TOKEN = os.environ.get("CESIUM_ION_TOKEN", "")
ANALYSIS_WORKER_TOKEN = os.environ.get("ANALYSIS_WORKER_TOKEN", "")
ANALYSIS_JOB_LEASE_SECONDS = int(os.environ.get("ANALYSIS_JOB_LEASE_SECONDS", "1800"))

SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-me")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,astro.nobulart.com,.railway.app,healthcheck.railway.app").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [u.strip() for u in os.environ.get("CSRF_TRUSTED_ORIGINS", "https://astro.nobulart.com").split(",") if u.strip()]
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
if RAILWAY_PUBLIC_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RAILWAY_PUBLIC_DOMAIN}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "astroportal.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "astroportal.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
