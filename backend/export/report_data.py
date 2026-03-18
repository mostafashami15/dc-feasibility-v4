"""Backwards-compatibility shim — import from export.report instead."""
from export.report import (
    build_report_context,
    build_report_bundle,
    validate_report_selection,
    get_result_selection_key,
    get_result_display_label,
)
from export.report._constants import NARRATIVE_POLICY, LAYOUT_MODE_LABELS
from api.store import GRID_CONTEXT_DIR, get_weather

__all__ = [
    "build_report_context",
    "build_report_bundle",
    "validate_report_selection",
    "get_result_selection_key",
    "get_result_display_label",
    "NARRATIVE_POLICY",
    "LAYOUT_MODE_LABELS",
    "GRID_CONTEXT_DIR",
    "get_weather",
]
