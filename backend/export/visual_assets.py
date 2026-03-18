"""
DC Feasibility Tool v4 - Export Visual Assets
=============================================
Builds export-safe inline SVG visuals so HTML/PDF reports can render
deterministic maps and charts without browser-side libraries or network calls.

Design principles:
- Clean, professional aesthetic matching the report CSS design system
- No external dependencies in the SVG output
- Consistent colour usage via primary/secondary theme colours
- Accessible labels and titles on all charts
"""

from __future__ import annotations

from html import escape
import math
from math import cos, pi, radians, sin
from typing import Any


# ── Canvas dimensions ─────────────────────────────────────────────────────────
MAP_WIDTH    = 720
MAP_HEIGHT   = 360
CHART_WIDTH  = 680
CHART_HEIGHT = 300

_PAD_OUTER = 24   # outer SVG padding
_PAD_AXIS  = 46   # space reserved for axis labels
_PAD_TOP   = 52   # space reserved for title + subtitle


# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(value: str | None, fallback: str) -> str:
    if not value or not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#rrggbb' to (r, g, b) ints."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ── Coordinate helpers ────────────────────────────────────────────────────────
def _point_pairs(coordinates: list[list[float]] | None) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for coord in coordinates or []:
        if len(coord) < 2:
            continue
        lat, lon = coord[0], coord[1]
        if lat is None or lon is None:
            continue
        pairs.append((float(lat), float(lon)))
    return pairs


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _map_bounds(
    points: list[tuple[float, float]],
    *,
    min_span_lat: float = 0.01,
    min_span_lon: float = 0.01,
) -> tuple[float, float, float, float]:
    if not points:
        return (0.0, 1.0, 0.0, 1.0)
    min_lat = min(p[0] for p in points)
    max_lat = max(p[0] for p in points)
    min_lon = min(p[1] for p in points)
    max_lon = max(p[1] for p in points)

    if (max_lat - min_lat) < min_span_lat:
        c = (min_lat + max_lat) / 2
        min_lat, max_lat = c - min_span_lat / 2, c + min_span_lat / 2
    if (max_lon - min_lon) < min_span_lon:
        c = (min_lon + max_lon) / 2
        min_lon, max_lon = c - min_span_lon / 2, c + min_span_lon / 2

    pad_lat = (max_lat - min_lat) * 0.18
    pad_lon = (max_lon - min_lon) * 0.18
    return (min_lat - pad_lat, max_lat + pad_lat, min_lon - pad_lon, max_lon + pad_lon)


def _project(
    lat: float,
    lon: float,
    bounds: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
    top_offset: int = 0,
) -> tuple[float, float]:
    min_lat, max_lat, min_lon, max_lon = bounds
    usable_w = width - _PAD_OUTER * 2
    usable_h = height - _PAD_OUTER * 2 - top_offset
    lon_span = max(max_lon - min_lon, 1e-9)
    lat_span = max(max_lat - min_lat, 1e-9)
    x = _PAD_OUTER + ((lon - min_lon) / lon_span) * usable_w
    y = _PAD_OUTER + top_offset + ((max_lat - lat) / lat_span) * usable_h
    return (x, y)


# ── SVG primitives ────────────────────────────────────────────────────────────
def _polyline(
    points: list[tuple[float, float]],
    *,
    stroke: str,
    stroke_width: float,
    fill: str = "none",
    dash: str | None = None,
    opacity: float = 1.0,
) -> str:
    if len(points) < 2:
        return ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline points="{pts}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" '
        f'opacity="{opacity:.2f}"{dash_attr} />'
    )


def _polygon(
    points: list[tuple[float, float]],
    *,
    stroke: str,
    stroke_width: float,
    fill: str,
    fill_opacity: float = 0.15,
) -> str:
    if len(points) < 3:
        return ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polygon points="{pts}" fill="{fill}" fill-opacity="{fill_opacity:.2f}" '
        f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-linejoin="round" />'
    )


def _site_anchor(
    site_data: dict[str, Any],
    geometry_points: list[tuple[float, float]],
) -> tuple[float, float] | None:
    location = site_data["location"]
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is not None and lon is not None:
        return (float(lat), float(lon))
    return _centroid(geometry_points)


def _voltage_color(voltage_kv: float | None, *, primary: str, secondary: str) -> str:
    if voltage_kv is None:
        return "#94a3b8"
    if voltage_kv >= 300:
        return "#b45309"
    if voltage_kv >= 220:
        return "#ea580c"
    if voltage_kv >= 132:
        return secondary
    return primary


# ── SVG shell ────────────────────────────────────────────────────────────────
def _svg_shell(
    *,
    width: int,
    height: int,
    title: str,
    subtitle: str,
    body: str,
    defs: str = "",
) -> str:
    """Render the outer SVG wrapper with consistent styling."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="{escape(title)}">'
        f"{defs}"
        # background
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#f9fafb" />'
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="11" '
        f'fill="white" stroke="#e5e7eb" stroke-width="1" />'
        # title + subtitle
        f'<text x="{_PAD_OUTER}" y="22" fill="#111827" font-family="system-ui,sans-serif" '
        f'font-size="12" font-weight="700" letter-spacing="-0.01em">{escape(title)}</text>'
        f'<text x="{_PAD_OUTER}" y="38" fill="#6b7280" font-family="system-ui,sans-serif" '
        f'font-size="9">{escape(subtitle)}</text>'
        # subtle title separator
        f'<line x1="{_PAD_OUTER}" y1="44" x2="{width - _PAD_OUTER}" y2="44" '
        f'stroke="#f3f4f6" stroke-width="1" />'
        f"{body}"
        "</svg>"
    )


def _grid_lines(
    width: int,
    height: int,
    *,
    top_offset: int = _PAD_TOP,
    cols: int = 5,
    rows: int = 5,
) -> str:
    parts = []
    uw = width - _PAD_OUTER * 2
    uh = height - _PAD_OUTER * 2 - top_offset
    for i in range(cols + 1):
        x = _PAD_OUTER + uw * i / cols
        parts.append(
            f'<line x1="{x:.1f}" y1="{_PAD_OUTER + top_offset}" '
            f'x2="{x:.1f}" y2="{height - _PAD_OUTER}" '
            'stroke="#f3f4f6" stroke-width="1" />'
        )
    for i in range(rows + 1):
        y = _PAD_OUTER + top_offset + uh * i / rows
        parts.append(
            f'<line x1="{_PAD_OUTER}" y1="{y:.1f}" '
            f'x2="{width - _PAD_OUTER}" y2="{y:.1f}" '
            'stroke="#f3f4f6" stroke-width="1" />'
        )
    return "".join(parts)


# ── Chart bounds ──────────────────────────────────────────────────────────────
def _chart_bounds(values: list[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 1.0)
    lo, hi = min(values), max(values)
    if lo == hi:
        lo -= 1.0
        hi += 1.0
    pad = (hi - lo) * 0.12
    return (lo - pad, hi + pad)


def _chart_xy(
    index: int,
    value: float,
    *,
    count: int,
    bounds: tuple[float, float],
    width: int,
    height: int,
) -> tuple[float, float]:
    plot_w = width - _PAD_AXIS - _PAD_OUTER
    plot_h = height - _PAD_TOP - _PAD_OUTER - 20  # 20 for x-axis labels
    x = _PAD_AXIS + (plot_w * index / max(count - 1, 1))
    lo, hi = bounds
    y = _PAD_TOP + ((hi - value) / max(hi - lo, 1e-9)) * plot_h
    return (x, y)


def _wrap_label(text: str, *, max_chars: int = 16, max_lines: int = 3) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    lines.append(current)
    return lines[:max_lines]


# ══════════════════════════════════════════════════════════════════════════════
# MAP VISUALS
# ══════════════════════════════════════════════════════════════════════════════

def build_site_map_visual(
    site_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """SVG schematic map of the site footprint and anchor point."""
    imported_geometry = site_data["imported_geometry"]
    geometry_points = _point_pairs(imported_geometry.get("coordinates"))
    anchor = _site_anchor(site_data, geometry_points)

    if anchor is None:
        return {
            "available": False,
            "title": "Site Map",
            "message": "No site coordinates or imported geometry available for map rendering.",
            "svg_markup": None,
        }

    primary  = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")
    bounds = _map_bounds(geometry_points + [anchor], min_span_lat=0.008, min_span_lon=0.008)

    # Geometry layer
    geometry_svg = ""
    projected = [
        _project(lat, lon, bounds, width=MAP_WIDTH, height=MAP_HEIGHT, top_offset=_PAD_TOP)
        for lat, lon in geometry_points
    ]
    geom_type = imported_geometry.get("geometry_type")
    if projected:
        if geom_type == "polygon":
            geometry_svg = _polygon(
                projected,
                stroke=primary,
                stroke_width=2.0,
                fill=secondary,
                fill_opacity=0.12,
            )
        elif geom_type == "line":
            geometry_svg = _polyline(projected, stroke=secondary, stroke_width=2.5)
        else:
            px, py = projected[0]
            geometry_svg = (
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" '
                f'fill="{secondary}" opacity="0.8" />'
            )

    ax, ay = _project(anchor[0], anchor[1], bounds, width=MAP_WIDTH, height=MAP_HEIGHT, top_offset=_PAD_TOP)
    city = escape(site_data["location"].get("city") or "Studied site")
    name = escape(site_data["name"])

    body = (
        _grid_lines(MAP_WIDTH, MAP_HEIGHT)
        + geometry_svg
        # site marker — outer pulse ring
        + f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="18" fill="{_rgba(primary, 0.1)}" />'
        + f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="10" fill="{_rgba(primary, 0.2)}" />'
        # site dot
        + f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="6" fill="{primary}" stroke="white" stroke-width="1.5" />'
        # label
        + f'<rect x="{ax + 14:.1f}" y="{ay - 18:.1f}" width="{len(name) * 6.5 + 8:.0f}" height="30" '
        + f'rx="4" fill="white" fill-opacity="0.9" stroke="{_rgba(primary, 0.15)}" stroke-width="1" />'
        + f'<text x="{ax + 18:.1f}" y="{ay - 5:.1f}" fill="{primary}" '
        + f'font-family="system-ui,sans-serif" font-size="10" font-weight="700">{name}</text>'
        + f'<text x="{ax + 18:.1f}" y="{ay + 8:.1f}" fill="#6b7280" '
        + f'font-family="system-ui,sans-serif" font-size="8">{city}</text>'
    )

    subtitle = (
        "Imported geometry overlay shown."
        if geometry_points
        else "Centered on saved site coordinates."
    )
    return {
        "available": True,
        "title": "Site Map",
        "message": "",
        "svg_markup": _svg_shell(
            width=MAP_WIDTH,
            height=MAP_HEIGHT,
            title="Site Map",
            subtitle=subtitle,
            body=body,
        ),
    }


def build_grid_context_map_visual(
    site_data: dict[str, Any],
    *,
    grid_center: tuple[float | None, float | None],
    radius_km: float | None,
    assets: list[dict[str, Any]],
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """SVG map showing nearby grid assets and the screening radius."""
    site_anchor = _site_anchor(
        {
            "location": {
                "latitude": grid_center[0] if grid_center[0] is not None
                            else site_data["location"].get("latitude"),
                "longitude": grid_center[1] if grid_center[1] is not None
                             else site_data["location"].get("longitude"),
            }
        },
        [],
    )
    if site_anchor is None:
        return {
            "available": False,
            "title": "Grid Context Map",
            "message": "No site coordinates available for the grid-context map.",
            "svg_markup": None,
        }

    primary  = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    lat_r = (radius_km / 111.0) if radius_km else 0.03
    lon_r = (
        radius_km / (111.0 * max(cos(radians(site_anchor[0])), 0.2))
        if radius_km else 0.03
    )
    map_pts = [site_anchor]
    for asset in assets:
        map_pts.extend(_point_pairs(asset.get("coordinates")))
    map_pts += [
        (site_anchor[0] - lat_r, site_anchor[1]),
        (site_anchor[0] + lat_r, site_anchor[1]),
        (site_anchor[0], site_anchor[1] - lon_r),
        (site_anchor[0], site_anchor[1] + lon_r),
    ]
    bounds = _map_bounds(
        map_pts,
        min_span_lat=max(lat_r * 2.4, 0.02),
        min_span_lon=max(lon_r * 2.4, 0.02),
    )

    sx, sy = _project(site_anchor[0], site_anchor[1], bounds, width=MAP_WIDTH, height=MAP_HEIGHT, top_offset=_PAD_TOP)
    rx, _ = _project(site_anchor[0], site_anchor[1] + lon_r, bounds, width=MAP_WIDTH, height=MAP_HEIGHT, top_offset=_PAD_TOP)
    _, ry = _project(site_anchor[0] + lat_r, site_anchor[1], bounds, width=MAP_WIDTH, height=MAP_HEIGHT, top_offset=_PAD_TOP)
    ellipse_rx = abs(rx - sx)
    ellipse_ry = abs(ry - sy)

    asset_svg: list[str] = []
    for asset in assets:
        asset_pts = _point_pairs(asset.get("coordinates"))
        if not asset_pts:
            continue
        color = _voltage_color(asset.get("voltage_kv"), primary=primary, secondary=secondary)
        projected = [
            _project(lat, lon, bounds, width=MAP_WIDTH, height=MAP_HEIGHT, top_offset=_PAD_TOP)
            for lat, lon in asset_pts
        ]
        geom_type = asset.get("geometry_type")
        if geom_type == "line" or len(projected) > 1:
            asset_svg.append(
                _polyline(
                    projected,
                    stroke=color,
                    stroke_width=2.5 if asset.get("voltage_kv") else 1.8,
                    dash="6 4" if asset.get("voltage_kv") is None else None,
                    opacity=0.9 if asset.get("voltage_kv") else 0.65,
                )
            )
        else:
            px, py = projected[0]
            if asset.get("asset_type") == "substation":
                asset_svg.append(
                    f'<rect x="{px - 5:.1f}" y="{py - 5:.1f}" width="10" height="10" '
                    f'rx="2" fill="{color}" stroke="white" stroke-width="1.5" />'
                )
            else:
                asset_svg.append(
                    f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" '
                    f'fill="{color}" stroke="white" stroke-width="1.5" />'
                )

    radius_label = escape(
        f"{radius_km:.1f} km screening radius" if radius_km is not None else "Screening radius"
    )
    site_name = escape(site_data["name"])

    body = (
        _grid_lines(MAP_WIDTH, MAP_HEIGHT)
        # search radius ellipse
        + f'<ellipse cx="{sx:.1f}" cy="{sy:.1f}" rx="{ellipse_rx:.1f}" ry="{ellipse_ry:.1f}" '
        + f'fill="{_rgba(secondary, 0.05)}" stroke="{secondary}" stroke-width="1.5" '
        + f'stroke-dasharray="8 5" />'
        # assets
        + "".join(asset_svg)
        # site marker
        + f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="16" fill="{_rgba(primary, 0.1)}" />'
        + f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="7" fill="{primary}" stroke="white" stroke-width="2" />'
        # label
        + f'<rect x="{sx + 12:.1f}" y="{sy - 18:.1f}" width="{len(site_name) * 6.5 + 8:.0f}" height="30" '
        + f'rx="4" fill="white" fill-opacity="0.92" stroke="{_rgba(primary, 0.15)}" stroke-width="1" />'
        + f'<text x="{sx + 16:.1f}" y="{sy - 5:.1f}" fill="{primary}" '
        + f'font-family="system-ui,sans-serif" font-size="10" font-weight="700">{site_name}</text>'
        + f'<text x="{sx + 16:.1f}" y="{sy + 8:.1f}" fill="#6b7280" '
        + f'font-family="system-ui,sans-serif" font-size="8">{radius_label}</text>'
    )

    return {
        "available": True,
        "title": "Grid Context Map",
        "message": "",
        "svg_markup": _svg_shell(
            width=MAP_WIDTH,
            height=MAP_HEIGHT,
            title="Grid Context Map",
            subtitle="Nearby mapped lines and substations within the selected screening extent.",
            body=body,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# CHART VISUALS
# ══════════════════════════════════════════════════════════════════════════════

def build_monthly_temperature_chart(
    monthly_stats: dict[str, list[float]] | None,
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Line chart showing monthly temperature min/mean/max."""
    if not monthly_stats:
        return {
            "available": False,
            "title": "Monthly Temperature Chart",
            "message": "Monthly chart requires a full 8,760-hour weather year.",
            "svg_markup": None,
        }

    monthly_mean = monthly_stats.get("monthly_mean") or []
    monthly_min  = monthly_stats.get("monthly_min")  or []
    monthly_max  = monthly_stats.get("monthly_max")  or []
    if len(monthly_mean) != 12 or len(monthly_min) != 12 or len(monthly_max) != 12:
        return {
            "available": False,
            "title": "Monthly Temperature Chart",
            "message": "Monthly chart requires 12 monthly values.",
            "svg_markup": None,
        }

    primary   = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")
    bounds = _chart_bounds(monthly_min + monthly_max)

    kw = {"count": 12, "bounds": bounds, "width": CHART_WIDTH, "height": CHART_HEIGHT}
    mean_pts = [_chart_xy(i, v, **kw) for i, v in enumerate(monthly_mean)]
    min_pts  = [_chart_xy(i, v, **kw) for i, v in enumerate(monthly_min)]
    max_pts  = [_chart_xy(i, v, **kw) for i, v in enumerate(monthly_max)]

    # Temperature band (polygon between min and max)
    band_pts = max_pts + list(reversed(min_pts))
    band_svg = _polygon(band_pts, stroke="none", stroke_width=0, fill=secondary, fill_opacity=0.08)

    # Y-axis ticks
    tick_parts: list[str] = []
    lo, hi = bounds
    for tick_i in range(5):
        val = lo + (hi - lo) * tick_i / 4
        _, ty = _chart_xy(0, val, **kw)
        tick_parts.append(
            f'<line x1="{_PAD_AXIS}" y1="{ty:.1f}" '
            f'x2="{CHART_WIDTH - _PAD_OUTER}" y2="{ty:.1f}" '
            'stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{_PAD_AXIS - 4}" y="{ty + 4:.1f}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">{val:.0f}°</text>'
        )

    # X-axis month labels
    month_labels = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    x_label_parts: list[str] = []
    for i, label in enumerate(month_labels):
        x, _ = _chart_xy(i, monthly_mean[i], **kw)
        x_label_parts.append(
            f'<text x="{x:.1f}" y="{CHART_HEIGHT - 8}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="middle">{label}</text>'
        )

    # Mean line dots
    dot_parts = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{primary}" />'
        for x, y in mean_pts
    )

    # Legend
    legend = (
        f'<circle cx="{CHART_WIDTH - 120}" cy="30" r="3" fill="{primary}" />'
        f'<text x="{CHART_WIDTH - 114}" y="34" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="8">Mean</text>'
        f'<rect x="{CHART_WIDTH - 80}" y="27" width="12" height="6" '
        f'rx="1" fill="{_rgba(secondary, 0.3)}" />'
        f'<text x="{CHART_WIDTH - 65}" y="34" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="8">Min–Max range</text>'
    )

    body = (
        "".join(tick_parts)
        + band_svg
        + _polyline(max_pts, stroke=_rgba(secondary, 0.5), stroke_width=1.2)
        + _polyline(min_pts, stroke=_rgba(secondary, 0.5), stroke_width=1.2)
        + _polyline(mean_pts, stroke=primary, stroke_width=2.2)
        + dot_parts
        + "".join(x_label_parts)
        + legend
    )

    return {
        "available": True,
        "title": "Monthly Temperature Chart",
        "message": "",
        "svg_markup": _svg_shell(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title="Monthly Temperature Profile",
            subtitle="Monthly mean dry-bulb temperature with min/max envelope.",
            body=body,
        ),
    }


def build_cooling_suitability_chart(
    free_cooling_rows: list[dict[str, Any]],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Grouped bar chart showing cooling suitability with DIFFERENT values per topology."""
    if not free_cooling_rows:
        return {
            "available": False,
            "title": "Cooling Topology Suitability",
            "message": "No free-cooling data available.",
            "svg_markup": None,
        }

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    # Colors for different topologies
    palette = [primary, secondary, "#16a34a", "#ea580c", "#8b5cf6", "#0891b2"]

    max_hours = max(float(item.get("free_cooling_hours") or 0.0) for item in free_cooling_rows)
    max_fraction = max(float(item.get("free_cooling_fraction") or 0.0) for item in free_cooling_rows)
    upper_h = max(max_hours * 1.15, 1.0)

    w, h = CHART_WIDTH, CHART_HEIGHT + 40
    plot_left = 100
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 10
    plot_bottom = h - 50
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    n = len(free_cooling_rows)
    bar_group_w = plot_w / max(n, 1)
    bar_w = min(bar_group_w * 0.55, 48)

    # Y-axis ticks
    tick_parts: list[str] = []
    for i in range(5):
        val = upper_h * i / 4
        y = plot_bottom - (val / upper_h) * plot_h
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" '
            f'x2="{plot_right}" y2="{y:.1f}" '
            'stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{plot_left - 6}" y="{y + 3:.1f}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">{val:.0f}h</text>'
        )

    bar_parts: list[str] = []
    for idx, item in enumerate(free_cooling_rows):
        hours = float(item.get("free_cooling_hours") or 0.0)
        fraction = float(item.get("free_cooling_fraction") or 0.0)
        suitability = str(item.get("suitability") or "")
        color = palette[idx % len(palette)]
        cx = plot_left + bar_group_w * idx + bar_group_w / 2
        bx = cx - bar_w / 2
        bar_h_px = (hours / upper_h) * plot_h
        by = plot_bottom - bar_h_px

        # Bar
        bar_parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h_px:.1f}" '
            f'rx="3" fill="{color}" opacity="0.85" />'
        )
        # Hours label above bar
        bar_parts.append(
            f'<text x="{cx:.1f}" y="{by - 12:.1f}" fill="{color}" '
            f'font-family="system-ui,sans-serif" font-size="9" font-weight="700" '
            f'text-anchor="middle">{hours:.0f}h</text>'
        )
        # Fraction label
        bar_parts.append(
            f'<text x="{cx:.1f}" y="{by - 3:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" '
            f'text-anchor="middle">{fraction * 100:.1f}%</text>'
        )
        # Cooling type label
        label = str(item.get("cooling_type") or "")
        wrapped = _wrap_label(label, max_chars=12, max_lines=2)
        for li, line in enumerate(wrapped):
            bar_parts.append(
                f'<text x="{cx:.1f}" y="{plot_bottom + 14 + li * 10:.1f}" fill="#374151" '
                f'font-family="system-ui,sans-serif" font-size="7.5" '
                f'text-anchor="middle">{escape(line)}</text>'
            )
        # Suitability badge
        suit_color = "#16a34a" if "excellent" in suitability.lower() or "good" in suitability.lower() else (
            "#ea580c" if "moderate" in suitability.lower() or "marginal" in suitability.lower() else "#6b7280"
        )
        bar_parts.append(
            f'<text x="{cx:.1f}" y="{plot_bottom + 14 + len(wrapped) * 10 + 2:.1f}" fill="{suit_color}" '
            f'font-family="system-ui,sans-serif" font-size="6.5" font-weight="600" '
            f'text-anchor="middle">{escape(suitability)}</text>'
        )

    body = "".join(tick_parts) + "".join(bar_parts)

    return {
        "available": True,
        "title": "Cooling Topology Suitability",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="Cooling Topology Suitability",
            subtitle="Free-cooling hours and fraction by cooling type — each topology has distinct values.",
            body=body,
        ),
    }


def build_free_cooling_chart(
    free_cooling_rows: list[dict[str, Any]],
    *,
    selected_cooling_type: str | None,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Horizontal bar chart of free-cooling hours by cooling topology."""
    if not free_cooling_rows:
        return {
            "available": False,
            "title": "Free Cooling Chart",
            "message": "No free-cooling rows available for chart rendering.",
            "svg_markup": None,
        }

    primary   = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    max_hours = max(float(item.get("free_cooling_hours") or 0.0) for item in free_cooling_rows)
    upper = max(max_hours * 1.12, 1.0)

    plot_w = CHART_WIDTH - _PAD_AXIS - _PAD_OUTER
    plot_h = CHART_HEIGHT - _PAD_TOP - _PAD_OUTER - 20
    bar_h = min(32.0, (plot_h - (len(free_cooling_rows) - 1) * 8) / max(len(free_cooling_rows), 1))
    gap = 8.0

    # X-axis ticks
    tick_parts: list[str] = []
    for tick_i in range(5):
        val = upper * tick_i / 4
        x = _PAD_AXIS + (val / upper) * plot_w
        tick_parts.append(
            f'<line x1="{x:.1f}" y1="{_PAD_TOP}" '
            f'x2="{x:.1f}" y2="{_PAD_TOP + plot_h}" '
            'stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{x:.1f}" y="{_PAD_TOP + plot_h + 14}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="middle">{val:.0f}h</text>'
        )

    bar_parts: list[str] = []
    for idx, item in enumerate(free_cooling_rows):
        hours = float(item.get("free_cooling_hours") or 0.0)
        y = _PAD_TOP + idx * (bar_h + gap)
        bar_w = (hours / upper) * plot_w
        is_selected = item.get("cooling_type") == selected_cooling_type

        fill   = primary if is_selected else secondary
        fill_a = 1.0 if is_selected else 0.45
        bar_fill = _rgba(fill, fill_a)
        bg_fill  = _rgba(fill, 0.06)

        # Background track
        bar_parts.append(
            f'<rect x="{_PAD_AXIS}" y="{y:.1f}" width="{plot_w:.1f}" height="{bar_h:.1f}" '
            f'rx="4" fill="{bg_fill}" />'
        )
        # Filled bar
        if bar_w > 0:
            bar_parts.append(
                f'<rect x="{_PAD_AXIS}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'rx="4" fill="{bar_fill}" />'
            )
        # Value label inside / outside bar
        label_x = _PAD_AXIS + bar_w + 6 if bar_w < plot_w * 0.7 else _PAD_AXIS + bar_w - 6
        label_anchor = "start" if bar_w < plot_w * 0.7 else "end"
        label_fill = "#111827" if bar_w < plot_w * 0.7 else "white"
        bar_parts.append(
            f'<text x="{label_x:.1f}" y="{y + bar_h / 2 + 4:.1f}" fill="{label_fill}" '
            f'font-family="system-ui,sans-serif" font-size="9" font-weight="600" '
            f'text-anchor="{label_anchor}">{hours:.0f} h</text>'
        )

        # Y-axis label (cooling type)
        label_text = str(item.get("cooling_type") or "")
        wrapped = _wrap_label(label_text, max_chars=14, max_lines=2)
        for li, line in enumerate(wrapped):
            bar_parts.append(
                f'<text x="{_PAD_AXIS - 6}" y="{y + bar_h / 2 - 4 + li * 10:.1f}" '
                f'fill={"#111827" if is_selected else "#374151"}" '
                f'font-family="system-ui,sans-serif" font-size="8" '
                f'font-weight="{"700" if is_selected else "400"}" text-anchor="end">'
                f'{escape(line)}</text>'
            )

        # "selected" badge
        if is_selected:
            badge_x = _PAD_AXIS + min(bar_w, plot_w) + 40
            bar_parts.append(
                f'<rect x="{badge_x:.1f}" y="{y + bar_h / 2 - 7:.1f}" '
                f'width="46" height="14" rx="7" fill="{_rgba(primary, 0.12)}" />'
                f'<text x="{badge_x + 23:.1f}" y="{y + bar_h / 2 + 4:.1f}" '
                f'fill="{primary}" font-family="system-ui,sans-serif" '
                f'font-size="7" font-weight="700" text-anchor="middle">SELECTED</text>'
            )

    body = "".join(tick_parts) + "".join(bar_parts)

    return {
        "available": True,
        "title": "Free Cooling Chart",
        "message": "",
        "svg_markup": _svg_shell(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title="Free Cooling Hours by Topology",
            subtitle="Annual free-cooling hours by cooling type. Selected scenario is highlighted.",
            body=body,
        ),
    }


# ======================================================================
# SCENARIO RESULT CHARTS
# ======================================================================

def build_it_capacity_spectrum_chart(
    metrics: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Horizontal bar chart showing IT capacity at different statistical checkpoints."""
    checkpoints = [
        ("Best hour", metrics.get("it_capacity_best_mw")),
        ("Mean", metrics.get("it_capacity_mean_mw")),
        ("P90", metrics.get("it_capacity_p90_mw")),
        ("P99 (Committed)", metrics.get("it_capacity_p99_mw") or metrics.get("committed_it_mw")),
        ("Worst hour", metrics.get("it_capacity_worst_mw")),
        ("Nominal design", metrics.get("it_load_mw")),
    ]
    available = [(label, float(val)) for label, val in checkpoints if val is not None]
    if len(available) < 2:
        return {
            "available": False,
            "title": "IT Capacity Spectrum",
            "message": "Insufficient data for IT capacity spectrum chart.",
            "svg_markup": None,
        }

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    max_val = max(v for _, v in available)
    upper = max_val * 1.18

    w, h = CHART_WIDTH, max(len(available) * 42 + _PAD_TOP + 40, 220)
    plot_left = 120
    plot_right = w - _PAD_OUTER - 40
    plot_top = _PAD_TOP + 5
    plot_w = plot_right - plot_left
    bar_h = min(28, (h - plot_top - 30) / max(len(available), 1) - 8)
    gap = 8

    palette = ["#16a34a", "#2563eb", "#7c3aed", primary, "#dc2626", secondary]

    bar_parts: list[str] = []
    for idx, (label, value) in enumerate(available):
        y = plot_top + idx * (bar_h + gap)
        bw = max((value / upper) * plot_w, 2)
        color = palette[idx % len(palette)]

        # Background track
        bar_parts.append(
            f'<rect x="{plot_left}" y="{y:.1f}" width="{plot_w:.1f}" height="{bar_h:.1f}" '
            f'rx="4" fill="{_rgba(color, 0.06)}" />'
        )
        # Filled bar
        bar_parts.append(
            f'<rect x="{plot_left}" y="{y:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" '
            f'rx="4" fill="{color}" opacity="0.82" />'
        )
        # Value label
        label_x = plot_left + bw + 6
        bar_parts.append(
            f'<text x="{label_x:.1f}" y="{y + bar_h / 2 + 4:.1f}" fill="#111827" '
            f'font-family="system-ui,sans-serif" font-size="9" font-weight="600">'
            f'{value:.2f} MW</text>'
        )
        # Y-axis label
        bar_parts.append(
            f'<text x="{plot_left - 6}" y="{y + bar_h / 2 + 4:.1f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end" '
            f'font-weight="{"700" if "Committed" in label or "P99" in label else "400"}">'
            f'{escape(label)}</text>'
        )

    body = "".join(bar_parts)
    return {
        "available": True,
        "title": "IT Capacity Spectrum",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="IT Capacity Spectrum",
            subtitle="MW capacity at different statistical checkpoints across the weather year.",
            body=body,
        ),
    }


def build_pue_breakdown_chart(
    pue: float | None,
    power_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Donut-style PUE breakdown showing IT vs overhead power components."""
    if pue is None or pue <= 0:
        return {
            "available": False,
            "title": "PUE Breakdown",
            "message": "No PUE data available for chart.",
            "svg_markup": None,
        }

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    it_mw = float(power_data.get("it_load_mw") or 0)
    facility_mw = float(power_data.get("facility_power_mw") or 0)
    overhead_mw = facility_mw - it_mw if facility_mw > it_mw else 0

    if it_mw <= 0:
        return {
            "available": False,
            "title": "PUE Breakdown",
            "message": "No IT load data available.",
            "svg_markup": None,
        }

    total = it_mw + overhead_mw
    it_pct = (it_mw / total * 100) if total > 0 else 0
    oh_pct = (overhead_mw / total * 100) if total > 0 else 0

    w, h = 340, CHART_HEIGHT
    cx, cy = 170, 160
    r_outer = 80
    r_inner = 50

    # IT arc
    it_angle = (it_pct / 100) * 2 * math.pi
    oh_angle = (oh_pct / 100) * 2 * math.pi

    def _arc(start_angle: float, end_angle: float, ro: float, ri: float) -> str:
        x1o = cx + ro * math.cos(start_angle - math.pi / 2)
        y1o = cy + ro * math.sin(start_angle - math.pi / 2)
        x2o = cx + ro * math.cos(end_angle - math.pi / 2)
        y2o = cy + ro * math.sin(end_angle - math.pi / 2)
        x1i = cx + ri * math.cos(end_angle - math.pi / 2)
        y1i = cy + ri * math.sin(end_angle - math.pi / 2)
        x2i = cx + ri * math.cos(start_angle - math.pi / 2)
        y2i = cy + ri * math.sin(start_angle - math.pi / 2)
        large = 1 if (end_angle - start_angle) > math.pi else 0
        return (
            f'M {x1o:.1f},{y1o:.1f} '
            f'A {ro},{ro} 0 {large},1 {x2o:.1f},{y2o:.1f} '
            f'L {x1i:.1f},{y1i:.1f} '
            f'A {ri},{ri} 0 {large},0 {x2i:.1f},{y2i:.1f} Z'
        )

    arcs = ""
    if it_pct >= 99.5:
        arcs = (
            f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="{primary}" />'
            f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="white" />'
        )
    elif oh_pct >= 99.5:
        arcs = (
            f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="{secondary}" />'
            f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="white" />'
        )
    else:
        it_path = _arc(0, it_angle, r_outer, r_inner)
        oh_path = _arc(it_angle, it_angle + oh_angle, r_outer, r_inner)
        arcs = (
            f'<path d="{it_path}" fill="{primary}" />'
            f'<path d="{oh_path}" fill="{secondary}" opacity="0.7" />'
        )

    # Center PUE text
    center_text = (
        f'<text x="{cx}" y="{cy - 6}" fill="{primary}" '
        f'font-family="system-ui,sans-serif" font-size="22" font-weight="800" '
        f'text-anchor="middle">{pue:.3f}</text>'
        f'<text x="{cx}" y="{cy + 10}" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="8" '
        f'text-anchor="middle">Annual PUE</text>'
    )

    # Legend
    legend_y = cy + r_outer + 24
    legend = (
        f'<rect x="{cx - 80}" y="{legend_y}" width="10" height="10" rx="2" fill="{primary}" />'
        f'<text x="{cx - 66}" y="{legend_y + 9}" fill="#374151" '
        f'font-family="system-ui,sans-serif" font-size="8">'
        f'IT Load {it_mw:.2f} MW ({it_pct:.1f}%)</text>'
        f'<rect x="{cx + 10}" y="{legend_y}" width="10" height="10" rx="2" fill="{secondary}" opacity="0.7" />'
        f'<text x="{cx + 24}" y="{legend_y + 9}" fill="#374151" '
        f'font-family="system-ui,sans-serif" font-size="8">'
        f'Overhead {overhead_mw:.2f} MW ({oh_pct:.1f}%)</text>'
    )

    body = arcs + center_text + legend

    return {
        "available": True,
        "title": "PUE Breakdown",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="PUE Breakdown",
            subtitle=f"IT vs overhead power split — PUE {pue:.3f}",
            body=body,
        ),
    }


def build_power_chain_waterfall(
    power_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Waterfall chart showing power chain from grid to IT load."""
    facility_mw = float(power_data.get("facility_power_mw") or 0)
    procurement_mw = float(power_data.get("procurement_power_mw") or 0)
    it_load_mw = float(power_data.get("it_load_mw") or 0)
    headroom_mw = float(power_data.get("power_headroom_mw") or 0)

    if facility_mw <= 0 and it_load_mw <= 0:
        return {
            "available": False,
            "title": "Power Chain Waterfall",
            "message": "No power data available for waterfall chart.",
            "svg_markup": None,
        }

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    overhead_mw = facility_mw - it_load_mw if facility_mw > it_load_mw else 0
    procurement_overhead_mw = procurement_mw - facility_mw if procurement_mw > facility_mw else 0

    stages = [
        ("Grid / Procurement", procurement_mw, primary),
        ("Procurement overhead", -procurement_overhead_mw, "#94a3b8"),
        ("Facility power", facility_mw, secondary),
        ("Cooling & electrical", -overhead_mw, "#ea580c"),
        ("IT Load", it_load_mw, "#16a34a"),
    ]
    # Filter out zero stages
    stages = [(label, val, color) for label, val, color in stages if abs(val) > 0.001]

    if not stages:
        return {
            "available": False,
            "title": "Power Chain Waterfall",
            "message": "No significant power stages to display.",
            "svg_markup": None,
        }

    max_val = max(abs(v) for _, v, _ in stages)
    upper = max_val * 1.2

    w, h = CHART_WIDTH, CHART_HEIGHT + 20
    plot_left = 140
    plot_right = w - _PAD_OUTER - 50
    plot_top = _PAD_TOP + 10
    plot_w = plot_right - plot_left
    n = len(stages)
    bar_group_w = plot_w / max(n, 1)
    bar_w = min(bar_group_w * 0.6, 60)

    # Baseline
    baseline_y = plot_top + (h - plot_top - 40) * 0.5
    parts: list[str] = []

    # Horizontal baseline
    parts.append(
        f'<line x1="{plot_left}" y1="{baseline_y:.1f}" '
        f'x2="{plot_right}" y2="{baseline_y:.1f}" '
        'stroke="#e5e7eb" stroke-width="1" stroke-dasharray="4 3" />'
    )

    running_y = baseline_y
    for idx, (label, value, color) in enumerate(stages):
        cx = plot_left + bar_group_w * idx + bar_group_w / 2
        bx = cx - bar_w / 2
        scale = (h - plot_top - 60) / 2 / max(upper, 0.001)

        if value >= 0:
            bar_px_h = value * scale
            by = running_y - bar_px_h
        else:
            bar_px_h = abs(value) * scale
            by = running_y

        parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_px_h:.1f}" '
            f'rx="3" fill="{color}" opacity="0.85" />'
        )

        # Value above/below bar
        val_y = by - 5 if value >= 0 else by + bar_px_h + 12
        parts.append(
            f'<text x="{cx:.1f}" y="{val_y:.1f}" fill="{color}" '
            f'font-family="system-ui,sans-serif" font-size="9" font-weight="700" '
            f'text-anchor="middle">{abs(value):.2f} MW</text>'
        )

        # Label below
        wrapped = _wrap_label(label, max_chars=14, max_lines=2)
        for li, line in enumerate(wrapped):
            parts.append(
                f'<text x="{cx:.1f}" y="{h - 20 + li * 10:.1f}" fill="#374151" '
                f'font-family="system-ui,sans-serif" font-size="7.5" '
                f'text-anchor="middle">{escape(line)}</text>'
            )

        if value < 0:
            running_y += bar_px_h
        else:
            running_y = by

    body = "".join(parts)
    return {
        "available": True,
        "title": "Power Chain Waterfall",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="Power Chain Waterfall",
            subtitle="Power flow from grid procurement through to IT load.",
            body=body,
        ),
    }


def build_scenario_comparison_chart(
    results: list[dict[str, Any]],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Grouped bar chart comparing IT load and PUE across scenarios."""
    if not results or len(results) < 2:
        return {
            "available": False,
            "title": "Scenario Comparison",
            "message": "Need at least two scenarios for comparison chart.",
            "svg_markup": None,
        }

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")
    palette = [primary, secondary, "#16a34a", "#7c3aed", "#ea580c", "#0891b2"]

    it_values = []
    labels = []
    for r in results[:8]:
        metrics = r.get("metrics", {})
        scenario = r.get("scenario", {})
        it_mw = metrics.get("committed_it_mw") or metrics.get("it_load_mw") or 0
        it_values.append(float(it_mw))
        short_label = f'{scenario.get("cooling_type", "?")} / {scenario.get("redundancy", "?")}'
        labels.append(short_label)

    max_it = max(it_values) if it_values else 1
    upper = max_it * 1.2

    n = len(it_values)
    w, h = CHART_WIDTH, CHART_HEIGHT + 30
    plot_left = 60
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 10
    plot_bottom = h - 55
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    bar_group_w = plot_w / max(n, 1)
    bar_w = min(bar_group_w * 0.55, 50)

    # Y-axis ticks
    tick_parts: list[str] = []
    for i in range(5):
        val = upper * i / 4
        y = plot_bottom - (val / upper) * plot_h
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" '
            'stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{plot_left - 4}" y="{y + 3:.1f}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">'
            f'{val:.1f}</text>'
        )

    bar_parts: list[str] = []
    for idx, (it_mw, label) in enumerate(zip(it_values, labels)):
        color = palette[idx % len(palette)]
        cx = plot_left + bar_group_w * idx + bar_group_w / 2
        bx = cx - bar_w / 2
        bar_h_px = max((it_mw / upper) * plot_h, 2)
        by = plot_bottom - bar_h_px

        is_primary = results[idx].get("is_primary", False)

        bar_parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h_px:.1f}" '
            f'rx="3" fill="{color}" opacity="{"0.95" if is_primary else "0.65"}" />'
        )
        bar_parts.append(
            f'<text x="{cx:.1f}" y="{by - 4:.1f}" fill="{color}" '
            f'font-family="system-ui,sans-serif" font-size="8" font-weight="700" '
            f'text-anchor="middle">{it_mw:.2f}</text>'
        )
        # PUE below
        pue = results[idx].get("metrics", {}).get("pue") or 0
        bar_parts.append(
            f'<text x="{cx:.1f}" y="{by - 13:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" '
            f'text-anchor="middle">PUE {pue:.3f}</text>'
        )
        # Label
        wrapped = _wrap_label(label, max_chars=12, max_lines=2)
        for li, line in enumerate(wrapped):
            bar_parts.append(
                f'<text x="{cx:.1f}" y="{plot_bottom + 14 + li * 9:.1f}" fill="#374151" '
                f'font-family="system-ui,sans-serif" font-size="7" '
                f'text-anchor="middle">{escape(line)}</text>'
            )

    # Y-axis label
    y_label = (
        f'<text x="14" y="{(plot_top + plot_bottom) / 2:.1f}" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="8" '
        f'text-anchor="middle" transform="rotate(-90, 14, {(plot_top + plot_bottom) / 2:.1f})">'
        f'Committed IT (MW)</text>'
    )

    body = "".join(tick_parts) + "".join(bar_parts) + y_label
    return {
        "available": True,
        "title": "Scenario Comparison",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="Scenario Comparison — IT Capacity & PUE",
            subtitle="Committed IT load (MW) and PUE across evaluated scenarios.",
            body=body,
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DAILY OPERATING PROFILE CHART
# ═══════════════════════════════════════════════════════════════════════════════

def build_daily_profile_chart(
    daily_profiles: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Line chart showing daily IT load and PUE ranges across the year."""
    days = daily_profiles.get("days") or []
    if not days or len(days) < 2:
        return {"available": False, "title": "Daily Operating Profiles", "message": "Insufficient data.", "svg_markup": None}

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    w, h = CHART_WIDTH, CHART_HEIGHT + 20
    plot_left = 70
    plot_right = w - 50
    plot_top = _PAD_TOP + 5
    plot_bottom = h - 40
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    # Extract data
    it_mins = [d["it_min_mw"] for d in days]
    it_maxs = [d["it_max_mw"] for d in days]
    it_avgs = [d["it_avg_mw"] for d in days]
    pue_avgs = [d["pue_avg"] for d in days]
    n = len(days)

    # Y-axis scales
    it_max_val = max(it_maxs) * 1.1 if max(it_maxs) > 0 else 1.0
    it_min_val = min(it_mins) * 0.95 if min(it_mins) > 0 else 0.0
    pue_max_val = max(d["pue_max"] for d in days) * 1.02
    pue_min_val = min(d["pue_min"] for d in days) * 0.98

    def x_pos(i: int) -> float:
        return plot_left + (i / max(n - 1, 1)) * plot_w

    def y_it(val: float) -> float:
        if it_max_val == it_min_val:
            return plot_top + plot_h / 2
        return plot_bottom - ((val - it_min_val) / (it_max_val - it_min_val)) * plot_h

    # Build IT range band (filled area between min and max)
    band_top = " ".join(f"{x_pos(i):.1f},{y_it(it_maxs[i]):.1f}" for i in range(n))
    band_bottom = " ".join(f"{x_pos(i):.1f},{y_it(it_mins[i]):.1f}" for i in range(n - 1, -1, -1))
    band = f'<polygon points="{band_top} {band_bottom}" fill="{primary}" opacity="0.15" />'

    # IT average line
    avg_points = " ".join(f"{x_pos(i):.1f},{y_it(it_avgs[i]):.1f}" for i in range(n))
    avg_line = f'<polyline points="{avg_points}" fill="none" stroke="{primary}" stroke-width="2" />'

    # Y-axis ticks for IT
    tick_parts: list[str] = []
    for i in range(5):
        frac = i / 4
        val = it_min_val + (it_max_val - it_min_val) * frac
        y = plot_bottom - frac * plot_h
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{plot_left - 6}" y="{y + 3:.1f}" fill="#9ca3af" font-family="system-ui,sans-serif" '
            f'font-size="8" text-anchor="end">{val:.1f}</text>'
        )

    # X-axis month labels
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    x_labels: list[str] = []
    for m in range(12):
        day_idx = int(m * 30.4)
        if day_idx < n:
            x_labels.append(
                f'<text x="{x_pos(day_idx):.1f}" y="{plot_bottom + 14:.1f}" fill="#9ca3af" '
                f'font-family="system-ui,sans-serif" font-size="7.5" text-anchor="middle">{month_labels[m]}</text>'
            )

    # Y-axis label
    y_label = (
        f'<text x="14" y="{(plot_top + plot_bottom) / 2:.1f}" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="8" text-anchor="middle" '
        f'transform="rotate(-90 14 {(plot_top + plot_bottom) / 2:.1f})">IT Load (MW)</text>'
    )

    body = "".join(tick_parts) + band + avg_line + "".join(x_labels) + y_label
    return {
        "available": True,
        "title": "Daily Operating Profiles",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="Daily IT Load Profile",
            subtitle="Range (band) and average (line) of IT capacity across the year.",
            body=body,
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FIRM CAPACITY CHART
# ═══════════════════════════════════════════════════════════════════════════════

def build_firm_capacity_chart(
    advisory: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Bar chart showing firm capacity gap and mitigation strategies."""
    strategies = advisory.get("strategies") or []
    firm_mw = advisory.get("firm_capacity_mw", 0)
    mean_mw = advisory.get("mean_capacity_mw", 0)
    worst_mw = advisory.get("worst_capacity_mw", 0)
    best_mw = advisory.get("best_capacity_mw", 0)

    if firm_mw <= 0 and mean_mw <= 0:
        return {"available": False, "title": "Firm Capacity", "message": "No data.", "svg_markup": None}

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")
    palette = [primary, "#16a34a", "#ea580c", "#8b5cf6"]

    # Capacity spectrum bars
    items = [
        ("Worst", worst_mw, "#ef4444"),
        ("P99 (Firm)", firm_mw, primary),
        ("Mean", mean_mw, secondary),
        ("Best", best_mw, "#16a34a"),
    ]
    items = [(label, val, color) for label, val, color in items if val and val > 0]

    w, h = CHART_WIDTH, CHART_HEIGHT
    plot_left = 100
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 5
    plot_bottom = h - 45
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    upper = max(val for _, val, _ in items) * 1.15 if items else 1.0
    n = len(items)
    bar_group_w = plot_w / max(n, 1)
    bar_w = min(bar_group_w * 0.55, 60)

    tick_parts: list[str] = []
    for i in range(5):
        val = upper * i / 4
        y = plot_bottom - (val / upper) * plot_h
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{plot_left - 6}" y="{y + 3:.1f}" fill="#9ca3af" font-family="system-ui,sans-serif" '
            f'font-size="8" text-anchor="end">{val:.1f} MW</text>'
        )

    bar_parts: list[str] = []
    for idx, (label, val, color) in enumerate(items):
        cx = plot_left + bar_group_w * idx + bar_group_w / 2
        bx = cx - bar_w / 2
        bar_h_px = (val / upper) * plot_h
        by = plot_bottom - bar_h_px
        bar_parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h_px:.1f}" rx="3" fill="{color}" opacity="0.85" />'
            f'<text x="{cx:.1f}" y="{by - 6:.1f}" fill="{color}" font-family="system-ui,sans-serif" '
            f'font-size="9" font-weight="700" text-anchor="middle">{val:.2f} MW</text>'
            f'<text x="{cx:.1f}" y="{plot_bottom + 14:.1f}" fill="#374151" font-family="system-ui,sans-serif" '
            f'font-size="8" text-anchor="middle">{escape(label)}</text>'
        )

    body = "".join(tick_parts) + "".join(bar_parts)
    return {
        "available": True,
        "title": "Firm Capacity Spectrum",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="IT Capacity Spectrum",
            subtitle=f"Firm (P99): {firm_mw:.2f} MW — Gap to mean: {max(0, mean_mw - firm_mw):.2f} MW",
            body=body,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PIE CHART
# ══════════════════════════════════════════════════════════════════════════════

_PIE_PALETTE = [
    "#1a365d", "#2b6cb0", "#16a34a", "#ea580c", "#8b5cf6",
    "#0891b2", "#d97706", "#dc2626", "#4f46e5", "#059669",
]


def build_pie_chart(
    slices: list[dict[str, Any]],
    *,
    title: str = "Pie Chart",
    subtitle: str = "",
    primary_color: str = "#1a365d",
    secondary_color: str = "#2b6cb0",
) -> dict[str, Any]:
    """Generic pie chart builder.

    Each slice dict: {"label": str, "value": float, "color": str (optional)}.
    """
    slices = [s for s in slices if s.get("value") and s["value"] > 0]
    if not slices:
        return {"available": False, "title": title, "message": "No data.", "svg_markup": None}

    total = sum(s["value"] for s in slices)
    w, h = CHART_WIDTH, CHART_HEIGHT + 20
    cx, cy = w * 0.38, _PAD_TOP + (h - _PAD_TOP - 20) / 2
    r = min(cx - _PAD_OUTER - 20, (h - _PAD_TOP - 40) / 2, 100)

    parts: list[str] = []
    angle = -pi / 2  # start at top

    for idx, s in enumerate(slices):
        fraction = s["value"] / total
        sweep = fraction * 2 * pi
        color = s.get("color") or _PIE_PALETTE[idx % len(_PIE_PALETTE)]

        x1 = cx + r * cos(angle)
        y1 = cy + r * sin(angle)
        x2 = cx + r * cos(angle + sweep)
        y2 = cy + r * sin(angle + sweep)

        large_arc = 1 if sweep > pi else 0

        if len(slices) == 1:
            # Full circle
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{color}" opacity="0.85" />'
            )
        else:
            parts.append(
                f'<path d="M {cx:.1f},{cy:.1f} L {x1:.1f},{y1:.1f} '
                f'A {r:.1f},{r:.1f} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" '
                f'fill="{color}" opacity="0.85" stroke="white" stroke-width="1.5" />'
            )

        angle += sweep

    # Legend on right side
    legend_x = cx + r + 40
    legend_y = _PAD_TOP + 10
    for idx, s in enumerate(slices):
        fraction = s["value"] / total
        color = s.get("color") or _PIE_PALETTE[idx % len(_PIE_PALETTE)]
        ly = legend_y + idx * 22
        parts.append(
            f'<rect x="{legend_x:.0f}" y="{ly:.0f}" width="10" height="10" rx="2" fill="{color}" />'
            f'<text x="{legend_x + 15:.0f}" y="{ly + 9:.0f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="8.5" font-weight="500">'
            f'{escape(s["label"])} ({fraction * 100:.1f}%)</text>'
        )

    body = "".join(parts)
    return {
        "available": True,
        "title": title,
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title=title,
            subtitle=subtitle,
            body=body,
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# TORNADO CHART (Sensitivity)
# ══════════════════════════════════════════════════════════════════════════════

def build_tornado_chart(
    bars: list[dict[str, Any]],
    *,
    baseline: float,
    output_unit: str = "MW",
    title: str = "Sensitivity Tornado",
    subtitle: str = "",
    primary_color: str = "#1a365d",
    secondary_color: str = "#2b6cb0",
) -> dict[str, Any]:
    """Tornado chart for sensitivity analysis.

    Each bar dict: {"label": str, "low": float, "high": float}.
    """
    bars = [b for b in bars if b.get("low") is not None and b.get("high") is not None]
    if not bars:
        return {"available": False, "title": title, "message": "No data.", "svg_markup": None}

    # Sort by spread (largest first)
    bars = sorted(bars, key=lambda b: abs(b["high"] - b["low"]), reverse=True)

    n = len(bars)
    w = CHART_WIDTH
    h = max(CHART_HEIGHT, _PAD_TOP + 30 + n * 28 + 30)

    label_w = 130
    plot_left = label_w + 10
    plot_right = w - _PAD_OUTER - 10
    plot_w = plot_right - plot_left

    all_vals = [b["low"] for b in bars] + [b["high"] for b in bars] + [baseline]
    v_min = min(all_vals)
    v_max = max(all_vals)
    pad = (v_max - v_min) * 0.1 or 0.1
    v_min -= pad
    v_max += pad
    v_range = v_max - v_min

    def x_pos(val: float) -> float:
        return plot_left + ((val - v_min) / v_range) * plot_w

    baseline_x = x_pos(baseline)
    bar_h = 16
    bar_gap = 28
    y_start = _PAD_TOP + 20

    primary_c = _c(primary_color, "#1a365d")
    secondary_c = _c(secondary_color, "#2b6cb0")

    parts: list[str] = []

    # Baseline vertical line
    parts.append(
        f'<line x1="{baseline_x:.1f}" y1="{y_start - 5}" '
        f'x2="{baseline_x:.1f}" y2="{y_start + n * bar_gap + 5}" '
        f'stroke="#9ca3af" stroke-width="1" stroke-dasharray="4,3" />'
    )
    parts.append(
        f'<text x="{baseline_x:.1f}" y="{y_start - 8}" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="8" text-anchor="middle">'
        f'Baseline: {baseline:.2f} {escape(output_unit)}</text>'
    )

    for idx, bar in enumerate(bars):
        cy = y_start + idx * bar_gap + bar_h / 2
        low_x = x_pos(bar["low"])
        high_x = x_pos(bar["high"])

        # Low side (left of baseline = red-ish, right = green-ish)
        if low_x < baseline_x:
            parts.append(
                f'<rect x="{low_x:.1f}" y="{cy - bar_h / 2:.1f}" '
                f'width="{baseline_x - low_x:.1f}" height="{bar_h}" rx="3" fill="#ef4444" opacity="0.75" />'
            )
        else:
            parts.append(
                f'<rect x="{baseline_x:.1f}" y="{cy - bar_h / 2:.1f}" '
                f'width="{low_x - baseline_x:.1f}" height="{bar_h}" rx="3" fill="#16a34a" opacity="0.75" />'
            )

        # High side
        if high_x > baseline_x:
            parts.append(
                f'<rect x="{baseline_x:.1f}" y="{cy - bar_h / 2:.1f}" '
                f'width="{high_x - baseline_x:.1f}" height="{bar_h}" rx="3" fill="#16a34a" opacity="0.75" />'
            )
        else:
            parts.append(
                f'<rect x="{high_x:.1f}" y="{cy - bar_h / 2:.1f}" '
                f'width="{baseline_x - high_x:.1f}" height="{bar_h}" rx="3" fill="#ef4444" opacity="0.75" />'
            )

        # Values on ends
        parts.append(
            f'<text x="{low_x - 4:.1f}" y="{cy + 3:.1f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="7.5" text-anchor="end">'
            f'{bar["low"]:.2f}</text>'
        )
        parts.append(
            f'<text x="{high_x + 4:.1f}" y="{cy + 3:.1f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="7.5" text-anchor="start">'
            f'{bar["high"]:.2f}</text>'
        )

        # Label on left
        parts.append(
            f'<text x="{label_w}" y="{cy + 3:.1f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">'
            f'{escape(bar["label"])}</text>'
        )

    body = "".join(parts)
    return {
        "available": True,
        "title": title,
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title=title,
            subtitle=subtitle,
            body=body,
        ),
    }
