"""
Limitless — POST /longitudinal-analysis Route
Ingests the client-held assessment history (JSON-only) and returns the
full longitudinal telemetry payload defined in PRD v1.0.0 §5.
"""

from fastapi import APIRouter, HTTPException

from app.models.longitudinal import LongitudinalRequest, LongitudinalResponse
from app.services.longitudinal_engine import run_longitudinal_analysis

router = APIRouter()


@router.post("/longitudinal-analysis", response_model=LongitudinalResponse)
async def longitudinal_analysis(request: LongitudinalRequest) -> LongitudinalResponse:
    """
    Longitudinal Cognitive Tracking Engine.

    Accepts >= 2 stored /analyze responses (each with a session timestamp)
    and returns trajectories, per-domain trends, the gated lifestyle
    attribution matrix, 30/60/90-day projections, and rule-based insights.
    """
    history = [record.model_dump() for record in request.history]

    try:
        payload = run_longitudinal_analysis(history, user_id=request.userId)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return LongitudinalResponse(**payload)
