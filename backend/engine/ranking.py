"""
DC Feasibility Tool v4 — Scenario Ranking & Load Mix Optimization
==================================================================
Two functions:

1. score_scenario()     — Compute a composite 0–100 score for one scenario,
                          used to rank scenarios in the comparison table.

2. optimize_load_mix()  — Given total IT capacity and allowed workload types,
                          find the best allocation across load types.
                          Section 3.12 of the Architecture Agreement.

Scoring philosophy:
    There is no industry standard for composite data center scoring.
    We define five components with configurable weights that reflect
    Metlen's priorities: efficiency first, then capacity, then utilization,
    then feasibility, then physical fit.

    Every weight is a default with a justification. Users can override
    all weights via the API.

Reference: Architecture Agreement v3.0, Sections 3.12, 3.17
"""

import itertools
from typing import Optional
from pydantic import BaseModel, Field

from engine.models import (
    RAGStatus,
    LoadType,
    CoolingType,
    DensityScenario,
)
from engine.assumptions import (
    COOLING_PROFILES,
    evaluate_compatibility,
    get_rack_density_kw,
)
from engine.assumption_overrides import get_effective_cooling_profile


# ─────────────────────────────────────────────────────────────
# Scoring Constants
# ─────────────────────────────────────────────────────────────

DEFAULT_SCORING_WEIGHTS: dict[str, float] = {
    "pue_efficiency": 0.35,
    # PUE is the primary efficiency metric. Lower PUE = less energy
    # overhead = lower OPEX. This is what clients compare across sites.
    # Weight 35%: largest single component.
    # Source: Engineering judgment; PUE is the industry's dominant KPI
    # per Uptime Institute and The Green Grid.

    "it_capacity": 0.25,
    # More IT capacity = more revenue potential for the data center.
    # This is the product you sell to tenants.
    # Weight 25%: second most important factor.

    "space_utilization": 0.15,
    # Higher rack deployment vs. available capacity = better ROI on
    # the building investment. A scenario that fills 90% of available
    # racks is better than one that fills 50%.
    # Weight 15%: important but secondary to PUE and capacity.

    "rag_status": 0.15,
    # The RAG status encodes all feasibility constraints (compatibility,
    # density limits, building height, etc.) into a single signal.
    # BLUE scenarios are the best; RED are non-viable.
    # Weight 15%: equal to space utilization.

    "infrastructure_fit": 0.10,
    # Whether the infrastructure equipment physically fits on the site.
    # Critical constraint but binary in nature — either it fits or it
    # doesn't. Scored on a gradient to prefer sites with more margin.
    # Weight 10%: smallest weight (tie-breaker role).
}

# PUE normalization range
# PUE 1.0 = theoretical perfect (score 100)
# PUE 2.0 = very poor (score 0)
# Linear interpolation between these bounds.
PUE_BEST = 1.0
PUE_WORST = 2.0

# RAG status scores (normalized 0–100)
RAG_SCORES: dict[RAGStatus, float] = {
    RAGStatus.BLUE: 100.0,
    RAGStatus.GREEN: 75.0,
    RAGStatus.AMBER: 25.0,
    RAGStatus.RED: 0.0,
}

# Load Mix Optimization defaults
DEFAULT_STEP_PCT = 10
# Increment size for load mix generation (% of total IT).
# 10% = 11 possible values per load type (0, 10, 20, ..., 100).
# 5% = 21 values (more combinations, slower, more granular).
# Source: Architecture Agreement Section 3.12.

DEFAULT_MIN_RACKS = 10
# Minimum number of racks per load type to be viable.
# You can't deploy 1 AI rack — you need a critical mass for
# the infrastructure investment to make sense.
# Source: Architecture Agreement Section 3.12.

DEFAULT_TOP_N = 5
# Number of top combinations to return.
# Source: Architecture Agreement Section 3.12 — "Present top 5."


# ─────────────────────────────────────────────────────────────
# Result Models
# ─────────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    """Detailed score breakdown showing each component's contribution.

    This is displayed in the Results Dashboard when the user hovers
    over or clicks a scenario's composite score.
    """

    # ── Component scores (each 0–100 before weighting) ──
    pue_score: float = Field(description="PUE efficiency score (0–100)")
    it_capacity_score: float = Field(description="IT capacity score (0–100)")
    space_utilization_score: float = Field(description="Space utilization score (0–100)")
    rag_score: float = Field(description="RAG status score (0–100)")
    infrastructure_fit_score: float = Field(description="Infrastructure fit score (0–100)")

    # ── Weights used ──
    weights: dict[str, float] = Field(description="Scoring weights applied")

    # ── Final composite ──
    composite_score: float = Field(
        description="Weighted composite score (0–100)"
    )


class LoadMixAllocation(BaseModel):
    """One allocation in a load mix combination.

    Represents "put X% of the IT capacity into load type Y."
    """
    load_type: str = Field(description="Workload type name")
    share_pct: float = Field(description="Percentage of total IT allocated (0–100)")
    it_load_mw: float = Field(description="IT load allocated to this type (MW)")
    rack_count: int = Field(description="Number of racks for this allocation")
    rack_density_kw: float = Field(description="Rack density used (kW)")


class LoadMixCandidate(BaseModel):
    """One candidate combination in the load mix optimization.

    Contains the allocation breakdown, compatibility checks,
    blended PUE, and composite score for ranking.
    """
    rank: int = Field(description="Rank (1 = best)")
    allocations: list[LoadMixAllocation] = Field(
        description="Per-load-type allocation breakdown"
    )
    total_racks: int = Field(description="Total rack count across all types")
    all_compatible: bool = Field(
        description="True if all load types are compatible with the cooling type"
    )
    blended_pue: float = Field(
        description=(
            "IT-share-weighted PUE across the mix. "
            "Each load type's PUE comes from the cooling profile typical."
        )
    )
    score: float = Field(description="Composite ranking score (0–100)")
    trade_off_notes: list[str] = Field(
        default_factory=list,
        description="Human-readable trade-off explanations"
    )


class LoadMixResult(BaseModel):
    """Output of the load mix optimizer (Section 3.12).

    Contains the top N candidate combinations ranked by composite score.
    """
    total_it_mw: float = Field(description="Total IT capacity being allocated (MW)")
    allowed_load_types: list[str] = Field(
        default_factory=list,
        description="Load types included in the optimization request"
    )
    cooling_type: str = Field(description="Cooling type used for compatibility checks")
    density_scenario: str = Field(description="Density scenario used (low/typical/high)")
    step_pct: int = Field(description="Step size used for combination generation (%)")
    min_racks: int = Field(description="Minimum rack threshold per load type")
    total_candidates_evaluated: int = Field(
        description="Number of combinations evaluated before ranking"
    )
    top_candidates: list[LoadMixCandidate] = Field(
        description="Top N candidates ranked by score"
    )
    assumption_override_preset_key: str | None = Field(
        default=None,
        description="Assumption override preset used for PUE lookup (if any)",
    )


# ─────────────────────────────────────────────────────────────
# Scenario Scoring
# ─────────────────────────────────────────────────────────────

def score_scenario(
    pue: float,
    it_load_mw: float,
    max_it_load_mw: float,
    racks_deployed: int,
    effective_racks: int,
    rag_status: RAGStatus,
    ground_utilization_ratio: float = 0.0,
    roof_utilization_ratio: float = 0.0,
    weights: Optional[dict[str, float]] = None,
) -> ScoreBreakdown:
    """Compute composite ranking score for one scenario.

    Normalizes each component to 0–100, then applies weighted sum.
    Used to populate ScenarioResult.score in the Results Dashboard.

    Args:
        pue:
            Annual PUE (energy-weighted from hourly engine, or static fallback).
            Lower is better. Normalized linearly: 1.0→100, 2.0→0.

        it_load_mw:
            Achievable IT load for this scenario (MW).
            Higher is better. Normalized relative to max_it_load_mw.

        max_it_load_mw:
            Maximum achievable IT load across all scenarios being compared.
            Used to normalize it_load_mw to 0–100. If only one scenario,
            pass the same value as it_load_mw (scores 100).

        racks_deployed:
            Actual racks deployed in this scenario.

        effective_racks:
            Maximum racks available by space (after cooling adjustment).
            Used to compute space utilization ratio.

        rag_status:
            Feasibility status from power.py RAG evaluation.
            BLUE=100, GREEN=75, AMBER=25, RED=0.

        ground_utilization_ratio:
            From footprint.py. Ground equipment / available outdoor area.
            >1.0 means doesn't fit. Default 0.0 (no footprint computed yet).

        roof_utilization_ratio:
            From footprint.py. Roof equipment / building roof area.
            >1.0 means doesn't fit. Default 0.0 (no footprint computed yet).

        weights:
            Optional custom scoring weights. If None, uses DEFAULT_SCORING_WEIGHTS.
            Must contain all 5 keys and sum to 1.0.

    Returns:
        ScoreBreakdown with per-component scores and weighted composite.

    Example:
        >>> breakdown = score_scenario(
        ...     pue=1.25, it_load_mw=15.0, max_it_load_mw=20.0,
        ...     racks_deployed=1500, effective_racks=1666,
        ...     rag_status=RAGStatus.GREEN,
        ... )
        >>> print(f"Score: {breakdown.composite_score:.1f}/100")
    """
    w = weights if weights is not None else DEFAULT_SCORING_WEIGHTS

    # ══════════════════════════════════════════════════════════
    # 1. PUE Efficiency Score (0–100)
    # ══════════════════════════════════════════════════════════
    # Linear normalization: PUE 1.0 → 100, PUE 2.0 → 0.
    # Clamped to [0, 100] for PUEs outside normal range.
    if PUE_WORST > PUE_BEST:
        pue_raw = (PUE_WORST - pue) / (PUE_WORST - PUE_BEST) * 100
    else:
        pue_raw = 100.0
    pue_score = max(0.0, min(100.0, pue_raw))

    # ══════════════════════════════════════════════════════════
    # 2. IT Capacity Score (0–100)
    # ══════════════════════════════════════════════════════════
    # Proportional to the maximum across all scenarios being compared.
    # If this is the best scenario, it scores 100.
    if max_it_load_mw > 0:
        it_score = (it_load_mw / max_it_load_mw) * 100
    else:
        it_score = 0.0
    it_score = max(0.0, min(100.0, it_score))

    # ══════════════════════════════════════════════════════════
    # 3. Space Utilization Score (0–100)
    # ══════════════════════════════════════════════════════════
    # What fraction of available rack positions are actually used?
    # 100% utilization → score 100. 0% → score 0.
    if effective_racks > 0:
        space_score = (racks_deployed / effective_racks) * 100
    else:
        space_score = 0.0
    space_score = max(0.0, min(100.0, space_score))

    # ══════════════════════════════════════════════════════════
    # 4. RAG Status Score (0–100)
    # ══════════════════════════════════════════════════════════
    # Direct mapping from the 4-level system.
    rag_score = RAG_SCORES.get(rag_status, 0.0)

    # ══════════════════════════════════════════════════════════
    # 5. Infrastructure Fit Score (0–100)
    # ══════════════════════════════════════════════════════════
    # Based on the WORST of ground and roof utilization.
    # Utilization < 0.5 → plenty of room → score 100
    # Utilization 0.5–1.0 → tight but fits → linear 100→50
    # Utilization > 1.0 → DOES NOT FIT → score 0
    worst_util = max(ground_utilization_ratio, roof_utilization_ratio)

    if worst_util > 1.0:
        infra_score = 0.0
    elif worst_util <= 0.5:
        infra_score = 100.0
    else:
        # Linear interpolation: 0.5 → 100, 1.0 → 50
        infra_score = 100.0 - (worst_util - 0.5) * 100.0
    infra_score = max(0.0, min(100.0, infra_score))

    # ══════════════════════════════════════════════════════════
    # Weighted Composite
    # ══════════════════════════════════════════════════════════
    composite = (
        pue_score * w["pue_efficiency"]
        + it_score * w["it_capacity"]
        + space_score * w["space_utilization"]
        + rag_score * w["rag_status"]
        + infra_score * w["infrastructure_fit"]
    )

    return ScoreBreakdown(
        pue_score=round(pue_score, 2),
        it_capacity_score=round(it_score, 2),
        space_utilization_score=round(space_score, 2),
        rag_score=round(rag_score, 2),
        infrastructure_fit_score=round(infra_score, 2),
        weights=w,
        composite_score=round(composite, 2),
    )


# ─────────────────────────────────────────────────────────────
# Load Mix Optimization (Architecture Agreement Section 3.12)
# ─────────────────────────────────────────────────────────────

def optimize_load_mix(
    total_it_mw: float,
    allowed_load_types: list[LoadType],
    cooling_type: CoolingType,
    density_scenario: DensityScenario = DensityScenario.TYPICAL,
    step_pct: int = DEFAULT_STEP_PCT,
    min_racks: int = DEFAULT_MIN_RACKS,
    top_n: int = DEFAULT_TOP_N,
    assumption_override_preset_key: str | None = None,
) -> LoadMixResult:
    """Find optimal workload allocation across load types.

    Given X MW of total IT and a set of allowed workload types,
    generate all combinations in step_pct increments and rank them.

    Algorithm (Architecture Agreement Section 3.12):
        1. Generate all share combinations that sum to 100%
        2. For each combination:
           a. Compute rack count per type
           b. Verify minimum viable allocation (min_racks constraint)
           c. Check cooling compatibility per type
           d. Compute blended PUE (IT-share-weighted)
        3. Filter out combinations that violate min_racks
        4. Rank by composite score
        5. Return top N with trade-off notes

    Blended PUE formula:
        PUE_blended = Σ (share_i × PUE_typical_i)
        where share_i = fraction of IT allocated to load type i.

        This uses the static PUE from cooling profiles as a proxy.
        The actual hourly PUE would require running the 8760 engine
        per combination — too expensive for optimization sweeps.
        The static PUE correctly captures the relative efficiency
        differences between cooling topologies for ranking purposes.

    Args:
        total_it_mw:
            Total IT capacity to allocate (MW). Must be > 0.

        allowed_load_types:
            Which workload types to include. Must have ≥ 2 types
            (single type = no optimization needed).

        cooling_type:
            Cooling system for compatibility checks and PUE lookup.

        density_scenario:
            Which rack density to use (low/typical/high).
            Default: TYPICAL.

        step_pct:
            Increment size in percentage points. Default 10.
            Smaller = more combinations, finer granularity, slower.

        min_racks:
            Minimum racks per active load type. Default 10.
            Types with fewer racks than this are excluded.

        top_n:
            Number of top candidates to return. Default 5.

    Returns:
        LoadMixResult with top N ranked candidates.

    Raises:
        ValueError: If total_it_mw ≤ 0 or fewer than 2 load types.

    Example:
        >>> result = optimize_load_mix(
        ...     total_it_mw=20.0,
        ...     allowed_load_types=[LoadType.AI_GPU, LoadType.HPC, LoadType.HYPERSCALE],
        ...     cooling_type=CoolingType.DLC,
        ... )
        >>> for c in result.top_candidates:
        ...     allocs = ", ".join(f"{a.load_type}: {a.share_pct}%" for a in c.allocations)
        ...     print(f"#{c.rank} PUE={c.blended_pue:.2f} — {allocs}")
    """
    if total_it_mw <= 0:
        raise ValueError(f"total_it_mw must be positive: {total_it_mw}")
    if len(allowed_load_types) < 2:
        raise ValueError(
            f"Need at least 2 load types for optimization, got {len(allowed_load_types)}"
        )
    if step_pct < 1 or step_pct > 50:
        raise ValueError(f"step_pct must be 1–50, got {step_pct}")

    n_types = len(allowed_load_types)
    cooling_profile = get_effective_cooling_profile(
        cooling_type.value, preset_key=assumption_override_preset_key
    )
    cooling_pue_typical = cooling_profile["pue_typical"]

    # ── Pre-compute rack densities per type ──
    densities: dict[str, float] = {}
    for lt in allowed_load_types:
        densities[lt.value] = get_rack_density_kw(lt.value, density_scenario.value)

    # ── Generate all share combinations summing to 100% ──
    # Using integer arithmetic: steps from 0 to 100 in step_pct increments.
    # For n_types load types, we need all non-negative integer tuples
    # (s1, s2, ..., sn) where each si is a multiple of step_pct and sum = 100.
    possible_shares = list(range(0, 101, step_pct))
    all_combos = [
        combo for combo in itertools.product(possible_shares, repeat=n_types)
        if sum(combo) == 100
    ]

    # ── Evaluate each combination ──
    candidates: list[LoadMixCandidate] = []

    for combo in all_combos:
        allocations: list[LoadMixAllocation] = []
        total_racks = 0
        all_compatible = True
        has_conditional_compatibility = False
        weighted_pue_sum = 0.0
        valid = True
        notes: list[str] = []

        for i, lt in enumerate(allowed_load_types):
            share_pct = float(combo[i])
            if share_pct == 0:
                continue  # Skip types with 0% allocation

            share_frac = share_pct / 100.0
            it_mw = total_it_mw * share_frac
            density_kw = densities[lt.value]
            rack_count = int(it_mw * 1000 / density_kw)

            # ── Minimum viable allocation check ──
            # Source: Architecture Agreement Section 3.12
            # "min_racks × rack_density_kW / 1000 MW"
            min_mw = min_racks * density_kw / 1000
            if it_mw < min_mw or rack_count < min_racks:
                valid = False
                break  # This combination violates the constraint

            # ── Cooling compatibility check ──
            compatibility_status, compatibility_reasons = evaluate_compatibility(
                lt.value,
                cooling_type.value,
                density_scenario=density_scenario.value,
                rack_density_kw=density_kw,
            )
            if compatibility_status == "incompatible":
                all_compatible = False
                valid = False
                break

            if compatibility_status == "conditional":
                has_conditional_compatibility = True
                notes.extend(compatibility_reasons)

            # ── Blended PUE contribution ──
            # Each load type uses the same cooling system PUE (since they
            # share the same facility). The "blended" PUE is simply the
            # cooling profile's typical PUE — it doesn't change with mix.
            # However, we weight by share to support future per-type cooling.
            weighted_pue_sum += share_frac * cooling_pue_typical

            allocations.append(LoadMixAllocation(
                load_type=lt.value,
                share_pct=share_pct,
                it_load_mw=round(it_mw, 3),
                rack_count=rack_count,
                rack_density_kw=density_kw,
            ))
            total_racks += rack_count

        if not valid or len(allocations) == 0:
            continue  # Skip invalid combinations

        blended_pue = round(weighted_pue_sum, 4)

        # ── Generate trade-off notes ──
        # Identify the dominant allocation
        dominant = max(allocations, key=lambda a: a.share_pct)
        if dominant.share_pct >= 70:
            notes.append(
                f"Dominated by {dominant.load_type} ({dominant.share_pct:.0f}%)"
            )

        # Check for high-density types
        high_density_allocs = [a for a in allocations if a.rack_density_kw >= 40]
        if high_density_allocs:
            names = ", ".join(a.load_type for a in high_density_allocs)
            notes.append(f"High-density workloads ({names}) — verify cooling capacity")

        # Balanced mix note
        shares = [a.share_pct for a in allocations]
        if len(shares) >= 2 and max(shares) - min(shares) <= step_pct:
            notes.append("Balanced allocation — good workload diversity")

        if has_conditional_compatibility:
            notes.append(
                "Contains conditional compatibility cases — validate thermal envelope"
            )

        # ── Score this combination ──
        # Use a simplified scoring: PUE + compatibility + rack utilization
        # PUE score: same normalization as score_scenario
        pue_raw = (PUE_WORST - blended_pue) / (PUE_WORST - PUE_BEST) * 100
        pue_score = max(0.0, min(100.0, pue_raw))

        # Compatibility bonus: conditional combinations stay viable but must not
        # outrank clearly compatible mixes on diversity alone.
        compat_score = 30.0 if has_conditional_compatibility else 100.0

        # Diversity bonus: more balanced allocations score higher
        # Measured by evenness (1 - Gini-like coefficient)
        if len(allocations) >= 2:
            mean_share = 100.0 / len(allocations)
            deviation = sum(abs(a.share_pct - mean_share) for a in allocations)
            max_deviation = 2 * (100.0 - mean_share)  # worst case: one type at 100%
            if max_deviation > 0:
                evenness = 1.0 - (deviation / max_deviation)
            else:
                evenness = 1.0
            diversity_score = evenness * 100.0
        else:
            diversity_score = 0.0  # Single type = no diversity

        # Composite: 50% PUE + 30% compatibility + 20% diversity
        combo_score = pue_score * 0.50 + compat_score * 0.30 + diversity_score * 0.20

        candidates.append(LoadMixCandidate(
            rank=0,  # Set after sorting
            allocations=allocations,
            total_racks=total_racks,
            all_compatible=all_compatible,
            blended_pue=blended_pue,
            score=round(combo_score, 2),
            trade_off_notes=notes,
        ))

    # ── Sort by score (descending) and assign ranks ──
    candidates.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(candidates):
        c.rank = i + 1

    top = candidates[:top_n]

    return LoadMixResult(
        total_it_mw=total_it_mw,
        allowed_load_types=[load_type.value for load_type in allowed_load_types],
        cooling_type=cooling_type.value,
        density_scenario=density_scenario.value,
        step_pct=step_pct,
        min_racks=min_racks,
        total_candidates_evaluated=len(candidates),
        top_candidates=top,
        assumption_override_preset_key=assumption_override_preset_key,
    )
