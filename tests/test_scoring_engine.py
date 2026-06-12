"""
Unit tests for Limitless Scoring Engine
Run: python -m pytest tests/test_scoring_engine.py -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.scoring.engine import (
    score,
    parse_responses,
    compute_section_averages,
    compute_section_scores,
    compute_domain_scores,
    compute_overall_score,
    compute_lifestyle_impacts,
    compute_risk_indicators,
    compute_strengths,
    normalize_invert,
    SectionScores,
    VALID_AGE_RANGE,
)
from tests.fixtures import (
    FIXTURE_PERFECT,
    FIXTURE_WORST,
    FIXTURE_MODERATE,
    FIXTURE_BURNOUT,
    FIXTURE_ATTENTION_ONLY,
    FIXTURE_OUT_OF_RANGE,
    build_missing_section_responses,
)


# ===========================================================================
# 1. Normalize-Invert Pipeline
# ===========================================================================

class TestNormalizeInvert:
    def test_zero_raw_gives_100(self):
        assert normalize_invert(0.0) == 100.0

    def test_max_raw_gives_zero(self):
        assert normalize_invert(4.0) == 0.0

    def test_midpoint(self):
        assert normalize_invert(2.0) == 50.0

    def test_known_value(self):
        # avg=1.0 → normalized=25 → inverted=75
        assert normalize_invert(1.0) == 75.0


# ===========================================================================
# 2. Response Parsing & Clamping
# ===========================================================================

class TestParseResponses:
    def test_valid_responses_pass_through(self):
        responses = [{"itemId": "S1_Q1", "value": 2}]
        parsed, flags = parse_responses(responses)
        assert parsed["S1_Q1"] == 2
        assert flags == []

    def test_value_above_max_is_clamped(self):
        responses = [{"itemId": "S1_Q1", "value": 7}]
        parsed, flags = parse_responses(responses)
        assert parsed["S1_Q1"] == 4
        assert len(flags) == 1
        assert "S1_Q1" in flags[0]

    def test_negative_value_clamped_to_zero(self):
        responses = [{"itemId": "S2_Q1", "value": -3}]
        parsed, flags = parse_responses(responses)
        assert parsed["S2_Q1"] == 0
        assert len(flags) == 1

    def test_boundary_values_not_flagged(self):
        responses = [
            {"itemId": "S1_Q1", "value": 0},
            {"itemId": "S1_Q2", "value": 4},
        ]
        _, flags = parse_responses(responses)
        assert flags == []

    def test_out_of_range_fixture_clamped(self):
        parsed, flags = parse_responses(FIXTURE_OUT_OF_RANGE)
        assert parsed["S1_Q1"] == 4   # 5 → clamped to 4
        assert parsed["S2_Q1"] == 0   # -1 → clamped to 0
        assert len(flags) == 2


# ===========================================================================
# 3. Section Averages & Imputation
# ===========================================================================

class TestSectionAverages:
    def test_all_present_no_imputation(self):
        # Provide full responses for ALL sections to ensure no missing-section notes
        parsed = {}
        for s in range(1, 8):
            for q in range(1, 5):
                parsed[f"S{s}_Q{q}"] = 2
        averages, notes = compute_section_averages(parsed)
        assert averages["S1"] == pytest.approx(2.0)
        assert averages["S2"] == pytest.approx(2.0)
        assert notes == []

    def test_missing_section_marked_insufficient(self):
        responses = build_missing_section_responses("S3")
        parsed, _ = parse_responses(responses)
        averages, notes = compute_section_averages(parsed)
        assert averages["S3"] is None
        assert any("S3" in n for n in notes)

    def test_partial_section_imputes_if_above_50pct(self):
        # 3 of 4 items answered → above 50%, should impute
        parsed = {"S1_Q1": 2, "S1_Q2": 2, "S1_Q3": 2}  # S1_Q4 missing
        averages, notes = compute_section_averages(parsed)
        assert averages["S1"] == pytest.approx(2.0)
        assert any("imputed" in n for n in notes)

    def test_partial_section_insufficient_below_50pct(self):
        # 1 of 4 items answered → below 50%, insufficient
        parsed = {"S1_Q1": 3}
        averages, notes = compute_section_averages(parsed)
        assert averages["S1"] is None


# ===========================================================================
# 4. Domain Score Computation
# ===========================================================================

class TestDomainScores:
    def _make_section(self, val: float) -> SectionScores:
        return SectionScores(
            focus_attention=val,
            memory_function=val,
            mental_clarity=val,
            emotional_wellbeing=val,
            stress_resilience=val,
            sleep_recovery=val,
            productivity_performance=val,
        )

    def test_processing_speed_clamped_at_95(self):
        # Mental clarity = 100 → 100 * 0.9 = 90, within clamp
        s = self._make_section(100.0)
        d = compute_domain_scores(s)
        assert d.processing_speed == pytest.approx(90.0)

    def test_processing_speed_clamped_at_40(self):
        # Mental clarity = 0 → 0 * 0.9 = 0, clamped to 40
        s = self._make_section(0.0)
        d = compute_domain_scores(s)
        assert d.processing_speed == pytest.approx(40.0)

    def test_language_skills_at_70_when_memory_equals_70(self):
        s = self._make_section(70.0)
        d = compute_domain_scores(s)
        assert d.language_skills == pytest.approx(70.0)

    def test_language_skills_delta_capped_at_10(self):
        # Memory = 100 → delta = 30 → delta*0.5 = 15 → capped at 10 → language = 80
        s = self._make_section(100.0)
        d = compute_domain_scores(s)
        assert d.language_skills == pytest.approx(80.0)

    def test_reaction_time_is_default_70(self):
        s = self._make_section(80.0)
        d = compute_domain_scores(s)
        assert d.reaction_time == 70.0

    def test_executive_function_is_average_of_clarity_and_productivity(self):
        s = SectionScores(
            focus_attention=80,
            memory_function=80,
            mental_clarity=60.0,
            emotional_wellbeing=80,
            stress_resilience=80,
            sleep_recovery=80,
            productivity_performance=80.0,
        )
        d = compute_domain_scores(s)
        assert d.executive_function == pytest.approx(70.0)


# ===========================================================================
# 5. Overall Score & Rating Bands
# ===========================================================================

class TestOverallScore:
    def _make_domains(self, val: float):
        from app.scoring.engine import DomainScores
        return DomainScores(
            memory=val, attention_focus=val, processing_speed=val,
            executive_function=val, mental_clarity=val, language_skills=val,
            problem_solving=val, reaction_time=val,
        )

    def test_all_100_gives_excellent(self):
        score, rating = compute_overall_score(self._make_domains(100.0))
        assert rating == "Excellent"
        assert score == pytest.approx(100.0)

    def test_all_0_gives_at_risk(self):
        score, rating = compute_overall_score(self._make_domains(0.0))
        assert rating == "At Risk"

    def test_score_75_is_good(self):
        score, rating = compute_overall_score(self._make_domains(75.0))
        assert rating == "Good"

    def test_score_60_is_needs_attention(self):
        score, rating = compute_overall_score(self._make_domains(60.0))
        assert rating == "Needs Attention"

    def test_score_85_is_excellent(self):
        score, rating = compute_overall_score(self._make_domains(85.0))
        assert rating == "Excellent"


# ===========================================================================
# 6. Risk Indicators
# ===========================================================================

class TestRiskIndicators:
    def _section(self, **kwargs) -> SectionScores:
        defaults = dict(
            focus_attention=80, memory_function=80, mental_clarity=80,
            emotional_wellbeing=80, stress_resilience=80,
            sleep_recovery=80, productivity_performance=80,
        )
        defaults.update(kwargs)
        return SectionScores(**defaults)

    def test_no_risks_when_all_high(self):
        s = self._section()
        from app.scoring.engine import DomainScores
        d = DomainScores(memory=80, attention_focus=80, processing_speed=80,
                         executive_function=80, mental_clarity=80,
                         language_skills=80, problem_solving=80, reaction_time=70)
        risks = compute_risk_indicators(s, d, age=22)
        assert risks == []

    def test_stress_fatigue_triggered(self):
        s = self._section(stress_resilience=55)
        from app.scoring.engine import DomainScores
        d = DomainScores(memory=80, attention_focus=80, processing_speed=80,
                         executive_function=80, mental_clarity=80,
                         language_skills=80, problem_solving=80, reaction_time=70)
        risks = compute_risk_indicators(s, d, age=22)
        assert any("stress" in r.lower() for r in risks)

    def test_burnout_requires_both_stress_and_productivity_low(self):
        # Only stress low → no burnout
        s = self._section(stress_resilience=55, productivity_performance=70)
        from app.scoring.engine import DomainScores
        d = DomainScores(memory=80, attention_focus=80, processing_speed=80,
                         executive_function=80, mental_clarity=80,
                         language_skills=80, problem_solving=80, reaction_time=70)
        risks = compute_risk_indicators(s, d, age=22)
        assert not any("burnout" in r.lower() for r in risks)

        # Both low → burnout triggered
        s2 = self._section(stress_resilience=55, productivity_performance=60)
        risks2 = compute_risk_indicators(s2, d, age=22)
        assert any("burnout" in r.lower() for r in risks2)

    def test_all_risk_indicators_prefixed_with_possible(self):
        s = self._section(
            stress_resilience=40,
            productivity_performance=40,
            emotional_wellbeing=40,
            sleep_recovery=40,
        )
        from app.scoring.engine import DomainScores
        d = DomainScores(memory=60, attention_focus=60, processing_speed=60,
                         executive_function=60, mental_clarity=60,
                         language_skills=60, problem_solving=60, reaction_time=70)
        risks = compute_risk_indicators(s, d, age=22)
        for r in risks:
            assert r.startswith("Possible"), f"Risk indicator missing 'Possible' prefix: {r}"


# ===========================================================================
# 7. Lifestyle Impacts
# ===========================================================================

class TestLifestyleImpacts:
    def test_high_impact_when_score_below_50(self):
        s = SectionScores(
            focus_attention=80, memory_function=80, mental_clarity=80,
            emotional_wellbeing=40, stress_resilience=40,
            sleep_recovery=40, productivity_performance=40,
        )
        impacts = compute_lifestyle_impacts(s)
        assert impacts.sleep_quality == "High"
        assert impacts.stress_level == "High"

    def test_low_impact_when_score_above_70(self):
        s = SectionScores(
            focus_attention=80, memory_function=80, mental_clarity=80,
            emotional_wellbeing=80, stress_resilience=80,
            sleep_recovery=80, productivity_performance=80,
        )
        impacts = compute_lifestyle_impacts(s)
        assert impacts.sleep_quality == "Low"
        assert impacts.stress_level == "Low"

    def test_moderate_impact_at_60(self):
        s = SectionScores(
            focus_attention=80, memory_function=80, mental_clarity=80,
            emotional_wellbeing=80, stress_resilience=60,
            sleep_recovery=60, productivity_performance=60,
        )
        impacts = compute_lifestyle_impacts(s)
        assert impacts.sleep_quality == "Moderate"
        assert impacts.stress_level == "Moderate"


# ===========================================================================
# 8. Strengths
# ===========================================================================

class TestStrengths:
    def test_no_strengths_when_all_below_80(self):
        from app.scoring.engine import DomainScores
        d = DomainScores(memory=70, attention_focus=70, processing_speed=70,
                         executive_function=70, mental_clarity=70,
                         language_skills=70, problem_solving=70, reaction_time=70)
        assert compute_strengths(d) == []

    def test_strengths_identified_at_80_and_above(self):
        from app.scoring.engine import DomainScores
        d = DomainScores(memory=85, attention_focus=82, processing_speed=70,
                         executive_function=70, mental_clarity=70,
                         language_skills=70, problem_solving=70, reaction_time=70)
        strengths = compute_strengths(d)
        assert len(strengths) == 2


# ===========================================================================
# 9. Full Pipeline Integration Tests
# ===========================================================================

class TestFullPipeline:
    def test_perfect_responses_give_excellent(self):
        result = score(22, "male", FIXTURE_PERFECT)
        assert result.rating == "Excellent"
        assert result.overall_score >= 85
        assert result.risk_indicators == []

    def test_worst_responses_give_at_risk(self):
        result = score(22, "female", FIXTURE_WORST)
        assert result.rating == "At Risk"
        assert result.overall_score < 50
        assert len(result.risk_indicators) > 0

    def test_burnout_profile_triggers_burnout_risk(self):
        result = score(21, "other", FIXTURE_BURNOUT)
        risk_text = " ".join(result.risk_indicators).lower()
        assert "burnout" in risk_text
        assert "stress" in risk_text

    def test_attention_only_profile_flags_attention(self):
        result = score(20, "female", FIXTURE_ATTENTION_ONLY)
        risk_text = " ".join(result.risk_indicators).lower()
        assert "attention" in risk_text

    def test_moderate_profile_scores_in_good_or_needs_attention(self):
        result = score(23, "male", FIXTURE_MODERATE)
        assert result.rating in ("Good", "Needs Attention")

    def test_audit_populated(self):
        result = score(22, "male", FIXTURE_MODERATE)
        assert "rules_version" in result.audit
        assert result.audit["age_cohort"] == "18-25"

    def test_clamping_audit_flag_on_out_of_range(self):
        result = score(22, "male", FIXTURE_OUT_OF_RANGE)
        assert "clamped_values" in result.audit

    def test_missing_section_noted_in_audit(self):
        responses = build_missing_section_responses("S3")
        result = score(22, "male", responses)
        assert "insufficient_sections" in result.audit
        assert "S3" in result.audit["insufficient_sections"]


# ===========================================================================
# 10. Age Validation (Phase 1 cohort guard)
# ===========================================================================

class TestAgeValidation:
    def test_valid_ages_pass(self):
        for age in [18, 20, 22, 25]:
            result = score(age, "male", FIXTURE_MODERATE)
            assert result is not None

    def test_age_below_18_raises(self):
        with pytest.raises(ValueError, match="outside Phase 1 scope"):
            score(17, "male", FIXTURE_MODERATE)

    def test_age_above_25_raises(self):
        with pytest.raises(ValueError, match="outside Phase 1 scope"):
            score(26, "male", FIXTURE_MODERATE)

    def test_boundary_18_passes(self):
        result = score(18, "female", FIXTURE_PERFECT)
        assert result.overall_score >= 85

    def test_boundary_25_passes(self):
        result = score(25, "female", FIXTURE_PERFECT)
        assert result.overall_score >= 85
