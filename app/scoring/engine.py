"""
Limitless Cognitive Wellness Platform
Scoring Engine — v1.0

Pipeline: Raw responses (0–4) → Section averages → Normalize (0–100) → Invert → Domain scores → Overall score

"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# Domain weights (must sum to 1.0)
DOMAIN_WEIGHTS = {
    "memory":            0.20,
    "attention_focus":   0.20,
    "processing_speed":  0.15,
    "executive_function":0.15,
    "mental_clarity":    0.10,
    "language_skills":   0.05,
    "problem_solving":   0.05,
    "reaction_time":     0.05,
    # Note: remaining 0.05 from reaction_time brings total to 0.95;
    # doc weights sum to 1.0 — reaction_time carries the remainder
}

# Rating bands
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


@dataclass
class ScoringResult:
    overall_score:      float
    rating:             str
    section_scores:     SectionScores
    domain_scores:      DomainScores
    lifestyle_impacts:  LifestyleImpacts
    risk_indicators:    list[str]
    strengths:          list[str]
    cognitive_age:      Optional[int]
    audit:              dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Step 1 — Parse & validate responses
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 4 — Domain scores from section scores
# ---------------------------------------------------------------------------

def compute_domain_scores(s: SectionScores) -> DomainScores:
    """
    Maps section scores → 8 cognitive domain scores per spec.
    Proxy domains use clamping and delta logic as documented.
    """
    memory           = s.memory_function
    attention_focus  = s.focus_attention
    mental_clarity   = s.mental_clarity

    # Processing Speed: proxy from Mental Clarity, clamped [40, 95]
    processing_speed = max(40.0, min(95.0, mental_clarity * 0.9))

    # Executive Function: composite of Mental Clarity + Productivity, decision-item weighted
    executive_function = round((mental_clarity + s.productivity_performance) / 2, 2)

    # Language Skills: proxy from memory recall items, ±10 delta from base 70
    memory_delta = memory - 70
    language_skills = round(max(0, min(100, 70 + max(-10, min(10, memory_delta * 0.5)))), 2)

    # Problem Solving: proxy from decision/overwhelm items in S3, ±10 delta from base 70
    clarity_delta = mental_clarity - 70
    problem_solving = round(max(0, min(100, 70 + max(-10, min(10, clarity_delta * 0.5)))), 2)

    # Reaction Time: default 70 (future subtest placeholder)
    reaction_time = 70.0

    return DomainScores(
        memory=             round(memory, 2),
        attention_focus=    round(attention_focus, 2),
        processing_speed=   round(processing_speed, 2),
        executive_function= round(executive_function, 2),
        mental_clarity=     round(mental_clarity, 2),
        language_skills=    language_skills,
        problem_solving=    problem_solving,
        reaction_time=      reaction_time,
    )


# ---------------------------------------------------------------------------
# Step 5 — Overall weighted score & rating band
# ---------------------------------------------------------------------------

def compute_overall_score(d: DomainScores) -> tuple[float, str]:
    domain_dict = {
        "memory":             d.memory,
        "attention_focus":    d.attention_focus,
        "processing_speed":   d.processing_speed,
        "executive_function": d.executive_function,
        "mental_clarity":     d.mental_clarity,
        "language_skills":    d.language_skills,
        "problem_solving":    d.problem_solving,
        "reaction_time":      d.reaction_time,
    }

    # Normalize weights in case they don't exactly sum to 1.0
    total_weight = sum(DOMAIN_WEIGHTS.values())
    overall = sum(domain_dict[k] * (w / total_weight) for k, w in DOMAIN_WEIGHTS.items())
    overall = round(overall, 2)

    rating = "At Risk"
    for low, high, label in RATING_BANDS:
        if low <= overall <= high:
            rating = label
            break

    return overall, rating


# ---------------------------------------------------------------------------
# Step 6 — Lifestyle impact factors
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Cognitive Age Heuristic
# ---------------------------------------------------------------------------

def compute_cognitive_age(
    age: int,
    overall_score: float,
    sleep_score: float,
    stress_score: float,
) -> Optional[int]:
    """
    Estimates cognitive age based on overall score, sleep, and stress.
    Returns None for bands below 43 — not meaningful for younger cohorts.
    
    Formula (from spec):
      base     = actual age
      score δ  = −1 year per +3 pts above 70 / +1 year per −3 pts below 70
      sleep δ  = ±1–2 years based on sleep quality
      stress δ = ±1–2 years based on stress level
      result   = clamp(base + all deltas, 18, 80)
    """
    if age < 43:
        return None

    estimated = float(age)

    # --- Score delta ---
    score_delta = overall_score - 70
    estimated -= score_delta / 3   # +3 pts above 70 = −1 yr; −3 pts below 70 = +1 yr

    # --- Sleep modifier ---
    if sleep_score < 50:
        estimated += 2
    elif sleep_score < 70:
        estimated += 1
    elif sleep_score >= 85:
        estimated -= 1

    # --- Stress modifier ---
    if stress_score < 50:
        estimated += 2
    elif stress_score < 70:
        estimated += 1
    elif stress_score >= 85:
        estimated -= 1

    # --- Clamp to realistic range ---
    return int(round(max(18, min(80, estimated))))
# ---------------------------------------------------------------------------
# Step 8 — Strengths (domains >= 80)
# ---------------------------------------------------------------------------

DOMAIN_LABELS = {
    "memory":             "Memory retention",
    "attention_focus":    "Attention & focus",
    "processing_speed":   "Processing speed",
    "executive_function": "Executive function",
    "mental_clarity":     "Mental clarity",
    "language_skills":    "Language skills",
    "problem_solving":    "Problem solving",
    "reaction_time":      "Reaction time",
}

def compute_strengths(d: DomainScores) -> list[str]:
    domain_dict = vars(d)
    return [
        DOMAIN_LABELS[k]
        for k, v in domain_dict.items()
        if isinstance(v, (int, float)) and v >= 80
    ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score(age: int, gender: str, responses: list[dict]) -> ScoringResult:
    """
    Full scoring pipeline.

    Args:
        age:       User age (must be 18–25 for Phase 1)
        gender:    "female" | "male" | "other" | "prefer-not-to-say"
        responses: List of {"itemId": str, "value": int} dicts (28 items)

    Returns:
        ScoringResult dataclass with all computed fields
    """
    # Validate age for Phase 1 cohort
    if not (VALID_AGE_RANGE[0] <= age <= VALID_AGE_RANGE[1]):
        raise ValueError(
            f"Age {age} is outside Phase 1 scope ({VALID_AGE_RANGE[0]}–{VALID_AGE_RANGE[1]}). "
            "Expand VALID_AGE_RANGE when moving to all age groups."
        )

    audit = {}

    # Step 1 — parse & clamp
    parsed, clamp_flags = parse_responses(responses)
    if clamp_flags:
        audit["clamped_values"] = clamp_flags

    # Step 2 — section averages with imputation
    averages, imputation_notes = compute_section_averages(parsed)
    if imputation_notes:
        audit["imputation_notes"] = imputation_notes

    insufficient = [sid for sid, avg in averages.items() if avg is None]
    if insufficient:
        audit["insufficient_sections"] = insufficient

    # Step 3 — section scores
    section_scores = compute_section_scores(averages)

    # Step 4 — domain scores
    domain_scores = compute_domain_scores(section_scores)

    # Step 5 — overall score + rating
    overall_score, rating = compute_overall_score(domain_scores)
    
    cognitive_age = compute_cognitive_age(
    age=age,
    overall_score=overall_score,
    sleep_score=section_scores.sleep_recovery,
    stress_score=section_scores.stress_resilience,
)
    # Step 6 — lifestyle impacts
    lifestyle_impacts = compute_lifestyle_impacts(section_scores)

    # Step 7 — risk indicators
    risk_indicators = compute_risk_indicators(section_scores, domain_scores, age,overall_score)

    # Step 8 — strengths
    strengths = compute_strengths(domain_scores)

    audit["rules_version"] = "1.0"
    audit["age_cohort"] = "18-25"

    return ScoringResult(
        overall_score=overall_score,
        rating=rating,
        section_scores=section_scores,
        domain_scores=domain_scores,
        lifestyle_impacts=lifestyle_impacts,
        risk_indicators=risk_indicators,
        strengths=strengths,
        cognitive_age=cognitive_age,
        audit=audit,
    )
