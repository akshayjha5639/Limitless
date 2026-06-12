"""
Limitless — PDF Generation Service
Produces a 7-page branded cognitive wellness report using ReportLab.

Pages:
  1. Cover
  2. Core Brain Function (radar chart)
  3. Lifestyle Impact Factors (bar chart)
  4. Risk Indicators
  5. Cognitive Age
  6. Strengths
  7. Improvement Plan + Legal
"""

import io
import os
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Drawing, String, Rect, Line, Wedge, Circle
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor

# ---------------------------------------------------------------------------
# Brand defaults
# ---------------------------------------------------------------------------

DEFAULT_PRIMARY   = "#1E6FD9"
DEFAULT_ACCENT    = "#00C2CB"
DEFAULT_BG        = "#F4F7FC"
DEFAULT_DARK      = "#1A1A2E"
DEFAULT_LIGHT_TXT = "#6B7280"
WHITE             = colors.white

W, H = A4  # 210 × 297 mm

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex(h: str):
    return HexColor(h)


def _rating_color(rating: str, primary: str) -> HexColor:
    return {
        "Excellent":       _hex("#16A34A"),
        "Good":            _hex(primary),
        "Needs Attention": _hex("#F59E0B"),
        "At Risk":         _hex("#DC2626"),
    }.get(rating, _hex(primary))


def _impact_color(level: str) -> HexColor:
    return {
        "High":     _hex("#DC2626"),
        "Moderate": _hex("#F59E0B"),
        "Low":      _hex("#16A34A"),
    }.get(level, _hex("#6B7280"))


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _build_styles(primary: str, accent: str):
    base = getSampleStyleSheet()
    P = _hex(primary)
    A = _hex(accent)
    D = _hex(DEFAULT_DARK)
    L = _hex(DEFAULT_LIGHT_TXT)

    styles = {
        "cover_title": ParagraphStyle(
            "cover_title", fontSize=28, textColor=WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=6,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle", fontSize=13, textColor=WHITE,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4,
        ),
        "cover_score": ParagraphStyle(
            "cover_score", fontSize=56, textColor=WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2,
        ),
        "cover_rating": ParagraphStyle(
            "cover_rating", fontSize=18, textColor=A,
            fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=16,
        ),
        "cover_disclaimer": ParagraphStyle(
            "cover_disclaimer", fontSize=8, textColor=WHITE,
            fontName="Helvetica-Oblique", alignment=TA_CENTER,
        ),
        "page_heading": ParagraphStyle(
            "page_heading", fontSize=20, textColor=P,
            fontName="Helvetica-Bold", spaceAfter=8, spaceBefore=4,
        ),
        "sub_heading": ParagraphStyle(
            "sub_heading", fontSize=14, textColor=D,
            fontName="Helvetica-Bold", spaceAfter=6, spaceBefore=8,
        ),
        "body": ParagraphStyle(
            "body", fontSize=12, textColor=D,
            fontName="Helvetica", spaceAfter=5, leading=16,
        ),
        "body_small": ParagraphStyle(
            "body_small", fontSize=10, textColor=L,
            fontName="Helvetica", spaceAfter=4, leading=13,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontSize=11, textColor=D, fontName="Helvetica",
            spaceAfter=5, leading=15, leftIndent=14, bulletIndent=0,
        ),
        "domain_label": ParagraphStyle(
            "domain_label", fontSize=11, textColor=D,
            fontName="Helvetica-Bold", spaceAfter=3,
        ),
        "score_number": ParagraphStyle(
            "score_number", fontSize=11, textColor=P,
            fontName="Helvetica-Bold", spaceAfter=3, alignment=TA_RIGHT,
        ),
        "risk_item": ParagraphStyle(
            "risk_item", fontSize=11, textColor=_hex("#7C3AED"),
            fontName="Helvetica", spaceAfter=6, leading=15, leftIndent=14,
        ),
        "strength_item": ParagraphStyle(
            "strength_item", fontSize=12, textColor=_hex("#16A34A"),
            fontName="Helvetica-Bold", spaceAfter=5,
        ),
        "rec_item": ParagraphStyle(
            "rec_item", fontSize=11, textColor=D,
            fontName="Helvetica", spaceAfter=7, leading=15, leftIndent=14,
        ),
        "legal": ParagraphStyle(
            "legal", fontSize=9, textColor=L,
            fontName="Helvetica-Oblique", spaceAfter=4, leading=12,
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=8, textColor=L,
            fontName="Helvetica", alignment=TA_CENTER,
        ),
    }
    return styles


# ---------------------------------------------------------------------------
# Radar chart (8 domains) — drawn as a polygon spider chart
# ---------------------------------------------------------------------------

def _radar_chart(domain_scores: dict, primary: str, accent: str, size=200) -> Drawing:
    import math

    labels = list(domain_scores.keys())
    values = list(domain_scores.values())
    n = len(labels)
    cx, cy = size / 2, size / 2
    max_r = size / 2 - 30

    d = Drawing(size, size)

    # Grid rings
    for ring in [0.25, 0.5, 0.75, 1.0]:
        pts = []
        for i in range(n):
            angle = math.pi / 2 - 2 * math.pi * i / n
            r = max_r * ring
            pts += [cx + r * math.cos(angle), cy + r * math.sin(angle)]
        # Draw polygon outline for each ring
        for i in range(n):
            x1 = pts[i * 2]
            y1 = pts[i * 2 + 1]
            x2 = pts[((i + 1) % n) * 2]
            y2 = pts[((i + 1) % n) * 2 + 1]
            line = Line(x1, y1, x2, y2, strokeColor=_hex("#E5E7EB"), strokeWidth=0.5)
            d.add(line)

    # Spokes
    for i in range(n):
        angle = math.pi / 2 - 2 * math.pi * i / n
        x = cx + max_r * math.cos(angle)
        y = cy + max_r * math.sin(angle)
        d.add(Line(cx, cy, x, y, strokeColor=_hex("#D1D5DB"), strokeWidth=0.5))

    # Data polygon
    data_pts = []
    for i, val in enumerate(values):
        angle = math.pi / 2 - 2 * math.pi * i / n
        r = max_r * (val / 100)
        data_pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Fill polygon
    from reportlab.graphics.shapes import Polygon
    flat = [coord for pt in data_pts for coord in pt]
    poly = Polygon(flat,
                   fillColor=_hex(accent) + "40" if False else _hex(primary),
                   strokeColor=_hex(primary),
                   strokeWidth=1.5,
                   fillOpacity=0.2)
    d.add(poly)

    # Dots + labels
    label_colors = _hex(DEFAULT_DARK)
    for i, (x, y) in enumerate(data_pts):
        d.add(Circle(x, y, 3, fillColor=_hex(primary), strokeColor=WHITE, strokeWidth=1))

    # Labels outside
    for i, label in enumerate(labels):
        angle = math.pi / 2 - 2 * math.pi * i / n
        lx = cx + (max_r + 18) * math.cos(angle)
        ly = cy + (max_r + 18) * math.sin(angle)
        short = label.replace(" & ", "/").replace("Attention", "Attn").replace("Executive", "Exec").replace("Processing", "Proc")
        s = String(lx, ly - 3, short[:12],
                   fontSize=7, textAnchor="middle",
                   fillColor=_hex(DEFAULT_DARK))
        d.add(s)

    return d


# ---------------------------------------------------------------------------
# Bar chart (lifestyle impacts)
# ---------------------------------------------------------------------------

def _bar_chart(labels: list, values: list, primary: str) -> Drawing:
    d = Drawing(380, 160)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 30
    chart.width = 320
    chart.height = 110
    chart.data = [values]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.valueStep = 25
    chart.valueAxis.labelTextFormat = "%d"
    chart.valueAxis.labels.fontSize = 8
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.angle = 0
    chart.bars[0].fillColor = _hex(primary)
    chart.bars[0].strokeColor = WHITE
    d.add(chart)
    return d


# ---------------------------------------------------------------------------
# Page header / footer callbacks
# ---------------------------------------------------------------------------

def _make_page_callbacks(primary: str, accent: str, footer_note: str):
    def on_page(canvas, doc):
        canvas.saveState()
        # Top accent bar
        canvas.setFillColor(_hex(primary))
        canvas.rect(0, H - 10 * mm, W, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(_hex(accent))
        canvas.rect(0, H - 12 * mm, W, 2 * mm, fill=1, stroke=0)

        # Footer
        canvas.setFillColor(_hex(DEFAULT_LIGHT_TXT))
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(W / 2, 8 * mm,
            f"Limitless Cognitive Wellness Report  •  {footer_note}  •  Page {doc.page}")
        canvas.drawCentredString(W / 2, 4 * mm,
            "Wellness screening tool — not a medical diagnosis. Not for clinical use.")
        canvas.restoreState()

    def on_cover(canvas, doc):
        # Full-bleed cover background
        canvas.saveState()
        canvas.setFillColor(_hex(primary))
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        # Accent strip at bottom
        canvas.setFillColor(_hex(accent))
        canvas.rect(0, 0, W, 18 * mm, fill=1, stroke=0)
        canvas.restoreState()

    return on_page, on_cover


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_pdf(analysis: dict, brand: dict) -> bytes:
    """
    Build the full PDF report.
    Returns raw PDF bytes.
    """
    primary      = brand.get("primaryColor", DEFAULT_PRIMARY)
    accent       = brand.get("accentColor",  DEFAULT_ACCENT)
    footer_note  = brand.get("footerNote",   "v1.0 • Limitless Platform")
    logo_url     = brand.get("logoUrl")

    buf = io.BytesIO()
    styles = _build_styles(primary, accent)

    on_page, on_cover = _make_page_callbacks(primary, accent, footer_note)

    # Document
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    # Two page templates: cover (no header/footer chrome) and inner pages
    cover_frame = Frame(0, 0, W, H, leftPadding=18*mm, rightPadding=18*mm,
                        topPadding=30*mm, bottomPadding=20*mm, id="cover")
    inner_frame = Frame(18*mm, 18*mm, W - 36*mm, H - 42*mm, id="inner")

    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=on_cover),
        PageTemplate(id="Inner", frames=[inner_frame], onPage=on_page),
    ])

    story = []

    # ==============================================================
    # PAGE 1 — COVER
    # ==============================================================
    overall  = analysis.get("overall", {})
    score    = overall.get("score", 0)
    rating   = overall.get("rating", "")
    age      = analysis.get("cognitiveAge", {}).get("actualAge", "")
    gender   = analysis.get("gender", "")

    # Logo
    logo_path = logo_url or (LOGO_PATH if os.path.exists(LOGO_PATH) else None)
    if logo_path and os.path.exists(str(logo_path)):
        story.append(Spacer(1, 10 * mm))
        story.append(Image(logo_path, width=40 * mm, height=40 * mm,
                           kind="proportional"))
        story.append(Spacer(1, 6 * mm))
    else:
        story.append(Spacer(1, 24 * mm))

    story.append(Paragraph("LIMITLESS", styles["cover_title"]))
    story.append(Paragraph("Cognitive Wellness Report", styles["cover_subtitle"]))
    story.append(Spacer(1, 10 * mm))

    story.append(Paragraph(f"{score:.0f}", styles["cover_score"]))
    story.append(Paragraph(rating, styles["cover_rating"]))
    story.append(Spacer(1, 8 * mm))

    # Quick snapshot table
    domains  = analysis.get("domains", {})
    impacts  = analysis.get("lifestyleImpacts", {})
    snap_data = [
        ["Memory", f"{domains.get('memory', 0):.0f}/100",
         "Attention", f"{domains.get('attentionFocus', 0):.0f}/100"],
        ["Sleep Impact", impacts.get("sleepQualityImpact", "—"),
         "Stress Impact", impacts.get("stressLevelImpact", "—")],
    ]
    snap_table = Table(snap_data, colWidths=[42*mm, 28*mm, 42*mm, 28*mm])
    snap_table.setStyle(TableStyle([
        ("TEXTCOLOR",    (0, 0), (-1, -1), WHITE),
        ("FONTNAME",     (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME",     (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME",     (3, 0), (3, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [colors.Color(1,1,1,0.08), colors.Color(1,1,1,0.04)]),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(snap_table)
    story.append(Spacer(1, 16 * mm))

    story.append(Paragraph(
        "This is a wellness screening tool — NOT a medical diagnosis. "
        "All outputs are for informational purposes only. "
        "Consult a licensed clinician for persistent symptoms.",
        styles["cover_disclaimer"],
    ))

    # Switch to inner template
    story.append(PageBreak())
    from reportlab.platypus import NextPageTemplate
    story.insert(0, NextPageTemplate("Cover"))

    # ==============================================================
    # PAGE 2 — CORE BRAIN FUNCTION
    # ==============================================================
    story.append(NextPageTemplate("Inner"))
    story.append(PageBreak())

    story.append(Paragraph("Core Brain Function", styles["page_heading"]))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=_hex(accent), spaceAfter=10))

    # Radar chart
    domain_scores = {
        "Memory":      domains.get("memory", 0),
        "Attn/Focus":  domains.get("attentionFocus", 0),
        "Proc Speed":  domains.get("processingSpeed", 0),
        "Exec Func":   domains.get("executiveFunction", 0),
        "Clarity":     domains.get("mentalClarity", 0),
        "Language":    domains.get("languageSkills", 0),
        "Problem Slv": domains.get("problemSolving", 0),
        "React Time":  domains.get("reactionTime", 0),
    }
    radar = _radar_chart(domain_scores, primary, accent, size=210)
    story.append(radar)
    story.append(Spacer(1, 6 * mm))

    # Domain score table
    story.append(Paragraph("Domain Scores", styles["sub_heading"]))
    domain_rows = []
    rating_bands = {"Excellent": (85,100), "Good": (70,84),
                    "Needs Attention": (50,69), "At Risk": (0,49)}

    def get_band(v):
        for band, (lo, hi) in rating_bands.items():
            if lo <= v <= hi:
                return band
        return "—"

    for label, val in domain_scores.items():
        band = get_band(val)
        band_color = _rating_color(band, primary)
        domain_rows.append([
            Paragraph(label, styles["domain_label"]),
            Paragraph(f"{val:.0f}", styles["score_number"]),
            Paragraph(band, ParagraphStyle("band", fontSize=10,
                      textColor=band_color, fontName="Helvetica-Bold")),
        ])

    dt = Table(domain_rows, colWidths=[90*mm, 30*mm, 50*mm])
    dt.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_hex(DEFAULT_BG), WHITE]),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, _hex("#E5E7EB")),
    ]))
    story.append(dt)

    # ==============================================================
    # PAGE 3 — LIFESTYLE IMPACT FACTORS
    # ==============================================================
    story.append(PageBreak())
    story.append(Paragraph("Lifestyle Impact Factors", styles["page_heading"]))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=_hex(accent), spaceAfter=10))

    story.append(Paragraph(
        "The chart below shows how lifestyle factors are affecting your cognitive performance. "
        "A lower bar value indicates a higher negative impact on cognition.",
        styles["body"],
    ))

    charts_data = analysis.get("charts", {})
    bar_data    = charts_data.get("barLifestyleImpacts", {})
    bar_labels  = bar_data.get("labels", ["Sleep", "Stress", "Anxiety", "Burnout"])
    bar_values  = bar_data.get("values", [50, 50, 50, 50])

    bar = _bar_chart(bar_labels, bar_values, primary)
    story.append(bar)
    story.append(Spacer(1, 6 * mm))

    # Impact detail table
    impact_items = [
        ("Sleep Quality",  impacts.get("sleepQualityImpact", "—")),
        ("Stress Level",   impacts.get("stressLevelImpact",  "—")),
        ("Anxiety Load",   impacts.get("anxietyLoadImpact",  "—")),
        ("Burnout Risk",   impacts.get("burnoutRiskImpact",  "—")),
    ]
    impact_rows = []
    for factor, level in impact_items:
        lc = _impact_color(level)
        impact_rows.append([
            Paragraph(factor, styles["domain_label"]),
            Paragraph(level, ParagraphStyle("il", fontSize=11,
                      textColor=lc, fontName="Helvetica-Bold")),
        ])

    it = Table(impact_rows, colWidths=[100*mm, 70*mm])
    it.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_hex(DEFAULT_BG), WHITE]),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, _hex("#E5E7EB")),
    ]))
    story.append(it)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Note: Physical activity, hydration, and nutrition are inferred from "
        "Stress, Sleep, and Productivity sections unless directly measured.",
        styles["body_small"],
    ))

    # ==============================================================
    # PAGE 4 — RISK INDICATORS
    # ==============================================================
    story.append(PageBreak())
    story.append(Paragraph("Possible Wellness Indicators", styles["page_heading"]))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=_hex(accent), spaceAfter=10))

    risk_indicators = analysis.get("riskIndicators", [])
    if risk_indicators:
        story.append(Paragraph(
            "The following indicators were identified based on your responses. "
            "All items use wellness language only — none are clinical diagnoses.",
            styles["body"],
        ))
        story.append(Spacer(1, 4 * mm))
        for risk in risk_indicators:
            story.append(Paragraph(f"• {risk}", styles["risk_item"]))
    else:
        story.append(Paragraph(
            "✓ No significant wellness indicators were identified. "
            "Your responses suggest good overall cognitive resilience.",
            ParagraphStyle("ok", fontSize=13, textColor=_hex("#16A34A"),
                           fontName="Helvetica-Bold", spaceAfter=6),
        ))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "⚠ All indicators above are prefixed with 'Possible' — they are "
        "screening signals, not diagnoses. Consult a licensed clinician "
        "if any of these resonate persistently.",
        styles["body_small"],
    ))

    # ==============================================================
    # PAGE 5 — COGNITIVE AGE
    # ==============================================================
    story.append(PageBreak())
    story.append(Paragraph("Cognitive Age", styles["page_heading"]))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=_hex(accent), spaceAfter=10))

    cog = analysis.get("cognitiveAge", {})
    actual_age = cog.get("actualAge", "—")
    est_age    = cog.get("estimatedCognitiveAge")
    disclaimer = cog.get("disclaimer", "Motivational wellness metric only.")

    age_data = [
        ["Actual Age", "Estimated Cognitive Age"],
        [str(actual_age), str(est_age) if est_age else "—  (Phase 1)"],
    ]
    age_table = Table(age_data, colWidths=[85*mm, 85*mm])
    age_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), _hex(primary)),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 12),
        ("FONTSIZE",     (0, 1), (-1, 1), 28),
        ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR",    (0, 1), (-1, 1), _hex(primary)),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("GRID",         (0, 0), (-1, -1), 0.5, _hex("#E5E7EB")),
    ]))
    story.append(age_table)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(f"⚠ {disclaimer}", styles["body_small"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "The Cognitive Age estimate is computed using a heuristic formula "
        "based on your overall score, sleep quality, and stress levels. "
        "For the 18–25 age cohort (Phase 1), this metric is shown as a "
        "placeholder and will be calibrated in a future release.",
        styles["body"],
    ))

    # ==============================================================
    # PAGE 6 — STRENGTHS
    # ==============================================================
    story.append(PageBreak())
    story.append(Paragraph("Your Cognitive Strengths", styles["page_heading"]))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=_hex(accent), spaceAfter=10))

    strengths = analysis.get("strengths", [])
    if strengths:
        story.append(Paragraph(
            "The following cognitive domains scored 80 or above — "
            "these represent your areas of strongest performance.",
            styles["body"],
        ))
        story.append(Spacer(1, 6 * mm))
        for s in strengths:
            story.append(Paragraph(f"✓  {s}", styles["strength_item"]))
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph(
            "Keep working on your wellness habits — strengths will emerge "
            "as your scores improve above 80.",
            styles["body"],
        ))

    # ==============================================================
    # PAGE 7 — IMPROVEMENT PLAN + LEGAL
    # ==============================================================
    story.append(PageBreak())
    story.append(Paragraph("Your Personal Improvement Plan", styles["page_heading"]))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=_hex(accent), spaceAfter=10))

    recommendations = analysis.get("recommendations", [])
    for i, rec in enumerate(recommendations, 1):
        story.append(Paragraph(f"{i}.  {rec}", styles["rec_item"]))

    story.append(Spacer(1, 10 * mm))

    # Progress section (if available)
    progress = analysis.get("progress", {})
    if progress.get("available") and progress.get("deltas"):
        story.append(Paragraph("Progress Since Last Assessment", styles["sub_heading"]))
        prog_rows = [["Domain", "Previous", "Current", "Change"]]
        for d in progress["deltas"]:
            arrow = "▲" if d["direction"] == "improved" else ("▼" if d["direction"] == "declined" else "→")
            prog_rows.append([
                d["domain"], f"{d['previous']:.0f}", f"{d['current']:.0f}",
                f"{arrow} {abs(d['delta']):.1f}",
            ])
        prog_table = Table(prog_rows, colWidths=[60*mm, 35*mm, 35*mm, 40*mm])
        prog_table.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), _hex(primary)),
            ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [_hex(DEFAULT_BG), WHITE]),
            ("GRID",        (0, 0), (-1, -1), 0.3, _hex("#E5E7EB")),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(prog_table)
        story.append(Spacer(1, 8 * mm))

    # Legal block
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=_hex("#D1D5DB"), spaceAfter=6))
    story.append(Paragraph("Legal & Privacy", styles["sub_heading"]))
    disclaimers = analysis.get("disclaimers", [])
    for disc in disclaimers:
        story.append(Paragraph(f"• {disc}", styles["legal"]))

    privacy = analysis.get("privacy", {})
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Data collected: {', '.join(privacy.get('dataCollected', ['age', 'gender']))}. "
        f"{privacy.get('storagePolicy', '')}",
        styles["legal"],
    ))
    story.append(Paragraph(privacy.get("hipaaNote", ""), styles["legal"]))

    # Build
    doc.build(story)
    return buf.getvalue()
