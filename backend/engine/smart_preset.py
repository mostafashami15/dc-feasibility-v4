"""
DC Feasibility Tool v4 — Smart Preset Engine
=============================================
Fixed load-type-to-cooling mappings for the Guided Mode.

Each load type maps to exactly ONE cooling topology, ONE density scenario,
and ONE redundancy level. These are hardcoded engineering best-practice
pairings, not ranked lists.

The Guided Mode runs ALL 6 load types automatically for a selected site
using these presets with full 8,760-hour hourly simulation (climate-specific
PUE, not static defaults).

Reference: Architecture Agreement v2.0, Sections 3.2, 3.15, 3.16
"""

from engine.models import LoadType, CoolingType, RedundancyLevel, DensityScenario


# ─────────────────────────────────────────────────────────────
# GUIDED MODE PRESET TABLE
# ─────────────────────────────────────────────────────────────
# Each load type has exactly one recommended cooling, density,
# and redundancy. Users wanting different combinations use
# Advanced Mode.

GUIDED_PRESETS: dict[str, dict] = {
    LoadType.COLOCATION_STANDARD.value: {
        "load_type": LoadType.COLOCATION_STANDARD,
        "cooling_type": CoolingType.AIR_CHILLER_ECON,
        "density_scenario": DensityScenario.TYPICAL,
        "redundancy": RedundancyLevel.N_PLUS_1,
        "rationale": (
            "Air-Cooled Chiller + Economizer is the industry standard for "
            "retail colocation. Best PUE (1.38) among compatible options with "
            "free-cooling capability."
        ),
    },
    LoadType.COLOCATION_HIGH_DENSITY.value: {
        "load_type": LoadType.COLOCATION_HIGH_DENSITY,
        "cooling_type": CoolingType.RDHX,
        "density_scenario": DensityScenario.TYPICAL,
        "redundancy": RedundancyLevel.N_PLUS_1,
        "rationale": (
            "Rear Door Heat Exchanger provides the best balance of PUE (1.30) "
            "and practicality for high-density colocation at 20 kW/rack."
        ),
    },
    LoadType.HPC.value: {
        "load_type": LoadType.HPC,
        "cooling_type": CoolingType.AIR_CHILLER_ECON,
        "density_scenario": DensityScenario.TYPICAL,
        "redundancy": RedundancyLevel.N_PLUS_1,
        "rationale": (
            "Air-Cooled Chiller + Economizer is a proven HPC topology with "
            "wide industry adoption and free-cooling capability."
        ),
    },
    LoadType.AI_GPU.value: {
        "load_type": LoadType.AI_GPU,
        "cooling_type": CoolingType.DLC,
        "density_scenario": DensityScenario.TYPICAL,
        "redundancy": RedundancyLevel.N_PLUS_1,
        "rationale": (
            "Direct Liquid Cooling is required for GPU-dense racks at 100 kW "
            "typical density. Best PUE (1.12) with warm water economizer."
        ),
    },
    LoadType.HYPERSCALE.value: {
        "load_type": LoadType.HYPERSCALE,
        "cooling_type": CoolingType.AIR_CHILLER_ECON,
        "density_scenario": DensityScenario.TYPICAL,
        "redundancy": RedundancyLevel.N_PLUS_1,
        "rationale": (
            "Air-Cooled Chiller + Economizer is the industry standard for "
            "hyperscale deployments with proven reliability at scale."
        ),
    },
    LoadType.EDGE_TELCO.value: {
        "load_type": LoadType.EDGE_TELCO,
        "cooling_type": CoolingType.AIR_CHILLER_ECON,
        "density_scenario": DensityScenario.TYPICAL,
        "redundancy": RedundancyLevel.N_PLUS_1,
        "rationale": (
            "Air-Cooled Chiller + Economizer is the best option among the "
            "3 compatible cooling types for edge/telco workloads."
        ),
    },
}


def get_guided_presets() -> list[dict]:
    """Return the full guided preset table for display.

    Returns a list of dicts, each containing:
        - load_type: str
        - cooling_type: str
        - density_scenario: str
        - density_kw: float (typical density for the load type)
        - redundancy: str
        - rationale: str
    """
    from engine.assumptions import LOAD_PROFILES

    result = []
    for load_type_value, preset in GUIDED_PRESETS.items():
        load_profile = LOAD_PROFILES[load_type_value]
        density_key = f"density_{preset['density_scenario'].value}_kw"

        result.append({
            "load_type": preset["load_type"].value,
            "cooling_type": preset["cooling_type"].value,
            "density_scenario": preset["density_scenario"].value,
            "density_kw": load_profile[density_key],
            "redundancy": preset["redundancy"].value,
            "rationale": preset["rationale"],
        })

    return result


def build_guided_scenarios() -> list[dict]:
    """Build Scenario objects for all 6 load types using guided presets.

    Returns a list of dicts with keys: load_type, cooling_type,
    density_scenario, redundancy (all as enum instances).
    """
    scenarios = []
    for preset in GUIDED_PRESETS.values():
        scenarios.append({
            "load_type": preset["load_type"],
            "cooling_type": preset["cooling_type"],
            "density_scenario": preset["density_scenario"],
            "redundancy": preset["redundancy"],
        })
    return scenarios
