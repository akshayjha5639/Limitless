"""
Tests for the Longitudinal Cognitive Tracking Engine (PRD v1.0.0)
and POST /api/v1/longitudinal-analysis.
Run: python -m pytest tests/test_longitudinal.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from starlette.testclient import TestClient
from app.main import app
from app.services.longitudinal_engine import (
    normalize_session,
    normalize_history,
    compute_attribution_matrix,
    run_longitudinal_analysis,
    smoothed_velocity,
)
from tests.fixtures import FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_PERFECT

client = TestClient(app)

ANALYZE_URL      = "/api/v1/analyze"
LONGITUDINAL_URL = "/api/v1/longitudinal-analysis"


# ===========================================================================
# Helpers
# ===========================================================================

def _get_analysis(fixture, age=30, gender="male", assessment_id="lng-test"):
    r = client.post(ANALYZE_URL, json={
        "assessmentId": assessment_id,
        "age": age,
        "gender": gender,
        "responses": fixture,
    })
    assert r.status_code == 200
    return r.json()


def _history_from_fixtures(fixtures, start="2026-05-01", step_days=14, age=30):
    """Build a history array by running /analyze per fixture with spaced
    synthetic timestamps (overriding the server-assigned ones)."""
    from datetime import datetime, timedelta, timezone
    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    history = []
    for i, fx in enumerate(fixtures):
        analysis = _get_analysis(fx, age=age, assessment_id=f"lng-{i}")
        ts = (t0 + timedelta(days=i * step_days)).isoformat().replace("+00:00", "Z")
        history.append({"sessionTimestamp": ts, "analysis": analysis})
    return history


# ===========================================================================
# 1. /analyze now emits a session timestamp
# ===========================================================================

class TestSessionTimestamp:
    def test_analyze_response_includes_session_timestamp(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        assert "sessionTimestamp" in analysis
        assert analysis["sessionTimestamp"].endswith("Z")

    def test_timestamp_is_parseable_iso8601(self):
        from app.services.longitudinal_engine import parse_timestamp
        analysis = _get_analysis(FIXTURE_MODERATE)
        parse_timestamp(analysis["sessionTimestamp"])  # must not raise


# ===========================================================================
# 2. Engine unit tests — normalization (PRD §3)
# ===========================================================================

class TestNormalization:
    def test_invariant_domain_keys_present(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        s = normalize_session({"sessionTimestamp": "2026-07-01T00:00:00Z",
                               "analysis": analysis})
        for key in ["score_memory", "score_attention", "score_processing_speed",
                    "score_executive_function", "score_clarity", "score_language",
                    "score_problem_solving", "score_reaction_time"]:
            assert key in s
            assert 0.0 <= s[key] <= 100.0

    def test_lifestyle_wellness_semantics(self):
        """High impact -> 30 (bad), Low impact -> 85 (good) — matches the
        convention used everywhere else in the codebase."""
        analysis = _get_analysis(FIXTURE_MODERATE)
        analysis["lifestyleImpacts"] = {
            "sleepQualityImpact": "High", "stressLevelImpact": "Low",
            "anxietyLoadImpact": "Moderate", "burnoutRiskImpact": "High",
        }
        s = normalize_session({"sessionTimestamp": "2026-07-01T00:00:00Z",
                               "analysis": analysis})
        assert s["lifestyle_sleep"] == 30.0
        assert s["lifestyle_stress"] == 85.0
        assert s["lifestyle_anxiety"] == 60.0
        assert s["lifestyle_burnout"] == 30.0

    def test_embedded_timestamp_used_when_record_level_missing(self):
        analysis = _get_analysis(FIXTURE_MODERATE)  # has sessionTimestamp
        s = normalize_session({"analysis": analysis})
        assert s["session_timestamp"].endswith("Z")

    def test_missing_timestamp_raises_with_index(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        analysis.pop("sessionTimestamp", None)
        with pytest.raises(ValueError, match=r"history\[0\].*sessionTimestamp"):
            normalize_history([{"analysis": analysis},
                               {"analysis": analysis}])

    def test_history_sorted_chronologically(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE])
        sessions = normalize_history(list(reversed(h)))
        assert sessions[0]["_dt"] < sessions[1]["_dt"]


# ===========================================================================
# 3. Engine unit tests — velocity & trends (PRD §4.1)
# ===========================================================================

class TestVelocityAndTrends:
    def test_improving_history_gives_improving_direction(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_PERFECT])
        result = run_longitudinal_analysis(h)
        traj = result["longitudinal_telemetry"]["overall_trajectory"]
        assert traj["direction"] == "improving"
        assert traj["velocity_score_per_day"] > 0
        assert traj["latest_overall_score"] > traj["baseline_overall_score"]

    def test_declining_history_gives_declining_direction(self):
        h = _history_from_fixtures([FIXTURE_PERFECT, FIXTURE_MODERATE, FIXTURE_WORST])
        result = run_longitudinal_analysis(h)
        traj = result["longitudinal_telemetry"]["overall_trajectory"]
        assert traj["direction"] == "declining"
        assert traj["velocity_score_per_day"] < 0

    def test_domain_trends_carry_full_history(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_PERFECT])
        trends = run_longitudinal_analysis(h)["longitudinal_telemetry"]["domain_trends"]
        assert len(trends) == 8
        for t in trends.values():
            assert len(t["historical_values"]) == 3
            assert t["status"] in {
                "requires_immediate_intervention", "declining_moderate",
                "stable", "improving_gradual", "improving_strong",
            }

    def test_severe_decline_flags_immediate_intervention(self):
        h = _history_from_fixtures([FIXTURE_PERFECT, FIXTURE_WORST])
        trends = run_longitudinal_analysis(h)["longitudinal_telemetry"]["domain_trends"]
        assert any(t["status"] == "requires_immediate_intervention"
                   for t in trends.values())

    def test_same_day_retake_does_not_crash(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE],
                                   step_days=0)
        result = run_longitudinal_analysis(h)  # Δt floored, must not raise
        assert result["historical_data_points_analyzed"] == 2

    def test_velocity_is_time_delta_scaled(self):
        """Same score change over a longer interval => smaller velocity."""
        fast = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE], step_days=7)
        slow = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE], step_days=70)
        v_fast = smoothed_velocity(normalize_history(fast), "overall_score")
        v_slow = smoothed_velocity(normalize_history(slow), "overall_score")
        assert v_fast > v_slow > 0


# ===========================================================================
# 4. Engine unit tests — attribution gating (PRD §4.2)
# ===========================================================================

class TestAttribution:
    def test_gated_below_four_points(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_PERFECT])
        sessions = normalize_history(h)
        assert compute_attribution_matrix(sessions) == {}

    def test_available_flag_matches_matrix(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_PERFECT])
        telemetry = run_longitudinal_analysis(h)["longitudinal_telemetry"]
        assert telemetry["attribution_available"] is False
        assert telemetry["lifestyle_attribution_matrix"] == {}

    def test_coefficients_bounded_when_present(self):
        h = _history_from_fixtures(
            [FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_WORST, FIXTURE_MODERATE,
             FIXTURE_PERFECT])
        matrix = run_longitudinal_analysis(h)[
            "longitudinal_telemetry"]["lifestyle_attribution_matrix"]
        for coeff in matrix.values():
            assert -1.0 <= coeff <= 1.0


# ===========================================================================
# 5. Engine unit tests — projections & insights
# ===========================================================================

class TestProjectionsAndInsights:
    def test_all_six_projection_keys_present(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE])
        proj = run_longitudinal_analysis(h)["predictive_projections_calibrated"]
        assert set(proj) == {
            "days_30_no_action", "days_30_with_recommendations",
            "days_60_no_action", "days_60_with_recommendations",
            "days_90_no_action", "days_90_with_recommendations",
        }

    def test_with_recommendations_beats_no_action(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE])
        proj = run_longitudinal_analysis(h)["predictive_projections_calibrated"]
        for days in ("30", "60", "90"):
            assert (proj[f"days_{days}_with_recommendations"]
                    > proj[f"days_{days}_no_action"])

    def test_projections_stay_in_score_bounds(self):
        for seq in ([FIXTURE_PERFECT, FIXTURE_PERFECT],
                    [FIXTURE_PERFECT, FIXTURE_WORST]):
            h = _history_from_fixtures(seq)
            proj = run_longitudinal_analysis(h)["predictive_projections_calibrated"]
            for v in proj.values():
                assert 0.0 <= v <= 100.0

    def test_insights_shape(self):
        h = _history_from_fixtures([FIXTURE_PERFECT, FIXTURE_WORST])
        ins = run_longitudinal_analysis(h)["contextual_ai_insights"]
        assert isinstance(ins["primary_bottleneck"], str)
        assert ins["primary_bottleneck"].endswith(".")
        assert 1 <= len(ins["dynamic_recommendations"]) <= 3


# ===========================================================================
# 6. Route tests — POST /api/v1/longitudinal-analysis
# ===========================================================================

class TestLongitudinalRoute:
    def test_happy_path_returns_200_and_payload(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE, FIXTURE_PERFECT])
        r = client.post(LONGITUDINAL_URL,
                        json={"userId": "testuser16@gmail.com", "history": h})
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == "testuser16@gmail.com"
        assert data["historical_data_points_analyzed"] == 3
        for key in ["aggregation_timestamp", "longitudinal_telemetry",
                    "predictive_projections_calibrated", "contextual_ai_insights"]:
            assert key in data

    def test_anonymous_when_no_user_id(self):
        h = _history_from_fixtures([FIXTURE_WORST, FIXTURE_MODERATE])
        r = client.post(LONGITUDINAL_URL, json={"history": h})
        assert r.status_code == 200
        assert r.json()["user_id"] == "anonymous"

    def test_single_record_rejected_422(self):
        h = _history_from_fixtures([FIXTURE_MODERATE])
        r = client.post(LONGITUDINAL_URL, json={"history": h})
        assert r.status_code == 422

    def test_missing_timestamp_rejected_422_with_detail(self):
        analysis = _get_analysis(FIXTURE_MODERATE)
        analysis.pop("sessionTimestamp", None)
        r = client.post(LONGITUDINAL_URL, json={"history": [
            {"analysis": analysis}, {"analysis": analysis},
        ]})
        assert r.status_code == 422
        assert "sessionTimestamp" in str(r.json()["detail"])

    def test_end_to_end_fresh_analyze_responses_work_unmodified(self):
        """New /analyze responses embed sessionTimestamp — the frontend can
        store and forward them without touching the JSON."""
        a1 = _get_analysis(FIXTURE_WORST,    assessment_id="e2e-1")
        a2 = _get_analysis(FIXTURE_MODERATE, assessment_id="e2e-2")
        # force distinct timestamps (same-second test runs)
        a1["sessionTimestamp"] = "2026-06-01T10:00:00Z"
        a2["sessionTimestamp"] = "2026-07-01T10:00:00Z"
        r = client.post(LONGITUDINAL_URL, json={"history": [
            {"analysis": a1}, {"analysis": a2},
        ]})
        assert r.status_code == 200
        traj = r.json()["longitudinal_telemetry"]["overall_trajectory"]
        assert traj["direction"] == "improving"
