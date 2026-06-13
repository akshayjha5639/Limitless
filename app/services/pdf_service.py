"""
LIMITLESS PREMIUM REPORT — PRODUCTION REDESIGN
Run:
    python pdf_service.py
"""

import os
import math
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color, white, black
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from io import BytesIO
from reportlab.lib.pagesizes import A4
from app.services.report_mapper import transform_analysis_to_report
# ============================================================
# PAGE CONFIG
# ============================================================

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 40

# ============================================================
# COLOR SYSTEM
# ============================================================

PRIMARY       = HexColor("#2563EB")
PRIMARY_LIGHT = HexColor("#3B82F6")
PRIMARY_DARK  = HexColor("#1D4ED8")

SECONDARY     = HexColor("#7C3AED")
SECONDARY_LIGHT = HexColor("#8B5CF6")

GRADIENT_1    = HexColor("#1E3A8A")
GRADIENT_2    = HexColor("#2D2080")
GRADIENT_3    = HexColor("#4C1D95")

SUCCESS       = HexColor("#10B981")
SUCCESS_LIGHT = HexColor("#D1FAE5")
WARNING       = HexColor("#F59E0B")
WARNING_LIGHT = HexColor("#FEF3C7")
DANGER        = HexColor("#EF4444")
DANGER_LIGHT  = HexColor("#FEE2E2")
INFO_LIGHT    = HexColor("#DBEAFE")

TEXT_PRIMARY   = HexColor("#0F172A")
TEXT_SECONDARY = HexColor("#64748B")
TEXT_MUTED     = HexColor("#94A3B8")
TEXT_WHITE     = white

BACKGROUND     = HexColor("#F1F5F9")
CARD_BG        = HexColor("#FFFFFF")
BORDER_COLOR   = HexColor("#E2E8F0")
SURFACE        = HexColor("#F8FAFC")

# ============================================================
# TYPOGRAPHY
# ============================================================

FONT      = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_OBL  = "Helvetica-Oblique"

# ============================================================
# HELPERS
# ============================================================

def score_color(score):
    if score >= 85: return SUCCESS
    elif score >= 70: return PRIMARY
    elif score >= 50: return WARNING
    return DANGER

def score_color_light(score):
    if score >= 85: return SUCCESS_LIGHT
    elif score >= 70: return INFO_LIGHT
    elif score >= 50: return WARNING_LIGHT
    return DANGER_LIGHT

def score_status(score):
    if score >= 85: return "Excellent"
    elif score >= 70: return "Good"
    elif score >= 50: return "Needs Attention"
    return "At Risk"

def score_emoji(score):
    if score >= 85: return "●"
    elif score >= 70: return "●"
    elif score >= 50: return "●"
    return "●"

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

# ============================================================
# LOW-LEVEL DRAW PRIMITIVES
# ============================================================

def draw_rect_shadow(c, x, y, w, h, radius=12, blur_layers=4):
    """Soft drop shadow via stacked translucent rects."""
    for i in range(blur_layers, 0, -1):
        alpha = 0.03
        offset = i * 1.5
        c.setFillColor(Color(0, 0, 0, alpha=alpha))
        c.roundRect(x + offset, y - offset, w, h, radius, fill=1, stroke=0)


def draw_card(c, x, y, w, h, radius=14, bg=None, border=False):
    draw_rect_shadow(c, x, y, w, h, radius)
    c.setFillColor(bg or CARD_BG)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
    if border:
        c.setStrokeColor(BORDER_COLOR)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)


def draw_gradient_rect(c, x, y, w, h, color1, color2, steps=60):
    """Vertical gradient via stacked thin rectangles."""
    r1, g1, b1 = color1.red, color1.green, color1.blue
    r2, g2, b2 = color2.red, color2.green, color2.blue
    step_h = h / steps
    for i in range(steps):
        t = i / steps
        r = r1 + (r2 - r1) * t
        g = g1 + (g2 - g1) * t
        b = b1 + (b2 - b1) * t
        c.setFillColor(Color(r, g, b))
        c.rect(x, y + h - (i + 1) * step_h, w, step_h + 0.5, fill=1, stroke=0)


def draw_text(c, text, x, y, size=13, font=FONT, color=TEXT_PRIMARY, align="left"):
    c.setFont(font, size)
    c.setFillColor(color)
    if align == "center":
        c.drawCentredString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)


def draw_tag(c, x, y, label, bg_color, text_color=white, width=None, height=22, radius=8):
    c.setFont(FONT_BOLD, 9)
    text_w = c.stringWidth(label, FONT_BOLD, 9)
    w = width or (text_w + 20)
    c.setFillColor(bg_color)
    c.roundRect(x, y, w, height, radius, fill=1, stroke=0)
    c.setFillColor(text_color)
    c.drawCentredString(x + w / 2, y + 6.5, label)
    return w


def draw_divider(c, x, y, w, color=BORDER_COLOR, thickness=0.75):
    c.setStrokeColor(color)
    c.setLineWidth(thickness)
    c.line(x, y, x + w, y)


def draw_score_badge(c, x, y, score, radius=26):
    """Circular score badge with ring."""
    col = score_color(score)
    # Outer ring
    c.setStrokeColor(col)
    c.setLineWidth(3)
    c.circle(x, y, radius, stroke=1, fill=0)
    # Inner fill
    c.setFillColor(score_color_light(score))
    c.circle(x, y, radius - 1.5, stroke=0, fill=1)
    # Score text
    c.setFillColor(col)
    c.setFont(FONT_BOLD, 16)
    c.drawCentredString(x, y - 5, str(score))
    c.setFont(FONT, 7)
    c.drawCentredString(x, y + 9, "/100")


def draw_progress_bar(c, x, y, w, h, value, bg=None, radius=5):
    # Track
    c.setFillColor(bg or HexColor("#E2E8F0"))
    c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
    # Fill — ensure minimum visible width
    fill_w = max(h, (clamp(value, 0, 100) / 100) * w)
    c.setFillColor(score_color(value))
    c.roundRect(x, y, fill_w, h, radius, fill=1, stroke=0)


# ============================================================
# GAUGE (COVER)
# ============================================================

def draw_large_gauge(c, cx, cy, radius, score):
    """Premium arc gauge with gradient-like effect."""
    # Outer decorative ring
    c.setStrokeColor(Color(1, 1, 1, alpha=0.1))
    c.setLineWidth(2)
    c.circle(cx, cy, radius + 20, stroke=1, fill=0)

    # Background arc
    c.setStrokeColor(Color(1, 1, 1, alpha=0.15))
    c.setLineWidth(18)
    c.arc(cx - radius, cy - radius, cx + radius, cy + radius,
          startAng=0, extent=360)

    # Score arc
    arc_color = score_color(score)
    c.setStrokeColor(arc_color)
    c.setLineWidth(18)
    angle = (score / 100) * 360
    c.arc(cx - radius, cy - radius, cx + radius, cy + radius,
          startAng=90, extent=-angle)

    # Center white circle
    c.setFillColor(Color(1, 1, 1, alpha=0.12))
    c.circle(cx, cy, radius - 22, stroke=0, fill=1)

    # Score number
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 52)
    c.drawCentredString(cx, cy + 12, str(score))

    # /100
    c.setFont(FONT, 14)
    c.setFillColor(Color(1, 1, 1, alpha=0.7))
    c.drawCentredString(cx, cy - 10, "/ 100")

    # Status
    status = score_status(score)
    col = score_color(score)
    badge_w = 120
    badge_h = 26
    c.setFillColor(col)
    c.roundRect(cx - badge_w / 2, cy - 48, badge_w, badge_h, 13, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 11)
    c.drawCentredString(cx, cy - 38, status)


# ============================================================
# RADAR CHART
# ============================================================

def draw_radar_chart(c, cx, cy, radius, domains, show_values=True):
    labels = list(domains.keys())
    values = list(domains.values())
    total = len(labels)

    # Grid rings
    for ring_i, ring in enumerate([0.25, 0.5, 0.75, 1.0]):
        alpha = 0.08 + ring_i * 0.05
        c.setStrokeColor(Color(37/255, 99/255, 235/255, alpha=alpha + 0.1))
        c.setLineWidth(0.75)
        pts = []
        for i in range(total):
            angle = (2 * math.pi * i / total) - math.pi / 2
            px = cx + math.cos(angle) * radius * ring
            py = cy + math.sin(angle) * radius * ring
            pts.append((px, py))
        for i in range(total):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % total]
            c.line(x1, y1, x2, y2)

    # Axis lines
    c.setStrokeColor(Color(37/255, 99/255, 235/255, alpha=0.15))
    c.setLineWidth(0.5)
    for i in range(total):
        angle = (2 * math.pi * i / total) - math.pi / 2
        ex = cx + math.cos(angle) * radius
        ey = cy + math.sin(angle) * radius
        c.line(cx, cy, ex, ey)

    # Filled polygon
    polygon = []
    for i, val in enumerate(values):
        angle = (2 * math.pi * i / total) - math.pi / 2
        r = radius * (val / 100)
        polygon.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))

    path = c.beginPath()
    path.moveTo(*polygon[0])
    for pt in polygon[1:]:
        path.lineTo(*pt)
    path.close()

    c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.20))
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(2.5)
    c.drawPath(path, fill=1, stroke=1)

    # Dots at vertices
    for px, py in polygon:
        c.setFillColor(PRIMARY)
        c.circle(px, py, 4, fill=1, stroke=0)
        c.setFillColor(white)
        c.circle(px, py, 2, fill=1, stroke=0)

    # Labels
    for i, label in enumerate(labels):
        angle = (2 * math.pi * i / total) - math.pi / 2
        lx = cx + math.cos(angle) * (radius + 28)
        ly = cy + math.sin(angle) * (radius + 28)
        val = values[i]

        c.setFont(FONT_BOLD, 9)
        c.setFillColor(TEXT_PRIMARY)
        c.drawCentredString(lx, ly + 4, label)

        if show_values:
            c.setFont(FONT, 8)
            c.setFillColor(score_color(val))
            c.drawCentredString(lx, ly - 7, f"{val}")


# ============================================================
# PAGE HEADER BAND
# ============================================================

def draw_page_header(c, title, subtitle=None, page_num=None):
    # Top accent bar
    draw_gradient_rect(c, 0, PAGE_HEIGHT - 72, PAGE_WIDTH, 72,
                       GRADIENT_1, GRADIENT_3)

    # Title
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 22)
    c.drawString(MARGIN, PAGE_HEIGHT - 44, title)

    if subtitle:
        c.setFont(FONT, 11)
        c.setFillColor(Color(1, 1, 1, alpha=0.7))
        c.drawString(MARGIN, PAGE_HEIGHT - 60, subtitle)

    if page_num:
        c.setFont(FONT, 10)
        c.setFillColor(Color(1, 1, 1, alpha=0.6))
        c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 44, f"Page {page_num}")

    # Page background
    c.setFillColor(BACKGROUND)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT - 72, fill=1, stroke=0)


def draw_page_footer(c, report_id=None):
    c.setFillColor(HexColor("#0F172A"))
    c.rect(0, 0, PAGE_WIDTH, 32, fill=1, stroke=0)

    c.setFont(FONT_BOLD, 9)
    c.setFillColor(white)
    c.drawString(MARGIN, 11, "LIMITLESS AI")

    c.setFont(FONT, 9)
    c.setFillColor(Color(1, 1, 1, alpha=0.5))
    c.drawCentredString(PAGE_WIDTH / 2, 11,
                        "AI-Powered Cognitive Wellness Assessment — Not a clinical diagnostic tool")

    if report_id:
        c.drawRightString(PAGE_WIDTH - MARGIN, 11, f"ID: {report_id}")


# ============================================================
# PAGE 1 — PREMIUM COVER
# ============================================================

def draw_cover_page(c, data):
    # Full gradient background
    draw_gradient_rect(c, 0, 0, PAGE_WIDTH, PAGE_HEIGHT, GRADIENT_3, GRADIENT_1)

    # Decorative circles
    c.setFillColor(Color(1, 1, 1, alpha=0.03))
    c.circle(PAGE_WIDTH - 60, PAGE_HEIGHT - 60, 200, fill=1, stroke=0)
    c.circle(60, 80, 150, fill=1, stroke=0)
    c.setFillColor(Color(1, 1, 1, alpha=0.02))
    c.circle(PAGE_WIDTH / 2, PAGE_HEIGHT / 2, 280, fill=1, stroke=0)

    # ── LOGO AREA ──
    c.setFillColor(Color(1, 1, 1, alpha=0.12))
    c.roundRect(MARGIN, PAGE_HEIGHT - 75, 200, 46, 10, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont(FONT_BOLD, 22)
    c.drawString(MARGIN + 14, PAGE_HEIGHT - 58, "LIMITLESS")
    c.setFont(FONT, 9)
    c.setFillColor(Color(1, 1, 1, alpha=0.7))
    c.drawString(MARGIN + 14, PAGE_HEIGHT - 72, "COGNITIVE WELLNESS")

    # Top-right report id
    c.setFont(FONT, 9)
    c.setFillColor(Color(1, 1, 1, alpha=0.5))
    c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 52,
                      f"Report ID: {data['report_id']}")
    c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 64,
                      datetime.now().strftime("%d %B %Y"))

    # ── TAGLINE ──
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 28)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 130,
                        "AI-Powered Cognitive")
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 158,
                        "Wellness Assessment")

    c.setFont(FONT, 13)
    c.setFillColor(Color(1, 1, 1, alpha=0.65))
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 178,
                        "Personalized insights to optimize your mental performance")

    # ── GAUGE ──
    draw_large_gauge(c, PAGE_WIDTH / 2, PAGE_HEIGHT - 310,
                     78, data["overall_score"])

    # Label above gauge
    c.setFont(FONT, 11)
    c.setFillColor(Color(1, 1, 1, alpha=0.6))
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 205,
                        "OVERALL WELLNESS SCORE")

    # ── USER INFO CARD ──
    ux, uy, uw, uh = MARGIN, PAGE_HEIGHT - 490, PAGE_WIDTH - MARGIN * 2, 80
    c.setFillColor(Color(1, 1, 1, alpha=0.10))
    c.roundRect(ux, uy, uw, uh, 14, fill=1, stroke=0)
    c.setStrokeColor(Color(1, 1, 1, alpha=0.2))
    c.setLineWidth(0.75)
    c.roundRect(ux, uy, uw, uh, 14, fill=0, stroke=1)

    user = data["user"]
    col1 = ux + 20
    col2 = ux + 145
    col3 = ux + 285
    col4 = ux + 390

    for col, key, val in [
        (col1, "NAME", user["name"]),
        (col2, "AGE", str(user["age"])),
        (col3, "GENDER", user["gender"]),
        (col4, "DATE", user.get("assessment_date", datetime.now().strftime("%d %b %Y"))),
    ]:
        c.setFont(FONT, 8)
        c.setFillColor(Color(1, 1, 1, alpha=0.5))
        c.drawString(col, uy + 56, key)
        c.setFont(FONT_BOLD, 13)
        c.setFillColor(white)
        c.drawString(col, uy + 38, val)

    # Separator lines
    c.setStrokeColor(Color(1, 1, 1, alpha=0.2))
    c.setLineWidth(0.5)
    for sep_x in [col2 - 10, col3 - 10, col4 - 10]:
        c.line(sep_x, uy + 14, sep_x, uy + 66)

    # ── KPI METRICS STRIP ──
    metrics = [
        ("Memory",    data["domains"]["Memory"],     "Brain"),
        ("Attention", data["domains"]["Attention"],   "Focus"),
        ("Sleep",     data["lifestyle"]["Sleep"],     "Recovery"),
        ("Stress",    data["lifestyle"]["Stress"],    "Load"),
    ]

    kpi_y = PAGE_HEIGHT - 590
    kpi_w = (PAGE_WIDTH - MARGIN * 2 - 12) / 4

    for i, (title, score, sub) in enumerate(metrics):
        kx = MARGIN + i * (kpi_w + 4)
        c.setFillColor(Color(1, 1, 1, alpha=0.10))
        c.roundRect(kx, kpi_y, kpi_w, 76, 12, fill=1, stroke=0)
        c.setStrokeColor(score_color(score))
        c.setLineWidth(2)
        c.roundRect(kx, kpi_y, kpi_w, 76, 12, fill=0, stroke=1)

        # Score
        c.setFillColor(score_color(score))
        c.setFont(FONT_BOLD, 26)
        c.drawCentredString(kx + kpi_w / 2, kpi_y + 42, str(score))

        # Title
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 11)
        c.drawCentredString(kx + kpi_w / 2, kpi_y + 26, title)

        # Sub
        c.setFont(FONT, 8)
        c.setFillColor(Color(1, 1, 1, alpha=0.55))
        c.drawCentredString(kx + kpi_w / 2, kpi_y + 14, sub)

    # ── BOTTOM CTA BAND ──
    c.setFillColor(Color(0, 0, 0, alpha=0.25))
    c.roundRect(MARGIN, PAGE_HEIGHT - 690, PAGE_WIDTH - MARGIN * 2, 72, 14, fill=1, stroke=0)

    insights_text = [
        ("8", "Cognitive Domains Analyzed"),
        ("4", "Lifestyle Factors Assessed"),
        ("30", "Day Improvement Plan"),
        ("AI", "Powered Insights"),
    ]
    band_item_w = (PAGE_WIDTH - MARGIN * 2) / 4
    for i, (num, lbl) in enumerate(insights_text):
        bx = MARGIN + i * band_item_w + band_item_w / 2
        c.setFont(FONT_BOLD, 20)
        c.setFillColor(white)
        c.drawCentredString(bx, PAGE_HEIGHT - 645, num)
        c.setFont(FONT, 8)
        c.setFillColor(Color(1, 1, 1, alpha=0.6))
        c.drawCentredString(bx, PAGE_HEIGHT - 658, lbl)

    # Footer
    c.setFillColor(Color(0, 0, 0, alpha=0.3))
    c.rect(0, 0, PAGE_WIDTH, 36, fill=1, stroke=0)
    c.setFont(FONT_BOLD, 10)
    c.setFillColor(white)
    c.drawCentredString(PAGE_WIDTH / 2, 13,
                        "Generated by Limitless AI  ·  Confidential  ·  Not a Clinical Diagnosis")


# ============================================================
# PAGE 2 — EXECUTIVE SUMMARY
# ============================================================

def draw_executive_summary(c, data):
    draw_page_header(c, "Executive Summary",
                     "Complete overview of your cognitive wellness assessment", 2)
    draw_page_footer(c, data["report_id"])

    y_start = PAGE_HEIGHT - 90

    # ── ROW 1: Score card + Risk card + AI Summary ──
    # Score card
    sc_x, sc_y, sc_w, sc_h = MARGIN, y_start - 130, 135, 125
    draw_card(c, sc_x, sc_y, sc_w, sc_h, radius=14)
    draw_text(c, "Wellness Score", sc_x + 12, sc_y + sc_h - 18, 9,
              FONT, TEXT_SECONDARY)
    c.setFont(FONT_BOLD, 44)
    c.setFillColor(score_color(data["overall_score"]))
    c.drawCentredString(sc_x + sc_w / 2, sc_y + 60, str(data["overall_score"]))
    c.setFont(FONT, 10)
    c.setFillColor(TEXT_MUTED)
    c.drawCentredString(sc_x + sc_w / 2, sc_y + 44, "out of 100")
    draw_progress_bar(c, sc_x + 12, sc_y + 20, sc_w - 24, 8,
                      data["overall_score"])

    # Risk classification card
    rx, ry, rw, rh = sc_x + sc_w + 10, y_start - 130, 130, 125
    risk_score = data["overall_score"]
    draw_card(c, rx, ry, rw, rh, radius=14)
    draw_text(c, "Risk Level", rx + 12, ry + rh - 18, 9, FONT, TEXT_SECONDARY)
    status = score_status(risk_score)
    col = score_color(risk_score)
    c.setFillColor(score_color_light(risk_score))
    c.roundRect(rx + 12, ry + 50, rw - 24, 42, 10, fill=1, stroke=0)
    c.setFillColor(col)
    c.setFont(FONT_BOLD, 13)
    c.drawCentredString(rx + rw / 2, ry + 75, status)
    c.setFont(FONT, 9)
    c.setFillColor(TEXT_SECONDARY)
    c.drawCentredString(rx + rw / 2, ry + 62, "Classification")
    # Risk dots
    levels = ["At Risk", "Needs Attention", "Good", "Excellent"]
    dot_y = ry + 34
    for li, lv in enumerate(levels):
        lx = rx + 12 + li * (rw - 24) / 4
        col_dot = [DANGER, WARNING, PRIMARY, SUCCESS][li]
        is_active = lv == status
        c.setFillColor(col_dot)
        c.circle(lx + 10, dot_y, 6 if is_active else 4, fill=1, stroke=0)
        if is_active:
            c.setStrokeColor(col_dot)
            c.setLineWidth(1.5)
            c.circle(lx + 10, dot_y, 9, fill=0, stroke=1)

    # AI Summary card
    ai_x, ai_y, ai_w, ai_h = rx + rw + 10, y_start - 130, PAGE_WIDTH - MARGIN - (rx + rw + 10), 125
    draw_card(c, ai_x, ai_y, ai_w, ai_h, radius=14)
    # AI badge
    c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.1))
    c.roundRect(ai_x + 12, ai_y + ai_h - 26, 42, 18, 8, fill=1, stroke=0)
    c.setFillColor(PRIMARY)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(ai_x + 33, ai_y + ai_h - 20, "AI ✦")

    summary_text = data["executive_summary"]["summary"]
    # Word wrap manually
    c.setFont(FONT, 10.5)
    c.setFillColor(TEXT_SECONDARY)
    wrap_text_in_box(c, summary_text, ai_x + 12, ai_y + ai_h - 30,
                     ai_w - 24, 10.5, line_height=15, max_lines=7)

    # ── KEY FINDINGS ──
    kf_y = y_start - 170
    draw_card(c, MARGIN, kf_y - 160, PAGE_WIDTH - MARGIN * 2, 155, radius=14)
    draw_text(c, "Key Findings", MARGIN + 16, kf_y - 24, 14, FONT_BOLD)
    draw_divider(c, MARGIN + 16, kf_y - 34, PAGE_WIDTH - MARGIN * 2 - 32)

    findings = data["executive_summary"]["key_findings"]
    cols = 2
    col_w = (PAGE_WIDTH - MARGIN * 2 - 32) / cols
    for fi, finding in enumerate(findings[:6]):
        fx = MARGIN + 16 + (fi % cols) * col_w
        fy = kf_y - 62 - (fi // cols) * 46
        # Icon dot
        c.setFillColor(PRIMARY)
        c.circle(fx + 8, fy + 5, 4, fill=1, stroke=0)
        c.setFillColor(white)
        c.circle(fx + 8, fy + 5, 2, fill=1, stroke=0)
        c.setFont(FONT, 11)
        c.setFillColor(TEXT_PRIMARY)
        wrap_text_in_box(
    c,
    finding,
    fx + 20,
    fy + 8,
    col_w - 40,
    10,
    line_height=12,
    max_lines=2
)

    # ── PRIORITY AREAS + STRENGTHS ──
    pa_y = kf_y - 355
    half_w = (PAGE_WIDTH - MARGIN * 2 - 10) / 2

    # Priority areas
    draw_card(c, MARGIN, pa_y, half_w, 155, radius=14)
    draw_text(c, "⚠  Priority Areas", MARGIN + 16, pa_y + 128, 13, FONT_BOLD, WARNING)
    draw_divider(c, MARGIN + 16, pa_y + 118, half_w - 32)

    for pi, area in enumerate(data["executive_summary"]["priority_areas"][:4]):
        ay = pa_y + 92 - pi * 28
        rank_colors = [DANGER, WARNING, WARNING, PRIMARY]
        c.setFillColor(rank_colors[pi] if pi < len(rank_colors) else TEXT_SECONDARY)
        c.roundRect(MARGIN + 16, ay - 4, 22, 16, 5, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(MARGIN + 27, ay + 3, str(pi + 1))
        c.setFont(FONT, 11)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 44, ay + 2, area)

    # Strengths
    sx = MARGIN + half_w + 10
    draw_card(c, sx, pa_y, half_w, 155, radius=14)
    draw_text(c, "★  Cognitive Strengths", sx + 16, pa_y + 128, 13, FONT_BOLD, SUCCESS)
    draw_divider(c, sx + 16, pa_y + 118, half_w - 32)

    for si, strength in enumerate(data["executive_summary"]["strongest_areas"][:4]):
        sy_item = pa_y + 92 - si * 28
        c.setFillColor(SUCCESS)
        c.roundRect(sx + 16, sy_item - 4, 22, 16, 5, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(sx + 27, sy_item + 3, str(si + 1))
        c.setFont(FONT, 11)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(sx + 44, sy_item + 2, strength)


# ============================================================
# PAGE 3 — CORE BRAIN FUNCTION ANALYSIS
# ============================================================

def draw_brain_analysis(c, data):

    draw_page_header(
        c,
        "Core Brain Function Analysis",
        "Detailed assessment across 8 cognitive domains",
        3
    )

    draw_page_footer(c, data["report_id"])

    domains = data["domains"]

    content_top = PAGE_HEIGHT - 88
    content_bottom = 50
    usable_h = content_top - content_bottom

    # ============================================================
    # TOP OVERVIEW SECTION
    # ============================================================

    top_h = 230
    top_y = content_top - top_h

    draw_card(
        c,
        MARGIN,
        top_y,
        PAGE_WIDTH - MARGIN * 2,
        top_h,
        radius=16
    )

    # ============================================================
    # HEADER
    # ============================================================

    draw_text(
        c,
        "Cognitive Domain Overview",
        MARGIN + 18,
        content_top - 24,
        15,
        FONT_BOLD
    )


    # ============================================================
    # CENTERED RADAR CHART
    # ============================================================

    radar_cx = PAGE_WIDTH / 2
    radar_cy = top_y + 112

    draw_radar_chart(
        c,
        radar_cx,
        radar_cy,
        68,   # bigger radar
        domains,
        show_values=True
    )

    # ============================================================
    # BOTTOM SECTION
    # ============================================================

    bottom_y = content_bottom
    bottom_h = usable_h - top_h - 18

    col_gap = 14

    col_w = (
        PAGE_WIDTH - MARGIN * 2 - col_gap
    ) / 2

    left_col = MARGIN
    right_col = MARGIN + col_w + col_gap

    card_h = 74
    card_gap = 12

    domain_interp = {
        "Memory": "Retention and recall appear below optimal range.",
        "Attention": "Sustained focus capacity requires improvement.",
        "Processing": "Information processing speed is moderate.",
        "Executive": "Planning and decision-making are within range.",
        "Clarity": "Mental sharpness shows room for improvement.",
        "Language": "Verbal reasoning and comprehension are strong.",
        "Problem Solving": "Logical analysis remains above average.",
        "Reaction Time": "Fast response speed is a clear strength.",
    }

    domain_items = list(domains.items())

    for i, (domain, value) in enumerate(domain_items):

        col_x = left_col if i < 4 else right_col

        row = i if i < 4 else i - 4

        y = (
            bottom_y
            + bottom_h
            - ((row + 1) * (card_h + card_gap))
        )

        draw_card(
            c,
            col_x,
            y,
            col_w,
            card_h,
            radius=12,
            border=True
        )

        # ============================================================
        # LEFT ACCENT
        # ============================================================

        c.setFillColor(score_color(value))

        c.roundRect(
            col_x,
            y,
            5,
            card_h,
            3,
            fill=1,
            stroke=0
        )

        # ============================================================
        # TITLE
        # ============================================================

        c.setFont(FONT_BOLD, 12)
        c.setFillColor(TEXT_PRIMARY)

        c.drawString(
            col_x + 16,
            y + 54,
            domain
        )

        # ============================================================
        # SCORE
        # ============================================================

        score_x = col_x + col_w - 16

        c.setFont(FONT_BOLD, 18)
        c.setFillColor(score_color(value))

        c.drawRightString(
            score_x,
            y + 54,
            f"{value}"
        )

        # ============================================================
        # STATUS BADGE
        # ============================================================

        status = score_status(value)

        badge_widths = {
            "Excellent": 64,
            "Good": 44,
            "Needs Attention": 96,
            "At Risk": 52
        }

        badge_w = badge_widths.get(status, 60)

        badge_x = score_x - badge_w

        draw_tag(
            c,
            badge_x,
            y + 24,
            status,
            score_color(value),
            width=badge_w,
            height=14,
            radius=5
        )

        # ============================================================
        # DESCRIPTION
        # ============================================================

        wrap_text_in_box(
            c,
            domain_interp.get(domain, ""),
            col_x + 16,
            y + 34,
            col_w - 130,
            7.5,
            line_height=9,
            max_lines=2,
            font=FONT,
            color=TEXT_SECONDARY
        )

        # ============================================================
        # PROGRESS BAR
        # ============================================================

        draw_progress_bar(
            c,
            col_x + 16,
            y + 10,
            col_w - 32,
            7,
            value
        )


# ============================================================
# PAGE 4 — LIFESTYLE IMPACT ANALYSIS
# ============================================================

def draw_lifestyle_page(c, data):
    draw_page_header(c, "Lifestyle Impact Analysis",
                     "How your daily habits are affecting cognitive performance", 4)
    draw_page_footer(c, data["report_id"])

    lifestyle = data["lifestyle"]
    content_top = PAGE_HEIGHT - 88

    lifestyle_meta = {
        "Sleep": {
            "icon": "☽",
            "desc": "Sleep quality directly impacts memory consolidation, "
                    "emotional regulation, and cognitive recovery.",
            "tip": "Aim for 7–9 hours of consistent, quality sleep.",
        },
        "Stress": {
            "icon": "⚡",
            "desc": "Chronic stress elevates cortisol, impairing "
                    "working memory and executive function over time.",
            "tip": "Daily mindfulness or breathing exercises can reduce stress load.",
        },
        "Anxiety": {
            "icon": "◎",
            "desc": "Anxiety diverts attentional resources and can "
                    "create cognitive bottlenecks during complex tasks.",
            "tip": "Structured worry time and CBT techniques show strong outcomes.",
        },
        "Burnout": {
            "icon": "▽",
            "desc": "Burnout depletes mental reserves and reduces "
                    "motivation, creativity, and sustained performance.",
            "tip": "Recovery blocks and workload distribution are essential.",
        },
    }

    card_w = (PAGE_WIDTH - MARGIN * 2 - 12) / 2
    card_h = 148
    positions = [
        (MARGIN,              content_top - card_h),
        (MARGIN + card_w + 12, content_top - card_h),
        (MARGIN,              content_top - card_h * 2 - 20),
        (MARGIN + card_w + 12, content_top - card_h * 2 - 20),
    ]

    for i, (key, val) in enumerate(lifestyle.items()):
        meta = lifestyle_meta.get(key, {})
        lx, ly = positions[i]
        draw_card(c, lx, ly, card_w, card_h, radius=14)

        # Top accent
        c.setFillColor(score_color(val))
        c.roundRect(lx, ly + card_h - 4, card_w, 4, 2, fill=1, stroke=0)

        # Icon + Title row
        c.setFont(FONT_BOLD, 16)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(lx + 14, ly + card_h - 28, f"{meta.get('icon', '●')}  {key}")

        # Score
        c.setFont(FONT_BOLD, 34)
        c.setFillColor(score_color(val))
        c.drawString(lx + 14, ly + card_h - 66, str(val))
        c.setFont(FONT, 11)
        c.setFillColor(TEXT_MUTED)
        c.drawString(lx + 14 + c.stringWidth(str(val), FONT_BOLD, 34) + 4,
                     ly + card_h - 60, "/ 100")

        # Status tag
        draw_tag(c, lx + 14, ly + card_h - 88, score_status(val),
                 score_color(val), height=16, radius=6)

        # Progress bar
        draw_progress_bar(c, lx + 14, ly + card_h - 106, card_w - 28, 8, val)

        # Description
        c.setFont(FONT, 8.5)
        c.setFillColor(TEXT_SECONDARY)
        wrap_text_in_box(c, meta.get("desc", ""), lx + 14, ly + card_h - 112,
                         card_w - 28, 8.5, line_height=12, max_lines=2)

        # Tip
        c.setFillColor(score_color_light(val))
        c.roundRect(lx + 10, ly + 10, card_w - 20, 34, 6, fill=1, stroke=0)
        c.setFont(FONT, 8)
        c.setFillColor(score_color(val))
        tip = meta.get("tip", "")
        wrap_text_in_box(
    c,
    f"Tip: {tip}",
    lx + 18,
    ly + 24,
    card_w - 36,
    8,
    line_height=10,
    max_lines=2
)

    # ── COMPARISON CHART ──
    chart_y = content_top - card_h * 2 - 54
    chart_h = 140
    draw_card(c, MARGIN, chart_y - chart_h, PAGE_WIDTH - MARGIN * 2, chart_h, radius=14)
    draw_text(c, "Lifestyle Factor Comparison", MARGIN + 16, chart_y - 22, 13, FONT_BOLD)
    draw_divider(c, MARGIN + 16, chart_y - 32, PAGE_WIDTH - MARGIN * 2 - 32)

    bar_area_w = PAGE_WIDTH - MARGIN * 2 - 32
    bar_h = 16
    keys = list(lifestyle.keys())
    for bi, key in enumerate(keys):
        val = lifestyle[key]
        by = chart_y - 52 - bi * 24
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_SECONDARY)
        c.drawString(MARGIN + 16, by + 2, key)
        draw_progress_bar(c, MARGIN + 100, by, bar_area_w - 145, bar_h, val)
        c.setFont(FONT_BOLD, 10)
        c.setFillColor(score_color(val))
        c.drawString(MARGIN + bar_area_w - 40, by + 2, f"{val}/100")


# ============================================================
# PAGE 5 — AI COGNITIVE INSIGHTS
# ============================================================
def draw_ai_insights_page(c, data):

    draw_page_header(
        c,
        "AI Cognitive Insights",
        "Personalized analysis powered by Limitless AI",
        5
    )

    draw_page_footer(c, data["report_id"])

    ai = data["ai_insights"]

    content_top = PAGE_HEIGHT - 88

    # ============================================================
    # MAIN ANALYSIS CARD
    # ============================================================

    main_h = 118

    draw_card(
        c,
        MARGIN,
        content_top - main_h,
        PAGE_WIDTH - MARGIN * 2,
        main_h,
        radius=16
    )

    # AI Badge
    c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.08))

    c.roundRect(
        MARGIN + 16,
        content_top - 24,
        54,
        16,
        7,
        fill=1,
        stroke=0
    )

    c.setFillColor(PRIMARY)
    c.setFont(FONT_BOLD, 7.5)

    c.drawCentredString(
        MARGIN + 43,
        content_top - 18,
        "AI ANALYSIS"
    )

    # Title
    draw_text(
        c,
        "Cognitive Performance Summary",
        MARGIN + 16,
        content_top - 46,
        14,
        FONT_BOLD
    )

    # Summary text
    wrap_text_in_box(
        c,
        ai["analysis"],
        MARGIN + 16,
        content_top - 60,
        PAGE_WIDTH - MARGIN * 2 - 32,
        10,
        line_height=15,
        max_lines=4,
        font=FONT,
        color=TEXT_SECONDARY
    )

    # ============================================================
    # INSIGHTS + CAUSES SECTION
    # ============================================================

    section_y = content_top - 138

    half_w = (PAGE_WIDTH - MARGIN * 2 - 12) / 2

    card_h = 132

    # ============================================================
    # BEHAVIORAL INSIGHTS
    # ============================================================

    draw_card(
        c,
        MARGIN,
        section_y - card_h,
        half_w,
        card_h,
        radius=14
    )

    draw_text(
        c,
        "Behavioral Insights",
        MARGIN + 16,
        section_y - 18,
        12,
        FONT_BOLD,
        PRIMARY
    )

    draw_divider(
        c,
        MARGIN + 16,
        section_y - 28,
        half_w - 32
    )

    for bii, insight in enumerate(ai["behavioral_insights"][:4]):

        iy = section_y - 52 - bii * 24

        # Bullet
        bullet_y = iy + 6

        c.setFillColor(PRIMARY)

        c.roundRect(
            MARGIN + 16,
            bullet_y,
            5,
            10,
            2,
            fill=1,
            stroke=0
        )

        # Text
        wrap_text_in_box(
            c,
            insight,
            MARGIN + 30,
            iy + 12,
            half_w - 46,
            8.5,
            line_height=10,
            max_lines=2,
            font=FONT,
            color=TEXT_SECONDARY
        )

    # ============================================================
    # POTENTIAL CAUSES
    # ============================================================

    cx = MARGIN + half_w + 12

    draw_card(
        c,
        cx,
        section_y - card_h,
        half_w,
        card_h,
        radius=14
    )

    draw_text(
        c,
        "Potential Causes",
        cx + 16,
        section_y - 18,
        12,
        FONT_BOLD,
        WARNING
    )

    draw_divider(
        c,
        cx + 16,
        section_y - 28,
        half_w - 32
    )

    for cai, cause in enumerate(ai["potential_causes"][:4]):

        cy = section_y - 52 - cai * 24

        # Bullet
        bullet_y = cy + 6

        c.setFillColor(WARNING)

        c.roundRect(
            cx + 16,
            bullet_y,
            5,
            10,
            2,
            fill=1,
            stroke=0
        )

        # Text
        wrap_text_in_box(
            c,
            cause,
            cx + 30,
            cy + 12,
            half_w - 46,
            8.5,
            line_height=10,
            max_lines=2,
            font=FONT,
            color=TEXT_SECONDARY
        )

    # ============================================================
    # PROJECTION SECTION
    # ============================================================

    proj = ai["improvement_projection"]

    proj_y = section_y - 182

    draw_text(
        c,
        "Projected Improvement (30 Days)",
        MARGIN,
        proj_y + 12,
        12,
        FONT_BOLD
    )

    proj_card_h = 130

    gap = 10

    proj_w = (
        PAGE_WIDTH - MARGIN * 2 - gap * 2
    ) / 3

    for pi, (domain, vals) in enumerate(proj.items()):

        px = MARGIN + pi * (proj_w + gap)

        draw_card(
            c,
            px,
            proj_y - proj_card_h,
            proj_w,
            proj_card_h,
            radius=14
        )

        # ============================================================
        # DOMAIN TITLE
        # ============================================================

        c.setFont(FONT_BOLD, 11)
        c.setFillColor(TEXT_PRIMARY)

        c.drawCentredString(
            px + proj_w / 2,
            proj_y - 20,
            domain
        )

        cur = vals["current"]
        prj = vals["projected"]
        gain = prj - cur

        # ============================================================
        # SCORES
        # ============================================================

        score_y = proj_y - 48

        c.setFont(FONT_BOLD, 18)
        c.setFillColor(DANGER)

        c.drawCentredString(
            px + proj_w / 2 - 28,
            score_y,
            str(cur)
        )

        c.setFont(FONT_BOLD, 16)
        c.setFillColor(TEXT_MUTED)

        c.drawCentredString(
            px + proj_w / 2,
            score_y + 1,
            "→"
        )

        c.setFont(FONT_BOLD, 18)
        c.setFillColor(SUCCESS)

        c.drawCentredString(
            px + proj_w / 2 + 28,
            score_y,
            str(prj)
        )

        # ============================================================
        # GAIN BADGE
        # ============================================================

        c.setFillColor(SUCCESS_LIGHT)

        c.roundRect(
            px + proj_w / 2 - 22,
            proj_y - 74,
            44,
            16,
            7,
            fill=1,
            stroke=0
        )

        c.setFillColor(SUCCESS)
        c.setFont(FONT_BOLD, 8)

        c.drawCentredString(
            px + proj_w / 2,
            proj_y - 68,
            f"+{gain} pts"
        )

        # ============================================================
        # BARS
        # ============================================================

        draw_text(
            c,
            "Current",
            px + 10,
            proj_y - 88,
            7,
            FONT,
            TEXT_MUTED
        )

        draw_progress_bar(
            c,
            px + 10,
            proj_y - 96,
            proj_w - 20,
            5,
            cur
        )

        draw_text(
            c,
            "Projected",
            px + 10,
            proj_y - 108,
            7,
            FONT,
            TEXT_MUTED
        )

        draw_progress_bar(
            c,
            px + 10,
            proj_y - 116,
            proj_w - 20,
            5,
            prj
        )


# ============================================================
# PAGE 6 — WELLNESS INDICATORS
# ============================================================

def draw_wellness_page(c, data):
    draw_page_header(c, "Wellness Indicators",
                     "Observed patterns that may affect your cognitive performance", 6)
    draw_page_footer(c, data["report_id"])

    indicators = data["wellness_indicators"]
    content_top = PAGE_HEIGHT - 88
    card_h = 112
    gap = 14

    for ii, ind in enumerate(indicators):
        iy = content_top - 14 - ii * (card_h + gap)
        draw_card(c, MARGIN, iy - card_h, PAGE_WIDTH - MARGIN * 2, card_h, radius=14)

        # Left accent strip
        c.setFillColor(WARNING)
        c.roundRect(MARGIN, iy - card_h, 5, card_h, 3, fill=1, stroke=0)

        # Warning icon circle
        c.setFillColor(WARNING_LIGHT)
        c.circle(MARGIN + 34, iy - card_h / 2, 20, fill=1, stroke=0)
        c.setFillColor(WARNING)
        c.setFont(FONT_BOLD, 16)
        c.drawCentredString(MARGIN + 34, iy - card_h / 2 - 5, "⚠")

        # Title
        c.setFont(FONT_BOLD, 14)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 64, iy - 22, ind["title"])

        # Description
        c.setFont(FONT, 11)
        c.setFillColor(TEXT_SECONDARY)
        wrap_text_in_box(c, ind["description"],
                         MARGIN + 64, iy - 40,
                         PAGE_WIDTH - MARGIN * 2 - 80, 11,
                         line_height=16, max_lines=3)

        # Tag
        draw_tag(c, MARGIN + 64, iy - card_h + 14,
                 "Wellness Observation", WARNING_LIGHT, WARNING, height=18, radius=6)

    # Disclaimer
    disc_y = content_top - 14 - len(indicators) * (card_h + gap) - 20
    c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.06))
    c.roundRect(MARGIN, disc_y - 56, PAGE_WIDTH - MARGIN * 2, 56, 10, fill=1, stroke=0)
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(0.5)
    c.roundRect(MARGIN, disc_y - 56, PAGE_WIDTH - MARGIN * 2, 56, 10, fill=0, stroke=1)
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(PRIMARY)
    c.drawString(MARGIN + 14, disc_y - 18, "ℹ  IMPORTANT NOTICE")
    c.setFont(FONT, 9)
    c.setFillColor(TEXT_SECONDARY)
    wrap_text_in_box(
    c,
    "These are wellness observations only and are not clinical diagnoses. Please consult a qualified healthcare professional for medical advice.",
    MARGIN + 14,
    disc_y - 30,
    PAGE_WIDTH - MARGIN * 2 - 28,
    9,
    line_height=11,
    max_lines=2
)


# ============================================================
# PAGE 7 — COGNITIVE STRENGTHS
# ============================================================

def draw_strengths_page(c, data):
    draw_page_header(c, "Cognitive Strengths",
                     "Your standout capabilities and performance advantages", 7)
    draw_page_footer(c, data["report_id"])

    strengths = data["strengths"]
    content_top = PAGE_HEIGHT - 88
    card_h = 105
    gap = 14

    # Intro card
    draw_card(c, MARGIN, content_top - 60, PAGE_WIDTH - MARGIN * 2, 52, radius=14,
              bg=HexColor("#F0FDF4"))
    c.setFillColor(SUCCESS)
    c.setFont(FONT_BOLD, 11)
    c.drawString(MARGIN + 16, content_top - 28,
                 "★  Your cognitive profile shows meaningful strengths worth celebrating and building upon.")
    c.setFont(FONT, 10)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(MARGIN + 16, content_top - 44,
                 "These areas demonstrate resilience and can serve as anchors for overall improvement.")

    strength_descs = {
        "Reaction Time":       "Fast processing and quick response speed remain a significant strength.",
        "Language Processing": "Strong comprehension and verbal reasoning abilities detected.",
        "Problem Solving":     "Logical thinking and analytical problem solving remain above average.",
    }

    for si, strength in enumerate(strengths):
        sy = content_top - 82 - si * (card_h + gap)
        draw_card(c, MARGIN, sy - card_h, PAGE_WIDTH - MARGIN * 2, card_h, radius=14)

        # Rank badge
        rank_colors = [SUCCESS, PRIMARY, PRIMARY_LIGHT]
        rc = rank_colors[si] if si < len(rank_colors) else TEXT_MUTED
        c.setFillColor(rc)
        c.circle(MARGIN + 28, sy - card_h / 2, 18, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 14)
        c.drawCentredString(MARGIN + 28, sy - card_h / 2 - 5, str(si + 1))

        # Title
        c.setFont(FONT_BOLD, 16)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 56, sy - 20, strength["title"])

        # Score
        c.setFont(FONT_BOLD, 20)
        c.setFillColor(SUCCESS)
        c.drawRightString(PAGE_WIDTH - MARGIN - 14, sy - 20, f"{strength['score']}/100")

        # Description
        desc = strength_descs.get(strength["title"], strength.get("description", ""))
        c.setFont(FONT, 10.5)
        c.setFillColor(TEXT_SECONDARY)
        c.drawString(MARGIN + 56, sy - 40, desc)

        # Progress bar
        draw_progress_bar(c, MARGIN + 56, sy - card_h + 30,
                          PAGE_WIDTH - MARGIN * 2 - 70, 10, strength["score"])

        # Score pips on bar
        for pip_val in [25, 50, 75, 100]:
            pip_x = MARGIN + 56 + (pip_val / 100) * (PAGE_WIDTH - MARGIN * 2 - 70)
            c.setFillColor(BACKGROUND)
            c.circle(pip_x, sy - card_h + 25, 2, fill=1, stroke=0)

        # Status tag
        draw_tag(c, MARGIN + 56, sy - card_h + 6,
                 score_status(strength["score"]), SUCCESS, height=14, radius=5)

    # Radar mini for strengths
    all_domains = data["domains"]
    chart_y = content_top - 82 - len(strengths) * (card_h + gap) - 20
    chart_h = 160
    if chart_y - chart_h > 44:
        draw_card(c, MARGIN, chart_y - chart_h,
                  PAGE_WIDTH - MARGIN * 2, chart_h, radius=14)
        draw_text(c, "Strength Distribution",
                  MARGIN + 14, chart_y - 20, 12, FONT_BOLD)
        # Mini bar chart for all domains sorted by score
        sorted_domains = sorted(all_domains.items(), key=lambda x: x[1], reverse=True)
        bar_w_total = PAGE_WIDTH - MARGIN * 2 - 28
        bar_item_w = bar_w_total / len(sorted_domains)
        for di, (dname, dval) in enumerate(sorted_domains):
            bx = MARGIN + 14 + di * bar_item_w
            max_bar_h = chart_h - 50
            bh = (dval / 100) * max_bar_h
            c.setFillColor(score_color(dval))
            c.roundRect(bx + 4, chart_y - chart_h + 28, bar_item_w - 8, bh, 4, fill=1, stroke=0)
            c.setFont(FONT, 7)
            c.setFillColor(TEXT_SECONDARY)
            c.drawCentredString(bx + bar_item_w / 2, chart_y - chart_h + 18,
                                dname[:5])
            c.setFont(FONT_BOLD, 8)
            c.setFillColor(TEXT_PRIMARY)
            c.drawCentredString(bx + bar_item_w / 2,
                                chart_y - chart_h + 28 + bh + 4, str(dval))


# ============================================================
# PAGE 8 — 30 DAY ROADMAP
# ============================================================

def draw_roadmap_page(c, data):
    draw_page_header(c, "30-Day Improvement Roadmap",
                     "Your personalized action plan for cognitive enhancement", 8)
    draw_page_footer(c, data["report_id"])

    roadmap = data["roadmap"]
    content_top = PAGE_HEIGHT - 88
    card_h = 118
    gap = 10

    # Timeline line
    line_x = MARGIN + 36
    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(2)
    c.setDash(4, 4)
    c.line(line_x, content_top - 20,
           line_x, content_top - len(roadmap) * (card_h + gap) - 20)
    c.setDash()

    week_colors = [PRIMARY, SECONDARY, SUCCESS, WARNING]

    for wi, week_data in enumerate(roadmap):
        wy = content_top - 20 - wi * (card_h + gap)
        wc = week_colors[wi % len(week_colors)]

        # Timeline node
        c.setFillColor(wc)
        c.circle(line_x, wy - card_h / 2, 14, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(line_x, wy - card_h / 2 - 3, str(wi + 1))

        # Card
        cx = MARGIN + 60
        cw = PAGE_WIDTH - cx - MARGIN
        draw_card(c, cx, wy - card_h, cw, card_h, radius=14)

        # Top accent
        c.setFillColor(wc)
        c.roundRect(cx, wy - 4, cw, 4, 2, fill=1, stroke=0)

        # Week label
        c.setFillColor(wc)
        c.roundRect(cx + 14, wy - 24, 60, 18, 7, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 9)
        c.drawCentredString(cx + 44, wy - 17, week_data["week"])

        # Focus area
        c.setFont(FONT_BOLD, 13)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(cx + 84, wy - 19, week_data["focus"])

        # Tasks
        tasks = week_data["tasks"]
        task_col_w = (cw - 28) / 3
        for ti, task in enumerate(tasks[:3]):
            tx = cx + 14 + ti * task_col_w
            ty = wy - 52

            # Task box
            c.setFillColor(SURFACE)
            c.roundRect(tx, ty - 30, task_col_w - 8, 34, 6, fill=1, stroke=0)

            # Checkbox
            c.setStrokeColor(BORDER_COLOR)
            c.setLineWidth(1)
            c.roundRect(tx + 8, ty - 14, 12, 12, 3, fill=0, stroke=1)

            c.setFont(FONT, 9)
            c.setFillColor(TEXT_SECONDARY)
            # Truncate task text
            task_display = task if len(task) <= 28 else task[:25] + "..."
            c.drawString(tx + 24, ty - 8, task_display)

        # Milestone badge
        milestones = [
            "Foundation Building",
            "Focus Habits Forming",
            "Peak Performance Mode",
            "Optimization & Review",
        ]
        ml = milestones[wi] if wi < len(milestones) else ""
        c.setFillColor(score_color_light(50 + wi * 10))
        c.roundRect(cx + cw - 130, wy - card_h + 10, 116, 20, 8, fill=1, stroke=0)
        c.setFillColor(wc)
        c.setFont(FONT, 8)
        c.drawCentredString(cx + cw - 72, wy - card_h + 18, f"✦  {ml}")


# ============================================================
# PAGE 9 — COGNITIVE AGE
# ============================================================

def draw_cognitive_age_page(c, data):
    draw_page_header(c, "Cognitive Age",
                     "Longitudinal performance tracking and calibration", 9)
    draw_page_footer(c, data["report_id"])

    cog = data["cognitive_age"]
    content_top = PAGE_HEIGHT - 88

    # Main status card
    draw_card(c, MARGIN, content_top - 160, PAGE_WIDTH - MARGIN * 2, 150, radius=14)

    # Animated-style progress ring placeholder
    cx_ring = MARGIN + 80
    cy_ring = content_top - 85
    c.setStrokeColor(HexColor("#E2E8F0"))
    c.setLineWidth(14)
    c.circle(cx_ring, cy_ring, 46, stroke=1, fill=0)
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(14)
    c.arc(cx_ring - 46, cy_ring - 46, cx_ring + 46, cy_ring + 46,
          startAng=90, extent=-200)
    c.setFillColor(PRIMARY)
    c.setFont(FONT_BOLD, 12)
    c.drawCentredString(cx_ring, cy_ring + 4, "IN")
    c.setFont(FONT_BOLD, 10)
    c.drawCentredString(cx_ring, cy_ring - 10, "PROGRESS")

    c.setFont(FONT_BOLD, 18)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(MARGIN + 150, content_top - 60, cog["status"])

    c.setFont(FONT, 11)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(MARGIN + 150, content_top - 82,
                 "Additional data points are being collected to establish your")
    c.drawString(MARGIN + 150, content_top - 96,
                 "cognitive age baseline with high accuracy.")

    # Progress tracker
    draw_tag(c, MARGIN + 150, content_top - 128,
             "Estimated completion: 2–3 more sessions", PRIMARY_LIGHT,
             white, height=18, radius=8)

    # Checklist cards
    cl_y = content_top - 190
    half_w = (PAGE_WIDTH - MARGIN * 2 - 10) / 2

    # Completed
    draw_card(c, MARGIN, cl_y - 148, half_w, 140, radius=14, bg=HexColor("#F0FDF4"))
    draw_text(c, "✓  Completed", MARGIN + 14, cl_y - 24, 13, FONT_BOLD, SUCCESS)
    draw_divider(c, MARGIN + 14, cl_y - 34, half_w - 28, color=HexColor("#BBF7D0"))

    for ci, item in enumerate(cog["completed"]):
        iy = cl_y - 56 - ci * 28
        c.setFillColor(SUCCESS)
        c.circle(MARGIN + 22, iy + 5, 7, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 9)
        c.drawCentredString(MARGIN + 22, iy + 2, "✓")
        c.setFont(FONT, 10.5)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 36, iy + 1, item)

    # Upcoming
    ux = MARGIN + half_w + 10
    draw_card(c, ux, cl_y - 148, half_w, 140, radius=14)
    draw_text(c, "○  Upcoming", ux + 14, cl_y - 24, 13, FONT_BOLD, TEXT_SECONDARY)
    draw_divider(c, ux + 14, cl_y - 34, half_w - 28)

    for ui, item in enumerate(cog["upcoming"]):
        iy = cl_y - 56 - ui * 28
        c.setStrokeColor(HexColor("#CBD5E1"))
        c.setLineWidth(1.5)
        c.circle(ux + 22, iy + 5, 7, stroke=1, fill=0)
        c.setFont(FONT, 10.5)
        c.setFillColor(TEXT_SECONDARY)
        c.drawString(ux + 36, iy + 1, item)

    # Why it matters card
    wim_y = cl_y - 360
    draw_card(c, MARGIN, wim_y, PAGE_WIDTH - MARGIN * 2, 100, radius=14,
              bg=HexColor("#EFF6FF"))
    draw_text(c, "Why Cognitive Age Matters", MARGIN + 14, wim_y + 74, 13, FONT_BOLD, PRIMARY)
    c.setFont(FONT, 10)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(MARGIN + 14, wim_y + 56,
                 "Cognitive age measures how your mental performance compares to population averages for")
    c.drawString(MARGIN + 14, wim_y + 42,
                 "your chronological age. A cognitive age younger than your actual age indicates strong")
    c.drawString(MARGIN + 14, wim_y + 28,
                 "brain health. Regular assessments allow tracking of improvement over time.")


# ============================================================
# PAGE 10 — LEGAL & PRIVACY
# ============================================================

def draw_legal_page(c, data):
    draw_page_header(c, "Legal, Privacy & Report Details",
                     "Important information about this assessment and your data", 10)
    draw_page_footer(c, data["report_id"])

    legal = data["legal"]
    content_top = PAGE_HEIGHT - 88

    sections = [
        {
            "title": "Report Methodology",
            "icon": "⊙",
            "color": PRIMARY,
            "content": (
                "This report is generated by the Limitless AI cognitive wellness engine using "
                "a combination of validated psychometric assessments, self-reported lifestyle data, "
                "and proprietary machine learning models trained on large-scale population data."
            ),
        },
        {
            "title": "Medical Disclaimer",
            "icon": "⚕",
            "color": WARNING,
            "content": legal["disclaimer"] + (
                " Results should not be used to self-diagnose or treat any medical condition. "
                "Always consult a qualified healthcare professional for personalized medical advice."
            ),
        },
        {
            "title": "Data Privacy & Security",
            "icon": "⊕",
            "color": SUCCESS,
            "content": legal["privacy"] + (
                " Data is never sold or shared with third parties without explicit consent. "
                "You retain full ownership of your personal wellness data at all times."
            ),
        },
        {
            "title": "HIPAA Readiness",
            "icon": "⊞",
            "color": SECONDARY,
            "content": legal["hipaa"] + (
                " Technical and administrative safeguards are in place to protect protected "
                "health information (PHI) in alignment with HIPAA guidelines."
            ),
        },
    ]

    card_h = 88
    gap = 10
    for si, sec in enumerate(sections):
        sy = content_top - 14 - si * (card_h + gap)
        draw_card(c, MARGIN, sy - card_h, PAGE_WIDTH - MARGIN * 2, card_h, radius=14)

        c.setFillColor(sec["color"])
        c.roundRect(MARGIN, sy - card_h, 5, card_h, 3, fill=1, stroke=0)

        # Icon
        c.setFillColor(score_color_light(70))
        c.circle(MARGIN + 30, sy - card_h / 2, 17, fill=1, stroke=0)
        c.setFillColor(sec["color"])
        c.setFont(FONT_BOLD, 13)
        c.drawCentredString(MARGIN + 30, sy - card_h / 2 - 5, sec["icon"])

        c.setFont(FONT_BOLD, 12)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 56, sy - 20, sec["title"])

        c.setFont(FONT, 9.5)
        c.setFillColor(TEXT_SECONDARY)
        wrap_text_in_box(c, sec["content"], MARGIN + 56, sy - 40,
                         PAGE_WIDTH - MARGIN * 2 - 70, 9.5,
                         line_height=13, max_lines=4)

    # Contact / branding
    brand_y = content_top - 14 - len(sections) * (card_h + gap) - 20
    draw_card(c, MARGIN, brand_y - 70, PAGE_WIDTH - MARGIN * 2, 66, radius=14,
              bg=GRADIENT_1)

    c.setFillColor(white)
    c.setFont(FONT_BOLD, 16)
    c.drawString(MARGIN + 18, brand_y - 24, "LIMITLESS AI")
    c.setFont(FONT, 10)
    c.setFillColor(Color(1, 1, 1, alpha=0.7))
    c.drawString(MARGIN + 18, brand_y - 40,
                 "The future of cognitive health is measurable, trackable, and improvable.")
    c.setFont(FONT, 10)
    c.setFillColor(Color(1, 1, 1, alpha=0.6))
    c.drawRightString(PAGE_WIDTH - MARGIN - 18, brand_y - 24, legal.get("contact", "support@limitless.ai"))
    c.drawRightString(PAGE_WIDTH - MARGIN - 18, brand_y - 40,
                      f"Report ID: {data['report_id']}")


# ============================================================
# TEXT WRAPPING HELPER
# ============================================================

def wrap_text_in_box(c, text, x, y, width, font_size, line_height=14,
                     max_lines=999, font=FONT, color=TEXT_SECONDARY):
    """Simple word-wrap within a fixed width."""
    c.setFont(font, font_size)
    c.setFillColor(color)
    words = text.split()
    line = ""
    lines = []
    for word in words:
        test = (line + " " + word).strip()
        if c.stringWidth(test, font, font_size) <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    for li, ln in enumerate(lines[:max_lines]):
        c.drawString(x, y - li * line_height, ln)


# ============================================================
# BUILD REPORT
# ============================================================


def build_report(analysis,brand=None):

    # ============================================
    # Transform analysis -> PDF report structure
    # ============================================

    data = transform_analysis_to_report(
        analysis
    )

    # ============================================
    # Create in-memory buffer
    # ============================================

    buffer = BytesIO()

    # ============================================
    # Create PDF canvas
    # ============================================

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    c.setTitle(
        "Limitless Cognitive Wellness Report"
    )

    c.setAuthor(
        "Limitless AI"
    )

    c.setSubject(
        f"Cognitive Wellness Assessment — {data['user']['name']}"
    )

    # ============================================
    # PAGES
    # ============================================

    draw_cover_page(c, data)
    c.showPage()

    draw_executive_summary(c, data)
    c.showPage()

    draw_brain_analysis(c, data)
    c.showPage()

    draw_lifestyle_page(c, data)
    c.showPage()

    draw_ai_insights_page(c, data)
    c.showPage()

    draw_wellness_page(c, data)
    c.showPage()

    draw_strengths_page(c, data)
    c.showPage()

    draw_roadmap_page(c, data)
    c.showPage()

    draw_cognitive_age_page(c, data)
    c.showPage()

    draw_legal_page(c, data)
    c.showPage()

    # ============================================
    # SAVE PDF
    # ============================================

    c.save()

    # ============================================
    # Return bytes
    # ============================================

    pdf_bytes = buffer.getvalue()

    buffer.close()

    return pdf_bytes



# ============================================================
# SAMPLE DATA
# ============================================================

sample_data = {
    "report_id": "LMT-2026-001284",
    "overall_score": 72,
    "risk_level": "Needs Attention",
    "user": {
        "name": "Sarah Johnson",
        "age": 29,
        "gender": "Female",
        "assessment_date": "13 June 2026",
    },
    "domains": {
        "Memory":         38,
        "Attention":      31,
        "Processing":     58,
        "Executive":      52,
        "Clarity":        44,
        "Language":       72,
        "Problem Solving":68,
        "Reaction Time":  80,
    },
    "lifestyle": {
        "Sleep":   54,
        "Stress":  68,
        "Anxiety": 73,
        "Burnout": 61,
    },
    "executive_summary": {
        "summary": (
            "Cognitive performance appears moderately affected by elevated stress "
            "and inconsistent sleep quality. Attention and memory are the primary "
            "areas requiring improvement while reaction time and language performance "
            "remain strong relative assets."
        ),
        "key_findings": [
            "Memory performance is below expected range",
            "Attention and focus require significant improvement",
            "Anxiety appears to be impacting cognition",
            "Reaction time remains a clear relative strength",
            "Sleep quality is contributing to reduced mental clarity",
            "Burnout risk is present and should be monitored",
        ],
        "priority_areas": [
            "Attention Control",
            "Memory Retention",
            "Stress Recovery",
            "Mental Clarity",
        ],
        "strongest_areas": [
            "Reaction Time",
            "Language Processing",
            "Problem Solving",
        ],
    },
    "ai_insights": {
        "analysis": (
            "The primary factor affecting cognitive performance appears to be reduced "
            "attention capacity combined with elevated stress levels and inconsistent "
            "sleep quality. Addressing these three pillars simultaneously is likely to "
            "produce measurable improvements within 30 days."
        ),
        "behavioral_insights": [
            "Frequent mental fatigue patterns detected",
            "Attention drift increases during complex tasks",
            "Stress appears to be reducing working memory efficiency",
            "Reaction speed remains highly resilient to lifestyle factors",
        ],
        "potential_causes": [
            "Inconsistent sleep schedule",
            "High cognitive workload",
            "Elevated anxiety levels",
            "Insufficient recovery periods",
        ],
        "improvement_projection": {
            "Memory":    {"current": 38, "projected": 55},
            "Attention": {"current": 31, "projected": 52},
            "Clarity":   {"current": 44, "projected": 60},
        },
    },
    "wellness_indicators": [
        {
            "title": "Possible Attention Difficulties",
            "description": (
                "Difficulty maintaining sustained focus for extended periods "
                "is indicated by assessment patterns. This may be linked to "
                "elevated anxiety and fragmented sleep cycles."
            ),
        },
        {
            "title": "Possible Mood-Related Concentration Issues",
            "description": (
                "Emotional stressors appear to be reducing cognitive efficiency "
                "and may be creating attentional interference during demanding tasks."
            ),
        },
        {
            "title": "Elevated Stress Response",
            "description": (
                "Stress patterns appear to be affecting memory retention and "
                "mental clarity, particularly during periods of high cognitive load."
            ),
        },
    ],
    "strengths": [
        {
            "title": "Reaction Time",
            "score": 80,
            "description": "Fast processing and quick response speed remain a significant strength.",
        },
        {
            "title": "Language Processing",
            "score": 72,
            "description": "Strong comprehension and verbal reasoning abilities detected.",
        },
        {
            "title": "Problem Solving",
            "score": 68,
            "description": "Logical thinking and analytical problem solving remain above average.",
        },
    ],
    "roadmap": [
        {
            "week": "Week 1",
            "focus": "Sleep Optimization",
            "tasks": [
                "Reduce screen time 1hr before bed",
                "Maintain consistent sleep schedule",
                "Track sleep duration daily",
            ],
        },
        {
            "week": "Week 2",
            "focus": "Attention Training",
            "tasks": [
                "Practice 25-min Pomodoro sessions",
                "Reduce multitasking habits",
                "Implement 90-min deep focus blocks",
            ],
        },
        {
            "week": "Week 3",
            "focus": "Recovery & Exercise",
            "tasks": [
                "Daily 30-min physical activity",
                "Practice progressive muscle relaxation",
                "Reduce cognitive overload triggers",
            ],
        },
        {
            "week": "Week 4",
            "focus": "Memory Optimization",
            "tasks": [
                "Daily memory recall exercises",
                "Full progress review and scoring",
                "Habit reinforcement and journaling",
            ],
        },
    ],
    "cognitive_age": {
        "status": "Calibration in Progress",
        "completed": [
            "Cognitive Wellness Score",
            "Lifestyle Analysis",
            "Wellness Indicators",
        ],
        "upcoming": [
            "Cognitive Age Calibration",
            "Predictive Cognitive Tracking",
            "Longitudinal Trend Analysis",
        ],
    },
    "legal": {
        "disclaimer": (
            "This report is an AI-generated wellness assessment and not a medical diagnosis."
        ),
        "privacy": (
            "All data is securely processed and stored using enterprise-grade encryption."
        ),
        "hipaa": (
            "Platform architecture is designed with HIPAA-readiness considerations."
        ),
        "contact": "support@limitless.ai",
    },
}

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    build_report(sample_data)
