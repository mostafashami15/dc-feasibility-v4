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
    """Grouped bar chart showing monthly mean, min, and max temperatures.

    Matches the frontend UI TemperatureChart (Recharts BarChart) with:
      - Max bars: red #ef4444 at 60% opacity
      - Mean bars: blue #3b82f6
      - Min bars: cyan #06b6d4 at 60% opacity
    """
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

    # UI-matching colors
    COLOR_MAX  = "#ef4444"
    COLOR_MEAN = "#3b82f6"
    COLOR_MIN  = "#06b6d4"

    all_vals = monthly_min + monthly_max
    lo = min(all_vals)
    hi = max(all_vals)
    margin = (hi - lo) * 0.12 or 2.0
    lo -= margin
    hi += margin

    w, h = CHART_WIDTH, CHART_HEIGHT + 70
    plot_left = _PAD_AXIS + 4
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 4
    plot_bottom = h - 34
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    group_w = plot_w / 12
    bar_w = min(group_w * 0.24, 14)
    bar_gap = 2

    def val_to_y(v: float) -> float:
        frac = (v - lo) / (hi - lo) if hi != lo else 0.5
        return plot_bottom - frac * plot_h

    # Zero line (if range spans 0)
    zero_line = ""
    if lo < 0 < hi:
        zy = val_to_y(0)
        zero_line = (
            f'<line x1="{plot_left}" y1="{zy:.1f}" '
            f'x2="{plot_right}" y2="{zy:.1f}" '
            'stroke="#d1d5db" stroke-width="1" stroke-dasharray="4 3" />'
        )

    # Grid lines + Y-axis ticks
    tick_parts: list[str] = []
    for tick_i in range(5):
        val = lo + (hi - lo) * tick_i / 4
        y = val_to_y(val)
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" '
            f'x2="{plot_right}" y2="{y:.1f}" '
            'stroke="#f0f0f0" stroke-width="1" />'
            f'<text x="{plot_left - 5}" y="{y + 3:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">{val:.0f}°C</text>'
        )

    # X-axis month labels
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    x_parts: list[str] = []
    for i, label in enumerate(month_labels):
        cx = plot_left + group_w * i + group_w / 2
        x_parts.append(
            f'<text x="{cx:.1f}" y="{plot_bottom + 14}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="middle">{label}</text>'
        )

    # Bars (3 per month: max, mean, min)
    bar_parts: list[str] = []
    baseline_y = val_to_y(max(lo, 0)) if lo < 0 else plot_bottom
    for i in range(12):
        cx = plot_left + group_w * i + group_w / 2
        total_bar_width = 3 * bar_w + 2 * bar_gap
        start_x = cx - total_bar_width / 2

        for j, (val, color, opacity) in enumerate([
            (monthly_max[i], COLOR_MAX, 0.6),
            (monthly_mean[i], COLOR_MEAN, 1.0),
            (monthly_min[i], COLOR_MIN, 0.6),
        ]):
            bx = start_x + j * (bar_w + bar_gap)
            by = val_to_y(val)
            if val >= 0:
                bar_top = by
                bar_height = baseline_y - by
            else:
                bar_top = baseline_y
                bar_height = by - baseline_y
            bar_height = max(bar_height, 1)
            bar_parts.append(
                f'<rect x="{bx:.1f}" y="{bar_top:.1f}" width="{bar_w:.1f}" '
                f'height="{bar_height:.1f}" rx="2" fill="{color}" opacity="{opacity}" />'
            )

    # Legend
    ly = 32
    legend = (
        f'<rect x="{w - 200}" y="{ly - 4}" width="10" height="10" rx="2" fill="{COLOR_MAX}" opacity="0.6" />'
        f'<text x="{w - 186}" y="{ly + 5}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="8">Max</text>'
        f'<rect x="{w - 155}" y="{ly - 4}" width="10" height="10" rx="2" fill="{COLOR_MEAN}" />'
        f'<text x="{w - 141}" y="{ly + 5}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="8">Mean</text>'
        f'<rect x="{w - 107}" y="{ly - 4}" width="10" height="10" rx="2" fill="{COLOR_MIN}" opacity="0.6" />'
        f'<text x="{w - 93}" y="{ly + 5}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="8">Min</text>'
    )

    body = (
        "".join(tick_parts)
        + zero_line
        + "".join(bar_parts)
        + "".join(x_parts)
        + legend
    )

    return {
        "available": True,
        "title": "Monthly Temperature Chart",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="Monthly Temperature Profile",
            subtitle="Monthly mean, min, and max dry-bulb temperatures (°C).",
            body=body,
        ),
    }


def build_cooling_suitability_chart(
    free_cooling_rows: list[dict[str, Any]],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Stacked bar chart matching the frontend FreeCoolingChart UI.

    Each bar stacks three segments:
      - Free Cooling (green #22c55e)
      - Partial / Economic (yellow #facc15)
      - Mechanical (red #ef4444)
    Suitability badges and percentage labels appear below the chart.
    """
    if not free_cooling_rows:
        return {
            "available": False,
            "title": "Free Cooling Analysis",
            "message": "No free-cooling data available.",
            "svg_markup": None,
        }

    COLOR_FREE = "#22c55e"
    COLOR_PARTIAL = "#facc15"
    COLOR_MECH = "#ef4444"

    n = len(free_cooling_rows)
    w, h = CHART_WIDTH, CHART_HEIGHT + 120
    plot_left = 60
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 4
    plot_bottom = h - 78
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    upper = 8760.0  # total hours in a year
    group_w = plot_w / max(n, 1)
    bar_w = min(group_w * 0.55, 50)

    def val_to_h(v: float) -> float:
        return (v / upper) * plot_h

    # Y-axis ticks
    tick_parts: list[str] = []
    for i in range(5):
        val = upper * i / 4
        y = plot_bottom - val_to_h(val)
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" '
            f'x2="{plot_right}" y2="{y:.1f}" '
            'stroke="#f0f0f0" stroke-width="1" />'
            f'<text x="{plot_left - 5}" y="{y + 3:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">{val:.0f}</text>'
        )
    # Y-axis label
    tick_parts.append(
        f'<text x="{plot_left - 5}" y="{plot_top - 8}" fill="#9ca3af" '
        f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">Hours</text>'
    )

    def _shorten_cooling_label(ct: str) -> str:
        return (ct
            .replace("Air-Cooled ", "")
            .replace("Water-Cooled ", "W-")
            .replace(" + Economizer", "+Econ")
            .replace("Rear Door Heat Exchanger (RDHx)", "RDHx")
            .replace("Direct Liquid Cooling (DLC / Cold Plate)", "DLC")
            .replace("Immersion Cooling (Single-Phase)", "Immersion")
            .replace("Free Cooling — Dry Cooler (Chiller-less)", "Dry Cooler"))

    bar_parts: list[str] = []
    badge_parts: list[str] = []
    for idx, item in enumerate(free_cooling_rows):
        free_h = float(item.get("free_cooling_hours") or 0.0)
        partial_h = float(item.get("partial_hours") or 0.0)
        mech_h = float(item.get("mechanical_hours") or 0.0)
        suitability = str(item.get("suitability") or "")
        fraction = float(item.get("free_cooling_fraction") or 0.0)

        cx = plot_left + group_w * idx + group_w / 2
        bx = cx - bar_w / 2

        # Stack bottom-up: free, partial, mechanical
        y_cursor = plot_bottom
        for seg_val, seg_color in [
            (free_h, COLOR_FREE),
            (partial_h, COLOR_PARTIAL),
            (mech_h, COLOR_MECH),
        ]:
            seg_px = val_to_h(seg_val)
            if seg_px > 0:
                ry = y_cursor - seg_px
                rx_top = "2" if seg_color == COLOR_MECH else "0"
                bar_parts.append(
                    f'<rect x="{bx:.1f}" y="{ry:.1f}" width="{bar_w:.1f}" '
                    f'height="{seg_px:.1f}" fill="{seg_color}" />'
                )
                y_cursor -= seg_px

        # X-axis label (shortened cooling type)
        label = _shorten_cooling_label(str(item.get("cooling_type") or ""))
        wrapped = _wrap_label(label, max_chars=10, max_lines=2)
        for li, line in enumerate(wrapped):
            bar_parts.append(
                f'<text x="{cx:.1f}" y="{plot_bottom + 13 + li * 10:.1f}" fill="#6b7280" '
                f'font-family="system-ui,sans-serif" font-size="7.5" '
                f'text-anchor="middle">{escape(line)}</text>'
            )

        # Suitability badge below x-axis labels
        suit_bg = (
            "#dbeafe" if "excellent" in suitability.lower()
            else "#dcfce7" if "good" in suitability.lower()
            else "#fef9c3" if "marginal" in suitability.lower()
            else "#fee2e2"
        )
        suit_fg = (
            "#1e40af" if "excellent" in suitability.lower()
            else "#166534" if "good" in suitability.lower()
            else "#854d0e" if "marginal" in suitability.lower()
            else "#991b1b"
        )
        badge_y = plot_bottom + 13 + len(wrapped) * 10 + 4
        badge_text = suitability.replace("_", " ")
        tw = len(badge_text) * 4.2 + 10
        badge_parts.append(
            f'<rect x="{cx - tw / 2:.1f}" y="{badge_y - 7:.1f}" width="{tw:.1f}" '
            f'height="13" rx="6.5" fill="{suit_bg}" />'
            f'<text x="{cx:.1f}" y="{badge_y + 3:.1f}" fill="{suit_fg}" '
            f'font-family="system-ui,sans-serif" font-size="6.5" font-weight="600" '
            f'text-anchor="middle">{escape(badge_text)}</text>'
        )
        # Percentage label
        badge_parts.append(
            f'<text x="{cx:.1f}" y="{badge_y + 16:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" '
            f'text-anchor="middle">{fraction * 100:.0f}% free</text>'
        )

    # Legend
    ly = 32
    legend = (
        f'<rect x="{w - 240}" y="{ly - 4}" width="10" height="10" rx="2" fill="{COLOR_FREE}" />'
        f'<text x="{w - 226}" y="{ly + 5}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="8">Free Cooling</text>'
        f'<rect x="{w - 160}" y="{ly - 4}" width="10" height="10" rx="2" fill="{COLOR_PARTIAL}" />'
        f'<text x="{w - 146}" y="{ly + 5}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="8">Partial</text>'
        f'<rect x="{w - 108}" y="{ly - 4}" width="10" height="10" rx="2" fill="{COLOR_MECH}" />'
        f'<text x="{w - 94}" y="{ly + 5}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="8">Mechanical</text>'
    )

    body = "".join(tick_parts) + "".join(bar_parts) + "".join(badge_parts) + legend

    return {
        "available": True,
        "title": "Free Cooling Analysis",
        "message": "",
        "svg_markup": _svg_shell(
            width=w,
            height=h,
            title="Free Cooling Analysis",
            subtitle="Annual hours by cooling mode for each topology.",
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
    """Vertical bar chart showing IT capacity at statistical checkpoints.

    Enhanced: larger bars, value labels above each bar, color-coded by level.
    """
    checkpoints = [
        ("Best\nhour", metrics.get("it_capacity_best_mw"), "#16a34a"),
        ("Mean", metrics.get("it_capacity_mean_mw"), "#2563eb"),
        ("P90", metrics.get("it_capacity_p90_mw"), "#7c3aed"),
        ("P99\n(Committed)", metrics.get("it_capacity_p99_mw") or metrics.get("committed_it_mw"), "#1a365d"),
        ("Worst\nhour", metrics.get("it_capacity_worst_mw"), "#dc2626"),
        ("Nominal\ndesign", metrics.get("it_load_mw"), "#6b7280"),
    ]
    available = [(label, float(val), color) for label, val, color in checkpoints if val is not None]
    if len(available) < 2:
        return {
            "available": False,
            "title": "IT Capacity Spectrum",
            "message": "Insufficient data for IT capacity spectrum chart.",
            "svg_markup": None,
        }

    primary = _c(primary_color, "#1a365d")

    max_val = max(v for _, v, _ in available)
    upper = max_val * 1.18

    w, h = CHART_WIDTH, CHART_HEIGHT + 20
    plot_left = 60
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 10
    plot_bottom = h - 50
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top
    n = len(available)
    group_w = plot_w / max(n, 1)
    bar_w = min(group_w * 0.6, 56)

    # Y-axis grid + ticks
    tick_parts: list[str] = []
    for i in range(5):
        val = upper * i / 4
        y = plot_bottom - (val / upper) * plot_h
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" '
            'stroke="#f0f0f0" stroke-width="1" />'
            f'<text x="{plot_left - 5}" y="{y + 3:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">{val:.1f}</text>'
        )
    tick_parts.append(
        f'<text x="{plot_left - 5}" y="{plot_top - 8}" fill="#9ca3af" '
        f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">MW</text>'
    )

    bar_parts: list[str] = []
    for idx, (label, value, color) in enumerate(available):
        cx = plot_left + group_w * idx + group_w / 2
        bx = cx - bar_w / 2
        bar_h_px = (value / upper) * plot_h
        by = plot_bottom - bar_h_px

        # Bar
        bar_parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h_px:.1f}" '
            f'rx="3" fill="{color}" opacity="0.85" />'
        )
        # Value above bar
        bar_parts.append(
            f'<text x="{cx:.1f}" y="{by - 6:.1f}" fill="{color}" '
            f'font-family="system-ui,sans-serif" font-size="9" font-weight="700" '
            f'text-anchor="middle">{value:.2f}</text>'
        )
        # Multi-line X-axis label
        lines = label.split("\n")
        for li, line in enumerate(lines):
            is_key = "P99" in line or "Committed" in line
            bar_parts.append(
                f'<text x="{cx:.1f}" y="{plot_bottom + 14 + li * 10:.1f}" fill="#374151" '
                f'font-family="system-ui,sans-serif" font-size="7.5" '
                f'font-weight="{"700" if is_key else "400"}" '
                f'text-anchor="middle">{escape(line)}</text>'
            )

    body = "".join(tick_parts) + "".join(bar_parts)
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
    """Compact donut-style PUE breakdown — IT vs overhead power."""
    if pue is None or pue <= 0:
        return {"available": False, "title": "PUE Breakdown", "message": "No PUE data.", "svg_markup": None}

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    it_mw = float(power_data.get("it_load_mw") or 0)
    facility_mw = float(power_data.get("facility_power_mw") or 0)
    overhead_mw = facility_mw - it_mw if facility_mw > it_mw else 0
    if it_mw <= 0:
        return {"available": False, "title": "PUE Breakdown", "message": "No IT load.", "svg_markup": None}

    total = it_mw + overhead_mw
    it_pct = (it_mw / total * 100) if total > 0 else 0
    oh_pct = 100 - it_pct

    w, h = CHART_WIDTH, 220
    cx, cy = w // 2, 120
    r_outer = 62
    r_inner = 40

    it_angle = (it_pct / 100) * 2 * math.pi
    oh_angle = (oh_pct / 100) * 2 * math.pi

    def _arc(sa: float, ea: float, ro: float, ri: float) -> str:
        x1o = cx + ro * math.cos(sa - math.pi / 2)
        y1o = cy + ro * math.sin(sa - math.pi / 2)
        x2o = cx + ro * math.cos(ea - math.pi / 2)
        y2o = cy + ro * math.sin(ea - math.pi / 2)
        x1i = cx + ri * math.cos(ea - math.pi / 2)
        y1i = cy + ri * math.sin(ea - math.pi / 2)
        x2i = cx + ri * math.cos(sa - math.pi / 2)
        y2i = cy + ri * math.sin(sa - math.pi / 2)
        large = 1 if (ea - sa) > math.pi else 0
        return (f'M {x1o:.1f},{y1o:.1f} A {ro},{ro} 0 {large},1 {x2o:.1f},{y2o:.1f} '
                f'L {x1i:.1f},{y1i:.1f} A {ri},{ri} 0 {large},0 {x2i:.1f},{y2i:.1f} Z')

    arcs = ""
    if it_pct >= 99.5:
        arcs = f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="{primary}" /><circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="white" />'
    elif oh_pct >= 99.5:
        arcs = f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="{secondary}" /><circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="white" />'
    else:
        arcs = f'<path d="{_arc(0, it_angle, r_outer, r_inner)}" fill="{primary}" /><path d="{_arc(it_angle, it_angle + oh_angle, r_outer, r_inner)}" fill="{secondary}" opacity="0.7" />'

    center_text = (
        f'<text x="{cx}" y="{cy - 4}" fill="{primary}" font-family="system-ui,sans-serif" '
        f'font-size="18" font-weight="800" text-anchor="middle">{pue:.3f}</text>'
        f'<text x="{cx}" y="{cy + 9}" fill="#6b7280" font-family="system-ui,sans-serif" '
        f'font-size="7" text-anchor="middle">Annual PUE</text>'
    )

    # Legend — single row below donut
    ly = cy + r_outer + 16
    legend = (
        f'<rect x="{cx - 120}" y="{ly}" width="8" height="8" rx="2" fill="{primary}" />'
        f'<text x="{cx - 109}" y="{ly + 7}" fill="#374151" font-family="system-ui,sans-serif" font-size="7.5">'
        f'IT Load {it_mw:.2f} MW ({it_pct:.1f}%)</text>'
        f'<rect x="{cx + 15}" y="{ly}" width="8" height="8" rx="2" fill="{secondary}" opacity="0.7" />'
        f'<text x="{cx + 26}" y="{ly + 7}" fill="#374151" font-family="system-ui,sans-serif" font-size="7.5">'
        f'Overhead {overhead_mw:.2f} MW ({oh_pct:.1f}%)</text>'
    )

    body = arcs + center_text + legend
    return {
        "available": True,
        "title": "PUE Breakdown",
        "message": "",
        "svg_markup": _svg_shell(width=w, height=h, title="PUE Breakdown",
                                  subtitle=f"IT vs overhead power split — PUE {pue:.3f}", body=body),
    }


def build_power_chain_waterfall(
    power_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Sankey-style diagram showing power flow from grid to IT load.

    Nodes are drawn as rounded rectangles on left/middle/right columns.
    Flows are drawn as curved bands whose thickness encodes MW.
    """
    procurement_mw = float(power_data.get("procurement_power_mw") or 0)
    facility_mw = float(power_data.get("facility_power_mw") or 0)
    it_load_mw = float(power_data.get("it_load_mw") or 0)

    if facility_mw <= 0 and it_load_mw <= 0:
        return {"available": False, "title": "Power Flow", "message": "No power data.", "svg_markup": None}

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    overhead_mw = max(facility_mw - it_load_mw, 0)
    procurement_overhead_mw = max(procurement_mw - facility_mw, 0)

    w, h = CHART_WIDTH, 260
    # Node positions: 3 columns
    col_left = 60
    col_mid = w // 2 - 30
    col_right = w - 130
    node_w = 60
    node_radius = 6

    # Scale: max value to pixel height
    max_mw = max(procurement_mw, facility_mw, it_load_mw, 0.001)
    max_node_h = 100

    def mw_to_h(mw: float) -> float:
        return max((mw / max_mw) * max_node_h, 12)

    # Define nodes
    top_y = _PAD_TOP + 20

    # Left column: Grid/Procurement
    grid_h = mw_to_h(procurement_mw)
    grid_y = top_y + (max_node_h - grid_h) / 2

    # Middle column: Facility
    fac_h = mw_to_h(facility_mw)
    fac_y = top_y + (max_node_h - fac_h) / 2

    # Right column: IT Load + Overhead (stacked)
    it_h = mw_to_h(it_load_mw)
    oh_h = mw_to_h(overhead_mw) if overhead_mw > 0.001 else 0
    total_right_h = it_h + oh_h + (6 if oh_h > 0 else 0)
    right_top = top_y + (max_node_h - total_right_h) / 2
    it_y = right_top
    oh_y = right_top + it_h + 6

    parts: list[str] = []

    # ── Flow bands (drawn first, behind nodes) ──
    def _flow_band(x1: float, y1_top: float, y1_bot: float,
                   x2: float, y2_top: float, y2_bot: float,
                   color: str, opacity: float = 0.18) -> str:
        mx = (x1 + x2) / 2
        return (
            f'<path d="M{x1:.1f},{y1_top:.1f} C{mx:.1f},{y1_top:.1f} {mx:.1f},{y2_top:.1f} {x2:.1f},{y2_top:.1f} '
            f'L{x2:.1f},{y2_bot:.1f} C{mx:.1f},{y2_bot:.1f} {mx:.1f},{y1_bot:.1f} {x1:.1f},{y1_bot:.1f} Z" '
            f'fill="{color}" opacity="{opacity}" />'
        )

    # Grid → Facility (full width of facility node)
    if procurement_mw > 0.001:
        parts.append(_flow_band(
            col_left + node_w, grid_y, grid_y + grid_h,
            col_mid, fac_y, fac_y + fac_h,
            primary, 0.15,
        ))

    # Facility → IT Load
    if it_load_mw > 0.001:
        # The IT flow occupies the top portion of facility node
        fac_it_ratio = it_load_mw / max(facility_mw, 0.001)
        fac_it_h = fac_h * fac_it_ratio
        parts.append(_flow_band(
            col_mid + node_w, fac_y, fac_y + fac_it_h,
            col_right, it_y, it_y + it_h,
            "#16a34a", 0.18,
        ))

    # Facility → Overhead
    if overhead_mw > 0.001 and oh_h > 0:
        fac_it_ratio = it_load_mw / max(facility_mw, 0.001)
        fac_oh_start = fac_y + fac_h * fac_it_ratio
        parts.append(_flow_band(
            col_mid + node_w, fac_oh_start, fac_y + fac_h,
            col_right, oh_y, oh_y + oh_h,
            "#ea580c", 0.15,
        ))

    # ── Nodes ──
    def _node(x: float, y: float, nw: float, nh: float,
              color: str, label: str, value_str: str) -> str:
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{nw}" height="{nh:.1f}" '
            f'rx="{node_radius}" fill="{color}" />'
            f'<text x="{x + nw / 2:.1f}" y="{y + nh / 2 - 4:.1f}" fill="white" '
            f'font-family="system-ui,sans-serif" font-size="8" font-weight="700" '
            f'text-anchor="middle">{escape(label)}</text>'
            f'<text x="{x + nw / 2:.1f}" y="{y + nh / 2 + 7:.1f}" fill="rgba(255,255,255,0.85)" '
            f'font-family="system-ui,sans-serif" font-size="7.5" '
            f'text-anchor="middle">{escape(value_str)}</text>'
        )

    if procurement_mw > 0.001:
        parts.append(_node(col_left, grid_y, node_w, grid_h, primary, "Grid", f"{procurement_mw:.2f} MW"))
    parts.append(_node(col_mid, fac_y, node_w, fac_h, secondary, "Facility", f"{facility_mw:.2f} MW"))
    parts.append(_node(col_right, it_y, node_w, it_h, "#16a34a", "IT Load", f"{it_load_mw:.2f} MW"))
    if overhead_mw > 0.001 and oh_h > 0:
        parts.append(_node(col_right, oh_y, node_w, oh_h, "#ea580c", "Overhead", f"{overhead_mw:.2f} MW"))

    # Procurement overhead (small label if present)
    if procurement_overhead_mw > 0.01:
        parts.append(
            f'<text x="{(col_left + col_mid) / 2 + node_w / 2:.1f}" y="{top_y + max_node_h + 18:.1f}" '
            f'fill="#94a3b8" font-family="system-ui,sans-serif" font-size="7" text-anchor="middle">'
            f'Procurement overhead: {procurement_overhead_mw:.2f} MW</text>'
        )

    body = "".join(parts)
    return {
        "available": True,
        "title": "Power Flow",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="Power Flow (Sankey)",
            subtitle="Power flow from grid procurement through facility to IT load and overhead.",
            body=body,
        ),
    }


def build_energy_decomposition_sankey(
    components: list[dict[str, Any]],
    total_facility_kwh: float,
    total_it_kwh: float,
    total_overhead_kwh: float,
    *,
    primary_color: str = "#1a365d",
    secondary_color: str = "#2b6cb0",
) -> dict[str, Any]:
    """Three-tier Sankey: Total Facility → IT Energy + Overhead → overhead sub-categories.

    ``components`` is a list of dicts with keys ``label`` and ``energy_kwh``.
    Font sizes are kept small to avoid readability issues inside narrow bands.
    """
    if total_facility_kwh <= 0:
        return {"available": False, "title": "Energy Decomposition", "message": "No data.", "svg_markup": None}

    primary = _c(primary_color, "#1a365d")
    secondary = _c(secondary_color, "#2b6cb0")

    # Convert to GWh for display
    total_fac_gwh = total_facility_kwh / 1_000_000
    it_gwh = total_it_kwh / 1_000_000
    oh_gwh = total_overhead_kwh / 1_000_000

    w, h = 540, 232
    # Three compact columns to keep the Sankey legible inside the split layout.
    col_left = 24
    col_mid = 170
    col_right = 326
    node_w = 46
    detail_node_w = 84
    node_radius = 6

    top_y = _PAD_TOP + 2
    max_node_h = 98

    # Scale helper — all heights relative to total facility energy
    def _h(kwh: float) -> float:
        return max((kwh / total_facility_kwh) * max_node_h, 10)

    # ── Left: Total Facility Energy ──
    fac_h = _h(total_facility_kwh)
    fac_y = top_y + (max_node_h - fac_h) / 2

    # ── Middle: IT Energy + Overhead Energy (stacked) ──
    it_h = _h(total_it_kwh)
    oh_h = _h(total_overhead_kwh)
    gap = 6
    mid_total = it_h + oh_h + gap
    mid_top = top_y + (max_node_h - mid_total) / 2
    it_y = mid_top
    oh_y = mid_top + it_h + gap

    # ── Right: Overhead sub-components (stacked) ──
    comp_items = [c for c in components if c.get("energy_kwh", 0) > 0]
    comp_heights = [_h(c["energy_kwh"]) for c in comp_items]
    comp_gap = 4
    right_total = sum(comp_heights) + max(len(comp_heights) - 1, 0) * comp_gap
    right_top = top_y + (max_node_h - right_total) / 2

    # Overhead sub-category colours
    comp_colors = ["#ef4444", "#3b82f6", "#8b5cf6", "#f59e0b", "#6b7280"]

    parts: list[str] = []

    # ── Flow band helper ──
    def _flow(x1: float, y1t: float, y1b: float,
              x2: float, y2t: float, y2b: float,
              color: str, opacity: float = 0.15) -> str:
        mx = (x1 + x2) / 2
        return (
            f'<path d="M{x1:.1f},{y1t:.1f} C{mx:.1f},{y1t:.1f} {mx:.1f},{y2t:.1f} {x2:.1f},{y2t:.1f} '
            f'L{x2:.1f},{y2b:.1f} C{mx:.1f},{y2b:.1f} {mx:.1f},{y1b:.1f} {x1:.1f},{y1b:.1f} Z" '
            f'fill="{color}" opacity="{opacity}" />'
        )

    # Flow: Facility → IT Energy (top portion of facility)
    fac_it_ratio = total_it_kwh / total_facility_kwh
    fac_it_h = fac_h * fac_it_ratio
    parts.append(_flow(
        col_left + node_w, fac_y, fac_y + fac_it_h,
        col_mid, it_y, it_y + it_h,
        "#16a34a", 0.18,
    ))

    # Flow: Facility → Overhead (bottom portion of facility)
    parts.append(_flow(
        col_left + node_w, fac_y + fac_it_h, fac_y + fac_h,
        col_mid, oh_y, oh_y + oh_h,
        "#ea580c", 0.15,
    ))

    # Flows: Overhead → each sub-component
    src_cursor = oh_y
    dst_cursor = right_top
    for idx, comp in enumerate(comp_items):
        ch = comp_heights[idx]
        src_ratio = comp["energy_kwh"] / total_overhead_kwh if total_overhead_kwh > 0 else 0
        src_band = oh_h * src_ratio
        color = comp_colors[idx % len(comp_colors)]
        parts.append(_flow(
            col_mid + node_w, src_cursor, src_cursor + src_band,
            col_right, dst_cursor, dst_cursor + ch,
            color, 0.18,
        ))
        src_cursor += src_band
        dst_cursor += ch + comp_gap

    # ── Node drawing helper ──
    def _node(x: float, y: float, nw: float, nh: float,
              color: str, label: str, value_str: str, pct_str: str = "") -> str:
        # Adaptive font sizing: smaller for narrow bands
        label_fs = "6.8" if nh < 24 else "7.8"
        val_fs = "6.3" if nh < 24 else "7.0"
        # For very narrow nodes, put text beside rather than inside
        if nh < 16:
            return (
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{nw}" height="{nh:.1f}" '
                f'rx="{node_radius}" fill="{color}" />'
                f'<text x="{x + nw + 4:.1f}" y="{y + nh / 2 + 3:.1f}" fill="{color}" '
                f'font-family="system-ui,sans-serif" font-size="6.6" font-weight="600" '
                f'text-anchor="start">{escape(label)}'
                f'{" · " + value_str if value_str else ""}'
                f'{" · " + pct_str if pct_str else ""}</text>'
            )
        label_y = y + nh / 2 - 2 if not pct_str else y + nh / 2 - 5
        val_y = y + nh / 2 + 6 if not pct_str else y + nh / 2 + 3
        pct_y = y + nh / 2 + 11
        result = (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{nw}" height="{nh:.1f}" '
            f'rx="{node_radius}" fill="{color}" />'
            f'<text x="{x + nw / 2:.1f}" y="{label_y:.1f}" fill="white" '
            f'font-family="system-ui,sans-serif" font-size="{label_fs}" font-weight="700" '
            f'text-anchor="middle">{escape(label)}</text>'
            f'<text x="{x + nw / 2:.1f}" y="{val_y:.1f}" fill="rgba(255,255,255,0.85)" '
            f'font-family="system-ui,sans-serif" font-size="{val_fs}" '
            f'text-anchor="middle">{escape(value_str)}</text>'
        )
        if pct_str and nh >= 30:
            result += (
                f'<text x="{x + nw / 2:.1f}" y="{pct_y:.1f}" fill="rgba(255,255,255,0.7)" '
                f'font-family="system-ui,sans-serif" font-size="6.0" '
                f'text-anchor="middle">{escape(pct_str)}</text>'
            )
        return result

    # Left node: Total Facility
    parts.append(_node(col_left, fac_y, node_w, fac_h, primary,
                        "Total Facility", f"{total_fac_gwh:.2f} GWh"))

    # Middle nodes
    parts.append(_node(col_mid, it_y, node_w, it_h, "#16a34a",
                        "IT Energy", f"{it_gwh:.2f} GWh",
                        f"{total_it_kwh / total_facility_kwh * 100:.1f}%"))
    parts.append(_node(col_mid, oh_y, node_w, oh_h, "#ea580c",
                        "Overhead", f"{oh_gwh:.2f} GWh",
                        f"{total_overhead_kwh / total_facility_kwh * 100:.1f}%"))

    # Right nodes: sub-components
    cursor_y = right_top
    for idx, comp in enumerate(comp_items):
        ch = comp_heights[idx]
        color = comp_colors[idx % len(comp_colors)]
        gwh = comp["energy_kwh"] / 1_000_000
        pct = comp["energy_kwh"] / total_overhead_kwh * 100 if total_overhead_kwh > 0 else 0
        # Shortened labels for narrow nodes
        short_labels = {
            "Electrical losses": "Elec. Losses",
            "Fans and pumps": "Fans/Pumps",
            "Cooling compressor and heat rejection": "Cooling",
            "Economizer overhead": "Economizer",
            "Miscellaneous fixed loads": "Misc. Fixed",
        }
        label = short_labels.get(comp["label"], comp["label"])
        parts.append(_node(col_right, cursor_y, detail_node_w, ch, color,
                            label, f"{gwh:.2f} GWh", f"{pct:.1f}%"))
        cursor_y += ch + comp_gap

    # Column headers
    for cx_pos, lbl in [(col_left + node_w / 2, "Source"),
                         (col_mid + node_w / 2, "Split"),
                         (col_right + detail_node_w / 2, "Overhead Detail")]:
        parts.append(
            f'<text x="{cx_pos:.1f}" y="{top_y - 6:.1f}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="7.2" font-weight="600" '
            f'text-anchor="middle">{lbl}</text>'
        )

    body = "".join(parts)
    return {
        "available": True,
        "title": "Energy Decomposition",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="PUE Energy Decomposition (Sankey)",
            subtitle="Energy flow: total facility → IT + overhead → overhead sub-categories",
            body=body,
        ),
    }


def build_pue_minmax_chart(
    pue_min: float,
    pue_avg: float,
    pue_max: float,
    *,
    primary_color: str = "#1a365d",
) -> dict[str, Any]:
    """Compact horizontal bar/gauge showing PUE min, avg, max."""
    primary = _c(primary_color, "#1a365d")

    w, h = CHART_WIDTH, 80
    bar_y = 52
    bar_h = 10
    margin_l = 60
    margin_r = 60
    bar_w = w - margin_l - margin_r

    # Determine display range with some padding
    lo = max(pue_min - 0.05, 1.0)
    hi = pue_max + 0.05

    def _x(val: float) -> float:
        if hi <= lo:
            return margin_l + bar_w / 2
        return margin_l + (val - lo) / (hi - lo) * bar_w

    parts: list[str] = []

    # Background bar
    parts.append(
        f'<rect x="{margin_l}" y="{bar_y}" width="{bar_w}" height="{bar_h}" '
        f'rx="5" fill="#f3f4f6" />'
    )

    # Filled range bar (min to max)
    x_min = _x(pue_min)
    x_max = _x(pue_max)
    parts.append(
        f'<rect x="{x_min:.1f}" y="{bar_y}" width="{max(x_max - x_min, 2):.1f}" '
        f'height="{bar_h}" rx="5" fill="{primary}" opacity="0.2" />'
    )

    # Average marker (diamond)
    x_avg = _x(pue_avg)
    parts.append(
        f'<polygon points="{x_avg:.1f},{bar_y - 2} {x_avg + 5:.1f},{bar_y + bar_h / 2:.1f} '
        f'{x_avg:.1f},{bar_y + bar_h + 2:.1f} {x_avg - 5:.1f},{bar_y + bar_h / 2:.1f}" '
        f'fill="{primary}" />'
    )

    # Labels
    for val, label, anchor, x_pos in [
        (pue_min, "Min", "end", margin_l - 6),
        (pue_avg, "Avg", "middle", x_avg),
        (pue_max, "Max", "start", w - margin_r + 6),
    ]:
        ly = bar_y - 8 if label == "Avg" else bar_y + bar_h / 2 + 3
        parts.append(
            f'<text x="{x_pos:.1f}" y="{ly:.1f}" fill="{primary}" '
            f'font-family="system-ui,sans-serif" font-size="11" font-weight="700" '
            f'text-anchor="{anchor}">{val:.3f}</text>'
        )
        label_y = ly + 11 if label == "Avg" else ly + 11
        parts.append(
            f'<text x="{x_pos:.1f}" y="{label_y:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" '
            f'text-anchor="{anchor}">{label}</text>'
        )

    body = "".join(parts)
    return {
        "available": True,
        "title": "PUE Range",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="PUE Range",
            subtitle=f"Annual min / average / max",
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
    w, h = CHART_WIDTH, CHART_HEIGHT + 90
    plot_left = 60
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 10
    plot_bottom = h - 62
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


def build_daily_pue_profile_chart(
    daily_profiles: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Line chart showing daily PUE range and average across the year."""
    days = daily_profiles.get("days") or []
    if not days or len(days) < 2:
        return {"available": False, "title": "Daily PUE Profile", "message": "Insufficient data.", "svg_markup": None}

    secondary = _c(secondary_color, "#2b6cb0")

    w, h = CHART_WIDTH, CHART_HEIGHT + 20
    plot_left = 70
    plot_right = w - 50
    plot_top = _PAD_TOP + 5
    plot_bottom = h - 40
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    pue_mins = [d["pue_min"] for d in days]
    pue_maxs = [d["pue_max"] for d in days]
    pue_avgs = [d["pue_avg"] for d in days]
    n = len(days)

    pue_lo = min(pue_mins) * 0.98 if min(pue_mins) > 0 else 1.0
    pue_hi = max(pue_maxs) * 1.02 if max(pue_maxs) > 0 else 2.0

    def x_pos(i: int) -> float:
        return plot_left + (i / max(n - 1, 1)) * plot_w

    def y_pue(val: float) -> float:
        if pue_hi == pue_lo:
            return plot_top + plot_h / 2
        return plot_bottom - ((val - pue_lo) / (pue_hi - pue_lo)) * plot_h

    # PUE range band
    band_top = " ".join(f"{x_pos(i):.1f},{y_pue(pue_maxs[i]):.1f}" for i in range(n))
    band_bottom = " ".join(f"{x_pos(i):.1f},{y_pue(pue_mins[i]):.1f}" for i in range(n - 1, -1, -1))
    band = f'<polygon points="{band_top} {band_bottom}" fill="{secondary}" opacity="0.15" />'

    # PUE avg line
    avg_points = " ".join(f"{x_pos(i):.1f},{y_pue(pue_avgs[i]):.1f}" for i in range(n))
    avg_line = f'<polyline points="{avg_points}" fill="none" stroke="{secondary}" stroke-width="2" />'

    # Y-axis ticks
    tick_parts: list[str] = []
    for i in range(5):
        frac = i / 4
        val = pue_lo + (pue_hi - pue_lo) * frac
        y = plot_bottom - frac * plot_h
        tick_parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{plot_left - 6}" y="{y + 3:.1f}" fill="#9ca3af" font-family="system-ui,sans-serif" '
            f'font-size="8" text-anchor="end">{val:.2f}</text>'
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
        f'transform="rotate(-90 14 {(plot_top + plot_bottom) / 2:.1f})">PUE</text>'
    )

    body = "".join(tick_parts) + band + avg_line + "".join(x_labels) + y_label
    return {
        "available": True,
        "title": "Daily PUE Profile",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="Daily PUE Profile",
            subtitle="Range (band) and average (line) of PUE across the year.",
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


def build_firm_capacity_deficit_chart(
    hourly_it_kw: list[float],
    firm_kw: float,
    mean_kw: float,
    *,
    primary_color: str = "#1a365d",
    secondary_color: str = "#2b6cb0",
) -> dict[str, Any]:
    """Hourly IT capacity chart with firm/mean lines and shaded deficit area.

    Shows the full year's hourly IT capacity with:
    - Blue line: hourly IT capacity
    - Dashed red line: Mean capacity
    - Dashed green line: Firm (P99) capacity
    - Red shaded area: where IT capacity dips below Mean (deficit to compensate)
    - The deficit energy integral shown in the legend
    """
    if not hourly_it_kw or len(hourly_it_kw) < 24:
        return {"available": False, "title": "Capacity Deficit", "message": "No hourly data.", "svg_markup": None}

    primary = _c(primary_color, "#1a365d")

    n = len(hourly_it_kw)
    w, h = 680, 240  # compact size for report print

    plot_left = _PAD_OUTER + _PAD_AXIS
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 8
    plot_bottom = h - 30
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    # Value range
    it_min = min(hourly_it_kw)
    it_max = max(hourly_it_kw)
    val_lo = max(it_min * 0.95, 0)
    val_hi = it_max * 1.05

    def x_pos(i: int) -> float:
        return plot_left + (i / max(n - 1, 1)) * plot_w

    def y_pos(val: float) -> float:
        if val_hi <= val_lo:
            return plot_top + plot_h / 2
        return plot_bottom - ((val - val_lo) / (val_hi - val_lo)) * plot_h

    parts: list[str] = []

    # Grid lines and Y-axis labels
    for frac_i in range(5):
        frac = frac_i / 4
        val = val_lo + (val_hi - val_lo) * frac
        y = plot_bottom - frac * plot_h
        parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" '
            f'stroke="#f3f4f6" stroke-width="1" />'
            f'<text x="{plot_left - 6}" y="{y + 3:.1f}" fill="#9ca3af" font-family="system-ui,sans-serif" '
            f'font-size="7" text-anchor="end">{val / 1000:.1f}</text>'
        )

    # Deficit area (below MEAN line — red shaded)
    # This is the energy deficit that mitigation strategies must cover
    # to raise guaranteed capacity from P99 to Mean.
    # Sample every ~12 hours for SVG efficiency (730 points for 8760 hours)
    step = max(n // 730, 1)
    sampled_indices = list(range(0, n, step))
    if sampled_indices[-1] != n - 1:
        sampled_indices.append(n - 1)

    has_deficit = any(hourly_it_kw[i] < mean_kw for i in sampled_indices)
    if has_deficit:
        # Build fill between mean line and IT capacity where IT < mean
        deficit_path_parts: list[str] = []
        in_deficit = False
        for idx in sampled_indices:
            x = x_pos(idx)
            it_val = hourly_it_kw[idx]
            if it_val < mean_kw:
                if not in_deficit:
                    # Start deficit region
                    deficit_path_parts.append(f"M{x:.1f},{y_pos(mean_kw):.1f}")
                    in_deficit = True
                deficit_path_parts.append(f"L{x:.1f},{y_pos(it_val):.1f}")
            else:
                if in_deficit:
                    # Close deficit region
                    deficit_path_parts.append(f"L{x:.1f},{y_pos(mean_kw):.1f}Z")
                    in_deficit = False
        if in_deficit:
            deficit_path_parts.append(f"L{x_pos(sampled_indices[-1]):.1f},{y_pos(mean_kw):.1f}Z")

        if deficit_path_parts:
            parts.append(
                f'<path d="{" ".join(deficit_path_parts)}" fill="#ef4444" opacity="0.3" />'
            )

    # Hourly IT capacity line
    line_points = " ".join(f"{x_pos(i):.1f},{y_pos(hourly_it_kw[i]):.1f}" for i in sampled_indices)
    parts.append(
        f'<polyline points="{line_points}" fill="none" stroke="{primary}" '
        f'stroke-width="1" opacity="0.6" />'
    )

    # Mean capacity horizontal line — dashed red (deficit reference)
    y_mean = y_pos(mean_kw)
    parts.append(
        f'<line x1="{plot_left}" y1="{y_mean:.1f}" x2="{plot_right}" y2="{y_mean:.1f}" '
        f'stroke="#ef4444" stroke-width="1.5" stroke-dasharray="6,3" />'
        f'<text x="{plot_right + 3}" y="{y_mean + 3:.1f}" fill="#ef4444" '
        f'font-family="system-ui,sans-serif" font-size="6.5" font-weight="600">'
        f'Mean {mean_kw / 1000:.2f} MW</text>'
    )

    # Firm capacity (P99) horizontal line — dashed green
    y_firm = y_pos(firm_kw)
    parts.append(
        f'<line x1="{plot_left}" y1="{y_firm:.1f}" x2="{plot_right}" y2="{y_firm:.1f}" '
        f'stroke="#16a34a" stroke-width="1.5" stroke-dasharray="6,3" />'
        f'<text x="{plot_right + 3}" y="{y_firm + 3:.1f}" fill="#16a34a" '
        f'font-family="system-ui,sans-serif" font-size="6.5" font-weight="600">'
        f'Firm {firm_kw / 1000:.2f} MW</text>'
    )

    # Compute deficit energy relative to Mean (the energy to compensate)
    deficit_energy_kwh = sum(max(mean_kw - it_kw, 0) for it_kw in hourly_it_kw)
    deficit_hours = sum(1 for it_kw in hourly_it_kw if it_kw < mean_kw)

    # X-axis month labels
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in range(12):
        day_start = m * (n // 12)
        x = x_pos(day_start)
        parts.append(
            f'<text x="{x:.1f}" y="{plot_bottom + 10:.1f}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="7" text-anchor="middle">{month_labels[m]}</text>'
        )

    # Y-axis label
    parts.append(
        f'<text x="{_PAD_OUTER}" y="{plot_top + plot_h / 2:.1f}" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="7" text-anchor="middle" '
        f'transform="rotate(-90 {_PAD_OUTER} {plot_top + plot_h / 2:.1f})">IT Capacity (MW)</text>'
    )

    # Legend
    ly = h - 12
    parts.append(
        f'<rect x="{plot_left}" y="{ly}" width="8" height="3" fill="#ef4444" opacity="0.4" />'
        f'<text x="{plot_left + 11}" y="{ly + 3}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="6.5">'
        f'Deficit below Mean: {deficit_energy_kwh / 1000:.1f} MWh ({deficit_hours} hours)</text>'
        f'<line x1="{plot_left + 230}" y1="{ly + 1.5}" x2="{plot_left + 244}" y2="{ly + 1.5}" '
        f'stroke="#16a34a" stroke-width="1.5" stroke-dasharray="4,2" />'
        f'<text x="{plot_left + 247}" y="{ly + 3}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="6.5">'
        f'Firm (P99)</text>'
        f'<line x1="{plot_left + 290}" y1="{ly + 1.5}" x2="{plot_left + 304}" y2="{ly + 1.5}" '
        f'stroke="#ef4444" stroke-width="1.5" stroke-dasharray="4,2" />'
        f'<text x="{plot_left + 307}" y="{ly + 3}" fill="#6b7280" font-family="system-ui,sans-serif" font-size="6.5">'
        f'Mean</text>'
    )

    body = "".join(parts)
    subtitle = (
        f"Firm (P99): {firm_kw / 1000:.2f} MW · Mean: {mean_kw / 1000:.2f} MW · "
        f"Gap: {max(0, mean_kw - firm_kw) / 1000:.2f} MW · "
        f"Peak deficit (Mean − Worst): {max(0, mean_kw - it_min) / 1000:.2f} MW"
    )
    return {
        "available": True,
        "title": "Hourly IT Capacity & Deficit",
        "message": "",
        "svg_markup": _svg_shell(
            width=w, height=h,
            title="Hourly IT Capacity — Deficit & Capacity Gap",
            subtitle=subtitle,
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
    legend_x = cx + r + 34
    legend_y = _PAD_TOP + 12
    for idx, s in enumerate(slices):
        fraction = s["value"] / total
        color = s.get("color") or _PIE_PALETTE[idx % len(_PIE_PALETTE)]
        ly = legend_y + idx * 24
        parts.append(
            f'<rect x="{legend_x:.0f}" y="{ly:.0f}" width="12" height="12" rx="2" fill="{color}" />'
            f'<text x="{legend_x + 18:.0f}" y="{ly + 10:.0f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="9.5" font-weight="600">'
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


# ── Green Energy Breakdown Bar Chart ─────────────────────────────────────────

def build_green_energy_breakdown_chart(
    *,
    total_facility_kwh: float | None = None,
    total_it_kwh: float | None = None,
    total_overhead_kwh: float | None = None,
    total_pv_generation_kwh: float | None = None,
    total_pv_to_overhead_kwh: float | None = None,
    total_pv_to_bess_kwh: float | None = None,
    total_bess_discharge_kwh: float | None = None,
    total_fuel_cell_kwh: float | None = None,
    total_grid_import_kwh: float | None = None,
    total_pv_curtailed_kwh: float | None = None,
) -> dict[str, Any]:
    """Build a horizontal bar chart SVG for annual energy breakdown."""
    categories = [
        ("Total Facility", total_facility_kwh, "#9ca3af"),
        ("Total IT", total_it_kwh, "#d1d5db"),
        ("Total Overhead", total_overhead_kwh, "#e5e7eb"),
        ("PV Generation", total_pv_generation_kwh, "#f59e0b"),
        ("PV \u2192 Overhead", total_pv_to_overhead_kwh, "#22c55e"),
        ("PV \u2192 BESS", total_pv_to_bess_kwh, "#3b82f6"),
        ("BESS Discharge", total_bess_discharge_kwh, "#8b5cf6"),
        ("Fuel Cell", total_fuel_cell_kwh, "#6366f1"),
        ("Grid Import", total_grid_import_kwh, "#ef4444"),
        ("PV Curtailed", total_pv_curtailed_kwh, "#d1d5db"),
    ]

    # Filter to only categories with actual values
    bars: list[tuple[str, float, str]] = []
    for label, val, color in categories:
        if val is not None and val > 0:
            bars.append((label, val / 1000.0, color))  # convert kWh -> MWh

    if not bars:
        return {"available": False, "title": "Annual energy breakdown", "svg_markup": ""}

    w = 680
    h = 212
    title = "Annual energy breakdown"
    subtitle = "Energy streams in MWh"

    label_w = 110
    plot_left = label_w + 8
    plot_right = w - _PAD_OUTER - 50  # room for value labels
    plot_top = _PAD_TOP + 2
    plot_bottom = h - 12
    plot_w = plot_right - plot_left

    n = len(bars)
    row_h = min((plot_bottom - plot_top) / max(n, 1), 18)
    bar_h = row_h * 0.65
    total_h = n * row_h
    y_start = plot_top + (plot_bottom - plot_top - total_h) / 2

    max_val = max(v for _, v, _ in bars) if bars else 1.0

    parts: list[str] = []

    for idx, (label, val, color) in enumerate(bars):
        cy = y_start + idx * row_h + row_h / 2
        bar_top = cy - bar_h / 2
        bar_width = (val / max_val) * plot_w if max_val > 0 else 0

        # Bar
        parts.append(
            f'<rect x="{plot_left}" y="{bar_top:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_h:.1f}" rx="2" fill="{color}" opacity="0.85" />'
        )
        # Label on left
        parts.append(
            f'<text x="{label_w}" y="{cy + 3:.1f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="8" text-anchor="end">'
            f'{escape(label)}</text>'
        )
        # Value at end of bar
        parts.append(
            f'<text x="{plot_left + bar_width + 4:.1f}" y="{cy + 3:.1f}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="7.5" text-anchor="start">'
            f'{val:,.1f} MWh</text>'
        )

    body_breakdown = "".join(parts)
    return {
        "available": True,
        "title": title,
        "svg_markup": _svg_shell(
            width=w, height=h,
            title=title,
            subtitle=subtitle,
            body=body_breakdown,
        ),
    }


# ── Green Dispatch Hourly Chart ──────────────────────────────────────────────

def build_green_dispatch_hourly_chart(
    hourly_dispatch: list[dict[str, float]],
) -> dict[str, Any]:
    """Build a stacked area chart SVG showing hourly energy dispatch over the year."""
    if not hourly_dispatch or len(hourly_dispatch) < 24:
        return {
            "available": False,
            "title": "Hourly Energy Dispatch",
            "svg_markup": "",
        }

    title = "Hourly Energy Dispatch"
    subtitle = "Stacked energy sources meeting overhead demand (kW)"
    w = 680
    h = 196

    plot_left = _PAD_AXIS + 8
    plot_right = w - _PAD_OUTER
    plot_top = _PAD_TOP + 4
    plot_bottom = h - 28
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    total_hours = len(hourly_dispatch)
    # Sample every ~12 hours for SVG efficiency
    step = max(total_hours // 730, 1)
    sampled_indices = list(range(0, total_hours, step))
    n_pts = len(sampled_indices)

    # Extract layers (bottom to top): pv_to_overhead, bess_discharge, fuel_cell, grid_import
    layers_keys = [
        ("pv_to_overhead_kw", "#22c55e"),
        ("bess_discharge_kw", "#8b5cf6"),
        ("fuel_cell_kw", "#6366f1"),
        ("grid_import_kw", "#ef4444"),
    ]

    # Build sampled data
    sampled: list[dict[str, float]] = []
    for i in sampled_indices:
        row = hourly_dispatch[i]
        sampled.append({
            "pv_to_overhead_kw": float(row.get("pv_to_overhead_kw") or 0),
            "bess_discharge_kw": float(row.get("bess_discharge_kw") or 0),
            "fuel_cell_kw": float(row.get("fuel_cell_kw") or 0),
            "grid_import_kw": float(row.get("grid_import_kw") or 0),
            "overhead_kw": float(row.get("overhead_kw") or 0),
        })

    # Find max stacked value for y-axis scaling
    max_y = 0.0
    for row in sampled:
        stack = sum(row[k] for k, _ in layers_keys)
        overhead = row["overhead_kw"]
        max_y = max(max_y, stack, overhead)
    if max_y <= 0:
        return {"available": False, "title": title, "svg_markup": ""}

    # Round up to a nice number
    magnitude = 10 ** math.floor(math.log10(max_y)) if max_y > 0 else 1
    y_max = math.ceil(max_y / magnitude) * magnitude
    if y_max <= 0:
        y_max = max_y * 1.1

    def x_pos(idx: int) -> float:
        return plot_left + (idx / max(n_pts - 1, 1)) * plot_w

    def y_pos(val: float) -> float:
        return plot_bottom - (val / y_max) * plot_h

    parts: list[str] = []

    # Y-axis gridlines and labels
    n_ticks = 4
    for i in range(n_ticks + 1):
        val = y_max * i / n_ticks
        y = y_pos(val)
        parts.append(
            f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" '
            f'stroke="#f0f0f0" stroke-width="1" />'
        )
        label = f"{val / 1000:.0f} MW" if val >= 1000 else f"{val:.0f} kW"
        parts.append(
            f'<text x="{plot_left - 4}" y="{y + 3:.1f}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" text-anchor="end">'
            f'{label}</text>'
        )

    # X-axis month labels
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    hours_per_month = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
    cum_hours = 0
    for mi, mname in enumerate(month_names):
        month_mid = cum_hours + hours_per_month[mi] / 2
        cum_hours += hours_per_month[mi]
        frac = month_mid / total_hours
        mx = plot_left + frac * plot_w
        parts.append(
            f'<text x="{mx:.1f}" y="{plot_bottom + 12}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" text-anchor="middle">'
            f'{mname}</text>'
        )

    # Build stacked area paths (bottom to top)
    # Compute cumulative baselines
    baselines = [[0.0] * n_pts]
    for key, _ in layers_keys:
        prev = baselines[-1]
        new_base = [prev[j] + sampled[j][key] for j in range(n_pts)]
        baselines.append(new_base)

    # Draw layers in reverse so bottom layers are painted first
    for layer_idx in range(len(layers_keys) - 1, -1, -1):
        _, color = layers_keys[layer_idx]
        top_line = baselines[layer_idx + 1]
        bot_line = baselines[layer_idx]

        # Forward along top, backward along bottom
        path_parts = [f"M{x_pos(0):.1f},{y_pos(top_line[0]):.1f}"]
        for j in range(1, n_pts):
            path_parts.append(f"L{x_pos(j):.1f},{y_pos(top_line[j]):.1f}")
        for j in range(n_pts - 1, -1, -1):
            path_parts.append(f"L{x_pos(j):.1f},{y_pos(bot_line[j]):.1f}")
        path_parts.append("Z")

        parts.append(
            f'<path d="{" ".join(path_parts)}" fill="{color}" opacity="0.7" />'
        )

    # Overhead demand line on top
    demand_path = [f"M{x_pos(0):.1f},{y_pos(sampled[0]['overhead_kw']):.1f}"]
    for j in range(1, n_pts):
        demand_path.append(f"L{x_pos(j):.1f},{y_pos(sampled[j]['overhead_kw']):.1f}")
    parts.append(
        f'<path d="{" ".join(demand_path)}" fill="none" stroke="#374151" '
        f'stroke-width="1" opacity="0.6" />'
    )

    # Legend
    legend_items = [
        ("PV Direct", "#22c55e"),
        ("BESS", "#8b5cf6"),
        ("Fuel Cell", "#6366f1"),
        ("Grid", "#ef4444"),
        ("Demand", "#374151"),
    ]
    lx = plot_left
    for li, (lbl, lcolor) in enumerate(legend_items):
        offset = li * 72
        parts.append(
            f'<rect x="{lx + offset}" y="{plot_bottom + 18}" width="8" height="6" '
            f'rx="1" fill="{lcolor}" opacity="0.7" />'
        )
        parts.append(
            f'<text x="{lx + offset + 11}" y="{plot_bottom + 24}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="6.5">{lbl}</text>'
        )

    body_dispatch = "".join(parts)
    return {
        "available": True,
        "title": title,
        "svg_markup": _svg_shell(
            width=w, height=h,
            title=title,
            subtitle=subtitle,
            body=body_dispatch,
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTIVE SUMMARY — PURPOSE-BUILT MINI CHARTS
# ═══════════════════════════════════════════════════════════════════════════════

_RAG_BAR_COLORS: dict[str, str] = {
    "BLUE": "#3b82f6",
    "GREEN": "#16a34a",
    "AMBER": "#f59e0b",
    "RED": "#ef4444",
}


def build_exec_comparison_chart(
    ranked_results: list[dict[str, Any]],
    *,
    primary_key: str | None,
    primary_color: str,
    width: int = 400,
    height: int = 140,
) -> str | None:
    """Horizontal bar chart for executive summary — top 5 scenarios.

    Shows load type, IT load bar, PUE, rack density, and racks per scenario.
    Returns raw ``<svg>`` markup (no wrapper dict).
    """
    results = ranked_results[:5]
    if len(results) < 2:
        return None

    pc = _c(primary_color, "#1a365d")

    # Extract data
    rows: list[dict[str, Any]] = []
    for r in results:
        m = r.get("metrics", {})
        s = r.get("scenario", {})
        it_mw = float(m.get("committed_it_mw") or m.get("it_load_mw") or 0)
        pue = float(m.get("pue") or 0)
        rag = r.get("status", {}).get("rag_status", "GREEN")
        load_type = s.get("load_type", "?")
        cooling = s.get("cooling_type", "?")
        redundancy = s.get("redundancy", "?")
        rack_density = float(m.get("rack_density_kw") or 0)
        racks = int(m.get("racks_deployed") or 0)
        is_primary = r.get("result_key") == primary_key if primary_key else r.get("is_primary", False)
        # Short label: cooling / redundancy
        label = f"{cooling} / {redundancy}"
        rows.append({
            "it_mw": it_mw, "pue": pue, "rag": rag,
            "label": label, "load_type": load_type,
            "rack_density": rack_density, "racks": racks,
            "is_primary": is_primary,
        })

    max_it = max(row["it_mw"] for row in rows) or 1
    upper = max_it * 1.25

    # Layout — compact rows with annotations
    n = len(rows)
    label_w = 100
    annot_w = 120  # Right side: IT MW, PUE, density, racks
    plot_left = label_w
    plot_right = width - annot_w
    plot_w = plot_right - plot_left
    row_h = height / n
    bar_h = min(row_h * 0.45, 14)

    parts: list[str] = []

    # Background
    parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="4" fill="#f9fafb" />'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="3.5" '
        f'fill="white" stroke="#e5e7eb" stroke-width="0.5" />'
    )

    for idx, row in enumerate(rows):
        cy = row_h * idx + row_h / 2
        by = cy - bar_h / 2

        bar_px = max((row["it_mw"] / upper) * plot_w, 2)
        color = pc if row["is_primary"] else _RAG_BAR_COLORS.get(row["rag"], "#94a3b8")
        opacity = "1" if row["is_primary"] else "0.7"
        weight = "600" if row["is_primary"] else "400"

        # Load type + cooling/redundancy label (left side, two lines)
        load_short = escape(row["load_type"][:16])
        label_short = escape(row["label"][:20])
        parts.append(
            f'<text x="{plot_left - 4}" y="{cy - 2}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="7" font-weight="{weight}" '
            f'text-anchor="end">{load_short}</text>'
        )
        parts.append(
            f'<text x="{plot_left - 4}" y="{cy + 7}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="6" '
            f'text-anchor="end">{label_short}</text>'
        )

        # Bar
        parts.append(
            f'<rect x="{plot_left}" y="{by:.1f}" width="{bar_px:.1f}" height="{bar_h:.1f}" '
            f'rx="2" fill="{color}" opacity="{opacity}" />'
        )

        # Row separator
        if idx < n - 1:
            sep_y = row_h * (idx + 1)
            parts.append(
                f'<line x1="4" y1="{sep_y:.1f}" x2="{width - 4}" y2="{sep_y:.1f}" '
                f'stroke="#f3f4f6" stroke-width="0.5" />'
            )

        # Right annotations: IT MW | PUE | Density | Racks
        ax = plot_right + 4
        parts.append(
            f'<text x="{ax}" y="{cy - 5}" fill="#111827" '
            f'font-family="system-ui,sans-serif" font-size="8" font-weight="600">'
            f'{row["it_mw"]:.2f} MW</text>'
        )
        parts.append(
            f'<text x="{ax}" y="{cy + 4}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="6.5">'
            f'PUE {row["pue"]:.3f} · {row["rack_density"]:.0f} kW/rack</text>'
        )
        parts.append(
            f'<text x="{ax}" y="{cy + 12}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="6">'
            f'{row["racks"]:,} racks</text>'
        )

        # Primary dot
        if row["is_primary"]:
            parts.append(
                f'<circle cx="5" cy="{cy}" r="2" fill="{pc}" />'
            )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Scenario comparison">'
        + "".join(parts)
        + "</svg>"
    )
    return svg


def build_exec_firm_capacity_chart(
    *,
    worst_mw: float,
    firm_mw: float,
    mean_mw: float,
    best_mw: float,
    primary_color: str,
    secondary_color: str,
    width: int = 400,
    height: int = 80,
) -> str | None:
    """Compact horizontal firm capacity chart for executive summary.

    Shows Worst → P99 (Firm) → Mean → Best as horizontal bars.
    Returns raw ``<svg>`` markup.
    """
    if firm_mw <= 0 and mean_mw <= 0:
        return None

    pc = _c(primary_color, "#1a365d")
    sc = _c(secondary_color, "#2b6cb0")

    items = [
        ("Worst", worst_mw, "#ef4444"),
        ("P99 Firm", firm_mw, pc),
        ("Mean", mean_mw, sc),
        ("Best", best_mw, "#16a34a"),
    ]
    items = [(label, val, color) for label, val, color in items if val and val > 0]
    if not items:
        return None

    upper = max(val for _, val, _ in items) * 1.15
    n = len(items)
    label_w = 55
    value_w = 55
    plot_left = label_w
    plot_right = width - value_w
    plot_w = plot_right - plot_left
    row_h = height / n
    bar_h = min(row_h * 0.5, 12)

    parts: list[str] = []
    parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="4" fill="#f9fafb" />'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="3.5" '
        f'fill="white" stroke="#e5e7eb" stroke-width="0.5" />'
    )

    for idx, (label, val, color) in enumerate(items):
        cy = row_h * idx + row_h / 2
        by = cy - bar_h / 2
        bar_px = max((val / upper) * plot_w, 2)

        # Label
        parts.append(
            f'<text x="{plot_left - 4}" y="{cy + 3}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="7" '
            f'text-anchor="end">{escape(label)}</text>'
        )

        # Bar
        parts.append(
            f'<rect x="{plot_left}" y="{by:.1f}" width="{bar_px:.1f}" height="{bar_h:.1f}" '
            f'rx="2" fill="{color}" opacity="0.85" />'
        )

        # Value
        parts.append(
            f'<text x="{plot_right + 4}" y="{cy + 3}" fill="{color}" '
            f'font-family="system-ui,sans-serif" font-size="8" font-weight="600">'
            f'{val:.2f} MW</text>'
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Firm capacity spectrum">'
        + "".join(parts)
        + "</svg>"
    )
    return svg


# ---------------------------------------------------------------------------
# Executive — compact hourly IT capacity deficit chart
# ---------------------------------------------------------------------------

def build_exec_deficit_chart(
    hourly_it_kw: list[float],
    firm_kw: float,
    mean_kw: float,
    *,
    primary_color: str = "#1a365d",
    width: int = 400,
    height: int = 120,
) -> str | None:
    """Compact hourly IT capacity & deficit chart for executive summary.

    Shows the annual hourly IT capacity line, mean/firm reference lines,
    and shaded deficit area — all in a small footprint suitable for a
    one-page report.  Returns raw ``<svg>`` markup.
    """
    if not hourly_it_kw or len(hourly_it_kw) < 24:
        return None

    pc = _c(primary_color, "#1a365d")
    n = len(hourly_it_kw)

    pad_l, pad_r, pad_t, pad_b = 42, 6, 10, 18
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    # Scale
    all_vals = hourly_it_kw + [firm_kw, mean_kw]
    y_min = min(all_vals) * 0.95
    y_max = max(all_vals) * 1.05
    y_range = y_max - y_min if y_max > y_min else 1

    def sx(i: int) -> float:
        return pad_l + (i / (n - 1)) * pw

    def sy(v: float) -> float:
        return pad_t + ph - ((v - y_min) / y_range) * ph

    # Sample every ~12 hours for SVG efficiency
    step = max(1, n // 365)
    indices = list(range(0, n, step))
    if indices[-1] != n - 1:
        indices.append(n - 1)

    parts: list[str] = []

    # Background
    parts.append(
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="white" />'
    )

    # Y-axis grid (3 lines)
    for tick_i in range(3):
        v = y_min + y_range * (tick_i / 2)
        yp = sy(v)
        parts.append(
            f'<line x1="{pad_l}" y1="{yp:.1f}" x2="{width - pad_r}" y2="{yp:.1f}" '
            f'stroke="#f3f4f6" stroke-width="0.5" />'
        )
        parts.append(
            f'<text x="{pad_l - 3}" y="{yp + 2.5}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="5" text-anchor="end">'
            f'{v / 1000:.1f}</text>'
        )

    # Deficit area (where IT < mean) — shaded red
    deficit_path = []
    in_deficit = False
    for i in indices:
        x = sx(i)
        it_v = hourly_it_kw[i]
        if it_v < mean_kw:
            if not in_deficit:
                deficit_path.append(f"M{x:.1f},{sy(mean_kw):.1f}")
                in_deficit = True
            deficit_path.append(f"L{x:.1f},{sy(it_v):.1f}")
        else:
            if in_deficit:
                deficit_path.append(f"L{x:.1f},{sy(mean_kw):.1f}Z")
                in_deficit = False
    if in_deficit:
        deficit_path.append(f"L{sx(indices[-1]):.1f},{sy(mean_kw):.1f}Z")
    if deficit_path:
        parts.append(
            f'<path d="{"".join(deficit_path)}" fill="#ef4444" opacity="0.2" />'
        )

    # Hourly IT capacity line
    points = " ".join(f"{sx(i):.1f},{sy(hourly_it_kw[i]):.1f}" for i in indices)
    parts.append(
        f'<polyline points="{points}" fill="none" stroke="{pc}" '
        f'stroke-width="0.8" opacity="0.8" />'
    )

    # Mean line (dashed red)
    my = sy(mean_kw)
    parts.append(
        f'<line x1="{pad_l}" y1="{my:.1f}" x2="{width - pad_r}" y2="{my:.1f}" '
        f'stroke="#ef4444" stroke-width="0.6" stroke-dasharray="3,2" />'
    )
    parts.append(
        f'<text x="{width - pad_r}" y="{my - 2}" fill="#ef4444" '
        f'font-family="system-ui,sans-serif" font-size="5" text-anchor="end">'
        f'Mean {mean_kw / 1000:.2f} MW</text>'
    )

    # Firm line (dashed green)
    fy = sy(firm_kw)
    parts.append(
        f'<line x1="{pad_l}" y1="{fy:.1f}" x2="{width - pad_r}" y2="{fy:.1f}" '
        f'stroke="#16a34a" stroke-width="0.6" stroke-dasharray="3,2" />'
    )
    parts.append(
        f'<text x="{width - pad_r}" y="{fy - 2}" fill="#16a34a" '
        f'font-family="system-ui,sans-serif" font-size="5" text-anchor="end">'
        f'Firm {firm_kw / 1000:.2f} MW</text>'
    )

    # X-axis month labels
    months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    for mi, label in enumerate(months):
        xi = pad_l + (mi / 12) * pw
        parts.append(
            f'<text x="{xi:.0f}" y="{height - 4}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="5">{label}</text>'
        )

    # Y-axis label
    parts.append(
        f'<text x="3" y="{pad_t + ph / 2}" fill="#9ca3af" '
        f'font-family="system-ui,sans-serif" font-size="5" '
        f'transform="rotate(-90,3,{pad_t + ph / 2})" text-anchor="middle">IT MW</text>'
    )

    # Deficit energy annotation
    deficit_kwh = sum(max(mean_kw - kw, 0) for kw in hourly_it_kw)
    deficit_hours = sum(1 for kw in hourly_it_kw if kw < mean_kw)
    gap_mw = (mean_kw - firm_kw) / 1000
    parts.append(
        f'<text x="{pad_l + 2}" y="{pad_t + 6}" fill="#6b7280" '
        f'font-family="system-ui,sans-serif" font-size="5">'
        f'Gap: {gap_mw:.2f} MW · Deficit: {deficit_kwh / 1000:.0f} MWh ({deficit_hours}h)</text>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Hourly IT capacity and deficit">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Executive — compact PUE decomposition pie chart
# ---------------------------------------------------------------------------

def build_exec_pue_pie_chart(
    slices: list[dict[str, Any]],
    *,
    pue_value: float | None = None,
    width: int = 200,
    height: int = 130,
) -> str | None:
    """Compact PUE overhead pie chart for executive summary.

    Each slice: {"label": str, "value": float, "color": str (optional)}.
    Returns raw ``<svg>`` markup.
    """
    slices = [s for s in slices if s.get("value") and s["value"] > 0]
    if not slices:
        return None

    total = sum(s["value"] for s in slices)
    cx, cy = 50, 52
    r = 36

    parts: list[str] = []

    # Draw pie
    angle = -pi / 2
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
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" opacity="0.85" />'
            )
        else:
            parts.append(
                f'<path d="M{cx},{cy} L{x1:.1f},{y1:.1f} '
                f'A{r},{r} 0 {large_arc},1 {x2:.1f},{y2:.1f} Z" '
                f'fill="{color}" opacity="0.85" />'
            )
        angle += sweep

    # PUE value in center
    if pue_value is not None:
        parts.append(
            f'<text x="{cx}" y="{cy + 2}" fill="#111827" '
            f'font-family="system-ui,sans-serif" font-size="9" font-weight="700" '
            f'text-anchor="middle">{pue_value:.3f}</text>'
        )
        parts.append(
            f'<text x="{cx}" y="{cy + 9}" fill="#9ca3af" '
            f'font-family="system-ui,sans-serif" font-size="5" '
            f'text-anchor="middle">PUE</text>'
        )

    # Legend (right side, compact)
    lx = 105
    ly_start = 12
    row_h = 12
    for idx, s in enumerate(slices):
        fraction = s["value"] / total
        color = s.get("color") or _PIE_PALETTE[idx % len(_PIE_PALETTE)]
        ly = ly_start + idx * row_h
        # Color swatch
        parts.append(
            f'<rect x="{lx}" y="{ly}" width="6" height="6" rx="1" fill="{color}" opacity="0.85" />'
        )
        # Shortened label
        label = s["label"]
        if len(label) > 18:
            label = label[:17] + "…"
        parts.append(
            f'<text x="{lx + 9}" y="{ly + 5.5}" fill="#374151" '
            f'font-family="system-ui,sans-serif" font-size="5.5">{escape(label)}</text>'
        )
        # Percentage
        parts.append(
            f'<text x="{width - 4}" y="{ly + 5.5}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="5" text-anchor="end">'
            f'{fraction * 100:.0f}%</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="PUE overhead breakdown">'
        + "".join(parts)
        + "</svg>"
    )
