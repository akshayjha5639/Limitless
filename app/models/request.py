"""
Limitless — Pydantic Request Models
Covers: /generate-questions, /analyze, /generate-pdf
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal
from uuid import UUID


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

GenderType = Literal["female", "male", "other", "prefer-not-to-say"]

VALID_ITEM_IDS = {
    f"S{s}_Q{q}" for s in range(1, 8) for q in range(1, 5)
}  # S1_Q1 … S7_Q4 (28 items)




# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------

class ResponseItem(BaseModel):
    itemId: str = Field(..., description="e.g. S1_Q1")
    value: int = Field(..., ge=0, le=4)

    @field_validator("itemId")
    @classmethod
    def item_id_must_be_valid(cls, v: str) -> str:
        if v not in VALID_ITEM_IDS:
            raise ValueError(f"Unknown itemId '{v}'. Must be S1_Q1 … S7_Q4.")
        return v


class BrandingParams(BaseModel):
    logoUrl: Optional[str] = None
    primaryColor: str = Field(default="#1E6FD9")
    accentColor: str = Field(default="#00C2CB")
    footerNote: Optional[str] = None


class AnalyzeRequest(BaseModel):
    assessmentId: str = Field(..., description="UUID from /generate-questions")
    age: int = Field(..., ge=18, le=25)
    gender: GenderType
    responses: list[ResponseItem] = Field(..., min_length=1, max_length=28)
    priorReport: Optional[dict] = Field(default=None, description="Previous analysis JSON for delta tracking")

    @model_validator(mode="after")
    def check_no_duplicate_item_ids(self) -> "AnalyzeRequest":
        seen = set()
        for r in self.responses:
            if r.itemId in seen:
                raise ValueError(f"Duplicate itemId '{r.itemId}' in responses.")
            seen.add(r.itemId)
        return self


# ---------------------------------------------------------------------------
# POST /generate-pdf
# ---------------------------------------------------------------------------

class GeneratePDFRequest(BaseModel):
    analysis: dict = Field(..., description="Full JSON object returned by /analyze")
    brand: BrandingParams = Field(default_factory=BrandingParams)
# Add at the bottom of your existing request.py
from enum import Enum

class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    non_binary = "non_binary"
    prefer_not_to_say = "prefer_not_to_say"
# ---------------------------------------------------------------------------
# POST /generate-questions
# ---------------------------------------------------------------------------

class GenerateQuestionsRequest(BaseModel):
    age: int = Field(..., ge=18, le=25, description="User age (Phase 1: 18–25 only)")
    gender: GenderEnum
    locale: str = Field(default="en", max_length=10)
