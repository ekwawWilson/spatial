import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone

from . import crypto
from .models import BasemapSource

GOOGLE_SESSION_URL = "https://tile.googleapis.com/v1/createSession"
GOOGLE_TILE_URL = "https://tile.googleapis.com/v1/2dtiles/{z}/{x}/{y}"


class OfflineCachingNotAllowed(Exception):
    """Raised when something tries to package tiles of a source whose terms
    don't allow offline use (enforced by the field packager, Phase 9)."""


def assert_offline_allowed(source: BasemapSource) -> None:
    if not source.offline_cache_allowed:
        raise OfflineCachingNotAllowed(
            f"{source.name}: its terms of use don't allow storing tiles for offline use."
        )


def api_key(source: BasemapSource) -> str:
    try:
        return crypto.decrypt(source.api_key_encrypted)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _google_session(source: BasemapSource, key: str) -> dict[str, Any]:
    """A Map Tiles API session (cached until shortly before it expires)."""
    cache_key = f"basemap-google-session:{source.pk}:{source.updated_at.timestamp()}"
    session: dict[str, Any] | None = cache.get(cache_key)
    if session:
        return session
    body = json.dumps({"mapType": source.layers or "roadmap", "language": "en-GB", "region": "GH"})
    request = urllib.request.Request(  # noqa: S310 - fixed https URL
        f"{GOOGLE_SESSION_URL}?{urllib.parse.urlencode({'key': key})}",
        data=body.encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            session = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.load(exc).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        raise ValidationError(
            f"Google rejected the API key for {source.name} (HTTP {exc.code}). {detail}".strip()
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValidationError(f"Couldn't reach Google to start a map session: {exc}") from exc
    assert session is not None
    expiry = int(session.get("expiry", 0))
    ttl = max(60, expiry - int(timezone.now().timestamp()) - 300) if expiry else 3600
    cache.set(cache_key, session, ttl)
    return session


def client_config(source: BasemapSource) -> dict[str, Any]:
    """What a browser needs to draw this basemap. Keys needed by the tile URLs
    are included (they're visible to the browser anyway); restrict them by
    site address in the provider's console."""
    config: dict[str, Any] = {
        "id": source.pk,
        "name": source.name,
        "kind": source.kind,
        "url": source.url,
        "layers": source.layers,
        "attribution": source.attribution,
        "min_zoom": source.min_zoom,
        "max_zoom": source.max_zoom,
    }
    key = api_key(source) if source.requires_key or source.api_key_encrypted else ""
    if source.requires_key and not key:
        raise ValidationError(
            f"{source.name} needs an API key. Ask an administrator to add one on the Basemaps page."
        )
    if source.kind == BasemapSource.Kind.GOOGLE:
        session = _google_session(source, key)
        query = urllib.parse.urlencode({"session": session["session"], "key": key})
        config["url"] = f"{GOOGLE_TILE_URL}?{query}"
        config["kind"] = "xyz"
    elif source.kind == BasemapSource.Kind.BING:
        config["key"] = key
    elif key:
        config["url"] = source.url.replace("{key}", urllib.parse.quote(key))
    return config
