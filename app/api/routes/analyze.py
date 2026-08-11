"""
Limitless — POST /analyze Route
Calls the scoring engine, assembles the full AnalyzeResponse.
"""

import math
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.config import settings
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
    ScaleScore,
    Composites,
    ValidityReport,
    Percentile,
    ReliableChange,
    ReliableChangeEntry,
)
from app.scoring.scoring_model import (
    score_assessment as run_scoring,
    ScoringResult,
    SCALE_DISPLAY_NAMES,
    build_rule_engine_shims,
    COMPOSITE_SD,
    COMPOSITE_ALPHA,
)
from app.services.recommendations import build_recommendations
from app.services.progress import compute_progress
from app.services.rci import compute_rci, MIN_RETEST_INTERVAL_DAYS

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
    # Radar axes follow the declared scale order so the chart, the PDF and the
    # response object can never drift apart.
    radar = RadarChartData(
        labels=[SCALE_DISPLAY_NAMES[k] for k in SCALE_DISPLAY_NAMES],
        values=[getattr(domains, k).score for k in SCALE_DISPLAY_NAMES],
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


def _to_scale_score(v) -> ScaleScore:
    return ScaleScore(score=v.score, sem=v.sem, ciLow=v.ciLow, ciHigh=v.ciHigh)


def _compute_reliable_change(
    result: ScoringResult, prior_report: dict | None
) -> tuple[ReliableChange | None, bool]:
    """
    Two-point RCI between this result and a prior /analyze response
    (the same `priorReport` used by compute_progress()).

    Applied to the 12-item composites and overall score only — individual
    4-item scales are too noisy for a formal reliable-change verdict (see
    the matching note in longitudinal_engine.compute_reliable_change, which
    does the same comparison across a multi-session history array; this is
    the single-prior-report equivalent that actually feeds the PDF
    Progress page, since /generate-pdf only ever sees one /analyze response).

    None/False unless ENABLE_RELIABLE_CHANGE is on and a prior report was
    supplied that carries composite scores. Reports produced before the
    composites existed simply have no `composites` key and are skipped.
    """
    if not settings.ENABLE_RELIABLE_CHANGE or not prior_report:
        return None, False

    prior_composites = prior_report.get("composites")
    prior_overall = prior_report.get("overall")
    if not prior_composites or not prior_overall:
        return None, False

    # No dedicated overall-score SEM is defined — reuse the composite-level
    # provisional constants as the nearest available proxy.
    overall_sem = COMPOSITE_SD * math.sqrt(1 - COMPOSITE_ALPHA)

    try:
        reliable_change = ReliableChange(
            cognitiveComplaintIndex=ReliableChangeEntry(**compute_rci(
                result.composites.cognitiveComplaintIndex.score,
                prior_composites["cognitiveComplaintIndex"]["score"],
                result.composites.cognitiveComplaintIndex.sem,
            )),
            modifiableLoadIndex=ReliableChangeEntry(**compute_rci(
                result.composites.modifiableLoadIndex.score,
                prior_composites["modifiableLoadIndex"]["score"],
                result.composites.modifiableLoadIndex.sem,
            )),
            overall=ReliableChangeEntry(**compute_rci(
                result.overall_score, prior_overall["score"], overall_sem,
            )),
        )
    except (KeyError, TypeError, ValueError):
        return None, False

    retest_interval_warning = False
    prior_ts = prior_report.get("sessionTimestamp")
    if prior_ts:
        try:
            prior_dt = datetime.fromisoformat(prior_ts.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - prior_dt).total_seconds() / 86400.0
            retest_interval_warning = days < MIN_RETEST_INTERVAL_DAYS
        except ValueError:
            pass

    return reliable_change, retest_interval_warning


def _map_result_to_response(
    assessment_id: str,
    age: int,
    result: ScoringResult,
    prior_report: dict | None,
    name: str | None = None,
    gender: str | None = None,
) -> AnalyzeResponse:
    """Maps ScoringResult → AnalyzeResponse."""

    scale_dict = vars(result.scales)

    # `domains` carries the seven measured scales. The key is unchanged from
    # earlier revisions so existing clients keep the same access path; its
    # contents are the real scales rather than the eight partly-derived
    # domains that used to live here.
    domains = DomainScores(**{k: _to_scale_score(v) for k, v in scale_dict.items()})

    composite_dict = vars(result.composites)
    composites = Composites(**{k: _to_scale_score(v) for k, v in composite_dict.items()})

    validity = ValidityReport(status=result.validity.status, flags=result.validity.flags)
    percentile = Percentile(value=result.percentile.value, provisional=result.percentile.provisional)

    # Lifestyle impacts
    li = result.lifestyle_impacts
    impacts = LifestyleImpacts(
        sleepQualityImpact= _impact_enum(li.sleep_quality),
        stressLevelImpact=  _impact_enum(li.stress_level),
        anxietyLoadImpact=  _impact_enum(li.anxiety_load),
        burnoutRiskImpact=  _impact_enum(li.burnout_risk),
    )

    # Recommendations — the rule engine is keyed on the SectionScores/
    # DomainScores structs, so feed it the same shims used for lifestyle/risk.
    section_scores_shim, domain_scores_shim = build_rule_engine_shims(
        {k: v.score for k, v in scale_dict.items()}
    )
    recommendations = build_recommendations(
        section_scores_shim, domain_scores_shim, result.risk_indicators, age=age
    )

    # Progress delta (only if a prior report was supplied).
    progress = (
        compute_progress(domains.model_dump(), prior_report)
        if prior_report else Progress(available=False)
    )

    # Reliable Change Index — two-point comparison vs prior_report.
    reliable_change, retest_interval_warning = _compute_reliable_change(result, prior_report)

    # Audit
    raw_audit = result.audit
    audit = AuditInfo(
        rules_version=         raw_audit.get("rules_version", "2.0"),
        age_cohort=            raw_audit.get("age_cohort", ""),
        clamped_values=        raw_audit.get("clamped_values", []),
        imputation_notes=      raw_audit.get("imputation_notes", []),
        insufficient_sections= raw_audit.get("insufficient_sections", []),
    )

    cog = result.cognitive_age
    cognitive_age = CognitiveAge(
        actualAge=cog.actualAge,
        estimatedCognitiveAge=cog.estimatedCognitiveAge,
        ageLow=cog.ageLow,
        ageHigh=cog.ageHigh,
        provisional=cog.provisional,
        disclaimer=cog.disclaimer,
    )

    charts = _build_chart_data(domains, impacts)

    return AnalyzeResponse(
        assessmentId=       assessment_id,
        name=               name,
        gender=             gender,
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
        composites=         composites,
        validity=           validity,
        percentile=         percentile,
        reliableChange=        reliable_change,
        retestIntervalWarning= retest_interval_warning,
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
            elapsed_seconds=request.elapsedSeconds,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _map_result_to_response(
        assessment_id=request.assessmentId,
        age=request.age,
        result=result,
        prior_report=request.priorReport,
        name=request.name,
        gender=request.gender,
    )
