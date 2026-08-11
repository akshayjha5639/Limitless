"""
Unit tests for v2 response validity checks (Phase 6).
Run: python -m pytest tests/test_validity.py -v

Covers app.scoring.scoring_model.check_response_validity in isolation, plus a
couple of score_assessment() integration checks. Does not modify any existing
test file.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scoring.engine import parse_responses
from app.scoring.scoring_model import check_response_validity, score_assessment
from tests.fixtures import FIXTURE_PERFECT, FIXTURE_WORST, FIXTURE_MODERATE


def _responses(values: list[int]) -> list[dict]:
    """Build a full 28-item response list from a flat list of 28 values."""
    assert len(values) == 28
    items = []
    idx = 0
    for s in range(1, 8):
        for q in range(1, 5):
            items.append({"itemId": f"S{s}_Q{q}", "value": values[idx]})
            idx += 1
    return items


def _parsed(responses: list[dict]) -> dict:
    parsed, _ = parse_responses(responses)
    return parsed


# ===========================================================================
# 1. Straight-lining
# ===========================================================================

class TestStraightLining:
    def test_all_identical_non_extreme_value_is_flagged(self):
        # All 2s: straight-lining fires, extreme_responding does not (2 is
        # neither 0 nor 4) -- isolates the straight_lining flag alone.
        result = check_response_validity(_parsed(_responses([2] * 28)))
        assert result["flags"] == ["straight_lining"]
        assert result["status"] == "Review"

    def test_26_of_28_identical_is_flagged(self):
        values = [2] * 28
        values[0] = 3
        values[1] = 1
        result = check_response_validity(_parsed(_responses(values)))
        assert "straight_lining" in result["flags"]

    def test_varied_responses_not_flagged(self):
        result = check_response_validity(_parsed(FIXTURE_MODERATE))
        assert "straight_lining" not in result["flags"]


# ===========================================================================
# 2. Extreme responding
# ===========================================================================

class TestExtremeResponding:
    def test_all_zero_is_flagged(self):
        result = check_response_validity(_parsed(FIXTURE_PERFECT))
        assert "extreme_responding" in result["flags"]

    def test_all_four_is_flagged(self):
        result = check_response_validity(_parsed(FIXTURE_WORST))
        assert "extreme_responding" in result["flags"]

    def test_varied_responses_not_flagged(self):
        result = check_response_validity(_parsed(FIXTURE_MODERATE))
        assert "extreme_responding" not in result["flags"]


# ===========================================================================
# 3. Speed floor
# ===========================================================================

class TestSpeedFloor:
    def test_under_90_seconds_is_flagged(self):
        result = check_response_validity(_parsed(FIXTURE_MODERATE), elapsed_seconds=60)
        assert "speed_floor" in result["flags"]

    def test_90_seconds_or_more_not_flagged(self):
        result = check_response_validity(_parsed(FIXTURE_MODERATE), elapsed_seconds=90)
        assert "speed_floor" not in result["flags"]

    def test_absent_elapsed_time_skips_check(self):
        result = check_response_validity(_parsed(FIXTURE_MODERATE), elapsed_seconds=None)
        assert "speed_floor" not in result["flags"]


# ===========================================================================
# 4. Reverse-coded inconsistency
# ===========================================================================

class TestReverseInconsistency:
    def test_contradictory_reverse_item_is_flagged(self):
        # S1: forward items (Q1-Q3) all 0, reverse item Q4 also raw 0 ->
        # converted (4-0=4) contradicts the forward average of 0 by 4 pts (>2).
        values = [0, 0, 0, 0] + [1] * 24
        result = check_response_validity(
            _parsed(_responses(values)), reverse_item_ids=["S1_Q4"]
        )
        assert result["flags"] == ["reverse_inconsistency"]
        assert result["status"] == "Review"

    def test_consistent_reverse_item_not_flagged(self):
        # S1_Q4 marked reverse but raw value 4 -> converted 0, matching the
        # forward average of 0 -- no contradiction.
        values = [0, 0, 0, 4] + [1] * 24
        result = check_response_validity(
            _parsed(_responses(values)), reverse_item_ids=["S1_Q4"]
        )
        assert "reverse_inconsistency" not in result["flags"]

    def test_no_reverse_items_supplied_never_flags(self):
        result = check_response_validity(_parsed(FIXTURE_WORST), reverse_item_ids=None)
        assert "reverse_inconsistency" not in result["flags"]


# ===========================================================================
# 5. Status thresholds — 0 flags Valid / 1 flag Review / 2+ Low confidence
# ===========================================================================

class TestValidityStatusThresholds:
    def test_valid_varied_responses_produce_valid(self):
        result = check_response_validity(_parsed(FIXTURE_MODERATE))
        assert result["flags"] == []
        assert result["status"] == "Valid"

    def test_one_flag_produces_review(self):
        result = check_response_validity(_parsed(_responses([2] * 28)))
        assert len(result["flags"]) == 1
        assert result["status"] == "Review"

    def test_two_or_more_flags_produce_low_confidence(self):
        # All zeros: straight_lining + extreme_responding = 2 flags.
        result = check_response_validity(_parsed(FIXTURE_PERFECT))
        assert len(result["flags"]) >= 2
        assert result["status"] == "Low confidence"


# ===========================================================================
# 6. score_assessment() integration — validity surfaces correctly on the full result
# ===========================================================================

class TestScoreV2ValidityIntegration:
    def test_valid_varied_responses_end_to_end(self):
        result = score_assessment(age=30, gender="male", responses=FIXTURE_MODERATE)
        assert result.validity.status == "Valid"
        assert result.validity.flags == []

    def test_straight_lined_responses_end_to_end(self):
        result = score_assessment(age=30, gender="male", responses=FIXTURE_PERFECT)
        assert result.validity.status in ("Review", "Low confidence")
        assert len(result.validity.flags) >= 1

    def test_speed_floor_and_reverse_inconsistency_combine_to_low_confidence(self):
        values = [0, 0, 0, 0] + [1] * 24
        result = score_assessment(
            age=30, gender="male", responses=_responses(values),
            elapsed_seconds=45, reverse_item_ids=["S1_Q4"],
        )
        assert len(result.validity.flags) >= 2
        assert result.validity.status == "Low confidence"
