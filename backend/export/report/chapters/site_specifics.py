"""Site specifics chapter builder."""
from __future__ import annotations

from typing import Any

from export.terrain_map import (
    generate_country_overview_base64,
    generate_site_location_base64,
    generate_terrain_base64,
)
from export.visual_assets import build_site_map_visual

from export.report._narratives import _build_site_specifics_narrative
from export.report._utils import (
    _display_bool,
    _display_coordinates,
    _display_number,
    _display_percent,
    _display_text,
    _fact,
)


def _build_site_specifics_chapter(
    site_data: dict[str, Any],
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    location = site_data["location"]
    land = site_data["land"]
    building = site_data["building"]
    power = site_data["power"]
    imported_geometry = site_data["imported_geometry"]

    # Generate map imagery if coordinates are available
    terrain_image_uri = None
    location_map_uri = None
    country_overview_uri = None
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is not None and lon is not None:
        terrain_image_uri = generate_terrain_base64(lat, lon, width=400, height=300)
        location_map_uri = generate_site_location_base64(lat, lon, width=400, height=300)
        country_overview_uri = generate_country_overview_base64(lat, lon, width=400, height=300)

    return {
        "title": "Site Specifics and Properties",
        "terrain_image": terrain_image_uri,
        "location_map": location_map_uri,
        "country_overview": country_overview_uri,
        "map_visual": build_site_map_visual(
            site_data,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "identity_items": [
            _fact("Site name", site_data["name"]),
            _fact("Site classification", site_data["site_type"]),
        ],
        "location_items": [
            _fact("Country", location["country"]),
            _fact("City", location["city"]),
            _fact(
                "Coordinates",
                _display_coordinates(location["latitude"], location["longitude"]),
            ),
        ],
        "property_items": [
            _fact("Land area", _display_number(land["land_area_m2"], digits=0, suffix="m2")),
            _fact("Buildable area mode", land["buildable_area_mode"]),
            _fact(
                "Site coverage ratio",
                _display_percent(land["site_coverage_ratio"], digits=0),
            ),
            _fact(
                "Buildable area",
                _display_number(land["buildable_area_m2"], digits=0, suffix="m2"),
            ),
            _fact(
                "Maximum building height",
                _display_number(building["max_building_height_m"], digits=1, suffix="m"),
            ),
            _fact(
                "Floor-to-floor height",
                _display_number(
                    building["floor_to_floor_height_m"],
                    digits=1,
                    suffix="m",
                ),
            ),
            _fact("Active floors", _display_number(building["num_floors"], digits=0)),
            _fact(
                "Expansion floors",
                _display_number(building["num_expansion_floors"], digits=0),
            ),
            _fact(
                "Whitespace ratio",
                _display_percent(building["whitespace_ratio"], digits=0),
            ),
            _fact(
                "Rack footprint",
                _display_number(building["rack_footprint_m2"], digits=1, suffix="m2"),
            ),
        ],
        "power_items": [
            _fact(
                "Available power",
                _display_number(power["available_power_mw"], digits=2, suffix="MW"),
            ),
            _fact(
                "Power confirmed",
                _display_bool(power["power_confirmed"], true_label="Confirmed"),
            ),
            _fact("Power input mode", power["power_input_mode"]),
            _fact("Declared voltage", power["voltage"]),
        ],
        "geometry_items": [
            _fact(
                "Imported geometry present",
                _display_bool(imported_geometry["present"]),
            ),
            _fact("Geometry type", imported_geometry["geometry_type"]),
            _fact(
                "Coordinate count",
                _display_number(imported_geometry["coordinate_count"], digits=0),
            ),
        ],
        "notes": _display_text(site_data["notes"], default=""),
        "narrative": _build_site_specifics_narrative(site_data),
    }
