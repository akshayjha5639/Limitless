
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

    sorted_domains = sorted(
        domains.items(),
        key=lambda x: x[1],
        reverse=True
    )

    strengths = []

    for name, score in sorted_domains[:3]:

        strengths.append({
            "title": name,
            "score": score,
            "description": generate_strength_description(name)
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
            "assessment_date":
                datetime.now().strftime("%d %B %Y"),
        },

        "domains": domains,

        "lifestyle": lifestyle,

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
