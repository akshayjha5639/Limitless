"""
Limitless — POST /analyze Route
Calls the scoring engine, assembles the full AnalyzeResponse.
"""

from fastapi import APIRouter, HTTPException

from app.models.request import AnalyzeRequest
from app.models.response import (
    AnalyzeResponse,
    OverallScore,
    DomainScores,
    LifestyleImpacts,
    ImpactLevel,
    CognitiveAge,
    ChartData,
    RadarChartData,
    BarChartData,
    AuditInfo,
    Progress,
    MANDATORY_DISCLAIMERS,
)
from app.scoring.engine import score as run_scoring, ScoringResult
from app.services.recommendations import build_recommendations
from app.services.progress import compute_progress

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _impact_enum(label: str) -> ImpactLevel:
    mapping = {
        "High":     ImpactLevel.HIGH,
        "Moderate": ImpactLevel.MODERATE,
        "Low":      ImpactLevel.LOW,
    }
    return mapping.get(label, ImpactLevel.INSUFFICIENT)


def _build_chart_data(domains: DomainScores, impacts: LifestyleImpacts) -> ChartData:
    radar = RadarChartData(
        labels=["Memory", "Attention & Focus", "Processing Speed", "Executive Function",
                "Mental Clarity", "Language Skills", "Problem Solving", "Reaction Time"],
        values=[
            domains.memory, domains.attentionFocus, domains.processingSpeed,
            domains.executiveFunction, domains.mentalClarity, domains.languageSkills,
            domains.problemSolving, domains.reactionTime,
        ],
    )

    # Bar chart: invert impact labels back to numeric for chart rendering
    # Lower number = higher impact (as per spec)
    impact_to_score = {ImpactLevel.HIGH: 30, ImpactLevel.MODERATE: 60, ImpactLevel.LOW: 85, ImpactLevel.INSUFFICIENT: 50}
    bar = BarChartData(
        labels=["Sleep Quality", "Stress Level", "Anxiety Load", "Burnout Risk"],
        values=[
            impact_to_score[impacts.sleepQualityImpact],
            impact_to_score[impacts.stressLevelImpact],
            impact_to_score[impacts.anxietyLoadImpact],
            impact_to_score[impacts.burnoutRiskImpact],
        ],
    )

    return ChartData(radarDomains=radar, barLifestyleImpacts=bar)


def _map_result_to_response(
    assessment_id: str,
    age: int,
    result: ScoringResult,
    prior_report: dict | None,
) -> AnalyzeResponse:
    """Maps ScoringResult → AnalyzeResponse."""

    # Domain scores (engine uses snake_case → response uses camelCase)
    ed = result.domain_scores
    domains = DomainScores(
        memory=             ed.memory,
        attentionFocus=     ed.attention_focus,
        processingSpeed=    ed.processing_speed,
        executiveFunction=  ed.executive_function,
        mentalClarity=      ed.mental_clarity,
        languageSkills=     ed.language_skills,
        problemSolving=     ed.problem_solving,
        reactionTime=       ed.reaction_time,
    )

    # Lifestyle impacts
    li = result.lifestyle_impacts
    impacts = LifestyleImpacts(
        sleepQualityImpact= _impact_enum(li.sleep_quality),
        stressLevelImpact=  _impact_enum(li.stress_level),
        anxietyLoadImpact=  _impact_enum(li.anxiety_load),
        burnoutRiskImpact=  _impact_enum(li.burnout_risk),
    )

    # Recommendations
    recommendations = build_recommendations(
        result.section_scores, result.domain_scores, result.risk_indicators,age=age
    )

    # Progress delta (only if prior report supplied)
    progress = (
        compute_progress(domains.model_dump(), prior_report)
        if prior_report else Progress(available=False)
    )

    # Audit
    raw_audit = result.audit
    audit = AuditInfo(
        rules_version=         raw_audit.get("rules_version", "1.0"),
        age_cohort=            raw_audit.get("age_cohort", "18-25"),
        clamped_values=        raw_audit.get("clamped_values", []),
        imputation_notes=      raw_audit.get("imputation_notes", []),
        insufficient_sections= raw_audit.get("insufficient_sections", []),
    )

    # Cognitive age — stubbed for 18–25 cohort
    cognitive_age = CognitiveAge(actualAge=age, estimatedCognitiveAge=result.cognitive_age)

    # Chart data
    charts = _build_chart_data(domains, impacts)

    return AnalyzeResponse(
        assessmentId=       assessment_id,
        overall=            OverallScore(score=result.overall_score, rating=result.rating),
        domains=            domains,
        lifestyleImpacts=   impacts,
        riskIndicators=     result.risk_indicators,
        cognitiveAge=       cognitive_age,
        strengths=          result.strengths,
        recommendations=    recommendations,
        progress=           progress,
        charts=             charts,
        audit=              audit,
        disclaimers=        MANDATORY_DISCLAIMERS,
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Core intelligence route.
    Accepts demographics + 28 item responses.
    Returns full cognitive wellness analysis.
    """
    responses_raw = [{"itemId": r.itemId, "value": r.value} for r in request.responses]

    try:
        result = run_scoring(
            age=request.age,
            gender=request.gender,
            responses=responses_raw,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _map_result_to_response(
        assessment_id=request.assessmentId,
        age=request.age,
        result=result,
        prior_report=request.priorReport,
    )
