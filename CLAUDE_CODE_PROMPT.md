# Claude Code Implementation Prompt — Limitless v2 Scoring Model

> **How to use:** place this file in your Limitless project root, then paste the
> ONE-LINE COMMAND at the bottom into Claude Code. Everything above it is the spec
> Claude Code will read.

---

## CONTEXT

You are working on **Limitless AI**, a cognitive wellness self-assessment platform:
Python 3.12, FastAPI, Pydantic v2, ReportLab (canvas API only, never Platypus),
Gemini for question generation, pytest for tests.

The product asks **28 self-report questions** (7 sections × 4 items, Likert 0–4) and
returns a scored analysis plus a 10-page PDF report. This will not change — 28
questions stay 28 questions.

We are adding a **v2 scoring model** alongside the existing v1 model. v2 fixes a
credibility problem: v1 reports 8 cognitive domains, but 3 of them are fabricated
(Reaction Time is hardcoded to 70 for every user; Language Skills and Problem Solving
are 70 ± 5 derivations; Processing Speed is Mental Clarity × 0.9).

---

## NON-NEGOTIABLE RULES

1. **v1 must keep working exactly as it does today.** Do not delete, rewrite, or
   change the behaviour of any existing scoring function, model, mapper function, or
   PDF drawing function. v2 is additive and parallel.
2. **Everything is behind a feature flag.** Add `SCORING_MODEL_VERSION` to
   `app/core/config.py`, default `"v1"`. When it is `"v1"`, output must be
   byte-identical to today's output.
3. **All existing tests must still pass, unmodified.** If an existing test fails,
   stop and report it. Never edit an existing test to make it pass.
4. **The PDF layout is CEO-approved.** Do not reorder pages, change page count,
   restructure any page, or alter the visual design. Only the changes explicitly
   listed in Phase 4 are permitted.
5. **ReportLab canvas only.** Never introduce SimpleDocTemplate, Paragraph, or Spacer.
6. **Pydantic v2 only.** `model_dump()` not `.dict()`; `field_validator` /
   `model_validator(mode="after")` not `@validator`.
7. Do not add new third-party dependencies. Standard library plus what is already in
   `requirements.txt`.
8. If any instruction here conflicts with existing working code, **stop and ask**
   rather than guessing.

---

## PHASE 1 — Configuration and flags

In `app/core/config.py` add these settings (all with safe defaults):

```
SCORING_MODEL_VERSION      = "v1"      # "v1" | "v2"
ENABLE_CONFIDENCE_INTERVALS = False
ENABLE_VALIDITY_CHECKS      = False
ENABLE_RELIABLE_CHANGE      = False
ENABLE_METHODOLOGY_PAGE     = False
ITEM_BANK_VERSION           = "items_v1.0"
```

Read them from environment variables with these values as fallbacks, matching how
existing settings in that file are read.

---

## PHASE 2 — v2 scoring engine (new file)

Create `app/scoring/engine_v2.py`. **Do not modify `app/scoring/engine.py`.**

Reuse from v1 by importing: `get_age_band`, `parse_responses`,
`compute_section_averages`, `normalize_invert`. Do not duplicate that logic.

### 2.1 Seven scales

v2 reports one scale per section, no proxies. Section → scale mapping:

| Section | v2 scale key | Display name |
|---------|--------------|--------------|
| S1 | `attentionFocus` | Attention & Focus |
| S2 | `memoryRecall` | Memory & Recall |
| S3 | `executiveFunction` | Executive Function |
| S4 | `mentalEnergy` | Mental Energy |
| S5 | `stressLoad` | Stress & Emotional Load |
| S6 | `sleepRecovery` | Sleep & Recovery |
| S7 | `lifestyleModule` | Lifestyle Module |

Scale score = the section score (normalize + invert), exactly as v1 computes section
scores. No proxy maths, no clamping tricks, no invented constants.

**Note:** section *content* is being redesigned separately (S3 becomes Executive
Function, S4 becomes Mental Energy, etc.). That is an item-authoring change, not a
code change. Your job is to map section index → scale key as in the table above.

### 2.2 Composite indices

```
cognitiveComplaintIndex = mean(S1, S2, S3)     # 12 items
modifiableLoadIndex     = mean(S4, S5, S6)     # 12 items
```

### 2.3 Overall score

Weighted average of the seven scales:

```
attentionFocus     0.20
memoryRecall       0.20
executiveFunction  0.18
mentalEnergy       0.14
sleepRecovery      0.13
stressLoad         0.10
lifestyleModule    0.05
```

Rating bands unchanged from v1: 85+ Excellent, 70–84 Good, 50–69 Needs Attention,
below 50 At Risk.

### 2.4 Confidence intervals (SEM)

Provisional constants — put them in clearly-named module-level constants with a
comment stating they are provisional and pending empirical calibration:

```
SCALE_SD          = 18.0   # provisional
SCALE_ALPHA       = 0.75   # provisional, 4-item scale
COMPOSITE_SD      = 15.0   # provisional
COMPOSITE_ALPHA   = 0.85   # provisional, 12-item composite
```

```
SEM = SD * sqrt(1 - alpha)
interval = ±1.96 * SEM      # 95%
```

Return per scale: `score`, `sem`, `ciLow`, `ciHigh` (clamped to 0–100, rounded to 1dp).

### 2.5 Cognitive age (rebased)

Replace v1's arbitrary anchor of 70 with an expected-score-by-age curve:

```
expected_score(age) = 78.0 - 0.25 * (age - 18)     # provisional curve
```

```
deviation      = overall_score - expected_score(age)
cognitive_age  = age - (deviation / 2.5)
cognitive_age  = clamp(cognitive_age, 18, 80)
band           = ±3 years  ->  ageLow, ageHigh
```

Keep the current behaviour of returning `None` below age 43 (the PDF depends on it),
but implement it as a config-readable threshold `COGNITIVE_AGE_MIN_AGE = 43` so it can
be changed later without touching logic.

Every cognitive-age output must carry:
`"provisional": True` and a disclaimer string stating it is a provisional wellness
index, not a clinical measure of brain age.

### 2.6 Percentile (provisional)

Using `expected_score(age)` as the band mean and `SCALE_SD` as spread, compute an
approximate normal percentile for the overall score. Return
`{"value": int, "provisional": True}`. Do not import scipy — implement the normal CDF
with `math.erf`.

### 2.7 Response validity checks

Pure function taking the raw parsed responses (and optionally elapsed seconds):

- **straight_lining** — all 28 answers identical, or ≥ 26 of 28 identical
- **extreme_responding** — all answers are 0, or all are 4
- **speed_floor** — elapsed seconds < 90 (skip this check when elapsed time is absent)
- **reverse_inconsistency** — accept a list of reverse-coded item IDs; if a scale's
  reverse items contradict its forward items by more than 2 scale points, flag it

Return:
```
{"status": "Valid" | "Review" | "Low confidence", "flags": [...]}
```
Rule: 0 flags → Valid; 1 flag → Review; 2+ flags → Low confidence.

### 2.8 Entry point

```
def score_v2(age, gender, responses, elapsed_seconds=None, reverse_item_ids=None)
```
Returns a `ScoringResultV2` containing scales, composites, overall, cognitive age,
percentile, validity, lifestyle impacts, risk indicators, and strengths. Reuse v1's
lifestyle-impact, risk-indicator, and strengths logic where the mapping still holds;
where a v1 rule references a dropped domain, adapt it to the nearest v2 scale and
leave a comment explaining the mapping.

---

## PHASE 3 — Models and route wiring

### 3.1 Models

In `app/models/response.py`, **add** new models — do not modify existing ones:
`ScaleScore` (score, sem, ciLow, ciHigh), `ScalesV2` (7 scale fields),
`Composites`, `ValidityReport`, `CognitiveAgeV2`, `PercentileV2`.

Add to `AnalyzeResponse` as **optional fields defaulting to None**, so v1 responses
are unchanged:
```
scales:      Optional[ScalesV2]      = None
composites:  Optional[Composites]    = None
validity:    Optional[ValidityReport] = None
percentile:  Optional[PercentileV2]  = None
modelVersion: str = "v1"
```

**Backward compatibility requirement:** when v2 is active, still populate the existing
`domains` object so the current PDF and frontend keep working. Map the 7 v2 scales
onto the existing domain keys, and for the three dropped domains
(`languageSkills`, `problemSolving`, `reactionTime`) populate them from the closest
v2 scale rather than inventing values — add a code comment marking these as
transitional shims to be removed when the PDF fully migrates.

### 3.2 Route

In `app/api/routes/analyze.py`, branch on `SCORING_MODEL_VERSION`: call `score()`
for v1, `score_v2()` for v2. Everything else in the route stays as-is. Accept two new
**optional** request fields: `elapsedSeconds: Optional[int]` and
`itemBankVersion: Optional[str]`.

---

## PHASE 4 — PDF changes (STRICTLY LIMITED)

Only these five changes. Nothing else in `pdf_service.py` may be touched. Each must
be guarded so that when its flag is off, the page renders exactly as it does today.

1. **Radar chart** — when v2 is active, feed 7 scales with v2 labels instead of 8
   domains. Same chart function, same position, same styling.
2. **Scale bars** — when `ENABLE_CONFIDENCE_INTERVALS` is on, draw a thin error band
   on each bar and render the value as `62 ± 6`. Same bar layout and colours.
3. **Cognitive Age page** — same ring, same big number. Add the range beneath it
   (`Range: 41–46`) and a single small footnote line with the provisional
   disclaimer. Do not restructure the page.
4. **Progress page** — add ONE column to the existing delta table: a reliable-change
   flag (`Reliable improvement` / `Reliable decline` / `Within normal variation`).
   Do not change the existing columns.
5. **Response quality badge** — when `ENABLE_VALIDITY_CHECKS` is on, draw a small
   `draw_tag()` badge in the footer area of page 1 showing the validity status.
   Use SUCCESS for Valid, WARNING for Review, DANGER for Low confidence.

**Optional, only if `ENABLE_METHODOLOGY_PAGE` is on:** append ONE new page at the very
end covering scale definitions, item bank version, scoring formula, provisional-values
notice, and limitations. It must append after the existing final page and never alter
page order.

**Reminder:** `report_mapper.py` computes, `pdf_service.py` only draws. Do not put
computation in drawing functions.

---

## PHASE 5 — Reliable Change Index (longitudinal engine)

In `app/services/longitudinal_engine.py`, add RCI without changing existing outputs.

```
SE_diff   = sqrt(2) * SEM
RCI       = (current - previous) / SE_diff
```
`|RCI| >= 1.96` → reliable change; otherwise within normal variation.

Because 4-item scales are noisy, apply RCI flags primarily to the **12-item
composites**, and mark individual scales as directional only. Include a code comment
explaining this.

Add to the response payload, additively:
```
"reliable_change": {
  "cognitiveComplaintIndex": {"delta": ..., "rci": ..., "flag": "..."},
  "modifiableLoadIndex":     {...},
  "overall":                 {...}
}
```
Also add `MIN_RETEST_INTERVAL_DAYS = 14` and, when two sessions fall closer together
than that, set a `"retest_interval_warning": true` field. Do not block the request.

---

## PHASE 6 — Tests

Create `tests/test_engine_v2.py` and `tests/test_validity.py`. Do not modify existing
test files.

Cover at minimum:
- With the flag at `"v1"`, output is identical to current behaviour (regression guard)
- v2 returns exactly 7 scales, all between 0 and 100
- v2 weights sum to 1.0
- Composites equal the mean of their constituent scales
- Confidence intervals are ordered `ciLow <= score <= ciHigh` and clamp at 0/100
- Cognitive age returns None below 43, an integer with a range at 43+
- Percentile stays within 1–99
- Straight-lined responses produce `Low confidence` or `Review`
- Valid varied responses produce `Valid`
- RCI flags reliable change only above the 1.96 threshold
- PDF generates successfully with v2 active and with every flag on
- PDF generates successfully with v2 active and every flag off

---

## VERIFICATION (run at the end, report results)

```bash
python -m py_compile $(git ls-files '*.py')
python -m pytest tests/ -v
```

Then confirm explicitly:
1. All pre-existing tests pass, unmodified.
2. With `SCORING_MODEL_VERSION=v1`, `/analyze` output is unchanged from before.
3. With `SCORING_MODEL_VERSION=v2`, `/analyze` returns scales, composites, validity,
   and percentile, and still populates `domains` for backward compatibility.
4. PDF generates in both modes without error.
5. No existing function was modified in a way that changes v1 behaviour.

---

## WHAT NOT TO DO

- Do not write the new question items. Item authoring is a separate human-reviewed
  process. Assume the existing 28-item structure and slot IDs (`S1_Q1` … `S7_Q4`).
- Do not delete the v1 engine, v1 domains, or any existing PDF page.
- Do not change the Gemini question generator in this pass.
- Do not restructure `report_mapper.py`; only add new keys.
- Do not add a database, ORM, or storage layer in this pass.

---

## ONE-LINE COMMAND FOR CLAUDE CODE

> Read CLAUDE_CODE_PROMPT.md in the project root and implement Phases 1 through 6 in
> order. Follow every non-negotiable rule exactly: v1 behaviour must remain identical,
> everything ships behind feature flags defaulting to off, no existing test may be
> modified, and PDF changes are limited to the five listed in Phase 4. After each
> phase, run the test suite and report status before continuing. If anything in the
> spec conflicts with the existing code, stop and ask me rather than guessing.
