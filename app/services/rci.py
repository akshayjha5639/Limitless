"""
Limitless — Reliable Change Index (RCI)

Shared, dependency-free (stdlib-only) RCI math used by both:
  - app/services/longitudinal_engine.py (/longitudinal-analysis payload,
    compares the two most recent sessions in a history array)
  - app/api/routes/analyze.py (single priorReport vs current comparison,
    feeds the Phase 4 PDF Progress page)

One shared helper so the formula is defined exactly once.

RCI (Jacobson & Truax, 1991):
    SE_diff = sqrt(2) * SEM
    RCI     = (current - previous) / SE_diff
    |RCI| >= 1.96 -> reliable change at 95% confidence
"""

import math

RCI_THRESHOLD = 1.96
MIN_RETEST_INTERVAL_DAYS = 14


def compute_rci(current: float, previous: float, sem: float) -> dict:
    """Returns {"delta", "rci", "flag"} for one score pair + its SEM."""
    delta = round(current - previous, 2)
    se_diff = math.sqrt(2) * sem
    rci = round(delta / se_diff, 2) if se_diff else 0.0

    if rci >= RCI_THRESHOLD:
        flag = "Reliable improvement"
    elif rci <= -RCI_THRESHOLD:
        flag = "Reliable decline"
    else:
        flag = "Within normal variation"

    return {"delta": delta, "rci": rci, "flag": flag}
