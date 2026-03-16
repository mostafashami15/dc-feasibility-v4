"""Display helpers, table builder, narrative builder, and other shared utilities."""
from __future__ import annotations

from statistics import mean
from typing import Any

from export.report._constants import NARRATIVE_POLICY


def _display_number(
    value: float | int | None,
    *,
    digits: int = 2,
    suffix: str | None = None,
    default: str = "Not available",
) -> str:
    if value is None:
        return default
    formatted = f"{value:,.{digits}f}"
    if suffix:
        return f"{formatted} {suffix}"
    return formatted


def _display_percent(
    value: float | None,
    *,
    digits: int = 0,
    default: str = "Not available",
) -> str:
    if value is None:
        return default
    return f"{value * 100:.{digits}f}%"


def _display_energy_mwh(
    value_kwh: float | None,
    *,
    digits: int = 2,
    default: str = "Not available",
) -> str:
    if value_kwh is None:
        return default
    return _display_number(value_kwh / 1000.0, digits=digits, suffix="MWh")


def _display_bool(
    value: bool | None,
    *,
    true_label: str = "Yes",
    false_label: str = "No",
    default: str = "Not available",
) -> str:
    if value is None:
        return default
    return true_label if value else false_label


def _display_text(value: Any, default: str = "Not available") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or default
    return str(value)


def _display_coordinates(
    latitude: float | None,
    longitude: float | None,
    *,
    digits: int = 5,
    default: str = "Not available",
) -> str:
    if latitude is None or longitude is None:
        return default
    return f"{latitude:.{digits}f}, {longitude:.{digits}f}"


def _display_list(values: list[Any], default: str = "Not available") -> str:
    filtered = [_display_text(value, default="") for value in values if value is not None]
    filtered = [value for value in filtered if value]
    return ", ".join(filtered) if filtered else default


def _fact(label: str, value: Any) -> dict[str, str]:
    return {"label": label, "value": _display_text(value)}


def _safe_mean(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def _normalize_sentence(text: str | None) -> str:
    cleaned = _display_text(text, default="").strip()
    if not cleaned or cleaned == "Not available":
        return ""
    cleaned = " ".join(cleaned.split())
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _build_narrative(
    *,
    paragraphs: list[str | None],
    basis_labels: list[str | None],
    intents: list[str] | None = None,
) -> dict[str, Any]:
    cleaned_paragraphs: list[str] = []
    for paragraph in paragraphs:
        normalized = _normalize_sentence(paragraph)
        if normalized and normalized not in cleaned_paragraphs:
            cleaned_paragraphs.append(normalized)

    cleaned_basis: list[str] = []
    for label in basis_labels:
        normalized = _display_text(label, default="").strip()
        if normalized and normalized != "Not available" and normalized not in cleaned_basis:
            cleaned_basis.append(normalized)

    return {
        "available": bool(cleaned_paragraphs),
        "mode": NARRATIVE_POLICY["mode"],
        "paragraphs": cleaned_paragraphs[: NARRATIVE_POLICY["max_paragraphs"]],
        "basis_labels": cleaned_basis[:6],
        "intents": intents or ["summary", "recommendation"],
    }


def _table(
    title: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "title": title,
        "columns": [{"key": key, "label": label} for key, label in columns],
        "rows": rows,
    }


def _clean_notes(values: list[Any] | None) -> list[str]:
    notes: list[str] = []
    for value in values or []:
        text = _display_text(value, default="")
        if text:
            notes.append(text)
    return notes


def _build_advanced_block(
    key: str,
    title: str,
    *,
    summary_items: list[dict[str, str]] | None = None,
    tables: list[dict[str, Any]] | None = None,
    notes: list[Any] | None = None,
) -> dict[str, Any] | None:
    cleaned_tables = [table for table in tables or [] if table.get("rows")]
    cleaned_notes = _clean_notes(notes)
    if not (summary_items or cleaned_tables or cleaned_notes):
        return None

    return {
        "key": key,
        "title": title,
        "summary_items": summary_items or [],
        "tables": cleaned_tables,
        "notes": cleaned_notes,
    }
