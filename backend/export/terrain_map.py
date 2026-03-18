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

def _voltage_color(voltage_kv: float | None) -> str:
    """Return a colour matching the frontend's voltage colour scheme."""
    if voltage_kv is None:
        return "#6b7280"  # gray for unknown
    if voltage_kv >= 300:
        return "#dc2626"  # red
    if voltage_kv >= 220:
        return "#ea580c"  # orange-red
    if voltage_kv >= 110:
        return "#f59e0b"  # amber
    if voltage_kv >= 36:
        return "#2563eb"  # blue
    return "#6b7280"  # gray


def _radius_circle_points(
    center_lat: float, center_lon: float, radius_km: float, n_points: int = 72
) -> list[tuple[float, float]]:
    """Return (lon, lat) points forming a circle for staticmap."""
    import math
    points = []
    for i in range(n_points + 1):
        angle = 2 * math.pi * i / n_points
        lat_delta = radius_km / 110.574
        lon_delta = radius_km / (111.32 * max(math.cos(math.radians(center_lat)), 0.01))
        pt_lat = center_lat + lat_delta * math.sin(angle)
        pt_lon = center_lon + lon_delta * math.cos(angle)
        points.append((pt_lon, pt_lat))
    return points


def _auto_zoom_for_radius(radius_km: float) -> int:
    """Pick a zoom level that comfortably fits the radius circle."""
    if radius_km <= 2:
        return 14
    if radius_km <= 5:
        return 12
    if radius_km <= 10:
        return 11
    if radius_km <= 20:
        return 10
    if radius_km <= 50:
        return 9
    return 8


def generate_grid_context_image(
    lat: float,
    lon: float,
    assets: list[dict[str, Any]] | None = None,
    radius_km: float | None = None,
    zoom: int | None = None,
    width: int = 800,
    height: int = 500,
) -> Optional[bytes]:
    """Return a PNG map showing the site, radius circle, and ALL grid infrastructure."""
    if not _HAS_STATICMAP:
        return None

    try:
        m = staticmap.StaticMap(width, height, url_template=OSM_URL)

        # Auto-pick zoom based on radius
        effective_zoom = zoom or (
            _auto_zoom_for_radius(radius_km) if radius_km else 12
        )

        # Draw radius circle (dashed border approximated by closely spaced line)
        if radius_km and radius_km > 0:
            circle_pts = _radius_circle_points(lat, lon, radius_km)
            circle_line = staticmap.Line(circle_pts, "#1d4ed8", 2)
            m.add_line(circle_line)

        # Draw ALL infrastructure assets
        for asset in (assets or []):
            coords = asset.get("coordinates") or []
            if not coords:
                continue

            asset_type = asset.get("asset_type", "")
            voltage_kv = asset.get("voltage_kv")
            color = _voltage_color(voltage_kv)

            valid_points = [
                (float(c[1]), float(c[0]))  # (lon, lat) for staticmap
                for c in coords
                if len(c) >= 2 and c[0] is not None and c[1] is not None
            ]

            if not valid_points:
                continue

            geom_type = asset.get("geometry_type", "")

            if geom_type == "polygon" and len(valid_points) >= 3:
                # Close the polygon and draw as a line outline
                closed = valid_points + [valid_points[0]]
                m.add_line(staticmap.Line(closed, color, 2))
            elif (geom_type == "line" or len(valid_points) > 1) and len(valid_points) >= 2:
                line_width = 4 if asset_type == "line" else 2
                m.add_line(staticmap.Line(valid_points, color, line_width))

            # Always add point markers for substations, or for point assets
            if asset_type == "substation" or geom_type == "point":
                lon_a, lat_a = valid_points[0]
                marker_size = 12 if asset_type == "substation" else 7
                m.add_marker(staticmap.CircleMarker((lon_a, lat_a), color, marker_size))
                if asset_type == "substation":
                    # White inner ring for substations (like frontend)
                    m.add_marker(staticmap.CircleMarker((lon_a, lat_a), "white", 6))
                    m.add_marker(staticmap.CircleMarker((lon_a, lat_a), color, 4))

        # Site marker on top (prominent)
        m.add_marker(staticmap.CircleMarker((lon, lat), "#1a365d", 16))
        m.add_marker(staticmap.CircleMarker((lon, lat), "white", 9))
        m.add_marker(staticmap.CircleMarker((lon, lat), "#1a365d", 6))

        image = m.render(zoom=effective_zoom)

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
    zoom: int | None = None,
    width: int = 800,
    height: int = 500,
) -> Optional[str]:
    """Return a base64-encoded grid context map for HTML embedding."""
    return _to_base64(
        generate_grid_context_image(lat, lon, assets, radius_km, zoom, width, height)
    )
