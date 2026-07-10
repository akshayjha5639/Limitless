"""
Limitless — Longitudinal Cognitive Tracking Engine
Implements the Technical Architecture & PRD v1.0.0 (July 2026):

  1. Unified schema normalization  (PRD §3 — invariant score_* keys)
  2. Time-series velocity analytics (PRD §4.1 — time-delta scaled, smoothed)
  3. Lifestyle → cognitive attribution (PRD §4.2 — gated at >= 4 sessions)
  4. Calibrated 30/60/90-day projections (no-action vs with-recommendations)
  5. Rule-based contextual insights (deterministic, no LLM call)

Design decisions (confirmed with product owner, July 2026):
  * Ingestion is JSON-only. Each history record is a stored /analyze
    response (plus a session timestamp). No PDF parsing.
  * Lifestyle categorical tags use WELLNESS semantics, matching the rest
    of the codebase: High impact -> 30.0, Moderate -> 60.0, Low -> 85.0.
    (Higher normalized value = healthier, consistent with score_* keys.
    Attribution coefficients therefore trend POSITIVE when lifestyle
    improvement tracks cognitive improvement.)
  * Attribution matrix is returned only when >= MIN_ATTRIBUTION_POINTS
    sessions are available; below that it is empty (coefficients from
    2-3 samples are statistical noise).

This module is intentionally dependency-free (stdlib only) so the maths
can be unit-tested without FastAPI/Pydantic installed.
"""

from datetime import datetime, timezone


# ============================================================
# CONSTANTS
# ============================================================

# PRD §3.2 — invariant key <- dashboard payload key
DOMAIN_KEY_MAP = {
    "memory":            "score_memory",
    "attentionFocus":    "score_attention",
    "processingSpeed":   "score_processing_speed",
    "executiveFunction": "score_executive_function",
    "mentalClarity":     "score_clarity",
    "languageSkills":    "score_language",
    "problemSolving":    "score_problem_solving",
    "reactionTime":      "score_reaction_time",
}

# Short trend keys used in the telemetry payload (PRD §5 example uses
# "memory", "executive_function" — snake_case without the score_ prefix).
DOMAIN_TREND_KEY = {
    "memory":            "memory",
    "attentionFocus":    "attention",
    "processingSpeed":   "processing_speed",
    "executiveFunction": "executive_function",
    "mentalClarity":     "clarity",
    "languageSkills":    "language",
    "problemSolving":    "problem_solving",
    "reactionTime":      "reaction_time",
}

DOMAIN_DISPLAY = {
    "memory": "Memory",              "attentionFocus": "Attention",
    "processingSpeed": "Processing", "executiveFunction": "Executive function",
    "mentalClarity": "Mental clarity", "languageSkills": "Language",
    "problemSolving": "Problem solving", "reactionTime": "Reaction time",
}

# PRD §3.3 — lifestyle vectors (dashboard key -> invariant key)
LIFESTYLE_KEY_MAP = {
    "sleepQualityImpact": "lifestyle_sleep",
    "stressLevelImpact":  "lifestyle_stress",
    "anxietyLoadImpact":  "lifestyle_anxiety",
    "burnoutRiskImpact":  "lifestyle_burnout",
}

# Wellness semantics — consistent with report_mapper.impact_to_score()
# and analyze._build_chart_data(). Higher = healthier.
IMPACT_TO_WELLNESS = {
    "High":              30.0,
    "Moderate":          60.0,
    "Medium":            60.0,
    "Low":               85.0,
    "Very High":         15.0,
    "Insufficient data": 50.0,
}

# Attribution pairs (lifestyle invariant key -> domain dashboard key).
# Mirrors the cross-feature dependencies the product already models in
# report_mapper.generate_risk_prediction().
ATTRIBUTION_PAIRS = [
    ("lifestyle_sleep",   "memory",            "sleep_to_memory_coefficient"),
    ("lifestyle_stress",  "attentionFocus",    "stress_to_attention_coefficient"),
    ("lifestyle_burnout", "executiveFunction", "burnout_to_executive_coefficient"),
    ("lifestyle_anxiety", "mentalClarity",     "anxiety_to_clarity_coefficient"),
]

MIN_HISTORY_POINTS     = 2   # velocity needs at least one interval
MIN_ATTRIBUTION_POINTS = 4   # below this, coefficients are noise
VELOCITY_WINDOW        = 3   # smoothing window (last N pairwise velocities)
MIN_DELTA_DAYS         = 1.0 / 24.0  # floor Δt at 1 hour to avoid div-by-~0

STABLE_BAND = 1.5            # |net delta| <= 1.5 -> stable (matches progress.py)

# Age-band improvement boost — identical table to
# report_mapper.generate_risk_prediction() so projections stay consistent
# across the product.
PROJECTION_BOOST = {
    "young_adult":            22,
    "emerging_professional":  20,
    "established_adult":      18,
    "mid_career":             16,
    "midlife_transition":     14,
    "pre_senior":             12,
    "senior_adult":           10,
}


# ============================================================
# HELPERS
# ============================================================

def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def parse_timestamp(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp ('Z' suffix supported). Raises ValueError."""
    if not isinstance(ts, str) or not ts.strip():
        raise ValueError("sessionTimestamp must be a non-empty ISO-8601 string")
    dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _get_age_band(age: int) -> str:
    """Local copy of the 7-band table (avoids importing the scoring engine,
    which pulls in Pydantic — keeping this module stdlib-only)."""
    if age <= 25: return "young_adult"
    if age <= 32: return "emerging_professional"
    if age <= 37: return "established_adult"
    if age <= 42: return "mid_career"
    if age <= 47: return "midlife_transition"
    if age <= 55: return "pre_senior"
    return "senior_adult"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation of two equal-length series. None if degenerate."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sxx = sum(d * d for d in dx)
    syy = sum(d * d for d in dy)
    if sxx == 0 or syy == 0:
        return None  # zero variance -> correlation undefined
    sxy = sum(a * b for a, b in zip(dx, dy))
    return round(sxy / (sxx ** 0.5 * syy ** 0.5), 2)


# ============================================================
# 1. SCHEMA NORMALIZATION (PRD §3)
# ============================================================

def normalize_session(record: dict) -> dict:
    """
    Normalize one history record into the invariant schema vector.

    Input record shape (from the frontend's localStorage array):
        {
          "sessionTimestamp": "2026-07-07T10:33:00Z",   # or inside analysis
          "analysis": { ...full /analyze response... }
        }
    A bare /analyze response containing its own sessionTimestamp is also
    accepted.

    Returns:
        {
          "session_timestamp": ISO string,
          "_dt": datetime (internal, for sorting/velocity),
          "chronological_age": int,
          "overall_score": float,
          "score_memory": float, ... (8 invariant domain keys),
          "lifestyle_sleep": float, ... (4 invariant lifestyle keys),
        }

    Raises ValueError with a human-readable message on malformed records.
    """
    if not isinstance(record, dict):
        raise ValueError("history record must be an object")

    analysis = record.get("analysis", record)
    if not isinstance(analysis, dict):
        raise ValueError("'analysis' must be an object")

    ts_raw = record.get("sessionTimestamp") or analysis.get("sessionTimestamp")
    if not ts_raw:
        raise ValueError(
            "record is missing 'sessionTimestamp' (needed for velocity math)"
        )
    dt = parse_timestamp(ts_raw)

    domains = analysis.get("domains")
    if not isinstance(domains, dict):
        raise ValueError("analysis is missing 'domains'")

    out = {
        "session_timestamp": dt.isoformat().replace("+00:00", "Z"),
        "_dt": dt,
        "chronological_age": int(
            (analysis.get("cognitiveAge") or {}).get("actualAge") or 0
        ),
        "overall_score": _clamp(float(
            (analysis.get("overall") or {}).get("score") or 0.0
        )),
    }

    for dash_key, invariant_key in DOMAIN_KEY_MAP.items():
        val = domains.get(dash_key)
        if val is None:
            raise ValueError(f"analysis.domains is missing '{dash_key}'")
        out[invariant_key] = _clamp(float(val))

    impacts = analysis.get("lifestyleImpacts") or {}
    for dash_key, invariant_key in LIFESTYLE_KEY_MAP.items():
        raw = impacts.get(dash_key)
        if isinstance(raw, (int, float)):          # already numeric
            out[invariant_key] = _clamp(float(raw))
        else:                                       # categorical tag
            out[invariant_key] = IMPACT_TO_WELLNESS.get(str(raw), 50.0)

    return out


def normalize_history(history: list[dict]) -> list[dict]:
    """Normalize + chronologically sort the full history (oldest first)."""
    if not isinstance(history, list) or len(history) < MIN_HISTORY_POINTS:
        raise ValueError(
            f"at least {MIN_HISTORY_POINTS} history records are required "
            f"for longitudinal analysis (got {len(history) if isinstance(history, list) else 0})"
        )
    normalized = []
    for i, record in enumerate(history):
        try:
            normalized.append(normalize_session(record))
        except ValueError as e:
            raise ValueError(f"history[{i}]: {e}")
    normalized.sort(key=lambda s: s["_dt"])
    return normalized


# ============================================================
# 2. TIME-SERIES VELOCITY ANALYTICS (PRD §4.1)
# ============================================================

def _pairwise_velocities(sessions: list[dict], key: str) -> list[float]:
    """v_i = (S_i - S_{i-1}) / Δt_days, with Δt floored at 1 hour."""
    velocities = []
    for prev, curr in zip(sessions, sessions[1:]):
        dt_days = (curr["_dt"] - prev["_dt"]).total_seconds() / 86400.0
        dt_days = max(dt_days, MIN_DELTA_DAYS)
        velocities.append((curr[key] - prev[key]) / dt_days)
    return velocities


def smoothed_velocity(sessions: list[dict], key: str) -> float:
    """Mean of the last VELOCITY_WINDOW pairwise velocities (per day)."""
    velocities = _pairwise_velocities(sessions, key)
    window = velocities[-VELOCITY_WINDOW:]
    return round(sum(window) / len(window), 2) if window else 0.0


def _direction(net_delta: float) -> str:
    if net_delta > STABLE_BAND:
        return "improving"
    if net_delta < -STABLE_BAND:
        return "declining"
    return "stable"


def _domain_status(net_delta: float, latest: float) -> str:
    """Classify a domain trend. Label set extends the two examples in
    PRD §5 (requires_immediate_intervention, improving_gradual)."""
    if net_delta <= -10 or (latest < 35 and net_delta < -STABLE_BAND):
        return "requires_immediate_intervention"
    if net_delta < -STABLE_BAND:
        return "declining_moderate"
    if net_delta >= 10:
        return "improving_strong"
    if net_delta > STABLE_BAND:
        return "improving_gradual"
    return "stable"


def compute_overall_trajectory(sessions: list[dict]) -> dict:
    baseline = sessions[0]["overall_score"]
    latest   = sessions[-1]["overall_score"]
    return {
        "direction": _direction(latest - baseline),
        "velocity_score_per_day": smoothed_velocity(sessions, "overall_score"),
        "baseline_overall_score": round(baseline, 2),
        "latest_overall_score":   round(latest, 2),
    }


def compute_domain_trends(sessions: list[dict]) -> dict:
    trends = {}
    for dash_key, invariant_key in DOMAIN_KEY_MAP.items():
        values = [round(s[invariant_key], 2) for s in sessions]
        net_delta = round(values[-1] - values[0], 2)
        trends[DOMAIN_TREND_KEY[dash_key]] = {
            "historical_values": values,
            "net_delta": net_delta,
            "velocity_score_per_day": smoothed_velocity(sessions, invariant_key),
            "status": _domain_status(net_delta, values[-1]),
        }
    return trends


# ============================================================
# 3. LIFESTYLE ATTRIBUTION (PRD §4.2 — gated)
# ============================================================

def compute_attribution_matrix(sessions: list[dict]) -> dict:
    """
    Pearson correlation between consecutive-session deltas of each
    lifestyle vector and its paired cognitive domain.

    Wellness semantics on both sides, so coefficients trend positive when
    lifestyle improvement tracks cognitive improvement.

    Gated: returns {} when fewer than MIN_ATTRIBUTION_POINTS sessions
    exist, or when a series has zero variance (e.g. lifestyle tag never
    changed) — no fabricated statistics.
    """
    if len(sessions) < MIN_ATTRIBUTION_POINTS:
        return {}

    matrix = {}
    for life_key, domain_dash_key, out_key in ATTRIBUTION_PAIRS:
        domain_key = DOMAIN_KEY_MAP[domain_dash_key]
        life_deltas = [
            b[life_key] - a[life_key] for a, b in zip(sessions, sessions[1:])
        ]
        dom_deltas = [
            b[domain_key] - a[domain_key] for a, b in zip(sessions, sessions[1:])
        ]
        coeff = _pearson(life_deltas, dom_deltas)
        if coeff is not None:
            matrix[out_key] = coeff
    return matrix


# ============================================================
# 4. CALIBRATED PROJECTIONS (30 / 60 / 90 DAY)
# ============================================================

def compute_projections(sessions: list[dict]) -> dict:
    """
    Deterministic projection model:

    NO ACTION      — if current smoothed velocity is negative, project it
                     forward (movement capped at 20 pts); if flat/positive,
                     apply the product's standard passive-decay factors
                     (0.97 / 0.945 / 0.92 at 30/60/90d — 90d matches the
                     0.92*..0.85 band already used in generate_risk_prediction).
    WITH RECS      — age-band boost table shared with
                     generate_risk_prediction(): 50% of boost by day 30,
                     75% by day 60, 100% + headroom recovery by day 90.
    """
    latest   = sessions[-1]["overall_score"]
    velocity = smoothed_velocity(sessions, "overall_score")
    age      = sessions[-1]["chronological_age"]
    boost    = PROJECTION_BOOST.get(_get_age_band(age), 15)

    def no_action(days: int, decay: float) -> float:
        if velocity < 0:
            drop = max(velocity * days, -20.0)      # cap projected loss
            return round(_clamp(latest + drop), 1)
        return round(_clamp(latest * decay), 1)

    def with_recs(days: int, fraction: float, headroom: float = 0.0) -> float:
        projected = latest + boost * fraction + (100 - latest) * headroom
        return round(_clamp(projected), 1)

    return {
        "days_30_no_action":             no_action(30, 0.97),
        "days_30_with_recommendations":  with_recs(30, 0.5),
        "days_60_no_action":             no_action(60, 0.945),
        "days_60_with_recommendations":  with_recs(60, 0.75),
        "days_90_no_action":             no_action(90, 0.92),
        "days_90_with_recommendations":  with_recs(90, 1.0, headroom=0.08),
    }


# ============================================================
# 5. CONTEXTUAL INSIGHTS (rule-based, deterministic)
# ============================================================

def _worst_domain(trends: dict) -> tuple[str, dict]:
    """Domain with the most negative net_delta; ties broken by lowest
    latest value."""
    def sort_key(item):
        _, t = item
        return (t["net_delta"], t["historical_values"][-1])
    return min(trends.items(), key=sort_key)


_LIFESTYLE_LABEL = {
    "lifestyle_sleep":   "compromised sleep quality",
    "lifestyle_stress":  "elevated stress load",
    "lifestyle_anxiety": "elevated anxiety load",
    "lifestyle_burnout": "a persistent high burnout index",
}

_LIFESTYLE_RECOMMENDATION = {
    "lifestyle_sleep": (
        "Escalate sleep prioritisation: protect a consistent 7-8 hour "
        "window and add micro-recovery intervals during the day."
    ),
    "lifestyle_stress": (
        "Introduce structured stress off-ramps: brief breathing or "
        "mindfulness blocks between high-demand tasks."
    ),
    "lifestyle_anxiety": (
        "Reduce ambient anxiety load: limit open loops by externalising "
        "tasks into a single trusted list each morning."
    ),
    "lifestyle_burnout": (
        "Initiate intentional work delegation to drop active decision-load "
        "below critical thresholds and schedule genuine recovery blocks."
    ),
}

_TREND_KEY_TO_DISPLAY = {
    DOMAIN_TREND_KEY[k]: v for k, v in DOMAIN_DISPLAY.items()
}


def generate_contextual_insights(
    sessions: list[dict], trends: dict, attribution: dict,
) -> dict:
    worst_key, worst = _worst_domain(trends)
    display  = _TREND_KEY_TO_DISPLAY.get(worst_key, worst_key.replace("_", " "))
    latest_v = worst["historical_values"][-1]
    latest_session = sessions[-1]

    # Lifestyle factors currently in the unhealthy zone (< 60 wellness)
    weak_factors = [
        key for key in _LIFESTYLE_LABEL
        if latest_session.get(key, 100.0) < 60.0
    ]

    # ---- primary bottleneck sentence ----
    if worst["net_delta"] < -STABLE_BAND:
        sentence = (
            f"{display} shows the sharpest deterioration "
            f"({worst['net_delta']:+.1f} pts to {latest_v:.0f})"
        )
    elif latest_v < 50:
        sentence = f"{display} is the weakest domain at {latest_v:.0f}/100"
    else:
        sentence = (
            f"No acute deterioration detected; {display} remains the "
            f"lowest-momentum domain at {latest_v:.0f}/100"
        )
    if weak_factors:
        labels = " and ".join(_LIFESTYLE_LABEL[k] for k in weak_factors[:2])
        sentence += f", coinciding with {labels}"
    primary_bottleneck = sentence + "."

    # ---- dynamic recommendations ----
    recommendations = [
        _LIFESTYLE_RECOMMENDATION[k] for k in weak_factors[:2]
    ]
    if worst["status"] == "requires_immediate_intervention":
        recommendations.insert(0, (
            f"Prioritise {display.lower()} recovery this week: schedule the "
            f"next assessment within 7-10 days to confirm the trend reverses."
        ))
    if not recommendations:
        recommendations.append(
            "Maintain current habits and reassess in 2-4 weeks to extend "
            "the trend baseline."
        )

    return {
        "primary_bottleneck": primary_bottleneck,
        "dynamic_recommendations": recommendations[:3],
    }


# ============================================================
# ENGINE ENTRY POINT
# ============================================================

def run_longitudinal_analysis(history: list[dict], user_id: str | None = None) -> dict:
    """
    Full pipeline: normalize -> trajectories -> attribution -> projections
    -> insights. Returns the PRD §5 payload.

    Raises ValueError (message is safe to surface as HTTP 422 detail).
    """
    sessions = normalize_history(history)

    trends      = compute_domain_trends(sessions)
    attribution = compute_attribution_matrix(sessions)

    return {
        "user_id": user_id or "anonymous",
        "aggregation_timestamp":
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "historical_data_points_analyzed": len(sessions),
        "session_timestamps": [s["session_timestamp"] for s in sessions],
        "longitudinal_telemetry": {
            "overall_trajectory": compute_overall_trajectory(sessions),
            "domain_trends": trends,
            "lifestyle_attribution_matrix": attribution,
            "attribution_available": bool(attribution),
        },
        "predictive_projections_calibrated": compute_projections(sessions),
        "contextual_ai_insights":
            generate_contextual_insights(sessions, trends, attribution),
    }
