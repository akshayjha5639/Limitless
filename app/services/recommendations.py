"""
Limitless — Recommendations Engine
Generates a personalized action plan based on domain scores + risk indicators.
Tuned for 18–25 cohort: academic stress, screen time, sleep debt, burnout.
"""

from app.scoring.engine import SectionScores, DomainScores
from app.scoring.engine import get_age_band

# ---------------------------------------------------------------------------
# Rule-based recommendation pool
# Each entry: (condition_fn, recommendation_string)
# Conditions checked in order; up to 7 recommendations returned.
# ---------------------------------------------------------------------------

 
_BAND_RULES: dict[str, list[tuple]] = {
 
    # ---------------------------------------------------------------
    "young_adult": [
        (
            lambda s, d, risks: s.sleep_recovery < 75,
            "Set a consistent sleep schedule (same time ±30 min on weekends) to stabilise your circadian rhythm before exam stress builds up.",
        ),
        (
            lambda s, d, risks: d.attention_focus < 65,
            "Try the Pomodoro technique (25 min focused work, 5 min break) during study sessions — structured intervals reduce mental fatigue and improve sustained attention.",
        ),
        (
            lambda s, d, risks: d.memory < 80,
            "Space your study sessions across multiple days instead of cramming — spaced repetition improves memory consolidation by 40–60%.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 65,
            "Limit passive social media scrolling to under 30 minutes daily — heavy use is linked to higher anxiety and lower mood in your age group.",
        ),
        (
            lambda s, d, risks: s.stress_resilience < 75 or d.processing_speed < 70,
            "Add 20 minutes of moderate aerobic exercise (run, cycle, swim) 4× per week — it boosts BDNF, the brain's growth hormone, and sharpens focus for studying.",
        ),
        (
            lambda s, d, risks: s.stress_resilience < 60,
            "Add 5–10 minutes of box breathing or guided mindfulness daily before high-pressure moments like exams — it lowers cortisol and protects working memory.",
        ),
        (
            lambda s, d, risks: len(risks) >= 3,
            "Consider speaking with a campus counsellor — most universities offer free, confidential sessions, and multiple wellness indicators suggest extra support could help right now.",
        ),
    ],
 
    # ---------------------------------------------------------------
    "emerging_professional": [
        (
            lambda s, d, risks: s.sleep_recovery < 75 or s.stress_resilience < 70,
            "Set a hard stop time for work each evening — an undefined boundary between work and rest is one of the biggest drivers of burnout at this career stage.",
        ),
        (
            lambda s, d, risks: s.stress_resilience < 60 or any("financ" in r.lower() for r in risks),
            "Build a simple monthly budget or automate part of your savings — financial uncertainty is a major hidden driver of stress and sleep disruption right now.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 70,
            "Schedule uninterrupted, phone-free time with your partner each week — relationship strain often goes unaddressed while career demands take priority.",
        ),
        (
            lambda s, d, risks: s.stress_resilience < 75 or d.processing_speed < 70,
            "Build a sustainable exercise habit you can keep up alongside a full-time job — even three 20-minute sessions a week meaningfully improves stress resilience and focus.",
        ),
        (
            lambda s, d, risks: d.attention_focus < 65 or d.executive_function < 70,
            "Set clearer boundaries around after-hours messages and back-to-back meetings — protecting blocks of uninterrupted time improves both focus and decision quality.",
        ),
        (
            lambda s, d, risks: len(risks) >= 3,
            "Consider working with a therapist or career coach — multiple wellness indicators suggest structured professional support could meaningfully help right now.",
        ),
    ],
 
    # ---------------------------------------------------------------
    "established_adult": [
        (
            lambda s, d, risks: s.stress_resilience < 70 or s.emotional_wellbeing < 70,
            "Build in micro-recovery moments during the day, even five minutes alone with a coffee — small breaks matter most when full days off are hard to find.",
        ),
        (
            lambda s, d, risks: d.executive_function < 70 or s.stress_resilience < 65,
            "Identify one task to delegate at work this week — reducing decision load at the office frees up mental bandwidth for home.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 70,
            "Protect a weekly check-in with your partner, even 20 minutes — staying connected amid parenting and work demands takes deliberate scheduling.",
        ),
        (
            lambda s, d, risks: s.sleep_recovery < 70 or d.processing_speed < 70,
            "Book an annual check-up covering thyroid, iron, and vitamin D — deficiencies in these are common at this life stage and can mimic cognitive fatigue.",
        ),
        (
            lambda s, d, risks: len(risks) >= 2 or s.stress_resilience < 65,
            "Block one hour of fully protected personal time each week, just for you — identity beyond parenting and career needs deliberate space to exist.",
        ),
    ],
 
    # ---------------------------------------------------------------
    "mid_career": [
        (
            lambda s, d, risks: d.executive_function < 70 or len(risks) >= 2,
            "Run a complexity audit: list every standing commitment and cut or pause one this month — fewer competing demands restores mental bandwidth faster than any productivity hack.",
        ),
        (
            lambda s, d, risks: d.attention_focus < 65,
            "Protect a 2-hour deep work block each day with notifications off — fragmented attention across competing priorities is the main driver of feeling mentally maxed out.",
        ),
        (
            lambda s, d, risks: s.stress_resilience < 65 or any("parent" in r.lower() for r in risks),
            "Start proactive planning conversations about your parents' care needs now, before a crisis forces reactive decisions — this single step reduces a major source of background anxiety.",
        ),
        (
            lambda s, d, risks: s.sleep_recovery < 70,
            "Upgrade your sleep hygiene with a consistent wind-down routine and no screens 30 minutes before bed — racing thoughts about responsibilities are easier to manage with better sleep architecture.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 70,
            "Invest in a regular communication check-in with your partner — relationship strain often gets deprioritised when work and caregiving compete for attention.",
        ),
    ],
 
    # ---------------------------------------------------------------
    "midlife_transition": [
        (
            lambda s, d, risks: len(risks) >= 2 or d.memory < 70,
            "Book a GP visit for hormonal screening — many of the memory and mood changes at this life stage have a treatable hormonal component worth ruling out.",
        ),
        (
            lambda s, d, risks: s.sleep_recovery < 70 or s.stress_resilience < 70,
            "Adopt a Mediterranean-style diet rich in omega-3s and leafy greens — it supports both mood regulation and cognitive performance during this transition.",
        ),
        (
            lambda s, d, risks: d.memory < 75 or d.mental_clarity < 70,
            "Pick up a brain-training activity like a new language or instrument — novel learning builds cognitive reserve precisely when you may be noticing more lapses.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 70,
            "Invest deliberately in your social circle — friendships often quietly thin out at this stage, and connection is protective for both mood and memory.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 65 or len(risks) >= 2,
            "Try a purpose audit: write down what currently feels meaningful versus what feels obligatory — clarity here often eases the restlessness common at this stage.",
        ),
    ],
 
    # ---------------------------------------------------------------
    "pre_senior": [
        (
            lambda s, d, risks: d.memory < 75 or d.mental_clarity < 70,
            "Build cognitive reserve through regular reading, a course, or social activities — these are some of the strongest protective factors for long-term brain health.",
        ),
        (
            lambda s, d, risks: len(risks) >= 2 or d.processing_speed < 70,
            "Start monitoring your blood pressure regularly — cardiovascular health is closely tied to cognitive sharpness from this age onward.",
        ),
        (
            lambda s, d, risks: s.sleep_recovery < 65,
            "Ask your doctor about a sleep apnea screening — undiagnosed apnea is common at this age and shows up as daytime grogginess and memory lapses.",
        ),
        (
            lambda s, d, risks: s.stress_resilience < 75 or d.processing_speed < 70,
            "Add weight-bearing exercise like brisk walking or light resistance training a few times a week — it supports brain health as much as muscle health.",
        ),
        (
            lambda s, d, risks: len(risks) >= 2,
            "Establish a cognitive baseline with your GP now — having a reference point makes any future changes easier to track and put in context.",
        ),
    ],
 
    # ---------------------------------------------------------------
    "senior_adult": [
        (
            lambda s, d, risks: s.emotional_wellbeing < 70,
            "Treat regular social engagement as part of your health routine, not an optional extra — consistent connection is one of the strongest predictors of healthy cognitive aging.",
        ),
        (
            lambda s, d, risks: d.problem_solving < 70 or d.mental_clarity < 70,
            "Spend time learning a new piece of technology, like a tablet feature or app — the unfamiliar problem-solving involved helps keep the brain adaptable.",
        ),
        (
            lambda s, d, risks: len(risks) >= 2 or d.reaction_time < 70,
            "Add simple balance exercises a few times a week, like standing on one foot while brushing your teeth — balance training supports both physical safety and brain function.",
        ),
        (
            lambda s, d, risks: d.memory < 75 or d.mental_clarity < 70,
            "Take up a class, course, or new skill — structured learning is one of the most effective ways to keep the mind active and engaged.",
        ),
        (
            lambda s, d, risks: s.emotional_wellbeing < 70 or len(risks) >= 2,
            "Lean into mentoring, volunteering, or time with grandchildren — having a clear sense of purpose is strongly linked to wellbeing in this life stage.",
        ),
    ],
}
 
# ---------------------------------------------------------------------------
# Rules that fire for every band, regardless of age
# ---------------------------------------------------------------------------
 
_UNIVERSAL_RULES: list[tuple] = [
    (
        lambda s, d, risks: len(risks) >= 3,
        "Consider speaking with a licensed clinician or healthcare professional — multiple wellness indicators suggest professional support could be beneficial.",
    ),
    (
        lambda s, d, risks: len(risks) == 0,
        "Your cognitive wellness is in great shape — maintain your current routines and reassess in 4–6 weeks to track progress.",
    ),
]
 
# Always appended last, unconditionally (compliance)
_DISCLAIMER = "This plan is a wellness guide, not medical advice. Consult a licensed clinician for persistent symptoms."
 
MAX_RECOMMENDATIONS = 7


def build_recommendations(
    section_scores: SectionScores,
    domain_scores: DomainScores,
    risk_indicators: list[str],
    age: int,
) -> list[str]:
    """
    Returns up to MAX_RECOMMENDATIONS personalised recommendations for the
    age band resolved from `age`, plus the mandatory universal disclaimer
    as the final item.
    """
    band = get_age_band(age)
    rules = _BAND_RULES[band] + _UNIVERSAL_RULES
 
    selected = []
 
    for condition, recommendation in rules:
        if len(selected) >= MAX_RECOMMENDATIONS:
            break
        if condition(section_scores, domain_scores, risk_indicators):
            selected.append(recommendation)
 
    # Always append compliance note
    selected.append(_DISCLAIMER)
 
    return selected