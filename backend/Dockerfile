# GDAL/OGR, GEOS and PROJ come from the official OSGeo image so GeoDjango and
# the import/export pipeline use one consistent, well-tested GIS stack.
# The "full" variant is needed: "small" lacks libkml, and the LIBKML driver is the
# only one that reads KML attributes (ExtendedData) back.
FROM ghcr.io/osgeo/gdal:ubuntu-full-3.10.3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Only stock Ubuntu packages are needed here. The base image also carries
# third-party apt sources (e.g. Apache Arrow); they are disabled for this step so
# an outage or expired key in one of them can't break our build.
RUN set -e; \
    mkdir /tmp/apt-extra; \
    find /etc/apt/sources.list.d -type f ! -name 'ubuntu.sources' -exec mv -t /tmp/apt-extra {} +; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3-venv postgresql-client; \
    rm -rf /var/lib/apt/lists/*; \
    find /tmp/apt-extra -type f -exec mv -t /etc/apt/sources.list.d {} +; \
    rmdir /tmp/apt-extra

# --system-site-packages exposes the image's GDAL Python bindings (osgeo) to the venv.
RUN python3 -m venv --system-site-packages $VIRTUAL_ENV

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
