"""
Tests for daily hourly-profile aggregation used by the scenario API.
"""

from types import SimpleNamespace

from api.routes_scenario import _build_daily_profiles


def test_build_daily_profiles_aggregates_two_days():
    """Two 24-hour slices should become two daily profile points."""
    sim = SimpleNamespace(
        annual_pue=1.3,
        it_capacity_mean_kw=1500.0,
        it_capacity_p99_kw=1000.0,
        it_capacity_worst_kw=1000.0,
        it_capacity_best_kw=2000.0,
        hourly_it_kw=[1000.0] * 24 + [2000.0] * 24,
        hourly_pue=[1.2] * 24 + [1.4] * 24,
    )

    result = _build_daily_profiles(sim)

    assert result["hours"] == 48
    assert result["day_count"] == 2
    assert result["annual_pue"] == 1.3
    assert result["annual_mean_it_mw"] == 1.5
    assert result["committed_it_mw"] == 1.0
    assert result["worst_it_mw"] == 1.0
    assert result["best_it_mw"] == 2.0

    day_1, day_2 = result["days"]
    assert day_1 == {
        "day": 1,
        "it_avg_mw": 1.0,
        "it_min_mw": 1.0,
        "it_max_mw": 1.0,
        "pue_avg": 1.2,
        "pue_min": 1.2,
        "pue_max": 1.2,
    }
    assert day_2 == {
        "day": 2,
        "it_avg_mw": 2.0,
        "it_min_mw": 2.0,
        "it_max_mw": 2.0,
        "pue_avg": 1.4,
        "pue_min": 1.4,
        "pue_max": 1.4,
    }
