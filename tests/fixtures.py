"""
Test fixtures — mock 28-item responses for different cognitive profiles.
Used across unit tests to avoid repetition.
"""

def _build_responses(values: list[int]) -> list[dict]:
    """Build a full 28-item response list from a flat list of 28 values."""
    assert len(values) == 28, f"Expected 28 values, got {len(values)}"
    items = []
    idx = 0
    for s in range(1, 8):
        for q in range(1, 5):
            items.append({"itemId": f"S{s}_Q{q}", "value": values[idx]})
            idx += 1
    return items


# All zeros → perfect score (no symptoms at all)
FIXTURE_PERFECT = _build_responses([0] * 28)

# All fours → worst score (severe symptoms across the board)
FIXTURE_WORST = _build_responses([4] * 28)

# Moderate overall — mixed responses typical of healthy 20-year-old
# S1(Focus)=1s, S2(Memory)=1s, S3(Clarity)=2s, S4(Emotion)=1s,
# S5(Stress)=2s, S6(Sleep)=2s, S7(Productivity)=1s
FIXTURE_MODERATE = _build_responses(
    [1, 1, 1, 1,   # S1 Focus — low symptoms
     1, 1, 2, 1,   # S2 Memory — mostly fine
     2, 2, 2, 2,   # S3 Clarity — some fogginess
     1, 1, 2, 1,   # S4 Emotion — mild
     2, 2, 3, 2,   # S5 Stress — moderate/high
     2, 2, 2, 3,   # S6 Sleep — disrupted
     1, 1, 2, 1]   # S7 Productivity — mostly fine
)

# High stress + poor sleep → burnout risk profile
FIXTURE_BURNOUT = _build_responses(
    [2, 3, 2, 3,   # S1 Focus — impaired
     2, 2, 2, 3,   # S2 Memory — borderline
     3, 3, 3, 2,   # S3 Clarity — impaired
     3, 3, 3, 3,   # S4 Emotion — high
     4, 4, 4, 3,   # S5 Stress — severe
     3, 4, 3, 4,   # S6 Sleep — severe
     3, 3, 3, 3]   # S7 Productivity — impaired
)

# Attention difficulty only — good everything else
FIXTURE_ATTENTION_ONLY = _build_responses(
    [3, 3, 3, 3,   # S1 Focus — high symptoms
     1, 1, 1, 1,   # S2 Memory — fine
     1, 1, 1, 1,   # S3 Clarity — fine
     1, 1, 1, 1,   # S4 Emotion — fine
     1, 1, 1, 1,   # S5 Stress — fine
     1, 1, 1, 1,   # S6 Sleep — fine
     1, 1, 1, 1]   # S7 Productivity — fine
)

# Missing items — S3 completely unanswered (tests imputation)
def build_missing_section_responses(missing_section: str = "S3") -> list[dict]:
    responses = []
    for s in range(1, 8):
        for q in range(1, 5):
            sid = f"S{s}"
            if sid != missing_section:
                responses.append({"itemId": f"{sid}_Q{q}", "value": 1})
    return responses


# Out-of-range values — should be clamped
FIXTURE_OUT_OF_RANGE = [
    {"itemId": f"S{s}_Q{q}", "value": 5 if (s == 1 and q == 1) else (-1 if (s == 2 and q == 1) else 2)}
    for s in range(1, 8) for q in range(1, 5)
]
# Band-specific moderate fixtures
FIXTURE_BAND_26 = _build_responses(
    [1,2,1,2, 2,1,2,1, 2,2,1,2, 1,2,1,2, 2,2,2,1, 1,2,2,1, 1,1,2,2]
)

FIXTURE_BAND_35 = _build_responses(
    [2,2,1,2, 2,2,1,2, 2,2,2,1, 2,2,2,1, 2,2,2,2, 2,2,1,2, 2,1,2,2]
)

FIXTURE_BAND_40 = _build_responses(
    [2,2,2,2, 2,2,2,1, 2,2,2,2, 2,2,2,2, 3,2,2,2, 2,2,2,2, 2,2,2,2]
)

FIXTURE_BAND_45 = _build_responses(
    [2,2,2,3, 2,2,2,2, 3,2,2,2, 2,3,2,2, 3,2,3,2, 2,3,2,2, 2,2,3,2]
)

FIXTURE_BAND_51 = _build_responses(
    [2,3,2,2, 3,2,2,2, 2,2,3,2, 2,2,2,3, 3,3,2,2, 3,2,3,2, 2,3,2,2]
)

FIXTURE_BAND_60 = _build_responses(
    [3,2,3,2, 3,3,2,2, 3,2,2,3, 2,3,2,2, 3,2,3,3, 3,3,2,3, 3,2,2,3]
)