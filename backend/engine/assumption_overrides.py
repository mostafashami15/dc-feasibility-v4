"""
Controlled assumption override catalog, persistence, and runtime helpers.

This module keeps the override workflow source-backed and bounded:
    - only curated assumption keys can be edited
    - every override must carry source + justification
    - values are range-checked before being persisted
    - engine modules resolve effective values through these helpers
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from engine.assumptions import COOLING_PROFILES, MISC_OVERHEAD, REDUNDANCY_PROFILES
from engine.models import AppliedAssumptionOverride, Scenario


_BASE_DIR = Path(__file__).resolve().parent.parent
_SETTINGS_DIR = _BASE_DIR / "data" / "settings"
_OVERRIDES_PATH = _SETTINGS_DIR / "assumption_overrides.json"
_HISTORY_PATH = _SETTINGS_DIR / "assumption_override_history.json"

_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


class PersistedAssumptionOverride(BaseModel):
    """One persisted override record saved to disk."""

    value: float
    source: str = Field(min_length=3, max_length=240)
    justification: str = Field(min_length=8, max_length=600)
    updated_at_utc: str


class AssumptionOverrideStore(BaseModel):
    """Serialized settings file containing the active overrides."""

    version: int = 1
    updated_at_utc: str | None = None
    overrides: dict[str, PersistedAssumptionOverride] = Field(default_factory=dict)


class AssumptionOverrideEntry(BaseModel):
    """Resolved catalog entry returned to the UI."""

    key: str
    section: Literal["cooling", "redundancy", "misc"]
    section_label: str
    scope_label: str
    parameter_label: str
    unit: str
    impact_scope: Literal["static_and_hourly", "hourly_only"]
    baseline_value: float
    effective_value: float
    min_value: float
    max_value: float
    baseline_source: str
    description: str
    override: PersistedAssumptionOverride | None = None


class AssumptionOverridesResponse(BaseModel):
    """Settings payload for the full override catalog."""

    updated_at_utc: str | None = None
    active_override_count: int
    assumptions: list[AssumptionOverrideEntry]


class AssumptionOverridePresetValue(BaseModel):
    """One resolved override value included in a scenario-local preset."""

    key: str
    section: Literal["cooling", "redundancy", "misc"]
    scope_label: str
    parameter_label: str
    unit: str
    impact_scope: Literal["static_and_hourly", "hourly_only"]
    baseline_value: float
    preset_value: float
    justification: str


class AssumptionOverridePreset(BaseModel):
    """Curated scenario-local preset built on top of the existing catalog."""

    key: str
    label: str
    description: str
    source: str
    override_count: int
    overrides: list[AssumptionOverridePresetValue]


class AssumptionOverridePresetsResponse(BaseModel):
    """Settings payload describing all available scenario-local presets."""

    presets: list[AssumptionOverridePreset]


class AssumptionOverrideHistoryItem(BaseModel):
    """One change or applied overlay captured in explicit override history."""

    action: Literal["activated", "updated", "cleared", "preset_applied"]
    key: str
    label: str
    scope_label: str
    parameter_label: str
    unit: str
    origin: Literal["settings_override", "scenario_preset"]
    previous_value: float | None = None
    effective_value: float
    source: str
    justification: str


class AssumptionOverrideHistoryEntry(BaseModel):
    """One persisted history event for the override workflow."""

    id: str
    recorded_at_utc: str
    event_type: Literal["settings_update", "scenario_preset_run"]
    title: str
    summary: str
    preset_key: str | None = None
    preset_label: str | None = None
    active_override_count: int | None = None
    site_count: int | None = None
    scenario_count: int | None = None
    changes: list[AssumptionOverrideHistoryItem] = Field(default_factory=list)


class AssumptionOverrideHistoryResponse(BaseModel):
    """Settings payload for explicit override history."""

    entries: list[AssumptionOverrideHistoryEntry]


class AssumptionOverrideUpdate(BaseModel):
    """One update operation from the Settings page."""

    key: str
    override_value: float | None = None
    source: str | None = None
    justification: str | None = None

    @model_validator(mode="after")
    def validate_override_metadata(self):
        if self.override_value is None:
            return self

        source = (self.source or "").strip()
        justification = (self.justification or "").strip()
        if not source:
            raise ValueError("A source/citation is required when saving an override")
        if not justification:
            raise ValueError("A justification is required when saving an override")
        self.source = source
        self.justification = justification
        return self


class AssumptionOverridesUpdateRequest(BaseModel):
    """Bulk update payload for controlled overrides."""

    overrides: list[AssumptionOverrideUpdate] = Field(default_factory=list)


class _CatalogSpec(BaseModel):
    key: str
    section: Literal["cooling", "redundancy", "misc"]
    section_label: str
    scope_name: str
    scope_label: str
    parameter_key: str
    parameter_label: str
    unit: str
    impact_scope: Literal["static_and_hourly", "hourly_only"]
    min_value: float
    max_value: float
    baseline_source: str
    description: str
    sort_order: int


class _PresetSpec(BaseModel):
    key: str
    label: str
    description: str
    source: str
    direction: Literal["efficient", "conservative"]


class AssumptionOverrideHistoryStore(BaseModel):
    """Serialized settings file containing explicit override history."""

    version: int = 1
    entries: list[AssumptionOverrideHistoryEntry] = Field(default_factory=list)


class _ResolvedOverride(BaseModel):
    value: float
    source: str
    justification: str
    updated_at_utc: str | None = None
    origin: Literal["settings_override", "scenario_preset"]
    preset_key: str | None = None
    preset_label: str | None = None
    previous_value: float | None = None


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cooling_spec(
    *,
    key: str,
    scope_name: str,
    parameter_key: str,
    parameter_label: str,
    unit: str,
    impact_scope: Literal["static_and_hourly", "hourly_only"],
    min_value: float,
    max_value: float,
    baseline_source: str,
    description: str,
    sort_order: int,
) -> _CatalogSpec:
    return _CatalogSpec(
        key=key,
        section="cooling",
        section_label="Cooling Profiles",
        scope_name=scope_name,
        scope_label=scope_name,
        parameter_key=parameter_key,
        parameter_label=parameter_label,
        unit=unit,
        impact_scope=impact_scope,
        min_value=min_value,
        max_value=max_value,
        baseline_source=baseline_source,
        description=description,
        sort_order=sort_order,
    )


def _redundancy_spec(
    *,
    key: str,
    scope_name: str,
    min_value: float,
    max_value: float,
    sort_order: int,
) -> _CatalogSpec:
    return _CatalogSpec(
        key=key,
        section="redundancy",
        section_label="Redundancy Profiles",
        scope_name=scope_name,
        scope_label=scope_name,
        parameter_key="eta_chain_derate",
        parameter_label="Chain Efficiency (eta_chain_derate)",
        unit="eta",
        impact_scope="static_and_hourly",
        min_value=min_value,
        max_value=max_value,
        baseline_source=(
            "Uptime Institute Tier Standard and IEEE 3006.7 partial-load UPS "
            "efficiency assumptions used by the current engine."
        ),
        description=(
            "Power-chain efficiency used in the space/power solve and the hourly "
            "PUE engine for this redundancy level."
        ),
        sort_order=sort_order,
    )


_CATALOG_SPECS: tuple[_CatalogSpec, ...] = (
    _cooling_spec(
        key="cooling.crac_dx.pue_typical",
        scope_name="Air-Cooled CRAC (DX)",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Air-Cooled CRAC (DX)"]["pue_min"],
        max_value=COOLING_PROFILES["Air-Cooled CRAC (DX)"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 benchmarked against DX CRAC "
            "reference performance."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=1,
    ),
    _cooling_spec(
        key="cooling.crac_dx.cop_ref",
        scope_name="Air-Cooled CRAC (DX)",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Air-Cooled CRAC (DX)"]["COP_min"],
        max_value=COOLING_PROFILES["Air-Cooled CRAC (DX)"]["COP_max"],
        baseline_source="Emerson/Copeland typical DX CRAC reference performance.",
        description="Reference COP anchor for the hourly DX cooling curve.",
        sort_order=2,
    ),
    _cooling_spec(
        key="cooling.crac_dx.k_fan",
        scope_name="Air-Cooled CRAC (DX)",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.04,
        max_value=0.12,
        baseline_source=(
            "Current engine assumption for floor-standing CRAC fan overhead."
        ),
        description="Integrated CRAC fan overhead as a fraction of IT load.",
        sort_order=3,
    ),
    _cooling_spec(
        key="cooling.ahu_no_econ.pue_typical",
        scope_name="Air-Cooled AHU (No Economizer)",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Air-Cooled AHU (No Economizer)"]["pue_min"],
        max_value=COOLING_PROFILES["Air-Cooled AHU (No Economizer)"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 benchmarked against central "
            "air-handling systems without economizer support."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=4,
    ),
    _cooling_spec(
        key="cooling.ahu_no_econ.cop_ref",
        scope_name="Air-Cooled AHU (No Economizer)",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Air-Cooled AHU (No Economizer)"]["COP_min"],
        max_value=COOLING_PROFILES["Air-Cooled AHU (No Economizer)"]["COP_max"],
        baseline_source="Carrier 30XA reference performance for central AHU systems.",
        description="Reference COP anchor for the hourly air-handling cooling curve.",
        sort_order=5,
    ),
    _cooling_spec(
        key="cooling.ahu_no_econ.k_fan",
        scope_name="Air-Cooled AHU (No Economizer)",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.03,
        max_value=0.10,
        baseline_source=(
            "Current engine assumption for central AHU fan overhead without "
            "economizer support."
        ),
        description="Central AHU fan overhead as a fraction of IT load.",
        sort_order=6,
    ),
    _cooling_spec(
        key="cooling.air_chiller_econ.pue_typical",
        scope_name="Air-Cooled Chiller + Economizer",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Air-Cooled Chiller + Economizer"]["pue_min"],
        max_value=COOLING_PROFILES["Air-Cooled Chiller + Economizer"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 benchmarked against high-efficiency "
            "air-cooled chiller references."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=10,
    ),
    _cooling_spec(
        key="cooling.air_chiller_econ.cop_ref",
        scope_name="Air-Cooled Chiller + Economizer",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Air-Cooled Chiller + Economizer"]["COP_min"],
        max_value=COOLING_PROFILES["Air-Cooled Chiller + Economizer"]["COP_max"],
        baseline_source="Carrier 30XA/30XV at Eurovent conditions.",
        description="Reference COP anchor for the hourly cooling-performance curve.",
        sort_order=11,
    ),
    _cooling_spec(
        key="cooling.air_chiller_econ.k_fan",
        scope_name="Air-Cooled Chiller + Economizer",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.02,
        max_value=0.10,
        baseline_source=(
            "Current engine assumption for integrated fan and pump overhead on "
            "air-cooled chiller economizer systems."
        ),
        description="Fan and pump parasitic load as a fraction of IT load.",
        sort_order=12,
    ),
    _cooling_spec(
        key="cooling.water_chiller_econ.pue_typical",
        scope_name="Water-Cooled Chiller + Economizer",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Water-Cooled Chiller + Economizer"]["pue_min"],
        max_value=COOLING_PROFILES["Water-Cooled Chiller + Economizer"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 benchmarked against water-cooled "
            "centrifugal chiller references."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=20,
    ),
    _cooling_spec(
        key="cooling.water_chiller_econ.cop_ref",
        scope_name="Water-Cooled Chiller + Economizer",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Water-Cooled Chiller + Economizer"]["COP_min"],
        max_value=COOLING_PROFILES["Water-Cooled Chiller + Economizer"]["COP_max"],
        baseline_source="Trane CenTraVac AHRI 550/590 reference performance.",
        description="Reference COP anchor for the hourly wet-bulb-driven cooling curve.",
        sort_order=21,
    ),
    _cooling_spec(
        key="cooling.water_chiller_econ.k_fan",
        scope_name="Water-Cooled Chiller + Economizer",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.02,
        max_value=0.10,
        baseline_source=(
            "Current engine assumption including tower fans and pumps for the "
            "water-side economizer topology."
        ),
        description="Fan, pump, and tower parasitic load as a fraction of IT load.",
        sort_order=22,
    ),
    _cooling_spec(
        key="cooling.rdhx.pue_typical",
        scope_name="Rear Door Heat Exchanger (RDHx)",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Rear Door Heat Exchanger (RDHx)"]["pue_min"],
        max_value=COOLING_PROFILES["Rear Door Heat Exchanger (RDHx)"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 with rear-door heat exchanger "
            "deployments using the shared air-chiller economizer backbone."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=25,
    ),
    _cooling_spec(
        key="cooling.rdhx.cop_ref",
        scope_name="Rear Door Heat Exchanger (RDHx)",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Rear Door Heat Exchanger (RDHx)"]["COP_min"],
        max_value=COOLING_PROFILES["Rear Door Heat Exchanger (RDHx)"]["COP_max"],
        baseline_source=(
            "Current RDHx model reuses the air-chiller economizer reference chiller "
            "performance."
        ),
        description="Reference COP anchor for the hourly RDHx cooling curve.",
        sort_order=26,
    ),
    _cooling_spec(
        key="cooling.rdhx.k_fan",
        scope_name="Rear Door Heat Exchanger (RDHx)",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.02,
        max_value=0.08,
        baseline_source=(
            "Current engine assumption for reduced rack-room fan overhead with "
            "rear-door heat exchangers."
        ),
        description="Rear-door heat exchanger parasitic overhead as a fraction of IT load.",
        sort_order=27,
    ),
    _cooling_spec(
        key="cooling.dlc.pue_typical",
        scope_name="Direct Liquid Cooling (DLC / Cold Plate)",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Direct Liquid Cooling (DLC / Cold Plate)"]["pue_min"],
        max_value=COOLING_PROFILES["Direct Liquid Cooling (DLC / Cold Plate)"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 with warm-water DLC reference data "
            "from Asetek/CoolIT."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=30,
    ),
    _cooling_spec(
        key="cooling.dlc.cop_ref",
        scope_name="Direct Liquid Cooling (DLC / Cold Plate)",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Direct Liquid Cooling (DLC / Cold Plate)"]["COP_min"],
        max_value=COOLING_PROFILES["Direct Liquid Cooling (DLC / Cold Plate)"]["COP_max"],
        baseline_source="Asetek/CoolIT warm-water DLC reference performance.",
        description="Reference COP anchor for the hourly warm-water DLC cooling curve.",
        sort_order=31,
    ),
    _cooling_spec(
        key="cooling.dlc.k_fan",
        scope_name="Direct Liquid Cooling (DLC / Cold Plate)",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.01,
        max_value=0.08,
        baseline_source=(
            "Current engine assumption for residual air movement and CDU pump overhead "
            "in the hybrid DLC model."
        ),
        description="Residual air and pumping overhead as a fraction of IT load.",
        sort_order=32,
    ),
    _cooling_spec(
        key="cooling.immersion.pue_typical",
        scope_name="Immersion Cooling (Single-Phase)",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Immersion Cooling (Single-Phase)"]["pue_min"],
        max_value=COOLING_PROFILES["Immersion Cooling (Single-Phase)"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 with GRC/LiquidCool single-phase "
            "immersion reference data."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=40,
    ),
    _cooling_spec(
        key="cooling.immersion.cop_ref",
        scope_name="Immersion Cooling (Single-Phase)",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Immersion Cooling (Single-Phase)"]["COP_min"],
        max_value=COOLING_PROFILES["Immersion Cooling (Single-Phase)"]["COP_max"],
        baseline_source="GRC/LiquidCool published immersion reference performance.",
        description="Reference COP anchor for the hourly immersion cooling curve.",
        sort_order=41,
    ),
    _cooling_spec(
        key="cooling.immersion.k_fan",
        scope_name="Immersion Cooling (Single-Phase)",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.01,
        max_value=0.06,
        baseline_source=(
            "Current engine assumption for immersion circulation and auxiliary pump "
            "overhead."
        ),
        description="Immersion auxiliary overhead as a fraction of IT load.",
        sort_order=42,
    ),
    _cooling_spec(
        key="cooling.dry_cooler.pue_typical",
        scope_name="Free Cooling — Dry Cooler (Chiller-less)",
        parameter_key="pue_typical",
        parameter_label="Typical PUE",
        unit="PUE",
        impact_scope="static_and_hourly",
        min_value=COOLING_PROFILES["Free Cooling — Dry Cooler (Chiller-less)"]["pue_min"],
        max_value=COOLING_PROFILES["Free Cooling — Dry Cooler (Chiller-less)"]["pue_max"],
        baseline_source=(
            "Architecture Agreement Section 3.2 benchmarked against chiller-less "
            "dry-cooler references."
        ),
        description=(
            "Static PUE anchor used when hourly weather is not available and as the "
            "initial feasibility solve input."
        ),
        sort_order=45,
    ),
    _cooling_spec(
        key="cooling.dry_cooler.cop_ref",
        scope_name="Free Cooling — Dry Cooler (Chiller-less)",
        parameter_key="COP_ref",
        parameter_label="Reference COP",
        unit="COP",
        impact_scope="hourly_only",
        min_value=COOLING_PROFILES["Free Cooling — Dry Cooler (Chiller-less)"]["COP_min"],
        max_value=COOLING_PROFILES["Free Cooling — Dry Cooler (Chiller-less)"]["COP_max"],
        baseline_source="Airedale/Guntner dry-cooler fan power reference curves.",
        description="Reference COP anchor for the hourly dry-cooler fan curve.",
        sort_order=46,
    ),
    _cooling_spec(
        key="cooling.dry_cooler.k_fan",
        scope_name="Free Cooling — Dry Cooler (Chiller-less)",
        parameter_key="k_fan",
        parameter_label="Fan / Pump Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.02,
        max_value=0.08,
        baseline_source=(
            "Current engine assumption for chiller-less dry-cooler fan overhead."
        ),
        description="Dry-cooler parasitic fan overhead as a fraction of IT load.",
        sort_order=47,
    ),
    _redundancy_spec(
        key="redundancy.n.eta_chain_derate",
        scope_name="N",
        min_value=0.94,
        max_value=0.99,
        sort_order=100,
    ),
    _redundancy_spec(
        key="redundancy.n_plus_1.eta_chain_derate",
        scope_name="N+1",
        min_value=0.93,
        max_value=0.98,
        sort_order=101,
    ),
    _redundancy_spec(
        key="redundancy.two_n.eta_chain_derate",
        scope_name="2N",
        min_value=0.90,
        max_value=0.97,
        sort_order=102,
    ),
    _redundancy_spec(
        key="redundancy.two_n_plus_1.eta_chain_derate",
        scope_name="2N+1",
        min_value=0.88,
        max_value=0.96,
        sort_order=103,
    ),
    _CatalogSpec(
        key="misc.f_misc",
        section="misc",
        section_label="Miscellaneous Overhead",
        scope_name="global",
        scope_label="Miscellaneous Fixed Loads",
        parameter_key="f_misc",
        parameter_label="Fixed Miscellaneous Overhead",
        unit="fraction",
        impact_scope="hourly_only",
        min_value=0.0,
        max_value=0.05,
        baseline_source=(
            "EU Code of Conduct on Data Centre Energy Efficiency (JRC, 2022) "
            "miscellaneous-load envelope used by the current model."
        ),
        description=(
            "Lighting, BMS, security, and similar fixed-load fraction used by the "
            "hourly PUE engine."
        ),
        sort_order=200,
    ),
)

_CATALOG_BY_KEY = {spec.key: spec for spec in _CATALOG_SPECS}

_PRESET_SPECS: tuple[_PresetSpec, ...] = (
    _PresetSpec(
        key="high_efficiency_envelope",
        label="High-Efficiency Envelope",
        description=(
            "Scenario-local overlay that moves the validated cooling, redundancy, "
            "and hourly misc assumptions halfway toward the efficient end of each "
            "current catalog range without changing saved Settings overrides."
        ),
        source=(
            "Repo-curated scenario preset derived from the existing cited min/max "
            "ranges in the controlled override catalog."
        ),
        direction="efficient",
    ),
    _PresetSpec(
        key="conservative_validation_envelope",
        label="Conservative Validation Envelope",
        description=(
            "Scenario-local overlay that moves the validated cooling, redundancy, "
            "and hourly misc assumptions halfway toward the conservative end of "
            "each current catalog range for downside testing without changing "
            "saved Settings overrides."
        ),
        source=(
            "Repo-curated scenario preset derived from the existing cited min/max "
            "ranges in the controlled override catalog."
        ),
        direction="conservative",
    ),
)

_PRESET_BY_KEY = {spec.key: spec for spec in _PRESET_SPECS}


def clear_assumption_override_cache() -> None:
    """Invalidate cached settings after a save/reset."""
    _load_store_cached.cache_clear()
    _load_history_cached.cache_clear()


@lru_cache(maxsize=1)
def _load_store_cached() -> AssumptionOverrideStore:
    if not _OVERRIDES_PATH.exists():
        return AssumptionOverrideStore()

    data = json.loads(_OVERRIDES_PATH.read_text())
    store = AssumptionOverrideStore(**data)
    store.overrides = {
        key: override
        for key, override in store.overrides.items()
        if key in _CATALOG_BY_KEY
    }
    return store


def _load_store_copy() -> AssumptionOverrideStore:
    return _load_store_cached().model_copy(deep=True)


@lru_cache(maxsize=1)
def _load_history_cached() -> AssumptionOverrideHistoryStore:
    if not _HISTORY_PATH.exists():
        return AssumptionOverrideHistoryStore()
    data = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    return AssumptionOverrideHistoryStore(**data)


def _load_history_copy() -> AssumptionOverrideHistoryStore:
    return _load_history_cached().model_copy(deep=True)


def _save_store(store: AssumptionOverrideStore) -> None:
    if not store.overrides and _OVERRIDES_PATH.exists():
        _OVERRIDES_PATH.unlink()
        clear_assumption_override_cache()
        return

    _OVERRIDES_PATH.write_text(
        json.dumps(store.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    clear_assumption_override_cache()


def _save_history(store: AssumptionOverrideHistoryStore) -> None:
    if not store.entries and _HISTORY_PATH.exists():
        _HISTORY_PATH.unlink()
        clear_assumption_override_cache()
        return

    _HISTORY_PATH.write_text(
        json.dumps(store.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    clear_assumption_override_cache()


def _baseline_value(spec: _CatalogSpec) -> float:
    if spec.section == "cooling":
        return float(COOLING_PROFILES[spec.scope_name][spec.parameter_key])
    if spec.section == "redundancy":
        return float(REDUNDANCY_PROFILES[spec.scope_name][spec.parameter_key])
    return float(MISC_OVERHEAD[spec.parameter_key])


def _prefers_lower_value(spec: _CatalogSpec) -> bool:
    return spec.parameter_key in {"pue_typical", "k_fan", "f_misc"}


def _preset_value(spec: _CatalogSpec, preset: _PresetSpec) -> float:
    baseline_value = _baseline_value(spec)
    efficient_target = spec.min_value if _prefers_lower_value(spec) else spec.max_value
    conservative_target = spec.max_value if _prefers_lower_value(spec) else spec.min_value
    target = efficient_target if preset.direction == "efficient" else conservative_target
    return round((baseline_value + target) / 2.0, 4)


def _preset_justification(spec: _CatalogSpec, preset: _PresetSpec) -> str:
    if preset.direction == "efficient":
        return (
            f"Scenario-local preset '{preset.label}' moves {spec.parameter_label} "
            "toward the efficient end of the validated range without changing the "
            "saved Settings catalog."
        )
    return (
        f"Scenario-local preset '{preset.label}' moves {spec.parameter_label} "
        "toward the conservative end of the validated range for downside testing "
        "without changing the saved Settings catalog."
    )


def _resolve_preset_spec(preset_key: str | None) -> _PresetSpec | None:
    if preset_key is None:
        return None
    preset = _PRESET_BY_KEY.get(preset_key)
    if preset is None:
        raise ValueError(f"Unsupported assumption override preset '{preset_key}'")
    return preset


def validate_assumption_override_preset_key(preset_key: str | None) -> None:
    """Validate a scenario-local preset key when one is provided."""
    _resolve_preset_spec(preset_key)


def _build_entry(spec: _CatalogSpec, override: PersistedAssumptionOverride | None) -> AssumptionOverrideEntry:
    baseline_value = _baseline_value(spec)
    effective_value = override.value if override is not None else baseline_value
    return AssumptionOverrideEntry(
        key=spec.key,
        section=spec.section,
        section_label=spec.section_label,
        scope_label=spec.scope_label,
        parameter_label=spec.parameter_label,
        unit=spec.unit,
        impact_scope=spec.impact_scope,
        baseline_value=baseline_value,
        effective_value=effective_value,
        min_value=spec.min_value,
        max_value=spec.max_value,
        baseline_source=spec.baseline_source,
        description=spec.description,
        override=override,
    )


def get_assumption_overrides() -> AssumptionOverridesResponse:
    """Return the full curated override catalog with effective values."""
    store = _load_store_copy()
    entries = [
        _build_entry(spec, store.overrides.get(spec.key))
        for spec in sorted(_CATALOG_SPECS, key=lambda item: item.sort_order)
    ]
    return AssumptionOverridesResponse(
        updated_at_utc=store.updated_at_utc,
        active_override_count=len(store.overrides),
        assumptions=entries,
    )


def get_assumption_override_presets() -> AssumptionOverridePresetsResponse:
    """Return the curated scenario-local preset catalog."""
    presets: list[AssumptionOverridePreset] = []
    for preset in _PRESET_SPECS:
        values = [
            AssumptionOverridePresetValue(
                key=spec.key,
                section=spec.section,
                scope_label=spec.scope_label,
                parameter_label=spec.parameter_label,
                unit=spec.unit,
                impact_scope=spec.impact_scope,
                baseline_value=_baseline_value(spec),
                preset_value=_preset_value(spec, preset),
                justification=_preset_justification(spec, preset),
            )
            for spec in sorted(_CATALOG_SPECS, key=lambda item: item.sort_order)
        ]
        presets.append(
            AssumptionOverridePreset(
                key=preset.key,
                label=preset.label,
                description=preset.description,
                source=preset.source,
                override_count=len(values),
                overrides=values,
            )
        )

    return AssumptionOverridePresetsResponse(presets=presets)


def get_assumption_override_history(limit: int = 20) -> AssumptionOverrideHistoryResponse:
    """Return recent explicit override history entries, newest first."""
    history = _load_history_copy()
    entries = list(reversed(history.entries))
    if limit > 0:
        entries = entries[:limit]
    return AssumptionOverrideHistoryResponse(entries=entries)


def _append_history_entry(entry: AssumptionOverrideHistoryEntry) -> None:
    history = _load_history_copy()
    history.entries.append(entry)
    history.entries = history.entries[-100:]
    _save_history(history)


def _resolved_overrides(
    preset_key: str | None = None,
) -> dict[str, _ResolvedOverride]:
    resolved: dict[str, _ResolvedOverride] = {}
    store = _load_store_cached()
    for key, override in store.overrides.items():
        resolved[key] = _ResolvedOverride(
            value=override.value,
            source=override.source,
            justification=override.justification,
            updated_at_utc=override.updated_at_utc,
            origin="settings_override",
        )

    preset = _resolve_preset_spec(preset_key)
    if preset is None:
        return resolved

    for spec in _CATALOG_SPECS:
        previous_override = resolved.get(spec.key)
        previous_value = previous_override.value if previous_override is not None else _baseline_value(spec)
        resolved[spec.key] = _ResolvedOverride(
            value=_preset_value(spec, preset),
            source=preset.source,
            justification=_preset_justification(spec, preset),
            updated_at_utc=None,
            origin="scenario_preset",
            preset_key=preset.key,
            preset_label=preset.label,
            previous_value=previous_value,
        )

    return resolved


def _settings_history_item(
    spec: _CatalogSpec,
    before_override: PersistedAssumptionOverride | None,
    after_override: PersistedAssumptionOverride | None,
) -> AssumptionOverrideHistoryItem | None:
    before_state = before_override.model_dump(mode="json") if before_override else None
    after_state = after_override.model_dump(mode="json") if after_override else None
    if before_state == after_state:
        return None

    baseline_value = _baseline_value(spec)
    if before_override is None and after_override is not None:
        action = "activated"
        previous_value = baseline_value
        effective_value = after_override.value
        source = after_override.source
        justification = after_override.justification
    elif before_override is not None and after_override is None:
        action = "cleared"
        previous_value = before_override.value
        effective_value = baseline_value
        source = before_override.source
        justification = before_override.justification
    else:
        action = "updated"
        previous_value = before_override.value if before_override is not None else baseline_value
        effective_value = after_override.value if after_override is not None else baseline_value
        source = after_override.source if after_override is not None else ""
        justification = after_override.justification if after_override is not None else ""

    return AssumptionOverrideHistoryItem(
        action=action,
        key=spec.key,
        label=f"{spec.scope_label} - {spec.parameter_label}",
        scope_label=spec.scope_label,
        parameter_label=spec.parameter_label,
        unit=spec.unit,
        origin="settings_override",
        previous_value=previous_value,
        effective_value=effective_value,
        source=source,
        justification=justification,
    )


def save_assumption_override_updates(
    updates: list[AssumptionOverrideUpdate],
) -> AssumptionOverridesResponse:
    """Apply validated override updates and persist the settings file."""
    before_store = _load_store_copy()
    store = before_store.model_copy(deep=True)
    seen: set[str] = set()

    for update in updates:
        if update.key in seen:
            raise ValueError(f"Duplicate override key '{update.key}' in one request")
        seen.add(update.key)

        spec = _CATALOG_BY_KEY.get(update.key)
        if spec is None:
            raise ValueError(f"Unsupported assumption override key '{update.key}'")

        if update.override_value is None:
            store.overrides.pop(update.key, None)
            continue

        value = float(update.override_value)
        if value < spec.min_value or value > spec.max_value:
            raise ValueError(
                f"{spec.scope_label} - {spec.parameter_label} must stay between "
                f"{spec.min_value} and {spec.max_value}"
            )

        store.overrides[update.key] = PersistedAssumptionOverride(
            value=value,
            source=(update.source or "").strip(),
            justification=(update.justification or "").strip(),
            updated_at_utc=_now_utc_iso(),
        )

    store.updated_at_utc = _now_utc_iso() if store.overrides else None
    _save_store(store)
    history_items: list[AssumptionOverrideHistoryItem] = []
    for spec in sorted(_CATALOG_SPECS, key=lambda item: item.sort_order):
        history_item = _settings_history_item(
            spec,
            before_store.overrides.get(spec.key),
            store.overrides.get(spec.key),
        )
        if history_item is not None:
            history_items.append(history_item)
    if history_items:
        _append_history_entry(
            AssumptionOverrideHistoryEntry(
                id=uuid4().hex,
                recorded_at_utc=_now_utc_iso(),
                event_type="settings_update",
                title="Controlled overrides updated",
                summary=(
                    f"{len(history_items)} override change"
                    f"{'' if len(history_items) == 1 else 's'} saved; "
                    f"{len(store.overrides)} active persistent override"
                    f"{'' if len(store.overrides) == 1 else 's'} now configured."
                ),
                active_override_count=len(store.overrides),
                changes=history_items,
            )
        )

    return get_assumption_overrides()


def get_assumption_override_preset_label(preset_key: str | None) -> str | None:
    """Resolve a preset label for UI/result metadata."""
    preset = _resolve_preset_spec(preset_key)
    return preset.label if preset is not None else None


def get_effective_cooling_profile(cooling_type: str, preset_key: str | None = None) -> dict:
    """Return one cooling profile with any active overrides applied."""
    if cooling_type not in COOLING_PROFILES:
        raise KeyError(f"Unknown cooling profile '{cooling_type}'")

    profile = dict(COOLING_PROFILES[cooling_type])
    overrides = _resolved_overrides(preset_key)

    for spec in _CATALOG_SPECS:
        if spec.section != "cooling" or spec.scope_name != cooling_type:
            continue
        override = overrides.get(spec.key)
        if override is not None:
            profile[spec.parameter_key] = override.value

    return profile


def get_effective_redundancy_profile(
    redundancy_level: str,
    preset_key: str | None = None,
) -> dict:
    """Return one redundancy profile with any active overrides applied."""
    if redundancy_level not in REDUNDANCY_PROFILES:
        raise KeyError(f"Unknown redundancy profile '{redundancy_level}'")

    profile = dict(REDUNDANCY_PROFILES[redundancy_level])
    overrides = _resolved_overrides(preset_key)

    for spec in _CATALOG_SPECS:
        if spec.section != "redundancy" or spec.scope_name != redundancy_level:
            continue
        override = overrides.get(spec.key)
        if override is not None:
            profile[spec.parameter_key] = override.value

    return profile


def get_effective_misc_overhead(preset_key: str | None = None) -> dict:
    """Return the misc-overhead defaults with any active overrides applied."""
    misc = dict(MISC_OVERHEAD)
    override = _resolved_overrides(preset_key).get("misc.f_misc")
    if override is not None:
        misc["f_misc"] = override.value
    return misc


def get_effective_misc_overhead_fraction(preset_key: str | None = None) -> float:
    """Convenience helper for the hourly engine."""
    return float(get_effective_misc_overhead(preset_key)["f_misc"])


def get_applied_overrides_for_scenario(
    scenario: Scenario,
    *,
    include_hourly_effects: bool,
) -> list[AppliedAssumptionOverride]:
    """Return only the active overrides that affected this scenario run."""
    overrides = _resolved_overrides(scenario.assumption_override_preset_key)
    if not overrides:
        return []

    relevant_keys: list[str] = []

    for spec in _CATALOG_SPECS:
        if spec.section == "redundancy" and spec.scope_name == scenario.redundancy.value:
            relevant_keys.append(spec.key)
        elif (
            spec.section == "cooling"
            and spec.scope_name == scenario.cooling_type.value
            and (
                spec.impact_scope == "static_and_hourly"
                or include_hourly_effects
            )
        ):
            relevant_keys.append(spec.key)

    if include_hourly_effects:
        effective_profile = get_effective_cooling_profile(
            scenario.cooling_type.value,
            scenario.assumption_override_preset_key,
        )
        residual_type = effective_profile.get("residual_cooling_type")
        if isinstance(residual_type, str):
            for spec in _CATALOG_SPECS:
                if (
                    spec.section == "cooling"
                    and spec.scope_name == residual_type
                    and spec.impact_scope == "hourly_only"
                ):
                    relevant_keys.append(spec.key)

        relevant_keys.append("misc.f_misc")

    deduped_keys = list(dict.fromkeys(relevant_keys))
    applied: list[AppliedAssumptionOverride] = []
    for key in deduped_keys:
        override = overrides.get(key)
        if override is None:
            continue
        spec = _CATALOG_BY_KEY[key]
        applied.append(
            AppliedAssumptionOverride(
                key=key,
                label=f"{spec.scope_label} - {spec.parameter_label}",
                scope_label=spec.scope_label,
                parameter_label=spec.parameter_label,
                unit=spec.unit,
                baseline_value=_baseline_value(spec),
                previous_effective_value=override.previous_value,
                effective_value=override.value,
                source=override.source,
                justification=override.justification,
                origin=override.origin,
                preset_key=override.preset_key,
                preset_label=override.preset_label,
                updated_at_utc=override.updated_at_utc,
            )
        )

    return applied


def record_assumption_override_preset_run(
    *,
    preset_key: str | None,
    site_count: int,
    scenario_count: int,
    applied_overrides: list[AppliedAssumptionOverride],
) -> None:
    """Persist an explicit history event for a scenario-local preset run."""
    preset = _resolve_preset_spec(preset_key)
    if preset is None:
        return

    deduped_changes: list[AssumptionOverrideHistoryItem] = []
    seen: set[str] = set()
    for override in applied_overrides:
        if override.origin != "scenario_preset" or override.key in seen:
            continue
        seen.add(override.key)
        deduped_changes.append(
            AssumptionOverrideHistoryItem(
                action="preset_applied",
                key=override.key,
                label=override.label,
                scope_label=override.scope_label,
                parameter_label=override.parameter_label,
                unit=override.unit,
                origin=override.origin,
                previous_value=override.previous_effective_value,
                effective_value=override.effective_value,
                source=override.source,
                justification=override.justification,
            )
        )

    if not deduped_changes:
        return

    _append_history_entry(
        AssumptionOverrideHistoryEntry(
            id=uuid4().hex,
            recorded_at_utc=_now_utc_iso(),
            event_type="scenario_preset_run",
            title="Scenario-local preset applied",
            summary=(
                f"Preset '{preset.label}' overlaid {len(deduped_changes)} relevant "
                f"override key{'' if len(deduped_changes) == 1 else 's'} across "
                f"{scenario_count} scenario run{'' if scenario_count == 1 else 's'} "
                f"on {site_count} site{'' if site_count == 1 else 's'}."
            ),
            preset_key=preset.key,
            preset_label=preset.label,
            site_count=site_count,
            scenario_count=scenario_count,
            changes=deduped_changes,
        )
    )
