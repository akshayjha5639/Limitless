"""
Centralised question bank for the Limitless assessment.
To add a new language, add a key to QUESTIONS_BY_LOCALE with the same
structure as the "en" entry below.
"""

from typing import TypedDict


class QuestionDef(TypedDict):
    id: str
    text: str


class SectionDef(TypedDict):
    id: str
    title: str
    items: list[QuestionDef]


QUESTIONS_BY_LOCALE: dict[str, list[SectionDef]] = {
    "en": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I find it difficult to concentrate on tasks."},
                {"id": "S1_Q2", "text": "I get easily distracted while working or studying."},
                {"id": "S1_Q3", "text": "I struggle to complete tasks without losing focus."},
                {"id": "S1_Q4", "text": "I feel mentally foggy or unclear."},
            ],
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget important tasks or appointments."},
                {"id": "S2_Q2", "text": "I have trouble recalling recent information."},
                {"id": "S2_Q3", "text": "I misplace items more often than usual."},
                {"id": "S2_Q4", "text": "I struggle to retain new information."},
            ],
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I find it hard to make decisions."},
                {"id": "S3_Q2", "text": "My thinking feels slow or unclear."},
                {"id": "S3_Q3", "text": "I feel overwhelmed when processing information."},
                {"id": "S3_Q4", "text": "I lack mental sharpness during daily activities."},
            ],
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel anxious or worried frequently."},
                {"id": "S4_Q2", "text": "I feel low, sad, or unmotivated."},
                {"id": "S4_Q3", "text": "I feel overwhelmed by daily responsibilities."},
                {"id": "S4_Q4", "text": "I have mood swings or emotional instability."},
            ],
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel stressed most of the time."},
                {"id": "S5_Q2", "text": "I struggle to relax or unwind."},
                {"id": "S5_Q3", "text": "I feel mentally exhausted."},
                {"id": "S5_Q4", "text": "I find it difficult to cope with challenges."},
            ],
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I have trouble falling asleep."},
                {"id": "S6_Q2", "text": "I wake up feeling tired or unrested."},
                {"id": "S6_Q3", "text": "My sleep is interrupted or poor quality."},
                {"id": "S6_Q4", "text": "I feel fatigued during the day."},
            ],
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "My productivity has decreased recently."},
                {"id": "S7_Q2", "text": "I struggle to stay motivated."},
                {"id": "S7_Q3", "text": "I find it hard to manage my time effectively."},
                {"id": "S7_Q4", "text": "I feel less efficient than usual."},
            ],
        },
    ]
}

# Fallback locale when the requested one isn't available
DEFAULT_LOCALE = "en"


def get_sections(locale: str) -> list[SectionDef]:
    """Return the section/question list for the given locale, falling back to English."""
    return QUESTIONS_BY_LOCALE.get(locale, QUESTIONS_BY_LOCALE[DEFAULT_LOCALE])
