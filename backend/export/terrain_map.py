"""
DC Feasibility Tool v4 — Map & Terrain Image Generator
=======================================================
Generates map imagery for data center site reports using
tile-based maps via the ``staticmap`` library.

Tile sources (all free, no API key required):
- OpenTopoMap (terrain/elevation)
- OpenStreetMap (street-level detail)
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import staticmap  # type: ignore[import-untyped]

    _HAS_STATICMAP = True
except ImportError:
    _HAS_STATICMAP = False


OPENTOPOMAP_URL = "https://tile.opentopomap.org/{z}/{x}/{y}.png"
OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def _to_base64(png_bytes: bytes | None) -> str | None:
    if png_bytes is None:
        return None
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Terrain map (existing)
# ---------------------------------------------------------------------------

def generate_terrain_image(
    lat: float,
    lon: float,
    zoom: int = 13,
    width: int = 800,
    height: int = 500,
) -> Optional[bytes]:
    """Return a PNG terrain image centred on (lat, lon), or None if staticmap is unavailable."""
    if not _HAS_STATICMAP:
        logger.warning("staticmap not installed — terrain images disabled")
        return None

    try:
        m = staticmap.StaticMap(width, height, url_template=OPENTOPOMAP_URL)
        marker = staticmap.CircleMarker((lon, lat), "red", 8)
        m.add_marker(marker)
        image = m.render(zoom=zoom)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        logger.exception("Failed to generate terrain image for (%.4f, %.4f)", lat, lon)
        return None


def generate_terrain_base64(
    lat: float,
    lon: float,
    zoom: int = 13,
    width: int = 800,
    height: int = 500,
) -> Optional[str]:
    """Return a base64-encoded PNG data URI for HTML embedding, or None."""
    return _to_base64(generate_terrain_image(lat, lon, zoom, width, height))


# ---------------------------------------------------------------------------
# Site location map (OSM street-level)
# ---------------------------------------------------------------------------

def generate_site_location_image(
    lat: float,
    lon: float,
    zoom: int = 14,
    width: int = 800,
    height: int = 400,
) -> Optional[bytes]:
    """Return a PNG street map centred on the site location."""
    if not _HAS_STATICMAP:
        return None

    try:
        m = staticmap.StaticMap(width, height, url_template=OSM_URL)
        # Outer ring
        m.add_marker(staticmap.CircleMarker((lon, lat), "#1a365d", 14))
        # Inner dot (white center)
        m.add_marker(staticmap.CircleMarker((lon, lat), "white", 7))
        # Core dot
        m.add_marker(staticmap.CircleMarker((lon, lat), "#2b6cb0", 5))
        image = m.render(zoom=zoom)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        logger.exception("Failed to generate site location map for (%.4f, %.4f)", lat, lon)
        return None


def generate_site_location_base64(
    lat: float,
    lon: float,
    zoom: int = 14,
    width: int = 800,
    height: int = 400,
) -> Optional[str]:
    """Return a base64-encoded site location map for HTML embedding."""
    return _to_base64(generate_site_location_image(lat, lon, zoom, width, height))


# ---------------------------------------------------------------------------
# Country overview map (zoomed-out showing site location in context)
# ---------------------------------------------------------------------------

def generate_country_overview_image(
    lat: float,
    lon: float,
    zoom: int = 6,
    width: int = 400,
    height: int = 400,
) -> Optional[bytes]:
    """Return a PNG country-level overview map showing the site location marker."""
    if not _HAS_STATICMAP:
        return None

    try:
        m = staticmap.StaticMap(width, height, url_template=OSM_URL)
        # Large marker visible at country zoom
        m.add_marker(staticmap.CircleMarker((lon, lat), "#dc2626", 12))
        m.add_marker(staticmap.CircleMarker((lon, lat), "white", 6))
        m.add_marker(staticmap.CircleMarker((lon, lat), "#dc2626", 4))
        image = m.render(zoom=zoom)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        logger.exception(
            "Failed to generate country overview map for (%.4f, %.4f)", lat, lon
        )
        return None


def generate_country_overview_base64(
    lat: float,
    lon: float,
    zoom: int = 6,
    width: int = 400,
    height: int = 400,
) -> Optional[str]:
    """Return a base64-encoded country overview map for HTML embedding."""
    return _to_base64(generate_country_overview_image(lat, lon, zoom, width, height))


# ---------------------------------------------------------------------------
# Grid context map (OSM with infrastructure markers)
# ---------------------------------------------------------------------------

def generate_grid_context_image(
    lat: float,
    lon: float,
    assets: list[dict[str, Any]] | None = None,
    radius_km: float | None = None,
    zoom: int = 12,
    width: int = 800,
    height: int = 450,
) -> Optional[bytes]:
    """Return a PNG map showing the site and nearby grid infrastructure assets."""
    if not _HAS_STATICMAP:
        return None

    try:
        m = staticmap.StaticMap(width, height, url_template=OSM_URL)

        # Add power line assets as lines or point markers
        for asset in (assets or []):
            coords = asset.get("coordinates") or []
            if not coords:
                continue

            asset_type = asset.get("asset_type", "")
            voltage_kv = asset.get("voltage_kv")

            # Color by voltage
            if voltage_kv is not None and voltage_kv >= 220:
                color = "#dc2626"  # red for HV
            elif voltage_kv is not None and voltage_kv >= 110:
                color = "#ea580c"  # orange for MV
            else:
                color = "#2563eb"  # blue for others

            valid_points = [
                (float(c[1]), float(c[0]))  # (lon, lat) for staticmap
                for c in coords
                if len(c) >= 2 and c[0] is not None and c[1] is not None
            ]

            if not valid_points:
                continue

            geom_type = asset.get("geometry_type", "")
            if (geom_type == "line" or len(valid_points) > 1) and len(valid_points) >= 2:
                line = staticmap.Line(valid_points, color, 3)
                m.add_line(line)
            else:
                # Point marker for substations or single-point assets
                lon_a, lat_a = valid_points[0]
                marker_size = 10 if asset_type == "substation" else 7
                m.add_marker(staticmap.CircleMarker((lon_a, lat_a), color, marker_size))

        # Site marker on top (prominent)
        m.add_marker(staticmap.CircleMarker((lon, lat), "#1a365d", 16))
        m.add_marker(staticmap.CircleMarker((lon, lat), "white", 9))
        m.add_marker(staticmap.CircleMarker((lon, lat), "#1a365d", 6))

        image = m.render(zoom=zoom)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        logger.exception(
            "Failed to generate grid context map for (%.4f, %.4f)", lat, lon
        )
        return None


def generate_grid_context_base64(
    lat: float,
    lon: float,
    assets: list[dict[str, Any]] | None = None,
    radius_km: float | None = None,
    zoom: int = 12,
    width: int = 800,
    height: int = 450,
) -> Optional[str]:
    """Return a base64-encoded grid context map for HTML embedding."""
    return _to_base64(
        generate_grid_context_image(lat, lon, assets, radius_km, zoom, width, height)
    )
