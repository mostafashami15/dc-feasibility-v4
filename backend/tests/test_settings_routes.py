import asyncio

import pytest

from api import routes_settings
from engine.assumption_overrides import (
    AssumptionOverrideHistoryEntry,
    AssumptionOverrideHistoryItem,
    AssumptionOverrideHistoryResponse,
    AssumptionOverrideEntry,
    AssumptionOverridePreset,
    AssumptionOverridePresetValue,
    AssumptionOverridePresetsResponse,
    AssumptionOverridesResponse,
    AssumptionOverridesUpdateRequest,
    PersistedAssumptionOverride,
)


def test_runtime_status_reports_cache_and_template_counts(monkeypatch):
    monkeypatch.setattr(routes_settings, "count_sites", lambda: 4)
    monkeypatch.setattr(routes_settings, "count_weather_caches", lambda: 3)
    monkeypatch.setattr(routes_settings, "count_solar_sites", lambda: 2)
    monkeypatch.setattr(routes_settings, "count_solar_profiles", lambda: 5)
    monkeypatch.setattr(
        routes_settings,
        "_template_names",
        lambda: ["base.html", "detailed_report.html", "executive_summary.html"],
    )

    result = asyncio.run(routes_settings.runtime_status_endpoint())

    assert result.model_dump() == {
        "sites_stored": 4,
        "weather_cached": 3,
        "solar_sites_cached": 2,
        "solar_profiles_cached": 5,
        "report_templates_available": 3,
        "report_template_names": [
            "base.html",
            "detailed_report.html",
            "executive_summary.html",
        ],
    }


def test_external_service_checks_return_probe_results(monkeypatch):
    def fake_probe(**kwargs):
        return routes_settings.ExternalServiceProbe(
            key=kwargs["key"],
            label=kwargs["label"],
            ok=kwargs["key"] != "pvgis_seriescalc",
            status_code=200 if kwargs["key"] != "pvgis_seriescalc" else 502,
            latency_ms=123,
            detail="ok" if kwargs["key"] != "pvgis_seriescalc" else "timeout",
        )

    monkeypatch.setattr(routes_settings, "_probe_http_service", fake_probe)

    result = asyncio.run(routes_settings.test_external_services_endpoint())

    assert len(result.services) == 3
    assert result.services[0].key == "open_meteo_archive"
    assert result.services[1].key == "open_meteo_geocoding"
    assert result.services[2].key == "pvgis_seriescalc"
    assert result.services[2].ok is False


def test_clear_cache_weather_only(monkeypatch):
    monkeypatch.setattr(routes_settings, "clear_weather_cache", lambda: 7)
    monkeypatch.setattr(routes_settings, "clear_all_solar_cache", lambda: 0)

    request = routes_settings.CacheClearRequest(target="weather")
    result = asyncio.run(routes_settings.clear_cache_endpoint(request))

    assert result.model_dump() == {
        "target": "weather",
        "removed_weather_files": 7,
        "removed_solar_profiles": 0,
    }


def test_clear_cache_all(monkeypatch):
    monkeypatch.setattr(routes_settings, "clear_weather_cache", lambda: 2)
    monkeypatch.setattr(routes_settings, "clear_all_solar_cache", lambda: 9)

    request = routes_settings.CacheClearRequest(target="all")
    result = asyncio.run(routes_settings.clear_cache_endpoint(request))

    assert result.model_dump() == {
        "target": "all",
        "removed_weather_files": 2,
        "removed_solar_profiles": 9,
    }


def test_assumption_overrides_catalog_endpoint(monkeypatch):
    payload = AssumptionOverridesResponse(
        updated_at_utc="2026-03-12T10:00:00+00:00",
        active_override_count=1,
        assumptions=[
            AssumptionOverrideEntry(
                key="cooling.air_chiller_econ.cop_ref",
                section="cooling",
                section_label="Cooling Profiles",
                scope_label="Air-Cooled Chiller + Economizer",
                parameter_label="Reference COP",
                unit="COP",
                impact_scope="hourly_only",
                baseline_value=5.5,
                effective_value=6.2,
                min_value=2.5,
                max_value=9.0,
                baseline_source="Carrier 30XA/30XV at Eurovent conditions.",
                description="Reference COP anchor for the hourly cooling-performance curve.",
                override=PersistedAssumptionOverride(
                    value=6.2,
                    source="Vendor test note",
                    justification="Site-specific chiller selection is more efficient than the baseline.",
                    updated_at_utc="2026-03-12T10:00:00+00:00",
                ),
            )
        ],
    )
    monkeypatch.setattr(routes_settings, "get_assumption_overrides", lambda: payload)

    result = asyncio.run(routes_settings.assumption_overrides_endpoint())

    assert result.active_override_count == 1
    assert result.assumptions[0].effective_value == 6.2
    assert result.assumptions[0].override is not None


def test_assumption_override_presets_endpoint(monkeypatch):
    payload = AssumptionOverridePresetsResponse(
        presets=[
            AssumptionOverridePreset(
                key="high_efficiency_envelope",
                label="High-Efficiency Envelope",
                description="Tightens assumptions toward the efficient side of the curated catalog.",
                source="Repo-curated preset.",
                override_count=2,
                overrides=[
                    AssumptionOverridePresetValue(
                        key="cooling.air_chiller_econ.pue_typical",
                        section="cooling",
                        scope_label="Air-Cooled Chiller + Economizer",
                        parameter_label="Typical PUE",
                        unit="PUE",
                        impact_scope="static_and_hourly",
                        baseline_value=1.38,
                        preset_value=1.31,
                        justification="Moves the static PUE toward the efficient end of the validated range.",
                    )
                ],
            )
        ]
    )
    monkeypatch.setattr(routes_settings, "get_assumption_override_presets", lambda: payload)

    result = asyncio.run(routes_settings.assumption_override_presets_endpoint())

    assert result.presets[0].key == "high_efficiency_envelope"
    assert result.presets[0].override_count == 2


def test_assumption_override_history_endpoint(monkeypatch):
    payload = AssumptionOverrideHistoryResponse(
        entries=[
            AssumptionOverrideHistoryEntry(
                id="history-1",
                recorded_at_utc="2026-03-12T10:30:00+00:00",
                event_type="scenario_preset_run",
                title="Scenario-local preset applied",
                summary="Preset overlaid two assumptions across one scenario run.",
                preset_key="high_efficiency_envelope",
                preset_label="High-Efficiency Envelope",
                site_count=1,
                scenario_count=1,
                changes=[
                    AssumptionOverrideHistoryItem(
                        action="preset_applied",
                        key="cooling.air_chiller_econ.pue_typical",
                        label="Air-Cooled Chiller + Economizer - Typical PUE",
                        scope_label="Air-Cooled Chiller + Economizer",
                        parameter_label="Typical PUE",
                        unit="PUE",
                        origin="scenario_preset",
                        previous_value=1.38,
                        effective_value=1.31,
                        source="Repo-curated preset.",
                        justification="Moves the static PUE toward the efficient end of the validated range.",
                    )
                ],
            )
        ]
    )

    def fake_history(limit):
        assert limit == 12
        return payload

    monkeypatch.setattr(routes_settings, "get_assumption_override_history", fake_history)

    result = asyncio.run(routes_settings.assumption_override_history_endpoint(limit=12))

    assert result.entries[0].event_type == "scenario_preset_run"
    assert result.entries[0].preset_key == "high_efficiency_envelope"


def test_update_assumption_overrides_endpoint(monkeypatch):
    def fake_save(updates):
        assert len(updates) == 1
        assert updates[0].key == "misc.f_misc"
        return AssumptionOverridesResponse(
            updated_at_utc="2026-03-12T10:15:00+00:00",
            active_override_count=1,
            assumptions=[],
        )

    monkeypatch.setattr(routes_settings, "save_assumption_override_updates", fake_save)

    request = AssumptionOverridesUpdateRequest(
        overrides=[
            {
                "key": "misc.f_misc",
                "override_value": 0.03,
                "source": "Ops metering review",
                "justification": "Recent metering shows higher fixed-load overhead than the default.",
            }
        ]
    )
    result = asyncio.run(routes_settings.update_assumption_overrides_endpoint(request))

    assert result.model_dump() == {
        "updated_at_utc": "2026-03-12T10:15:00+00:00",
        "active_override_count": 1,
        "assumptions": [],
    }


def test_update_assumption_overrides_returns_400(monkeypatch):
    monkeypatch.setattr(
        routes_settings,
        "save_assumption_override_updates",
        lambda updates: (_ for _ in ()).throw(ValueError("bad override")),
    )
    request = AssumptionOverridesUpdateRequest(overrides=[])

    with pytest.raises(routes_settings.HTTPException) as excinfo:
        asyncio.run(routes_settings.update_assumption_overrides_endpoint(request))

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "bad override"
