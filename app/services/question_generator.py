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
from app.scoring.engine import get_age_band
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
    "young_adult": {
        "life_stage":       "late teens to mid twenties — college or early career",
        "stressors":        "academic deadlines, exam anxiety, social comparison on social media, financial dependence on parents, identity formation, irregular sleep from late nights, peer pressure",
        "focus_areas":      "concentration during lectures, phone and social media distraction, motivation to study, first job adjustment, romantic relationship stress, FOMO and social anxiety",
        "question_tone":    "casual and relatable, first person, references study sessions, lectures, assignments, and social life naturally",
        "domain_emphasis":  "attention and focus, stress and resilience — these are the primary cognitive concerns for this life stage",
    },

    "emerging_professional": {
        "life_stage":       "mid to late twenties — career building and relationship decisions",
        "stressors":        "workplace performance pressure, imposter syndrome in new roles, relationship decisions including marriage, financial independence and loan repayment, career comparison with peers, relocation and city adjustment stress",
        "focus_areas":      "work deadline management, professional confidence, maintaining relationships outside work, gym and health neglect, first-time financial planning anxiety, performance reviews",
        "question_tone":    "professional and self-aware, first person, references work environment, professional goals, and adult responsibilities naturally",
        "domain_emphasis":  "executive function and stress resilience — career demands require planning, decision-making, and sustained mental energy",
    },

    "established_adult": {
        "life_stage":       "early to mid thirties — career established, family commitments beginning or deepening",
        "stressors":        "early parenthood demands and sleep disruption, career leadership pressure, mortgage and financial commitments, marriage or partnership stress, identity shifting beyond individual career, social circle narrowing",
        "focus_areas":      "parenting fatigue affecting concentration, work-life balance deterioration, decision fatigue from managing multiple responsibilities simultaneously, reduced personal recovery time, health beginning to require attention",
        "question_tone":    "mature and responsibility-aware, first person, references family demands and career pressures existing simultaneously without choosing one over the other",
        "domain_emphasis":  "executive function and emotional wellbeing — managing complexity across life domains is the defining cognitive challenge of this stage",
    },

    "mid_career": {
        "life_stage":       "late thirties to early forties — peak responsibility and complexity phase",
        "stressors":        "peak career complexity and leadership demands, teenage or young children requiring different engagement, aging parents beginning to need support, long-term relationship stress, first noticeable physical health changes, financial peak pressure",
        "focus_areas":      "multitasking overload from simultaneous life demands, cognitive fatigue from leadership and management decisions, sleep disruption from worry and responsibility, mental bandwidth exhaustion, social obligation overwhelm",
        "question_tone":    "complexity-aware and grounded, first person, acknowledges that multiple major life domains are competing for mental energy simultaneously",
        "domain_emphasis":  "memory and processing speed beginning to show sensitivity alongside stress — questions should probe mental fatigue and cognitive load specifically",
    },

    "midlife_transition": {
        "life_stage":       "early to mid forties — biological transitions and life reassessment phase",
        "stressors":        "hormonal changes with perimenopause or andropause beginning, career plateau or existential questioning, children gaining independence shifting parental role, parent caregiving responsibilities increasing, health monitoring and diagnosis anxiety increasing",
        "focus_areas":      "noticing word-finding difficulty for the first time, memory lapses becoming more noticeable, mood volatility and emotional regulation, motivation and energy shifts, cognitive purpose and meaning questioning, brain fog episodes",
        "question_tone":    "health-conscious and introspective, first person, acknowledges biological and life changes with matter-of-fact normalising language — never alarmist, never dismissive",
        "domain_emphasis":  "memory and mental clarity are the primary cognitive concerns — questions should probe everyday memory failures and thinking clarity specifically and concretely",
    },

    "pre_senior": {
        "life_stage":       "late forties to mid fifties — active health maintenance and cognitive vigilance phase",
        "stressors":        "retirement planning financial stress, health diagnosis anxiety and medical appointments, social circle gradually shifting, career wind-down or reinvention, long-term relationship renegotiation, sleep quality declining noticeably",
        "focus_areas":      "memory vigilance and awareness of changes over time, cognitive reserve building habits, physical health conditions impacting mental sharpness, maintaining social engagement as life structure shifts, daily task efficiency and organisation",
        "question_tone":    "proactive and measured, first person, frames cognitive wellness as something actively managed rather than passively experienced — strength and capability focused, non-alarmist",
        "domain_emphasis":  "memory and processing speed are the primary clinical concerns — sleep recovery is the highest-leverage lifestyle factor at this stage and should be probed carefully",
    },

    "senior_adult": {
        "life_stage":       "mid fifties to mid sixties — active senior phase with cognitive maintenance priority",
        "stressors":        "retirement adjustment and purpose redefinition, grandparenting responsibilities and demands, health management complexity with multiple conditions, beginning to experience loss of peers, technology overwhelm, independence and driving confidence",
        "focus_areas":      "daily functioning confidence, word retrieval difficulty in conversation, spatial navigation and getting lost, task completion and follow-through, social connection quality and loneliness risk, confidence learning new skills or technology",
        "question_tone":    "respectful and dignity-preserving, capability-affirming language throughout, shorter sentences with maximum 12 words per question, everyday concrete language with zero technical or clinical terms, never infantilizing",
        "domain_emphasis":  "memory and reaction time are the primary cognitive concerns — language skills and problem solving should also be probed carefully as these show earliest decline signals in this band",
    },
}

GENDER_CONTEXT = {
    "male": "tends to underreport emotional symptoms; frame emotional questions around performance impact and energy levels",
    "female": "may experience mood variability; for ages 43-55 acknowledge hormonal cognitive impact naturally in question framing",
    "other": "use inclusive neutral language avoiding gender-specific assumptions",
    "prefer-not-to-say": "use inclusive neutral language avoiding gender-specific assumptions",
    "non_binary": "use inclusive neutral language avoiding gender-specific assumptions",
    "prefer_not_to_say": "use inclusive neutral language avoiding gender-specific assumptions",
}


def _get_age_context(age: int) -> dict:
    band = get_age_band(age)
    return AGE_CONTEXT[band]


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(age: int, gender: str) -> str:
    age_ctx    = _get_age_context(age)
    gender_ctx = GENDER_CONTEXT.get(gender, GENDER_CONTEXT["other"])
    band       = get_age_band(age)

    # Band label for display in prompt
    band_labels = {
        "young_adult":            "Young Adult (18–25)",
        "emerging_professional":  "Emerging Professional (26–32)",
        "established_adult":      "Established Adult (33–37)",
        "mid_career":             "Mid-Career Adult (38–42)",
        "midlife_transition":     "Midlife Transition (43–47)",
        "pre_senior":             "Pre-Senior Adult (48–55)",
        "senior_adult":           "Senior Adult (56–66)",
    }
    band_label = band_labels.get(band, "Adult")

    # Hormonal context — only for 43–55 band
    hormonal_note = ""
    if gender == "female" and 43 <= age <= 55:
        hormonal_note = (
            "\nHORMONAL CONTEXT: This woman may be experiencing perimenopause. "
            "Cognitive symptoms like brain fog, word-finding difficulty, and mood variability "
            "are common during this phase. Where relevant, frame questions to capture these "
            "experiences naturally without being clinical or alarming."
        )
    elif gender == "male" and 43 <= age <= 55:
        hormonal_note = (
            "\nHORMONAL CONTEXT: This man may be experiencing andropause. "
            "Motivation shifts, energy dips, and mood changes are relevant cognitive factors. "
            "Frame questions around energy, drive, and emotional regulation for this band."
        )

    sections_spec = "\n".join(
        f'  - {s["id"]} | {s["title"]} | domain: {s["domain"]}'
        for s in SECTION_DEFINITIONS
    )

    return f"""You are an expert cognitive wellness assessment designer specialising in age-appropriate psychological questionnaires.

Generate a cognitive wellness questionnaire for a {age}-year-old {gender} person.

LIFE STAGE BAND: {band_label}

USER CONTEXT:
- Life stage:        {age_ctx['life_stage']}
- Common stressors:  {age_ctx['stressors']}
- Key focus areas:   {age_ctx['focus_areas']}
- Gender framing:    {gender_ctx}{hormonal_note}

STYLE INSTRUCTIONS:
- Tone:              {age_ctx['question_tone']}
- Domain emphasis:   {age_ctx['domain_emphasis']}

QUESTION REQUIREMENTS:
1. Generate exactly 7 sections, each with exactly 4 questions.
2. All questions use first-person ("I...") phrasing.
3. Likert scale applies to all questions: 0 = Never/Rarely, 4 = Very Often/Severe.
   Higher scores = more symptoms = worse cognitive wellness.
4. Questions must feel personally relevant to this specific person's age, life stage, and stressors.
   Do NOT write generic questions that could apply to anyone at any age.
5. Write MORE specific and probing questions for the domain emphasis areas listed above.
6. Keep every question under 15 words. Simple, clear language. Zero clinical jargon.
7. For the senior_adult band: maximum 12 words per question, everyday concrete language only.
8. Each section must match its assigned domain exactly — do not blend domains.
9. Apply the gender framing guidance subtly within the question content — never make it obvious.
10. Do NOT repeat the same idea across multiple questions within a section.

SECTIONS TO GENERATE:
{sections_spec}

OUTPUT FORMAT:
Return ONLY valid JSON with no markdown fences, no explanation, no preamble.
Exactly this structure:
{{
  "sections": [
    {{
      "id": "S1",
      "title": "Focus & Attention",
      "items": [
        {{"id": "S1_Q1", "text": "I struggle to focus during work meetings."}},
        {{"id": "S1_Q2", "text": "..."}},
        {{"id": "S1_Q3", "text": "..."}},
        {{"id": "S1_Q4", "text": "..."}}
      ]
    }},
    {{ "id": "S2", ... }},
    {{ "id": "S3", ... }},
    {{ "id": "S4", ... }},
    {{ "id": "S5", ... }},
    {{ "id": "S6", ... }},
    {{ "id": "S7", ... }}
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
STATIC_QUESTIONS = {
    "young_adult": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I struggle to focus during lectures or study sessions."},
                {"id": "S1_Q2", "text": "I get distracted by my phone while trying to study."},
                {"id": "S1_Q3", "text": "I lose track of what I'm reading and have to reread it."},
                {"id": "S1_Q4", "text": "I zone out during conversations with friends or classmates."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget exam dates or assignment deadlines."},
                {"id": "S2_Q2", "text": "I blank out on information during tests I studied for."},
                {"id": "S2_Q3", "text": "I forget what a professor just explained in class."},
                {"id": "S2_Q4", "text": "I lose track of plans I made with friends."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I feel unsure which classes or career path to choose."},
                {"id": "S3_Q2", "text": "I overthink small decisions like what to wear or eat."},
                {"id": "S3_Q3", "text": "I feel mentally foggy after a night of poor sleep."},
                {"id": "S3_Q4", "text": "I struggle to organize my thoughts before writing assignments."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel anxious comparing myself to peers on social media."},
                {"id": "S4_Q2", "text": "I feel overwhelmed by pressure to figure out my future."},
                {"id": "S4_Q3", "text": "I feel isolated even when surrounded by classmates."},
                {"id": "S4_Q4", "text": "My mood shifts depending on how my day at school went."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel panicked before exams even when I'm prepared."},
                {"id": "S5_Q2", "text": "I struggle to bounce back after a bad grade."},
                {"id": "S5_Q3", "text": "I feel stressed about managing money as a student."},
                {"id": "S5_Q4", "text": "I feel overwhelmed juggling classes, work, and a social life."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I stay up too late scrolling instead of sleeping."},
                {"id": "S6_Q2", "text": "I pull all-nighters before exams or deadlines."},
                {"id": "S6_Q3", "text": "I wake up tired even after a full night's sleep."},
                {"id": "S6_Q4", "text": "My mind races about school when I'm trying to fall asleep."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I procrastinate on assignments until the last minute."},
                {"id": "S7_Q2", "text": "I struggle to start studying even when I have time."},
                {"id": "S7_Q3", "text": "I find it hard to keep up with my coursework."},
                {"id": "S7_Q4", "text": "I feel less motivated to attend classes than I used to."},
            ]
        },
    ],
    "emerging_professional": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I find it hard to concentrate during back-to-back work meetings."},
                {"id": "S1_Q2", "text": "I get distracted checking emails or messages during tasks."},
                {"id": "S1_Q3", "text": "I lose focus midway through reading work reports."},
                {"id": "S1_Q4", "text": "I struggle to stay present during conversations with my partner."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget important work tasks or meeting details."},
                {"id": "S2_Q2", "text": "I forget names of new colleagues or clients I've met."},
                {"id": "S2_Q3", "text": "I lose track of which emails I still need to answer."},
                {"id": "S2_Q4", "text": "I forget commitments I made to friends or family."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I doubt my decisions even when I'm qualified to make them."},
                {"id": "S3_Q2", "text": "I feel mentally drained after making decisions all day at work."},
                {"id": "S3_Q3", "text": "I overanalyze whether I'm on the right career path."},
                {"id": "S3_Q4", "text": "I struggle to think clearly when facing competing work priorities."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel like a fraud despite my professional achievements."},
                {"id": "S4_Q2", "text": "I feel anxious comparing my career progress to peers."},
                {"id": "S4_Q3", "text": "I feel emotionally drained after a demanding work week."},
                {"id": "S4_Q4", "text": "I feel uncertain balancing my career with personal relationships."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel stressed meeting tight work deadlines."},
                {"id": "S5_Q2", "text": "I struggle to recover emotionally after a difficult workday."},
                {"id": "S5_Q3", "text": "I feel anxious about my financial independence and future stability."},
                {"id": "S5_Q4", "text": "I feel pressure to perform perfectly to prove myself at work."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I lie awake thinking about unfinished work tasks."},
                {"id": "S6_Q2", "text": "I sacrifice sleep to meet work deadlines."},
                {"id": "S6_Q3", "text": "I wake up still feeling exhausted before my workday starts."},
                {"id": "S6_Q4", "text": "I have trouble unwinding after a stressful day at the office."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I struggle to manage my workload within deadlines."},
                {"id": "S7_Q2", "text": "I find myself working longer hours than I intend to."},
                {"id": "S7_Q3", "text": "I procrastinate on tasks that feel overwhelming or unclear."},
                {"id": "S7_Q4", "text": "I feel less efficient at work than I expect myself to be."},
            ]
        },
    ],
    "established_adult": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I lose focus when managing work tasks and family needs together."},
                {"id": "S1_Q2", "text": "I get distracted mid-task by my children's needs."},
                {"id": "S1_Q3", "text": "I struggle to focus during conversations with my partner after a long day."},
                {"id": "S1_Q4", "text": "I find it hard to concentrate when juggling household and work demands."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget things I need to do for my children or partner."},
                {"id": "S2_Q2", "text": "I forget appointments or school events for my kids."},
                {"id": "S2_Q3", "text": "I lose track of household bills or tasks I meant to handle."},
                {"id": "S2_Q4", "text": "I forget conversations I had with my spouse earlier in the day."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I feel mentally exhausted from making decisions for my whole family."},
                {"id": "S3_Q2", "text": "I struggle to think clearly by the end of a long day."},
                {"id": "S3_Q3", "text": "I second-guess parenting decisions more than I used to."},
                {"id": "S3_Q4", "text": "I feel overwhelmed weighing financial decisions like mortgage or savings."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel guilty when I can't give enough time to my family."},
                {"id": "S4_Q2", "text": "I feel like I've lost parts of my identity outside of parenting."},
                {"id": "S4_Q3", "text": "I feel emotionally stretched thin between work and home."},
                {"id": "S4_Q4", "text": "I feel disconnected from my partner amid daily responsibilities."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel stressed balancing my career with raising children."},
                {"id": "S5_Q2", "text": "I struggle to bounce back after a chaotic day at home."},
                {"id": "S5_Q3", "text": "I feel anxious about financial pressures like mortgage payments."},
                {"id": "S5_Q4", "text": "I feel overwhelmed by the demands of marriage and parenting together."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I lose sleep tending to my children's needs at night."},
                {"id": "S6_Q2", "text": "I wake up exhausted even after a full night's rest."},
                {"id": "S6_Q3", "text": "I find it hard to wind down once the kids are asleep."},
                {"id": "S6_Q4", "text": "I lie awake worrying about family or financial responsibilities."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I struggle to get tasks done with constant family interruptions."},
                {"id": "S7_Q2", "text": "I feel less productive at work since becoming a parent."},
                {"id": "S7_Q3", "text": "I find it hard to prioritize tasks across work and home."},
                {"id": "S7_Q4", "text": "I rarely find time for myself amid daily responsibilities."},
            ]
        },
    ],
    "mid_career": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I struggle to focus when juggling multiple high-priority demands."},
                {"id": "S1_Q2", "text": "I get pulled in different directions during my workday."},
                {"id": "S1_Q3", "text": "I find it hard to concentrate with so many responsibilities competing for attention."},
                {"id": "S1_Q4", "text": "I lose focus when thinking about my teenager and aging parents at once."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget key details from important meetings or conversations."},
                {"id": "S2_Q2", "text": "I forget tasks I promised to handle for my parents or kids."},
                {"id": "S2_Q3", "text": "I lose track of details across multiple ongoing projects."},
                {"id": "S2_Q4", "text": "I forget things I meant to follow up on by day's end."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I feel mentally overloaded managing work, family, and aging parents."},
                {"id": "S3_Q2", "text": "I struggle to think clearly when too many demands compete at once."},
                {"id": "S3_Q3", "text": "I feel decision fatigue by the middle of most days."},
                {"id": "S3_Q4", "text": "I find it harder to switch between different roles and responsibilities."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel stretched thin caring for my children and aging parents."},
                {"id": "S4_Q2", "text": "I feel emotionally exhausted balancing so many responsibilities."},
                {"id": "S4_Q3", "text": "I feel tension in my relationship from competing life demands."},
                {"id": "S4_Q4", "text": "I feel like I have little energy left for myself."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel overwhelmed by the sheer number of responsibilities I carry."},
                {"id": "S5_Q2", "text": "I struggle to recover when one part of life adds more stress."},
                {"id": "S5_Q3", "text": "I feel anxious about my parents' health and my teenager's choices."},
                {"id": "S5_Q4", "text": "My stress rarely has time to fully ease before more builds up."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I lie awake worrying about my family's competing needs."},
                {"id": "S6_Q2", "text": "I wake up during the night thinking about unfinished responsibilities."},
                {"id": "S6_Q3", "text": "I feel mentally wired even when I'm physically tired."},
                {"id": "S6_Q4", "text": "I struggle to fully rest with so much on my mind."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I struggle to keep up with leadership demands at work."},
                {"id": "S7_Q2", "text": "I find my mental bandwidth maxed out most days."},
                {"id": "S7_Q3", "text": "I feel less sharp at work than I used to be."},
                {"id": "S7_Q4", "text": "I struggle to give full attention to any one task."},
            ]
        },
    ],
    "midlife_transition": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I find my concentration drifting during important conversations."},
                {"id": "S1_Q2", "text": "I notice it's harder to focus than it used to be."},
                {"id": "S1_Q3", "text": "I get mentally sidetracked more easily during the day."},
                {"id": "S1_Q4", "text": "I struggle to stay focused on one task for very long."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I struggle to remember names of people I know well."},
                {"id": "S2_Q2", "text": "I walk into a room and forget why I went there."},
                {"id": "S2_Q3", "text": "I have trouble recalling words mid-sentence."},
                {"id": "S2_Q4", "text": "I forget recent conversations more than I used to."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I notice more brain fog than I had a few years ago."},
                {"id": "S3_Q2", "text": "I take longer to make decisions than I used to."},
                {"id": "S3_Q3", "text": "I struggle to find the right word while speaking."},
                {"id": "S3_Q4", "text": "I feel less mentally sharp than I expect myself to be."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "My mood shifts more unpredictably than it used to."},
                {"id": "S4_Q2", "text": "I find myself questioning what gives my life purpose."},
                {"id": "S4_Q3", "text": "I feel less motivated about things I used to enjoy."},
                {"id": "S4_Q4", "text": "I feel more irritable than I used to without clear reason."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel more affected by stress than I used to."},
                {"id": "S5_Q2", "text": "It takes me longer to feel calm after stress."},
                {"id": "S5_Q3", "text": "I feel anxious noticing changes in my body or mind."},
                {"id": "S5_Q4", "text": "I feel uncertain navigating this stage of life."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I wake up during the night more than I used to."},
                {"id": "S6_Q2", "text": "I notice my sleep quality has changed in recent years."},
                {"id": "S6_Q3", "text": "I feel tired during the day despite sleeping enough hours."},
                {"id": "S6_Q4", "text": "I have more trouble falling back asleep once I wake."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I feel less driven at work than I used to be."},
                {"id": "S7_Q2", "text": "I notice my career feels stagnant or plateaued lately."},
                {"id": "S7_Q3", "text": "I take longer to complete tasks than I once did."},
                {"id": "S7_Q4", "text": "I find it harder to stay motivated on daily tasks."},
            ]
        },
    ],
    "pre_senior": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I have trouble staying focused when reading or watching something."},
                {"id": "S1_Q2", "text": "I notice my attention wandering during longer conversations."},
                {"id": "S1_Q3", "text": "It takes more effort to concentrate than it used to."},
                {"id": "S1_Q4", "text": "I lose my place when following multi-step instructions."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget where I placed everyday items around the house."},
                {"id": "S2_Q2", "text": "I forget appointments unless I write them down."},
                {"id": "S2_Q3", "text": "I struggle to recall details from conversations a few days later."},
                {"id": "S2_Q4", "text": "I forget why I started a task partway through it."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I take longer than before to work through a problem."},
                {"id": "S3_Q2", "text": "I feel less confident making decisions quickly."},
                {"id": "S3_Q3", "text": "My thinking feels slower on tiring days."},
                {"id": "S3_Q4", "text": "I have to double-check my work more than I used to."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel anxious about changes in my memory or focus."},
                {"id": "S4_Q2", "text": "I feel uncertain about what retirement will look like for me."},
                {"id": "S4_Q3", "text": "I feel the impact of my social circle changing in recent years."},
                {"id": "S4_Q4", "text": "I feel low some days without a clear cause."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel stressed planning for retirement and finances."},
                {"id": "S5_Q2", "text": "I worry about new health concerns more than before."},
                {"id": "S5_Q3", "text": "I bounce back more slowly from stressful days."},
                {"id": "S5_Q4", "text": "I feel anxious about staying mentally sharp as I age."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I notice my sleep quality has declined in recent years."},
                {"id": "S6_Q2", "text": "I wake up earlier than I'd like and can't fall back asleep."},
                {"id": "S6_Q3", "text": "I feel groggy in the morning more often than before."},
                {"id": "S6_Q4", "text": "I find naps necessary to get through the day."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I take longer to complete everyday tasks than I used to."},
                {"id": "S7_Q2", "text": "I need more breaks to stay productive."},
                {"id": "S7_Q3", "text": "My energy for tasks fades earlier in the day."},
                {"id": "S7_Q4", "text": "I have to work at keeping my mind active and engaged."},
            ]
        },
    ],
    "senior_adult": [
        {
            "id": "S1",
            "title": "Focus & Attention",
            "items": [
                {"id": "S1_Q1", "text": "I find it hard to focus on one thing at a time."},
                {"id": "S1_Q2", "text": "I get distracted easily when doing daily tasks."},
                {"id": "S1_Q3", "text": "I lose focus during long conversations or TV shows."},
                {"id": "S1_Q4", "text": "I struggle to concentrate in noisy or busy places."},
            ]
        },
        {
            "id": "S2",
            "title": "Memory Function",
            "items": [
                {"id": "S2_Q1", "text": "I forget names of people I have met before."},
                {"id": "S2_Q2", "text": "I forget where I put things around the house."},
                {"id": "S2_Q3", "text": "I forget appointments unless someone reminds me."},
                {"id": "S2_Q4", "text": "I forget parts of conversations from earlier that day."},
            ]
        },
        {
            "id": "S3",
            "title": "Mental Clarity & Decision-Making",
            "items": [
                {"id": "S3_Q1", "text": "I take longer to make simple decisions now."},
                {"id": "S3_Q2", "text": "I feel confused following multi-step instructions."},
                {"id": "S3_Q3", "text": "I struggle to find the right word when speaking."},
                {"id": "S3_Q4", "text": "I feel unsure handling new or unfamiliar tasks."},
            ]
        },
        {
            "id": "S4",
            "title": "Emotional Well-being",
            "items": [
                {"id": "S4_Q1", "text": "I feel lonely since losing friends or loved ones."},
                {"id": "S4_Q2", "text": "I worry about losing my independence."},
                {"id": "S4_Q3", "text": "I feel low or down without clear reason."},
                {"id": "S4_Q4", "text": "I feel anxious about changes in my health."},
            ]
        },
        {
            "id": "S5",
            "title": "Stress & Resilience",
            "items": [
                {"id": "S5_Q1", "text": "I feel stressed managing my health and medications."},
                {"id": "S5_Q2", "text": "I feel overwhelmed by changes in my daily routine."},
                {"id": "S5_Q3", "text": "I feel anxious about staying independent as I age."},
                {"id": "S5_Q4", "text": "I take longer to feel better after a hard day."},
            ]
        },
        {
            "id": "S6",
            "title": "Sleep & Recovery",
            "items": [
                {"id": "S6_Q1", "text": "I wake up several times during the night."},
                {"id": "S6_Q2", "text": "I feel tired even after a full night's sleep."},
                {"id": "S6_Q3", "text": "I have trouble falling asleep most nights."},
                {"id": "S6_Q4", "text": "I feel groggy or foggy in the morning."},
            ]
        },
        {
            "id": "S7",
            "title": "Productivity & Performance",
            "items": [
                {"id": "S7_Q1", "text": "I struggle to complete daily tasks I used to manage easily."},
                {"id": "S7_Q2", "text": "I find new technology confusing or overwhelming."},
                {"id": "S7_Q3", "text": "I avoid learning new skills or hobbies."},
                {"id": "S7_Q4", "text": "I struggle to navigate to familiar places."},
            ]
        },
    ],
}
def _static_fallback(age: int, gender: str) -> list[dict]:
    band = get_age_band(age)
    return STATIC_QUESTIONS[band]

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
