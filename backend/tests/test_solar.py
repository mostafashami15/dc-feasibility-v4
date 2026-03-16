"""
Tests for solar.py — PVGIS normalized profile workflow
======================================================
Network access is mocked. Every expected value is explicit.
"""

import pytest

from api.routes_green import _resolve_hourly_pv_input
from engine.solar import (
    PVGISNormalizedProfile,
    _parse_pvgis_hourly_response,
    build_representative_pvgis_profile,
    make_pvgis_profile_key,
    scale_normalized_profile,
)


def _sample_pvgis_json(p_values: list[float]) -> dict:
    return {
        "inputs": {
            "location": {"elevation": 122.7},
            "meteo_data": {"radiation_db": "PVGIS-SARAH3"},
            "pv_module": {"technology": "crystSi"},
            "mounting_system": {
                "fixed": {
                    "slope": {"value": 32.0},
                    "azimuth": {"value": -7.0},
                }
            },
        },
        "outputs": {
            "hourly": [{"P": value} for value in p_values],
        },
    }


class TestPVGISParsing:
    def test_parse_hourly_output_converts_watts_to_kw(self):
        profile, metadata = _parse_pvgis_hourly_response(
            _sample_pvgis_json([0.0, 500.0, 1000.0])
        )
        assert profile == [0.0, 0.5, 1.0]
        assert metadata["radiation_database"] == "PVGIS-SARAH3"
        assert metadata["elevation_m"] == pytest.approx(122.7)
        assert metadata["resolved_slope"] == pytest.approx(32.0)
        assert metadata["resolved_azimuth"] == pytest.approx(-7.0)

    def test_parse_requires_outputs_hourly(self):
        with pytest.raises(ValueError, match="outputs.hourly"):
            _parse_pvgis_hourly_response({"outputs": {}})


class TestRepresentativeProfile:
    def test_representative_profile_averages_years(self, monkeypatch: pytest.MonkeyPatch):
        year_values = {
            2019: [0.10] * 8760,
            2020: [0.30] * 8760,
        }

        def fake_fetch(**kwargs):
            year = kwargs["year"]
            return year_values[year], {
                "radiation_database": "PVGIS-SARAH3",
                "elevation_m": 125.0,
                "pv_module_info": "crystSi",
                "resolved_slope": 27.5,
                "resolved_azimuth": 3.0,
            }

        monkeypatch.setattr("engine.solar.fetch_pvgis_hourly_year", fake_fetch)

        profile = build_representative_pvgis_profile(
            site_id="site-1",
            latitude=45.4642,
            longitude=9.19,
            start_year=2019,
            end_year=2020,
            optimal_angles=True,
        )

        assert isinstance(profile, PVGISNormalizedProfile)
        assert profile.hours == 8760
        assert profile.hourly_pv_kw_per_kwp[0] == pytest.approx(0.20)
        assert profile.hourly_pv_kw_per_kwp[-1] == pytest.approx(0.20)
        assert profile.surface_tilt_deg == pytest.approx(27.5)
        assert profile.surface_azimuth_deg == pytest.approx(3.0)
        assert profile.radiation_database == "PVGIS-SARAH3"

    def test_manual_angles_require_explicit_inputs(self):
        with pytest.raises(ValueError, match="surface_tilt_deg is required"):
            build_representative_pvgis_profile(
                site_id="site-1",
                latitude=45.4642,
                longitude=9.19,
                start_year=2019,
                end_year=2019,
                optimal_angles=False,
                surface_tilt_deg=None,
                surface_azimuth_deg=0.0,
            )


class TestProfileKeysAndScaling:
    def test_cache_key_is_stable(self):
        first = make_pvgis_profile_key(
            site_id="site-1",
            latitude=45.4642,
            longitude=9.19,
            start_year=2019,
            end_year=2023,
            pv_technology="crystSi",
            mounting_place="free",
            system_loss_pct=14.0,
            use_horizon=True,
            optimal_angles=True,
            surface_tilt_deg=None,
            surface_azimuth_deg=None,
        )
        second = make_pvgis_profile_key(
            site_id="site-1",
            latitude=45.4642001,
            longitude=9.1900001,
            start_year=2019,
            end_year=2023,
            pv_technology="crystSi",
            mounting_place="free",
            system_loss_pct=14.0,
            use_horizon=True,
            optimal_angles=True,
            surface_tilt_deg=None,
            surface_azimuth_deg=None,
        )
        assert first == second

    def test_scaling_multiplies_normalized_profile(self):
        assert scale_normalized_profile([0.1, 0.5, 0.9], 2500) == [
            pytest.approx(250.0),
            pytest.approx(1250.0),
            pytest.approx(2250.0),
        ]


class TestRoutePVResolution:
    def test_manual_profile_has_priority(self):
        resolved, source = _resolve_hourly_pv_input(
            site_id="site-1",
            expected_hours=3,
            hourly_pv_kw=[1.0, 2.0, 3.0],
            pvgis_profile_key="ignored",
            pv_capacity_kwp=100.0,
        )
        assert resolved == [1.0, 2.0, 3.0]
        assert source == "manual"

    def test_cached_pvgis_profile_is_scaled(self, monkeypatch: pytest.MonkeyPatch):
        normalized_profile = [0.2] * 8760
        normalized_profile[1] = 0.4
        normalized_profile[2] = 0.6
        monkeypatch.setattr(
            "api.routes_green.get_solar_profile",
            lambda site_id, profile_key: {
                "site_id": site_id,
                "latitude": 45.4642,
                "longitude": 9.19,
                "profile_key": profile_key,
                "start_year": 2019,
                "end_year": 2023,
                "years_averaged": [2019, 2020, 2021, 2022, 2023],
                "pv_technology": "crystSi",
                "mounting_place": "free",
                "system_loss_pct": 14.0,
                "use_horizon": True,
                "optimal_angles": True,
                "surface_tilt_deg": 27.5,
                "surface_azimuth_deg": 3.0,
                "hours": 8760,
                "hourly_pv_kw_per_kwp": normalized_profile,
                "source": "PVGIS test",
                "radiation_database": "PVGIS-SARAH3",
                "elevation_m": 125.0,
                "pv_module_info": "crystSi",
            },
        )

        resolved, source = _resolve_hourly_pv_input(
            site_id="site-1",
            expected_hours=8760,
            hourly_pv_kw=None,
            pvgis_profile_key="profile-1",
            pv_capacity_kwp=1000,
        )

        assert resolved[0] == pytest.approx(200.0)
        assert resolved[1] == pytest.approx(400.0)
        assert resolved[2] == pytest.approx(600.0)
        assert len(resolved) == 8760
        assert source == "pvgis"
