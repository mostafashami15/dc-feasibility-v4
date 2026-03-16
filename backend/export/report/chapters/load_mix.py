"""Load mix chapter builder."""
from __future__ import annotations

from typing import Any

from export.report._narratives import _build_load_mix_narrative
from export.report._utils import (
    _display_bool,
    _display_list,
    _display_number,
    _display_text,
    _fact,
    _table,
    _clean_notes,
)


def _summarize_load_mix_allocations(allocations: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for allocation in allocations:
        load_type = _display_text(allocation.get("load_type"), default="")
        if not load_type:
            continue
        share_pct = allocation.get("share_pct")
        it_load_mw = allocation.get("it_load_mw")
        parts.append(
            (
                f"{load_type} "
                f"{_display_number(share_pct, digits=0, default='0')}% / "
                f"{_display_number(it_load_mw, digits=2, suffix='MW')}"
            )
        )
    return "; ".join(parts) if parts else "Not available"


def _build_load_mix_chapter(
    load_mix: dict[str, Any],
    primary_result: dict[str, Any] | None,
) -> dict[str, Any]:
    result = load_mix.get("result")
    if load_mix.get("status") != "available" or result is None:
        return {
            "title": "Load Mix Scenario",
            "included": False,
        }

    candidates = result.get("top_candidates") or []
    top_candidate = candidates[0] if candidates else None
    allowed_load_types = result.get("allowed_load_types") or []

    input_items = [
        _fact(
            "Primary scenario context",
            primary_result["label"] if primary_result is not None else None,
        ),
        _fact(
            "Allowed load types",
            _display_list(allowed_load_types, default="Not available"),
        ),
        _fact(
            "Total IT target",
            _display_number(result.get("total_it_mw"), digits=2, suffix="MW"),
        ),
        _fact("Cooling type", result.get("cooling_type")),
        _fact("Density scenario", result.get("density_scenario")),
        _fact(
            "Step size",
            _display_number(result.get("step_pct"), digits=0, suffix="%"),
        ),
        _fact(
            "Minimum racks per type",
            _display_number(result.get("min_racks"), digits=0),
        ),
        _fact(
            "Candidates evaluated",
            _display_number(result.get("total_candidates_evaluated"), digits=0),
        ),
    ]

    if top_candidate is None:
        return {
            "title": "Load Mix Scenario",
            "included": True,
            "has_candidates": False,
            "input_items": input_items,
            "headline_items": [],
            "top_candidate_table": None,
            "ranked_candidates_table": None,
            "top_candidate_notes": [],
            "message": (
                "The load-mix optimizer data was available, but no ranked candidate "
                "mixes were returned for these assumptions."
            ),
            "narrative": _build_load_mix_narrative(
                total_it_mw=result.get("total_it_mw"),
                total_candidates_evaluated=result.get("total_candidates_evaluated"),
                top_candidate=None,
            ),
        }

    top_candidate_allocations = top_candidate.get("allocations") or []
    ranked_rows = [
        {
            "rank": _display_number(candidate.get("rank"), digits=0),
            "score": _display_number(candidate.get("score"), digits=1),
            "blended_pue": _display_number(candidate.get("blended_pue"), digits=3),
            "compatible": _display_bool(
                candidate.get("all_compatible"),
                true_label="Compatible",
                false_label="Needs review",
            ),
            "total_racks": _display_number(candidate.get("total_racks"), digits=0),
            "allocation_summary": _summarize_load_mix_allocations(
                candidate.get("allocations") or []
            ),
        }
        for candidate in candidates[:5]
    ]

    return {
        "title": "Load Mix Scenario",
        "included": True,
        "has_candidates": True,
        "input_items": input_items,
        "headline_items": [
            _fact(
                "Top candidate score",
                _display_number(top_candidate.get("score"), digits=1),
            ),
            _fact(
                "Top candidate blended PUE",
                _display_number(top_candidate.get("blended_pue"), digits=3),
            ),
            _fact(
                "Top candidate racks",
                _display_number(top_candidate.get("total_racks"), digits=0),
            ),
            _fact(
                "Top candidate compatibility",
                _display_bool(
                    top_candidate.get("all_compatible"),
                    true_label="Compatible",
                    false_label="Needs review",
                ),
            ),
        ],
        "top_candidate_table": _table(
            "Top candidate mix",
            [
                ("load_type", "Load Type"),
                ("share_pct", "Share"),
                ("it_load_mw", "IT MW"),
                ("rack_count", "Racks"),
                ("rack_density_kw", "Rack Density"),
            ],
            [
                {
                    "load_type": _display_text(allocation.get("load_type")),
                    "share_pct": _display_number(
                        allocation.get("share_pct"),
                        digits=0,
                        suffix="%",
                    ),
                    "it_load_mw": _display_number(
                        allocation.get("it_load_mw"),
                        digits=2,
                        suffix="MW",
                    ),
                    "rack_count": _display_number(
                        allocation.get("rack_count"),
                        digits=0,
                    ),
                    "rack_density_kw": _display_number(
                        allocation.get("rack_density_kw"),
                        digits=1,
                        suffix="kW/rack",
                    ),
                }
                for allocation in top_candidate_allocations
            ],
        ),
        "ranked_candidates_table": _table(
            "Ranked candidate overview",
            [
                ("rank", "Rank"),
                ("score", "Score"),
                ("blended_pue", "Blended PUE"),
                ("compatible", "Compatibility"),
                ("total_racks", "Total Racks"),
                ("allocation_summary", "Allocation Summary"),
            ],
            ranked_rows,
        ),
        "top_candidate_notes": _clean_notes(top_candidate.get("trade_off_notes")),
        "message": None,
        "narrative": _build_load_mix_narrative(
            total_it_mw=result.get("total_it_mw"),
            total_candidates_evaluated=result.get("total_candidates_evaluated"),
            top_candidate=top_candidate,
        ),
    }
