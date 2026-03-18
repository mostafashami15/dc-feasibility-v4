"""Climate chapter builder."""
from __future__ import annotations

from typing import Any

from export.visual_assets import (
    build_cooling_suitability_chart,
    build_free_cooling_chart,
    build_monthly_temperature_chart,
)

from export.report._constants import MONTH_NAMES
from export.report._narratives import _build_climate_narrative
from export.report._utils import (
    _display_bool,
    _display_coordinates,
    _display_list,
    _display_number,
    _display_percent,
    _display_text,
    _fact,
)


def _build_climate_delta_rows_full(
    delta_results: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    """Build the FULL delta projection table — every cooling type × every delta.

    Used in the appendix to give the complete picture.
    """
    rows: list[dict[str, str]] = []

    def _delta_sort_key(item: tuple[str, list[dict[str, Any]]]) -> float:
        try:
            return float(item[0])
        except (TypeError, ValueError):
            return float("inf")

    for delta, analyses in sorted(delta_results.items(), key=_delta_sort_key):
        for item in analyses:
            rows.append(
                {
                    "delta": f"+{delta}°C",
                    "cooling_type": _display_text(item.get("cooling_type")),
                    "free_cooling_hours": _display_number(
                        item.get("free_cooling_hours"),
                        digits=0,
                    ),
                    "partial_hours": _display_number(
                        item.get("partial_hours"),
                        digits=0,
                    ),
                    "mechanical_hours": _display_number(
                        item.get("mechanical_hours"),
                        digits=0,
                    ),
                    "free_cooling_fraction": _display_percent(
                        item.get("free_cooling_fraction"),
                        digits=1,
                    ),
                    "suitability": _display_text(item.get("suitability")),
                }
            )
    return rows


def _build_climate_chapter(
    climate: dict[str, Any],
    primary_result: dict[str, Any] | None,
    *,
    primary_color: str,
    secondary_color: str,
) -> dict[str, Any]:
    if climate["status"] != "available" or climate["analysis"] is None:
        return {
            "title": "Climate Study",
            "included": False,
        }

    weather_status = climate["weather_status"] or {}
    analysis = climate["analysis"]
    temperature_stats = analysis["temperature_stats"]
    monthly_stats = analysis["monthly_stats"] or {}
    selected_cooling_type = (
        primary_result["scenario"]["cooling_type"] if primary_result is not None else None
    )

    monthly_rows = []
    monthly_mean = monthly_stats.get("monthly_mean") or []
    monthly_min = monthly_stats.get("monthly_min") or []
    monthly_max = monthly_stats.get("monthly_max") or []
    for index, month_name in enumerate(MONTH_NAMES):
        if index >= len(monthly_mean):
            break
        monthly_rows.append(
            {
                "month": month_name,
                "mean": _display_number(monthly_mean[index], digits=1, suffix="C"),
                "min": _display_number(monthly_min[index], digits=1, suffix="C"),
                "max": _display_number(monthly_max[index], digits=1, suffix="C"),
            }
        )

    free_cooling_rows = [
        {
            "cooling_type": _display_text(item.get("cooling_type")),
            "threshold": _display_text(item.get("threshold_description")),
            "free_cooling_hours": _display_number(
                item.get("free_cooling_hours"),
                digits=0,
            ),
            "free_cooling_fraction": _display_percent(
                item.get("free_cooling_fraction"),
                digits=1,
            ),
            "suitability": _display_text(item.get("suitability")),
            "is_selected": item.get("cooling_type") == selected_cooling_type,
        }
        for item in analysis["free_cooling"]
    ]
    selected_free_cooling = next(
        (row for row in free_cooling_rows if row["is_selected"]),
        None,
    )

    best_free_cooling = analysis.get("best_free_cooling") or {}

    return {
        "title": "Climate Study",
        "included": True,
        "monthly_chart_visual": build_monthly_temperature_chart(
            monthly_stats if monthly_stats else None,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "free_cooling_chart_visual": build_free_cooling_chart(
            analysis["free_cooling"],
            selected_cooling_type=selected_cooling_type,
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "cooling_suitability_chart_visual": build_cooling_suitability_chart(
            analysis["free_cooling"],
            primary_color=primary_color,
            secondary_color=secondary_color,
        ),
        "weather_items": [
            _fact("Weather source", weather_status.get("source")),
            _fact("Source type", weather_status.get("source_type")),
            _fact("Hours analysed", _display_number(weather_status.get("hours"), digits=0)),
            _fact(
                "Humidity available",
                _display_bool(weather_status.get("has_humidity")),
            ),
            _fact("Uploaded file", weather_status.get("original_filename")),
            _fact(
                "Years averaged",
                _display_list(weather_status.get("years_averaged") or []),
            ),
            _fact(
                "Weather coordinates",
                _display_coordinates(
                    weather_status.get("latitude"),
                    weather_status.get("longitude"),
                ),
            ),
        ],
        "temperature_items": [
            # First 5 match the frontend UI stat cards
            _fact("Mean", _display_number(temperature_stats.get("mean"), digits=1, suffix="°C")),
            _fact("Min", _display_number(temperature_stats.get("min"), digits=1, suffix="°C")),
            _fact("Max", _display_number(temperature_stats.get("max"), digits=1, suffix="°C")),
            _fact("P1 (cold)", _display_number(temperature_stats.get("p1"), digits=1, suffix="°C")),
            _fact("P99 (hot)", _display_number(temperature_stats.get("p99"), digits=1, suffix="°C")),
            # Additional stats
            _fact("Median", _display_number(temperature_stats.get("median"), digits=1, suffix="°C")),
            _fact("Std Dev", _display_number(temperature_stats.get("std_dev"), digits=2, suffix="°C")),
            _fact("Samples", _display_number(temperature_stats.get("count"), digits=0)),
        ],
        "best_free_cooling_summary": [
            _fact("Best cooling type", best_free_cooling.get("cooling_type")),
            _fact(
                "Best free cooling hours",
                _display_number(best_free_cooling.get("free_cooling_hours"), digits=0),
            ),
            _fact(
                "Best free cooling fraction",
                _display_percent(best_free_cooling.get("free_cooling_fraction"), digits=1),
            ),
            _fact("Best suitability", best_free_cooling.get("suitability")),
        ],
        "monthly_rows": monthly_rows,
        "monthly_message": (
            ""
            if monthly_rows
            else "Monthly temperature breakout is only available when a full 8,760-hour weather year is present."
        ),
        "free_cooling_rows": free_cooling_rows,
        "delta_rows_full": _build_climate_delta_rows_full(
            analysis["delta_results"],
        ),
        "narrative": _build_climate_narrative(
            weather_status=weather_status,
            temperature_stats=temperature_stats,
            selected_cooling_type=selected_cooling_type,
            selected_free_cooling=selected_free_cooling,
            best_free_cooling=best_free_cooling,
        ),
    }
