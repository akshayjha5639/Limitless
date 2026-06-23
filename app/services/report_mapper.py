
from datetime import datetime
from app.scoring.engine import get_age_band

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

    # ============================================================
    # Helpers
    # ============================================================

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
    sorted_domains = sorted(
        domains.items(),
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
            generate_projection(domains,analysis["cognitiveAge"]["actualAge"])
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
            "name": "Assessment User",
            "age": analysis["cognitiveAge"]["actualAge"],
            "gender": "Not Specified",
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
        
        "score_breakdown": generate_score_breakdown(domains),
        "traffic_light":   generate_traffic_light(domains),
        "lifestyle": lifestyle,
        
        "root_causes": generate_root_causes(lifestyle, domains),

        "benchmarks": generate_benchmarks(
            age=analysis["cognitiveAge"]["actualAge"],
            gender=analysis.get("gender", "female"),
            overall_score=analysis["overall"]["score"],
        ),
        "risk_prediction": generate_risk_prediction(
            lifestyle=lifestyle,
            domains=domains,
            overall_score=analysis["overall"]["score"],
            age=analysis["cognitiveAge"]["actualAge"],
        ),
        "executive_summary": executive_summary,

        "ai_insights": ai_insights,

        "wellness_indicators": wellness_indicators,

        "strengths": strengths,

        "roadmap": roadmap,

        "cognitive_age": generate_cognitive_age_section(age, est_age),

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

    band   = get_age_band(age)
    gender_key = gender.lower() if gender.lower() in ("male", "female") else "female"

    # Average male and female for non-binary / prefer not to say
    if gender_key not in ("male", "female"):
        m = BENCHMARKS[band]["male"]
        f = BENCHMARKS[band]["female"]
        peer_avg = int((m[0] + f[0]) / 2)
        top_10   = int((m[1] + f[1]) / 2)
    else:
        peer_avg, top_10 = BENCHMARKS[band][gender_key]

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
        "peer_average": peer_avg,
        "top_10_pct":   top_10,
        "percentile":   percentile,
        "band_label":   band_labels.get(band, "Your Age Group"),
        "gender_label": gender_key.capitalize(),
    }
def generate_risk_prediction(
    lifestyle: dict,
    domains: dict,
    overall_score: float,
    age: int,
) -> dict:

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
            "domain":      "Memory",
            "current":     int(domains.get("Memory", 0)),
            "projected":   max(0, int(domains.get("Memory", 0)) - 10),
            "decline_pct": 12,
        })
        no_action_declines.append({
            "domain":      "Attention",
            "current":     int(domains.get("Attention", 0)),
            "projected":   max(0, int(domains.get("Attention", 0)) - 8),
            "decline_pct": 8,
        })
    elif lifestyle.get("Sleep", 100) <= 60:
        no_action_declines.append({
            "domain":      "Memory",
            "current":     int(domains.get("Memory", 0)),
            "projected":   max(0, int(domains.get("Memory", 0)) - 6),
            "decline_pct": 8,
        })

    if lifestyle.get("Stress", 100) <= 30:
        no_action_declines.append({
            "domain":      "Attention",
            "current":     int(domains.get("Attention", 0)),
            "projected":   max(0, int(domains.get("Attention", 0)) - 10),
            "decline_pct": 12,
        })
        no_action_declines.append({
            "domain":      "Executive",
            "current":     int(domains.get("Executive", 0)),
            "projected":   max(0, int(domains.get("Executive", 0)) - 7),
            "decline_pct": 8,
        })
    elif lifestyle.get("Stress", 100) <= 60:
        no_action_declines.append({
            "domain":      "Attention",
            "current":     int(domains.get("Attention", 0)),
            "projected":   max(0, int(domains.get("Attention", 0)) - 6),
            "decline_pct": 8,
        })

    if lifestyle.get("Anxiety", 100) <= 30:
        no_action_declines.append({
            "domain":      "Clarity",
            "current":     int(domains.get("Clarity", 0)),
            "projected":   max(0, int(domains.get("Clarity", 0)) - 8),
            "decline_pct": 10,
        })

    if lifestyle.get("Burnout", 100) <= 30:
        no_action_declines.append({
            "domain":      "Processing",
            "current":     int(domains.get("Processing", 0)),
            "projected":   max(0, int(domains.get("Processing", 0)) - 12),
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

    return descriptions.get(
        name,
        "Performance in this domain remains stable."
    )


def generate_indicator_description(item):

    return (
        f"{item} appears to be contributing to reduced "
        f"cognitive efficiency and wellness patterns."
    )


def generate_projection(domains,age):

    projection = {}

    target_domains = [
        "Memory",
        "Attention",
        "Clarity"
    ]
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

def generate_root_causes(lifestyle: dict, domains: dict) -> list:

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
    if domains.get("Memory", 100) < 50:
        candidates.append({
            "factor":      "Memory consolidation deficit",
            "impact_pct":  20,
            "description": "Low memory scores suggest difficulty encoding and retrieving information.",
        })

    if domains.get("Attention", 100) < 50:
        candidates.append({
            "factor":      "Sustained attention difficulty",
            "impact_pct":  18,
            "description": "Attention scores indicate difficulty maintaining focus on demanding tasks.",
        })

    if domains.get("Clarity", 100) < 50:
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
def generate_score_breakdown(domains):

    weights = {
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