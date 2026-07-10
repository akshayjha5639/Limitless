"""
Limitless — Longitudinal Analysis Models
Request/response schemas for POST /api/v1/longitudinal-analysis (PRD v1.0.0).

The frontend keeps an array of past /analyze responses in localStorage
("reportHistory") and posts the whole array here. No server-side storage.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class HistoryRecord(BaseModel):
    sessionTimestamp: Optional[str] = Field(
        default=None,
        description=(
            "ISO-8601 completion time. Optional here only because newer "
            "/analyze responses embed their own sessionTimestamp — one of "
            "the two must be present or the request is rejected."
        ),
    )
    analysis: dict = Field(
        ..., description="Full JSON object returned by /analyze"
    )


class LongitudinalRequest(BaseModel):
    userId: Optional[str] = Field(
        default=None,
        description="Optional client-side identifier echoed back in the payload",
    )
    history: list[HistoryRecord] = Field(
        ..., min_length=2, max_length=100,
        description="Chronological (any order accepted) list of past assessments",
    )


# ---------------------------------------------------------------------------
# Response (PRD §5 payload)
# ---------------------------------------------------------------------------

class OverallTrajectory(BaseModel):
    direction: str                              # improving | declining | stable
    velocity_score_per_day: float
    baseline_overall_score: float
    latest_overall_score: float


class DomainTrend(BaseModel):
    historical_values: list[float]
    net_delta: float
    velocity_score_per_day: float
    status: str
    # requires_immediate_intervention | declining_moderate | stable
    # | improving_gradual | improving_strong


class LongitudinalTelemetry(BaseModel):
    overall_trajectory: OverallTrajectory
    domain_trends: dict[str, DomainTrend]
    lifestyle_attribution_matrix: dict[str, float] = Field(
        default_factory=dict,
        description="Empty when fewer than 4 sessions exist (gated).",
    )
    attribution_available: bool = False


class ContextualInsights(BaseModel):
    primary_bottleneck: str
    dynamic_recommendations: list[str]


class LongitudinalResponse(BaseModel):
    user_id: str
    aggregation_timestamp: str
    historical_data_points_analyzed: int
    session_timestamps: list[str]
    longitudinal_telemetry: LongitudinalTelemetry
    predictive_projections_calibrated: dict[str, float]
    contextual_ai_insights: ContextualInsights
