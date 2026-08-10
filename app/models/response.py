"""
Limitless — Pydantic Response Models
Mirrors the full /analyze output schema from the technical spec.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with Z suffix (PRD §3.1 session_timestamp)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        description="Estimated age according the performation on the assessment."
    )
    disclaimer: str = Field(
        default="Motivational wellness metric only — not a clinical measurement."
    )


# ---------------------------------------------------------------------------
# v2 scoring model — additive sub-models (v1 models above are untouched)
# ---------------------------------------------------------------------------

class ScaleScore(BaseModel):
    score:  float = Field(..., ge=0, le=100)
    sem:    float = Field(..., ge=0)
    ciLow:  float = Field(..., ge=0, le=100)
    ciHigh: float = Field(..., ge=0, le=100)


class ScalesV2(BaseModel):
    attentionFocus:     ScaleScore
    memoryRecall:        ScaleScore
    executiveFunction:   ScaleScore
    mentalEnergy:        ScaleScore
    stressLoad:          ScaleScore
    sleepRecovery:       ScaleScore
    lifestyleModule:     ScaleScore


class Composites(BaseModel):
    cognitiveComplaintIndex: ScaleScore
    modifiableLoadIndex:     ScaleScore


class ValidityReport(BaseModel):
    status: str
    flags:  list[str] = Field(default_factory=list)


class CognitiveAgeV2(BaseModel):
    actualAge:              int
    estimatedCognitiveAge:  Optional[int] = None
    ageLow:                 Optional[int] = None
    ageHigh:                Optional[int] = None
    provisional:            bool = True
    disclaimer:             str = Field(
        default="Provisional wellness index — not a clinical measure of brain age."
    )


class PercentileV2(BaseModel):
    value:       Optional[int] = None
    provisional: bool = True


class ReliableChangeEntry(BaseModel):
    delta: float
    rci:   float
    flag:  str


class ReliableChange(BaseModel):
    cognitiveComplaintIndex: ReliableChangeEntry
    modifiableLoadIndex:     ReliableChangeEntry
    overall:                  ReliableChangeEntry


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
    sessionTimestamp:   str = Field(
        default_factory=_utc_now_iso,
        description="ISO-8601 UTC completion time — required by the "
                    "longitudinal tracking engine for velocity math.",
    )
    name:                Optional[str] = None
    gender:              Optional[str] = None
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

    # --- v2 scoring model — additive, optional, default None so v1 responses
    #     are byte-for-byte unchanged when SCORING_MODEL_VERSION="v1" ---
    scales:          Optional[ScalesV2]      = None
    composites:      Optional[Composites]    = None
    validity:        Optional[ValidityReport] = None
    percentile:      Optional[PercentileV2]  = None
    cognitiveAgeV2:  Optional[CognitiveAgeV2] = None
    modelVersion:    str = "v1"

    # --- Phase 5, additive — two-point RCI vs priorReport (v2-only, feeds
    #     the PDF Progress page); None/False unless both reports are v2 ---
    reliableChange:        Optional[ReliableChange] = None
    retestIntervalWarning: bool = False

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