"""
LIMITLESS PREMIUM REPORT — PRODUCTION REDESIGN
Run:
    python pdf_service.py
"""
import io
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
from app.scoring.engine import get_age_band
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

STRENGTH_BADGES = {
    "Reaction Time":   {"badge": "Fast Thinker",            "icon": "⚡"},
    "Language":        {"badge": "Strong Verbal Processing", "icon": "📚"},
    "Problem Solving": {"badge": "Above-Avg Problem Solver", "icon": "🎯"},
    "Memory":          {"badge": "Sharp Memory",             "icon": "🧠"},
    "Attention":       {"badge": "Focused Mind",             "icon": "🔍"},
    "Executive":       {"badge": "Strategic Thinker",        "icon": "♟"},
    "Processing":      {"badge": "Quick Processor",          "icon": "⚙"},
    "Clarity":         {"badge": "Clear Thinker",            "icon": "💡"},
}
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
    ux, uy, uw, uh = MARGIN, PAGE_HEIGHT - 590, PAGE_WIDTH - MARGIN * 2, 80
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

    kpi_y = PAGE_HEIGHT - 690
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
    def _interpolate_color(c1, c2, t):
        """Linearly interpolate between two Color objects at t in [0,1]."""
        return Color(
            c1.red + (c2.red - c1.red) * t,
            c1.green + (c2.green - c1.green) * t,
            c1.blue + (c2.blue - c1.blue) * t,
            alpha=c1.alpha + (c2.alpha - c1.alpha) * t,
        )


    def draw_gradient_hbar(c, x, y, width, height, color_start, color_end, radius=4, segments=60):
        """Draw a horizontal bar filled with a left-to-right gradient, clipped to a rounded rect."""
        c.saveState()
        path = c.beginPath()
        path.roundRect(x, y, width, height, radius)
        c.clipPath(path, stroke=0, fill=0)

        seg_width = width / segments
        for i in range(segments):
            t = i / (segments - 1) if segments > 1 else 0
            c.setFillColor(_interpolate_color(color_start, color_end, t))
            c.rect(x + i * seg_width, y, seg_width + 1, height, fill=1, stroke=0)  # +1 avoids hairline gaps
        c.restoreState()


    # --- Cognitive Age Card with horizontal gradient bar (between KPI strip and CTA band) ---
    cog_age_display = data["user"]["cognitive_age_display"]
    cog_age_message = data["user"]["cognitive_age_message"]
    actual_age = data["user"]["age"]

    CARD_HEIGHT = 56
    CTA_BAND_TOP_Y = 350   # <-- still need your real CTA band height here
    CARD_Y = CTA_BAND_TOP_Y + 8
    CARD_X = MARGIN
    CARD_WIDTH = PAGE_WIDTH - 2 * MARGIN

    # Card background
    c.setFillColor(Color(1, 1, 1, alpha=0.12))
    c.roundRect(CARD_X, CARD_Y, CARD_WIDTH, CARD_HEIGHT, 8, fill=1, stroke=0)

    # Header row: label left, message right
    c.setFont(FONT_BOLD, 10)
    c.setFillColor(Color(1, 1, 1, alpha=0.70))
    c.drawString(CARD_X + 16, CARD_Y + CARD_HEIGHT - 14, "COGNITIVE AGE")

    c.setFont(FONT, 9)
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.drawRightString(CARD_X + CARD_WIDTH - 16, CARD_Y + CARD_HEIGHT - 14, cog_age_message)

    # Bar chart setup
    BAR_X = CARD_X + 16
    BAR_WIDTH = CARD_WIDTH - 32
    BAR_Y = CARD_Y + 14
    BAR_HEIGHT = 14

    lo = max(min(actual_age, cog_age_display) - 8, 18)
    hi = max(actual_age, cog_age_display) + 8

    def age_to_x(age):
        return BAR_X + (age - lo) / (hi - lo) * BAR_WIDTH

    # Track
    c.setFillColor(Color(1, 1, 1, alpha=0.10))
    c.roundRect(BAR_X, BAR_Y, BAR_WIDTH, BAR_HEIGHT, BAR_HEIGHT / 2, fill=1, stroke=0)

    # Actual age bar (neutral, underneath)
    actual_x = age_to_x(actual_age)
    c.setFillColor(Color(1, 1, 1, alpha=0.35))
    c.roundRect(BAR_X, BAR_Y, max(actual_x - BAR_X, BAR_HEIGHT), BAR_HEIGHT, BAR_HEIGHT / 2, fill=1, stroke=0)

    # Cognitive age bar (gradient, on top, colored by comparison)
    cog_x = age_to_x(cog_age_display)
    cog_bar_width = max(cog_x - BAR_X, BAR_HEIGHT)

    if cog_age_display < actual_age:        # younger
        grad_start, grad_end = Color(0.20, 0.55, 0.35, alpha=0.55), Color(0.30, 0.85, 0.45, alpha=0.95)
    elif cog_age_display == actual_age:     # same
        grad_start, grad_end = Color(0.70, 0.55, 0.15, alpha=0.55), Color(0.95, 0.78, 0.20, alpha=0.95)
    else:                                    # older
        grad_start, grad_end = Color(0.65, 0.20, 0.20, alpha=0.55), Color(0.95, 0.40, 0.40, alpha=0.95)

    draw_gradient_hbar(c, BAR_X, BAR_Y, cog_bar_width, BAR_HEIGHT, grad_start, grad_end, radius=BAR_HEIGHT / 2)

    # Tick markers + labels for both ages
    def draw_tick(x, label, color, label_above=True):
        c.setStrokeColor(color)
        c.setLineWidth(1.5)
        c.line(x, BAR_Y - 2, x, BAR_Y + BAR_HEIGHT + 2)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(color)
        label_y = BAR_Y + BAR_HEIGHT + 4 if label_above else BAR_Y - 10
        c.drawCentredString(x, label_y, label)

    draw_tick(actual_x, f"Actual {actual_age}", Color(1, 1, 1, alpha=0.75), label_above=False)
    draw_tick(cog_x, f"Cognitive {cog_age_display}", grad_end, label_above=True)
    # ── BOTTOM CTA BAND ──
    c.setFillColor(Color(0, 0, 0, alpha=0.25))
    c.roundRect(MARGIN, PAGE_HEIGHT - 780, PAGE_WIDTH - MARGIN * 2, 72, 14, fill=1, stroke=0)

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
        c.drawCentredString(bx, PAGE_HEIGHT - 745, num)
        c.setFont(FONT, 8)
        c.setFillColor(Color(1, 1, 1, alpha=0.6))
        c.drawCentredString(bx, PAGE_HEIGHT - 758, lbl)

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

# def draw_executive_summary(c, data):
#     draw_page_header(c, "Executive Summary",
#                      "Complete overview of your cognitive wellness assessment", 2)
#     draw_page_footer(c, data["report_id"])

#     y_start = PAGE_HEIGHT - 90

#     # ── ROW 1: Score card + Risk card + AI Summary ──
#     sc_x, sc_y, sc_w, sc_h = MARGIN, y_start - 130, 135, 125
#     draw_card(c, sc_x, sc_y, sc_w, sc_h, radius=14)
#     draw_text(c, "Wellness Score", sc_x + 12, sc_y + sc_h - 18, 9,
#               FONT, TEXT_SECONDARY)
#     c.setFont(FONT_BOLD, 44)
#     c.setFillColor(score_color(data["overall_score"]))
#     c.drawCentredString(sc_x + sc_w / 2, sc_y + 60, str(data["overall_score"]))
#     c.setFont(FONT, 10)
#     c.setFillColor(TEXT_MUTED)
#     c.drawCentredString(sc_x + sc_w / 2, sc_y + 44, "out of 100")
#     draw_progress_bar(c, sc_x + 12, sc_y + 20, sc_w - 24, 8, data["overall_score"])

#     # Risk classification card
#     rx, ry, rw, rh = sc_x + sc_w + 10, y_start - 130, 130, 125
#     risk_score = data["overall_score"]
#     draw_card(c, rx, ry, rw, rh, radius=14)
#     draw_text(c, "Risk Level", rx + 12, ry + rh - 18, 9, FONT, TEXT_SECONDARY)
#     status = score_status(risk_score)
#     col = score_color(risk_score)
#     c.setFillColor(score_color_light(risk_score))
#     c.roundRect(rx + 12, ry + 50, rw - 24, 42, 10, fill=1, stroke=0)
#     c.setFillColor(col)
#     c.setFont(FONT_BOLD, 13)
#     c.drawCentredString(rx + rw / 2, ry + 75, status)
#     c.setFont(FONT, 9)
#     c.setFillColor(TEXT_SECONDARY)
#     c.drawCentredString(rx + rw / 2, ry + 62, "Classification")
#     levels = ["At Risk", "Needs Attention", "Good", "Excellent"]
#     dot_y = ry + 34
#     for li, lv in enumerate(levels):
#         lx = rx + 12 + li * (rw - 24) / 4
#         col_dot = [DANGER, WARNING, PRIMARY, SUCCESS][li]
#         is_active = lv == status
#         c.setFillColor(col_dot)
#         c.circle(lx + 10, dot_y, 6 if is_active else 4, fill=1, stroke=0)
#         if is_active:
#             c.setStrokeColor(col_dot)
#             c.setLineWidth(1.5)
#             c.circle(lx + 10, dot_y, 9, fill=0, stroke=1)

#     # AI Summary card
#     ai_x = rx + rw + 10
#     ai_y = y_start - 130
#     ai_w = PAGE_WIDTH - MARGIN - ai_x
#     ai_h = 125
#     draw_card(c, ai_x, ai_y, ai_w, ai_h, radius=14)
#     c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.1))
#     c.roundRect(ai_x + 12, ai_y + ai_h - 26, 42, 18, 8, fill=1, stroke=0)
#     c.setFillColor(PRIMARY)
#     c.setFont(FONT_BOLD, 8)
#     c.drawCentredString(ai_x + 33, ai_y + ai_h - 20, "AI ✦")
#     summary_text = data["executive_summary"]["summary"]
#     c.setFont(FONT, 10.5)
#     c.setFillColor(TEXT_SECONDARY)
#     wrap_text_in_box(c, summary_text, ai_x + 12, ai_y + ai_h - 30,
#                      ai_w - 24, 10.5, line_height=15, max_lines=7)

#     # ── SCORE BREAKDOWN TABLE ──
#     bd = data.get("score_breakdown", [])
#     tbl_y     = y_start - 148          # sits just below row 1
#     row_h     = 18
#     tbl_h     = row_h * (len(bd) + 1)+5  # +1 for header
#     tbl_w     = PAGE_WIDTH - MARGIN * 2

#     draw_card(c, MARGIN, tbl_y - tbl_h, tbl_w, tbl_h, radius=10)

#     # Column x positions
#     cx_domain = MARGIN + 14
#     cx_weight = MARGIN + 200
#     cx_score  = MARGIN + 290
#     cx_bar    = MARGIN + 350
#     cx_contrib= MARGIN + tbl_w - 14

#     bar_max_w = cx_contrib - cx_bar - 40

#     # Header row
#     hdr_y = tbl_y - row_h + 4
#     c.setFillColor(PRIMARY)
#     c.roundRect(MARGIN, tbl_y - row_h, tbl_w, row_h, 10, fill=1, stroke=0)
#     c.setFillColor(white)
#     c.setFont(FONT_BOLD, 8)
#     c.drawString(cx_domain,  hdr_y, "DOMAIN")
#     c.drawString(cx_weight,  hdr_y, "WEIGHT")
#     c.drawString(cx_score,   hdr_y, "SCORE")
#     c.drawString(cx_bar,     hdr_y, "PERFORMANCE")
#     c.drawRightString(cx_contrib, hdr_y, "CONTRIBUTION")

#     # Data rows
#     for ri, row in enumerate(bd):
#         ry2    = tbl_y - row_h * (ri + 2)
#         row_bg = SURFACE if ri % 2 == 0 else CARD_BG
#         c.setFillColor(row_bg)
#         c.rect(MARGIN, ry2, tbl_w, row_h, fill=1, stroke=0)

#         # Left color strip
#         c.setFillColor(score_color(row["score"]))
#         c.rect(MARGIN, ry2, 3, row_h, fill=1, stroke=0)

#         text_y = ry2 + 5

#         # Domain name
#         c.setFont(FONT_BOLD, 8)
#         c.setFillColor(TEXT_PRIMARY)
#         c.drawString(cx_domain, text_y, row["domain"])

#         # Weight
#         c.setFont(FONT, 8)
#         c.setFillColor(TEXT_MUTED)
#         c.drawString(cx_weight, text_y, f"{row['weight_pct']}%")

#         # Score
#         c.setFont(FONT_BOLD, 8)
#         c.setFillColor(score_color(row["score"]))
#         c.drawString(cx_score, text_y, str(row["score"]))

#         # Mini progress bar
#         draw_progress_bar(c, cx_bar, ry2 + 5, bar_max_w, 7, row["score"])

#         # Contribution
#         c.setFont(FONT_BOLD, 8)
#         c.setFillColor(TEXT_PRIMARY)
#         c.drawRightString(cx_contrib, text_y, f"{row['contribution']} pts")

#     # Bottom border line on table
#     c.setStrokeColor(BORDER_COLOR)
#     c.setLineWidth(0.5)
#     c.line(MARGIN, tbl_y - tbl_h, MARGIN + tbl_w, tbl_y - tbl_h)

#     # ── KEY FINDINGS ──
#     kf_y = tbl_y - tbl_h - 18          # pushed down below table
#     kf_h = 140
#     draw_card(c, MARGIN, kf_y - kf_h, PAGE_WIDTH - MARGIN * 2, kf_h, radius=14)
#     draw_text(c, "Key Findings", MARGIN + 16, kf_y - 18, 13, FONT_BOLD)
#     draw_divider(c, MARGIN + 16, kf_y - 28, PAGE_WIDTH - MARGIN * 2 - 32)

#     findings = data["executive_summary"]["key_findings"]
#     cols     = 2
#     col_w    = (PAGE_WIDTH - MARGIN * 2 - 32) / cols
#     for fi, finding in enumerate(findings[:4]):
#         fx = MARGIN + 16 + (fi % cols) * col_w
#         fy = kf_y - 52 - (fi // cols) * 40
#         c.setFillColor(PRIMARY)
#         c.circle(fx + 8, fy + 5, 4, fill=1, stroke=0)
#         c.setFillColor(white)
#         c.circle(fx + 8, fy + 5, 2, fill=1, stroke=0)
#         c.setFont(FONT, 10)
#         c.setFillColor(TEXT_PRIMARY)
#         wrap_text_in_box(c, finding, fx + 20, fy + 8,
#                          col_w - 40, 10, line_height=12, max_lines=2)

#     # ── PRIORITY AREAS + STRENGTHS ──
#     pa_y  = kf_y - kf_h - 14
#     pa_h  = 138
#     half_w = (PAGE_WIDTH - MARGIN * 2 - 10) / 2

#     # Priority areas
#     draw_card(c, MARGIN, pa_y - pa_h, half_w, pa_h, radius=14)
#     draw_text(c, "⚠  Priority Areas", MARGIN + 16, pa_y - 18, 12, FONT_BOLD, WARNING)
#     draw_divider(c, MARGIN + 16, pa_y - 28, half_w - 32)
#     for pi, area in enumerate(data["executive_summary"]["priority_areas"][:4]):
#         ay = pa_y - 52 - pi * 22
#         rank_colors = [DANGER, WARNING, WARNING, PRIMARY]
#         c.setFillColor(rank_colors[pi] if pi < len(rank_colors) else TEXT_SECONDARY)
#         c.roundRect(MARGIN + 16, ay - 4, 20, 14, 4, fill=1, stroke=0)
#         c.setFillColor(white)
#         c.setFont(FONT_BOLD, 7)
#         c.drawCentredString(MARGIN + 26, ay + 3, str(pi + 1))
#         c.setFont(FONT, 10)
#         c.setFillColor(TEXT_PRIMARY)
#         c.drawString(MARGIN + 42, ay + 2, area)

#     # Strengths
#     sx = MARGIN + half_w + 10
#     draw_card(c, sx, pa_y - pa_h, half_w, pa_h, radius=14)
#     draw_text(c, "★  Cognitive Strengths", sx + 16, pa_y - 18, 12, FONT_BOLD, SUCCESS)
#     draw_divider(c, sx + 16, pa_y - 28, half_w - 32)
#     for si, strength in enumerate(data["executive_summary"]["strongest_areas"][:4]):
#         sy_item = pa_y - 52 - si * 22
#         c.setFillColor(SUCCESS)
#         c.roundRect(sx + 16, sy_item - 4, 20, 14, 4, fill=1, stroke=0)
#         c.setFillColor(white)
#         c.setFont(FONT_BOLD, 7)
#         c.drawCentredString(sx + 26, sy_item + 3, str(si + 1))
#         c.setFont(FONT, 10)
#         c.setFillColor(TEXT_PRIMARY)
#         c.drawString(sx + 42, sy_item + 2, strength)
def draw_executive_summary(c, data):
    draw_page_header(c, "Executive Summary",
                     "Complete overview of your cognitive wellness assessment", 2)
    draw_page_footer(c, data["report_id"])

    y_start = PAGE_HEIGHT - 90

    # ============================================================
    # TRAFFIC LIGHT SUMMARY
    # ============================================================
    tl      = data.get("traffic_light", {"green": [], "yellow": [], "red": []})
    tl_h    = 62
    tl_y    = y_start
    tl_w    = PAGE_WIDTH - MARGIN * 2
    col3_w  = tl_w / 3

    draw_card(c, MARGIN, tl_y - tl_h, tl_w, tl_h, radius=12)

    # Three columns: red | yellow | green
    columns = [
        ("🔴 High Priority",   tl["red"],    DANGER,   DANGER_LIGHT),
        ("🟡 Needs Attention",  tl["yellow"], WARNING,  WARNING_LIGHT),
        ("🟢 Strengths",        tl["green"],  SUCCESS,  SUCCESS_LIGHT),
    ]

    for ci, (label, items, col, col_light) in enumerate(columns):
        cx3 = MARGIN + ci * col3_w

        # Column left accent strip
        c.setFillColor(col)
        c.roundRect(cx3, tl_y - tl_h, 3, tl_h, 2, fill=1, stroke=0)

        # Label
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(col)
        c.drawString(cx3 + 10, tl_y - 14, label)

        # Domain pills
        pill_x = cx3 + 10
        pill_y = tl_y - 30
        for item in items[:3]:
            pill_w = c.stringWidth(item["domain"], FONT, 7.5) + 14
            if pill_x + pill_w > cx3 + col3_w - 8:
                pill_x  = cx3 + 10
                pill_y -= 18
            c.setFillColor(col_light)
            c.roundRect(pill_x, pill_y, pill_w, 14, 5, fill=1, stroke=0)
            c.setFillColor(col)
            c.setFont(FONT_BOLD, 7.5)
            c.drawString(pill_x + 7, pill_y + 4, item["domain"])
            pill_x += pill_w + 5

        # Vertical divider between columns
        if ci < 2:
            c.setStrokeColor(BORDER_COLOR)
            c.setLineWidth(0.5)
            c.line(cx3 + col3_w, tl_y - tl_h + 8,
                   cx3 + col3_w, tl_y - 8)

    # ============================================================
    # ROW 1: Score card + Risk card + AI Summary
    # ============================================================
    row1_y = tl_y - tl_h 

    sc_x, sc_y, sc_w, sc_h = MARGIN, row1_y - 125, 135, 120
    draw_card(c, sc_x, sc_y, sc_w, sc_h, radius=14)
    draw_text(c, "Wellness Score", sc_x + 12, sc_y + sc_h - 18, 9,
              FONT, TEXT_SECONDARY)
    c.setFont(FONT_BOLD, 42)
    c.setFillColor(score_color(data["overall_score"]))
    c.drawCentredString(sc_x + sc_w / 2, sc_y + 58, str(data["overall_score"]))
    c.setFont(FONT, 10)
    c.setFillColor(TEXT_MUTED)
    c.drawCentredString(sc_x + sc_w / 2, sc_y + 42, "out of 100")
    draw_progress_bar(c, sc_x + 12, sc_y + 18, sc_w - 24, 8, data["overall_score"])

    # Risk classification card
    rx, ry, rw, rh = sc_x + sc_w + 10, row1_y - 125, 130, 120
    draw_card(c, rx, ry, rw, rh, radius=14)
    draw_text(c, "Risk Level", rx + 12, ry + rh - 18, 9, FONT, TEXT_SECONDARY)
    status = score_status(data["overall_score"])
    col    = score_color(data["overall_score"])
    c.setFillColor(score_color_light(data["overall_score"]))
    c.roundRect(rx + 12, ry + 48, rw - 24, 40, 10, fill=1, stroke=0)
    c.setFillColor(col)
    c.setFont(FONT_BOLD, 12)
    c.drawCentredString(rx + rw / 2, ry + 72, status)
    c.setFont(FONT, 9)
    c.setFillColor(TEXT_SECONDARY)
    c.drawCentredString(rx + rw / 2, ry + 60, "Classification")
    levels = ["At Risk", "Needs Attention", "Good", "Excellent"]
    dot_y  = ry + 32
    for li, lv in enumerate(levels):
        lx      = rx + 12 + li * (rw - 24) / 4
        col_dot = [DANGER, WARNING, PRIMARY, SUCCESS][li]
        is_active = lv == status
        c.setFillColor(col_dot)
        c.circle(lx + 10, dot_y, 6 if is_active else 4, fill=1, stroke=0)
        if is_active:
            c.setStrokeColor(col_dot)
            c.setLineWidth(1.5)
            c.circle(lx + 10, dot_y, 9, fill=0, stroke=1)

    # AI Summary card
    ai_x = rx + rw + 10
    ai_y = row1_y - 125
    ai_w = PAGE_WIDTH - MARGIN - ai_x
    ai_h = 120
    draw_card(c, ai_x, ai_y, ai_w, ai_h, radius=14)
    c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.1))
    c.roundRect(ai_x + 12, ai_y + ai_h - 24, 42, 16, 8, fill=1, stroke=0)
    c.setFillColor(PRIMARY)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(ai_x + 33, ai_y + ai_h - 18, "AI ✦")
    c.setFont(FONT, 10)
    c.setFillColor(TEXT_SECONDARY)
    wrap_text_in_box(c, data["executive_summary"]["summary"],
                     ai_x + 12, ai_y + ai_h - 28,
                     ai_w - 24, 10, line_height=14, max_lines=6)

    # ============================================================
    # SCORE BREAKDOWN TABLE
    # ============================================================
    bd    = data.get("score_breakdown", [])
    tbl_y = row1_y - 125 - 12
    row_h = 18
    tbl_h = row_h * (len(bd) + 1) + 5
    tbl_w = PAGE_WIDTH - MARGIN * 2

    draw_card(c, MARGIN, tbl_y - tbl_h, tbl_w, tbl_h, radius=10)

    cx_domain  = MARGIN + 14
    cx_weight  = MARGIN + 200
    cx_score   = MARGIN + 290
    cx_bar     = MARGIN + 350
    cx_contrib = MARGIN + tbl_w - 14
    bar_max_w  = cx_contrib - cx_bar - 40

    # Header
    hdr_y = tbl_y - row_h + 4
    c.setFillColor(PRIMARY)
    c.roundRect(MARGIN, tbl_y - row_h, tbl_w, row_h, 10, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 8)
    c.drawString(cx_domain,  hdr_y, "DOMAIN")
    c.drawString(cx_weight,  hdr_y, "WEIGHT")
    c.drawString(cx_score,   hdr_y, "SCORE")
    c.drawString(cx_bar,     hdr_y, "PERFORMANCE")
    c.drawRightString(cx_contrib, hdr_y, "CONTRIBUTION")

    for ri, row in enumerate(bd):
        ry2    = tbl_y - row_h * (ri + 2)
        c.setFillColor(SURFACE if ri % 2 == 0 else CARD_BG)
        c.rect(MARGIN, ry2, tbl_w, row_h, fill=1, stroke=0)
        c.setFillColor(score_color(row["score"]))
        c.rect(MARGIN, ry2, 3, row_h, fill=1, stroke=0)
        text_y = ry2 + 5
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(cx_domain, text_y, row["domain"])
        c.setFont(FONT, 8)
        c.setFillColor(TEXT_MUTED)
        c.drawString(cx_weight, text_y, f"{row['weight_pct']}%")
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(score_color(row["score"]))
        c.drawString(cx_score, text_y, str(row["score"]))
        draw_progress_bar(c, cx_bar, ry2 + 5, bar_max_w, 7, row["score"])
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(TEXT_PRIMARY)
        c.drawRightString(cx_contrib, text_y, f"{row['contribution']} pts")

    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(0.5)
    c.line(MARGIN, tbl_y - tbl_h, MARGIN + tbl_w, tbl_y - tbl_h)

    # ============================================================
    # BENCHMARK COMPARISON
    # ============================================================
    bm   = data.get("benchmarks", {})
    bm_y = tbl_y - tbl_h - 16
    bm_h = 84
    draw_card(c, MARGIN, bm_y - bm_h, PAGE_WIDTH - MARGIN * 2, bm_h, radius=12)

    draw_text(c, "How You Compare", MARGIN + 16, bm_y - 14, 11, FONT_BOLD)
    c.setFont(FONT, 8)
    c.setFillColor(TEXT_MUTED)
    c.drawString(MARGIN + 16, bm_y - 26,
                 f"vs {bm.get('gender_label','')} {bm.get('band_label','your age group')}")

    pct = bm.get("percentile", 50)
    c.setFillColor(score_color(pct))
    c.roundRect(PAGE_WIDTH - MARGIN - 86, bm_y - 34, 72, 24, 8, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 10)
    c.drawCentredString(PAGE_WIDTH - MARGIN - 50, bm_y - 23, f"Top {100 - pct}%")

    bar_labels = [
        ("You",          bm.get("user_score",   0), score_color(bm.get("user_score", 0))),
        ("Peer Average", bm.get("peer_average", 0), TEXT_MUTED),
        ("Top 10%",      bm.get("top_10_pct",   0), SUCCESS),
    ]
    bm_bar_w = PAGE_WIDTH - MARGIN * 2 - 126
    for bi, (lbl, val, bcol) in enumerate(bar_labels):
        by2 = bm_y - 42 - bi * 13
        c.setFont(FONT, 7.5)
        c.setFillColor(TEXT_SECONDARY)
        c.drawString(MARGIN + 16, by2 + 2, lbl)
        c.setFillColor(BORDER_COLOR)
        c.roundRect(MARGIN + 96, by2, bm_bar_w, 9, 4, fill=1, stroke=0)
        fill_w = max(9, (val / 100) * bm_bar_w)
        c.setFillColor(bcol)
        c.roundRect(MARGIN + 96, by2, fill_w, 9, 4, fill=1, stroke=0)
        c.setFont(FONT_BOLD, 7.5)
        c.setFillColor(bcol)
        c.drawString(MARGIN + 96 + fill_w + 4, by2 + 1, str(val))

    # ============================================================
    # KEY FINDINGS
    # ============================================================
    kf_y = bm_y - bm_h - 12
    kf_h = 118
    draw_card(c, MARGIN, kf_y - kf_h, PAGE_WIDTH - MARGIN * 2, kf_h, radius=14)
    draw_text(c, "Key Findings", MARGIN + 16, kf_y - 16, 12, FONT_BOLD)
    draw_divider(c, MARGIN + 16, kf_y - 26, PAGE_WIDTH - MARGIN * 2 - 32)

    findings = data["executive_summary"]["key_findings"]
    col_w    = (PAGE_WIDTH - MARGIN * 2 - 32) / 2
    for fi, finding in enumerate(findings[:4]):
        fx = MARGIN + 16 + (fi % 2) * col_w
        fy = kf_y - 46 - (fi // 2) * 36
        c.setFillColor(PRIMARY)
        c.circle(fx + 8, fy + 5, 4, fill=1, stroke=0)
        c.setFillColor(white)
        c.circle(fx + 8, fy + 5, 2, fill=1, stroke=0)
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_PRIMARY)
        wrap_text_in_box(c, finding, fx + 20, fy + 8,
                         col_w - 40, 10, line_height=12, max_lines=2)

    # ============================================================
    # PRIORITY AREAS + STRENGTHS
    # ============================================================
    pa_y   = kf_y - kf_h - 10
    pa_h   = 114
    half_w = (PAGE_WIDTH - MARGIN * 2 - 10) / 2

    draw_card(c, MARGIN, pa_y - pa_h, half_w, pa_h, radius=14)
    draw_text(c, "⚠  Priority Areas", MARGIN + 16, pa_y - 16, 11, FONT_BOLD, WARNING)
    draw_divider(c, MARGIN + 16, pa_y - 26, half_w - 32)
    for pi, area in enumerate(data["executive_summary"]["priority_areas"][:4]):
        ay = pa_y - 46 - pi * 20
        rank_colors = [DANGER, WARNING, WARNING, PRIMARY]
        c.setFillColor(rank_colors[pi] if pi < len(rank_colors) else TEXT_SECONDARY)
        c.roundRect(MARGIN + 16, ay - 4, 20, 14, 4, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 7)
        c.drawCentredString(MARGIN + 26, ay + 3, str(pi + 1))
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 42, ay + 2, area)

    sx = MARGIN + half_w + 10
    draw_card(c, sx, pa_y - pa_h, half_w, pa_h, radius=14)
    draw_text(c, "★  Cognitive Strengths", sx + 16, pa_y - 16, 11, FONT_BOLD, SUCCESS)
    draw_divider(c, sx + 16, pa_y - 26, half_w - 32)
    for si, strength in enumerate(data["executive_summary"]["strongest_areas"][:4]):
        sy_item = pa_y - 46 - si * 20
        c.setFillColor(SUCCESS)
        c.roundRect(sx + 16, sy_item - 4, 20, 14, 4, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 7)
        c.drawCentredString(sx + 26, sy_item + 3, str(si + 1))
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(sx + 42, sy_item + 2, strength)
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
    pb_card_h = 248
    pb_y      = 500
    draw_card(c, MARGIN, pb_y - pb_card_h,
              PAGE_WIDTH - MARGIN * 2, pb_card_h, radius=16)

    draw_text(c, "Brain Performance Dashboard",
              MARGIN + 16, pb_y - 20, 14, FONT_BOLD)
    c.setFont(FONT, 9)
    c.setFillColor(TEXT_MUTED)
    c.drawString(MARGIN + 16, pb_y - 33,
                 "Primary visualization — progress bars show each domain score at a glance")
    draw_divider(c, MARGIN + 16, pb_y - 40, PAGE_WIDTH - MARGIN * 2 - 32)

    bar_label_w = 100
    bar_score_w = 32
    bar_pct_w   = 32
    bar_area_w  = PAGE_WIDTH - MARGIN * 2 - bar_label_w - bar_score_w - bar_pct_w - 32
    bar_x_start = MARGIN + 16 + bar_label_w
    row_gap     = 24

    for di, (domain, value) in enumerate(domains.items()):
        dy = pb_y - 58 - di * row_gap

        # Domain label
        c.setFont(FONT_BOLD, 9)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 16, dy + 3, domain)

        # Score number
        c.setFont(FONT_BOLD, 9)
        c.setFillColor(score_color(value))
        c.drawString(bar_x_start + bar_area_w + 6, dy + 3, str(value))

        # Status label
        c.setFont(FONT, 7.5)
        c.setFillColor(TEXT_MUTED)
        c.drawString(bar_x_start + bar_area_w + 32, dy + 3, score_status(value))

        # Progress bar track
        c.setFillColor(BORDER_COLOR)
        c.roundRect(bar_x_start, dy, bar_area_w, 12, 6, fill=1, stroke=0)

        # Fill
        fill_w = max(12, (value / 100) * bar_area_w)
        c.setFillColor(score_color(value))
        c.roundRect(bar_x_start, dy, fill_w, 12, 6, fill=1, stroke=0)

        # Score pip markers at 25/50/75/100
        for pip in [25, 50, 70, 85]:
            pip_x = bar_x_start + (pip / 100) * bar_area_w
            c.setFillColor(BACKGROUND)
            c.rect(pip_x - 0.5, dy, 1, 12, fill=1, stroke=0)



# ============================================================
# PAGE 4 — LIFESTYLE IMPACT ANALYSIS
# ============================================================

# def draw_lifestyle_page(c, data):
#     draw_page_header(c, "Lifestyle Impact Analysis",
#                      "How your daily habits are affecting cognitive performance", 4)
#     draw_page_footer(c, data["report_id"])

#     lifestyle = data["lifestyle"]
#     content_top = PAGE_HEIGHT - 88

#     lifestyle_meta = {
#         "Sleep": {
#             "icon": "☽",
#             "desc": "Sleep quality directly impacts memory consolidation, "
#                     "emotional regulation, and cognitive recovery.",
#             "tip": "Aim for 7–9 hours of consistent, quality sleep.",
#         },
#         "Stress": {
#             "icon": "⚡",
#             "desc": "Chronic stress elevates cortisol, impairing "
#                     "working memory and executive function over time.",
#             "tip": "Daily mindfulness or breathing exercises can reduce stress load.",
#         },
#         "Anxiety": {
#             "icon": "◎",
#             "desc": "Anxiety diverts attentional resources and can "
#                     "create cognitive bottlenecks during complex tasks.",
#             "tip": "Structured worry time and CBT techniques show strong outcomes.",
#         },
#         "Burnout": {
#             "icon": "▽",
#             "desc": "Burnout depletes mental reserves and reduces "
#                     "motivation, creativity, and sustained performance.",
#             "tip": "Recovery blocks and workload distribution are essential.",
#         },
#     }

#     card_w = (PAGE_WIDTH - MARGIN * 2 - 12) / 2
#     card_h = 148
#     positions = [
#         (MARGIN,              content_top - card_h),
#         (MARGIN + card_w + 12, content_top - card_h),
#         (MARGIN,              content_top - card_h * 2 - 20),
#         (MARGIN + card_w + 12, content_top - card_h * 2 - 20),
#     ]

#     for i, (key, val) in enumerate(lifestyle.items()):
#         meta = lifestyle_meta.get(key, {})
#         lx, ly = positions[i]
#         draw_card(c, lx, ly, card_w, card_h, radius=14)

#         # Top accent
#         c.setFillColor(score_color(val))
#         c.roundRect(lx, ly + card_h - 4, card_w, 4, 2, fill=1, stroke=0)

#         # Icon + Title row
#         c.setFont(FONT_BOLD, 16)
#         c.setFillColor(TEXT_PRIMARY)
#         c.drawString(lx + 14, ly + card_h - 28, f"{meta.get('icon', '●')}  {key}")

#         # Score
#         c.setFont(FONT_BOLD, 34)
#         c.setFillColor(score_color(val))
#         c.drawString(lx + 14, ly + card_h - 66, str(val))
#         c.setFont(FONT, 11)
#         c.setFillColor(TEXT_MUTED)
#         c.drawString(lx + 14 + c.stringWidth(str(val), FONT_BOLD, 34) + 4,
#                      ly + card_h - 60, "/ 100")

#         # Status tag
#         draw_tag(c, lx + 14, ly + card_h - 88, score_status(val),
#                  score_color(val), height=16, radius=6)

#         # Progress bar
#         draw_progress_bar(c, lx + 14, ly + card_h - 106, card_w - 28, 8, val)

#         # Description
#         c.setFont(FONT, 8.5)
#         c.setFillColor(TEXT_SECONDARY)
#         wrap_text_in_box(c, meta.get("desc", ""), lx + 14, ly + card_h - 112,
#                          card_w - 28, 8.5, line_height=12, max_lines=2)

#         # Tip
#         c.setFillColor(score_color_light(val))
#         c.roundRect(lx + 10, ly + 10, card_w - 20, 34, 6, fill=1, stroke=0)
#         c.setFont(FONT, 8)
#         c.setFillColor(score_color(val))
#         tip = meta.get("tip", "")
#         wrap_text_in_box(
#     c,
#     f"Tip: {tip}",
#     lx + 18,
#     ly + 24,
#     card_w - 36,
#     8,
#     line_height=10,
#     max_lines=2
# )

#     # ── COMPARISON CHART ──
#     chart_y = content_top - card_h * 2 - 54
#     chart_h = 140
#     draw_card(c, MARGIN, chart_y - chart_h, PAGE_WIDTH - MARGIN * 2, chart_h, radius=14)
#     draw_text(c, "Lifestyle Factor Comparison", MARGIN + 16, chart_y - 22, 13, FONT_BOLD)
#     draw_divider(c, MARGIN + 16, chart_y - 32, PAGE_WIDTH - MARGIN * 2 - 32)

#     bar_area_w = PAGE_WIDTH - MARGIN * 2 - 32
#     bar_h = 16
#     keys = list(lifestyle.keys())
#     for bi, key in enumerate(keys):
#         val = lifestyle[key]
#         by = chart_y - 52 - bi * 24
#         c.setFont(FONT, 10)
#         c.setFillColor(TEXT_SECONDARY)
#         c.drawString(MARGIN + 16, by + 2, key)
#         draw_progress_bar(c, MARGIN + 100, by, bar_area_w - 145, bar_h, val)
#         c.setFont(FONT_BOLD, 10)
#         c.setFillColor(score_color(val))
#         c.drawString(MARGIN + bar_area_w - 40, by + 2, f"{val}/100")
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
    card_h = 138
    positions = [
        (MARGIN,               content_top - card_h),
        (MARGIN + card_w + 12, content_top - card_h),
        (MARGIN,               content_top - card_h * 2 - 14),
        (MARGIN + card_w + 12, content_top - card_h * 2 - 14),
    ]

    for i, (key, val) in enumerate(lifestyle.items()):
        meta = lifestyle_meta.get(key, {})
        lx, ly = positions[i]
        draw_card(c, lx, ly, card_w, card_h, radius=14)

        # Top accent
        c.setFillColor(score_color(val))
        c.roundRect(lx, ly + card_h - 4, card_w, 4, 2, fill=1, stroke=0)

        # Icon + Title
        c.setFont(FONT_BOLD, 15)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(lx + 14, ly + card_h - 26, f"{meta.get('icon', '●')}  {key}")

        # Score
        c.setFont(FONT_BOLD, 30)
        c.setFillColor(score_color(val))
        c.drawString(lx + 14, ly + card_h - 58, str(val))
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_MUTED)
        c.drawString(lx + 14 + c.stringWidth(str(val), FONT_BOLD, 30) + 4,
                     ly + card_h - 52, "/ 100")

        # Status tag
        draw_tag(c, lx + 14, ly + card_h - 76,
                 score_status(val), score_color(val), height=14, radius=5)

        # Progress bar
        draw_progress_bar(c, lx + 14, ly + card_h - 90, card_w - 28, 7, val)

        # Description
        wrap_text_in_box(c, meta.get("desc", ""), lx + 14, ly + card_h - 100,
                         card_w - 28, 8, line_height=11, max_lines=2,
                         font=FONT, color=TEXT_SECONDARY)

        # Tip
        c.setFillColor(score_color_light(val))
        c.roundRect(lx + 10, ly + 8, card_w - 20, 24, 5, fill=1, stroke=0)
        c.setFont(FONT, 7.5)
        c.setFillColor(score_color(val))
        wrap_text_in_box(c, f"Tip: {meta.get('tip', '')}",
                         lx + 18, ly + 22, card_w - 36,
                         7.5, line_height=10, max_lines=2)

    # ── ROOT CAUSE ANALYSIS ──
    root_causes = data.get("root_causes", [])
    rc_top = content_top - card_h * 2 - 28
    rc_h   = 44 + len(root_causes) * 44 + 16
    draw_card(c, MARGIN, rc_top - rc_h, PAGE_WIDTH - MARGIN * 2, rc_h, radius=14)

    # Section header
    c.setFillColor(DANGER)
    c.roundRect(MARGIN, rc_top - rc_h, PAGE_WIDTH - MARGIN * 2, rc_h, 14, fill=0, stroke=1)
    c.setLineWidth(0)
    draw_text(c, "Primary Contributors to Score", MARGIN + 16, rc_top - 20, 13, FONT_BOLD)
    c.setFont(FONT, 9)
    c.setFillColor(TEXT_MUTED)
    c.drawString(MARGIN + 16, rc_top - 32,
                 "Factors most significantly affecting your cognitive performance")
    draw_divider(c, MARGIN + 16, rc_top - 38, PAGE_WIDTH - MARGIN * 2 - 32)

    bar_full_w = PAGE_WIDTH - MARGIN * 2 - 200
    
    for ri, cause in enumerate(root_causes):
        ry = rc_top - 85 - ri * 44  # increased from 36 to 44 — more breathing room

        # Rank dot — left edge
        dot_col = [DANGER, WARNING, WARNING, PRIMARY][ri] if ri < 4 else TEXT_MUTED
        c.setFillColor(dot_col)
        c.circle(MARGIN + 10, ry + 18, 5, fill=1, stroke=0)

        # Impact badge
        c.setFillColor(DANGER_LIGHT)
        c.roundRect(MARGIN + 22, ry + 8, 42, 20, 6, fill=1, stroke=0)
        c.setFillColor(DANGER)
        c.setFont(FONT_BOLD, 9)
        c.drawCentredString(MARGIN + 43, ry + 16, f"{cause['impact_pct']}%")

        # Factor name
        c.setFont(FONT_BOLD, 10)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 72, ry + 28, cause["factor"])

        # Description — full width, no truncation
        c.setFont(FONT, 8)
        c.setFillColor(TEXT_SECONDARY)
        wrap_text_in_box(
            c,
            cause["description"],
            MARGIN + 72,
            ry + 17,
            PAGE_WIDTH - MARGIN * 2 - 200,  # leave space for bar on right
            8,
            line_height=10,
            max_lines=2,
        )

        # Impact bar — right side, does NOT overlap text
        bar_x     = PAGE_WIDTH - MARGIN - 140
        bar_w     = 120
        bar_val   = cause["impact_pct"] * 2  # scale 0–50 → 0–100 visually
        bar_col   = [DANGER, WARNING, WARNING, PRIMARY][ri] if ri < 4 else TEXT_MUTED

        # Track
        c.setFillColor(DANGER_LIGHT)
        c.roundRect(bar_x, ry + 12, bar_w, 10, 5, fill=1, stroke=0)

        # Fill — color matches rank
        fill_w = max(10, (bar_val / 100) * bar_w)
        c.setFillColor(bar_col)
        c.roundRect(bar_x, ry + 12, fill_w, 10, 5, fill=1, stroke=0)

        # Value label right of bar
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(bar_col)
        c.drawString(bar_x + bar_w + 4, ry + 14, f"{cause['impact_pct']}%")

# ============================================================
# PAGE 5 — AI COGNITIVE INSIGHTS
# ============================================================
# def draw_ai_insights_page(c, data):

#     draw_page_header(
#         c,
#         "AI Cognitive Insights",
#         "Personalized analysis powered by Limitless AI",
#         5
#     )

#     draw_page_footer(c, data["report_id"])

#     ai = data["ai_insights"]

#     content_top = PAGE_HEIGHT - 88

#     # ============================================================
#     # MAIN ANALYSIS CARD
#     # ============================================================

#     main_h = 118

#     draw_card(
#         c,
#         MARGIN,
#         content_top - main_h,
#         PAGE_WIDTH - MARGIN * 2,
#         main_h,
#         radius=16
#     )

#     # AI Badge
#     c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.08))

#     c.roundRect(
#         MARGIN + 16,
#         content_top - 24,
#         54,
#         16,
#         7,
#         fill=1,
#         stroke=0
#     )

#     c.setFillColor(PRIMARY)
#     c.setFont(FONT_BOLD, 7.5)

#     c.drawCentredString(
#         MARGIN + 43,
#         content_top - 18,
#         "AI ANALYSIS"
#     )

#     # Title
#     draw_text(
#         c,
#         "Cognitive Performance Summary",
#         MARGIN + 16,
#         content_top - 46,
#         14,
#         FONT_BOLD
#     )

#     # Summary text
#     wrap_text_in_box(
#         c,
#         ai["analysis"],
#         MARGIN + 16,
#         content_top - 60,
#         PAGE_WIDTH - MARGIN * 2 - 32,
#         10,
#         line_height=15,
#         max_lines=4,
#         font=FONT,
#         color=TEXT_SECONDARY
#     )

#     # ============================================================
#     # INSIGHTS + CAUSES SECTION
#     # ============================================================

#     section_y = content_top - 138

#     half_w = (PAGE_WIDTH - MARGIN * 2 - 12) / 2

#     card_h = 132

#     # ============================================================
#     # BEHAVIORAL INSIGHTS
#     # ============================================================

#     draw_card(
#         c,
#         MARGIN,
#         section_y - card_h,
#         half_w,
#         card_h,
#         radius=14
#     )

#     draw_text(
#         c,
#         "Behavioral Insights",
#         MARGIN + 16,
#         section_y - 18,
#         12,
#         FONT_BOLD,
#         PRIMARY
#     )

#     draw_divider(
#         c,
#         MARGIN + 16,
#         section_y - 28,
#         half_w - 32
#     )

#     for bii, insight in enumerate(ai["behavioral_insights"][:4]):

#         iy = section_y - 52 - bii * 24

#         # Bullet
#         bullet_y = iy + 6

#         c.setFillColor(PRIMARY)

#         c.roundRect(
#             MARGIN + 16,
#             bullet_y,
#             5,
#             10,
#             2,
#             fill=1,
#             stroke=0
#         )

#         # Text
#         wrap_text_in_box(
#             c,
#             insight,
#             MARGIN + 30,
#             iy + 12,
#             half_w - 46,
#             8.5,
#             line_height=10,
#             max_lines=2,
#             font=FONT,
#             color=TEXT_SECONDARY
#         )

#     # ============================================================
#     # POTENTIAL CAUSES
#     # ============================================================

#     cx = MARGIN + half_w + 12

#     draw_card(
#         c,
#         cx,
#         section_y - card_h,
#         half_w,
#         card_h,
#         radius=14
#     )

#     draw_text(
#         c,
#         "Potential Causes",
#         cx + 16,
#         section_y - 18,
#         12,
#         FONT_BOLD,
#         WARNING
#     )

#     draw_divider(
#         c,
#         cx + 16,
#         section_y - 28,
#         half_w - 32
#     )

#     for cai, cause in enumerate(ai["potential_causes"][:4]):

#         cy = section_y - 52 - cai * 24

#         # Bullet
#         bullet_y = cy + 6

#         c.setFillColor(WARNING)

#         c.roundRect(
#             cx + 16,
#             bullet_y,
#             5,
#             10,
#             2,
#             fill=1,
#             stroke=0
#         )

#         # Text
#         wrap_text_in_box(
#             c,
#             cause,
#             cx + 30,
#             cy + 12,
#             half_w - 46,
#             8.5,
#             line_height=10,
#             max_lines=2,
#             font=FONT,
#             color=TEXT_SECONDARY
#         )

#     # ============================================================
#     # PROJECTION SECTION
#     # ============================================================

#     proj = ai["improvement_projection"]

#     proj_y = section_y - 182

#     draw_text(
#         c,
#         "Projected Improvement (30 Days)",
#         MARGIN,
#         proj_y + 12,
#         12,
#         FONT_BOLD
#     )

#     proj_card_h = 130

#     gap = 10

#     proj_w = (
#         PAGE_WIDTH - MARGIN * 2 - gap * 2
#     ) / 3

#     for pi, (domain, vals) in enumerate(proj.items()):

#         px = MARGIN + pi * (proj_w + gap)

#         draw_card(
#             c,
#             px,
#             proj_y - proj_card_h,
#             proj_w,
#             proj_card_h,
#             radius=14
#         )

#         # ============================================================
#         # DOMAIN TITLE
#         # ============================================================

#         c.setFont(FONT_BOLD, 11)
#         c.setFillColor(TEXT_PRIMARY)

#         c.drawCentredString(
#             px + proj_w / 2,
#             proj_y - 20,
#             domain
#         )

#         cur = vals["current"]
#         prj = vals["projected"]
#         gain = prj - cur

#         # ============================================================
#         # SCORES
#         # ============================================================

#         score_y = proj_y - 48

#         c.setFont(FONT_BOLD, 18)
#         c.setFillColor(DANGER)

#         c.drawCentredString(
#             px + proj_w / 2 - 28,
#             score_y,
#             str(cur)
#         )

#         c.setFont(FONT_BOLD, 16)
#         c.setFillColor(TEXT_MUTED)

#         c.drawCentredString(
#             px + proj_w / 2,
#             score_y + 1,
#             "→"
#         )

#         c.setFont(FONT_BOLD, 18)
#         c.setFillColor(SUCCESS)

#         c.drawCentredString(
#             px + proj_w / 2 + 28,
#             score_y,
#             str(prj)
#         )

#         # ============================================================
#         # GAIN BADGE
#         # ============================================================

#         c.setFillColor(SUCCESS_LIGHT)

#         c.roundRect(
#             px + proj_w / 2 - 22,
#             proj_y - 74,
#             44,
#             16,
#             7,
#             fill=1,
#             stroke=0
#         )

#         c.setFillColor(SUCCESS)
#         c.setFont(FONT_BOLD, 8)

#         c.drawCentredString(
#             px + proj_w / 2,
#             proj_y - 68,
#             f"+{gain} pts"
#         )

#         # ============================================================
#         # BARS
#         # ============================================================

#         draw_text(
#             c,
#             "Current",
#             px + 10,
#             proj_y - 88,
#             7,
#             FONT,
#             TEXT_MUTED
#         )

#         draw_progress_bar(
#             c,
#             px + 10,
#             proj_y - 96,
#             proj_w - 20,
#             5,
#             cur
#         )

#         draw_text(
#             c,
#             "Projected",
#             px + 10,
#             proj_y - 108,
#             7,
#             FONT,
#             TEXT_MUTED
#         )

#         draw_progress_bar(
#             c,
#             px + 10,
#             proj_y - 116,
#             proj_w - 20,
#             5,
#             prj
#         )
def draw_ai_insights_page(c, data):
    draw_page_header(
        c,
        "AI Cognitive Insights",
        "Personalized analysis powered by Limitless AI",
        5
    )
    draw_page_footer(c, data["report_id"])

    ai           = data["ai_insights"]
    risk_pred    = data.get("risk_prediction", {})
    no_action    = risk_pred.get("no_action", {})
    with_action  = risk_pred.get("with_action", {})
    content_top  = PAGE_HEIGHT - 88

    # ============================================================
    # MAIN ANALYSIS CARD
    # ============================================================
    main_h = 100
    draw_card(c, MARGIN, content_top - main_h,
              PAGE_WIDTH - MARGIN * 2, main_h, radius=16)

    c.setFillColor(Color(37/255, 99/255, 235/255, alpha=0.08))
    c.roundRect(MARGIN + 16, content_top - 22, 54, 14, 7, fill=1, stroke=0)
    c.setFillColor(PRIMARY)
    c.setFont(FONT_BOLD, 7.5)
    c.drawCentredString(MARGIN + 43, content_top - 17, "AI ANALYSIS")

    draw_text(c, "Cognitive Performance Summary",
              MARGIN + 16, content_top - 40, 13, FONT_BOLD)

    wrap_text_in_box(
        c, ai["analysis"],
        MARGIN + 16, content_top - 54,
        PAGE_WIDTH - MARGIN * 2 - 32,
        9.5, line_height=14, max_lines=3,
        font=FONT, color=TEXT_SECONDARY,
    )

    # ============================================================
    # BEHAVIORAL INSIGHTS + POTENTIAL CAUSES
    # ============================================================
    section_y = content_top - main_h - 12
    half_w    = (PAGE_WIDTH - MARGIN * 2 - 12) / 2
    card_h    = 120

    # Behavioral insights
    draw_card(c, MARGIN, section_y - card_h, half_w, card_h, radius=14)
    draw_text(c, "Behavioral Insights",
              MARGIN + 16, section_y - 16, 11, FONT_BOLD, PRIMARY)
    draw_divider(c, MARGIN + 16, section_y - 26, half_w - 32)

    for bii, insight in enumerate(ai["behavioral_insights"][:4]):
        iy = section_y - 46 - bii * 20
        c.setFillColor(PRIMARY)
        c.roundRect(MARGIN + 16, iy + 4, 4, 9, 2, fill=1, stroke=0)
        wrap_text_in_box(
            c, insight,
            MARGIN + 28, iy + 12,
            half_w - 44, 8,
            line_height=10, max_lines=2,
            font=FONT, color=TEXT_SECONDARY,
        )

    # Potential causes
    cx2 = MARGIN + half_w + 12
    draw_card(c, cx2, section_y - card_h, half_w, card_h, radius=14)
    draw_text(c, "Potential Causes",
              cx2 + 16, section_y - 16, 11, FONT_BOLD, WARNING)
    draw_divider(c, cx2 + 16, section_y - 26, half_w - 32)

    for cai, cause in enumerate(ai["potential_causes"][:4]):
        cy3 = section_y - 46 - cai * 20
        c.setFillColor(WARNING)
        c.roundRect(cx2 + 16, cy3 + 4, 4, 9, 2, fill=1, stroke=0)
        wrap_text_in_box(
            c, cause,
            cx2 + 28, cy3 + 12,
            half_w - 44, 8,
            line_height=10, max_lines=2,
            font=FONT, color=TEXT_SECONDARY,
        )

    # ============================================================
    # PROJECTED IMPROVEMENT (30 Days)
    # ============================================================
    proj      = ai["improvement_projection"]
    proj_y    = section_y - card_h - 25
    proj_card_h = 110
    proj_w    = (PAGE_WIDTH - MARGIN * 2 - 20) / 3

    draw_text(c, "Projected Improvement (30 Days)",
              MARGIN, proj_y + 10, 11, FONT_BOLD)

    for pi, (domain, vals) in enumerate(proj.items()):
        px  = MARGIN + pi * (proj_w + 10)
        cur = vals["current"]
        prj = vals["projected"]
        gain = prj - cur

        draw_card(c, px, proj_y - proj_card_h, proj_w, proj_card_h, radius=12)

        c.setFont(FONT_BOLD, 10)
        c.setFillColor(TEXT_PRIMARY)
        c.drawCentredString(px + proj_w / 2, proj_y - 18, domain)

        # Current → Projected scores
        c.setFont(FONT_BOLD, 16)
        c.setFillColor(DANGER)
        c.drawCentredString(px + proj_w / 2 - 24, proj_y - 42, str(cur))
        c.setFont(FONT_BOLD, 14)
        c.setFillColor(TEXT_MUTED)
        c.drawCentredString(px + proj_w / 2, proj_y - 41, "→")
        c.setFont(FONT_BOLD, 16)
        c.setFillColor(SUCCESS)
        c.drawCentredString(px + proj_w / 2 + 24, proj_y - 42, str(prj))

        # Gain badge
        c.setFillColor(SUCCESS_LIGHT)
        c.roundRect(px + proj_w / 2 - 20, proj_y - 62, 40, 14, 6, fill=1, stroke=0)
        c.setFillColor(SUCCESS)
        c.setFont(FONT_BOLD, 7.5)
        c.drawCentredString(px + proj_w / 2, proj_y - 54, f"+{gain} pts")

        # Bars
        draw_text(c, "Now",  px + 8, proj_y - 76, 7, FONT, TEXT_MUTED)
        draw_progress_bar(c, px + 8, proj_y - 84, proj_w - 16, 5, cur)
        draw_text(c, "30d",  px + 8, proj_y - 96, 7, FONT, TEXT_MUTED)
        draw_progress_bar(c, px + 8, proj_y - 104, proj_w - 16, 5, prj)

    # ============================================================
    # RISK PREDICTION — TWO CARDS SIDE BY SIDE
    # ============================================================
    rp_y    = proj_y - proj_card_h -28
    rp_h    = 175
    rp_half = (PAGE_WIDTH - MARGIN * 2 - 12) / 2

    draw_text(c, "Future Outlook", MARGIN, rp_y + 10, 11, FONT_BOLD)

    # ── LEFT CARD — Without Action ──
    draw_card(c, MARGIN, rp_y - rp_h, rp_half, rp_h, radius=14)

    # Red header band
    c.setFillColor(DANGER)
    c.roundRect(MARGIN, rp_y - 22, rp_half, 22, 14, fill=1, stroke=0)
    c.roundRect(MARGIN, rp_y - 22, rp_half, 11, 0, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 9)
    c.drawCentredString(MARGIN + rp_half / 2, rp_y - 14, "⚠  WITHOUT ACTION")

    # Overall score projections
    oa_y = rp_y - 40
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(MARGIN + 12, oa_y, "Overall Score Projection")
    # 30 day
    c.setFillColor(DANGER_LIGHT)
    c.roundRect(MARGIN + 12, oa_y - 22, rp_half - 24, 18, 5, fill=1, stroke=0)
    c.setFont(FONT, 8)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(MARGIN + 18, oa_y - 13, "30 days:")
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(DANGER)
    no_30 = no_action.get("overall_30_days", 0)
    overall_now = data["overall_score"]
    drop_30 = round(overall_now - no_30, 1)
    c.drawString(MARGIN + 60, oa_y - 13,
                 f"{no_30}  (−{drop_30} pts / −{round(drop_30/max(overall_now,1)*100,1)}%)")
    # 90 day
    c.setFillColor(DANGER_LIGHT)
    c.roundRect(MARGIN + 12, oa_y - 44, rp_half - 24, 18, 5, fill=1, stroke=0)
    c.setFont(FONT, 8)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(MARGIN + 18, oa_y - 35, "90 days:")
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(DANGER)
    no_90  = no_action.get("overall_90_days", 0)
    drop_90 = round(overall_now - no_90, 1)
    c.drawString(MARGIN + 60, oa_y - 35,
                 f"{no_90}  (−{drop_90} pts / −{round(drop_90/max(overall_now,1)*100,1)}%)")

    # Domain declines
    declines = no_action.get("domain_declines", [])
    dl_y = oa_y - 58
    c.setFont(FONT_BOLD, 8)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(MARGIN + 12, dl_y, "Domain Risk")

    for di, dec in enumerate(declines[:3]):
        dy = dl_y - 18 - di * 24
        cur_v  = dec["current"]
        proj_v = dec["projected"]
        pct_v  = dec["decline_pct"]
        pts_v  = cur_v - proj_v

        # Domain label
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(MARGIN + 12, dy + 8, dec["domain"])

        # Points drop — bold red
        c.setFont(FONT_BOLD, 9)
        c.setFillColor(DANGER)
        c.drawString(MARGIN + 80, dy + 8, f"{cur_v} → {proj_v}")

        # Percentage in smaller text below
        c.setFont(FONT, 7.5)
        c.setFillColor(TEXT_MUTED)
        c.drawString(MARGIN + 80, dy - 1, f"−{pts_v} pts  /  −{pct_v}%")

        # Mini decline bar
        bar_x3  = MARGIN + rp_half - 70
        bar_w3  = 54
        c.setFillColor(DANGER_LIGHT)
        c.roundRect(bar_x3, dy + 2, bar_w3, 8, 4, fill=1, stroke=0)
        decline_fill = max(4, int((pct_v / 20) * bar_w3))
        c.setFillColor(DANGER)
        c.roundRect(bar_x3, dy + 2, decline_fill, 8, 4, fill=1, stroke=0)

    # Burnout statement
    bs_y = dl_y - 18 - len(declines) * 24 - 6
    c.setFillColor(WARNING_LIGHT)
    c.roundRect(MARGIN + 12, bs_y - 14, rp_half - 24, 18, 5, fill=1, stroke=0)
    c.setFont(FONT, 7.5)
    c.setFillColor(WARNING)
    wrap_text_in_box(
        c,
        no_action.get("burnout_statement", ""),
        MARGIN + 16, bs_y - 3,
        rp_half - 32, 7.5,
        line_height=10, max_lines=2,
    )

    # ── RIGHT CARD — With Recommendations ──
    rx2 = MARGIN + rp_half + 12
    draw_card(c, rx2, rp_y - rp_h, rp_half, rp_h, radius=14)

    # Green header band
    c.setFillColor(SUCCESS)
    c.roundRect(rx2, rp_y - 22, rp_half, 22, 14, fill=1, stroke=0)
    c.roundRect(rx2, rp_y - 22, rp_half, 11, 0, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONT_BOLD, 9)
    c.drawCentredString(rx2 + rp_half / 2, rp_y - 14,
                        "✓  WITH RECOMMENDATIONS")

    # Overall score projections
    wa_y = rp_y - 40
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(rx2 + 12, wa_y, "Expected Score")

    # 30 day
    c.setFillColor(SUCCESS_LIGHT)
    c.roundRect(rx2 + 12, wa_y - 22, rp_half - 24, 18, 5, fill=1, stroke=0)
    c.setFont(FONT, 8)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(rx2 + 18, wa_y - 13, "30 days:")
    wa_30   = with_action.get("overall_30_days", 0)
    gain_30 = round(wa_30 - overall_now, 1)
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(SUCCESS)
    c.drawString(rx2 + 60, wa_y - 13,
                 f"{wa_30}  (+{gain_30} pts / +{round(gain_30/max(overall_now,1)*100,1)}%)")

    # 90 day
    c.setFillColor(SUCCESS_LIGHT)
    c.roundRect(rx2 + 12, wa_y - 44, rp_half - 24, 18, 5, fill=1, stroke=0)
    c.setFont(FONT, 8)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(rx2 + 18, wa_y - 35, "90 days:")
    wa_90   = with_action.get("overall_90_days", 0)
    gain_90 = round(wa_90 - overall_now, 1)
    c.setFont(FONT_BOLD, 9)
    c.setFillColor(SUCCESS)
    c.drawString(rx2 + 60, wa_y - 35,
                 f"{wa_90}  (+{gain_90} pts / +{round(gain_90/max(overall_now,1)*100,1)}%)")

    # Domain gains
    gains  = with_action.get("domain_gains", [])
    ga_y   = wa_y - 58
    c.setFont(FONT_BOLD, 8)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(rx2 + 12, ga_y, "Highest Improvement Potential")

    for gi, gain_item in enumerate(gains[:3]):
        gy      = ga_y - 18 - gi * 24
        cur_v   = gain_item["current"]
        p30     = gain_item["projected_30"]
        p90     = gain_item["projected_90"]
        gain_pt = gain_item["gain_pts"]
        gain_pc = gain_item["gain_pct"]

        # Domain label
        c.setFont(FONT_BOLD, 8)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(rx2 + 12, gy + 8, gain_item["domain"])

        # Points gain — bold green
        c.setFont(FONT_BOLD, 9)
        c.setFillColor(SUCCESS)
        c.drawString(rx2 + 80, gy + 8, f"{cur_v} → {p90}")

        # Percentage in smaller text below
        c.setFont(FONT, 7.5)
        c.setFillColor(TEXT_MUTED)
        c.drawString(rx2 + 80, gy - 1, f"+{gain_pt} pts  /  +{gain_pc}%")

        # Mini gain bar
        bar_x4  = rx2 + rp_half - 70
        bar_w4  = 54
        c.setFillColor(SUCCESS_LIGHT)
        c.roundRect(bar_x4, gy + 2, bar_w4, 8, 4, fill=1, stroke=0)
        gain_fill = max(4, int((min(gain_pc, 50) / 50) * bar_w4))
        c.setFillColor(SUCCESS)
        c.roundRect(bar_x4, gy + 2, gain_fill, 8, 4, fill=1, stroke=0)

    # Motivational footer inside card
    mf_y = ga_y - 18 - len(gains) * 24 - 6
    c.setFillColor(SUCCESS_LIGHT)
    c.roundRect(rx2 + 12, mf_y - 14, rp_half - 24, 18, 5, fill=1, stroke=0)
    c.setFont(FONT_BOLD, 7.5)
    c.setFillColor(SUCCESS)
    c.drawCentredString(rx2 + rp_half / 2,
                        mf_y - 6,
                        "Consistent habits compound — results grow over time.")

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

# def draw_strengths_page(c, data):
#     draw_page_header(c, "Cognitive Strengths",
#                      "Your standout capabilities and performance advantages", 7)
#     draw_page_footer(c, data["report_id"])

#     strengths = data["strengths"]
#     content_top = PAGE_HEIGHT - 88
#     card_h = 105
#     gap = 14

#     # Intro card
#     draw_card(c, MARGIN, content_top - 60, PAGE_WIDTH - MARGIN * 2, 52, radius=14,
#               bg=HexColor("#F0FDF4"))
#     c.setFillColor(SUCCESS)
#     c.setFont(FONT_BOLD, 11)
#     c.drawString(MARGIN + 16, content_top - 28,
#                  "★  Your cognitive profile shows meaningful strengths worth celebrating and building upon.")
#     c.setFont(FONT, 10)
#     c.setFillColor(TEXT_SECONDARY)
#     c.drawString(MARGIN + 16, content_top - 44,
#                  "These areas demonstrate resilience and can serve as anchors for overall improvement.")

#     strength_descs = {
#         "Reaction Time":       "Fast processing and quick response speed remain a significant strength.",
#         "Language Processing": "Strong comprehension and verbal reasoning abilities detected.",
#         "Problem Solving":     "Logical thinking and analytical problem solving remain above average.",
#     }

#     for si, strength in enumerate(strengths):
#         sy = content_top - 82 - si * (card_h + gap)
#         draw_card(c, MARGIN, sy - card_h, PAGE_WIDTH - MARGIN * 2, card_h, radius=14)

#         # Rank badge
#         rank_colors = [SUCCESS, PRIMARY, PRIMARY_LIGHT]
#         rc = rank_colors[si] if si < len(rank_colors) else TEXT_MUTED
#         c.setFillColor(rc)
#         c.circle(MARGIN + 28, sy - card_h / 2, 18, fill=1, stroke=0)
#         c.setFillColor(white)
#         c.setFont(FONT_BOLD, 14)
#         c.drawCentredString(MARGIN + 28, sy - card_h / 2 - 5, str(si + 1))

#         # Title
#         c.setFont(FONT_BOLD, 16)
#         c.setFillColor(TEXT_PRIMARY)
#         c.drawString(MARGIN + 56, sy - 20, strength["title"])

#         # Score
#         c.setFont(FONT_BOLD, 20)
#         c.setFillColor(SUCCESS)
#         c.drawRightString(PAGE_WIDTH - MARGIN - 14, sy - 20, f"{strength['score']}/100")

#         # Description
#         desc = strength_descs.get(strength["title"], strength.get("description", ""))
#         c.setFont(FONT, 10.5)
#         c.setFillColor(TEXT_SECONDARY)
#         c.drawString(MARGIN + 56, sy - 40, desc)

#         # Progress bar
#         draw_progress_bar(c, MARGIN + 56, sy - card_h + 30,
#                           PAGE_WIDTH - MARGIN * 2 - 70, 10, strength["score"])

#         # Score pips on bar
#         for pip_val in [25, 50, 75, 100]:
#             pip_x = MARGIN + 56 + (pip_val / 100) * (PAGE_WIDTH - MARGIN * 2 - 70)
#             c.setFillColor(BACKGROUND)
#             c.circle(pip_x, sy - card_h + 25, 2, fill=1, stroke=0)

#         # Status tag
#         draw_tag(c, MARGIN + 56, sy - card_h + 6,
#                  score_status(strength["score"]), SUCCESS, height=14, radius=5)

#     # Radar mini for strengths
#     all_domains = data["domains"]
#     chart_y = content_top - 82 - len(strengths) * (card_h + gap) - 20
#     chart_h = 160
#     if chart_y - chart_h > 44:
#         draw_card(c, MARGIN, chart_y - chart_h,
#                   PAGE_WIDTH - MARGIN * 2, chart_h, radius=14)
#         draw_text(c, "Strength Distribution",
#                   MARGIN + 14, chart_y - 20, 12, FONT_BOLD)
#         # Mini bar chart for all domains sorted by score
#         sorted_domains = sorted(all_domains.items(), key=lambda x: x[1], reverse=True)
#         bar_w_total = PAGE_WIDTH - MARGIN * 2 - 28
#         bar_item_w = bar_w_total / len(sorted_domains)
#         for di, (dname, dval) in enumerate(sorted_domains):
#             bx = MARGIN + 14 + di * bar_item_w
#             max_bar_h = chart_h - 50
#             bh = (dval / 100) * max_bar_h
#             c.setFillColor(score_color(dval))
#             c.roundRect(bx + 4, chart_y - chart_h + 28, bar_item_w - 8, bh, 4, fill=1, stroke=0)
#             c.setFont(FONT, 7)
#             c.setFillColor(TEXT_SECONDARY)
#             c.drawCentredString(bx + bar_item_w / 2, chart_y - chart_h + 18,
#                                 dname[:5])
#             c.setFont(FONT_BOLD, 8)
#             c.setFillColor(TEXT_PRIMARY)
#             c.drawCentredString(bx + bar_item_w / 2,
#                                 chart_y - chart_h + 28 + bh + 4, str(dval))
def draw_strengths_page(c, data):
    draw_page_header(c, "Cognitive Strengths",
                     "Your standout capabilities and performance advantages", 7)
    draw_page_footer(c, data["report_id"])

    strengths   = data["strengths"]
    content_top = PAGE_HEIGHT - 88
    card_h      = 110
    gap         = 12

    # Intro card
    draw_card(c, MARGIN, content_top - 56,
              PAGE_WIDTH - MARGIN * 2, 48, radius=14, bg=HexColor("#F0FDF4"))
    c.setFillColor(SUCCESS)
    c.setFont(FONT_BOLD, 10)
    c.drawString(MARGIN + 16, content_top - 24,
                 "★  Your cognitive profile shows meaningful strengths worth celebrating and building upon.")
    c.setFont(FONT, 9)
    c.setFillColor(TEXT_SECONDARY)
    c.drawString(MARGIN + 16, content_top - 38,
                 "These areas demonstrate resilience and serve as anchors for overall improvement.")

    for si, strength in enumerate(strengths):
        sy = content_top - 74 - si * (card_h + gap)
        draw_card(c, MARGIN, sy - card_h, PAGE_WIDTH - MARGIN * 2, card_h, radius=14)

        # Rank badge
        rank_colors = [SUCCESS, PRIMARY, PRIMARY_LIGHT]
        rc = rank_colors[si] if si < len(rank_colors) else TEXT_MUTED
        c.setFillColor(rc)
        c.circle(MARGIN + 28, sy - card_h / 2, 18, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont(FONT_BOLD, 13)
        c.drawCentredString(MARGIN + 28, sy - card_h / 2 - 5, str(si + 1))

        # ── BADGE PILL ──
        badge_text  = f"{strength.get('icon','★')}  {strength.get('badge', strength['title'])}"
        badge_w     = c.stringWidth(badge_text, FONT_BOLD, 9) + 20
        c.setFillColor(score_color_light(strength["score"]))
        c.roundRect(MARGIN + 56, sy - 24, badge_w, 18, 8, fill=1, stroke=0)
        c.setFillColor(rc)
        c.setFont(FONT_BOLD, 9)
        c.drawCentredString(MARGIN + 56 + badge_w / 2, sy - 17, badge_text)

        # Domain title (smaller, below badge)
        c.setFont(FONT, 9)
        c.setFillColor(TEXT_MUTED)
        c.drawString(MARGIN + 56, sy - 38, strength["title"])

        # Score
        c.setFont(FONT_BOLD, 22)
        c.setFillColor(SUCCESS)
        c.drawRightString(PAGE_WIDTH - MARGIN - 14, sy - 24, f"{strength['score']}")
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_MUTED)
        c.drawRightString(PAGE_WIDTH - MARGIN - 14, sy - 38, "/100")

        # Description
        c.setFont(FONT, 10)
        c.setFillColor(TEXT_SECONDARY)
        wrap_text_in_box(c, strength.get("description", ""),
                         MARGIN + 56, sy - 58,
                         PAGE_WIDTH - MARGIN * 2 - 100, 10,
                         line_height=13, max_lines=2)

        # Progress bar with pip markers
        bar_y3 = sy - card_h + 25
        draw_progress_bar(c, MARGIN + 56, bar_y3,
                          PAGE_WIDTH - MARGIN * 2 - 70, 10, strength["score"])
        for pip_val in [25, 50, 70, 85]:
            pip_x = MARGIN + 56 + (pip_val / 100) * (PAGE_WIDTH - MARGIN * 2 - 70)
            c.setFillColor(BACKGROUND)
            c.circle(pip_x, bar_y3 + 5, 2, fill=1, stroke=0)

        # Status tag
        draw_tag(c, MARGIN + 56, sy - card_h + 6,
                 score_status(strength["score"]), rc, height=13, radius=5)

    # Strength distribution bar chart
    all_domains = data["domains"]
    chart_y     = content_top - 74 - len(strengths) * (card_h + gap) - 16
    chart_h     = 148

    if chart_y - chart_h > 44:
        draw_card(c, MARGIN, chart_y - chart_h,
                  PAGE_WIDTH - MARGIN * 2, chart_h, radius=14)
        draw_text(c, "Strength Distribution — All Domains",
                  MARGIN + 14, chart_y - 18, 11, FONT_BOLD)
        draw_divider(c, MARGIN + 14, chart_y - 28,
                     PAGE_WIDTH - MARGIN * 2 - 28)

        sorted_domains = sorted(all_domains.items(),
                                key=lambda x: x[1], reverse=True)
        bar_item_w  = (PAGE_WIDTH - MARGIN * 2 - 28) / len(sorted_domains)
        max_bar_h   = chart_h - 52

        for di, (dname, dval) in enumerate(sorted_domains):
            bx   = MARGIN + 14 + di * bar_item_w
            bh   = (dval / 100) * max_bar_h
            by3  = chart_y - chart_h + 28

            # Bar
            c.setFillColor(score_color(dval))
            c.roundRect(bx + 4, by3, bar_item_w - 8, bh, 4, fill=1, stroke=0)

            # Score above bar
            c.setFont(FONT_BOLD, 8)
            c.setFillColor(score_color(dval))
            c.drawCentredString(bx + bar_item_w / 2, by3 + bh + 2, str(dval))

            # Domain label below
            c.setFont(FONT, 6)
            c.setFillColor(TEXT_SECONDARY)
            c.drawCentredString(bx + bar_item_w / 2,
                                chart_y - chart_h + 16, dname)

            # Badge for top 3
            badge_info = STRENGTH_BADGES.get(dname, {})
            if badge_info and dval >= 70:
                icon = badge_info.get("icon", "")
                c.setFont(FONT, 9)
                c.setFillColor(score_color(dval))
                c.drawCentredString(bx + bar_item_w / 2, by3 + bh + 12, icon)

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
    "assessmentId": "LMT-2026-001284",
    "overall": {
        "score": 72,
        "rating": "Good"
    },
    "domains": {
        "memory":             38,
        "attentionFocus":     31,
        "processingSpeed":    58,
        "executiveFunction":  52,
        "mentalClarity":      44,
        "languageSkills":     72,
        "problemSolving":     68,
        "reactionTime":       80,
    },
    "lifestyleImpacts": {
        "sleepQualityImpact": "High",
        "stressLevelImpact":  "Moderate",
        "anxietyLoadImpact":  "Moderate",
        "burnoutRiskImpact":  "High",
    },
    "riskIndicators": [
        "Possible attention difficulties",
        "Possible mood-related concentration issues",
        "Possible stress-related cognitive fatigue",
    ],
    "cognitiveAge": {
        "actualAge":             29,
        "estimatedCognitiveAge": None,
        "disclaimer": "Motivational wellness metric only — not a clinical measurement.",
    },
    "strengths": [
        "Reaction time",
        "Language skills",
        "Problem solving",
    ],
    "recommendations": [
        "Prioritise 7–8 hours of sleep — even one extra hour improves memory consolidation.",
        "Try the Pomodoro technique (25 min focused work, 5 min break) to improve attention.",
        "Add 5–10 minutes of box breathing or mindfulness daily to reduce cortisol levels.",
        "20 minutes of aerobic exercise 4× per week significantly boosts cognitive performance.",
        "Limit passive social media scrolling to under 30 minutes daily.",
        "Use active recall instead of re-reading — doubles long-term retention.",
        "Set a consistent sleep schedule (same time ±30 min on weekends).",
        "This plan is a wellness guide, not medical advice. Consult a licensed clinician for persistent symptoms.",
    ],
    "progress": {
        "available": False,
        "deltas": [],
    },
    "charts": {
        "radarDomains": {
            "labels": [
                "Memory", "Attention & Focus", "Processing Speed",
                "Executive Function", "Mental Clarity", "Language Skills",
                "Problem Solving", "Reaction Time"
            ],
            "values": [38, 31, 58, 52, 44, 72, 68, 80],
        },
        "barLifestyleImpacts": {
            "labels": ["Sleep Quality", "Stress Level", "Anxiety Load", "Burnout Risk"],
            "values": [30, 60, 60, 30],
        },
    },
    "disclaimers": [
        "This is a wellness screening tool, not a diagnosis.",
        "Not intended to replace professional medical advice.",
        "Seek a licensed clinician for persistent symptoms.",
    ],
    "privacy": {
        "dataCollected":  ["age", "gender", "assessment_responses"],
        "storagePolicy":  "Responses not stored unless user explicitly opts in.",
        "hipaaNote":      "HIPAA safeguards apply when deployed in US healthcare context.",
    },
}

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    import os
    from app.services.report_mapper import transform_analysis_to_report

    pdf_bytes = build_report(sample_data, brand={
        "userName":     "Sarah Johnson",
        "primaryColor": "#2563EB",
        "accentColor":  "#7C3AED",
        "footerNote":   "Limitless Platform • v2.0",
    })

    output_path = "test_report.pdf"
    with open(output_path, "wb") as f:
        f.write(pdf_bytes)

    print(f"PDF generated: {os.path.getsize(output_path):,} bytes → {output_path}") 

def _draw_radar(c, cx, cy, radius, domains, fill=PRIMARY):
    """
    8-axis radar / spider chart of domain scores (0-100).
    Labels + scores sit just outside the outer ring, anchored by quadrant.
    """
    import math
    names = list(domains.keys())
    n = len(names)
    short = {"Problem Solving": "Problem", "Reaction Time": "Reaction"}
 
    def pt(frac, i):
        ang = math.radians(90 - i * (360.0 / n))
        return (cx + radius * frac * math.cos(ang),
                cy + radius * frac * math.sin(ang))
 
    # Grid rings (octagons)
    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(0.5)
    for ring in (0.25, 0.5, 0.75, 1.0):
        p = c.beginPath()
        x0, y0 = pt(ring, 0)
        p.moveTo(x0, y0)
        for i in range(1, n):
            xi, yi = pt(ring, i)
            p.lineTo(xi, yi)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
 
    # Spokes
    for i in range(n):
        xi, yi = pt(1.0, i)
        c.line(cx, cy, xi, yi)
 
    # Data polygon
    p = c.beginPath()
    fx, fy = pt(domains[names[0]] / 100.0, 0)
    p.moveTo(fx, fy)
    for i in range(1, n):
        xi, yi = pt(domains[names[i]] / 100.0, i)
        p.lineTo(xi, yi)
    p.close()
    c.setFillColor(Color(fill.red, fill.green, fill.blue, alpha=0.20))
    c.setStrokeColor(fill)
    c.setLineWidth(1.6)
    c.drawPath(p, stroke=1, fill=1)
 
    # Vertex dots + labels + scores
    for i, name in enumerate(names):
        sc = domains[name]
        vx, vy = pt(sc / 100.0, i)
        c.setFillColor(score_color(sc))
        c.circle(vx, vy, 2.4, fill=1, stroke=0)
 
        ang = math.radians(90 - i * (360.0 / n))
        ox, oy = math.cos(ang), math.sin(ang)
        tx = cx + (radius + 9) * ox
        ty = cy + (radius + 9) * oy + (2 if oy >= 0 else -8)
        lbl = short.get(name, name)
        c.setFont(FONT_BOLD, 7)
        c.setFillColor(TEXT_SECONDARY)
        draw_fn = (c.drawString if ox > 0.25
                   else c.drawRightString if ox < -0.25 else c.drawCentredString)
        draw_fn(tx, ty, lbl)
        c.setFont(FONT_BOLD, 7)
        c.setFillColor(score_color(sc))
        draw_fn(tx, ty - 8, str(sc))
 
 
def draw_teaser_report(c, data):
    """
    Single-page A4 cognitive wellness report for the Limitless AI platform.
 
    `data` is the dict returned by transform_analysis_to_report().
    All content is fully visible; the "Your Complete Report Includes" card
    lists what the detailed report adds and notes how to unlock it.
    """
    score      = data["overall_score"]
    user       = data["user"]
    benchmarks = data["benchmarks"]
    strengths  = data["strengths"]
    traffic    = data["traffic_light"]
    lifestyle  = data["lifestyle"]
 
    inner_w = PAGE_WIDTH - 2 * MARGIN          # 515pt
    GAP     = 13
 
    # ---- Page background ----------------------------------------------------
    c.setFillColor(BACKGROUND)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
 
    # =======================================================================
    # SECTION 1 — Header strip (56pt, full width)
    # =======================================================================
    HEADER_H = 56
    header_y = PAGE_HEIGHT - HEADER_H
    draw_gradient_rect(c, 0, header_y, PAGE_WIDTH, HEADER_H, GRADIENT_1, GRADIENT_3)
    draw_text(c, "LIMITLESS", MARGIN, header_y + 30, size=18, font=FONT_BOLD, color=white)
    draw_text(c, "COGNITIVE WELLNESS", MARGIN, header_y + 14, size=8, color=white)
    draw_text(c, f"Report ID: {data.get('report_id', '')}", PAGE_WIDTH - MARGIN,
              header_y + 32, size=8, color=white, align="right")
    draw_text(c, user.get("assessment_date", ""), PAGE_WIDTH - MARGIN,
              header_y + 18, size=8, color=Color(1, 1, 1, alpha=0.85), align="right")
 
    y = header_y - GAP
 
    # =======================================================================
    # SECTION 2 — Score gauge + peer comparison (compact)
    # =======================================================================
    S2_H = 144
    S2_Y = y - S2_H
    PAD  = 14
    draw_card(c, MARGIN, S2_Y, inner_w, S2_H, radius=14, border=True)
 
    left_w   = inner_w * 0.40
    gauge_cx = MARGIN + left_w / 2
    gauge_cy = S2_Y + S2_H / 2 + 14
    draw_large_gauge(c, gauge_cx, gauge_cy, 46, score)
    status = score_status(score)
    draw_tag(c, gauge_cx - 42, S2_Y + 12, status, score_color(score),
             white, width=84, height=20, radius=9)
 
    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(0.5)
    c.line(MARGIN + left_w, S2_Y + PAD, MARGIN + left_w, S2_Y + S2_H - PAD)
 
    rx = MARGIN + left_w + PAD
    rw = inner_w - left_w - PAD * 2
    ry = S2_Y + S2_H - PAD - 4
    draw_text(c, "Your Cognitive Wellness Score", rx, ry, size=12,
              font=FONT_BOLD, color=TEXT_PRIMARY)
    ry -= 16
    draw_text(c, f"{status} - {score}/100", rx, ry, size=10,
              font=FONT_BOLD, color=score_color(score))
    ry -= 13
    draw_text(c, f"Top {100 - benchmarks['percentile']}% of {benchmarks['band_label']}",
              rx, ry, size=8, color=TEXT_MUTED)
    ry -= 20
 
    label_w = 60
    bar_x   = rx + label_w
    bar_w   = rw - label_w - 26
    rows = [
        ("You",      score,                       score_color(score)),
        ("Peer Avg", benchmarks["peer_average"],  HexColor("#CBD5E1")),
        ("Top 10%",  benchmarks["top_10_pct"],    SUCCESS),
    ]
    for label, val, clr in rows:
        draw_text(c, label, rx, ry, size=8, color=TEXT_SECONDARY)
        c.setFillColor(HexColor("#F1F5F9"))
        c.roundRect(bar_x, ry - 2, bar_w, 8, 4, fill=1, stroke=0)
        c.setFillColor(clr)
        c.roundRect(bar_x, ry - 2, max(4, bar_w * val / 100), 8, 4, fill=1, stroke=0)
        draw_text(c, str(val), bar_x + bar_w + 6, ry, size=8,
                  font=FONT_BOLD, color=TEXT_SECONDARY)
        ry -= 18
 
    y = S2_Y - GAP
 
    # =======================================================================
    # SECTION 3 — Domain radar + Cognitive Age + Risk indicators
    # =======================================================================
    S3_H = 176
    S3_Y = y - S3_H
    draw_card(c, MARGIN, S3_Y, inner_w, S3_H, radius=14, border=True)
 
    radar_zone_w = 268
    draw_text(c, "Brain Function - 8 Domains", MARGIN + 16, S3_Y + S3_H - 18,
              size=10, font=FONT_BOLD, color=TEXT_PRIMARY)
    radar_cx = MARGIN + radar_zone_w / 2
    radar_cy = S3_Y + S3_H / 2 - 6
    _draw_radar(c, radar_cx, radar_cy, 56, data["domains"])
 
    # Vertical divider
    div_x = MARGIN + radar_zone_w
    c.setStrokeColor(BORDER_COLOR)
    c.setLineWidth(0.5)
    c.line(div_x, S3_Y + 12, div_x, S3_Y + S3_H - 12)
 
    # Right panel — Cognitive Age
    px = div_x + 16
    pw = inner_w - radar_zone_w - 30
    cog_age = user.get("cognitive_age_display")
    actual  = user.get("age")
    draw_text(c, "COGNITIVE AGE", px, S3_Y + S3_H - 20, size=8,
              font=FONT_BOLD, color=TEXT_SECONDARY)
    if cog_age is not None and actual is not None:
        delta = cog_age - actual
        if delta <= 0:
            d_color, d_text = SUCCESS, f"{abs(delta)} yrs younger"
        elif delta <= 3:
            d_color, d_text = WARNING, f"+{delta} yrs older"
        else:
            d_color, d_text = DANGER, f"+{delta} yrs older"
        draw_text(c, str(cog_age), px, S3_Y + S3_H - 52, size=34,
                  font=FONT_BOLD, color=d_color)
        draw_text(c, "yrs", px + c.stringWidth(str(cog_age), FONT_BOLD, 34) + 4,
                  S3_Y + S3_H - 52, size=11, color=TEXT_MUTED)
        draw_text(c, f"Actual age: {actual}", px, S3_Y + S3_H - 66, size=8,
                  color=TEXT_MUTED)
        draw_tag(c, px, S3_Y + S3_H - 88, d_text, d_color, white,
                 height=16, radius=7)
        msg = user.get("cognitive_age_message", "")
        if msg:
            wrap_text_in_box(c, msg, px, S3_Y + S3_H - 104, pw, 8,
                             line_height=10, max_lines=2, color=TEXT_SECONDARY)
    else:
        draw_text(c, "Available in full report", px, S3_Y + S3_H - 50, size=9,
                  color=TEXT_MUTED)
 
    # Right panel — Risk indicators (below cognitive age)
    draw_divider(c, px, S3_Y + 58, pw)
    draw_text(c, "RISK INDICATORS", px, S3_Y + 46, size=8,
              font=FONT_BOLD, color=DANGER)
    risks = data.get("risk_indicators", []) or ["No significant risks detected"]
    ind_y = S3_Y + 32
    for r in risks[:2]:
        c.setFillColor(DANGER)
        c.circle(px + 2, ind_y + 3, 2, fill=1, stroke=0)
        wrap_text_in_box(c, r, px + 9, ind_y, pw - 10, 8,
                         line_height=9, max_lines=2, color=TEXT_SECONDARY)
        ind_y -= 20
 
    y = S3_Y - GAP
 
    # =======================================================================
    # SECTION 4 — Traffic light (all three columns visible)
    # =======================================================================
    S4_H  = 84
    S4_Y  = y - S4_H
    col_w = inner_w / 3
    cpad  = 12
    draw_card(c, MARGIN, S4_Y, inner_w, S4_H, radius=14, border=True)
 
    def _tl_column(idx, header, header_color, items):
        col_x = MARGIN + idx * col_w
        if idx > 0:
            c.setStrokeColor(BORDER_COLOR)
            c.setLineWidth(0.5)
            c.line(col_x, S4_Y + 8, col_x, S4_Y + S4_H - 8)
        draw_text(c, header, col_x + cpad, S4_Y + S4_H - 18, size=8,
                  font=FONT_BOLD, color=header_color)
        row_y = S4_Y + S4_H - 36
        if not items:
            draw_text(c, "None", col_x + cpad, row_y + 2, size=8, color=TEXT_MUTED)
            return
        for i, item in enumerate(items[:3]):
            lbl = item["domain"] if isinstance(item, dict) else str(item)
            sc  = item["score"] if isinstance(item, dict) else 75
            pw2 = c.stringWidth(lbl, FONT_BOLD, 8) + 14
            c.setFillColor(score_color_light(sc))
            c.roundRect(col_x + cpad, row_y - i * 16, pw2, 13, 5, fill=1, stroke=0)
            draw_text(c, lbl, col_x + cpad + 7, row_y - i * 16 + 4, size=8,
                      font=FONT_BOLD, color=score_color(sc))
 
    _tl_column(0, "HIGH PRIORITY",   DANGER,  traffic["red"])
    _tl_column(1, "NEEDS ATTENTION", WARNING, traffic["yellow"])
    _tl_column(2, "STRENGTHS",       SUCCESS, traffic["green"])
 
    y = S4_Y - GAP
 
    # =======================================================================
    # SECTION 5 — Lifestyle snapshot
    # =======================================================================
    S5_H = 78
    S5_Y = y - S5_H
    draw_card(c, MARGIN, S5_Y, inner_w, S5_H, radius=14, border=True)
    draw_text(c, "Lifestyle Impact Snapshot", MARGIN + PAD, S5_Y + S5_H - 16,
              size=10, font=FONT_BOLD, color=TEXT_PRIMARY)
    keys   = list(lifestyle.keys())
    slot_w = inner_w / len(keys)
    dots_y = S5_Y + S5_H - 40
    for i, k in enumerate(keys):
        dcx = MARGIN + slot_w * i + slot_w / 2
        c.setFillColor(score_color(lifestyle[k]))
        c.circle(dcx, dots_y, 7, fill=1, stroke=0)
        draw_text(c, k, dcx, dots_y - 16, size=8, color=TEXT_MUTED, align="center")
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(TEXT_MUTED)
    c.drawCentredString(PAGE_WIDTH / 2, S5_Y + 8,
                        "Full lifestyle analysis available in your complete report")
 
    y = S5_Y - GAP
 
    # =======================================================================
    # SECTION 6 — Complete report contents (with unlock note)
    # =======================================================================
    S6_H = 104
    S6_Y = y - S6_H
    draw_card(c, MARGIN, S6_Y, inner_w, S6_H, radius=14, border=True)
    c.setFillColor(PRIMARY)
    c.roundRect(MARGIN, S6_Y, 12, S6_H, 14, fill=1, stroke=0)
    c.rect(MARGIN + 6, S6_Y, 6, S6_H, fill=1, stroke=0)
 
    tx = MARGIN + 24
    draw_text(c, "Your Complete Report Includes", tx, S6_Y + S6_H - 20,
              size=11, font=FONT_BOLD, color=TEXT_PRIMARY)
    draw_divider(c, tx, S6_Y + S6_H - 30, inner_w - 36)
 
    items = [
        "Core Brain Function (8 Domains)",
        "Root Cause Analysis",
        "Benchmark vs Age Group",
        "Future Risk Prediction (30 & 90 days)",
        "30-Day Improvement Roadmap",
        "AI Coach Recommendations",
        "Cognitive Age Estimate",
    ]
    col_item_w = (inner_w - 36) / 2
    x_left  = tx
    x_right = tx + col_item_w
    start_y = S6_Y + S6_H - 42
    spacing = 13
    for idx, item in enumerate(items):
        col = 0 if idx < 4 else 1
        row = idx if idx < 4 else idx - 4
        ix  = x_left if col == 0 else x_right
        iy  = start_y - row * spacing
        c.setFillColor(PRIMARY)
        c.circle(ix + 3, iy + 3, 2.2, fill=1, stroke=0)
        draw_text(c, item, ix + 12, iy, size=9, color=TEXT_SECONDARY)
 
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(PRIMARY)
    c.drawString(tx, S6_Y + 10,
                 "See your full detailed report by unlocking full access.")
 
 
    # =======================================================================
    # SECTION 7 — CTA banner (pinned above footer)
    # =======================================================================
    FOOTER_H = 30
    S7_H = 80
    S7_Y = FOOTER_H + 10
    # rounded gradient: clip a rounded rect, paint gradient inside
    c.saveState()
    p = c.beginPath()
    p.roundRect(MARGIN, S7_Y, inner_w, S7_H, 14)
    c.clipPath(p, stroke=0, fill=0)
    draw_gradient_rect(c, MARGIN, S7_Y, inner_w, S7_H, GRADIENT_1, GRADIENT_3, steps=50)
    c.restoreState()
 
    cta_cx = PAGE_WIDTH / 2
    draw_text(c, "Your full 10-page AI Cognitive Wellness Report is ready.",
              cta_cx, S7_Y + S7_H - 22, size=11, font=FONT_BOLD, color=white, align="center")
    draw_text(c, "Unlock personalized insights, your improvement plan, and cognitive age estimate.",
              cta_cx, S7_Y + S7_H - 38, size=9,
              color=Color(1, 1, 1, alpha=0.70), align="center")
    btn_w, btn_h = 168, 28
    btn_x = cta_cx - btn_w / 2
    btn_y = S7_Y + 14
    c.setFillColor(SUCCESS)
    c.roundRect(btn_x, btn_y, btn_w, btn_h, 9, fill=1, stroke=0)
    draw_text(c, "UNLOCK FULL REPORT", cta_cx, btn_y + btn_h / 2 - 4, size=10,
              font=FONT_BOLD, color=white, align="center")
 
    # ---- Footer -------------------------------------------------------------
    c.setFillColor(HexColor("#0F172A"))
    c.rect(0, 0, PAGE_WIDTH, FOOTER_H, fill=1, stroke=0)
    draw_text(c, "LIMITLESS AI", MARGIN, FOOTER_H / 2 - 3, size=9,
              font=FONT_BOLD, color=white)
    draw_text(c, "Not a clinical diagnostic tool", PAGE_WIDTH / 2, FOOTER_H / 2 - 3,
              size=9, color=TEXT_MUTED, align="center")
    draw_text(c, f"Report ID: {data.get('report_id', '')}", PAGE_WIDTH - MARGIN,
              FOOTER_H / 2 - 3, size=9, color=TEXT_MUTED, align="right")
 
 
def build_teaser_report(analysis: dict, brand: dict = None) -> bytes:
    """Build the teaser PDF and return raw bytes."""
    data = transform_analysis_to_report(analysis["analysis"])   # prod: transform_analysis_to_report(analysis)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_teaser_report(c, data)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
 
 
if __name__ == "__main__":
    sample_analysis = {
        "assessmentId": "LMT-TEASER-001",
        "overall": {"score": 72, "rating": "Good"},
        "domains": {
            "memory": 38, "attentionFocus": 31, "processingSpeed": 58,
            "executiveFunction": 52, "mentalClarity": 44,
            "languageSkills": 72, "problemSolving": 68, "reactionTime": 80,
        },
        "lifestyleImpacts": {
            "sleepQualityImpact": "High", "stressLevelImpact": "Moderate",
            "anxietyLoadImpact": "Moderate", "burnoutRiskImpact": "High",
        },
        "riskIndicators": ["Possible attention difficulties", "Possible stress-related fatigue"],
        "cognitiveAge": {"actualAge": 29, "estimatedCognitiveAge": None},
        "strengths": ["Reaction time", "Language skills", "Problem solving"],
        "recommendations": ["Prioritise 7-8 hours sleep.", "Try Pomodoro technique."],
        "progress": {"available": False, "deltas": []},
        "charts": {"radarDomains": {"labels": [], "values": []}, "barLifestyleImpacts": {"labels": [], "values": []}},
        "disclaimers": ["This is a wellness screening tool, not a diagnosis."],
        "privacy": {"dataCollected": ["age", "gender"], "storagePolicy": "Not stored.", "hipaaNote": "HIPAA applies."},
    }
    pdf = build_teaser_report(sample_analysis, {})
    open("teaser_report.pdf", "wb").write(pdf)
    print(f"Generated: {len(pdf):,} bytes")
 
