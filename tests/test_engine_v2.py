"""
Unit + integration tests for the v2 scoring engine (Phase 6).
Run: python -m pytest tests/test_engine_v2.py -v

Does not modify any existing test file. Response-validity-specific tests
live in tests/test_validity.py.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.scoring.engine import score as run_scoring_v1
from app.scoring.engine_v2 import score_v2, SCALE_WEIGHTS, COGNITIVE_AGE_MIN_AGE
from app.services.rci import compute_rci, RCI_THRESHOLD
from tests.fixtures import (
    FIXTURE_PERFECT,
    FIXTURE_WORST,
    FIXTURE_MODERATE,
    FIXTURE_BURNOUT,
)

client = TestClient(app)

ANALYZE_URL = "/api/v1/analyze"
PDF_URL     = "/api/v1/generate-pdf"


def _payload(responses, age=50, gender="female", assessment_id="v2-test", elapsed=None, prior=None):
    body = {"assessmentId": assessment_id, "age": age, "gender": gender, "responses": responses}
    if elapsed is not None:
        body["elapsedSeconds"] = elapsed
    if prior is not None:
        body["priorReport"] = prior
    return body


# ===========================================================================
# 1. v1 regression guard — default config must produce v1-shaped output,
#    identical to a direct call of the untouched v1 engine.
# ===========================================================================

class TestV1RegressionGuard:
    def test_default_scoring_model_version_is_v1(self):
        assert settings.SCORING_MODEL_VERSION == "v1"

    def test_v1_route_output_unaffected_by_v2_fields(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        assert r.status_code == 200
        body = r.json()

        assert body["modelVersion"] == "v1"
        assert body["scales"] is None
        assert body["composites"] is None
        assert body["validity"] is None
        assert body["percentile"] is None
        assert body["cognitiveAgeV2"] is None
        assert body["reliableChange"] is None
        assert body["retestIntervalWarning"] is False

    def test_v1_route_output_matches_direct_engine_call(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_BURNOUT, age=45, gender="male"))
        body = r.json()

        direct = run_scoring_v1(age=45, gender="male", responses=FIXTURE_BURNOUT)
        assert body["overall"]["score"] == direct.overall_score
        assert body["overall"]["rating"] == direct.rating
        assert body["domains"]["reactionTime"] == direct.domain_scores.reaction_time


# ===========================================================================
# 2. Seven scales, no proxies
# ===========================================================================

class TestSevenScales:
    @pytest.mark.parametrize("fixture", [FIXTURE_PERFECT, FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_BURNOUT])
    def test_exactly_seven_scales_all_in_range(self, fixture):
        result = score_v2(age=50, gender="female", responses=fixture)
        scale_dict = vars(result.scales)
        assert len(scale_dict) == 7
        for v in scale_dict.values():
            assert 0 <= v.score <= 100

    def test_weights_sum_to_one(self):
        assert sum(SCALE_WEIGHTS.values()) == pytest.approx(1.0)


# ===========================================================================
# 3. Composites equal the mean of their constituent scales
# ===========================================================================

class TestComposites:
    @pytest.mark.parametrize("fixture", [FIXTURE_MODERATE, FIXTURE_BURNOUT])
    def test_composites_equal_mean_of_constituent_scales(self, fixture):
        result = score_v2(age=50, gender="female", responses=fixture)
        s = vars(result.scales)
        c = vars(result.composites)

        expected_cci = round(
            (s["attentionFocus"].score + s["memoryRecall"].score + s["executiveFunction"].score) / 3, 1
        )
        expected_mli = round(
            (s["mentalEnergy"].score + s["stressLoad"].score + s["sleepRecovery"].score) / 3, 1
        )
        assert c["cognitiveComplaintIndex"].score == expected_cci
        assert c["modifiableLoadIndex"].score == expected_mli


# ===========================================================================
# 4. Confidence intervals — ordered and clamped
# ===========================================================================

class TestConfidenceIntervals:
    @pytest.mark.parametrize("fixture", [FIXTURE_PERFECT, FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_BURNOUT])
    def test_ci_ordered_and_clamped(self, fixture):
        result = score_v2(age=45, gender="male", responses=fixture)
        for v in vars(result.scales).values():
            assert 0 <= v.ciLow <= v.score <= v.ciHigh <= 100
        for v in vars(result.composites).values():
            assert 0 <= v.ciLow <= v.score <= v.ciHigh <= 100


# ===========================================================================
# 5. Cognitive age — None below 43, integer + range at 43+
# ===========================================================================

class TestCognitiveAgeV2:
    def test_none_below_min_age(self):
        result = score_v2(age=COGNITIVE_AGE_MIN_AGE - 1, gender="male", responses=FIXTURE_MODERATE)
        assert result.cognitive_age.estimatedCognitiveAge is None
        assert result.cognitive_age.ageLow is None
        assert result.cognitive_age.ageHigh is None

    def test_integer_with_range_at_min_age_and_above(self):
        result = score_v2(age=COGNITIVE_AGE_MIN_AGE, gender="male", responses=FIXTURE_MODERATE)
        cog = result.cognitive_age
        assert isinstance(cog.estimatedCognitiveAge, int)
        assert isinstance(cog.ageLow, int) and isinstance(cog.ageHigh, int)
        assert cog.ageLow <= cog.estimatedCognitiveAge <= cog.ageHigh
        assert cog.provisional is True
        assert cog.disclaimer

    def test_clamped_to_18_80(self):
        result = score_v2(age=66, gender="male", responses=FIXTURE_WORST)
        assert 18 <= result.cognitive_age.estimatedCognitiveAge <= 80


# ===========================================================================
# 6. Percentile stays within 1-99
# ===========================================================================

class TestPercentileV2:
    @pytest.mark.parametrize("age,fixture", [
        (66, FIXTURE_PERFECT), (18, FIXTURE_WORST), (50, FIXTURE_MODERATE),
    ])
    def test_percentile_within_1_99(self, age, fixture):
        result = score_v2(age=age, gender="male", responses=fixture)
        assert 1 <= result.percentile.value <= 99
        assert result.percentile.provisional is True


# ===========================================================================
# 7. Reliable Change Index — flags reliable change only above threshold
# ===========================================================================

class TestReliableChangeIndex:
    def test_small_delta_is_within_normal_variation(self):
        out = compute_rci(current=52, previous=50, sem=9.0)
        assert abs(out["rci"]) < RCI_THRESHOLD
        assert out["flag"] == "Within normal variation"

    def test_large_positive_delta_is_reliable_improvement(self):
        out = compute_rci(current=80, previous=50, sem=9.0)
        assert out["rci"] >= RCI_THRESHOLD
        assert out["flag"] == "Reliable improvement"

    def test_large_negative_delta_is_reliable_decline(self):
        out = compute_rci(current=50, previous=80, sem=9.0)
        assert out["rci"] <= -RCI_THRESHOLD
        assert out["flag"] == "Reliable decline"

    def test_analyze_route_reliable_change_end_to_end(self, monkeypatch):
        monkeypatch.setattr(settings, "SCORING_MODEL_VERSION", "v2")
        monkeypatch.setattr(settings, "ENABLE_RELIABLE_CHANGE", True)

        r1 = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST))
        prior = r1.json()
        r2 = client.post(ANALYZE_URL, json=_payload(FIXTURE_PERFECT, prior=prior))
        body = r2.json()

        assert body["reliableChange"] is not None
        assert body["reliableChange"]["overall"]["flag"] == "Reliable improvement"

    def test_analyze_route_reliable_change_off_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "SCORING_MODEL_VERSION", "v2")
        # ENABLE_RELIABLE_CHANGE left at its default (False)

        r1 = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST))
        prior = r1.json()
        r2 = client.post(ANALYZE_URL, json=_payload(FIXTURE_PERFECT, prior=prior))
        body = r2.json()

        assert body["reliableChange"] is None


# ===========================================================================
# 8. PDF generation — v2 active, every flag on / every flag off
# ===========================================================================

class TestPDFGenerationV2:
    def test_pdf_generates_with_v2_and_every_flag_on(self, monkeypatch):
        monkeypatch.setattr(settings, "SCORING_MODEL_VERSION", "v2")
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_INTERVALS", True)
        monkeypatch.setattr(settings, "ENABLE_VALIDITY_CHECKS", True)
        monkeypatch.setattr(settings, "ENABLE_RELIABLE_CHANGE", True)
        monkeypatch.setattr(settings, "ENABLE_METHODOLOGY_PAGE", True)

        r1 = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST, elapsed=300))
        assert r1.status_code == 200
        prior = r1.json()

        r2 = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, elapsed=300, prior=prior))
        assert r2.status_code == 200
        analysis = r2.json()
        assert analysis["modelVersion"] == "v2"

        pdf = client.post(PDF_URL, json={"analysis": analysis})
        assert pdf.status_code == 200
        assert len(pdf.content) > 0

    def test_teaser_pdf_uses_seven_v2_scales(self, monkeypatch):
        monkeypatch.setattr(settings, "SCORING_MODEL_VERSION", "v2")

        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE))
        analysis = r.json()

        # report_mapper computes; assert on the computed teaser inputs
        from app.services.report_mapper import transform_analysis_to_report
        data = transform_analysis_to_report(analysis)

        assert len(data["radar_domains"]) == 7
        assert "Attention & Focus" in data["radar_domains"]
        # the three fabricated v1 domains must not reach the v2 teaser
        for dropped in ("Reaction Time", "Language", "Problem Solving"):
            assert dropped not in data["radar_domains"]

        pdf = client.post("/api/v1/generate-teaser-pdf", json={"analysis": analysis})
        assert pdf.status_code == 200
        assert len(pdf.content) > 0

    def test_full_report_narrative_migrated_to_v2_scales(self, monkeypatch):
        """Every narrative generator must speak the v2 vocabulary, not the
        legacy 8 domains (3 of which were fabricated)."""
        monkeypatch.setattr(settings, "SCORING_MODEL_VERSION", "v2")

        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE))
        from app.services.report_mapper import transform_analysis_to_report
        data = transform_analysis_to_report(r.json())

        scale_names = set(data["radar_domains"])
        assert len(scale_names) == 7

        # score breakdown: v2 scales, weights still total 100%
        assert {row["domain"] for row in data["score_breakdown"]} == scale_names
        assert sum(row["weight_pct"] for row in data["score_breakdown"]) == 100

        # traffic light, strengths, priority areas all drawn from v2 scales
        tl = data["traffic_light"]
        assert {i["domain"] for g in tl.values() for i in g} == scale_names
        assert {s["title"] for s in data["strengths"]} <= scale_names
        assert set(data["executive_summary"]["priority_areas"]) <= scale_names

        # projections / risk predictions reference v2 scales only
        assert set(data["ai_insights"]["improvement_projection"]) <= scale_names
        rp = data["risk_prediction"]
        for row in rp["no_action"]["domain_declines"] + rp["with_action"]["domain_gains"]:
            assert row["domain"] in scale_names

        # none of the dropped/fabricated v1 domains survive anywhere
        for dropped in ("Reaction Time", "Problem Solving", "Language", "Processing"):
            assert dropped not in scale_names

    def test_teaser_pdf_unchanged_under_v1(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=22, gender="male"))
        analysis = r.json()
        assert analysis["modelVersion"] == "v1"

        from app.services.report_mapper import transform_analysis_to_report
        data = transform_analysis_to_report(analysis)

        # v1 still drives the teaser off the legacy 8 domains
        assert data["radar_domains"] == data["domains"]
        assert len(data["radar_domains"]) == 8
        # legacy vocabulary intact — the fabricated domains still appear under v1
        assert "Reaction Time" in data["radar_domains"]
        assert {row["domain"] for row in data["score_breakdown"]} == set(data["domains"])

        pdf = client.post("/api/v1/generate-teaser-pdf", json={"analysis": analysis})
        assert pdf.status_code == 200

    def test_benchmarks_expose_both_cohort_averages(self):
        """The report compares against both cohorts rather than picking one
        by the user's gender; percentile stays cohort-based."""
        from app.services.report_mapper import generate_benchmarks, BENCHMARKS
        from app.scoring.engine import get_age_band

        for gender in ("female", "male", "other", "prefer-not-to-say"):
            bm = generate_benchmarks(45, gender, 61)
            band = get_age_band(45)
            assert bm["peer_average_female"] == BENCHMARKS[band]["female"][0]
            assert bm["peer_average_male"] == BENCHMARKS[band]["male"][0]
            assert 5 <= bm["percentile"] <= 99

    def test_non_binary_benchmarks_use_mean_not_female(self):
        """Regression guard: 'other'/'prefer-not-to-say' previously fell into
        an unreachable branch and were silently scored against female
        benchmarks. They must now use the mean of both cohorts."""
        from app.services.report_mapper import generate_benchmarks

        female = generate_benchmarks(45, "female", 61)
        male   = generate_benchmarks(45, "male", 61)
        for gender in ("other", "prefer-not-to-say"):
            neutral = generate_benchmarks(45, gender, 61)
            expected = int((female["peer_average"] + male["peer_average"]) / 2)
            assert neutral["peer_average"] == expected
            assert neutral["peer_average"] != female["peer_average"]
            assert neutral["cohort_label"] == "All genders"

    def test_pdf_generates_with_v2_and_every_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "SCORING_MODEL_VERSION", "v2")
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_INTERVALS", False)
        monkeypatch.setattr(settings, "ENABLE_VALIDITY_CHECKS", False)
        monkeypatch.setattr(settings, "ENABLE_RELIABLE_CHANGE", False)
        monkeypatch.setattr(settings, "ENABLE_METHODOLOGY_PAGE", False)

        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE))
        assert r.status_code == 200
        analysis = r.json()
        assert analysis["modelVersion"] == "v2"

        pdf = client.post(PDF_URL, json={"analysis": analysis})
        assert pdf.status_code == 200
        assert len(pdf.content) > 0
