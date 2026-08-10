
from datetime import datetime
from app.scoring.engine import get_age_band
from app.core.config import settings
from app.scoring.engine_v2 import SCALE_WEIGHTS

# ============================================================
# v2 additive helpers (Phase 4) — report_mapper computes,
# pdf_service.py only draws. None of this changes any existing
# key in the dict returned by transform_analysis_to_report(); it
# only adds new keys that are empty/None when v2 data is absent,
# so v1 (or v2 with a flag off) output is unaffected.
# ============================================================

V2_SCALE_DISPLAY_NAMES = {
    "attentionFocus":    "Attention & Focus",
    "memoryRecall":       "Memory & Recall",
    "executiveFunction":  "Executive Function",
    "mentalEnergy":       "Mental Energy",
    "stressLoad":         "Stress & Emotional Load",
    "sleepRecovery":      "Sleep & Recovery",
    "lifestyleModule":    "Lifestyle Module",
}

_LEGACY_DOMAIN_DISPLAY = {
    "memory": "Memory", "attentionFocus": "Attention",
    "processingSpeed": "Processing", "executiveFunction": "Executive",
    "mentalClarity": "Clarity", "languageSkills": "Language",
    "problemSolving": "Problem Solving", "reactionTime": "Reaction Time",
}

_COMPOSITE_DISPLAY = {
    "cognitiveComplaintIndex": "Cognitive Complaint Index",
    "modifiableLoadIndex":     "Modifiable Load Index",
    "overall":                  "Overall Score",
}

# ---------------------------------------------------------------------------
# Concept -> label resolution.
#
# The narrative generators (root causes, risk prediction, projections) refer to
# cognitive concepts by name. Those names differ between the two vocabularies,
# so each generator takes a label map instead of hardcoding strings. v1 keeps
# the exact legacy labels, which is what makes v1 output byte-identical.
#
# Under v2, "clarity" resolves to Executive Function: v1's Mental Clarity was
# the S3 section, which v2 reports as Executive Function. "processing" maps to
# Mental Energy — v1's Processing Speed was a fabricated Mental Clarity x 0.9
# proxy, so Mental Energy is the nearest scale that measures anything real.
# ---------------------------------------------------------------------------

CONCEPT_LABELS_V1 = {
    "memory":     "Memory",
    "attention":  "Attention",
    "executive":  "Executive",
    "clarity":    "Clarity",
    "processing": "Processing",
}

CONCEPT_LABELS_V2 = {
    "memory":     "Memory & Recall",
    "attention":  "Attention & Focus",
    "executive":  "Executive Function",
    "clarity":    "Executive Function",
    "processing": "Mental Energy",
}

# Score-breakdown weights per vocabulary (v2 mirrors engine_v2.SCALE_WEIGHTS)
V2_BREAKDOWN_WEIGHTS = {
    V2_SCALE_DISPLAY_NAMES[k]: w for k, w in SCALE_WEIGHTS.items()
}

V2_STRENGTH_BADGES = {
    "Attention & Focus":       {"badge": "Focused Mind",         "icon": "🔍"},
    "Memory & Recall":         {"badge": "Sharp Memory",         "icon": "🧠"},
    "Executive Function":      {"badge": "Strategic Thinker",    "icon": "♟"},
    "Mental Energy":           {"badge": "High Mental Stamina",  "icon": "⚡"},
    "Stress & Emotional Load": {"badge": "Resilient Under Load", "icon": "🛡"},
    "Sleep & Recovery":        {"badge": "Well Recovered",       "icon": "🌙"},
    "Lifestyle Module":        {"badge": "Strong Daily Habits",  "icon": "🌱"},
}

V2_STRENGTH_DESCRIPTIONS = {
    "Attention & Focus":
        "Sustained attention holds up well against distraction during demanding tasks.",
    "Memory & Recall":
        "Retention and recall of recently learned information remain reliable.",
    "Executive Function":
        "Planning, decision-making, and cognitive flexibility remain balanced under complexity.",
    "Mental Energy":
        "Mental stamina is well maintained, with good resistance to cognitive fatigue.",
    "Stress & Emotional Load":
        "Stress burden is well managed and is not meaningfully impairing daily functioning.",
    "Sleep & Recovery":
        "Sleep quality is supporting effective next-day cognitive recovery.",
    "Lifestyle Module":
        "Daily routines and recovery habits are actively supporting cognitive wellness.",
}


def _v2_radar_and_confidence(analysis: dict, domains: dict) -> tuple[dict, dict]:
    """Item 1 (radar) + item 2 (scale bars) source data.

    radar_domains: label -> score. 7 real v2 scales when v2 is active,
    otherwise the same legacy 8-domain dict already used today (so the
    radar chart / brain performance bars render identically when v1).

    scale_confidence: label -> {sem, ciLow, ciHigh}. Only populated when
    v2 is active AND ENABLE_CONFIDENCE_INTERVALS is on — empty otherwise,
    which is what keeps the scale-bar drawing unchanged by default.
    """
    scales = analysis.get("scales")
    if analysis.get("modelVersion") != "v2" or not scales:
        return domains, {}

    radar_domains = {
        V2_SCALE_DISPLAY_NAMES[k]: scales[k]["score"] for k in V2_SCALE_DISPLAY_NAMES
    }

    scale_confidence = {}
    if settings.ENABLE_CONFIDENCE_INTERVALS:
        scale_confidence = {
            V2_SCALE_DISPLAY_NAMES[k]: {
                "sem": scales[k]["sem"], "ciLow": scales[k]["ciLow"], "ciHigh": scales[k]["ciHigh"],
            }
            for k in V2_SCALE_DISPLAY_NAMES
        }

    return radar_domains, scale_confidence


def _cognitive_age_range(analysis: dict) -> dict | None:
    """Item 3 — Cognitive Age page range + provisional footnote."""
    cog_v2 = analysis.get("cognitiveAgeV2")
    if not cog_v2 or cog_v2.get("ageLow") is None or cog_v2.get("ageHigh") is None:
        return None
    return {
        "low":  cog_v2["ageLow"],
        "high": cog_v2["ageHigh"],
        "disclaimer": cog_v2.get("disclaimer", ""),
    }


def _progress_table(analysis: dict) -> dict | None:
    """Item 4 — Progress page data. Only built when Phase 5's reliable-change
    data is actually present (two-point RCI requires v2 + SEM on both the
    current and prior report) — the PDF only ever adds the new page when
    there is real reliable-change data to show, never speculatively."""
    reliable_change = analysis.get("reliableChange")
    if not reliable_change:
        return None

    deltas = (analysis.get("progress") or {}).get("deltas") or []
    domain_rows = [
        {
            "domain":      _LEGACY_DOMAIN_DISPLAY.get(d["domain"], d["domain"]),
            "previous":    d["previous"],
            "current":     d["current"],
            "delta":       d["delta"],
            # 4-item scales are noisy — only the 12-item composites/overall
            # below get a formal reliable-change verdict (see Phase 5 note).
            "reliability": "Directional only",
        }
        for d in deltas
    ]

    composite_rows = []
    for key, label in _COMPOSITE_DISPLAY.items():
        entry = reliable_change.get(key)
        if entry:
            composite_rows.append({
                "domain": label,
                "delta":  entry["delta"],
                "rci":    entry["rci"],
                "flag":   entry["flag"],
            })

    if not domain_rows and not composite_rows:
        return None

    return {"domain_rows": domain_rows, "composite_rows": composite_rows}


SCALE_DESCRIPTIONS = {
    "attentionFocus":    "Sustained attention and resistance to distraction during demanding tasks.",
    "memoryRecall":       "Short-term retention and recall of recently learned information.",
    "executiveFunction":  "Planning, decision-making, and cognitive flexibility under complexity.",
    "mentalEnergy":       "Subjective mental stamina and resistance to cognitive fatigue.",
    "stressLoad":         "Self-reported stress burden and its perceived impact on daily functioning.",
    "sleepRecovery":      "Sleep quality and its contribution to next-day cognitive recovery.",
    "lifestyleModule":    "Broader lifestyle factors (activity, routine, recovery habits) linked to wellness.",
}


def _methodology(analysis: dict) -> dict | None:
    """Optional methodology page (Phase 4) source data — v2 only."""
    if analysis.get("modelVersion") != "v2":
        return None
    return {
        "item_bank_version": settings.ITEM_BANK_VERSION,
        "scales": [
            {
                "name":        V2_SCALE_DISPLAY_NAMES[k],
                "description": SCALE_DESCRIPTIONS[k],
                "weight_pct":  round(SCALE_WEIGHTS[k] * 100),
            }
            for k in V2_SCALE_DISPLAY_NAMES
        ],
    }


def transform_analysis_to_report(analysis: dict) -> dict:

    domains = {
        "Memory": analysis["domains"]["memory"],
        "Attention": analysis["domains"]["attentionFocus"],
        "Processing": analysis["domains"]["processingSpeed"],
        "Executive": analysis["domains"]["executiveFunction"],
        "Clarity": analysis["domains"]["mentalClarity"],
        "Language": analysis["domains"]["languageSkills"],
        "Problem Solving": analysis["domains"]["problemSolving"],
        "Reaction Time": analysis["domains"]["reactionTime"],
    }

    radar_domains, scale_confidence = _v2_radar_and_confidence(analysis, domains)
    validity_status     = (analysis.get("validity") or {}).get("status")
    cognitive_age_range = _cognitive_age_range(analysis)
    progress_table       = _progress_table(analysis)
    methodology          = _methodology(analysis)

    # `active` is the vocabulary the whole report narrates: the 7 real v2
    # scales when v2 is on, otherwise the legacy 8 domains. Under v1
    # _v2_radar_and_confidence returns the `domains` dict itself, so every
    # downstream generator receives exactly what it received before and v1
    # output stays byte-identical.
    is_v2   = analysis.get("modelVersion") == "v2"
    active  = radar_domains
    labels  = CONCEPT_LABELS_V2 if is_v2 else CONCEPT_LABELS_V1
    weights = V2_BREAKDOWN_WEIGHTS if is_v2 else None

    # ============================================================
    # Helpers
    # ============================================================

    def format_gender_display(value):

        labels = {
            "male": "Male",
            "female": "Female",
            "other": "Other",
            "prefer-not-to-say": "Prefer Not to Say",
        }

        return labels.get((value or "").lower(), "Not Specified")

    def impact_to_score(value: str) -> int:

        mapping = {
            "Low": 85,
            "Medium":50,
            "Moderate": 60,
            "High": 30,
            "Very High": 15,
        }

        return mapping.get(value, 50)

    # ============================================================
    # Lifestyle
    # ============================================================

    lifestyle = {
        "Sleep": impact_to_score(
            analysis["lifestyleImpacts"]["sleepQualityImpact"]
        ),

        "Stress": impact_to_score(
            analysis["lifestyleImpacts"]["stressLevelImpact"]
        ),

        "Anxiety": impact_to_score(
            analysis["lifestyleImpacts"]["anxietyLoadImpact"]
        ),

        "Burnout": impact_to_score(
            analysis["lifestyleImpacts"]["burnoutRiskImpact"]
        ),
    }

    # ============================================================
    # Top strengths
    # ============================================================
    STRENGTH_BADGES = {
    "Reaction Time":   {"badge": "Fast Thinker",              "icon": "⚡"},
    "Language":        {"badge": "Strong Verbal Processing",   "icon": "📚"},
    "Problem Solving": {"badge": "Above-Avg Problem Solver",   "icon": "🎯"},
    "Memory":          {"badge": "Sharp Memory",               "icon": "🧠"},
    "Attention":       {"badge": "Focused Mind",               "icon": "🔍"},
    "Executive":       {"badge": "Strategic Thinker",          "icon": "♟"},
    "Processing":      {"badge": "Quick Processor",            "icon": "⚙"},
    "Clarity":         {"badge": "Clear Thinker",              "icon": "💡"},
    }
    if is_v2:
        STRENGTH_BADGES = V2_STRENGTH_BADGES

    sorted_domains = sorted(
        active.items(),
        key=lambda x: x[1],
        reverse=True
    )

    strengths = []

    for name, score in sorted_domains[:3]:
        badge_info = STRENGTH_BADGES.get(name, {"badge": name, "icon": "★"})
        strengths.append({
            "title":       name,
            "score":       score,
            "description": generate_strength_description(name),
            "badge":       badge_info["badge"],
            "icon":        badge_info["icon"],
        })
    # ============================================================
    # Executive Summary
    # ============================================================

    executive_summary = {
        "summary": generate_summary(analysis),

        "key_findings": analysis["riskIndicators"][:6],

        "priority_areas": [
            name for name, value in sorted_domains[-4:]
        ],

        "strongest_areas": [
            name for name, value in sorted_domains[:3]
        ],
    }

    # ============================================================
    # AI Insights
    # ============================================================

    ai_insights = {
        "analysis": generate_ai_analysis(analysis),

        "behavioral_insights":
            analysis["riskIndicators"][:4],

        "potential_causes":
            analysis["recommendations"][:4],

        "improvement_projection":
            generate_projection(active,analysis["cognitiveAge"]["actualAge"],labels)
    }

    # ============================================================
    # Wellness Indicators
    # ============================================================

    wellness_indicators = []

    for item in analysis["riskIndicators"]:

        wellness_indicators.append({
            "title": item,
            "description": generate_indicator_description(item)
        })

    # ============================================================
    # Roadmap
    # ============================================================

    roadmap = generate_roadmap(
        analysis["recommendations"]
    )

    # ===========================================================
    # Cognitive age
    # ===========================================================
    age        = analysis["cognitiveAge"]["actualAge"]
    est_age    = analysis["cognitiveAge"].get("estimatedCognitiveAge")
    
    # ============================================================
    # Final Report Structure
    # ============================================================

    return {

        "report_id": analysis["assessmentId"],

        "overall_score":
            analysis["overall"]["score"],

        "risk_level":
            analysis["overall"]["rating"],

        "user": {
            "name": analysis.get("name") or "Assessment User",
            "age": analysis["cognitiveAge"]["actualAge"],
            "gender": format_gender_display(analysis.get("gender")),
            "band": get_age_band(analysis["cognitiveAge"]["actualAge"]),
            "cognitive_age_display": get_cognitive_age_display(
                age=analysis["cognitiveAge"]["actualAge"],
                estimated=analysis["cognitiveAge"].get("estimatedCognitiveAge"),
                overall_score=analysis["overall"]["score"],
            ),
            "cognitive_age_message": get_cognitive_age_message(
                age=analysis["cognitiveAge"]["actualAge"],
                estimated=analysis["cognitiveAge"].get("estimatedCognitiveAge"),
                overall_score=analysis["overall"]["score"],
            ),
            "assessment_date":
                datetime.now().strftime("%d %B %Y"),
        },

        "domains": domains,

        "score_breakdown": generate_score_breakdown(active, weights),
        "traffic_light":   generate_traffic_light(active),
        "lifestyle": lifestyle,

        "root_causes": generate_root_causes(lifestyle, active, labels),

        "benchmarks": generate_benchmarks(
            age=analysis["cognitiveAge"]["actualAge"],
            gender=analysis.get("gender", "female"),
            overall_score=analysis["overall"]["score"],
        ),
        "risk_prediction": generate_risk_prediction(
            lifestyle=lifestyle,
            domains=active,
            overall_score=analysis["overall"]["score"],
            age=analysis["cognitiveAge"]["actualAge"],
            labels=labels,
        ),
        "executive_summary": executive_summary,

        "ai_insights": ai_insights,

        "wellness_indicators": wellness_indicators,

        "strengths": strengths,

        "roadmap": roadmap,

        "cognitive_age": generate_cognitive_age_section(age, est_age),

        # --- v2 additive keys (Phase 4) — all None/empty unless v2 data is
        # present, so v1 output (and v2 with flags off) is unaffected ---
        "model_version":       analysis.get("modelVersion", "v1"),
        "radar_domains":      radar_domains,
        "scale_confidence":   scale_confidence,
        "validity_status":    validity_status,
        "cognitive_age_range": cognitive_age_range,
        "progress_table":      progress_table,
        "methodology":         methodology,

        "legal": {
            "disclaimer":
                analysis["disclaimers"][0],

            "privacy":
                analysis["privacy"]["storagePolicy"],

            "hipaa":
                analysis["privacy"]["hipaaNote"],

            "contact":
                "support@limitless.ai",
        },
    }


# ================================================================
# HELPERS
# ================================================================
def get_cognitive_age_display(age, estimated, overall_score):

    if estimated is not None:
        return int(estimated)

    if age < 43:

        if overall_score >= 85:

            return age - 3

        elif overall_score >= 70:
        
            return age

        elif overall_score >= 50:
        
            return age + 3

        else:
        
            return age + 6

    return age
def get_cognitive_age_message(age, estimated, overall_score):
    if estimated is not None:
        diff = age - estimated
        if diff > 0:
            return f"Brain functioning {diff} years ahead of expectations ✅"
        elif diff == 0:
            return "Brain functioning matches age expectations"
        else:
            return f"Brain performance appears {abs(diff)} years older than expected ⚠️"
    if age < 43:
        if overall_score >= 85:
            return "Cognitive performance exceeds age expectations ✅"
        elif overall_score >= 70:
            return "Cognitive performance is on track for your age"
        elif overall_score >= 50:
            return "Cognitive performance may benefit from targeted improvement ⚠️"
        else:
            return "Cognitive performance requires attention ⚠️"
    return ""

BENCHMARKS = {
    "young_adult":            {"female": (65, 88), "male": (63, 86)},
    "emerging_professional":  {"female": (62, 85), "male": (60, 84)},
    "established_adult":      {"female": (60, 83), "male": (58, 82)},
    "mid_career":             {"female": (57, 80), "male": (55, 79)},
    "midlife_transition":     {"female": (54, 78), "male": (52, 77)},
    "pre_senior":             {"female": (51, 75), "male": (49, 73)},
    "senior_adult":           {"female": (48, 71), "male": (46, 70)},
}

def generate_benchmarks(age: int, gender: str, overall_score: float) -> dict:
    """
    Peer benchmarks for the user's age band.

    The report shows BOTH the female and male cohort averages side by side
    rather than silently picking one by the user's gender, so the comparison
    is not framed around a single cohort.

    The percentile is still computed against the user's own cohort (that is
    what makes it a meaningful "where do I sit" number); non-binary and
    prefer-not-to-say are scored against the mean of both cohorts.
    """
    band = get_age_band(age)

    female_avg, female_top = BENCHMARKS[band]["female"]
    male_avg,   male_top   = BENCHMARKS[band]["male"]

    gender_key = (gender or "").lower()

    if gender_key in ("male", "female"):
        peer_avg, top_10 = BENCHMARKS[band][gender_key]
        cohort_label = gender_key.capitalize()
    else:
        # Non-binary / prefer-not-to-say -> mean of both cohorts.
        # (The original code intended this but the branch was unreachable:
        # gender_key had already been coerced to "female" on the line above,
        # so these users were silently scored against female benchmarks.)
        peer_avg = int((male_avg + female_avg) / 2)
        top_10   = int((male_top + female_top) / 2)
        cohort_label = "All genders"

    # Compute rough percentile
    if overall_score >= top_10:
        percentile = 95
    elif overall_score >= peer_avg:
        # Linear interpolation between peer_avg (50th) and top_10 (90th)
        pct_range = top_10 - peer_avg
        if pct_range > 0:
            percentile = int(50 + 40 * (overall_score - peer_avg) / pct_range)
        else:
            percentile = 50
    else:
        # Below average — interpolate between 10th and 50th
        if peer_avg > 0:
            percentile = int(10 + 40 * (overall_score / peer_avg))
        else:
            percentile = 10

    percentile = max(5, min(99, percentile))

    band_labels = {
        "young_adult":            "Young Adults (18–25)",
        "emerging_professional":  "Emerging Professionals (26–32)",
        "established_adult":      "Established Adults (33–37)",
        "mid_career":             "Mid-Career Adults (38–42)",
        "midlife_transition":     "Midlife Adults (43–47)",
        "pre_senior":             "Pre-Senior Adults (48–55)",
        "senior_adult":           "Senior Adults (56–66)",
    }

    return {
        "user_score":   int(overall_score),
        # Cohort used for the percentile maths (user's own gender, or the
        # mean of both for non-binary / prefer-not-to-say).
        "peer_average": peer_avg,
        "top_10_pct":   top_10,
        "percentile":   percentile,
        # Both cohort averages, shown side by side in the report.
        "peer_average_female": female_avg,
        "peer_average_male":   male_avg,
        "band_label":   band_labels.get(band, "Your Age Group"),
        "cohort_label": cohort_label,
        # Retained for backward compatibility with any existing consumer;
        # the report no longer frames the comparison by gender.
        "gender_label": cohort_label,
    }
def generate_risk_prediction(
    lifestyle: dict,
    domains: dict,
    overall_score: float,
    age: int,
    labels: dict | None = None,
) -> dict:

    # labels=None keeps the legacy v1 vocabulary, so v1 output is unchanged.
    L = labels or CONCEPT_LABELS_V1
    NAME_MEMORY     = L["memory"]
    NAME_ATTENTION  = L["attention"]
    NAME_EXECUTIVE  = L["executive"]
    NAME_CLARITY    = L["clarity"]
    NAME_PROCESSING = L["processing"]

    band = get_age_band(age)

    projection_boost = {
        "young_adult":            22,
        "emerging_professional":  20,
        "established_adult":      18,
        "mid_career":             16,
        "midlife_transition":     14,
        "pre_senior":             12,
        "senior_adult":           10,
    }.get(band, 15)

    # ── Scenario A — No action taken ──
    no_action_declines = []

    if lifestyle.get("Sleep", 100) <= 30:
        no_action_declines.append({
            "domain":      NAME_MEMORY,
            "current":     int(domains.get(NAME_MEMORY, 0)),
            "projected":   max(0, int(domains.get(NAME_MEMORY, 0)) - 10),
            "decline_pct": 12,
        })
        no_action_declines.append({
            "domain":      NAME_ATTENTION,
            "current":     int(domains.get(NAME_ATTENTION, 0)),
            "projected":   max(0, int(domains.get(NAME_ATTENTION, 0)) - 8),
            "decline_pct": 8,
        })
    elif lifestyle.get("Sleep", 100) <= 60:
        no_action_declines.append({
            "domain":      NAME_MEMORY,
            "current":     int(domains.get(NAME_MEMORY, 0)),
            "projected":   max(0, int(domains.get(NAME_MEMORY, 0)) - 6),
            "decline_pct": 8,
        })

    if lifestyle.get("Stress", 100) <= 30:
        no_action_declines.append({
            "domain":      NAME_ATTENTION,
            "current":     int(domains.get(NAME_ATTENTION, 0)),
            "projected":   max(0, int(domains.get(NAME_ATTENTION, 0)) - 10),
            "decline_pct": 12,
        })
        no_action_declines.append({
            "domain":      NAME_EXECUTIVE,
            "current":     int(domains.get(NAME_EXECUTIVE, 0)),
            "projected":   max(0, int(domains.get(NAME_EXECUTIVE, 0)) - 7),
            "decline_pct": 8,
        })
    elif lifestyle.get("Stress", 100) <= 60:
        no_action_declines.append({
            "domain":      NAME_ATTENTION,
            "current":     int(domains.get(NAME_ATTENTION, 0)),
            "projected":   max(0, int(domains.get(NAME_ATTENTION, 0)) - 6),
            "decline_pct": 8,
        })

    if lifestyle.get("Anxiety", 100) <= 30:
        no_action_declines.append({
            "domain":      NAME_CLARITY,
            "current":     int(domains.get(NAME_CLARITY, 0)),
            "projected":   max(0, int(domains.get(NAME_CLARITY, 0)) - 8),
            "decline_pct": 10,
        })

    if lifestyle.get("Burnout", 100) <= 30:
        no_action_declines.append({
            "domain":      NAME_PROCESSING,
            "current":     int(domains.get(NAME_PROCESSING, 0)),
            "projected":   max(0, int(domains.get(NAME_PROCESSING, 0)) - 12),
            "decline_pct": 15,
        })

    # Deduplicate by domain — keep worst decline
    seen = {}
    for item in no_action_declines:
        d = item["domain"]
        if d not in seen or item["decline_pct"] > seen[d]["decline_pct"]:
            seen[d] = item
    no_action_declines = sorted(
        seen.values(),
        key=lambda x: x["decline_pct"],
        reverse=True,
    )[:3]

    # Overall score decline
    overall_decline_30  = max(0, round(overall_score * 0.92, 1))
    overall_decline_90  = max(0, round(overall_score * 0.85, 1))

    # Burnout risk
    burnout_score = lifestyle.get("Burnout", 100)
    if burnout_score <= 30:
        burnout_statement = "Burnout risk may increase significantly without intervention"
    elif burnout_score <= 60:
        burnout_statement = "Burnout risk is present and may worsen without recovery habits"
    else:
        burnout_statement = "Burnout risk remains manageable with current habits"

    # ── Scenario B — Recommendations followed ──
    score_30  = min(100, round(overall_score + projection_boost * 0.5, 1))
    score_90  = min(100, round(overall_score + projection_boost * 1.0
                               + (100 - overall_score) * 0.08, 1))

    # Top 3 domains that will improve most
    improvement_domains = sorted(
        domains.items(),
        key=lambda x: x[1],
    )[:3]

    with_action_gains = []
    for domain_name, current_val in improvement_domains:
        projected_val = min(100, int(current_val) + projection_boost)
        gain_pts      = projected_val - int(current_val)
        gain_pct      = round((gain_pts / max(current_val, 1)) * 100, 1)
        with_action_gains.append({
            "domain":       domain_name,
            "current":      int(current_val),
            "projected_30": min(100, int(current_val) + int(projection_boost * 0.5)),
            "projected_90": projected_val,
            "gain_pts":     gain_pts,
            "gain_pct":     gain_pct,
        })

    return {
        "no_action": {
            "overall_30_days":    overall_decline_30,
            "overall_90_days":    overall_decline_90,
            "domain_declines":    no_action_declines,
            "burnout_statement":  burnout_statement,
        },
        "with_action": {
            "overall_30_days":    score_30,
            "overall_90_days":    score_90,
            "domain_gains":       with_action_gains,
        },
    }

def generate_summary(analysis):

    score = analysis["overall"]["score"]

    if score >= 80:
        level = "strong overall cognitive wellness"

    elif score >= 60:
        level = "moderate cognitive performance"

    else:
        level = "areas requiring cognitive improvement"

    return (
        f"The assessment indicates {level}. "
        f"Lifestyle factors including stress, sleep quality, "
        f"and recovery patterns appear to influence performance."
    )
def generate_cognitive_age_section(age: int, est_age):

    completed = [
        "Cognitive Wellness Score",
        "Lifestyle Analysis",
        "Wellness Indicators",
    ]

    upcoming = [
        "Cognitive Age Calibration",
        "Predictive Cognitive Tracking",
        "Longitudinal Trend Analysis",
    ]

    if age < 43:
        return {
            "status":   "Cognitive Age Tracking Not Yet Active",
            "subtitle": f"Activates at age 43 — you are currently {age}",
            "note":     "At your life stage, developmental wellness tracking applies.",
            "completed": completed,
            "upcoming":  upcoming,
        }

    if est_age is not None:
        diff = age - est_age
        direction = "younger" if diff > 0 else "older"
        return {
            "status":   f"Estimated Cognitive Age: {est_age}",
            "subtitle": f"Actual Age: {age}  •  {abs(diff)} years {direction} cognitively",
            "note":     "Motivational wellness metric only — not a clinical measurement.",
            "completed": completed,
            "upcoming":  upcoming,
        }

    # 43+ but no estimate yet (safety fallback)
    return {
        "status":   "Calibration in Progress",
        "subtitle": "Complete more assessments to establish your baseline",
        "note":     "Feature activates with longitudinal data.",
        "completed": completed,
        "upcoming":  upcoming,
    }

def generate_ai_analysis(analysis):

    return (
        "The primary factors affecting cognitive performance "
        "appear to be attention regulation, stress load, "
        "and recovery quality. Addressing these areas "
        "simultaneously may produce measurable improvement."
    )
def generate_traffic_light(domains: dict) -> dict:
    green  = []  # >= 75
    yellow = []  # 50–74
    red    = []  # < 50

    for domain, score in domains.items():
        if score >= 75:
            green.append({"domain": domain, "score": score})
        elif score >= 50:
            yellow.append({"domain": domain, "score": score})
        else:
            red.append({"domain": domain, "score": score})

    # Sort each group by score descending
    green.sort(key=lambda x: -x["score"])
    yellow.sort(key=lambda x: -x["score"])
    red.sort(key=lambda x: -x["score"])

    return {
        "green":  green,
        "yellow": yellow,
        "red":    red,
    }

def generate_strength_description(name):

    descriptions = {

        "Reaction Time":
            "Fast processing and response speed remain a significant strength.",

        "Language":
            "Strong verbal reasoning and comprehension abilities detected.",

        "Problem Solving":
            "Analytical reasoning and logical thinking remain above average.",

        "Memory":
            "Information retention and recall abilities remain stable.",

        "Attention":
            "Focus regulation appears resilient during demanding tasks.",

        "Executive":
            "Planning and decision-making capabilities remain balanced.",

        "Processing":
            "Information processing speed appears efficient.",

        "Clarity":
            "Mental clarity and cognitive sharpness remain stable.",
    }

    # v2 scale names fall through to the v2 table; unknown names to the default.
    return descriptions.get(
        name,
        V2_STRENGTH_DESCRIPTIONS.get(
            name,
            "Performance in this domain remains stable."
        )
    )


def generate_indicator_description(item):

    return (
        f"{item} appears to be contributing to reduced "
        f"cognitive efficiency and wellness patterns."
    )


def generate_projection(domains,age,labels=None):

    projection = {}

    # labels=None keeps the legacy v1 vocabulary, so v1 output is unchanged.
    # dict.fromkeys de-duplicates while preserving order: under v2 "clarity"
    # and "executive" both resolve to Executive Function.
    L = labels or CONCEPT_LABELS_V1
    target_domains = list(dict.fromkeys([
        L["memory"],
        L["attention"],
        L["clarity"],
    ]))
    band = get_age_band(age)
    boost = {
        "young_adult":            22,
        "emerging_professional":  20,
        "established_adult":      18,
        "mid_career":             16,
        "midlife_transition":     14,
        "pre_senior":             12,
        "senior_adult":           10,
    }.get(band, 15)
    for domain in target_domains:

        current = domains[domain]

        projected = min(current + boost, 100)

        projection[domain] = {
            "current": current,
            "projected": projected
        }

    return projection

def generate_root_causes(lifestyle: dict, domains: dict, labels: dict | None = None) -> list:

    # labels=None keeps the legacy v1 vocabulary, so v1 output is unchanged.
    L = labels or CONCEPT_LABELS_V1
    candidates = []

    # Lifestyle-based causes
    if lifestyle.get("Sleep", 100) <= 30:
        candidates.append({
            "factor":      "Poor sleep quality",
            "impact_pct":  42,
            "description": "Sleep deprivation directly reduces memory consolidation and attention span.",
        })
    elif lifestyle.get("Sleep", 100) <= 60:
        candidates.append({
            "factor":      "Disrupted sleep patterns",
            "impact_pct":  32,
            "description": "Inconsistent sleep is reducing cognitive recovery and mental clarity.",
        })

    if lifestyle.get("Stress", 100) <= 30:
        candidates.append({
            "factor":      "Elevated stress load",
            "impact_pct":  35,
            "description": "High cortisol levels are impairing working memory and executive function.",
        })
    elif lifestyle.get("Stress", 100) <= 60:
        candidates.append({
            "factor":      "Moderate stress burden",
            "impact_pct":  22,
            "description": "Ongoing stress is consuming cognitive resources needed for focus.",
        })

    if lifestyle.get("Anxiety", 100) <= 30:
        candidates.append({
            "factor":      "High anxiety burden",
            "impact_pct":  28,
            "description": "Anxiety is diverting attentional resources and creating cognitive bottlenecks.",
        })
    elif lifestyle.get("Anxiety", 100) <= 60:
        candidates.append({
            "factor":      "Moderate anxiety levels",
            "impact_pct":  18,
            "description": "Anxiety is creating intermittent interference during demanding tasks.",
        })

    if lifestyle.get("Burnout", 100) <= 30:
        candidates.append({
            "factor":      "Cognitive overload / burnout",
            "impact_pct":  30,
            "description": "Sustained overload is depleting mental reserves and reducing motivation.",
        })

    # Domain-based causes
    if domains.get(L["memory"], 100) < 50:
        candidates.append({
            "factor":      "Memory consolidation deficit",
            "impact_pct":  20,
            "description": "Low memory scores suggest difficulty encoding and retrieving information.",
        })

    if domains.get(L["attention"], 100) < 50:
        candidates.append({
            "factor":      "Sustained attention difficulty",
            "impact_pct":  18,
            "description": "Attention scores indicate difficulty maintaining focus on demanding tasks.",
        })

    if domains.get(L["clarity"], 100) < 50:
        candidates.append({
            "factor":      "Reduced mental clarity",
            "impact_pct":  15,
            "description": "Brain fog is slowing decision-making and information processing.",
        })

    # Sort by impact descending, take top 4
    candidates.sort(key=lambda x: x["impact_pct"], reverse=True)

    # Re-assign impact percentages to top 4 so they feel credible
    pct_tiers = [40, 28, 18, 10]
    for i, item in enumerate(candidates[:4]):
        item["impact_pct"] = pct_tiers[i]

    return candidates[:4]
def generate_roadmap(recommendations):

    weeks = [
        "Week 1",
        "Week 2",
        "Week 3",
        "Week 4"
    ]

    focuses = [
        "Recovery Optimization",
        "Attention Training",
        "Stress Regulation",
        "Performance Reinforcement"
    ]

    roadmap = []

    for i in range(4):

        tasks = recommendations[i:i+3]

        if not tasks:
            tasks = [
                "Daily wellness practice",
                "Track cognitive performance",
                "Maintain recovery consistency"
            ]

        roadmap.append({
            "week": weeks[i],
            "focus": focuses[i],
            "tasks": tasks
        })

    return roadmap
def generate_score_breakdown(domains, weights=None):

    # weights=None keeps the legacy v1 domain weights, so v1 output is unchanged.
    weights = weights or {
        "Memory":        0.20,
        "Attention":     0.20,
        "Processing":    0.15,
        "Executive":     0.15,
        "Clarity":       0.10,
        "Language":      0.05,
        "Problem Solving": 0.05,
        "Reaction Time": 0.05,
    }

    breakdown = []

    for domain, weight in weights.items():
        score        = domains.get(domain, 0)
        contribution = round(weight * score, 1)
        breakdown.append({
            "domain":       domain,
            "weight_pct":   int(weight * 100),
            "score":        score,
            "contribution": contribution,
        })

    return sorted(breakdown, key=lambda x: x["weight_pct"], reverse=True)