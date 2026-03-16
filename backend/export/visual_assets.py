"""
DC Feasibility Tool v4 - Export Visual Assets
=============================================
Builds export-safe inline SVG visuals so HTML/PDF reports can render
deterministic maps and charts without browser-side libraries or network calls.
"""

from __future__ import annotations

from html import escape
from math import cos, radians
from typing import Any


MAP_WIDTH = 720
MAP_HEIGHT = 380
CHART_WIDTH = 720
CHART_HEIGHT = 320
OUTER_PADDING = 28
PLOT_PADDING = 42


def _color(value: str | None, fallback: str) -> str:
    if not value or not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def _point_pairs(coordinates: list[list[float]] | None) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for coordinate in coordinates or []:
        if len(coordinate) < 2:
            continue
        latitude, longitude = coordinate[0], coordinate[1]
        if latitude is None or longitude is None:
            continue
        pairs.append((float(latitude), float(longitude)))
    return pairs


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _map_bounds(
    points: list[tuple[float, float]],
    *,
    min_span_lat: float = 0.01,
    min_span_lon: float = 0.01,
) -> tuple[float, float, float, float]:
    if not points:
        return (0.0, 1.0, 0.0, 1.0)

    min_lat = min(point[0] for point in points)
    max_lat = max(point[0] for point in points)
    min_lon = min(point[1] for point in points)
    max_lon = max(point[1] for point in points)

    if (max_lat - min_lat) < min_span_lat:
        center_lat = (min_lat + max_lat) / 2
        min_lat = center_lat - (min_span_lat / 2)
        max_lat = center_lat + (min_span_lat / 2)

    if (max_lon - min_lon) < min_span_lon:
        center_lon = (min_lon + max_lon) / 2
        min_lon = center_lon - (min_span_lon / 2)
        max_lon = center_lon + (min_span_lon / 2)

    lat_padding = (max_lat - min_lat) * 0.18
    lon_padding = (max_lon - min_lon) * 0.18
    return (
        min_lat - lat_padding,
        max_lat + lat_padding,
        min_lon - lon_padding,
        max_lon + lon_padding,
    )


def _project(
    latitude: float,
    longitude: float,
    bounds: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
) -> tuple[float, float]:
    min_lat, max_lat, min_lon, max_lon = bounds
    usable_width = width - (OUTER_PADDING * 2)
    usable_height = height - (OUTER_PADDING * 2)
    lon_span = max(max_lon - min_lon, 1e-9)
    lat_span = max(max_lat - min_lat, 1e-9)
    x = OUTER_PADDING + ((longitude - min_lon) / lon_span) * usable_width
    y = OUTER_PADDING + ((max_lat - latitude) / lat_span) * usable_height
    return (x, y)


def _grid_lines(width: int, height: int) -> str:
    parts = []
    usable_width = width - (OUTER_PADDING * 2)
    usable_height = height - (OUTER_PADDING * 2)
    for index in range(5):
        x = OUTER_PADDING + (usable_width * index / 4)
        y = OUTER_PADDING + (usable_height * index / 4)
        parts.append(
            f'<line x1="{x:.2f}" y1="{OUTER_PADDING}" x2="{x:.2f}" y2="{height - OUTER_PADDING}" '
            'stroke="#dce4ee" stroke-width="1" />'
        )
        parts.append(
            f'<line x1="{OUTER_PADDING}" y1="{y:.2f}" x2="{width - OUTER_PADDING}" y2="{y:.2f}" '
            'stroke="#dce4ee" stroke-width="1" />'
        )
    return "".join(parts)


def _svg_shell(
    *,
    width: int,
    height: int,
    title: str,
    subtitle: str,
    body: str,
) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="xMidYMid meet" role="img">'
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#f7fafc" />'
        f'<rect x="12" y="12" width="{width - 24}" height="{height - 24}" rx="14" fill="white" stroke="#d4dce5" />'
        f'{_grid_lines(width, height)}'
        f'<text x="{OUTER_PADDING}" y="26" fill="#17314f" font-size="14" font-weight="700">{escape(title)}</text>'
        f'<text x="{OUTER_PADDING}" y="44" fill="#607080" font-size="10">{escape(subtitle)}</text>'
        f"{body}"
        "</svg>"
    )


def _polyline(points: list[tuple[float, float]], *, stroke: str, stroke_width: float, fill: str = "none", dash: str | None = None, opacity: float = 1.0) -> str:
    if len(points) < 2:
        return ""
    points_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline points="{points_str}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" '
        f'opacity="{opacity:.2f}"{dash_attr} />'
    )


def _polygon(points: list[tuple[float, float]], *, stroke: str, stroke_width: float, fill: str, fill_opacity: float = 0.18) -> str:
    if len(points) < 3:
        return ""
    points_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polygon points="{points_str}" fill="{fill}" fill-opacity="{fill_opacity:.2f}" '
        f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-linejoin="round" />'
    )


def _site_anchor(
    site_data: dict[str, Any],
    geometry_points: list[tuple[float, float]],
) -> tuple[float, float] | None:
    location = site_data["location"]
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if latitude is not None and longitude is not None:
        return (float(latitude), float(longitude))
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


def build_site_map_visual(
    site_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    imported_geometry = site_data["imported_geometry"]
    geometry_points = _point_pairs(imported_geometry.get("coordinates"))
    anchor = _site_anchor(site_data, geometry_points)

    if anchor is None:
        return {
            "available": False,
            "title": "Site Map",
            "message": "No site coordinates or imported geometry were available for export-safe map rendering.",
            "svg_markup": None,
        }

    bounds = _map_bounds(geometry_points + [anchor], min_span_lat=0.008, min_span_lon=0.008)
    primary = _color(primary_color, "#17314f")
    secondary = _color(secondary_color, "#2563eb")

    geometry_svg = ""
    projected_geometry = [_project(lat, lon, bounds, width=MAP_WIDTH, height=MAP_HEIGHT) for lat, lon in geometry_points]
    geometry_type = imported_geometry.get("geometry_type")
    if projected_geometry:
        if geometry_type == "polygon":
            geometry_svg = _polygon(
                projected_geometry,
                stroke=primary,
                stroke_width=2.4,
                fill=secondary,
                fill_opacity=0.16,
            )
        elif geometry_type == "line":
            geometry_svg = _polyline(
                projected_geometry,
                stroke=secondary,
                stroke_width=3.0,
            )
        else:
            point_x, point_y = projected_geometry[0]
            geometry_svg = (
                f'<circle cx="{point_x:.2f}" cy="{point_y:.2f}" r="6.5" fill="{secondary}" opacity="0.9" />'
            )

    anchor_x, anchor_y = _project(anchor[0], anchor[1], bounds, width=MAP_WIDTH, height=MAP_HEIGHT)
    body = (
        geometry_svg
        + f'<circle cx="{anchor_x:.2f}" cy="{anchor_y:.2f}" r="8" fill="{primary}" />'
        + f'<circle cx="{anchor_x:.2f}" cy="{anchor_y:.2f}" r="15" fill="none" stroke="{primary}" stroke-opacity="0.22" stroke-width="2" />'
        + f'<text x="{anchor_x + 12:.2f}" y="{anchor_y - 10:.2f}" fill="#17314f" font-size="11" font-weight="700">{escape(site_data["name"])}</text>'
        + f'<text x="{anchor_x + 12:.2f}" y="{anchor_y + 6:.2f}" fill="#607080" font-size="9">'
        f'{escape(site_data["location"].get("city") or "Studied site")}</text>'
    )

    subtitle = (
        "Centered on saved site coordinates with imported geometry overlay."
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
    site_anchor = _site_anchor(
        {
            "location": {
                "latitude": grid_center[0] if grid_center[0] is not None else site_data["location"].get("latitude"),
                "longitude": grid_center[1] if grid_center[1] is not None else site_data["location"].get("longitude"),
            }
        },
        [],
    )
    if site_anchor is None:
        return {
            "available": False,
            "title": "Grid Context Map",
            "message": "No site coordinates were available for the grid-context map.",
            "svg_markup": None,
        }

    lat_radius = (radius_km / 111.0) if radius_km else 0.03
    lon_radius = (
        radius_km / (111.0 * max(cos(radians(site_anchor[0])), 0.2))
        if radius_km
        else 0.03
    )
    map_points = [site_anchor]
    for asset in assets:
        map_points.extend(_point_pairs(asset.get("coordinates")))
    map_points.extend(
        [
            (site_anchor[0] - lat_radius, site_anchor[1]),
            (site_anchor[0] + lat_radius, site_anchor[1]),
            (site_anchor[0], site_anchor[1] - lon_radius),
            (site_anchor[0], site_anchor[1] + lon_radius),
        ]
    )
    bounds = _map_bounds(
        map_points,
        min_span_lat=max(lat_radius * 2.4, 0.02),
        min_span_lon=max(lon_radius * 2.4, 0.02),
    )

    primary = _color(primary_color, "#17314f")
    secondary = _color(secondary_color, "#2563eb")
    site_x, site_y = _project(site_anchor[0], site_anchor[1], bounds, width=MAP_WIDTH, height=MAP_HEIGHT)
    ring_x, _ = _project(site_anchor[0], site_anchor[1] + lon_radius, bounds, width=MAP_WIDTH, height=MAP_HEIGHT)
    _, ring_y = _project(site_anchor[0] + lat_radius, site_anchor[1], bounds, width=MAP_WIDTH, height=MAP_HEIGHT)
    radius_x = abs(ring_x - site_x)
    radius_y = abs(ring_y - site_y)

    asset_svg = []
    for asset in assets:
        asset_points = _point_pairs(asset.get("coordinates"))
        if not asset_points:
            continue
        color = _voltage_color(asset.get("voltage_kv"), primary=primary, secondary=secondary)
        projected = [
            _project(lat, lon, bounds, width=MAP_WIDTH, height=MAP_HEIGHT)
            for lat, lon in asset_points
        ]
        geometry_type = asset.get("geometry_type")
        if geometry_type == "line" or len(projected) > 1:
            asset_svg.append(
                _polyline(
                    projected,
                    stroke=color,
                    stroke_width=3.2 if asset.get("voltage_kv") else 2.2,
                    dash="6 6" if asset.get("voltage_kv") is None else None,
                    opacity=0.9 if asset.get("voltage_kv") else 0.72,
                )
            )
        else:
            point_x, point_y = projected[0]
            if asset.get("asset_type") == "substation":
                asset_svg.append(
                    f'<rect x="{point_x - 5:.2f}" y="{point_y - 5:.2f}" width="10" height="10" '
                    f'rx="2" fill="{color}" stroke="white" stroke-width="1.5" />'
                )
            else:
                asset_svg.append(
                    f'<circle cx="{point_x:.2f}" cy="{point_y:.2f}" r="4.5" fill="{color}" stroke="white" stroke-width="1.5" />'
                )

    body = (
        f'<ellipse cx="{site_x:.2f}" cy="{site_y:.2f}" rx="{radius_x:.2f}" ry="{radius_y:.2f}" '
        f'fill="none" stroke="{secondary}" stroke-width="2" stroke-dasharray="8 6" stroke-opacity="0.55" />'
        + "".join(asset_svg)
        + f'<circle cx="{site_x:.2f}" cy="{site_y:.2f}" r="8" fill="{primary}" stroke="white" stroke-width="2" />'
        + f'<circle cx="{site_x:.2f}" cy="{site_y:.2f}" r="18" fill="none" stroke="{primary}" stroke-opacity="0.18" stroke-width="2.5" />'
        + f'<text x="{site_x + 12:.2f}" y="{site_y - 10:.2f}" fill="#17314f" font-size="11" font-weight="700">{escape(site_data["name"])}</text>'
        + f'<text x="{site_x + 12:.2f}" y="{site_y + 6:.2f}" fill="#607080" font-size="9">'
        f'{escape(f"{radius_km:.1f} km screening radius" if radius_km is not None else "Screening radius")}</text>'
    )
    return {
        "available": True,
        "title": "Grid Context Map",
        "message": "",
        "svg_markup": _svg_shell(
            width=MAP_WIDTH,
            height=MAP_HEIGHT,
            title="Grid Context Map",
            subtitle="Nearby mapped lines and substations shown within the selected screening extent.",
            body=body,
        ),
    }


def _chart_bounds(values: list[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 1.0)
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        minimum -= 1.0
        maximum += 1.0
    padding = (maximum - minimum) * 0.12
    return (minimum - padding, maximum + padding)


def _chart_xy(
    index: int,
    value: float,
    *,
    count: int,
    bounds: tuple[float, float],
) -> tuple[float, float]:
    plot_width = CHART_WIDTH - (PLOT_PADDING * 2)
    plot_height = CHART_HEIGHT - (PLOT_PADDING * 2)
    x = PLOT_PADDING + (plot_width * index / max(count - 1, 1))
    minimum, maximum = bounds
    y = PLOT_PADDING + ((maximum - value) / max(maximum - minimum, 1e-9)) * plot_height
    return (x, y)


def _wrap_label(text: str, *, max_chars: int = 18, max_lines: int = 3) -> list[str]:
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


def build_monthly_temperature_chart(
    monthly_stats: dict[str, list[float]] | None,
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    if not monthly_stats:
        return {
            "available": False,
            "title": "Monthly Temperature Chart",
            "message": "Monthly chart rendering requires a full 8,760-hour weather year.",
            "svg_markup": None,
        }

    monthly_mean = monthly_stats.get("monthly_mean") or []
    monthly_min = monthly_stats.get("monthly_min") or []
    monthly_max = monthly_stats.get("monthly_max") or []
    if len(monthly_mean) != 12 or len(monthly_min) != 12 or len(monthly_max) != 12:
        return {
            "available": False,
            "title": "Monthly Temperature Chart",
            "message": "Monthly chart rendering requires 12 monthly values.",
            "svg_markup": None,
        }

    primary = _color(primary_color, "#17314f")
    secondary = _color(secondary_color, "#2563eb")
    bounds = _chart_bounds(monthly_min + monthly_max)
    mean_points = [
        _chart_xy(index, value, count=12, bounds=bounds)
        for index, value in enumerate(monthly_mean)
    ]
    min_points = [
        _chart_xy(index, value, count=12, bounds=bounds)
        for index, value in enumerate(monthly_min)
    ]
    max_points = [
        _chart_xy(index, value, count=12, bounds=bounds)
        for index, value in enumerate(monthly_max)
    ]
    band_points = max_points + list(reversed(min_points))
    band_svg = _polygon(
        band_points,
        stroke="none",
        stroke_width=0,
        fill=secondary,
        fill_opacity=0.10,
    )
    mean_svg = _polyline(mean_points, stroke=primary, stroke_width=3)
    min_svg = _polyline(min_points, stroke="#93c5fd", stroke_width=1.8, opacity=0.9)
    max_svg = _polyline(max_points, stroke="#7dd3fc", stroke_width=1.8, opacity=0.9)

    ticks = []
    for tick in range(5):
        value = bounds[0] + ((bounds[1] - bounds[0]) * tick / 4)
        _, y = _chart_xy(0, value, count=12, bounds=bounds)
        ticks.append(
            f'<line x1="{PLOT_PADDING}" y1="{y:.2f}" x2="{CHART_WIDTH - PLOT_PADDING}" y2="{y:.2f}" '
            'stroke="#e4ebf2" stroke-width="1" />'
            f'<text x="10" y="{y + 4:.2f}" fill="#607080" font-size="9">{value:.1f} C</text>'
        )

    month_labels = []
    for index, label in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
        x, _ = _chart_xy(index, monthly_mean[index], count=12, bounds=bounds)
        month_labels.append(
            f'<text x="{x:.2f}" y="{CHART_HEIGHT - 10}" fill="#607080" font-size="9" text-anchor="middle">{label}</text>'
        )

    body = (
        "".join(ticks)
        + band_svg
        + max_svg
        + min_svg
        + mean_svg
        + "".join(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.5" fill="{primary}" />'
            for x, y in mean_points
        )
        + "".join(month_labels)
    )
    return {
        "available": True,
        "title": "Monthly Temperature Chart",
        "message": "",
        "svg_markup": _svg_shell(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title="Monthly Temperature Chart",
            subtitle="Monthly mean dry-bulb with min/max envelope from the cached weather year.",
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
    if not free_cooling_rows:
        return {
            "available": False,
            "title": "Free Cooling Chart",
            "message": "No free-cooling rows were available for chart rendering.",
            "svg_markup": None,
        }

    max_hours = max(float(item.get("free_cooling_hours") or 0.0) for item in free_cooling_rows)
    upper_bound = max(max_hours * 1.1, 1.0)
    plot_width = CHART_WIDTH - (PLOT_PADDING * 2)
    plot_height = CHART_HEIGHT - (PLOT_PADDING * 2)
    bar_width = min(96.0, plot_width / max(len(free_cooling_rows) * 1.5, 1.0))
    gap = (plot_width - (bar_width * len(free_cooling_rows))) / max(len(free_cooling_rows) + 1, 1)
    primary = _color(primary_color, "#17314f")
    secondary = _color(secondary_color, "#2563eb")

    ticks = []
    for tick in range(5):
        value = upper_bound * tick / 4
        y = PLOT_PADDING + plot_height - ((value / upper_bound) * plot_height)
        ticks.append(
            f'<line x1="{PLOT_PADDING}" y1="{y:.2f}" x2="{CHART_WIDTH - PLOT_PADDING}" y2="{y:.2f}" '
            'stroke="#e4ebf2" stroke-width="1" />'
            f'<text x="10" y="{y + 4:.2f}" fill="#607080" font-size="9">{value:.0f} h</text>'
        )

    bars = []
    for index, item in enumerate(free_cooling_rows):
        hours = float(item.get("free_cooling_hours") or 0.0)
        x = PLOT_PADDING + gap + index * (bar_width + gap)
        height = (hours / upper_bound) * plot_height
        y = PLOT_PADDING + plot_height - height
        is_selected = item.get("cooling_type") == selected_cooling_type
        fill = secondary if is_selected else "#93c5fd"
        stroke = primary if is_selected else "#60a5fa"
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{height:.2f}" '
            f'rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5" />'
            f'<text x="{x + (bar_width / 2):.2f}" y="{y - 8:.2f}" fill="#17314f" font-size="10" '
            f'text-anchor="middle">{hours:.0f} h</text>'
        )
        wrapped = _wrap_label(str(item.get("cooling_type") or "Cooling"), max_chars=17, max_lines=3)
        label_y = CHART_HEIGHT - 26
        for line_index, line in enumerate(wrapped):
            bars.append(
                f'<text x="{x + (bar_width / 2):.2f}" y="{label_y + line_index * 11:.2f}" '
                f'fill="#607080" font-size="9" text-anchor="middle">{escape(line)}</text>'
            )

    return {
        "available": True,
        "title": "Free Cooling Chart",
        "message": "",
        "svg_markup": _svg_shell(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title="Free Cooling Chart",
            subtitle="Annual free-cooling hours by analysed cooling topology; selected scenario is highlighted.",
            body="".join(ticks) + "".join(bars),
        ),
    }
