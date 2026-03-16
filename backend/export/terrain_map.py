"""
DC Feasibility Tool v4 — Terrain Map Generator
================================================
Generates terrain imagery for data center site locations using
OpenTopoMap tiles via the ``staticmap`` library.

No API key required — OpenTopoMap is free under ODbL.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import staticmap  # type: ignore[import-untyped]

    _HAS_STATICMAP = True
except ImportError:
    _HAS_STATICMAP = False


# OpenTopoMap tile URL (free, no key needed)
OPENTOPOMAP_URL = "https://tile.opentopomap.org/{z}/{x}/{y}.png"


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
    png_bytes = generate_terrain_image(lat, lon, zoom, width, height)
    if png_bytes is None:
        return None
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"
