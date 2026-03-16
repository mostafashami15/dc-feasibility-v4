"""Report data shaping package.

Public API — callers should import from this module (or from the
backwards-compatibility shim at export.report_data).
"""
from export.report._assembly import build_report_bundle, build_report_context
from export.report._selection import (
    get_result_display_label,
    get_result_selection_key,
    validate_report_selection,
)

__all__ = [
    "build_report_context",
    "build_report_bundle",
    "validate_report_selection",
    "get_result_selection_key",
    "get_result_display_label",
]
