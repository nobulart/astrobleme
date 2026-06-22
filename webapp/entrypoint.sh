#!/bin/sh
set -eu

: "${SECRET_KEY:?SECRET_KEY must be set in Railway}"
: "${DATABASE_URL:?DATABASE_URL must be supplied by the linked Railway PostgreSQL service}"

python manage.py migrate --noinput
exec gunicorn astroportal.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --worker-class gthread --workers "${WEB_CONCURRENCY:-2}" --threads "${WEB_THREADS:-4}" --timeout 120
