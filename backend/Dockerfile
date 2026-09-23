# GDAL/OGR, GEOS and PROJ come from the official OSGeo image so GeoDjango and
# the import/export pipeline use one consistent, well-tested GIS stack.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv python3-dev build-essential libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# --system-site-packages exposes the image's GDAL Python bindings (osgeo) to the venv.
RUN python3 -m venv --system-site-packages $VIRTUAL_ENV

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
