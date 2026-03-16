"""
Tests for ranking.py — Scenario Ranking & Load Mix Optimization
================================================================
Every expected value is hand-calculated from the scoring formulas
defined in ranking.py and the defaults in assumptions.py.

NO random values.
"""

import pytest

from engine.models import (
    RAGStatus,
    LoadType,
    CoolingType,
    DensityScenario,
)
from engine.assumptions import LOAD_PROFILES, COOLING_PROFILES
from engine.ranking import (
    score_scenario,
    optimize_load_mix,
    ScoreBreakdown,
    LoadMixResult,
    LoadMixCandidate,
    DEFAULT_SCORING_WEIGHTS,
    RAG_SCORES,
    PUE_BEST,
    PUE_WORST,
    DEFAULT_MIN_RACKS,
    DEFAULT_STEP_PCT,
)


# ─────────────────────────────────────────────────────────────
# Scenario Scoring Tests
# ─────────────────────────────────────────────────────────────

class TestScoreScenarioBasic:
    """Test composite scoring with known inputs and hand-calculated results."""

    def test_perfect_scenario(self):
        """Perfect scenario: PUE=1.0, max IT, full utilization, BLUE, fits easily.

        Hand calculation:
            pue_score = (2.0 - 1.0) / (2.0 - 1.0) × 100 = 100.0
            it_score = (20.0 / 20.0) × 100 = 100.0
            space_score = (1666 / 1666) × 100 = 100.0
            rag_score = 100.0 (BLUE)
            infra_score = 100.0 (utilization 0.1 < 0.5)

            composite = 100×0.35 + 100×0.25 + 100×0.15 + 100×0.15 + 100×0.10
                      = 35 + 25 + 15 + 15 + 10 = 100.0
        """
        result = score_scenario(
            pue=1.0,
            it_load_mw=20.0,
            max_it_load_mw=20.0,
            racks_deployed=1666,
            effective_racks=1666,
            rag_status=RAGStatus.BLUE,
            ground_utilization_ratio=0.1,
            roof_utilization_ratio=0.1,
        )

        assert isinstance(result, ScoreBreakdown)
        assert result.pue_score == 100.0
        assert result.it_capacity_score == 100.0
        assert result.space_utilization_score == 100.0
        assert result.rag_score == 100.0
        assert result.infrastructure_fit_score == 100.0
        assert result.composite_score == 100.0

    def test_worst_scenario(self):
        """Worst scenario: PUE=2.0, 0 IT, no racks, RED, doesn't fit.

        Hand calculation:
            pue_score = (2.0 - 2.0) / 1.0 × 100 = 0.0
            it_score = 0.0 / 20.0 × 100 = 0.0
            space_score = 0.0 / 1666 × 100 = 0.0
            rag_score = 0.0 (RED)
            infra_score = 0.0 (utilization 2.0 > 1.0)

            composite = 0
        """
        result = score_scenario(
            pue=2.0,
            it_load_mw=0.0,
            max_it_load_mw=20.0,
            racks_deployed=0,
            effective_racks=1666,
            rag_status=RAGStatus.RED,
            ground_utilization_ratio=2.0,
            roof_utilization_ratio=1.5,
        )

        assert result.pue_score == 0.0
        assert result.it_capacity_score == 0.0
        assert result.space_utilization_score == 0.0
        assert result.rag_score == 0.0
        assert result.infrastructure_fit_score == 0.0
        assert result.composite_score == 0.0

    def test_typical_green_scenario(self):
        """Typical GREEN scenario: PUE=1.25, 15 MW of 20 MW max.

        Hand calculation:
            pue_score = (2.0 - 1.25) / 1.0 × 100 = 75.0
            it_score = (15.0 / 20.0) × 100 = 75.0
            space_score = (1200 / 1666) × 100 = 72.03
            rag_score = 75.0 (GREEN)
            infra_score = 100.0 (utilization 0.3 < 0.5)

            composite = 75×0.35 + 75×0.25 + 72.03×0.15 + 75×0.15 + 100×0.10
                      = 26.25 + 18.75 + 10.80 + 11.25 + 10.0 = 77.05
        """
        result = score_scenario(
            pue=1.25,
            it_load_mw=15.0,
            max_it_load_mw=20.0,
            racks_deployed=1200,
            effective_racks=1666,
            rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=0.3,
            roof_utilization_ratio=0.2,
        )

        assert result.pue_score == 75.0
        assert result.it_capacity_score == 75.0
        assert result.space_utilization_score == pytest.approx(72.03, abs=0.01)
        assert result.rag_score == 75.0
        assert result.infrastructure_fit_score == 100.0
        assert result.composite_score == pytest.approx(77.05, abs=0.01)


class TestPUEScoring:
    """Test PUE normalization across the range."""

    def test_pue_1_0(self):
        """PUE 1.0 → score 100 (theoretical perfect)."""
        result = score_scenario(
            pue=1.0, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.pue_score == 100.0

    def test_pue_1_5(self):
        """PUE 1.5 → score 50.0 (midpoint)."""
        result = score_scenario(
            pue=1.5, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.pue_score == 50.0

    def test_pue_2_0(self):
        """PUE 2.0 → score 0 (very poor)."""
        result = score_scenario(
            pue=2.0, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.pue_score == 0.0

    def test_pue_below_1_clamped(self):
        """PUE 0.9 → clamped to 100 (can't exceed 100)."""
        result = score_scenario(
            pue=0.9, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.pue_score == 100.0

    def test_pue_above_2_clamped(self):
        """PUE 2.5 → clamped to 0 (can't go negative)."""
        result = score_scenario(
            pue=2.5, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.pue_score == 0.0

    def test_pue_1_12(self):
        """PUE 1.12 → score 88.0 (typical DLC).

        (2.0 - 1.12) / 1.0 × 100 = 88.0
        """
        result = score_scenario(
            pue=1.12, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.pue_score == 88.0


class TestRAGScoring:
    """Test RAG status score mapping."""

    def test_blue(self):
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.BLUE,
        )
        assert result.rag_score == 100.0

    def test_green(self):
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
        )
        assert result.rag_score == 75.0

    def test_amber(self):
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.AMBER,
        )
        assert result.rag_score == 25.0

    def test_red(self):
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.RED,
        )
        assert result.rag_score == 0.0


class TestInfrastructureFitScoring:
    """Test infrastructure fit score based on utilization ratios."""

    def test_plenty_of_room(self):
        """Utilization 0.1 → score 100 (well under 0.5 threshold)."""
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=0.1, roof_utilization_ratio=0.1,
        )
        assert result.infrastructure_fit_score == 100.0

    def test_threshold_exactly_0_5(self):
        """Utilization exactly 0.5 → score 100 (boundary of 'plenty of room')."""
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=0.5, roof_utilization_ratio=0.3,
        )
        assert result.infrastructure_fit_score == 100.0

    def test_tight_at_0_75(self):
        """Utilization 0.75 → score 75.0.

        infra = 100.0 - (0.75 - 0.5) × 100 = 100 - 25 = 75.0
        """
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=0.75, roof_utilization_ratio=0.3,
        )
        assert result.infrastructure_fit_score == 75.0

    def test_barely_fits_at_1_0(self):
        """Utilization exactly 1.0 → score 50.0.

        infra = 100.0 - (1.0 - 0.5) × 100 = 100 - 50 = 50.0
        """
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=1.0, roof_utilization_ratio=0.3,
        )
        assert result.infrastructure_fit_score == 50.0

    def test_does_not_fit(self):
        """Utilization 1.5 → score 0 (doesn't fit)."""
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=1.5, roof_utilization_ratio=0.3,
        )
        assert result.infrastructure_fit_score == 0.0

    def test_roof_is_bottleneck(self):
        """When roof utilization is worse than ground, it dominates.

        ground=0.3, roof=0.9 → worst=0.9
        infra = 100.0 - (0.9 - 0.5) × 100 = 60.0
        """
        result = score_scenario(
            pue=1.2, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100, rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=0.3, roof_utilization_ratio=0.9,
        )
        assert result.infrastructure_fit_score == 60.0


class TestCustomWeights:
    """Test scoring with custom weights."""

    def test_pue_only_weights(self):
        """100% weight on PUE → composite = PUE score.

        PUE=1.25 → score = 75.0
        composite = 75.0 × 1.0 = 75.0
        """
        weights = {
            "pue_efficiency": 1.0,
            "it_capacity": 0.0,
            "space_utilization": 0.0,
            "rag_status": 0.0,
            "infrastructure_fit": 0.0,
        }
        result = score_scenario(
            pue=1.25, it_load_mw=5.0, max_it_load_mw=20.0,
            racks_deployed=100, effective_racks=1666,
            rag_status=RAGStatus.AMBER,
            weights=weights,
        )
        assert result.composite_score == 75.0

    def test_equal_weights(self):
        """Equal weights (0.20 each) with known scores.

        PUE=1.5 → 50.0, IT=10/20 → 50.0, Space=500/1000 → 50.0,
        RAG=GREEN → 75.0, Infra=util 0.1 → 100.0

        composite = (50 + 50 + 50 + 75 + 100) × 0.20 = 65.0
        """
        weights = {
            "pue_efficiency": 0.20,
            "it_capacity": 0.20,
            "space_utilization": 0.20,
            "rag_status": 0.20,
            "infrastructure_fit": 0.20,
        }
        result = score_scenario(
            pue=1.5, it_load_mw=10.0, max_it_load_mw=20.0,
            racks_deployed=500, effective_racks=1000,
            rag_status=RAGStatus.GREEN,
            ground_utilization_ratio=0.1, roof_utilization_ratio=0.1,
            weights=weights,
        )
        assert result.composite_score == 65.0


class TestScoreEdgeCases:
    """Edge cases for scoring."""

    def test_single_scenario_max_it_equals_it(self):
        """When evaluating a single scenario, max_it_load_mw = it_load_mw → 100."""
        result = score_scenario(
            pue=1.3, it_load_mw=15.0, max_it_load_mw=15.0,
            racks_deployed=1000, effective_racks=1666,
            rag_status=RAGStatus.GREEN,
        )
        assert result.it_capacity_score == 100.0

    def test_zero_max_it_load(self):
        """max_it_load_mw = 0 → IT capacity score = 0 (avoid division by zero)."""
        result = score_scenario(
            pue=1.3, it_load_mw=0.0, max_it_load_mw=0.0,
            racks_deployed=0, effective_racks=1666,
            rag_status=RAGStatus.GREEN,
        )
        assert result.it_capacity_score == 0.0

    def test_zero_effective_racks(self):
        """effective_racks = 0 → space score = 0 (avoid division by zero)."""
        result = score_scenario(
            pue=1.3, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=0, effective_racks=0,
            rag_status=RAGStatus.GREEN,
        )
        assert result.space_utilization_score == 0.0

    def test_default_utilization_ratios(self):
        """Default utilization ratios (0.0) → infra score = 100."""
        result = score_scenario(
            pue=1.3, it_load_mw=10.0, max_it_load_mw=10.0,
            racks_deployed=100, effective_racks=100,
            rag_status=RAGStatus.GREEN,
        )
        assert result.infrastructure_fit_score == 100.0


class TestWeightsConsistency:
    """Verify default weights are properly defined."""

    def test_default_weights_sum_to_1(self):
        """Weights must sum to exactly 1.0."""
        total = sum(DEFAULT_SCORING_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-10)

    def test_all_five_components_present(self):
        """All 5 scoring components must be in the weights dict."""
        expected_keys = {
            "pue_efficiency", "it_capacity", "space_utilization",
            "rag_status", "infrastructure_fit",
        }
        assert set(DEFAULT_SCORING_WEIGHTS.keys()) == expected_keys

    def test_all_rag_statuses_have_scores(self):
        """Every RAGStatus enum value must have a score mapping."""
        for status in RAGStatus:
            assert status in RAG_SCORES, f"Missing RAG score for {status}"


# ─────────────────────────────────────────────────────────────
# Load Mix Optimization Tests
# ─────────────────────────────────────────────────────────────

class TestLoadMixBasic:
    """Test load mix optimizer with known inputs."""

    def test_two_types_produces_candidates(self):
        """Two load types at 10% steps should produce valid candidates.

        HPC + Hyperscale with DLC cooling:
            HPC is compatible with DLC ✓
            Hyperscale is NOT compatible with DLC ✗
            So only HPC-dominant mixes will be fully compatible.
        """
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.DLC,
        )
        assert isinstance(result, LoadMixResult)
        assert result.total_it_mw == 20.0
        assert result.cooling_type == CoolingType.DLC.value
        assert result.step_pct == DEFAULT_STEP_PCT
        assert len(result.top_candidates) <= 5
        assert result.total_candidates_evaluated > 0

    def test_candidates_ranked_by_score(self):
        """Candidates must be sorted by score descending."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.AI_GPU],
            cooling_type=CoolingType.DLC,
        )
        if len(result.top_candidates) >= 2:
            for i in range(len(result.top_candidates) - 1):
                assert result.top_candidates[i].score >= result.top_candidates[i + 1].score

    def test_ranks_are_sequential(self):
        """Ranks must be 1, 2, 3, ..."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.AI_GPU],
            cooling_type=CoolingType.DLC,
        )
        for i, c in enumerate(result.top_candidates):
            assert c.rank == i + 1

    def test_allocations_sum_to_100_pct(self):
        """For every candidate, allocation shares must sum to 100%."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.AI_GPU, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
        )
        for c in result.top_candidates:
            total_pct = sum(a.share_pct for a in c.allocations)
            assert total_pct == pytest.approx(100.0, abs=0.01), (
                f"Candidate #{c.rank} shares sum to {total_pct}%"
            )

    def test_it_load_sum_matches_total(self):
        """IT load across allocations should approximately equal total_it_mw."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
        )
        for c in result.top_candidates:
            total_mw = sum(a.it_load_mw for a in c.allocations)
            assert total_mw == pytest.approx(20.0, abs=0.01)


class TestLoadMixMinRacks:
    """Test minimum viable allocation constraint."""

    def test_min_racks_filters_tiny_allocations(self):
        """Allocations that result in < min_racks are excluded.

        AI/GPU at typical density = 100 kW/rack.
        min_racks = 10 → min IT = 10 × 100 / 1000 = 1.0 MW.
        At 10% step with 5 MW total: 10% = 0.5 MW < 1.0 MW → excluded.
        """
        result = optimize_load_mix(
            total_it_mw=5.0,
            allowed_load_types=[LoadType.AI_GPU, LoadType.HYPERSCALE],
            cooling_type=CoolingType.DLC,
            min_racks=10,
        )
        for c in result.top_candidates:
            for a in c.allocations:
                density = a.rack_density_kw
                min_mw = 10 * density / 1000
                assert a.it_load_mw >= min_mw, (
                    f"Allocation {a.load_type}: {a.it_load_mw} MW < min {min_mw} MW"
                )

    def test_custom_min_racks(self):
        """Custom min_racks is applied correctly."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            min_racks=20,
        )
        assert result.min_racks == 20
        for c in result.top_candidates:
            for a in c.allocations:
                assert a.rack_count >= 20


class TestLoadMixCompatibility:
    """Test cooling compatibility in load mix results."""

    def test_compatible_mix_flagged_true(self):
        """HPC + AI with DLC — both compatible → all_compatible=True."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.AI_GPU],
            cooling_type=CoolingType.DLC,
        )
        # At least some candidates should be all-compatible
        compatible_candidates = [c for c in result.top_candidates if c.all_compatible]
        assert len(compatible_candidates) > 0

    def test_incompatible_mix_is_filtered_out(self):
        """Edge/Telco with DLC — incompatible mixes should not be returned."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.AI_GPU, LoadType.EDGE_TELCO],
            cooling_type=CoolingType.DLC,
        )

        for c in result.top_candidates:
            edge_allocs = [a for a in c.allocations if a.load_type == "Edge / Telco"]
            assert edge_allocs == []
            assert c.all_compatible is True

    def test_conditional_mix_gets_tradeoff_note_and_lower_rank(self):
        """Low-density AI on water-cooled chillers stays advisory, not top-ranked."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.AI_GPU, LoadType.HPC],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            density_scenario=DensityScenario.LOW,
            step_pct=50,
        )

        conditional_candidates = [
            c for c in result.top_candidates
            if any(a.load_type == "AI / GPU Clusters" for a in c.allocations)
        ]
        assert conditional_candidates
        assert any(
            "conditional" in note.lower()
            for c in conditional_candidates
            for note in c.trade_off_notes
        )

        fully_compatible_scores = [
            c.score
            for c in result.top_candidates
            if all(a.load_type != "AI / GPU Clusters" for a in c.allocations)
        ]
        assert fully_compatible_scores
        assert max(c.score for c in conditional_candidates) < max(fully_compatible_scores)

    def test_ai_immersion_mix_is_not_penalized_as_conditional(self):
        """AI-only immersion candidates should stay compatible at typical density."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.AI_GPU, LoadType.HPC],
            cooling_type=CoolingType.IMMERSION,
            density_scenario=DensityScenario.TYPICAL,
            step_pct=50,
        )

        ai_only = next(
            c for c in result.top_candidates
            if len(c.allocations) == 1 and c.allocations[0].load_type == LoadType.AI_GPU.value
        )
        hpc_only = next(
            c for c in result.top_candidates
            if len(c.allocations) == 1 and c.allocations[0].load_type == LoadType.HPC.value
        )

        assert all("conditional" not in note.lower() for note in ai_only.trade_off_notes)
        assert any("conditional" in note.lower() for note in hpc_only.trade_off_notes)
        assert ai_only.score > hpc_only.score

    def test_colocation_high_density_dlc_mix_stays_advisory(self):
        """High-density colo on DLC should carry a trade-off note and rank below pure HPC."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.COLOCATION_HIGH_DENSITY, LoadType.HPC],
            cooling_type=CoolingType.DLC,
            density_scenario=DensityScenario.TYPICAL,
            step_pct=50,
        )

        colo_candidates = [
            c for c in result.top_candidates
            if any(a.load_type == LoadType.COLOCATION_HIGH_DENSITY.value for a in c.allocations)
        ]
        assert colo_candidates
        assert any(
            "conditional" in note.lower()
            for c in colo_candidates
            for note in c.trade_off_notes
        )

        hpc_only = next(
            c for c in result.top_candidates
            if len(c.allocations) == 1 and c.allocations[0].load_type == LoadType.HPC.value
        )
        assert max(c.score for c in colo_candidates) < hpc_only.score


class TestLoadMixStepSize:
    """Test different step sizes."""

    def test_step_10_produces_fewer_than_step_5(self):
        """Step 5% generates more combinations than step 10%."""
        result_10 = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            step_pct=10,
        )
        result_5 = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            step_pct=5,
        )
        assert result_5.total_candidates_evaluated >= result_10.total_candidates_evaluated


class TestLoadMixEdgeCases:
    """Edge cases for load mix optimizer."""

    def test_negative_it_raises(self):
        """Negative total IT should raise ValueError."""
        with pytest.raises(ValueError, match="total_it_mw must be positive"):
            optimize_load_mix(
                total_it_mw=-5.0,
                allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
                cooling_type=CoolingType.DLC,
            )

    def test_zero_it_raises(self):
        """Zero total IT should raise ValueError."""
        with pytest.raises(ValueError, match="total_it_mw must be positive"):
            optimize_load_mix(
                total_it_mw=0.0,
                allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
                cooling_type=CoolingType.DLC,
            )

    def test_single_type_raises(self):
        """Single load type = no optimization needed → ValueError."""
        with pytest.raises(ValueError, match="at least 2 load types"):
            optimize_load_mix(
                total_it_mw=20.0,
                allowed_load_types=[LoadType.HPC],
                cooling_type=CoolingType.DLC,
            )

    def test_invalid_step_pct_raises(self):
        """Step size outside 1–50 range should raise ValueError."""
        with pytest.raises(ValueError, match="step_pct must be 1–50"):
            optimize_load_mix(
                total_it_mw=20.0,
                allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
                cooling_type=CoolingType.DLC,
                step_pct=0,
            )

    def test_top_n_respected(self):
        """Only top_n candidates returned."""
        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            top_n=3,
        )
        assert len(result.top_candidates) <= 3

    def test_three_types_works(self):
        """Three load types produces valid multi-way allocations."""
        result = optimize_load_mix(
            total_it_mw=30.0,
            allowed_load_types=[LoadType.HPC, LoadType.AI_GPU, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            step_pct=10,
        )
        assert result.total_candidates_evaluated > 0
        # Some candidates should have 2 or 3 active allocations
        multi_alloc = [c for c in result.top_candidates if len(c.allocations) >= 2]
        assert len(multi_alloc) > 0


class TestLoadMixRackCounts:
    """Verify rack count calculations in load mix."""

    def test_rack_count_formula(self):
        """rack_count = int(it_load_mw × 1000 / rack_density_kw).

        HPC typical = 40 kW/rack.
        10 MW → 10,000 / 40 = 250 racks.
        """
        result = optimize_load_mix(
            total_it_mw=10.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            step_pct=50,  # Only 50/50 and 100/0 combos
        )
        for c in result.top_candidates:
            for a in c.allocations:
                expected_racks = int(a.it_load_mw * 1000 / a.rack_density_kw)
                assert a.rack_count == expected_racks, (
                    f"{a.load_type}: got {a.rack_count}, expected {expected_racks}"
                )


class TestBlendedPUE:
    """Verify blended PUE calculation."""

    def test_single_dominant_type_pue(self):
        """100% of one type → blended PUE = cooling profile typical.

        Water Chiller + Econ typical PUE = 1.28
        """
        expected_pue = COOLING_PROFILES["Water-Cooled Chiller + Economizer"]["pue_typical"]

        result = optimize_load_mix(
            total_it_mw=20.0,
            allowed_load_types=[LoadType.HPC, LoadType.HYPERSCALE],
            cooling_type=CoolingType.WATER_CHILLER_ECON,
            step_pct=50,
        )
        # All candidates use the same cooling type → same PUE
        for c in result.top_candidates:
            assert c.blended_pue == pytest.approx(expected_pue, abs=0.001)
