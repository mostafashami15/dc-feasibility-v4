"""Tests for guided-mode smart presets."""

from engine.models import RedundancyLevel
from engine.smart_preset import build_guided_scenarios, get_guided_presets


def test_guided_presets_use_n_redundancy():
    presets = get_guided_presets()

    assert presets
    assert all(preset["redundancy"] == RedundancyLevel.N.value for preset in presets)


def test_build_guided_scenarios_use_n_redundancy():
    scenarios = build_guided_scenarios()

    assert scenarios
    assert all(scenario["redundancy"] == RedundancyLevel.N for scenario in scenarios)
