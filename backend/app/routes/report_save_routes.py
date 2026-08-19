"""
report_save_routes.py
---------------------
Generates a real PDF report and saves it to:
  D:/c103191-Data/DigitalDRM/Reports/

Uses fpdf2 (pure Python, no system dependencies).
Install once: venv\\Scripts\\pip install fpdf2

Prefix: /report-save  (no conflict with existing /reports router)
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.email_service import send_email_with_attachment
from app.services import email_recipient_service as recipients_svc
from app.database import SessionLocal

logger = logging.getLogger("digitaldrm.report_save")

REPORTS_DIR = Path(r"D:\Digitalization_DigitalDRM2.o\DigitalDRM\Reports")

# Recipients for auto-emailed reports (combined report, per-department
# reports, and the President Dashboard's Overall Summary) are resolved
# at send-time from the email_recipients table (Admin Dashboard > Email
# Services) via _resolve_recipient() below, instead of being hardcoded
# here. See app/services/email_recipient_service.py.


def _resolve_recipient(recipient_type: str, department: str | None = None, plant_id: int | None = None) -> list[str]:
    """Opens a short-lived DB session to resolve recipients for one
    email send. These report-building functions are plain module
    functions (not FastAPI route handlers), so they don't already have
    a `db: Session` available via Depends()."""
    db = SessionLocal()
    try:
        return recipients_svc.get_recipients(db, recipient_type, department=department, plant_id=plant_id)
    finally:
        db.close()

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Standardized Indian-FY quarter labels — used for display text (report
# subtitles, the "Period" meta row, and email subjects) across all
# PDF/Excel exports. Matches report_service.py's get_quarter_months()
# and scheduler.py's quarter_just_ended mapping exactly:
#   Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar
QUARTER_RANGES = {1: "Apr-Jun", 2: "Jul-Sep", 3: "Oct-Dec", 4: "Jan-Mar"}


def _quarter_display(quarter: Optional[int]) -> str:
    """'Q1' -> 'Q1 (Apr-Jun)'. Used only for human-facing display text;
    filenames keep the plain 'Q{n}' form via _period()/_period_overall()/
    _period_dept() so file naming conventions don't change."""
    if quarter is None:
        return ""
    rng = QUARTER_RANGES.get(quarter, "")
    return f"Q{quarter} ({rng})" if rng else f"Q{quarter}"

router = APIRouter(prefix="/report-save", tags=["Report Auto-Save"])


# ── Request schema ─────────────────────────────────────────────────────────────

class ReportSaveRequest(BaseModel):
    plant_id:    int
    report_type: str                # "Monthly" | "Quarterly" | "Yearly"
    year:        int
    month:       Optional[int] = None
    quarter:     Optional[int] = None
    report_data: Dict[str, Any]


class PlantSummaryRow(BaseModel):
    """One plant's row in the President Dashboard's Overall Summary,
    exactly as displayed on screen (already-computed plan/actual/
    achieved% — no recalculation happens on the backend)."""
    plant_id:              int
    plant_name:             str
    total_plan:             float
    total_actual:           float
    overall_achieved:       Optional[float] = None
    departments_with_data:  int
    on_track_count:         int
    total_departments:      int


class DepartmentDetailRow(BaseModel):
    """
    One department row within a single selected plant, exactly as shown
    in the President Dashboard's plant-specific view (Department
    Performance cards / Department-wise Performance chart). Sent only
    when `plant_filter` is a specific plant (not "all") — mirrors
    PlantSummaryOverview.jsx's `selectedPlant.rows`.
    """
    label:    str
    plan:     float
    actual:   float
    achieved: Optional[float] = None
    status:   str    # "green" | "amber" | "red" | "nodata" (matches statusOf() in the frontend)


class OverallSummarySaveRequest(BaseModel):
    """
    Payload for the President Dashboard's "Generate Report" button.
    `plants` must be EXACTLY the currently filtered/visible rows shown
    on screen (i.e. respecting the Plant / Period Type / Year /
    Month-Quarter filters already applied in PlantSummaryOverview.jsx) —
    the backend does not re-query or re-filter anything, it only renders
    whatever is sent, so the PDF always matches what the President is
    looking at.

    When the President has selected an individual plant (plant_filter is
    a specific plant id, not "all"), the frontend additionally sends
    `department_details` — the selected plant's per-department rows. In
    that case the PDF renders the plant-specific layout (department KPIs,
    Department-wise Performance table/chart) instead of the multi-plant
    layout, exactly matching what's on screen.
    """
    period_type:  str                 # "monthly" | "quarterly" | "yearly"
    year:         int
    month:        Optional[int] = None
    quarter:      Optional[int] = None
    plant_filter: str                 # "all" or a specific plant id (as string)
    plants:       List[PlantSummaryRow]
    overall_achieved:   Optional[float] = None
    on_track_plants:    int = 0
    attention_plants:   int = 0
    department_details: Optional[List[DepartmentDetailRow]] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

DEPTS = [
    ("Production",    "production"),
    ("Manpower",      "manpower"),
    ("Sales",         "sales"),
    ("OVC Elements",  "ovc"),
    ("Despatch",      "despatch"),
    ("Rejection PPM", "rejection_ppm"),
    ("Product Value", "product_value"),
]


def _period(req: ReportSaveRequest) -> str:
    if req.report_type == "Monthly"   and req.month:   return MONTH_NAMES[req.month]
    if req.report_type == "Quarterly" and req.quarter: return f"Q{req.quarter}"
    return str(req.year)


def _stem(req: ReportSaveRequest) -> str:
    plant  = f"Plant{req.plant_id:02d}"
    period = _period(req)
    if req.report_type == "Yearly":
        return f"{plant}_Yearly_{req.year}"
    return f"{plant}_{req.report_type}_{period}_{req.year}"


def _period_overall(req: "OverallSummarySaveRequest") -> str:
    if req.period_type == "monthly"   and req.month:   return MONTH_NAMES[req.month]
    if req.period_type == "quarterly" and req.quarter: return f"Q{req.quarter}"
    return str(req.year)


def _stem_overall(req: "OverallSummarySaveRequest") -> str:
    period = _period_overall(req)
    is_plant_view = req.plant_filter != "all" and bool(req.department_details)
    label = req.period_type.capitalize()
    if is_plant_view:
        plant_name = req.plants[0].plant_name if req.plants else f"Plant{req.plant_filter}"
        scope = plant_name.replace(" ", "")
        prefix = "PlantDashboard"
    else:
        scope = "AllPlants"
        prefix = "OverallSummary"
    if req.period_type == "yearly":
        return f"{prefix}_{scope}_Yearly_{req.year}"
    return f"{prefix}_{scope}_{label}_{period}_{req.year}"


# ── Automated per-department Monthly/Quarterly/Yearly reports ──────────────────
#
# One department report each period, emailed to that department's own
# Staff Incharge — separate from the combined all-departments report
# (generate_and_save_report above) and from the
# President Dashboard's Overall Summary. Triggered by
# app/scheduler.py's _run_report_generation_job on the 1st of every
# month/quarter/year.
#
# Department labels only — the actual Staff Incharge email address(es)
# for each department are resolved at send-time from the
# email_recipients table (Admin Dashboard > Email Services) via
# _resolve_recipient("staff_incharge", department=dept_key, plant_id=...),
# using the SAME department slugs as reminder_service.DEPARTMENTS and
# role_access.role, so one Admin Dashboard edit updates reminders,
# escalations, and reports together.
DEPARTMENT_RECIPIENTS = {
    "production":    {"label": "Production"},
    "manpower":      {"label": "Manpower"},
    "ovc":           {"label": "OVC Elements"},
    "rejection_ppm": {"label": "Rejection PPM"},
    "product_value": {"label": "Product Value"},
    "despatch":      {"label": "Despatch"},
    "sales":         {"label": "Sales"},
}


def _period_dept(report_type: str, year: int, month: Optional[int], quarter: Optional[int]) -> str:
    if report_type == "Monthly"   and month:   return MONTH_NAMES[month]
    if report_type == "Quarterly" and quarter: return f"Q{quarter}"
    return str(year)


def _stem_department(
    dept_key: str, plant_id: int, report_type: str,
    year: int, month: Optional[int], quarter: Optional[int],
) -> str:
    """
    Deterministic filename for one department's report for one period —
    e.g. Plant05_Production_Monthly_June_2026.pdf. Because this name is
    always exactly the same for a given (plant, department, period), its
    mere existence in REPORTS_DIR is used as the "already generated"
    guard: the same period is never generated (or re-emailed) twice,
    even if the scheduler runs more than once on the same day.
    """
    dept_label = DEPARTMENT_RECIPIENTS[dept_key]["label"].replace(" ", "")
    plant = f"Plant{plant_id:02d}"
    period = _period_dept(report_type, year, month, quarter)
    if report_type == "Yearly":
        return f"{plant}_{dept_label}_Yearly_{year}"
    return f"{plant}_{dept_label}_{report_type}_{period}_{year}"


# ── Brand palette (kept consistent with the app's existing UI colors) ──────────

_NAVY        = (15, 23, 42)      # #0f172a — header band / primary text
_SLATE_BG    = (248, 250, 252)   # #f8fafc — light card backgrounds
_SLATE_BORDER= (226, 232, 240)   # #e2e8f0 — card / table borders
_SLATE_MUTED = (100, 116, 139)   # #64748b — muted labels
_ACCENT_BLUE = (37, 99, 235)     # #2563eb — accent line / brand blue
_GREEN       = (22, 163, 74)     # #16a34a — on track / positive
_AMBER       = (217, 119, 6)     # #d97706 — near target
_RED         = (220, 38, 38)     # #dc2626 — below target / negative
_WHITE       = (255, 255, 255)

# Achievement thresholds — identical to the ones already used elsewhere in
# the app (e.g. DepartmentDetail.jsx's "On Track / Near Target / Below
# Target" status labels), so the PDF's color coding matches the dashboard.
_THRESHOLD_ON_TRACK   = 100
_THRESHOLD_NEAR_TARGET = 80


def _status_color(achieved_pct: Optional[float]):
    if achieved_pct is None:
        return _SLATE_MUTED
    if achieved_pct >= _THRESHOLD_ON_TRACK:
        return _GREEN
    if achieved_pct >= _THRESHOLD_NEAR_TARGET:
        return _AMBER
    return _RED


def _status_label(achieved_pct: Optional[float]) -> str:
    if achieved_pct is None:
        return "No Data"
    if achieved_pct >= _THRESHOLD_ON_TRACK:
        return "On Track"
    if achieved_pct >= _THRESHOLD_NEAR_TARGET:
        return "Near Target"
    return "Below Target"


class _ReportPDF:
    """
    Thin wrapper around fpdf2's FPDF that draws a consistent branded
    header and footer on every page automatically (fpdf2 calls header()/
    footer() on every add_page()/page break). Purely presentational —
    does not touch any report data, calculation, or the public
    _build_pdf() signature/return type.
    """

    def __new__(cls, *args, **kwargs):
        from fpdf import FPDF

        class _Inner(FPDF):
            report_title = "DIGITAL DRM REPORT"
            report_subtitle = ""

            def header(self):
                self.set_fill_color(*_NAVY)
                self.rect(0, 0, 210, 22, style="F")

                self.set_text_color(*_WHITE)
                self.set_font("Helvetica", "B", 13)
                self.set_xy(14, 5)
                self.cell(0, 7, "RANE MADRAS LTD", ln=True)

                self.set_font("Helvetica", "", 8)
                self.set_text_color(191, 219, 254)  # light blue tint
                self.set_xy(14, 13)
                self.cell(0, 5, self.report_subtitle, ln=True)

                # Right-aligned title badge
                self.set_font("Helvetica", "B", 10)
                self.set_text_color(*_WHITE)
                self.set_xy(0, 8)
                self.cell(196, 6, self.report_title, align="R")

                # Thin accent line beneath the navy band
                self.set_fill_color(*_ACCENT_BLUE)
                self.rect(0, 22, 210, 1.2, style="F")

                self.set_text_color(*_NAVY)
                self.set_y(30)

            def footer(self):
                self.set_y(-15)
                self.set_draw_color(*_SLATE_BORDER)
                self.line(14, self.get_y(), 196, self.get_y())

                self.set_font("Helvetica", "I", 7.5)
                self.set_text_color(148, 163, 184)  # #94a3b8
                self.set_xy(14, self.get_y() + 2)
                self.cell(
                    120, 5,
                    "Generated by DigitalDRM Automated System - Confidential",
                    align="L",
                )
                self.set_xy(0, self.get_y())
                self.cell(196, 5, f"Page {self.page_no()} of {{nb}}", align="R")

        return _Inner(*args, **kwargs)


def _kpi_card(pdf, x: float, y: float, w: float, h: float, label: str, value: str, accent):
    """Draws a single rounded-look KPI card (fpdf2 has no native rounded
    rect fill+border combo we rely on here, so a simple bordered card with
    a colored top strip is used — clean and consistent across renderers)."""
    pdf.set_xy(x, y)
    pdf.set_fill_color(*_WHITE)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(x, y, w, h, style="DF")

    # Colored accent strip along the top of the card
    pdf.set_fill_color(*accent)
    pdf.rect(x, y, w, 1.4, style="F")

    pdf.set_xy(x + 3, y + 4)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*_SLATE_MUTED)
    pdf.cell(w - 6, 4, label.upper())

    pdf.set_xy(x + 3, y + 9.5)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*_NAVY)
    pdf.cell(w - 6, 7, value)


def _build_pdf(req: ReportSaveRequest) -> bytes:
    """
    Generates a clean, professional, branded PDF using fpdf2 and returns
    the bytes. Presentation only — reads exactly the same req.report_data
    the caller already computed; no calculation, schema, or workflow
    changes versus the previous version of this function.
    """
    period       = _period(req)
    period_display = _quarter_display(req.quarter) if req.report_type == "Quarterly" and req.quarter else period
    generated_at = datetime.now().strftime("%d-%b-%Y %H:%M")

    # ── Aggregate the department rows once so the executive summary, KPI
    # cards, table, and chart all read from the same derived values instead
    # of recomputing anything differently. This is pure display-layer
    # aggregation of numbers report_data already contains — no new business
    # logic, nothing written back anywhere.
    rows = []
    for label, key in DEPTS:
        d = req.report_data.get(key)
        if not d:
            continue
        plan   = d.get("plan",   0) or 0
        actual = d.get("actual", 0) or 0
        variance = actual - plan
        achieved = (actual / plan * 100) if plan else None
        rows.append({
            "label": label, "plan": plan, "actual": actual,
            "variance": variance, "achieved": achieved,
        })

    total_plan   = sum(r["plan"]   for r in rows)
    total_actual = sum(r["actual"] for r in rows)
    overall_achieved = (total_actual / total_plan * 100) if total_plan else None
    on_track_count = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] >= _THRESHOLD_ON_TRACK)
    attention_count = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] < _THRESHOLD_NEAR_TARGET)
    best_row = max((r for r in rows if r["achieved"] is not None), key=lambda r: r["achieved"], default=None)
    worst_row = min((r for r in rows if r["achieved"] is not None), key=lambda r: r["achieved"], default=None)

    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.report_title = f"{req.report_type.upper()} REPORT"
    pdf.report_subtitle = f"ECD Division  |  Plant {req.plant_id}  |  {period_display} {req.year}"
    pdf.add_page()

    # ── Report details bar ───────────────────────────────────────────────
    pdf.set_fill_color(*_SLATE_BG)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(14, pdf.get_y(), 182, 16, style="DF")

    meta_items = [
        ("Plant",       f"Plant {req.plant_id}"),
        ("Report Type", req.report_type),
        ("Period",      f"{period_display} {req.year}"),
        ("Generated",   generated_at),
    ]
    col_w = 45.5
    meta_y = pdf.get_y()
    for i, (label, value) in enumerate(meta_items):
        x = 14 + i * col_w
        pdf.set_xy(x + 3, meta_y + 2.5)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(col_w - 4, 4, label.upper())
        pdf.set_xy(x + 3, meta_y + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_w - 4, 5, value)
    pdf.set_y(meta_y + 20)

    # ── Executive summary ─────────────────────────────────────────────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Executive Summary", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(3)

    overall_txt = f"{overall_achieved:.1f}%" if overall_achieved is not None else "N/A"
    summary_lines = [
        f"This {req.report_type.lower()} report covers Plant {req.plant_id} for {period} {req.year}, "
        f"consolidating {len(rows)} department(s). Overall achievement against plan stood at {overall_txt}, "
        f"with {on_track_count} department(s) on track and {attention_count} department(s) needing attention.",
    ]
    if best_row:
        summary_lines.append(
            f"{best_row['label']} was the top performer at {best_row['achieved']:.1f}% of plan."
        )
    if worst_row and worst_row is not best_row:
        summary_lines.append(
            f"{worst_row['label']} recorded the lowest achievement at {worst_row['achieved']:.1f}% and may need review."
        )

    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)  # #334155
    pdf.multi_cell(182, 5, "  ".join(summary_lines))
    pdf.ln(4)

    # ── KPI cards row ──────────────────────────────────────────────────────
    # "Overall Achieved" box intentionally removed per requirement — the
    # remaining 3 cards (Departments, On Track, Needs Attention) are
    # unchanged in content/values, only widened to fill the row evenly.
    card_y = pdf.get_y()
    card_h = 17
    gap = 4
    card_w = (182 - gap * 2) / 3

    _kpi_card(pdf, 14, card_y, card_w, card_h,
              "Departments", str(len(rows)), _ACCENT_BLUE)
    _kpi_card(pdf, 14 + (card_w + gap) * 1, card_y, card_w, card_h,
              "On Track", str(on_track_count), _GREEN)
    _kpi_card(pdf, 14 + (card_w + gap) * 2, card_y, card_w, card_h,
              "Needs Attention", str(attention_count), _RED if attention_count else _SLATE_MUTED)

    pdf.set_y(card_y + card_h + 8)

    # ── Table ───────────────────────────────────────────────────────────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Department-wise Performance", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

    headers    = ["Department", "Plan", "Actual", "Variance", "Achieved %", "Status"]
    col_widths = [42, 24, 24, 26, 28, 38]

    pdf.set_x(14)
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_draw_color(*_SLATE_BORDER)
    for h, w in zip(headers, col_widths):
        align = "L" if h == "Department" else "C" if h == "Status" else "R"
        pdf.cell(w, 8, h, border=0, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    row_fill = False
    for r in rows:
        plan, actual, variance, achieved = r["plan"], r["actual"], r["variance"], r["achieved"]
        # Show deviation from 100%, matching the original report's format
        # (e.g. 136.75% -> +36.75%, 95.85% -> -4.15%).
        pct = f"{(achieved - 100):+.2f}%" if achieved is not None else "N/A"
        sign  = "+" if variance >= 0 else ""
        v_str = f"{sign}{variance:.2f}"

        pdf.set_fill_color(*(_SLATE_BG if row_fill else _WHITE))
        pdf.set_x(14)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_widths[0], 8, r["label"],       border="B", align="L", fill=True)
        pdf.cell(col_widths[1], 8, f"{plan:.2f}",     border="B", align="R", fill=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[2], 8, f"{actual:.2f}",   border="B", align="R", fill=True)

        pdf.set_text_color(*(_GREEN if variance >= 0 else _RED))
        pdf.cell(col_widths[3], 8, v_str,             border="B", align="R", fill=True)

        pdf.set_text_color(*_NAVY)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[4], 8, pct,               border="B", align="R", fill=True)

        status = _status_label(achieved)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_status_color(achieved))
        pdf.cell(col_widths[5], 8, status,            border="B", align="C", fill=True)
        pdf.set_font("Helvetica", "", 9)

        pdf.ln()
        row_fill = not row_fill

    pdf.ln(6)

    # ── Achievement chart (native fpdf2 bars — no extra dependency) ────────
    if rows:
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_NAVY)
        pdf.cell(0, 6, "Achievement % by Department", ln=True)
        pdf.set_x(14)
        pdf.set_draw_color(*_ACCENT_BLUE)
        pdf.set_line_width(0.6)
        pdf.line(14, pdf.get_y(), 34, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.ln(5)

        chart_x = 60          # leave room on the left for department labels
        chart_w = 110          # width available for the bars themselves
        bar_h = 5.5
        row_gap = 3
        # Scale: 100% baseline drawn at a fixed position; bars beyond 100%
        # are capped visually at 140% of the baseline width so one runaway
        # value can't squeeze every other bar into an unreadable sliver.
        scale_max = max([max(r["achieved"] or 0, 100) for r in rows] + [100])
        scale_max = min(scale_max, 160)

        for r in rows:
            y0 = pdf.get_y()
            pdf.set_xy(14, y0)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_NAVY)
            pdf.cell(chart_x - 16, bar_h, r["label"], align="L")

            # Track (background) bar
            pdf.set_fill_color(*_SLATE_BG)
            pdf.set_draw_color(*_SLATE_BORDER)
            pdf.rect(chart_x, y0, chart_w, bar_h, style="DF")

            achieved = r["achieved"] or 0
            frac = max(0.0, min(achieved, scale_max)) / scale_max
            bar_len = chart_w * frac
            pdf.set_fill_color(*_status_color(r["achieved"]))
            if bar_len > 0:
                pdf.rect(chart_x, y0, bar_len, bar_h, style="F")

            # 100% baseline marker
            baseline_x = chart_x + (100 / scale_max) * chart_w
            pdf.set_draw_color(*_SLATE_MUTED)
            pdf.line(baseline_x, y0 - 0.5, baseline_x, y0 + bar_h + 0.5)

            label_val = f"{achieved:.1f}%" if r["achieved"] is not None else "N/A"
            pdf.set_xy(chart_x + chart_w + 2, y0)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_status_color(r["achieved"]))
            pdf.cell(16, bar_h, label_val, align="L")

            pdf.set_y(y0 + bar_h + row_gap)

        pdf.ln(2)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(
            0, 4,
            "Vertical marker = 100% of plan.  Green = On Track, Amber = Near Target, Red = Below Target.",
        )

    return bytes(pdf.output())


def _build_overall_summary_pdf(req: "OverallSummarySaveRequest") -> bytes:
    """
    Builds the President Dashboard's Overall Summary PDF from EXACTLY the
    data the frontend sent — i.e. exactly what is on screen after the
    Plant / Period Type / Year / Month-Quarter filters have been applied.
    No re-querying, re-filtering, or recalculation happens here; this
    function only renders the numbers it is given, so the exported
    report always matches the applied filters.

    Two layouts, mirroring PlantSummaryOverview.jsx exactly:
      - "All Plants" (plant_filter == "all"): plant-wise KPI cards
        (Plants On Track / Plants Needing Attention / Top Performing
        Plant), Plant-wise Comparison chart, Plant-wise Ranking table.
      - A specific plant selected (department_details present): plant-
        specific KPI cards (Departments Reporting / Total Plan vs
        Actual — NO "Plants On Track", "Plants Needing Attention", or
        "Needing Attention" cards; those stay only in the unfiltered
        All Plants view, per the frontend), Department-wise
        Performance chart/table for every department in that plant.
    """
    is_plant_view = req.plant_filter != "all" and bool(req.department_details)
    if is_plant_view:
        return _build_plant_view_pdf(req)
    return _build_all_plants_pdf(req)


def _build_all_plants_pdf(req: "OverallSummarySaveRequest") -> bytes:
    """"All Plants" layout — plant-wise KPI cards, Plant-wise Comparison
    chart, and Plant-wise Ranking & Comparison table. Unchanged from the
    original consolidated Overall Summary layout."""
    period       = _period_overall(req)
    period_display = _quarter_display(req.quarter) if req.period_type == "quarterly" and req.quarter else period
    generated_at = datetime.now().strftime("%d-%b-%Y %H:%M")
    scope_label  = "All Plants"

    plants = req.plants
    total_departments = plants[0].total_departments if plants else 0

    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.report_title = "OVERALL SUMMARY REPORT"
    pdf.report_subtitle = f"President Dashboard  |  {scope_label}  |  {period_display} {req.year}"
    pdf.add_page()

    # ── Report details bar ───────────────────────────────────────────────
    pdf.set_fill_color(*_SLATE_BG)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(14, pdf.get_y(), 182, 16, style="DF")

    meta_items = [
        ("Scope",       scope_label),
        ("Period Type", req.period_type.capitalize()),
        ("Period",      f"{period_display} {req.year}"),
        ("Generated",   generated_at),
    ]
    col_w = 45.5
    meta_y = pdf.get_y()
    for i, (label, value) in enumerate(meta_items):
        x = 14 + i * col_w
        pdf.set_xy(x + 3, meta_y + 2.5)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(col_w - 4, 4, label.upper())
        pdf.set_xy(x + 3, meta_y + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_w - 4, 5, str(value))
    pdf.set_y(meta_y + 20)

    # ── Executive summary ─────────────────────────────────────────────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Executive Summary", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(3)

    overall_txt = f"{req.overall_achieved:.1f}%" if req.overall_achieved is not None else "N/A"
    ranked = sorted(
        [p for p in plants if p.overall_achieved is not None],
        key=lambda p: p.overall_achieved, reverse=True,
    )
    best  = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    summary_lines = [
        f"This {req.period_type} Overall Summary covers {scope_label} for {period} {req.year}, "
        f"consolidating {len(plants)} plant(s). Overall achievement against plan stood at {overall_txt}, "
        f"with {req.on_track_plants} plant(s) on track and {req.attention_plants} plant(s) needing attention.",
    ]
    if best:
        summary_lines.append(f"{best.plant_name} was the top performer at {best.overall_achieved:.1f}% of plan.")
    if worst and worst is not best:
        summary_lines.append(
            f"{worst.plant_name} recorded the lowest achievement at {worst.overall_achieved:.1f}% and may need review."
        )

    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)  # #334155
    pdf.multi_cell(182, 5, "  ".join(summary_lines))
    pdf.ln(4)

    # ── KPI cards row ──────────────────────────────────────────────────────
    card_y = pdf.get_y()
    card_h = 17
    gap = 4
    card_w = (182 - gap * 3) / 4

    _kpi_card(pdf, 14, card_y, card_w, card_h,
              "Plants", str(len(plants)), _ACCENT_BLUE)
    _kpi_card(pdf, 14 + (card_w + gap) * 1, card_y, card_w, card_h,
              "Overall Achieved", overall_txt, _status_color(req.overall_achieved))
    _kpi_card(pdf, 14 + (card_w + gap) * 2, card_y, card_w, card_h,
              "Plants On Track", str(req.on_track_plants), _GREEN)
    _kpi_card(pdf, 14 + (card_w + gap) * 3, card_y, card_w, card_h,
              "Needs Attention", str(req.attention_plants), _RED if req.attention_plants else _SLATE_MUTED)

    pdf.set_y(card_y + card_h + 8)

    # ── Plant-wise table ─────────────────────────────────────────────────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Plant-wise Ranking & Comparison", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

    headers    = ["Plant", "Depts Reporting", "Plan", "Actual", "Achieved %", "On Track", "Status"]
    col_widths = [30, 30, 26, 26, 26, 22, 22]

    pdf.set_x(14)
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_draw_color(*_SLATE_BORDER)
    for h, w in zip(headers, col_widths):
        align = "L" if h == "Plant" else "C" if h == "Status" else "R"
        pdf.cell(w, 8, h, border=0, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    row_fill = False
    for p in sorted(plants, key=lambda x: (x.overall_achieved is None, -(x.overall_achieved or 0))):
        pct = f"{p.overall_achieved:.2f}%" if p.overall_achieved is not None else "N/A"
        status = _status_label(p.overall_achieved)

        pdf.set_fill_color(*(_SLATE_BG if row_fill else _WHITE))
        pdf.set_x(14)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_widths[0], 8, p.plant_name, border="B", align="L", fill=True)
        pdf.cell(col_widths[1], 8, f"{p.departments_with_data}/{p.total_departments}", border="B", align="R", fill=True)
        pdf.cell(col_widths[2], 8, f"{p.total_plan:.2f}", border="B", align="R", fill=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[3], 8, f"{p.total_actual:.2f}", border="B", align="R", fill=True)

        pdf.set_text_color(*_status_color(p.overall_achieved))
        pdf.cell(col_widths[4], 8, pct, border="B", align="R", fill=True)

        pdf.set_text_color(*_NAVY)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[5], 8, f"{p.on_track_count}/{p.total_departments}", border="B", align="R", fill=True)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_status_color(p.overall_achieved))
        pdf.cell(col_widths[6], 8, status, border="B", align="C", fill=True)
        pdf.set_font("Helvetica", "", 9)

        pdf.ln()
        row_fill = not row_fill

    pdf.ln(6)

    # ── Achievement chart (native fpdf2 bars) ───────────────────────────────
    if plants:
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_NAVY)
        pdf.cell(0, 6, "Achievement % by Plant", ln=True)
        pdf.set_x(14)
        pdf.set_draw_color(*_ACCENT_BLUE)
        pdf.set_line_width(0.6)
        pdf.line(14, pdf.get_y(), 34, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.ln(5)

        chart_x = 60
        chart_w = 110
        bar_h = 5.5
        row_gap = 3
        scale_max = max([max(p.overall_achieved or 0, 100) for p in plants] + [100])
        scale_max = min(scale_max, 160)

        for p in plants:
            y0 = pdf.get_y()
            pdf.set_xy(14, y0)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_NAVY)
            pdf.cell(chart_x - 16, bar_h, p.plant_name, align="L")

            pdf.set_fill_color(*_SLATE_BG)
            pdf.set_draw_color(*_SLATE_BORDER)
            pdf.rect(chart_x, y0, chart_w, bar_h, style="DF")

            achieved = p.overall_achieved or 0
            frac = max(0.0, min(achieved, scale_max)) / scale_max
            bar_len = chart_w * frac
            pdf.set_fill_color(*_status_color(p.overall_achieved))
            if bar_len > 0:
                pdf.rect(chart_x, y0, bar_len, bar_h, style="F")

            baseline_x = chart_x + (100 / scale_max) * chart_w
            pdf.set_draw_color(*_SLATE_MUTED)
            pdf.line(baseline_x, y0 - 0.5, baseline_x, y0 + bar_h + 0.5)

            label_val = f"{achieved:.1f}%" if p.overall_achieved is not None else "N/A"
            pdf.set_xy(chart_x + chart_w + 2, y0)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_status_color(p.overall_achieved))
            pdf.cell(16, bar_h, label_val, align="L")

            pdf.set_y(y0 + bar_h + row_gap)

        pdf.ln(2)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(
            0, 4,
            "Vertical marker = 100% of plan.  Green = On Track, Amber = Near Target, Red = Below Target.",
        )

    return bytes(pdf.output())


# Maps the frontend's statusOf() color keys ("green"/"amber"/"red"/
# "nodata") to the same colors/labels used by _status_color()/
# _status_label() elsewhere in this file, so a single-plant PDF's colors
# never disagree with the multi-plant PDF's colors for the same status.
_STATUS_KEY_COLOR = {"green": _GREEN, "amber": _AMBER, "red": _RED, "nodata": _SLATE_MUTED}
_STATUS_KEY_LABEL = {"green": "On Track", "amber": "Near Target", "red": "Below Target", "nodata": "No Data"}


def _build_plant_view_pdf(req: "OverallSummarySaveRequest") -> bytes:
    """
    Single-plant layout — mirrors PlantSummaryOverview.jsx's plant-
    specific view EXACTLY:
      - KPI cards: Plant Achieved, Departments Reporting, Total Plan vs
        Actual. Deliberately NO "Plants On Track" / "Plants Needing
        Attention" cards, and NO "Needing Attention" card either — that
        box only appears in the unfiltered President Overall Summary
        (All Plants view); once an individual plant is selected it is
        removed entirely, per requirement.
      - Executive Insights sentence phrased exactly like the frontend's
        plant-view insight text (department on-track/attention counts,
        not plant counts).
      - "Department-wise Performance" table AND chart covering every
        department in the selected plant (status, plan, actual,
        achieved %) — replacing the multi-plant table/chart entirely.
    """
    period       = _period_overall(req)
    period_display = _quarter_display(req.quarter) if req.period_type == "quarterly" and req.quarter else period
    generated_at = datetime.now().strftime("%d-%b-%Y %H:%M")

    plant = req.plants[0] if req.plants else None
    plant_name = plant.plant_name if plant else f"Plant {req.plant_filter}"
    scope_label = plant_name

    dept_rows = req.department_details or []
    total_departments = plant.total_departments if plant else len(dept_rows)
    departments_with_data = plant.departments_with_data if plant else sum(1 for d in dept_rows if d.achieved is not None)
    on_track_count = plant.on_track_count if plant else sum(1 for d in dept_rows if d.status == "green")
    attention_count = sum(1 for d in dept_rows if d.status == "red")

    total_plan   = plant.total_plan   if plant else sum(d.plan   for d in dept_rows)
    total_actual = plant.total_actual if plant else sum(d.actual for d in dept_rows)

    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.report_title = "PLANT DASHBOARD REPORT"
    pdf.report_subtitle = f"President Dashboard  |  {scope_label}  |  {period_display} {req.year}"
    pdf.add_page()

    # ── Report details bar ───────────────────────────────────────────────
    pdf.set_fill_color(*_SLATE_BG)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(14, pdf.get_y(), 182, 16, style="DF")

    meta_items = [
        ("Plant",       scope_label),
        ("Period Type", req.period_type.capitalize()),
        ("Period",      f"{period_display} {req.year}"),
        ("Generated",   generated_at),
    ]
    col_w = 45.5
    meta_y = pdf.get_y()
    for i, (label, value) in enumerate(meta_items):
        x = 14 + i * col_w
        pdf.set_xy(x + 3, meta_y + 2.5)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(col_w - 4, 4, label.upper())
        pdf.set_xy(x + 3, meta_y + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_w - 4, 5, str(value))
    pdf.set_y(meta_y + 20)

    # ── Executive summary — phrased exactly like the frontend's ─────────────
    # plant-view Executive Insights text (department counts, not plants).
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Executive Summary", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(3)

    overall_txt = f"{req.overall_achieved:.1f}%" if req.overall_achieved is not None else "N/A"
    summary = (
        f"{plant_name} performance for {period} {req.year} stands at {overall_txt} of plan. "
        f"The plant has {on_track_count} department(s) on track and {attention_count} department(s) needing attention."
    )
    if attention_count > 0:
        summary += " The underperforming departments should be prioritized for improvement initiatives."

    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)  # #334155
    pdf.multi_cell(182, 5, summary)
    pdf.ln(4)

    # ── KPI cards row — matches the frontend's plant-view cards:
    # Plant Achieved / Departments Reporting / Total Plan vs Actual.
    # NO "Needing Attention" card here — per requirement, that box only
    # appears in the unfiltered President Overall Summary (All Plants
    # view, as "Plants Needing Attention"), not when an individual plant
    # is selected.
    card_y = pdf.get_y()
    card_h = 17
    gap = 5
    card_w = (182 - gap * 2) / 3

    _kpi_card(pdf, 14, card_y, card_w, card_h,
              "Plant Achieved", overall_txt, _status_color(req.overall_achieved))
    _kpi_card(pdf, 14 + (card_w + gap) * 1, card_y, card_w, card_h,
              "Departments Reporting", f"{departments_with_data}/{total_departments}", _ACCENT_BLUE)
    variance_total = total_actual - total_plan
    _kpi_card(pdf, 14 + (card_w + gap) * 2, card_y, card_w, card_h,
              "Plan vs Actual", f"{total_actual:,.0f} / {total_plan:,.0f}", (139, 92, 246))  # #8b5cf6, matches frontend card accent

    pdf.set_y(card_y + card_h + 8)

    # ── Department-wise Performance table — replaces the plant-wise table
    # entirely in this view, covering every department in the plant. ────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, f"Department-wise Performance - {plant_name}", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(4)

    headers    = ["Department", "Plan", "Actual", "Variance", "Achieved %", "Status"]
    col_widths = [42, 24, 24, 26, 28, 38]

    pdf.set_x(14)
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_draw_color(*_SLATE_BORDER)
    for h, w in zip(headers, col_widths):
        align = "L" if h == "Department" else "C" if h == "Status" else "R"
        pdf.cell(w, 8, h, border=0, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    row_fill = False
    for d in dept_rows:
        variance = d.actual - d.plan
        pct = f"{d.achieved:.2f}%" if d.achieved is not None else "N/A"
        sign  = "+" if variance >= 0 else ""
        v_str = f"{sign}{variance:.2f}"
        status_label = _STATUS_KEY_LABEL.get(d.status, "No Data")
        status_color = _STATUS_KEY_COLOR.get(d.status, _SLATE_MUTED)

        pdf.set_fill_color(*(_SLATE_BG if row_fill else _WHITE))
        pdf.set_x(14)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_widths[0], 8, d.label,        border="B", align="L", fill=True)
        pdf.cell(col_widths[1], 8, f"{d.plan:.2f}",  border="B", align="R", fill=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[2], 8, f"{d.actual:.2f}", border="B", align="R", fill=True)

        pdf.set_text_color(*(_GREEN if variance >= 0 else _RED))
        pdf.cell(col_widths[3], 8, v_str,            border="B", align="R", fill=True)

        pdf.set_text_color(*_NAVY)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[4], 8, pct,              border="B", align="R", fill=True)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*status_color)
        pdf.cell(col_widths[5], 8, status_label,     border="B", align="C", fill=True)
        pdf.set_font("Helvetica", "", 9)

        pdf.ln()
        row_fill = not row_fill

    pdf.ln(6)

    # ── Department-wise Performance chart (native fpdf2 bars) ──────────────
    # Mirrors the frontend's "Department-wise Performance" bar chart for
    # the selected plant.
    if dept_rows:
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_NAVY)
        pdf.cell(0, 6, f"Department-wise Performance Chart - {plant_name}", ln=True)
        pdf.set_x(14)
        pdf.set_draw_color(*_ACCENT_BLUE)
        pdf.set_line_width(0.6)
        pdf.line(14, pdf.get_y(), 34, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.ln(5)

        chart_x = 60
        chart_w = 110
        bar_h = 5.5
        row_gap = 3
        scale_max = max([max(d.achieved or 0, 100) for d in dept_rows] + [100])
        scale_max = min(scale_max, 160)

        for d in dept_rows:
            y0 = pdf.get_y()
            pdf.set_xy(14, y0)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_NAVY)
            pdf.cell(chart_x - 16, bar_h, d.label, align="L")

            pdf.set_fill_color(*_SLATE_BG)
            pdf.set_draw_color(*_SLATE_BORDER)
            pdf.rect(chart_x, y0, chart_w, bar_h, style="DF")

            achieved = d.achieved or 0
            frac = max(0.0, min(achieved, scale_max)) / scale_max
            bar_len = chart_w * frac
            status_color = _STATUS_KEY_COLOR.get(d.status, _SLATE_MUTED)
            pdf.set_fill_color(*status_color)
            if bar_len > 0:
                pdf.rect(chart_x, y0, bar_len, bar_h, style="F")

            baseline_x = chart_x + (100 / scale_max) * chart_w
            pdf.set_draw_color(*_SLATE_MUTED)
            pdf.line(baseline_x, y0 - 0.5, baseline_x, y0 + bar_h + 0.5)

            label_val = f"{achieved:.1f}%" if d.achieved is not None else "N/A"
            pdf.set_xy(chart_x + chart_w + 2, y0)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*status_color)
            pdf.cell(16, bar_h, label_val, align="L")

            pdf.set_y(y0 + bar_h + row_gap)

        pdf.ln(2)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(
            0, 4,
            "Vertical marker = 100% of plan.  Green = On Track, Amber = Near Target, Red = Below Target.",
        )

    return bytes(pdf.output())


def _email_generated_report(req: ReportSaveRequest, pdf_bytes: bytes, filename: str) -> None:
    """
    Emails the already-generated PDF as an attachment. Called AFTER the
    report has been built and saved to disk — never before, and never in
    a way that can affect report generation itself. Any failure here is
    logged and swallowed; it must never propagate to the caller.
    """
    period = _period(req)
    period_display = _quarter_display(req.quarter) if req.report_type == "Quarterly" and req.quarter else period
    if req.report_type == "Monthly":
        subject = f"Monthly DigitalDRM Report – {period_display} {req.year}"
    elif req.report_type == "Quarterly":
        subject = f"Quarterly DigitalDRM Report – {period_display} {req.year}"
    else:
        subject = f"Yearly DigitalDRM Report – {req.year}"

    body = (
        f"Hello,\n\n"
        f"The {req.report_type} DigitalDRM report for Plant {req.plant_id} "
        f"({period_display} {req.year}) has been generated successfully. "
        f"The report is attached as a PDF.\n\n"
        f"This is an automated notification from the DigitalDRM system.\n"
    )

    # Monthly/Quarterly/Yearly report recipient: the President — this
    # used to be a separate "Combined Report Recipient" role, but there
    # is only one President (per plant, or the global one for All
    # Plants), so it now uses the same "president" type every other
    # plant-wide/president-facing email already uses. Falls back to the
    # global (plant_id=None) President row if this plant has no
    # plant-specific President configured.
    recipients = _resolve_recipient("president", department=None, plant_id=req.plant_id)
    if not recipients:
        logger.error(
            "[REPORT EMAIL] ❌ No President recipient configured for plant=%s — "
            "add one in Admin Dashboard > Email Services. Email NOT sent.",
            req.plant_id,
        )
        return

    try:
        sent = send_email_with_attachment(
            to_email=recipients,
            subject=subject,
            body=body,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
        )
        if sent:
            logger.info(
                "[REPORT EMAIL] ✅ Report emailed to %s | %s", recipients, filename
            )
        else:
            logger.error(
                "[REPORT EMAIL] ❌ Failed to email report to %s | %s (see email_service logs above)",
                recipients, filename,
            )
    except Exception as exc:
        # Belt and suspenders: send_email_with_attachment already never
        # raises, but report generation must be bulletproof against any
        # future change to that guarantee too.
        logger.error("[REPORT EMAIL] ❌ Unexpected error emailing report: %s", exc, exc_info=True)


def generate_and_save_report(req: ReportSaveRequest) -> dict:
    """
    Core logic: build the PDF, save it to disk, then email it — in that
    exact order, so the report is always generated first and the email
    is a pure side effect afterward. Used by BOTH the manual
    POST /report-save/save endpoint AND the scheduled report job in
    app/scheduler.py, so behavior (including the email step) is
    guaranteed identical for manual and scheduled report generation.
    """
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[REPORT SAVE] Cannot create directory: %s", exc)
        return {"status": "error", "message": f"Cannot create directory: {exc}"}

    filename = f"{_stem(req)}.pdf"
    filepath = REPORTS_DIR / filename

    try:
        pdf_bytes = _build_pdf(req)
        filepath.write_bytes(pdf_bytes)
        logger.info("[REPORT SAVE] PDF saved: %s (%d bytes)", filepath, len(pdf_bytes))
    except ImportError:
        msg = (
            "fpdf2 is not installed. "
            "Run: venv\\Scripts\\pip install fpdf2"
        )
        logger.error("[REPORT SAVE] %s", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        logger.error("[REPORT SAVE] Failed: %s", exc, exc_info=True)
        return {"status": "error", "message": str(exc)}

    # Report is generated and saved successfully — now email it. Any
    # failure here is logged inside _email_generated_report and never
    # raised, so it cannot affect the result returned below.
    _email_generated_report(req, pdf_bytes, filename)

    return {
        "status":   "ok",
        "filename": filename,
        "path":     str(filepath),
        "format":   "pdf",
    }


def _build_department_pdf(
    dept_key: str, dept_data: Dict[str, Any], plant_id: int,
    report_type: str, year: int, month: Optional[int], quarter: Optional[int],
) -> bytes:
    """
    Builds a single-department report PDF — Plan, Actual, Variance,
    Achieved % and status for exactly one department, for one plant and
    one period. Deliberately simple/focused (one department's numbers
    only) since this is what gets emailed straight to that department's
    own Staff Incharge, not the full multi-department report.
    """
    dept_label   = DEPARTMENT_RECIPIENTS[dept_key]["label"]
    period       = _period_dept(report_type, year, month, quarter)
    period_display = _quarter_display(quarter) if report_type == "Quarterly" and quarter else period
    generated_at = datetime.now().strftime("%d-%b-%Y %H:%M")

    plan     = dept_data.get("plan") or 0
    actual   = dept_data.get("actual") or 0
    variance = dept_data.get("variance", actual - plan)
    achieved = (actual / plan * 100) if plan else None

    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.report_title = f"{dept_label.upper()} REPORT"
    pdf.report_subtitle = f"Plant {plant_id}  |  {report_type}  |  {period_display} {year}"
    pdf.add_page()

    # ── Report details bar ───────────────────────────────────────────────
    pdf.set_fill_color(*_SLATE_BG)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(14, pdf.get_y(), 182, 16, style="DF")

    meta_items = [
        ("Department", dept_label),
        ("Plant",      str(plant_id)),
        ("Period",     f"{period_display} {year}"),
        ("Generated",  generated_at),
    ]
    col_w = 45.5
    meta_y = pdf.get_y()
    for i, (label, value) in enumerate(meta_items):
        x = 14 + i * col_w
        pdf.set_xy(x + 3, meta_y + 2.5)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(col_w - 4, 4, label.upper())
        pdf.set_xy(x + 3, meta_y + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_w - 4, 5, str(value))
    pdf.set_y(meta_y + 20)

    # ── Executive summary ─────────────────────────────────────────────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Summary", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(3)

    achieved_txt = f"{achieved:.1f}%" if achieved is not None else "N/A"
    summary = (
        f"For {period} {year}, {dept_label} recorded a plan of {plan:,.2f} against an actual "
        f"of {actual:,.2f}, achieving {achieved_txt} of plan "
        f"({_status_label(achieved)})."
    )
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(182, 5, summary)
    pdf.ln(4)

    # ── KPI cards ────────────────────────────────────────────────────────
    card_y = pdf.get_y()
    card_h = 20
    gap = 5
    card_w = (182 - gap * 3) / 4

    _kpi_card(pdf, 14, card_y, card_w, card_h, "Plan", f"{plan:,.2f}", _ACCENT_BLUE)
    _kpi_card(pdf, 14 + (card_w + gap) * 1, card_y, card_w, card_h, "Actual", f"{actual:,.2f}", _NAVY)
    _kpi_card(pdf, 14 + (card_w + gap) * 2, card_y, card_w, card_h, "Variance",
              f"{'+' if variance >= 0 else ''}{variance:,.2f}", _GREEN if variance >= 0 else _RED)
    _kpi_card(pdf, 14 + (card_w + gap) * 3, card_y, card_w, card_h, "Achieved %", achieved_txt, _status_color(achieved))

    pdf.set_y(card_y + card_h + 10)

    # ── Status banner ────────────────────────────────────────────────────
    status = _status_label(achieved)
    color = _status_color(achieved)
    pdf.set_x(14)
    pdf.set_fill_color(*color)
    pdf.rect(14, pdf.get_y(), 182, 12, style="F")
    pdf.set_xy(14, pdf.get_y() + 3.5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_WHITE)
    pdf.cell(182, 5, f"Status: {status}", align="C")

    return bytes(pdf.output())


def _email_department_report(
    dept_key: str, plant_id: int, report_type: str,
    year: int, month: Optional[int], quarter: Optional[int],
    pdf_bytes: bytes, filename: str,
) -> None:
    """
    Emails the already-generated department PDF to that department's own
    Staff Incharge. Called AFTER the report has been built and saved to
    disk. Any failure here is logged and swallowed — it must never
    propagate and never block other departments' reports from being
    generated/emailed.
    """
    dept = DEPARTMENT_RECIPIENTS[dept_key]
    dept_label = dept["label"]
    recipients = _resolve_recipient("staff_incharge", department=dept_key, plant_id=plant_id)
    period = _period_dept(report_type, year, month, quarter)
    period_display = _quarter_display(quarter) if report_type == "Quarterly" and quarter else period

    if not recipients:
        logger.error(
            "[DEPT REPORT EMAIL] ❌ No Staff Incharge recipient configured for dept=%s plant=%s — "
            "add one in Admin Dashboard > Email Services. Email NOT sent.",
            dept_key, plant_id,
        )
        return

    subject = f"{report_type} {dept_label} Report – Plant {plant_id} – {period_display} {year}"
    body = (
        f"Hello,\n\n"
        f"The {report_type} {dept_label} report for Plant {plant_id} ({period_display} {year}) "
        f"has been generated automatically and is attached as a PDF.\n\n"
        f"This is an automated notification from the DigitalDRM system.\n"
    )

    try:
        sent = send_email_with_attachment(
            to_email=recipients,
            subject=subject,
            body=body,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
        )
        if sent:
            logger.info(
                "[DEPT REPORT EMAIL] ✅ %s report emailed to %s | %s",
                dept_label, recipients, filename,
            )
        else:
            logger.error(
                "[DEPT REPORT EMAIL] ❌ Failed to email %s report to %s | %s",
                dept_label, recipients, filename,
            )
    except Exception as exc:
        logger.error("[DEPT REPORT EMAIL] ❌ Unexpected error emailing %s report: %s", dept_label, exc, exc_info=True)


def generate_and_save_department_report(
    db, dept_key: str, plant_id: int, report_type: str,
    year: int, month: Optional[int] = None, quarter: Optional[int] = None,
) -> dict:
    """
    Generates ONE department's report for ONE period, saves it to
    REPORTS_DIR, and emails it to that department's Staff Incharge — in
    that order. Idempotent per (plant, department, period): the filename
    is fully deterministic (see _stem_department), so if that exact file
    already exists on disk, generation is skipped entirely — nothing is
    rebuilt and nothing is re-emailed — even if this function is called
    again later the same day (e.g. the app restarts, or the scheduler
    fires more than once). This is what guarantees each report is
    produced only once per reporting period.
    """
    from app.services.report_service import (
        generate_monthly_report, generate_quarterly_report, generate_yearly_report,
    )

    if dept_key not in DEPARTMENT_RECIPIENTS:
        return {"status": "error", "message": f"Unknown department key: {dept_key}"}

    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[DEPT REPORT SAVE] Cannot create directory: %s", exc)
        return {"status": "error", "message": f"Cannot create directory: {exc}"}

    filename = f"{_stem_department(dept_key, plant_id, report_type, year, month, quarter)}.pdf"
    filepath = REPORTS_DIR / filename

    # ── Idempotency guard: already generated for this exact period? ────────
    if filepath.exists():
        logger.info(
            "[DEPT REPORT SAVE] Skipped — already generated for this period: %s", filepath,
        )
        return {"status": "skipped", "filename": filename, "path": str(filepath), "reason": "already generated"}

    try:
        if report_type == "Monthly":
            report_data = generate_monthly_report(db, plant_id, year, month)
        elif report_type == "Quarterly":
            report_data = generate_quarterly_report(db, plant_id, year, quarter)
        else:
            report_data = generate_yearly_report(db, plant_id, year)

        dept_data = report_data.get(dept_key, {"plan": 0, "actual": 0, "variance": 0})
        pdf_bytes = _build_department_pdf(dept_key, dept_data, plant_id, report_type, year, month, quarter)
        filepath.write_bytes(pdf_bytes)
        logger.info("[DEPT REPORT SAVE] PDF saved: %s (%d bytes)", filepath, len(pdf_bytes))
    except ImportError:
        msg = "fpdf2 is not installed. Run: venv\\Scripts\\pip install fpdf2"
        logger.error("[DEPT REPORT SAVE] %s", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        logger.error("[DEPT REPORT SAVE] Failed for dept=%s: %s", dept_key, exc, exc_info=True)
        return {"status": "error", "message": str(exc)}

    _email_department_report(dept_key, plant_id, report_type, year, month, quarter, pdf_bytes, filename)

    return {"status": "ok", "filename": filename, "path": str(filepath), "format": "pdf"}


def generate_all_department_reports_for_period(
    db, plant_id: int, report_type: str,
    year: int, month: Optional[int] = None, quarter: Optional[int] = None,
) -> List[dict]:
    """
    Runs generate_and_save_department_report() for every department for
    one plant/period — this is what app/scheduler.py calls on the 1st of
    every month/quarter/year. A failure generating one department's
    report is logged and never stops the others from being generated.
    """
    results = []
    for dept_key in DEPARTMENT_RECIPIENTS:
        try:
            result = generate_and_save_department_report(db, dept_key, plant_id, report_type, year, month, quarter)
        except Exception as exc:
            logger.error(
                "[DEPT REPORT SAVE] Unexpected error for dept=%s plant=%s %s %s: %s",
                dept_key, plant_id, report_type, year, exc, exc_info=True,
            )
            result = {"status": "error", "message": str(exc)}
        results.append({"department": dept_key, **result})
    return results


def _email_overall_summary_report(
    req: "OverallSummarySaveRequest", pdf_bytes: bytes, filename: str,
    recipient_override: Optional[List[str]] = None,
) -> None:
    """
    Emails the already-generated Overall Summary PDF to the President
    Dashboard's fixed recipient. Called AFTER the report has been built
    and saved to disk. Any failure here is logged and swallowed; it must
    never propagate to the caller.

    `recipient_override`, if given, is used INSTEAD of the DB-configured
    Admin Dashboard > Email Services recipient — for callers (like the
    scheduled daily all-plants report) that need to send to a specific
    fixed address regardless of whatever's configured there.
    """
    period = _period_overall(req)
    period_display = _quarter_display(req.quarter) if req.period_type == "quarterly" and req.quarter else period
    is_plant_view = req.plant_filter != "all" and bool(req.department_details)

    if is_plant_view:
        plant_name = req.plants[0].plant_name if req.plants else f"Plant {req.plant_filter}"
        subject = f"Plant Dashboard Report – {plant_name} – {period_display} {req.year}"
        body = (
            f"Hello,\n\n"
            f"The Plant Dashboard report from the President Dashboard has been generated "
            f"successfully for {plant_name}, {req.period_type} period {period_display} {req.year}. "
            f"The report covers every department in this plant and is attached as a PDF, "
            f"reflecting exactly the filters that were applied when it was generated.\n\n"
            f"This is an automated notification from the DigitalDRM system.\n"
        )
    else:
        scope_label = "All Plants"
        subject = f"Overall Summary Report – {scope_label} – {period_display} {req.year}"
        body = (
            f"Hello,\n\n"
            f"The Overall Summary report from the President Dashboard has been generated "
            f"successfully for {scope_label}, {req.period_type} period {period_display} {req.year}. "
            f"The report is attached as a PDF and reflects exactly the filters that were "
            f"applied when it was generated.\n\n"
            f"This is an automated notification from the DigitalDRM system.\n"
        )

    # Plant-specific view -> try that plant's configured President first,
    # falling back to the global (plant_id = NULL) President row. "All
    # Plants" view has no single plant_id, so it always uses the global row.
    overall_plant_id = req.plants[0].plant_id if (is_plant_view and req.plants) else None
    recipients = recipient_override or _resolve_recipient("overall_summary_recipient", department=None, plant_id=overall_plant_id)
    if not recipients:
        logger.error(
            "[OVERALL SUMMARY EMAIL] ❌ No Overall Summary recipient configured — "
            "add one in Admin Dashboard > Email Services. Email NOT sent."
        )
        return

    try:
        sent = send_email_with_attachment(
            to_email=recipients,
            subject=subject,
            body=body,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
        )
        if sent:
            logger.info(
                "[OVERALL SUMMARY EMAIL] ✅ Report emailed to %s | %s",
                recipients, filename,
            )
        else:
            logger.error(
                "[OVERALL SUMMARY EMAIL] ❌ Failed to email report to %s | %s (see email_service logs above)",
                recipients, filename,
            )
    except Exception as exc:
        logger.error("[OVERALL SUMMARY EMAIL] ❌ Unexpected error emailing report: %s", exc, exc_info=True)


def generate_and_save_overall_summary(
    req: "OverallSummarySaveRequest", recipient_override: Optional[List[str]] = None,
) -> dict:
    """
    Core logic for the President Dashboard's "Generate Report" button:
    build the Overall Summary PDF from exactly the filtered data sent by
    the frontend, save it to the same DigitalDRM/Reports folder used by
    the per-plant reports, then email it to the fixed Overall Summary
    recipient — in that exact order, mirroring generate_and_save_report().

    `recipient_override`, if given, sends to that address instead of the
    DB-configured recipient — used by the scheduled daily all-plants
    report (see run_daily_all_plants_report() below).
    """
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[OVERALL SUMMARY SAVE] Cannot create directory: %s", exc)
        return {"status": "error", "message": f"Cannot create directory: {exc}"}

    filename = f"{_stem_overall(req)}.pdf"
    filepath = REPORTS_DIR / filename

    try:
        pdf_bytes = _build_overall_summary_pdf(req)
        filepath.write_bytes(pdf_bytes)
        logger.info("[OVERALL SUMMARY SAVE] PDF saved: %s (%d bytes)", filepath, len(pdf_bytes))
    except ImportError:
        msg = "fpdf2 is not installed. Run: venv\\Scripts\\pip install fpdf2"
        logger.error("[OVERALL SUMMARY SAVE] %s", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        logger.error("[OVERALL SUMMARY SAVE] Failed: %s", exc, exc_info=True)
        return {"status": "error", "message": str(exc)}

    _email_overall_summary_report(req, pdf_bytes, filename, recipient_override=recipient_override)

    return {
        "status":   "ok",
        "filename": filename,
        "path":     str(filepath),
        "format":   "pdf",
        "emailed_to": "configured recipients (see Admin Dashboard > Email Services)",
    }


# ── Scheduled daily "all plants" Overall Summary report ────────────────────────
#
# A separate, simpler path from the President Dashboard's "Generate
# Report" button above: this is called once a day by app/scheduler.py,
# builds the current month-to-date Overall Summary across every plant
# directly from the database (no frontend round trip), and always sends
# it to one fixed address rather than whatever's configured in Admin
# Dashboard > Email Services for the manual button.

ALL_PLANT_IDS = [2, 3, 4, 5, 6]
PLANT_NAMES = {pid: f"Plant {pid}" for pid in ALL_PLANT_IDS}


def _summarize_plant_report_data(plant_id: int, report_data: dict) -> PlantSummaryRow:
    """Same plan/actual/achieved%/on-track aggregation PlantSummaryOverview.jsx's
    summarizePlant() does on the frontend, done here server-side so the
    scheduled job doesn't need a frontend round trip. Mirrors that logic
    exactly (sum plan/actual across every department that has data)."""
    total_plan = 0.0
    total_actual = 0.0
    departments_with_data = 0
    on_track_count = 0
    for _, key in DEPTS:
        d = report_data.get(key)
        if not d:
            continue
        plan = d.get("plan") or 0
        actual = d.get("actual") or 0
        if plan == 0 and actual == 0:
            continue
        departments_with_data += 1
        total_plan += plan
        total_actual += actual
        achieved = (actual / plan * 100) if plan else None
        if achieved is not None and achieved >= 100:
            on_track_count += 1

    overall_achieved = (total_actual / total_plan * 100) if total_plan else None
    return PlantSummaryRow(
        plant_id=plant_id,
        plant_name=PLANT_NAMES.get(plant_id, f"Plant {plant_id}"),
        total_plan=total_plan,
        total_actual=total_actual,
        overall_achieved=overall_achieved,
        departments_with_data=departments_with_data,
        on_track_count=on_track_count,
        total_departments=len(DEPTS),
    )


def build_all_plants_overall_summary_request(db, year: int, month: int) -> "OverallSummarySaveRequest":
    """Builds the same OverallSummarySaveRequest shape the President
    Dashboard's frontend sends when 'All Plants' is selected — except
    computed directly from the database for every plant in
    ALL_PLANT_IDS, for the given month, instead of from whatever's
    currently on screen."""
    from app.services.report_service import generate_monthly_report

    plants = []
    for plant_id in ALL_PLANT_IDS:
        report_data = generate_monthly_report(db, plant_id, year, month)
        plants.append(_summarize_plant_report_data(plant_id, report_data))

    total_plan = sum(p.total_plan for p in plants)
    total_actual = sum(p.total_actual for p in plants)
    overall_achieved = (total_actual / total_plan * 100) if total_plan else None
    on_track_plants = sum(1 for p in plants if p.overall_achieved is not None and p.overall_achieved >= 100)
    attention_plants = sum(1 for p in plants if p.overall_achieved is not None and p.overall_achieved < 80)

    return OverallSummarySaveRequest(
        period_type="monthly",
        year=year,
        month=month,
        plant_filter="all",
        plants=plants,
        overall_achieved=overall_achieved,
        on_track_plants=on_track_plants,
        attention_plants=attention_plants,
    )


def run_daily_all_plants_report(db, recipient_email: str) -> dict:
    """
    Generates today's month-to-date Overall Summary PDF across every
    plant in ALL_PLANT_IDS and emails it to `recipient_email` — called
    daily by app/scheduler.py (see _run_daily_all_plants_report_job()).
    Saves to the same Reports folder as every other report; the filename
    includes today's date so each day's run produces its own file rather
    than overwriting the previous day's.
    """
    from datetime import date
    today = date.today()

    req = build_all_plants_overall_summary_request(db, today.year, today.month)

    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[DAILY ALL-PLANTS REPORT] Cannot create directory: %s", exc)
        return {"status": "error", "message": f"Cannot create directory: {exc}"}

    filename = f"AllPlants_Daily_{today.isoformat()}.pdf"
    filepath = REPORTS_DIR / filename

    try:
        pdf_bytes = _build_overall_summary_pdf(req)
        filepath.write_bytes(pdf_bytes)
        logger.info("[DAILY ALL-PLANTS REPORT] PDF saved: %s (%d bytes)", filepath, len(pdf_bytes))
    except ImportError:
        msg = "fpdf2 is not installed. Run: venv\\Scripts\\pip install fpdf2"
        logger.error("[DAILY ALL-PLANTS REPORT] %s", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        logger.error("[DAILY ALL-PLANTS REPORT] Failed: %s", exc, exc_info=True)
        return {"status": "error", "message": str(exc)}

    _email_overall_summary_report(req, pdf_bytes, filename, recipient_override=[recipient_email])

    return {"status": "ok", "filename": filename, "path": str(filepath), "emailed_to": recipient_email}


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/overall-summary")
def save_overall_summary_report(req: OverallSummarySaveRequest):
    """
    Generates the President Dashboard's Overall Summary as a real PDF —
    built EXACTLY from the filtered data the frontend sends (i.e. exactly
    what's on screen after the Plant / Period Type / Year / Month-Quarter
    filters are applied), saves it to
    D:\\Digitalization_DigitalDRM2.o\\DigitalDRM\\Reports\\, and emails it
    to r.keerthana-contr@ranegroup.com.

    - plant_filter == "all": renders the multi-plant "Overall Summary"
      layout (Plant-wise Comparison / Ranking).
    - plant_filter is a specific plant AND department_details is sent:
      renders the plant-specific "Plant Dashboard" layout (Department-
      wise Performance for every department in that plant, with no
      "Plants On Track" / "Plants Needing Attention" cards).
    """
    result = generate_and_save_overall_summary(req)
    if result.get("status") == "error":
        return JSONResponse(status_code=500, content=result)
    return result


@router.post("/save")
def save_report(req: ReportSaveRequest):
    """
    Generates a real PDF and saves it directly to
    D:\\c103191-Data\\DigitalDRM\\Reports\\  — no user interaction required.
    Also emails the generated report (see generate_and_save_report()).
    """
    result = generate_and_save_report(req)
    if result.get("status") == "error":
        return JSONResponse(status_code=500, content=result)
    return result