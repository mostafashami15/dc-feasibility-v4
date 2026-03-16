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
from math import cos, radians
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
