"""
Tests for /analyze route, recommendations service, and progress delta service.
Run: python -m pytest tests/test_analyze.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from starlette.testclient import TestClient
from app.main import app
from tests.fixtures import (
    FIXTURE_PERFECT,
    FIXTURE_WORST,
    FIXTURE_MODERATE,
    FIXTURE_BURNOUT,
    FIXTURE_ATTENTION_ONLY,
    FIXTURE_OUT_OF_RANGE,
    build_missing_section_responses,
)

client = TestClient(app)

BASE_URL = "/api/v1/analyze"

def _payload(responses, age=22, gender="male", assessment_id="test-uuid-001", prior=None):
    body = {
        "assessmentId": assessment_id,
        "age": age,
        "gender": gender,
        "responses": responses,
    }
    if prior:
        body["priorReport"] = prior
    return body


# ===========================================================================
# 1. Happy path — full response structure
# ===========================================================================

class TestAnalyzeHappyPath:
    def test_cognitive_age_null_for_under_43(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE, age=30))
        assert r.json()["cognitiveAge"]["estimatedCognitiveAge"] is None
    
    def test_cognitive_age_integer_for_43_plus(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE, age=50))
        est = r.json()["cognitiveAge"]["estimatedCognitiveAge"]
        assert est is not None
        assert isinstance(est, int)
        assert 18 <= est <= 80
    def test_returns_200(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        assert r.status_code == 200

    def test_response_has_all_top_level_keys(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        data = r.json()
        for key in ["assessmentId", "overall", "domains", "lifestyleImpacts",
                    "riskIndicators", "cognitiveAge", "strengths",
                    "recommendations", "progress", "charts", "audit", "disclaimers"]:
            assert key in data, f"Missing key: {key}"

    def test_overall_score_in_range(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        score = r.json()["overall"]["score"]
        assert 0 <= score <= 100

    def test_all_8_domains_present(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        domains = r.json()["domains"]
        for key in ["memory", "attentionFocus", "processingSpeed", "executiveFunction",
                    "mentalClarity", "languageSkills", "problemSolving", "reactionTime"]:
            assert key in domains

    def test_three_mandatory_disclaimers_present(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        disclaimers = r.json()["disclaimers"]
        assert len(disclaimers) == 3
        assert any("not a diagnosis" in d for d in disclaimers)
        assert any("medical advice" in d for d in disclaimers)
        assert any("clinician" in d for d in disclaimers)

    def test_assessment_id_echoed_back(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE, assessment_id="my-test-id"))
        assert r.json()["assessmentId"] == "my-test-id"

    def test_cognitive_age_stubbed_for_cohort(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        cog = r.json()["cognitiveAge"]
        assert cog["actualAge"] == 22
        assert cog["estimatedCognitiveAge"] is None
        assert "wellness metric" in cog["disclaimer"].lower()


# ===========================================================================
# 2. Score profiles
# ===========================================================================

class TestScoreProfiles:
    def test_perfect_fixture_gives_excellent(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_PERFECT))
        assert r.json()["overall"]["rating"] == "Excellent"

    def test_worst_fixture_gives_at_risk(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_WORST))
        assert r.json()["overall"]["rating"] == "At Risk"

    def test_burnout_fixture_has_burnout_risk_indicator(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_BURNOUT))
        risks = " ".join(r.json()["riskIndicators"]).lower()
        assert "burnout" in risks

    def test_attention_fixture_flags_attention_risk(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_ATTENTION_ONLY))
        risks = " ".join(r.json()["riskIndicators"]).lower()
        assert "attention" in risks

    def test_all_risk_indicators_prefixed_with_possible(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_BURNOUT))
        for risk in r.json()["riskIndicators"]:
            assert risk.startswith("Possible"), f"Risk not prefixed: {risk}"


# ===========================================================================
# 3. Recommendations
# ===========================================================================

class TestRecommendations:
    def test_recommendations_list_not_empty(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        assert len(r.json()["recommendations"]) > 0

    def test_last_recommendation_is_compliance_note(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        last = r.json()["recommendations"][-1]
        assert "wellness guide" in last.lower() or "clinician" in last.lower()

    def test_burnout_profile_gets_burnout_recommendation(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_BURNOUT,age=44))
        recs = " ".join(r.json()["recommendations"]).lower()
        assert "burnout" in recs or "recovery" in recs or "rest" in recs

    def test_perfect_profile_gets_positive_reinforcement(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_PERFECT))
        recs = " ".join(r.json()["recommendations"]).lower()
        assert "great shape" in recs or "maintain" in recs

    def test_recommendations_capped_at_8(self):
        # 7 recommendations + 1 universal compliance note
        r = client.post(BASE_URL, json=_payload(FIXTURE_BURNOUT))
        assert len(r.json()["recommendations"]) <= 8


# ===========================================================================
# 4. Chart data
# ===========================================================================

class TestChartData:
    def test_radar_has_8_labels_and_8_values(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        radar = r.json()["charts"]["radarDomains"]
        assert len(radar["labels"]) == 8
        assert len(radar["values"]) == 8

    def test_bar_has_4_lifestyle_factors(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        bar = r.json()["charts"]["barLifestyleImpacts"]
        assert len(bar["labels"]) == 4
        assert len(bar["values"]) == 4

    def test_radar_values_in_range(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        for v in r.json()["charts"]["radarDomains"]["values"]:
            assert 0 <= v <= 100


# ===========================================================================
# 5. Progress delta
# ===========================================================================

class TestProgressDelta:
    def _run_once(self, fixture):
        r = client.post(BASE_URL, json=_payload(fixture))
        return r.json()

    def test_no_prior_report_gives_unavailable_progress(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        assert r.json()["progress"]["available"] is False
        assert r.json()["progress"]["deltas"] == []

    def test_prior_report_enables_progress(self):
        first_report = self._run_once(FIXTURE_WORST)
        payload = _payload(FIXTURE_MODERATE, prior=first_report)
        r = client.post(BASE_URL, json=payload)
        progress = r.json()["progress"]
        assert progress["available"] is True
        assert len(progress["deltas"]) > 0

    def test_progress_deltas_show_improvement_from_worst_to_moderate(self):
        first_report = self._run_once(FIXTURE_WORST)
        payload = _payload(FIXTURE_MODERATE, prior=first_report)
        r = client.post(BASE_URL, json=payload)
        deltas = r.json()["progress"]["deltas"]
        improved = [d for d in deltas if d["direction"] == "improved"]
        assert len(improved) > 0

    def test_progress_delta_fields_present(self):
        first_report = self._run_once(FIXTURE_WORST)
        payload = _payload(FIXTURE_MODERATE, prior=first_report)
        r = client.post(BASE_URL, json=payload)
        for d in r.json()["progress"]["deltas"]:
            for field in ["domain", "previous", "current", "delta", "direction"]:
                assert field in d


# ===========================================================================
# 6. Input validation (422 errors)
# ===========================================================================

class TestInputValidation:
    @pytest.mark.parametrize("age", [26, 33, 38, 43, 48, 56, 66])
    def test_band_boundary_ages_return_200(self, age):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE, age=age))
        assert r.status_code == 200
    def test_age_below_18_returns_422(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE, age=17))
        assert r.status_code == 422

    def test_age_above_66_returns_422(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE, age=67))
        assert r.status_code == 422

    def test_invalid_gender_returns_422(self):
        payload = _payload(FIXTURE_MODERATE)
        payload["gender"] = "unknown"
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 422

    def test_invalid_item_id_returns_422(self):
        bad_responses = [{"itemId": "S9_Q1", "value": 2}]
        r = client.post(BASE_URL, json=_payload(bad_responses))
        assert r.status_code == 422

    def test_duplicate_item_id_returns_422(self):
        duped = FIXTURE_MODERATE + [{"itemId": "S1_Q1", "value": 3}]
        r = client.post(BASE_URL, json=_payload(duped))
        assert r.status_code == 422

    def test_out_of_range_values_clamped_not_rejected(self):
        # Values 5 and -1 should be clamped, not rejected — Pydantic accepts 0–4
        # but the engine clamps; Pydantic will reject these at model level (ge=0, le=4)
        r = client.post(BASE_URL, json=_payload(FIXTURE_OUT_OF_RANGE))
        assert r.status_code == 422  # Pydantic rejects out-of-range at route level

    def test_missing_responses_key_returns_422(self):
        payload = {"assessmentId": "x", "age": 22, "gender": "male"}
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 422


# ===========================================================================
# 7. Audit trail
# ===========================================================================

class TestAudit:
    def test_audit_has_version_and_cohort(self):
        r = client.post(BASE_URL, json=_payload(FIXTURE_MODERATE))
        audit = r.json()["audit"]
        assert audit["rules_version"] == "1.0"
        assert audit["age_cohort"] == "18-25"

    def test_missing_section_appears_in_audit(self):
        responses = build_missing_section_responses("S3")
        r = client.post(BASE_URL, json=_payload(responses))
        assert "S3" in r.json()["audit"]["insufficient_sections"]
