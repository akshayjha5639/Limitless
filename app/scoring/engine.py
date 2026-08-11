"""
Limitless Cognitive Wellness Platform
Shared scoring primitives.

Response parsing, section averaging, normalise/invert, age banding, the
lifestyle-impact and risk-indicator rule engines, and the dataclasses those
rules are keyed on. The scales, composites and everything reported to the
user are computed in scoring_model.py, which builds on these.

DomainScores is an internal rule-engine input, not a reported structure --
app/services/recommendations.py keys several of its rules on fields such as
processing_speed, so the shape is retained and fed from the nearest real
scale. Nothing in it reaches the API response.
"""

from dataclasses import dataclass
from typing import Optional


VALID_AGE_RANGE = (18, 66) 

# ---------------------------------------------------------------------------
# Age Band Helper
# ---------------------------------------------------------------------------

def get_age_band(age: int) -> str:
    """
    Returns the age band key for a given age.
    Used by question_generator.py and recommendations.py
    to avoid duplicating band logic across files.
    
    Bands:
        18–25  → young_adult
        26–32  → emerging_professional
        33–37  → established_adult
        38–42  → mid_career
        43–47  → midlife_transition
        48–55  → pre_senior
        56–66  → senior_adult
    
    Note: 38 belongs to mid_career per design decision.
    """
    if 18 <= age <= 25:
        return "young_adult"
    elif 26 <= age <= 32:
        return "emerging_professional"
    elif 33 <= age <= 37:
        return "established_adult"
    elif 38 <= age <= 42:
        return "mid_career"
    elif 43 <= age <= 47:
        return "midlife_transition"
    elif 48 <= age <= 55:
        return "pre_senior"
    elif 56 <= age <= 66:
        return "senior_adult"
    else:
        raise ValueError(
            f"Age {age} is outside supported range (18–66). "
            f"Update VALID_AGE_RANGE and get_age_band() together."
        )
        
SECTION_IDS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
ITEMS_PER_SECTION = 4
RESPONSE_MIN, RESPONSE_MAX = 0, 4

RATING_BANDS = [
    (85, 100, "Excellent"),
    (70,  84, "Good"),
    (50,  69, "Needs Attention"),
    (0,   49, "At Risk"),
]

# Risk indicator rules: (label, condition_fn)
# condition_fn receives domain_scores dict + age
RISK_RULES = [
    (
        "Possible stress-related cognitive fatigue",
        lambda d, age: d["stress_resilience"] < 60,
    ),
    (
        "Possible burnout symptoms",
        lambda d, age: d["stress_resilience"] < 60 and d["productivity_performance"] < 65,
    ),
    (
        "Possible attention difficulties",
        lambda d, age: d["attention_focus"] < 65,
    ),
    (
        "Possible sleep-related memory decline",
        lambda d, age: d["sleep_recovery"] < 60 and d["memory"] < 75,
    ),
    (
        "Possible mood-related concentration issues",
        lambda d, age: d["emotional_wellbeing"] < 60,
    ),
    (
        "Possible midlife burnout pattern",
        lambda d, age: age >= 43 and d["stress_resilience"] < 60 and d["productivity_performance"] < 65,
    ),
    (
        "Possible age-related cognitive slowdown indicators",
        lambda d, age: age >= 56 and d["overall"] < 72,
    ),
]

# Lifestyle impact factor thresholds → High / Moderate / Low
def _impact_label(score: float) -> str:
    if score < 50:
        return "High"
    elif score < 70:
        return "Moderate"
    else:
        return "Low"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SectionScores:
    """Inverted 0–100 scores per section (higher = better)."""
    focus_attention:        float  # S1
    memory_function:        float  # S2
    mental_clarity:         float  # S3
    emotional_wellbeing:    float  # S4
    stress_resilience:      float  # S5
    sleep_recovery:         float  # S6
    productivity_performance: float  # S7


@dataclass
class DomainScores:
    memory:             float
    attention_focus:    float
    processing_speed:   float
    executive_function: float
    mental_clarity:     float
    language_skills:    float
    problem_solving:    float
    reaction_time:      float


@dataclass
class LifestyleImpacts:
    sleep_quality:  str
    stress_level:   str
    anxiety_load:   str
    burnout_risk:   str

def parse_responses(responses: list[dict]) -> dict[str, int]:
    """
    Input:  [{"itemId": "S1_Q1", "value": 2}, ...]
    Output: {"S1_Q1": 2, ...}

    Clamps all values to [0, 4]. Flags out-of-range in returned audit dict.
    Returns (parsed_dict, audit_flags)
    """
    parsed = {}
    audit_flags = []

    for r in responses:
        item_id = r["itemId"]
        raw_val = r["value"]
        clamped = max(RESPONSE_MIN, min(RESPONSE_MAX, int(raw_val)))
        if clamped != raw_val:
            audit_flags.append(f"{item_id}: value {raw_val} clamped to {clamped}")
        parsed[item_id] = clamped

    return parsed, audit_flags


# ---------------------------------------------------------------------------
# Step 2 — Section averages with missing-item imputation
# ---------------------------------------------------------------------------

def compute_section_averages(parsed: dict[str, int]) -> tuple[dict[str, Optional[float]], list[str]]:
    """
    Returns section_avg dict: {"S1": 1.75, "S2": None (insufficient), ...}
    None means <50% of items were answered → mark as insufficient.
    """
    averages = {}
    notes = []

    for sid in SECTION_IDS:
        item_keys = [f"{sid}_Q{i}" for i in range(1, ITEMS_PER_SECTION + 1)]
        answered = {k: parsed[k] for k in item_keys if k in parsed}
        total_items = ITEMS_PER_SECTION
        answered_count = len(answered)

        if answered_count == 0:
            averages[sid] = None
            notes.append(f"{sid}: no responses — marked Insufficient")
        elif answered_count < total_items * 0.5:
            averages[sid] = None
            notes.append(f"{sid}: only {answered_count}/{total_items} answered — marked Insufficient")
        else:
            # Impute missing items with section average of answered items
            partial_avg = sum(answered.values()) / answered_count
            if answered_count < total_items:
                notes.append(f"{sid}: {total_items - answered_count} item(s) imputed with section avg {partial_avg:.2f}")
            averages[sid] = partial_avg

    return averages, notes


# ---------------------------------------------------------------------------
# Step 3 — Normalize & invert to section scores (0–100, higher = better)
# ---------------------------------------------------------------------------

def normalize_invert(raw_avg: float) -> float:
    """(raw_avg / 4) * 100 → invert → domain score."""
    normalized = (raw_avg / RESPONSE_MAX) * 100
    return round(100 - normalized, 2)


def compute_section_scores(averages: dict[str, Optional[float]]) -> SectionScores:
    def score(sid: str) -> float:
        avg = averages.get(sid)
        return normalize_invert(avg) if avg is not None else 50.0  # neutral fallback

    return SectionScores(
        focus_attention=         score("S1"),
        memory_function=         score("S2"),
        mental_clarity=          score("S3"),
        emotional_wellbeing=     score("S4"),
        stress_resilience=       score("S5"),
        sleep_recovery=          score("S6"),
        productivity_performance=score("S7"),
    )

def compute_lifestyle_impacts(s: SectionScores) -> LifestyleImpacts:
    return LifestyleImpacts(
        sleep_quality= _impact_label(s.sleep_recovery),
        stress_level=  _impact_label(s.stress_resilience),
        anxiety_load=  _impact_label(s.emotional_wellbeing),
        burnout_risk=  _impact_label(
            (s.stress_resilience + s.productivity_performance) / 2
        ),
    )


# ---------------------------------------------------------------------------
# Step 7 — Risk indicators
# ---------------------------------------------------------------------------

def compute_risk_indicators(s: SectionScores, d: DomainScores, age: int,overall_score : float=0.0) -> list[str]:
    # Build a flat dict including both section and domain scores for rule access
    scores = {
        "stress_resilience":      s.stress_resilience,
        "productivity_performance": s.productivity_performance,
        "attention_focus":        d.attention_focus,
        "sleep_recovery":         s.sleep_recovery,
        "memory":                 d.memory,
        "emotional_wellbeing":    s.emotional_wellbeing,
        "overall":                  overall_score,
    }
    return [label for label, condition in RISK_RULES if condition(scores, age)]

