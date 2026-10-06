"""Offline basemap for a field package: an MBTiles file of a project's
planning area, built from a tile source whose terms allow offline use.

Tiles are fetched by the server from a URL a district administrator entered,
so the address is checked first: only http(s), and never a private, loopback
or link-local address (that would let the URL reach into the server's own
network).
"""

import ipaddress
import math
import socket
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from django.core.exceptions import ValidationError

from basemaps import services as basemap_services
from basemaps.models import BasemapSource

MAX_TILES = 20_000
TIMEOUT = 15
USER_AGENT = "spatial-field-packager/1"


def tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    """The XYZ tile holding a position (Web Mercator tiling)."""
    lat = max(min(lat, 85.0511), -85.0511)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_ranges(
    bbox: list[float], min_zoom: int, max_zoom: int
) -> list[tuple[int, int, int, int, int]]:
    """(zoom, x0, x1, y0, y1) covering a [west, south, east, north] box."""
    west, south, east, north = bbox
    ranges = []
    for zoom in range(min_zoom, max_zoom + 1):
        x0, y0 = tile_xy(west, north, zoom)
        x1, y1 = tile_xy(east, south, zoom)
        ranges.append((zoom, x0, x1, y0, y1))
    return ranges


def count_tiles(ranges: list[tuple[int, int, int, int, int]]) -> int:
    return sum((x1 - x0 + 1) * (y1 - y0 + 1) for _, x0, x1, y0, y1 in ranges)


def check_public_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValidationError("The basemap's address must start with http:// or https://.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationError(f"The basemap's server ({parts.hostname}) can't be found.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise ValidationError(
                "The basemap's address points inside a private network, so the server won't"
                " fetch it."
            )


def fetch_tile(url: str) -> bytes | None:
    """One tile's bytes; None when the source has no tile there."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - checked by check_public_url
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            data: bytes = response.read()
            return data
    except urllib.error.HTTPError as exc:
        if exc.code in (204, 404):
            return None
        raise ValidationError(f"The basemap's server answered HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValidationError(f"The basemap's server couldn't be reached: {exc}.") from exc


def local_tiles(source: BasemapSource) -> Callable[[int, int, int], bytes | None] | None:
    """A tile reader for a basemap backed by the district's own imagery on
    this server (rendered directly, no HTTP), or None for remote sources."""
    from imagery import raster
    from imagery.models import Imagery
    from imagery.services import cog_path

    imagery = Imagery.objects.filter(basemap=source, status=Imagery.Status.READY).first()
    if imagery is None or imagery.bounds is None:
        return None
    path, bounds, scale = cog_path(imagery), imagery.bounds, imagery.value_range

    def read(zoom: int, x: int, y: int) -> bytes | None:
        if not raster.tile_intersects(bounds, zoom, x, y):
            return None
        return raster.render_tile(path, zoom, x, y, scale=scale)

    return read


def _format(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def build(
    source: BasemapSource, bbox: list[float], max_zoom: int | None, target: Path
) -> dict[str, int]:
    """Writes the MBTiles file. Refuses sources that may not be stored offline."""
    basemap_services.assert_offline_allowed(source)
    if source.kind != BasemapSource.Kind.XYZ:
        raise ValidationError("Only XYZ tile basemaps can be packaged for offline use so far.")
    top = min(source.max_zoom, max_zoom if max_zoom is not None else source.max_zoom)
    if top < source.min_zoom:
        raise ValidationError(f"This basemap starts at zoom {source.min_zoom}.")
    ranges = tile_ranges(bbox, source.min_zoom, top)
    total = count_tiles(ranges)
    if total > MAX_TILES:
        raise ValidationError(
            f"That is {total:,} tiles; the limit is {MAX_TILES:,}. Choose a lower maximum zoom."
        )
    key = basemap_services.api_key(source) if source.api_key_encrypted else ""
    local = local_tiles(source)
    if local is None:
        check_public_url(source.url.replace("{z}", "0").replace("{x}", "0").replace("{y}", "0"))

    db = sqlite3.connect(target)
    try:
        db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        db.execute(
            "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER,"
            " tile_data BLOB)"
        )
        db.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
        stored = 0
        tile_format = "png"
        for zoom, x0, x1, y0, y1 in ranges:
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    url = (
                        source.url.replace("{z}", str(zoom))
                        .replace("{x}", str(x))
                        .replace("{y}", str(y))
                        .replace("{key}", urllib.parse.quote(key))
                    )
                    data = local(zoom, x, y) if local else fetch_tile(url)
                    if not data:
                        continue
                    if stored == 0:
                        tile_format = _format(data)
                    # MBTiles rows count from the south (TMS), XYZ from the north.
                    db.execute(
                        "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                        (zoom, x, (2**zoom - 1) - y, data),
                    )
                    stored += 1
        metadata = {
            "name": source.name,
            "format": tile_format,
            "type": "baselayer",
            "version": "1",
            "description": "Offline basemap for a field package",
            "attribution": source.attribution,
            "bounds": ",".join(str(v) for v in bbox),
            "minzoom": str(source.min_zoom),
            "maxzoom": str(top),
        }
        db.executemany("INSERT INTO metadata VALUES (?, ?)", list(metadata.items()))
        db.commit()
    finally:
        db.close()
    return {"tiles": stored, "requested": total, "min_zoom": source.min_zoom, "max_zoom": top}
