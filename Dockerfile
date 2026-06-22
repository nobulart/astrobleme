FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    ASTROBLEME_DATA_ROOT=/app

WORKDIR /app
COPY webapp/requirements.txt /app/webapp/requirements.txt
RUN pip install --no-cache-dir -r /app/webapp/requirements.txt
COPY webapp /app/webapp
COPY study_results_geojson /app/study_results_geojson
COPY catalog_repair/astroblemes_analysis.geojson /app/catalog_repair/astroblemes_analysis.geojson
COPY african_impact_structures.geojson /app/african_impact_structures.geojson
COPY data/controls.geojson /app/data/controls.geojson
COPY geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson /app/geology_sources/gem-global-active-faults/geojson/gem_active_faults_harmonized.geojson
RUN chmod +x /app/webapp/entrypoint.sh && cd /app/webapp && python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["/app/webapp/entrypoint.sh"]
