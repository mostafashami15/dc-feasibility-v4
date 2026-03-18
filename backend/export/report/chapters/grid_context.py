"""Grid context chapter builder."""
from __future__ import annotations

from typing import Any

from export.terrain_map import generate_grid_context_base64
from export.visual_assets import build_grid_context_map_visual

from export.report._narratives import _build_grid_context_narrative
from export.report._utils import (
    _display_bool,
    _display_list,
    _display_number,
    _display_text,
    _fact,
)


def _grid_asset_report_key(asset: dict[str, Any]) -> tuple[int, int, float, float]:
    voltage = asset.get("voltage_kv")
    return (
        0 if voltage is not None else 1,
        0 if asset.get("asset_type") == "substation" else 1,
        -(voltage or 0.0),
        asset.get("distance_km", 0.0),
    )


def _select_grid_display_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_assets = sorted(assets, key=_grid_asset_report_key)
    display_assets = [asset for asset in ranked_assets if asset.get("voltage_kv") is not None]
    if not display_assets:
        return ranked_assets[:4]
    return display_assets[:6]


def _build_grid_context_chapter(
    grid_context: dict[str, Any],
    site_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    if grid_context["status"] != "available" or grid_context["selected"] is None:
        return {
            "title": "Grid Context / Power Access Context",
            "included": False,
        }

    selected = grid_context["selected"]
    summary = selected["summary"]
    score = selected["score"]
    assets = list(selected["assets"])

    display_assets = _select_grid_display_assets(assets)
    display_asset_ids = {asset["asset_id"] for asset in display_assets}
    omitted_asset_count = sum(1 for asset in assets if asset["asset_id"] not in display_asset_ids)
    voltage_classes = sorted(
        {asset["voltage_kv"] for asset in display_assets if asset.get("voltage_kv") is not None},
        reverse=True,
    )

    official = selected["official_evidence"] or {}
    official_items = [
        _fact("Reference", official.get("utility_or_tso_reference")),
        _fact("Reference date", official.get("reference_date")),
        _fact("Confirmed substation", official.get("confirmed_substation_name")),
        _fact(
            "Confirmed voltage",
            _display_number(official.get("confirmed_voltage_kv"), digits=0, suffix="kV"),
        ),
        _fact(
            "Requested capacity",
            _display_number(official.get("confirmed_requested_mw"), digits=2, suffix="MW"),
        ),
        _fact(
            "Available capacity",
            _display_number(official.get("confirmed_available_mw"), digits=2, suffix="MW"),
        ),
        _fact("Connection status", official.get("connection_status")),
        _fact("Timeline status", official.get("timeline_status")),
        _fact("Notes", official.get("notes")),
    ]
    official_items = [item for item in official_items if item["value"] != "Not available"]

    asset_rows = [
        {
            "asset_type": _display_text(asset.get("asset_type")),
            "name": _display_text(asset.get("name")),
            "operator": _display_text(asset.get("operator")),
            "voltage": _display_number(asset.get("voltage_kv"), digits=0, suffix="kV"),
            "distance": _display_number(asset.get("distance_km"), digits=2, suffix="km"),
            "confidence": _display_text(asset.get("confidence")),
        }
        for asset in display_assets
    ]

    score_items = []
    score_notes: list[str] = []
    if score is not None:
        score_items = [
            _fact("Heuristic score", _display_number(score.get("overall_score"), digits=1)),
            _fact("Voltage score", _display_number(score.get("voltage_score"), digits=1)),
            _fact("Distance score", _display_number(score.get("distance_score"), digits=1)),
            _fact(
                "Substation score",
                _display_number(score.get("substation_score"), digits=1),
            ),
            _fact("Evidence score", _display_number(score.get("evidence_score"), digits=1)),
        ]
        score_notes = [
            _display_text(note, default="")
            for note in score.get("notes", [])
            if _display_text(note, default="")
        ]

    evidence_notes = [
        f'{_display_text(note.get("label"))}: {_display_text(note.get("detail"))}'
        for note in selected["evidence_notes"]
    ]
    evidence_notes.extend(
        _display_text(note, default="")
        for note in selected["official_context_notes"]
        if _display_text(note, default="")
    )
    if grid_context.get("message"):
        evidence_notes.append(grid_context["message"])

    # Generate real tile-based grid context map with ALL assets and radius circle
    grid_map_uri = None
    grid_lat = selected.get("latitude") or site_data["location"].get("latitude")
    grid_lon = selected.get("longitude") or site_data["location"].get("longitude")
    all_assets_with_coords = [a for a in assets if a.get("coordinates")]
    if grid_lat is not None and grid_lon is not None:
        grid_map_uri = generate_grid_context_base64(
            grid_lat,
            grid_lon,
            assets=all_assets_with_coords,
            radius_km=summary.get("radius_km"),
        )

    return {
        "title": "Grid Context / Power Access Context",
        "included": True,
        "grid_context_map": grid_map_uri,
        "map_visual": build_grid_context_map_visual(
            site_data,
            grid_center=(selected.get("latitude"), selected.get("longitude")),
            radius_km=summary.get("radius_km"),
            assets=display_assets,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "summary_items": [
            _fact("Search radius", _display_number(summary.get("radius_km"), digits=1, suffix="km")),
            _fact(
                "Nearby lines",
                _display_number(summary.get("nearby_line_count"), digits=0),
            ),
            _fact(
                "Nearby substations",
                _display_number(summary.get("nearby_substation_count"), digits=0),
            ),
            _fact(
                "Nearest line",
                _display_number(summary.get("nearest_line_km"), digits=2, suffix="km"),
            ),
            _fact(
                "Nearest substation",
                _display_number(summary.get("nearest_substation_km"), digits=2, suffix="km"),
            ),
            _fact(
                "Maximum mapped voltage",
                _display_number(summary.get("max_voltage_kv"), digits=0, suffix="kV"),
            ),
            _fact(
                "High-voltage assets within radius",
                _display_number(summary.get("high_voltage_assets_within_radius"), digits=0),
            ),
            _fact("Voltage classes shown", _display_list([f"{value:.0f} kV" for value in voltage_classes])),
            _fact("Confidence", selected["confidence"]),
            _fact("Source layers", _display_list(selected["source_layers"])),
        ],
        "score_items": score_items,
        "score_notes": score_notes,
        "official_items": official_items,
        "asset_rows": asset_rows,
        "asset_count": selected["asset_count"],
        "omitted_asset_count": omitted_asset_count,
        "evidence_notes": evidence_notes,
        "narrative": _build_grid_context_narrative(
            summary=summary,
            score=score,
            has_official_evidence=bool(selected["official_evidence"]),
        ),
    }
