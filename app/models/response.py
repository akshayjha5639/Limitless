"""
Limitless — Pydantic Response Models
Mirrors the full /analyze output schema from the technical spec.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RatingBand(str, Enum):
    EXCELLENT       = "Excellent"
    GOOD            = "Good"
    NEEDS_ATTENTION = "Needs Attention"
    AT_RISK         = "At Risk"

class ImpactLevel(str, Enum):
    HIGH     = "High"
    MODERATE = "Moderate"
    LOW      = "Low"
    INSUFFICIENT = "Insufficient data"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class OverallScore(BaseModel):
    score:  float = Field(..., ge=0, le=100)
    rating: RatingBand


class DomainScores(BaseModel):
    memory:             float = Field(..., ge=0, le=100)
    attentionFocus:     float = Field(..., ge=0, le=100)
    processingSpeed:    float = Field(..., ge=0, le=100)
    executiveFunction:  float = Field(..., ge=0, le=100)
    mentalClarity:      float = Field(..., ge=0, le=100)
    languageSkills:     float = Field(..., ge=0, le=100)
    problemSolving:     float = Field(..., ge=0, le=100)
    reactionTime:       float = Field(..., ge=0, le=100)


class LifestyleImpacts(BaseModel):
    sleepQualityImpact: ImpactLevel
    stressLevelImpact:  ImpactLevel
    anxietyLoadImpact:  ImpactLevel
    burnoutRiskImpact:  ImpactLevel


class CognitiveAge(BaseModel):
    actualAge:              int
    estimatedCognitiveAge:  Optional[int] = Field(
        default=None,
        description="None for Phase 1 (18–25 cohort). Heuristic not meaningful at this age range."
    )
    disclaimer: str = Field(
        default="Motivational wellness metric only — not a clinical measurement."
    )


class ProgressDelta(BaseModel):
    domain:     str
    previous:   float
    current:    float
    delta:      float           # positive = improvement
    direction:  str             # "improved" | "declined" | "stable"


class Progress(BaseModel):
    available:  bool = False
    deltas:     list[ProgressDelta] = Field(default_factory=list)


class RadarChartData(BaseModel):
    labels: list[str]   # domain names
    values: list[float] # 0–100 scores, same order as labels


class BarChartData(BaseModel):
    labels: list[str]   # lifestyle factor names
    values: list[float] # impact scores (lower = higher impact)


class ChartData(BaseModel):
    radarDomains:       RadarChartData
    barLifestyleImpacts: BarChartData


class AuditInfo(BaseModel):
    rules_version:          str = "1.0"
    age_cohort:             str = "18-25"
    clamped_values:         list[str] = Field(default_factory=list)
    imputation_notes:       list[str] = Field(default_factory=list)
    insufficient_sections:  list[str] = Field(default_factory=list)


class PrivacyInfo(BaseModel):
    dataCollected:  list[str] = Field(default=["age", "gender", "assessment_responses"])
    storagePolicy:  str = Field(default="Responses not stored unless user explicitly opts in.")
    hipaaNote:      str = Field(default="HIPAA safeguards apply when deployed in US healthcare context.")


# ---------------------------------------------------------------------------
# Root response model
# ---------------------------------------------------------------------------

MANDATORY_DISCLAIMERS = [
    "This is a wellness screening tool, not a diagnosis.",
    "Not intended to replace professional medical advice.",
    "Seek a licensed clinician for persistent symptoms.",
]

class AnalyzeResponse(BaseModel):
    assessmentId:       str
    overall:            OverallScore
    domains:            DomainScores
    lifestyleImpacts:   LifestyleImpacts
    riskIndicators:     list[str]       = Field(default_factory=list)
    cognitiveAge:       CognitiveAge
    strengths:          list[str]       = Field(default_factory=list)
    recommendations:    list[str]       = Field(default_factory=list)
    progress:           Progress        = Field(default_factory=Progress)
    charts:             ChartData
    audit:              AuditInfo       = Field(default_factory=AuditInfo)
    disclaimers:        list[str]       = Field(default=MANDATORY_DISCLAIMERS)
    privacy:            PrivacyInfo     = Field(default_factory=PrivacyInfo)

class QuestionItem(BaseModel):
    id: str
    text: str

class Section(BaseModel):
    id: str
    title: str
    items: list[QuestionItem]

class AssessmentMetadata(BaseModel):
    version: str
    createdAt: str

class GenerateQuestionsResponse(BaseModel):
    assessmentId: str = Field(..., description="UUID v4 for this assessment session")
    scale: str = Field(default="0-4")
    sections: list[Section]
    metadata: AssessmentMetadata