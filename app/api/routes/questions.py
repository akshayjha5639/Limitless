"""
Limitless — POST /generate-questions Route
Uses Gemini API to generate age/gender-tailored questions.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from enum import Enum

from app.services.question_generator import generate_questions

router = APIRouter()


class GenderEnum(str, Enum):
    male             = "male"
    female           = "female"
    non_binary       = "non_binary"
    prefer_not_to_say = "prefer_not_to_say"


class GenerateQuestionsRequest(BaseModel):
    age:    int        = Field(..., ge=18, le=66)
    gender: GenderEnum
    locale: str        = Field(default="en")


@router.post("/generate-questions")
async def generate_questions_route(payload: GenerateQuestionsRequest):
    """
    Accepts age + gender. Returns a Gemini-generated 28-item questionnaire
    tailored to the user's life stage and gender context.
    Falls back to static questions if Gemini is unavailable.
    """
    # Normalize gender value for prompt context
    gender_str = payload.gender.value.replace("_", "-")

    try:
        sections, is_ai = generate_questions(
            age=payload.age,
            gender=gender_str,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "assessmentId":  str(uuid.uuid4()),
        "scale":         "0-4",
        "scaleLabels":   {
            "0": "Never / Rarely",
            "1": "Rarely",
            "2": "Sometimes",
            "3": "Often",
            "4": "Very Often / Severe",
        },
        "sections":      sections,
        "metadata": {
            "version":      "1.0",
            "createdAt":    datetime.now(timezone.utc).isoformat(),
            "aiGenerated":  is_ai,
            "model":        "gemini-2.0-flash" if is_ai else "static-fallback",
        },
    }
