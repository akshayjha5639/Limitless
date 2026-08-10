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
    ScalesV2,
    Composites,
    ValidityReport,
    CognitiveAgeV2,
    PercentileV2,
    ReliableChange,
    ReliableChangeEntry,
)
from app.scoring.engine import score as run_scoring, ScoringResult
from app.scoring.engine_v2 import (
    score_v2 as run_scoring_v2,
    ScoringResultV2,
    build_v1_shims,
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


def _map_domains_from_v2(scale_dict: dict) -> DomainScores:
    """
    Backward-compatibility shim: maps the 7 v2 scales onto the legacy 8-key
    DomainScores object so the existing PDF/frontend keep working while v2
    is active (non-negotiable rule 4 — populate `domains` even under v2).

    memory / attentionFocus / executiveFunction have a genuine 1:1 v2 scale.
    mentalClarity carries forward the same S3 section v2 now calls
    executiveFunction (not fabricated — same underlying computed value).
    processingSpeed, languageSkills, problemSolving, reactionTime have no
    v2 equivalent (v1 fabricated all four) — populated from the closest v2
    scale rather than inventing values. These four are transitional shims
    to be removed once the PDF fully migrates to v2 scales.
    """
    return DomainScores(
        memory=             scale_dict["memoryRecall"].score,
        attentionFocus=     scale_dict["attentionFocus"].score,
        executiveFunction=  scale_dict["executiveFunction"].score,
        mentalClarity=      scale_dict["executiveFunction"].score,
        # --- transitional shims: no v2 equivalent, nearest scale used ---
        processingSpeed=    scale_dict["mentalEnergy"].score,     # cognitive tempo proxy
        languageSkills=     scale_dict["memoryRecall"].score,     # verbal/recall-adjacent
        problemSolving=     scale_dict["executiveFunction"].score,# reasoning-adjacent
        reactionTime=       scale_dict["attentionFocus"].score,   # alertness-adjacent
    )


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
    name: str | None = None,
    gender: str | None = None,
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
    )


def _to_scale_score(v) -> ScaleScore:
    return ScaleScore(score=v.score, sem=v.sem, ciLow=v.ciLow, ciHigh=v.ciHigh)


def _compute_reliable_change(
    result: ScoringResultV2, prior_report: dict | None
) -> tuple[ReliableChange | None, bool]:
    """
    Phase 5 — two-point RCI between this v2 result and a prior v2
    /analyze response (the same `priorReport` used by compute_progress()).

    Applied to the 12-item composites and overall score only — individual
    4-item scales are too noisy for a formal reliable-change verdict (see
    the matching note in longitudinal_engine.compute_reliable_change, which
    does the same comparison across a multi-session history array; this is
    the single-prior-report equivalent that actually feeds the PDF
    Progress page, since /generate-pdf only ever sees one /analyze response).

    None/False unless ENABLE_RELIABLE_CHANGE is on, a prior report was
    supplied, and it is itself a v2 response with composite data.
    """
    if not settings.ENABLE_RELIABLE_CHANGE or not prior_report:
        return None, False
    if prior_report.get("modelVersion") != "v2":
        return None, False

    prior_composites = prior_report.get("composites")
    prior_overall = prior_report.get("overall")
    if not prior_composites or not prior_overall:
        return None, False

    # v2 doesn't define a dedicated overall-score SEM — reuse the
    # composite-level provisional constants as the nearest available proxy.
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


def _map_result_to_response_v2(
    assessment_id: str,
    age: int,
    result: ScoringResultV2,
    prior_report: dict | None,
    name: str | None = None,
    gender: str | None = None,
) -> AnalyzeResponse:
    """Maps ScoringResultV2 → AnalyzeResponse (v1 fields backward-populated)."""

    scale_dict = vars(result.scales)
    scales = ScalesV2(**{k: _to_scale_score(v) for k, v in scale_dict.items()})

    composite_dict = vars(result.composites)
    composites = Composites(**{k: _to_scale_score(v) for k, v in composite_dict.items()})

    validity = ValidityReport(status=result.validity.status, flags=result.validity.flags)
    percentile = PercentileV2(value=result.percentile.value, provisional=result.percentile.provisional)

    # Backward-compat: still populate the legacy 8-key `domains` object
    domains = _map_domains_from_v2(scale_dict)

    # Lifestyle impacts
    li = result.lifestyle_impacts
    impacts = LifestyleImpacts(
        sleepQualityImpact= _impact_enum(li.sleep_quality),
        stressLevelImpact=  _impact_enum(li.stress_level),
        anxietyLoadImpact=  _impact_enum(li.anxiety_load),
        burnoutRiskImpact=  _impact_enum(li.burnout_risk),
    )

    # Recommendations — reuses v1's rule engine via the same SectionScores/
    # DomainScores shim engine_v2 uses internally for lifestyle/risk logic.
    section_scores_shim, domain_scores_shim = build_v1_shims(
        {k: v.score for k, v in scale_dict.items()}
    )
    recommendations = build_recommendations(
        section_scores_shim, domain_scores_shim, result.risk_indicators, age=age
    )

    # Progress delta (only if prior report supplied) — unchanged mechanism,
    # operates on the backward-compat `domains` object either version produces.
    progress = (
        compute_progress(domains.model_dump(), prior_report)
        if prior_report else Progress(available=False)
    )

    # Reliable Change Index (Phase 5) — two-point comparison vs prior_report.
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

    # Cognitive age — legacy field populated from the v2 result (richer detail
    # carried separately in the additive `cognitiveAgeV2` field).
    cog = result.cognitive_age
    cognitive_age = CognitiveAge(
        actualAge=age,
        estimatedCognitiveAge=cog.estimatedCognitiveAge,
        disclaimer=cog.disclaimer,
    )
    cognitive_age_v2 = CognitiveAgeV2(
        actualAge=cog.actualAge,
        estimatedCognitiveAge=cog.estimatedCognitiveAge,
        ageLow=cog.ageLow,
        ageHigh=cog.ageHigh,
        provisional=cog.provisional,
        disclaimer=cog.disclaimer,
    )

    # Chart data — same helper, fed by the backward-compat domains object
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
        scales=             scales,
        composites=         composites,
        validity=           validity,
        percentile=         percentile,
        cognitiveAgeV2=     cognitive_age_v2,
        modelVersion=       "v2",
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

    if settings.SCORING_MODEL_VERSION == "v2":
        try:
            result_v2 = run_scoring_v2(
                age=request.age,
                gender=request.gender,
                responses=responses_raw,
                elapsed_seconds=request.elapsedSeconds,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        return _map_result_to_response_v2(
            assessment_id=request.assessmentId,
            age=request.age,
            result=result_v2,
            prior_report=request.priorReport,
            name=request.name,
            gender=request.gender,
        )

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
        name=request.name,
        gender=request.gender,
    )
