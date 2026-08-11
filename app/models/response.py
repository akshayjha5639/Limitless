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


class ScaleScore(BaseModel):
    """One scored scale: the point estimate plus its measurement error.

    ciLow/ciHigh are the 95% confidence interval (score +/- 1.96 * sem).
    """
    score:  float = Field(..., ge=0, le=100)
    sem:    float = Field(..., ge=0)
    ciLow:  float = Field(..., ge=0, le=100)
    ciHigh: float = Field(..., ge=0, le=100)


class DomainScores(BaseModel):
    """The seven measured scales.

    These are the only scales the questionnaire supports. An earlier revision
    reported eight domains, four of which (processingSpeed, mentalClarity,
    languageSkills, problemSolving, reactionTime) could not be measured by
    self-report and were derived from the others; they have been removed
    rather than reported as if they were measured.
    """
    attentionFocus:     ScaleScore
    memoryRecall:       ScaleScore
    executiveFunction:  ScaleScore
    mentalEnergy:       ScaleScore
    stressLoad:         ScaleScore
    sleepRecovery:      ScaleScore
    lifestyleModule:    ScaleScore


class LifestyleImpacts(BaseModel):
    sleepQualityImpact: ImpactLevel
    stressLevelImpact:  ImpactLevel
    anxietyLoadImpact:  ImpactLevel
    burnoutRiskImpact:  ImpactLevel


class CognitiveAge(BaseModel):
    """Cognitive-age estimate with its uncertainty range.

    estimatedCognitiveAge / ageLow / ageHigh are None below
    COGNITIVE_AGE_MIN_AGE — render nothing rather than a null.
    """
    actualAge:              int
    estimatedCognitiveAge:  Optional[int] = Field(
        default=None,
        description="Estimated age according to performance on the assessment."
    )
    ageLow:                 Optional[int] = None
    ageHigh:                Optional[int] = None
    provisional:            bool = True
    disclaimer:             str = Field(
        default="Provisional wellness index — not a clinical measure of brain age."
    )


class Composites(BaseModel):
    cognitiveComplaintIndex: ScaleScore
    modifiableLoadIndex:     ScaleScore


class ValidityReport(BaseModel):
    status: str
    flags:  list[str] = Field(default_factory=list)


class Percentile(BaseModel):
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

    composites:      Composites
    validity:        ValidityReport
    percentile:      Percentile

    # --- Two-point RCI vs priorReport (feeds the PDF Progress page).
    #     None/False unless ENABLE_RELIABLE_CHANGE is on and a usable
    #     priorReport was supplied. ---
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