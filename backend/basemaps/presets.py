"""Ready-made basemap definitions. None allows offline caching: OpenStreetMap's
tile policy and the Google, Esri and Bing terms all forbid bulk or offline use
of their tiles without a separate agreement."""

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "osm": {
        "name": "OpenStreetMap",
        "kind": "xyz",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
        "max_zoom": 19,
        "requires_key": False,
        "notes": "Free for light interactive use. The OSM tile policy forbids bulk and offline downloading.",
    },
    "esri_imagery": {
        "name": "Esri World Imagery",
        "kind": "xyz",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Tiles © Esri: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        "max_zoom": 19,
        "requires_key": False,
        "notes": "Esri terms of use apply. Offline use needs an Esri licence.",
    },
    "google_roadmap": {
        "name": "Google Maps (roadmap)",
        "kind": "google",
        "layers": "roadmap",
        "attribution": "Map data © Google",
        "max_zoom": 22,
        "requires_key": True,
        "notes": "Google Map Tiles API. Needs an API key from Google Cloud; restrict it to this site's "
        "address. Google's terms forbid caching tiles for offline use.",
    },
    "google_satellite": {
        "name": "Google Maps (satellite)",
        "kind": "google",
        "layers": "satellite",
        "attribution": "Imagery © Google",
        "max_zoom": 22,
        "requires_key": True,
        "notes": "Google Map Tiles API. Needs an API key from Google Cloud; restrict it to this site's "
        "address. Google's terms forbid caching tiles for offline use.",
    },
    "bing_aerial": {
        "name": "Bing Maps (aerial)",
        "kind": "bing",
        "layers": "Aerial",
        "attribution": "© Microsoft",
        "max_zoom": 19,
        "requires_key": True,
        "notes": "Deprecated: Bing Maps for Enterprise is being retired and free keys have ended. "
        "Prefer another source.",
    },
}
