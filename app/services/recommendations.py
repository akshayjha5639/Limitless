"""
Limitless — Recommendations Engine
Generates a personalized action plan based on domain scores + risk indicators.
Tuned for 18–25 cohort: academic stress, screen time, sleep debt, burnout.
"""

from app.scoring.engine import SectionScores, DomainScores


# ---------------------------------------------------------------------------
# Rule-based recommendation pool
# Each entry: (condition_fn, recommendation_string)
# Conditions checked in order; up to 7 recommendations returned.
# ---------------------------------------------------------------------------

_RULES: list[tuple] = [
    # --- Sleep ---
    (
        lambda s, d, risks: s.sleep_recovery < 60,
        "Prioritise 7–8 hours of sleep — even one extra hour significantly improves memory consolidation and focus the next day.",
    ),
    (
        lambda s, d, risks: s.sleep_recovery < 75,
        "Set a consistent sleep schedule (same time ±30 min on weekends) to stabilise your circadian rhythm.",
    ),
    # --- Stress ---
    (
        lambda s, d, risks: s.stress_resilience < 60,
        "Add 5–10 minutes of box breathing or guided mindfulness daily — it directly lowers cortisol and improves working memory.",
    ),
    (
        lambda s, d, risks: any("burnout" in r.lower() for r in risks),
        "Schedule at least one full recovery day per week with no academic or work obligations — burnout compounds without deliberate rest.",
    ),
    # --- Attention & Focus ---
    (
        lambda s, d, risks: d.attention_focus < 65,
        "Try the Pomodoro technique (25 min focused work, 5 min break) — structured intervals reduce mental fatigue and improve sustained attention.",
    ),
    (
        lambda s, d, risks: d.attention_focus < 75,
        "Reduce multitasking: single-task for at least 2 hours each day. Switching costs reduce effective IQ by up to 10 points.",
    ),
    # --- Screen time / Emotional ---
    (
        lambda s, d, risks: s.emotional_wellbeing < 65,
        "Limit passive social media scrolling to under 30 minutes daily — studies link it to higher anxiety and lower mood in the 18–25 age group.",
    ),
    # --- Exercise ---
    (
        lambda s, d, risks: s.stress_resilience < 75 or d.processing_speed < 70,
        "20 minutes of moderate aerobic exercise (run, cycle, swim) 4× per week boosts BDNF — the brain's growth hormone.",
    ),
    # --- Memory ---
    (
        lambda s, d, risks: d.memory < 70,
        "Use active recall instead of re-reading: close your notes and write what you remember — this alone doubles long-term retention.",
    ),
    (
        lambda s, d, risks: d.memory < 80,
        "Space your study sessions across multiple days rather than cramming — spaced repetition improves memory consolidation by 40–60%.",
    ),
    # --- Nutrition ---
    (
        lambda s, d, risks: s.sleep_recovery < 70 or s.stress_resilience < 70,
        "Adopt a Mediterranean-style diet (whole grains, omega-3s, leafy greens) — it supports both mood regulation and cognitive performance.",
    ),
    # --- Professional referral (compliance requirement) ---
    (
        lambda s, d, risks: len(risks) >= 3,
        "Consider speaking with a campus counsellor or licensed clinician — multiple wellness indicators suggest professional support could be beneficial.",
    ),
    # --- Positive reinforcement for high scorers ---
    (
        lambda s, d, risks: len(risks) == 0,
        "Your cognitive wellness is in great shape — maintain your current routines and reassess in 4–6 weeks to track progress.",
    ),
]

# Always appended regardless of scores (compliance)
_UNIVERSAL = "This plan is a wellness guide, not medical advice. Consult a licensed clinician for persistent symptoms."

MAX_RECOMMENDATIONS = 7


def build_recommendations(
    section_scores: SectionScores,
    domain_scores: DomainScores,
    risk_indicators: list[str],
) -> list[str]:
    """
    Returns up to MAX_RECOMMENDATIONS personalised recommendations
    plus the mandatory universal disclaimer as the final item.
    """
    selected = []

    for condition, recommendation in _RULES:
        if len(selected) >= MAX_RECOMMENDATIONS:
            break
        if condition(section_scores, domain_scores, risk_indicators):
            selected.append(recommendation)

    # Always append compliance note
    selected.append(_UNIVERSAL)

    return selected
