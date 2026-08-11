"""
Unit + integration tests for the scoring model.
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
from app.scoring.scoring_model import SCALE_DISPLAY_NAMES, score_assessment, SCALE_WEIGHTS, COGNITIVE_AGE_MIN_AGE
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
# 1. Single-model guard — there is one scoring model and `domains` is it.
# ===========================================================================

SCALE_KEYS = {
    "attentionFocus", "memoryRecall", "executiveFunction", "mentalEnergy",
    "stressLoad", "sleepRecovery", "lifestyleModule",
}

# The eight-domain vocabulary that used to live in `domains`, four of which
# were derived rather than measured. None of it may come back.
RETIRED_DOMAIN_KEYS = {
    "memory", "processingSpeed", "mentalClarity",
    "languageSkills", "problemSolving", "reactionTime",
}


class TestSingleModel:
    def test_domains_holds_exactly_the_seven_scales(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        assert r.status_code == 200
        domains = r.json()["domains"]

        assert set(domains) == SCALE_KEYS
        assert not set(domains) & RETIRED_DOMAIN_KEYS

    def test_every_domain_entry_carries_its_confidence_interval(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        for key, entry in r.json()["domains"].items():
            assert set(entry) == {"score", "sem", "ciLow", "ciHigh"}, key

    def test_no_model_version_field_is_advertised(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        body = r.json()
        assert "modelVersion" not in body
        assert "scales" not in body
        assert "cognitiveAgeV2" not in body

    def test_scoring_features_are_always_present(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        body = r.json()
        for key in ("composites", "validity", "percentile", "cognitiveAge"):
            assert body[key] is not None, key

    def test_radar_chart_uses_the_seven_scale_labels(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        radar = r.json()["charts"]["radarDomains"]
        assert len(radar["labels"]) == 7
        assert "Reaction Time" not in radar["labels"]
        assert "Sleep & Recovery" in radar["labels"]


# ===========================================================================
# 2. Seven scales, no proxies
# ===========================================================================

class TestSevenScales:
    @pytest.mark.parametrize("fixture", [FIXTURE_PERFECT, FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_BURNOUT])
    def test_exactly_seven_scales_all_in_range(self, fixture):
        result = score_assessment(age=50, gender="female", responses=fixture)
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
        result = score_assessment(age=50, gender="female", responses=fixture)
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
        result = score_assessment(age=45, gender="male", responses=fixture)
        for v in vars(result.scales).values():
            assert 0 <= v.ciLow <= v.score <= v.ciHigh <= 100
        for v in vars(result.composites).values():
            assert 0 <= v.ciLow <= v.score <= v.ciHigh <= 100


# ===========================================================================
# 5. Cognitive age — None below 43, integer + range at 43+
# ===========================================================================

class TestCognitiveAge:
    def test_none_below_min_age(self):
        result = score_assessment(age=COGNITIVE_AGE_MIN_AGE - 1, gender="male", responses=FIXTURE_MODERATE)
        assert result.cognitive_age.estimatedCognitiveAge is None
        assert result.cognitive_age.ageLow is None
        assert result.cognitive_age.ageHigh is None

    def test_integer_with_range_at_min_age_and_above(self):
        result = score_assessment(age=COGNITIVE_AGE_MIN_AGE, gender="male", responses=FIXTURE_MODERATE)
        cog = result.cognitive_age
        assert isinstance(cog.estimatedCognitiveAge, int)
        assert isinstance(cog.ageLow, int) and isinstance(cog.ageHigh, int)
        assert cog.ageLow <= cog.estimatedCognitiveAge <= cog.ageHigh
        assert cog.provisional is True
        assert cog.disclaimer

    def test_clamped_to_18_80(self):
        result = score_assessment(age=66, gender="male", responses=FIXTURE_WORST)
        assert 18 <= result.cognitive_age.estimatedCognitiveAge <= 80


# ===========================================================================
# 6. Percentile stays within 1-99
# ===========================================================================

class TestPercentile:
    @pytest.mark.parametrize("age,fixture", [
        (66, FIXTURE_PERFECT), (18, FIXTURE_WORST), (50, FIXTURE_MODERATE),
    ])
    def test_percentile_within_1_99(self, age, fixture):
        result = score_assessment(age=age, gender="male", responses=fixture)
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
        monkeypatch.setattr(settings, "ENABLE_RELIABLE_CHANGE", True)

        r1 = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST))
        prior = r1.json()
        r2 = client.post(ANALYZE_URL, json=_payload(FIXTURE_PERFECT, prior=prior))
        body = r2.json()

        assert body["reliableChange"] is not None
        assert body["reliableChange"]["overall"]["flag"] == "Reliable improvement"

    def test_analyze_route_reliable_change_suppressed_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_RELIABLE_CHANGE", False)

        r1 = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST))
        prior = r1.json()
        r2 = client.post(ANALYZE_URL, json=_payload(FIXTURE_PERFECT, prior=prior))
        body = r2.json()

        assert body["reliableChange"] is None


# ===========================================================================
# 8. PDF generation — every flag on / every flag off
# ===========================================================================

class TestPDFGeneration:
    def test_pdf_generates_with_every_flag_on(self, monkeypatch):
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

        pdf = client.post(PDF_URL, json={"analysis": analysis})
        assert pdf.status_code == 200
        assert len(pdf.content) > 0

    def test_teaser_pdf_uses_seven_scales(self, monkeypatch):

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

    def test_full_report_narrative_uses_scales(self, monkeypatch):
        """Every narrative generator must speak the v2 vocabulary, not the
        legacy 8 domains (3 of which were fabricated)."""

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

    def test_pdf_generates_with_every_flag_off(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_CONFIDENCE_INTERVALS", False)
        monkeypatch.setattr(settings, "ENABLE_VALIDITY_CHECKS", False)
        monkeypatch.setattr(settings, "ENABLE_RELIABLE_CHANGE", False)
        monkeypatch.setattr(settings, "ENABLE_METHODOLOGY_PAGE", False)

        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_MODERATE))
        assert r.status_code == 200
        analysis = r.json()

        pdf = client.post(PDF_URL, json={"analysis": analysis})
        assert pdf.status_code == 200
        assert len(pdf.content) > 0


# ===========================================================================
# 9. Zero-score guard
# ===========================================================================

class TestZeroScoreRendering:
    """A floor score used to divide by zero inside ReportLab's bezierArc.

    Both gauges draw an arc whose extent is proportional to the score, so a
    0 produces a zero-extent arc. Guarded in _draw_score_gauge and the
    cognitive-age ring; these pin it for both documents.
    """

    def test_zero_overall_score_is_reachable(self):
        r = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST, age=60))
        assert r.json()["overall"]["score"] == 0.0

    @pytest.mark.parametrize("url", [PDF_URL, "/api/v1/generate-teaser-pdf"])
    def test_zero_score_renders_without_crashing(self, url):
        analysis = client.post(ANALYZE_URL, json=_payload(FIXTURE_WORST, age=60)).json()
        pdf = client.post(url, json={"analysis": analysis})
        assert pdf.status_code == 200
        assert len(pdf.content) > 1000


class TestProgressPageLabels:
    def test_progress_rows_use_scale_display_names(self):
        """Delta rows are keyed by scale, so they must resolve through the
        scale display names — not the retired domain labels, which would
        leave most rows showing a raw camelCase key."""
        from app.services.report_mapper import transform_analysis_to_report

        base = _payload(FIXTURE_WORST, age=47)
        prior = client.post(ANALYZE_URL, json=base).json()
        current = client.post(
            ANALYZE_URL, json=_payload(FIXTURE_PERFECT, age=47, prior=prior)
        ).json()

        rows = transform_analysis_to_report(current)["progress_table"]["domain_rows"]
        labels = [r["domain"] for r in rows]

        assert labels, "expected delta rows"
        for label in labels:
            assert label in SCALE_DISPLAY_NAMES.values(), label
            assert " " in label, f"raw key leaked through: {label}"
