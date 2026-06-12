"""
Limitless — Dynamic Question Generator
Uses Gemini API to generate age/gender-tailored cognitive wellness questions.

Structure is always identical (7 sections × 4 items, Likert 0–4) so the
scoring engine requires zero changes. Only the question text changes.
"""

import json
import os
import re
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Age/gender context builder
# ---------------------------------------------------------------------------

SECTION_DEFINITIONS = [
    {"id": "S1", "title": "Focus & Attention",               "domain": "attention and concentration"},
    {"id": "S2", "title": "Memory Function",                  "domain": "memory and recall"},
    {"id": "S3", "title": "Mental Clarity & Decision-Making", "domain": "cognitive clarity and decision-making"},
    {"id": "S4", "title": "Emotional Well-being",             "domain": "emotional health and mood"},
    {"id": "S5", "title": "Stress & Resilience",              "domain": "stress management and resilience"},
    {"id": "S6", "title": "Sleep & Recovery",                 "domain": "sleep quality and recovery"},
    {"id": "S7", "title": "Productivity & Performance",       "domain": "productivity and daily performance"},
]

AGE_CONTEXT = {
    (18, 20): {
        "life_stage": "late teens / early college",
        "stressors": "academic transition, new independence, social pressure, identity formation, irregular sleep from dorm life",
        "focus_areas": "exam anxiety, social media distraction, homesickness, peer comparison, motivation to study",
    },
    (21, 22): {
        "life_stage": "college mid-years",
        "stressors": "academic workload, internship pressure, relationship stress, financial concerns, career uncertainty",
        "focus_areas": "deadline management, burnout from over-commitment, caffeine dependence, procrastination, focus during lectures",
    },
    (23, 25): {
        "life_stage": "early career / post-graduation",
        "stressors": "job transition, workplace adjustment, financial independence, relationship decisions, long working hours",
        "focus_areas": "work performance anxiety, imposter syndrome, work-life balance, decision fatigue, career motivation",
    },
}

GENDER_CONTEXT = {
    "male": "tends to underreport emotional symptoms; frame emotional questions around performance impact and energy levels rather than feelings directly",
    "female": "may experience mood variability linked to hormonal cycles; include questions sensitive to emotional load, social pressures, and self-perception",
    "other": "use inclusive, neutral language avoiding gender-specific assumptions about stress sources or emotional expression",
    "prefer-not-to-say": "use inclusive, neutral language avoiding gender-specific assumptions",
    # Also handle non_binary from GenderEnum
    "non_binary": "use inclusive, neutral language avoiding gender-specific assumptions about stress sources or emotional expression",
    "prefer_not_to_say": "use inclusive, neutral language avoiding gender-specific assumptions",
}


def _get_age_context(age: int) -> dict:
    for (lo, hi), ctx in AGE_CONTEXT.items():
        if lo <= age <= hi:
            return ctx
    # Fallback — shouldn't happen for 18–25
    return AGE_CONTEXT[(23, 25)]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(age: int, gender: str) -> str:
    age_ctx    = _get_age_context(age)
    gender_ctx = GENDER_CONTEXT.get(gender, GENDER_CONTEXT["other"])

    sections_spec = "\n".join(
        f'  - {s["id"]} | {s["title"]} | domain: {s["domain"]}'
        for s in SECTION_DEFINITIONS
    )

    return f"""You are an expert cognitive wellness assessment designer.

Generate a cognitive wellness questionnaire for a {age}-year-old {gender} person.

USER CONTEXT:
- Life stage: {age_ctx['life_stage']}
- Common stressors: {age_ctx['stressors']}
- Key focus areas: {age_ctx['focus_areas']}
- Gender framing guidance: {gender_ctx}

REQUIREMENTS:
1. Generate exactly 7 sections, each with exactly 4 questions.
2. All questions use first-person ("I...") and a Likert scale where:
   0 = Never/Rarely, 4 = Very Often/Severe
   So higher scores indicate MORE symptoms (worse cognitive wellness).
3. Questions must be specific to this person's age, life stage, and likely stressors.
   Do NOT use generic questions — make them feel personally relevant.
4. Keep each question under 15 words. Clear, simple language. No clinical jargon.
5. Each section must match its assigned domain exactly.
6. Use gender framing guidance subtly — don't make it obvious in the question text.

SECTIONS TO GENERATE:
{sections_spec}

OUTPUT FORMAT — return ONLY valid JSON, no markdown, no explanation:
{{
  "sections": [
    {{
      "id": "S1",
      "title": "Focus & Attention",
      "items": [
        {{"id": "S1_Q1", "text": "I struggle to focus during lectures or study sessions."}},
        {{"id": "S1_Q2", "text": "..."}},
        {{"id": "S1_Q3", "text": "..."}},
        {{"id": "S1_Q4", "text": "..."}}
      ]
    }},
    ... (S2 through S7)
  ]
}}"""


# ---------------------------------------------------------------------------
# Response parser & validator
# ---------------------------------------------------------------------------

EXPECTED_SECTION_IDS = [f"S{i}" for i in range(1, 8)]
EXPECTED_ITEM_COUNT  = 4


def _parse_and_validate(raw: str) -> list[dict]:
    """
    Parse Gemini's JSON response and validate structure.
    Raises ValueError with a clear message on any structural issue.
    """
    # Strip markdown fences if Gemini wraps in ```json ... ```
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini returned invalid JSON: {e}\nRaw: {raw[:300]}")

    sections = data.get("sections", [])

    if len(sections) != 7:
        raise ValueError(f"Expected 7 sections, got {len(sections)}")

    for i, section in enumerate(sections):
        expected_sid = EXPECTED_SECTION_IDS[i]

        if section.get("id") != expected_sid:
            raise ValueError(f"Section {i} has id '{section.get('id')}', expected '{expected_sid}'")

        items = section.get("items", [])
        if len(items) != EXPECTED_ITEM_COUNT:
            raise ValueError(
                f"Section {expected_sid} has {len(items)} items, expected {EXPECTED_ITEM_COUNT}"
            )

        for j, item in enumerate(items):
            expected_iid = f"{expected_sid}_Q{j + 1}"
            if item.get("id") != expected_iid:
                raise ValueError(
                    f"Item {j} in {expected_sid} has id '{item.get('id')}', expected '{expected_iid}'"
                )
            if not item.get("text", "").strip():
                raise ValueError(f"Item {expected_iid} has empty text")

    return sections


# ---------------------------------------------------------------------------
# Fallback — static questions if Gemini fails
# ---------------------------------------------------------------------------

def _static_fallback(age: int, gender: str) -> list[dict]:
    """
    Returns minimally age-aware static questions.
    Used when Gemini API call fails (network error, quota, etc.)
    """
    age_ctx = _get_age_context(age)
    stage   = age_ctx["life_stage"]

    return [
        {"id": "S1", "title": "Focus & Attention", "items": [
            {"id": "S1_Q1", "text": f"I struggle to concentrate on tasks at my {stage} stage."},
            {"id": "S1_Q2", "text": "I get easily distracted while working or studying."},
            {"id": "S1_Q3", "text": "I lose focus before finishing important tasks."},
            {"id": "S1_Q4", "text": "I feel mentally foggy or unclear during the day."},
        ]},
        {"id": "S2", "title": "Memory Function", "items": [
            {"id": "S2_Q1", "text": "I forget important tasks or deadlines."},
            {"id": "S2_Q2", "text": "I have trouble recalling things I recently learned."},
            {"id": "S2_Q3", "text": "I misplace items or forget where I put things."},
            {"id": "S2_Q4", "text": "I struggle to retain new information."},
        ]},
        {"id": "S3", "title": "Mental Clarity & Decision-Making", "items": [
            {"id": "S3_Q1", "text": "I find it hard to make decisions under pressure."},
            {"id": "S3_Q2", "text": "My thinking feels slow or unclear."},
            {"id": "S3_Q3", "text": "I feel overwhelmed when processing too much information."},
            {"id": "S3_Q4", "text": "I lack mental sharpness during important activities."},
        ]},
        {"id": "S4", "title": "Emotional Well-being", "items": [
            {"id": "S4_Q1", "text": "I feel anxious or worried about my performance."},
            {"id": "S4_Q2", "text": "I feel unmotivated or low in energy."},
            {"id": "S4_Q3", "text": "I feel overwhelmed by daily responsibilities."},
            {"id": "S4_Q4", "text": "My mood affects my ability to work or study."},
        ]},
        {"id": "S5", "title": "Stress & Resilience", "items": [
            {"id": "S5_Q1", "text": "I feel stressed about upcoming deadlines or tasks."},
            {"id": "S5_Q2", "text": "I struggle to relax or unwind after a long day."},
            {"id": "S5_Q3", "text": "I feel mentally exhausted by end of day."},
            {"id": "S5_Q4", "text": "I find it hard to cope with unexpected challenges."},
        ]},
        {"id": "S6", "title": "Sleep & Recovery", "items": [
            {"id": "S6_Q1", "text": "I have trouble falling asleep due to racing thoughts."},
            {"id": "S6_Q2", "text": "I wake up feeling tired or unrested."},
            {"id": "S6_Q3", "text": "My sleep schedule is irregular or poor quality."},
            {"id": "S6_Q4", "text": "I feel fatigued during the day despite sleeping."},
        ]},
        {"id": "S7", "title": "Productivity & Performance", "items": [
            {"id": "S7_Q1", "text": "My productivity has dropped recently."},
            {"id": "S7_Q2", "text": "I struggle to stay motivated on important tasks."},
            {"id": "S7_Q3", "text": "I find it hard to manage my time effectively."},
            {"id": "S7_Q4", "text": "I feel less efficient than I used to be."},
        ]},
    ]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_questions(age: int, gender: str) -> tuple[list[dict], bool]:
    """
    Generate age/gender-tailored questions using Gemini API.

    Returns:
        (sections, is_ai_generated)
        sections          — list of 7 section dicts with items
        is_ai_generated   — True if Gemini succeeded, False if fallback used
    """
    try:
        client = _get_client()
        prompt = _build_prompt(age, gender)

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,        # some creativity but not too random
                max_output_tokens=2048,
                response_mime_type="application/json",  # enforce JSON output
            ),
        )

        raw = response.text
        sections = _parse_and_validate(raw)
        return sections, True

    except RuntimeError as e:
        # GEMINI_API_KEY not set
        raise e

    except Exception as e:
        # Network error, quota exceeded, parse failure — use fallback
        print(f"[question_generator] Gemini call failed: {e}. Using static fallback.")
        return _static_fallback(age, gender), False
