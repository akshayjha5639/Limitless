"""
Limitless Cognitive Wellness Platform
Scoring Engine — v2.0 (additive, parallel to engine.py — v1 is untouched)

v2 reports one real scale per section (no fabricated proxies): the three
domains v1 fabricated (hardcoded Reaction Time, ±5 Language/Problem-Solving
derivations, Mental Clarity × 0.9 Processing Speed) are dropped entirely.

Pipeline: Raw responses (0-4) -> Section averages -> Normalize/invert (0-100)
          -> 7 scale scores -> composites + overall -> cognitive age /
          percentile / validity (all provisional, clearly labelled as such).

Reused from engine.py (v1): get_age_band, parse_responses,
compute_section_averages, normalize_invert, SectionScores, DomainScores,
compute_lifestyle_impacts, compute_risk_indicators, RATING_BANDS,
VALID_AGE_RANGE, SECTION_IDS, ITEMS_PER_SECTION.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from app.scoring.engine import (
    get_age_band,
    parse_responses,
    compute_section_averages,
    normalize_invert,
    SectionScores,
    DomainScores,
    LifestyleImpacts,
    compute_lifestyle_impacts as _v1_compute_lifestyle_impacts,
    compute_risk_indicators as _v1_compute_risk_indicators,
    RATING_BANDS,
    VALID_AGE_RANGE,
    SECTION_IDS,
    ITEMS_PER_SECTION,
)

# ---------------------------------------------------------------------------
# Section -> v2 scale mapping (item authoring/section content redesign is a
# separate, human-reviewed process — this is only the index -> key mapping)
# ---------------------------------------------------------------------------

SECTION_TO_SCALE = {
    "S1": "attentionFocus",
    "S2": "memoryRecall",
    "S3": "executiveFunction",
    "S4": "mentalEnergy",
    "S5": "stressLoad",
    "S6": "sleepRecovery",
    "S7": "lifestyleModule",
}

SCALE_DISPLAY_NAMES = {
    "attentionFocus":    "Attention & Focus",
    "memoryRecall":       "Memory & Recall",
    "executiveFunction":  "Executive Function",
    "mentalEnergy":       "Mental Energy",
    "stressLoad":         "Stress & Emotional Load",
    "sleepRecovery":      "Sleep & Recovery",
    "lifestyleModule":    "Lifestyle Module",
}

# Overall score weights (must sum to 1.0)
SCALE_WEIGHTS = {
    "attentionFocus":    0.20,
    "memoryRecall":       0.20,
    "executiveFunction":  0.18,
    "mentalEnergy":       0.14,
    "sleepRecovery":      0.13,
    "stressLoad":         0.10,
    "lifestyleModule":    0.05,
}

# ---------------------------------------------------------------------------
# Provisional statistical constants — pending empirical calibration.
# SEM = SD * sqrt(1 - alpha); 95% interval = score +/- 1.96 * SEM
# ---------------------------------------------------------------------------

SCALE_SD        = 18.0   # provisional
SCALE_ALPHA     = 0.75   # provisional, 4-item scale
COMPOSITE_SD    = 15.0   # provisional
COMPOSITE_ALPHA = 0.85   # provisional, 12-item composite

CI_Z = 1.96  # 95% interval

# Cognitive age — rebased expected-score-by-age curve (provisional)
COGNITIVE_AGE_MIN_AGE = 43  # config-readable threshold; below this, None is returned (matches v1 UX)


def expected_score(age: float) -> float:
    """Provisional expected-score-by-age curve, replacing v1's fixed anchor of 70."""
    return 78.0 - 0.25 * (age - 18)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScaleResult:
    score:  float
    sem:    float
    ciLow:  float
    ciHigh: float


@dataclass
class ScalesV2Result:
    attentionFocus:     ScaleResult
    memoryRecall:        ScaleResult
    executiveFunction:   ScaleResult
    mentalEnergy:        ScaleResult
    stressLoad:          ScaleResult
    sleepRecovery:       ScaleResult
    lifestyleModule:     ScaleResult


@dataclass
class CompositesResult:
    cognitiveComplaintIndex: ScaleResult
    modifiableLoadIndex:     ScaleResult


@dataclass
class CognitiveAgeV2Result:
    actualAge:             int
    estimatedCognitiveAge: Optional[int]
    ageLow:                Optional[int]
    ageHigh:               Optional[int]
    provisional:           bool = True
    disclaimer:            str = (
        "Provisional wellness index — not a clinical measure of brain age."
    )


@dataclass
class PercentileV2Result:
    value:       Optional[int]
    provisional: bool = True


@dataclass
class ValidityResult:
    status: str
    flags:  list[str] = field(default_factory=list)


@dataclass
class ScoringResultV2:
    overall_score:     float
    rating:             str
    scales:             ScalesV2Result
    composites:         CompositesResult
    lifestyle_impacts:  LifestyleImpacts
    risk_indicators:    list[str]
    strengths:          list[str]
    cognitive_age:      CognitiveAgeV2Result
    percentile:         PercentileV2Result
    validity:           ValidityResult
    audit:              dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 2.1 — Seven scales (reuses v1's normalize/invert pipeline, no proxies)
# ---------------------------------------------------------------------------

def compute_scale_scores_raw(averages: dict[str, Optional[float]]) -> dict[str, float]:
    """Scale score = section score (normalize + invert), exactly as v1 computes
    section scores — same 50.0 neutral fallback for insufficient sections."""
    def sc(sid: str) -> float:
        avg = averages.get(sid)
        return normalize_invert(avg) if avg is not None else 50.0

    return {scale_key: sc(sid) for sid, scale_key in SECTION_TO_SCALE.items()}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _apply_ci(score: float, sd: float, alpha: float) -> ScaleResult:
    sem = sd * math.sqrt(1 - alpha)
    margin = CI_Z * sem
    return ScaleResult(
        score=round(score, 1),
        sem=round(sem, 2),
        ciLow=round(_clamp(score - margin), 1),
        ciHigh=round(_clamp(score + margin), 1),
    )


# ---------------------------------------------------------------------------
# 2.2 — Composite indices (mean of constituent scale scores)
# ---------------------------------------------------------------------------

def compute_composites_raw(scale_rounded: dict[str, float]) -> dict[str, float]:
    cognitive_complaint_index = (
        scale_rounded["attentionFocus"] + scale_rounded["memoryRecall"] + scale_rounded["executiveFunction"]
    ) / 3
    modifiable_load_index = (
        scale_rounded["mentalEnergy"] + scale_rounded["stressLoad"] + scale_rounded["sleepRecovery"]
    ) / 3
    return {
        "cognitiveComplaintIndex": cognitive_complaint_index,
        "modifiableLoadIndex":     modifiable_load_index,
    }


# ---------------------------------------------------------------------------
# 2.3 — Overall score & rating (weighted average of the seven scales)
# ---------------------------------------------------------------------------

def compute_overall_v2(scale_rounded: dict[str, float]) -> tuple[float, str]:
    total_weight = sum(SCALE_WEIGHTS.values())
    overall = sum(scale_rounded[k] * (w / total_weight) for k, w in SCALE_WEIGHTS.items())
    overall = round(overall, 2)

    rating = "At Risk"
    for low, high, label in RATING_BANDS:
        if low <= overall <= high:
            rating = label
            break

    return overall, rating


# ---------------------------------------------------------------------------
# 2.5 — Cognitive age (rebased expected-score-by-age curve)
# ---------------------------------------------------------------------------

def compute_cognitive_age_v2(age: int, overall_score: float) -> CognitiveAgeV2Result:
    if age < COGNITIVE_AGE_MIN_AGE:
        return CognitiveAgeV2Result(
            actualAge=age, estimatedCognitiveAge=None, ageLow=None, ageHigh=None,
        )

    deviation = overall_score - expected_score(age)
    cognitive_age = age - (deviation / 2.5)
    cognitive_age = _clamp(cognitive_age, 18, 80)

    return CognitiveAgeV2Result(
        actualAge=age,
        estimatedCognitiveAge=int(round(cognitive_age)),
        ageLow=int(round(_clamp(cognitive_age - 3, 18, 80))),
        ageHigh=int(round(_clamp(cognitive_age + 3, 18, 80))),
    )


# ---------------------------------------------------------------------------
# 2.6 — Percentile (provisional, normal CDF via math.erf — no scipy)
# ---------------------------------------------------------------------------

def compute_percentile_v2(age: int, overall_score: float) -> PercentileV2Result:
    mean = expected_score(age)
    std = SCALE_SD
    z = (overall_score - mean) / std
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    pct = int(round(cdf * 100))
    pct = max(1, min(99, pct))
    return PercentileV2Result(value=pct)


# ---------------------------------------------------------------------------
# 2.7 — Response validity checks
# ---------------------------------------------------------------------------

STRAIGHT_LINE_SLACK = 2  # "all 28 identical, or >= 26 of 28 identical" for a 28-item bank


def _straight_lining(parsed: dict[str, int]) -> bool:
    values = list(parsed.values())
    if not values:
        return False
    max_count = max(Counter(values).values())
    return (len(values) - max_count) <= STRAIGHT_LINE_SLACK


def _extreme_responding(parsed: dict[str, int]) -> bool:
    values = list(parsed.values())
    if not values:
        return False
    return all(v == 0 for v in values) or all(v == 4 for v in values)


def _speed_floor(elapsed_seconds: Optional[int]) -> bool:
    if elapsed_seconds is None:
        return False
    return elapsed_seconds < 90


def _reverse_inconsistency(parsed: dict[str, int], reverse_item_ids: Optional[list[str]]) -> bool:
    """Flags a scale where reverse-coded items contradict forward-coded items
    by more than 2 scale points (0-4 scale, so inverted via 4 - value)."""
    if not reverse_item_ids:
        return False
    reverse_set = set(reverse_item_ids)

    for sid in SECTION_IDS:
        item_keys = [f"{sid}_Q{i}" for i in range(1, ITEMS_PER_SECTION + 1)]
        forward_vals = [parsed[k] for k in item_keys if k in parsed and k not in reverse_set]
        reverse_vals = [4 - parsed[k] for k in item_keys if k in parsed and k in reverse_set]
        if forward_vals and reverse_vals:
            forward_avg = sum(forward_vals) / len(forward_vals)
            reverse_avg = sum(reverse_vals) / len(reverse_vals)
            if abs(forward_avg - reverse_avg) > 2:
                return True

    return False


def check_response_validity(
    parsed: dict[str, int],
    elapsed_seconds: Optional[int] = None,
    reverse_item_ids: Optional[list[str]] = None,
) -> dict:
    flags = []
    if _straight_lining(parsed):
        flags.append("straight_lining")
    if _extreme_responding(parsed):
        flags.append("extreme_responding")
    if _speed_floor(elapsed_seconds):
        flags.append("speed_floor")
    if _reverse_inconsistency(parsed, reverse_item_ids):
        flags.append("reverse_inconsistency")

    if len(flags) == 0:
        status = "Valid"
    elif len(flags) == 1:
        status = "Review"
    else:
        status = "Low confidence"

    return {"status": status, "flags": flags}


# ---------------------------------------------------------------------------
# Strengths — NOT reused from v1.
#
# v1's compute_strengths() reads DomainScores, three of whose fields
# (processingSpeed, languageSkills, problemSolving, reactionTime) are
# fabricated proxies/hardcoded values — exactly the credibility problem v2
# exists to fix. Reusing it would leak fabricated "strengths" back into v2
# output, so v2 strengths are computed directly from the 7 real scales.
# ---------------------------------------------------------------------------

def compute_strengths_v2(scale_rounded: dict[str, float]) -> list[str]:
    return [
        SCALE_DISPLAY_NAMES[k] for k, v in scale_rounded.items() if v >= 80
    ]


# ---------------------------------------------------------------------------
# Lifestyle impacts / risk indicators — reused from v1 via shim dataclasses.
#
# Both v1 functions only read fields with a genuine v2 equivalent
# (sleep_recovery, stress_resilience, emotional_wellbeing,
# productivity_performance on SectionScores; attention_focus and memory on
# DomainScores). The remaining DomainScores fields have no v2 equivalent
# (v1 fabricated them) and are never read by these two functions — filled
# with the nearest real v2 scale purely to satisfy the dataclass shape.
#
# build_v1_shims is public (not module-private) because app/api/routes/analyze.py
# also needs it to call app.services.recommendations.build_recommendations(),
# which likewise only expects the SectionScores/DomainScores shape.
# ---------------------------------------------------------------------------

def build_v1_shims(scale_rounded: dict[str, float]) -> tuple[SectionScores, DomainScores]:
    section_scores = SectionScores(
        focus_attention=          scale_rounded["attentionFocus"],
        memory_function=          scale_rounded["memoryRecall"],
        mental_clarity=           scale_rounded["executiveFunction"],
        emotional_wellbeing=      scale_rounded["mentalEnergy"],
        stress_resilience=        scale_rounded["stressLoad"],
        sleep_recovery=           scale_rounded["sleepRecovery"],
        productivity_performance= scale_rounded["lifestyleModule"],
    )
    domain_scores = DomainScores(
        memory=             scale_rounded["memoryRecall"],
        attention_focus=    scale_rounded["attentionFocus"],
        executive_function= scale_rounded["executiveFunction"],
        # No v2 equivalent; unused by compute_lifestyle_impacts/compute_risk_indicators,
        # never surfaced in ScoringResultV2 — nearest real v2 scale used as filler only.
        processing_speed=   scale_rounded["mentalEnergy"],
        mental_clarity=     scale_rounded["executiveFunction"],
        language_skills=    scale_rounded["memoryRecall"],
        problem_solving=    scale_rounded["executiveFunction"],
        reaction_time=      scale_rounded["mentalEnergy"],
    )
    return section_scores, domain_scores


# ---------------------------------------------------------------------------
# 2.8 — Entry point
# ---------------------------------------------------------------------------

def score_v2(
    age: int,
    gender: str,
    responses: list[dict],
    elapsed_seconds: Optional[int] = None,
    reverse_item_ids: Optional[list[str]] = None,
) -> ScoringResultV2:
    if not (VALID_AGE_RANGE[0] <= age <= VALID_AGE_RANGE[1]):
        raise ValueError(
            f"Age {age} is outside supported range ({VALID_AGE_RANGE[0]}-{VALID_AGE_RANGE[1]})."
        )

    audit: dict = {}

    parsed, clamp_flags = parse_responses(responses)
    if clamp_flags:
        audit["clamped_values"] = clamp_flags

    averages, imputation_notes = compute_section_averages(parsed)
    if imputation_notes:
        audit["imputation_notes"] = imputation_notes

    insufficient = [sid for sid, avg in averages.items() if avg is None]
    if insufficient:
        audit["insufficient_sections"] = insufficient

    # Scales + composites
    scale_raw = compute_scale_scores_raw(averages)
    scales = ScalesV2Result(**{
        k: _apply_ci(v, SCALE_SD, SCALE_ALPHA) for k, v in scale_raw.items()
    })
    scale_rounded = {k: sc.score for k, sc in vars(scales).items()}

    composites_raw = compute_composites_raw(scale_rounded)
    composites = CompositesResult(**{
        k: _apply_ci(v, COMPOSITE_SD, COMPOSITE_ALPHA) for k, v in composites_raw.items()
    })

    # Overall + rating
    overall_score, rating = compute_overall_v2(scale_rounded)

    # Cognitive age + percentile
    cognitive_age = compute_cognitive_age_v2(age, overall_score)
    percentile = compute_percentile_v2(age, overall_score)

    # Lifestyle impacts + risk indicators (reused from v1 via shims)
    section_scores, domain_scores = build_v1_shims(scale_rounded)
    lifestyle_impacts = _v1_compute_lifestyle_impacts(section_scores)
    risk_indicators = _v1_compute_risk_indicators(section_scores, domain_scores, age, overall_score)

    # Strengths (v2-native, not reused — see comment above compute_strengths_v2)
    strengths = compute_strengths_v2(scale_rounded)

    # Validity
    validity_dict = check_response_validity(parsed, elapsed_seconds, reverse_item_ids)
    validity = ValidityResult(status=validity_dict["status"], flags=validity_dict["flags"])

    audit["rules_version"] = "2.0"
    audit["age_cohort"] = get_age_band(age)

    return ScoringResultV2(
        overall_score=     overall_score,
        rating=             rating,
        scales=             scales,
        composites=         composites,
        lifestyle_impacts=  lifestyle_impacts,
        risk_indicators=    risk_indicators,
        strengths=          strengths,
        cognitive_age=      cognitive_age,
        percentile=         percentile,
        validity=           validity,
        audit=              audit,
    )
