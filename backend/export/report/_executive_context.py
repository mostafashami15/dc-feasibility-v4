"""Build a flat, purpose-built context dict for the one-page executive summary.

This module bypasses the chapter system entirely — it reads raw data from the
site_bundle produced by ``_build_site_bundle`` and returns a flat dict that the
``executive_summary.html`` template can consume directly.
"""
from __future__ import annotations

from typing import Any

from export.visual_assets import (
    build_exec_comparison_chart,
    build_exec_firm_capacity_chart,
    build_exec_pue_pie_chart,
)


def _build_capacity_spectrum_svg(
    worst_mw: float, firm_mw: float, mean_mw: float, best_mw: float,
) -> str:
    """Build a tiny inline horizontal capacity spectrum indicator (200×28)."""
    w, h = 200, 28
    pad_l, pad_r = 4, 4
    bar_y, bar_h = 4, 8
    bw = w - pad_l - pad_r
    upper = best_mw * 1.05 if best_mw > 0 else mean_mw * 1.1

    def sx(v: float) -> float:
        return pad_l + (v / upper) * bw if upper > 0 else pad_l

    # Background track
    parts = [
        f'<rect x="{pad_l}" y="{bar_y}" width="{bw}" height="{bar_h}" '
        f'rx="2" fill="#f3f4f6" />',
    ]

    # Worst → Firm segment (red-ish)
    if worst_mw > 0:
        x1 = sx(worst_mw)
        x2 = sx(firm_mw)
        parts.append(
            f'<rect x="{x1:.1f}" y="{bar_y}" width="{max(x2 - x1, 1):.1f}" '
            f'height="{bar_h}" fill="#fca5a5" opacity="0.7" />'
        )

    # Firm → Mean segment (blue)
    x1 = sx(firm_mw)
    x2 = sx(mean_mw)
    parts.append(
        f'<rect x="{x1:.1f}" y="{bar_y}" width="{max(x2 - x1, 1):.1f}" '
        f'height="{bar_h}" fill="#93c5fd" opacity="0.7" />'
    )

    # Mean → Best segment (green)
    x2m = sx(mean_mw)
    x3 = sx(best_mw)
    parts.append(
        f'<rect x="{x2m:.1f}" y="{bar_y}" width="{max(x3 - x2m, 1):.1f}" '
        f'height="{bar_h}" fill="#86efac" opacity="0.7" />'
    )

    # Markers with labels
    markers = [
        (worst_mw, "#ef4444", "Worst"),
        (firm_mw, "#1a365d", "P99"),
        (mean_mw, "#2b6cb0", "Mean"),
        (best_mw, "#16a34a", "Best"),
    ]
    for val, color, label in markers:
        if val <= 0:
            continue
        mx = sx(val)
        parts.append(
            f'<line x1="{mx:.1f}" y1="{bar_y - 1}" x2="{mx:.1f}" y2="{bar_y + bar_h + 1}" '
            f'stroke="{color}" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{mx:.1f}" y="{bar_y + bar_h + 8}" fill="{color}" '
            f'font-family="system-ui,sans-serif" font-size="5" text-anchor="middle" '
            f'font-weight="600">{label}</text>'
        )
        parts.append(
            f'<text x="{mx:.1f}" y="{bar_y + bar_h + 14}" fill="#6b7280" '
            f'font-family="system-ui,sans-serif" font-size="4.5" text-anchor="middle">'
            f'{val:.1f}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="IT capacity spectrum">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(value: float | None, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}{suffix}"


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def _build_climate_snapshot(climate_block: dict[str, Any]) -> dict[str, Any] | None:
    if climate_block.get("status") != "available":
        return None
    analysis = climate_block.get("analysis")
    if analysis is None:
        return None

    temp = analysis.get("temperature_stats") or {}
    best_fc = analysis.get("best_free_cooling")

    return {
        "temp_mean": _fmt(temp.get("mean"), 1, " °C"),
        "temp_min": _fmt(temp.get("min"), 1, " °C"),
        "temp_max": _fmt(temp.get("max"), 1, " °C"),
        "free_cooling_pct": (
            _pct(best_fc["free_cooling_fraction"] * 100)
            if best_fc and best_fc.get("free_cooling_fraction") is not None
            else None
        ),
        "free_cooling_type": best_fc.get("cooling_type") if best_fc else None,
    }


def _build_grid_snapshot(grid_block: dict[str, Any]) -> dict[str, Any] | None:
    """Return structured grid snapshot with summary line and top assets."""
    if not grid_block.get("available"):
        return None
    selected = grid_block.get("selected")
    if selected is None:
        return None
    summary = selected.get("summary") or {}
    asset_count = selected.get("asset_count", 0)
    radius = summary.get("radius_km", "?")
    voltage_levels = summary.get("voltage_levels_found") or []
    voltage_str = ", ".join(str(v) for v in voltage_levels[:3]) if voltage_levels else "—"
    summary_line = f"{asset_count} assets within {radius} km · Voltages: {voltage_str} kV"

    # Extract top 3 individual assets for display
    assets = selected.get("assets") or []
    top_assets: list[dict[str, str]] = []
    # Sort by voltage descending, then distance
    sorted_assets = sorted(
        assets,
        key=lambda a: (-(a.get("voltage_kv") or 0), a.get("distance_km", 999)),
    )
    for asset in sorted_assets[:3]:
        name = asset.get("name") or asset.get("asset_type", "Unknown")
        asset_type = asset.get("asset_type", "")
        voltage = asset.get("voltage_kv")
        distance = asset.get("distance_km")
        line = f"{name}"
        if voltage:
            line += f" · {voltage} kV"
        if distance is not None:
            line += f" · {distance:.1f} km"
        top_assets.append({
            "type": asset_type,
            "description": line,
        })

    return {
        "summary_line": summary_line,
        "top_assets": top_assets,
    }


def _build_green_snapshot(green_chapter: dict[str, Any]) -> dict[str, Any] | None:
    if not green_chapter.get("included"):
        return None

    snapshot: dict[str, Any] = {}

    # Headline items
    for item in green_chapter.get("headline_items") or []:
        label = (item.get("label") or "").lower()
        value = item.get("value", "—")
        if "renewable" in label or "fraction" in label:
            snapshot["renewable_fraction"] = value
        elif "co2" in label or "co₂" in label or "carbon" in label:
            snapshot["co2_avoided"] = value
        elif "overhead" in label and "coverage" in label:
            snapshot["overhead_coverage"] = value
        elif "grid import" in label:
            snapshot["grid_import"] = value

    # Configuration items
    for item in green_chapter.get("configuration_items") or []:
        label = (item.get("label") or "").lower()
        value = item.get("value", "—")
        if "pv capacity" in label:
            snapshot["pv_capacity"] = value
        elif "bess capacity" in label:
            snapshot["bess_capacity"] = value
        elif "fuel cell" in label:
            snapshot["fuel_cell"] = value

    return snapshot if snapshot else None


def _build_loadmix_snapshot(loadmix_chapter: dict[str, Any]) -> dict[str, Any] | None:
    if not loadmix_chapter.get("included") or not loadmix_chapter.get("has_candidates"):
        return None
    items = loadmix_chapter.get("headline_items") or []
    snapshot: dict[str, Any] = {}
    for item in items:
        label = (item.get("label") or "").lower()
        value = item.get("value", "—")
        if "pue" in label:
            snapshot["blended_pue"] = value
        elif "candidate" in label or "rank" in label:
            snapshot["top_label"] = value
    return snapshot if snapshot else None


def _build_pue_decomposition_snapshot(
    deep_dive: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract PUE decomposition data and build a compact pie chart."""
    block = _find_advanced_block(deep_dive, "pue_decomposition")
    if block is None:
        return None

    pue_value = block.get("annual_pue")
    slices = block.get("component_slices") or []

    # Build compact exec pie chart from raw component data
    compact_svg = None
    if slices:
        compact_svg = build_exec_pue_pie_chart(
            slices, pue_value=pue_value,
        )

    # Fallback to pre-rendered chart if compact build fails
    if compact_svg is None:
        component_pie = block.get("component_pie_visual") or {}
        compact_svg = component_pie.get("svg_markup") if component_pie.get("available") else None

    return {
        "pue_value": pue_value,
        "component_pie_svg": compact_svg,
    }


def _find_advanced_block(
    deep_dive: dict[str, Any], block_type: str
) -> dict[str, Any] | None:
    """Find an advanced block by key from deep_dive chapter."""
    for block in deep_dive.get("advanced_blocks", []):
        if block.get("key") == block_type:
            return block
    return None


def _build_expansion_snapshot(deep_dive: dict[str, Any]) -> dict[str, Any] | None:
    """Extract expansion advisory snapshot from deep_dive chapter."""
    block = _find_advanced_block(deep_dive, "expansion_advisory")
    if block is None:
        return None
    snapshots = block.get("capacity_snapshots") or []
    if not snapshots:
        return None
    return {
        "snapshots": snapshots,
        "notes": (block.get("notes") or [])[:2],
    }


def _build_footprint_snapshot(deep_dive: dict[str, Any]) -> dict[str, Any] | None:
    """Extract infrastructure footprint snapshot."""
    block = _find_advanced_block(deep_dive, "infrastructure_footprint")
    if block is None:
        return None
    items = block.get("summary_items") or []
    snapshot: dict[str, Any] = {
        "ground_fits": block.get("ground_fits", True),
        "roof_fits": block.get("roof_fits", True),
    }
    for item in items:
        label = (item.get("label") or "").lower()
        value = item.get("value", "—")
        if "ground equipment" in label:
            snapshot["ground_area"] = value
        elif "roof equipment" in label:
            snapshot["roof_area"] = value
        elif "ground utilization" in label:
            snapshot["ground_util"] = value
        elif "roof utilization" in label:
            snapshot["roof_util"] = value
    return snapshot if len(snapshot) > 2 else None


def _build_firm_capacity_snapshot(
    deep_dive: dict[str, Any],
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any] | None:
    """Extract firm capacity advisory data and the hourly deficit chart."""
    block = _find_advanced_block(deep_dive, "firm_capacity")
    if block is None:
        return None

    items = block.get("summary_items") or []
    data: dict[str, str] = {}
    for item in items:
        label = (item.get("label") or "").lower()
        data[label] = item.get("value", "—")

    # Extract the pre-rendered deficit chart SVG (680×240, has viewBox, scales via CSS)
    deficit_visual = block.get("deficit_chart_visual") or {}
    deficit_svg = deficit_visual.get("svg_markup") if deficit_visual.get("available") else None

    # Parse numeric values for the bar chart fallback
    firm_mw = mean_mw = worst_mw = best_mw = None
    for item in items:
        label = (item.get("label") or "").lower()
        val_str = (item.get("value") or "").replace(",", "").replace("MW", "").strip()
        try:
            val = float(val_str)
        except (ValueError, TypeError):
            continue
        if "p99" in label or "firm" in label:
            firm_mw = val
        elif "mean" in label:
            mean_mw = val
        elif "worst" in label:
            worst_mw = val
        elif "nominal" in label or "target" in label:
            best_mw = val

    bar_chart_svg = None
    spectrum_svg = None
    if firm_mw and mean_mw:
        bar_chart_svg = build_exec_firm_capacity_chart(
            worst_mw=worst_mw or 0,
            firm_mw=firm_mw,
            mean_mw=mean_mw,
            best_mw=best_mw or mean_mw,
            primary_color=primary_color,
            secondary_color=secondary_color,
        )
        spectrum_svg = _build_capacity_spectrum_svg(
            worst_mw=worst_mw or 0,
            firm_mw=firm_mw,
            mean_mw=mean_mw,
            best_mw=best_mw or mean_mw,
        )

    return {
        "nominal_it": data.get("nominal it target", "—"),
        "mean_it": data.get("mean it capacity", "—"),
        "firm_it": data.get("p99 committed (firm)", "—"),
        "worst_it": data.get("worst-hour it", "—"),
        "capacity_gap": data.get("capacity gap", "—"),
        "deficit_hours": data.get("deficit hours", "—"),
        "deficit_energy": data.get("deficit energy", "—"),
        "deficit_chart_svg": deficit_svg,
        "bar_chart_svg": bar_chart_svg,
        "spectrum_svg": spectrum_svg,
    }


def _build_findings(
    primary: dict[str, Any],
    climate_snap: dict[str, Any] | None,
    grid_snap: dict[str, Any] | None,
    green_snap: dict[str, Any] | None,
) -> list[str]:
    """Assemble 3–6 concise bullet strings for the Key Findings card."""
    findings: list[str] = []

    # RAG reasons (max 3)
    rag_reasons = primary.get("status", {}).get("rag_reasons") or []
    for reason in rag_reasons[:3]:
        findings.append(reason)

    # Binding constraint
    constraint = primary.get("metrics", {}).get("binding_constraint")
    if constraint:
        findings.append(f"Binding constraint: {constraint}")

    # Overtemperature
    ot_hours = primary.get("metrics", {}).get("overtemperature_hours")
    if ot_hours is not None and ot_hours > 0:
        findings.append(f"Overtemperature risk: {ot_hours:,} hours/year")

    # Climate — use the scenario's actual cooling type, not the theoretical best
    if climate_snap and climate_snap.get("free_cooling_pct"):
        scenario_cooling = primary.get("scenario", {}).get("cooling_type", "")
        findings.append(
            f"Free cooling potential: {climate_snap['free_cooling_pct']}"
            + (f" ({scenario_cooling})" if scenario_cooling else "")
        )

    # Green energy
    if green_snap and green_snap.get("renewable_fraction"):
        findings.append(f"Renewable fraction: {green_snap['renewable_fraction']}")

    return findings[:6]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_executive_site_context(
    site_bundle: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    """Return a flat context dict for one site's executive summary page."""
    site = site_bundle["site_data"]
    primary = site_bundle["results"]["primary"]
    all_ranked = site_bundle["results"]["all_ranked"]
    climate_block = site_bundle.get("climate", {})
    grid_block = site_bundle.get("grid_context", {})
    chapters = site_bundle.get("chapters", {})
    green_chapter = chapters.get("green_energy", {})
    loadmix_chapter = chapters.get("load_mix", {})
    deep_dive = chapters.get("deep_dive", {})
    site_specifics = chapters.get("site_specifics", {})
    grid_chapter = chapters.get("grid_context", {})

    # --- Site identity ---
    loc = site.get("location", {})
    city = loc.get("city") or ""
    country = loc.get("country") or ""
    location_line = ", ".join(filter(None, [city, country]))
    if loc.get("coordinates_present"):
        location_line += f"  ({loc['latitude']:.4f}, {loc['longitude']:.4f})"

    land = site.get("land", {})
    power_info = site.get("power", {})

    # --- Primary result metrics ---
    metrics = primary.get("metrics", {}) if primary else {}
    status = primary.get("status", {}) if primary else {}
    scenario = primary.get("scenario", {}) if primary else {}
    space = primary.get("space", {}) if primary else {}

    scenario_pills = []
    for key in ("load_type", "cooling_type", "redundancy", "density_scenario", "backup_power"):
        val = scenario.get(key)
        if val:
            scenario_pills.append(val)

    # --- Analysis snapshots ---
    climate_snap = _build_climate_snapshot(climate_block)
    grid_snap = _build_grid_snapshot(grid_block)
    green_snap = _build_green_snapshot(green_chapter)
    loadmix_snap = _build_loadmix_snapshot(loadmix_chapter)
    expansion_snap = _build_expansion_snapshot(deep_dive)
    footprint_snap = _build_footprint_snapshot(deep_dive)
    firm_capacity_snap = _build_firm_capacity_snapshot(
        deep_dive, primary_color, secondary_color,
    )
    pue_decomposition_snap = _build_pue_decomposition_snapshot(deep_dive)

    # --- Findings ---
    findings = _build_findings(primary or {}, climate_snap, grid_snap, green_snap)

    # --- Map image (grid context map with infrastructure overlay) ---
    grid_context_map = grid_chapter.get("grid_context_map")
    # Fallback to location map if no grid map
    location_map = site_specifics.get("location_map")
    map_image = grid_context_map or location_map

    # --- Purpose-built comparison chart (reduced size) ---
    primary_key = primary.get("result_key") if primary else None
    comparison_svg = None
    if len(all_ranked) >= 2:
        comparison_svg = build_exec_comparison_chart(
            all_ranked[:5],
            primary_key=primary_key,
            primary_color=primary_color,
            width=400,
            height=140,
        )

    return {
        # Site identity
        "site_name": site.get("name", "Unknown Site"),
        "location_line": location_line,
        "land_area_m2": land.get("land_area_m2"),
        "land_area_display": _fmt(land.get("land_area_m2"), 0, " m²"),
        "available_power_mw": power_info.get("available_power_mw"),
        "available_power_display": _fmt(power_info.get("available_power_mw"), 1, " MW"),
        "voltage": power_info.get("voltage") or "—",
        "power_confirmed": power_info.get("power_confirmed", False),

        # Verdict metrics
        "rag_status": status.get("rag_status", "—"),
        "score": metrics.get("score"),
        "score_display": _fmt(metrics.get("score"), 1),
        "binding_constraint": metrics.get("binding_constraint", "—"),

        # Capacity headline
        "it_load_mw": metrics.get("it_load_mw"),
        "it_load_display": _fmt(metrics.get("it_load_mw"), 2, " MW"),
        "facility_power_mw": metrics.get("facility_power_mw"),
        "facility_power_display": _fmt(metrics.get("facility_power_mw"), 2, " MW"),
        "pue": metrics.get("pue"),
        "pue_display": _fmt(metrics.get("pue"), 3),
        "racks_deployable": space.get("effective_racks"),
        "racks_deployable_display": f"{space.get('effective_racks', 0):,}",
        "rack_density_kw": metrics.get("rack_density_kw"),
        "rack_density_display": _fmt(metrics.get("rack_density_kw"), 1, " kW"),
        "buildable_footprint_m2": space.get("buildable_footprint_m2"),
        "buildable_footprint_display": _fmt(space.get("buildable_footprint_m2"), 0, " m²"),
        "it_whitespace_m2": space.get("it_whitespace_m2"),
        "it_whitespace_display": _fmt(space.get("it_whitespace_m2"), 0, " m²"),

        # Scenario config
        "scenario_pills": scenario_pills,

        # Map image (base64 data URI)
        "map_image": map_image,

        # Analysis snapshots
        "climate_snapshot": climate_snap,
        "grid_snapshot": grid_snap,
        "green_snapshot": green_snap,
        "loadmix_snapshot": loadmix_snap,
        "expansion_snapshot": expansion_snap,
        "footprint_snapshot": footprint_snap,
        "firm_capacity": firm_capacity_snap,
        "pue_decomposition": pue_decomposition_snap,

        # Key findings
        "findings": findings,

        # Chart
        "comparison_chart_svg": comparison_svg,

        # IT capacity spectrum
        "has_capacity_spectrum": metrics.get("it_capacity_p99_mw") is not None,
        "committed_it_display": _fmt(metrics.get("committed_it_mw"), 2, " MW"),
    }
