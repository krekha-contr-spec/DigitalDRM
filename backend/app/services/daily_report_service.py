"""
daily_report_service.py
------------------------
Daily Report generation for each plant — a NEW report type, additive to
the existing Monthly / Quarterly / Yearly reports (report_service.py /
report_save_routes.py), which are left completely untouched.

A Daily Report covers exactly ONE calendar date for ONE plant and shows
only 5 departments:
    Production, Manpower, OVC, Product Value, Despatch
(Sales and Rejection PPM, which appear in the 7-department Monthly/
Quarterly/Yearly reports, are intentionally excluded here.)

This module:
  1. Aggregates that single day's Plan / Actual per department
     (generate_daily_report()).
  2. Renders a professional branded PDF — company logo, plant name,
     report date & time, report type, overall summary, a Plan/Actual/
     Variance/Achievement% table, and a Plan-vs-Actual bar chart per
     department (_build_daily_pdf()).
  3. Saves the PDF to the same Reports folder as every other report and
     emails it via SMTP to that plant's configured recipients
     (generate_and_save_daily_report()).
  4. Provides a "run for every plant" helper for the scheduler / the
     "generate all" API endpoint (generate_daily_reports_for_all_plants()).
"""

import logging
from datetime import datetime, date as date_cls
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    DailyProduction,
    DailyManpower,
    OVCElement,
    CustomerDespatch,
    Plant,
)
from app.services.email_service import send_email_with_attachment
from app.services import email_recipient_service as recipients_svc

logger = logging.getLogger("digitaldrm.daily_report")

# Same on-disk destination every other report already uses.
REPORTS_DIR = Path(r"D:\Digitalization_DigitalDRM2.o\DigitalDRM\Reports")

REJECTION_PPM_TYPE = "Rejection PPM"
PRODUCT_VALUE_TYPE = "Product Value"

ALL_PLANT_IDS = [2, 3, 4, 5, 6]

# Exactly the 5 departments the Daily Report should show, in display order.
DAILY_DEPTS = [
    ("Production",     "production"),
    ("Manpower",       "manpower"),
    ("OVC",             "ovc"),
    ("Product Value",  "product_value"),
    ("Despatch",       "despatch"),
]

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "Rane_Group_Logo.jpg"


def _plant_name(db: Session, plant_id: int) -> str:
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    return plant.name if plant else f"Plant {plant_id}"


def _resolve_recipients(plant_id: int) -> List[str]:
    """
    Resolves the Daily Report's recipients from the same email_recipients
    table (Admin Dashboard > Email Services) every other automated email
    uses, under the dedicated "daily_report_recipient" type — this is
    that plant's Staff Incharge for Daily Report purposes specifically
    (plant-wide, department=None; NOT the same row as the per-department
    "staff_incharge" reminder recipients).

    Deliberately does NOT fall back to "president" (the Monthly/
    Quarterly/Yearly report recipient) — a plant with no
    daily_report_recipient configured yet must stay silent (no email
    sent) rather than accidentally emailing whoever the President's
    address is. See run_daily_report_recipient_seed() in app/database.py
    for the initial seed (P5 = adprisha12@gmail.com; P2/P3/P4/P6 left as
    an empty placeholder row for an admin to fill in later via Email
    Services).
    """
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        return recipients_svc.get_recipients(
            db, "daily_report_recipient", department=None, plant_id=plant_id
        )
    finally:
        db.close()


def _dept(row, key="variance") -> Dict[str, float]:
    plan = row.plan or 0
    actual = row.actual or 0
    return {"plan": plan, "actual": actual, "variance": actual - plan}


# ── Daily data aggregation ──────────────────────────────────────────────────

def generate_daily_report(db: Session, plant_id: int, target_date: date_cls) -> Dict[str, Any]:
    """
    Aggregates exactly ONE date's Plan/Actual for the 5 Daily-Report
    departments. Purely additive — does not call, modify, or share
    mutable state with report_service.py's Monthly/Quarterly/Yearly
    functions.
    """
    year, month, day = target_date.year, target_date.month, target_date.day

    production = db.query(
        func.sum(DailyProduction.plan).label("plan"),
        func.sum(DailyProduction.actual).label("actual"),
    ).filter(
        DailyProduction.plant_id == plant_id,
        DailyProduction.date == target_date,
    ).first()

    manpower = db.query(
        func.sum(DailyManpower.plan).label("plan"),
        func.sum(DailyManpower.actual).label("actual"),
    ).filter(
        DailyManpower.plant_id == plant_id,
        DailyManpower.date == target_date,
    ).first()

    ovc = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type.notin_([REJECTION_PPM_TYPE, PRODUCT_VALUE_TYPE]),
        OVCElement.date == target_date,
    ).first()

    product_value = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == PRODUCT_VALUE_TYPE,
        OVCElement.date == target_date,
    ).first()

    despatch = db.query(
        func.sum(CustomerDespatch.month_plan).label("plan"),
        func.sum(CustomerDespatch.mtd_actual).label("actual"),
    ).filter(
        CustomerDespatch.plant_id == plant_id,
        CustomerDespatch.date == target_date,
    ).first()

    return {
        "report_type":   "Daily",
        "date":          target_date.isoformat(),
        "production":    _dept(production),
        "manpower":      _dept(manpower),
        "ovc":           _dept(ovc),
        "product_value": _dept(product_value),
        "despatch":      _dept(despatch),
    }


# ── Brand palette — identical to the Monthly/Quarterly/Yearly PDFs so the
# Daily Report looks like part of the same report family. ──────────────────

_NAVY         = (15, 23, 42)
_SLATE_BG     = (248, 250, 252)
_SLATE_BORDER = (226, 232, 240)
_SLATE_MUTED  = (100, 116, 139)
_ACCENT_BLUE  = (37, 99, 235)
_GREEN        = (22, 163, 74)
_AMBER        = (217, 119, 6)
_RED          = (220, 38, 38)
_WHITE        = (255, 255, 255)

_THRESHOLD_ON_TRACK    = 100
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


class _DailyReportPDF:
    """fpdf2 wrapper with a branded header (company logo + plant name +
    report type) and footer, drawn automatically on every page."""

    def __new__(cls, *args, **kwargs):
        from fpdf import FPDF

        class _Inner(FPDF):
            report_title = "DAILY REPORT"
            report_subtitle = ""

            def header(self):
                self.set_fill_color(*_NAVY)
                self.rect(0, 0, 210, 24, style="F")

                # Company logo, top-left, inside the navy band.
                if LOGO_PATH.exists():
                    try:
                        self.image(str(LOGO_PATH), x=14, y=4, h=15)
                        text_x = 32
                    except Exception:
                        text_x = 14
                else:
                    text_x = 14

                self.set_text_color(*_WHITE)
                self.set_font("Helvetica", "B", 13)
                self.set_xy(text_x, 5)
                self.cell(0, 7, "RANE MADRAS LTD", ln=True)

                self.set_font("Helvetica", "", 8)
                self.set_text_color(191, 219, 254)
                self.set_xy(text_x, 13)
                self.cell(0, 5, self.report_subtitle, ln=True)

                self.set_font("Helvetica", "B", 10)
                self.set_text_color(*_WHITE)
                self.set_xy(0, 8)
                self.cell(196, 6, self.report_title, align="R")

                self.set_fill_color(*_ACCENT_BLUE)
                self.rect(0, 24, 210, 1.2, style="F")

                self.set_text_color(*_NAVY)
                self.set_y(32)

            def footer(self):
                self.set_y(-15)
                self.set_draw_color(*_SLATE_BORDER)
                self.line(14, self.get_y(), 196, self.get_y())

                self.set_font("Helvetica", "I", 7.5)
                self.set_text_color(148, 163, 184)
                self.set_xy(14, self.get_y() + 2)
                self.cell(
                    120, 5,
                    "Generated by DigitalDRM Automated System - Confidential",
                    align="L",
                )
                self.set_xy(0, self.get_y())
                self.cell(196, 5, f"Page {self.page_no()} of {{nb}}", align="R")

        return _Inner(*args, **kwargs)


def _kpi_card(pdf, x, y, w, h, label, value, accent):
    pdf.set_xy(x, y)
    pdf.set_fill_color(*_WHITE)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(x, y, w, h, style="DF")
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


def _draw_dept_bar_chart(pdf, rows: List[Dict[str, Any]]) -> None:
    """
    Draws the Plan-vs-Actual horizontal bar chart for a list of
    department rows (each: label/plan/actual/achieved) at the PDF's
    current Y position, then advances Y past it — identical output to
    what _build_daily_pdf always drew inline; extracted here so the
    combined President's Daily Report (president_daily_report_service.py)
    can draw the exact same chart style per plant/department without
    duplicating this drawing logic.
    """
    if not rows:
        return

    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Plan vs Actual by Department", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(5)

    chart_x = 60
    chart_w = 100
    bar_h = 4.2
    bar_gap = 1
    group_gap = 4

    max_val = max([max(r["plan"], r["actual"]) for r in rows] + [1])

    for r in rows:
        y0 = pdf.get_y()
        pdf.set_xy(14, y0)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_NAVY)
        pdf.cell(chart_x - 16, bar_h * 2 + bar_gap, r["label"], align="L")

        # Plan bar (muted blue-grey)
        plan_len = chart_w * (r["plan"] / max_val) if max_val else 0
        pdf.set_fill_color(*_SLATE_MUTED)
        if plan_len > 0:
            pdf.rect(chart_x, y0, plan_len, bar_h, style="F")
        pdf.set_xy(chart_x + max(plan_len, 0) + 2, y0 - 0.3)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_SLATE_MUTED)
        pdf.cell(28, bar_h, f"Plan: {r['plan']:.1f}", align="L")

        # Actual bar (status-colored)
        y1 = y0 + bar_h + bar_gap
        actual_len = chart_w * (r["actual"] / max_val) if max_val else 0
        pdf.set_fill_color(*_status_color(r["achieved"]))
        if actual_len > 0:
            pdf.rect(chart_x, y1, actual_len, bar_h, style="F")
        pdf.set_xy(chart_x + max(actual_len, 0) + 2, y1 - 0.3)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*_status_color(r["achieved"]))
        pdf.cell(28, bar_h, f"Actual: {r['actual']:.1f}", align="L")

        pdf.set_y(y1 + bar_h + group_gap)

    pdf.ln(1)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*_SLATE_MUTED)
    pdf.cell(
        0, 4,
        "Grey bar = Plan, colored bar = Actual (Green = On Track, Amber = Near Target, Red = Below Target).",
    )


def _build_daily_pdf(plant_id: int, plant_name: str, target_date: date_cls, report_data: Dict[str, Any]) -> bytes:
    """
    Builds the Daily Report PDF: company logo, plant name, report
    date & time, report type, overall summary, a Plan/Actual/Variance/
    Achievement% table, and a Plan-vs-Actual bar chart — for exactly the
    5 Daily-Report departments.
    """
    generated_at = datetime.now().strftime("%d-%b-%Y %H:%M")
    date_display = target_date.strftime("%d-%b-%Y")

    rows = []
    for label, key in DAILY_DEPTS:
        d = report_data.get(key) or {}
        plan = d.get("plan", 0) or 0
        actual = d.get("actual", 0) or 0
        variance = actual - plan
        achieved = (actual / plan * 100) if plan else None
        rows.append({"label": label, "plan": plan, "actual": actual, "variance": variance, "achieved": achieved})

    total_plan = sum(r["plan"] for r in rows)
    total_actual = sum(r["actual"] for r in rows)
    overall_achieved = (total_actual / total_plan * 100) if total_plan else None
    on_track_count = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] >= _THRESHOLD_ON_TRACK)
    attention_count = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] < _THRESHOLD_NEAR_TARGET)
    best_row = max((r for r in rows if r["achieved"] is not None), key=lambda r: r["achieved"], default=None)
    worst_row = min((r for r in rows if r["achieved"] is not None), key=lambda r: r["achieved"], default=None)

    pdf = _DailyReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.report_title = "DAILY REPORT"
    pdf.report_subtitle = f"ECD Division  |  {plant_name}  |  {date_display}"
    pdf.add_page()

    # ── Report details bar ──────────────────────────────────────────────
    pdf.set_fill_color(*_SLATE_BG)
    pdf.set_draw_color(*_SLATE_BORDER)
    pdf.rect(14, pdf.get_y(), 182, 16, style="DF")

    meta_items = [
        ("Plant",       plant_name),
        ("Report Type", "Daily"),
        ("Report Date", date_display),
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

    # ── Overall summary ──────────────────────────────────────────────────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 6, "Overall Summary", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(3)

    overall_txt = f"{overall_achieved:.1f}%" if overall_achieved is not None else "N/A"
    summary_lines = [
        f"This Daily report covers {plant_name} for {date_display}, consolidating {len(rows)} "
        f"department(s). Overall achievement against plan stood at {overall_txt}, with "
        f"{on_track_count} department(s) on track and {attention_count} department(s) needing attention.",
    ]
    if best_row:
        summary_lines.append(f"{best_row['label']} was the top performer at {best_row['achieved']:.1f}% of plan.")
    if worst_row and worst_row is not best_row:
        summary_lines.append(
            f"{worst_row['label']} recorded the lowest achievement at {worst_row['achieved']:.1f}% and may need review."
        )

    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(182, 5, "  ".join(summary_lines))
    pdf.ln(4)

    # ── KPI cards ─────────────────────────────────────────────────────────
    # "Overall Achieved" box intentionally removed per requirement — the
    # remaining 3 cards (Departments, On Track, Needs Attention) are
    # unchanged in content/values, only widened to fill the row evenly.
    card_y = pdf.get_y()
    card_h = 17
    gap = 4
    card_w = (182 - gap * 2) / 3

    _kpi_card(pdf, 14, card_y, card_w, card_h, "Departments", str(len(rows)), _ACCENT_BLUE)
    _kpi_card(pdf, 14 + (card_w + gap) * 1, card_y, card_w, card_h, "On Track", str(on_track_count), _GREEN)
    _kpi_card(pdf, 14 + (card_w + gap) * 2, card_y, card_w, card_h,
              "Needs Attention", str(attention_count), _RED if attention_count else _SLATE_MUTED)

    pdf.set_y(card_y + card_h + 8)

    # ── Table ─────────────────────────────────────────────────────────────
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

    headers = ["Department", "Plan", "Actual", "Variance", "Achieved %", "Status"]
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
        pct = f"{(achieved - 100):+.2f}%" if achieved is not None else "N/A"
        sign = "+" if variance >= 0 else ""
        v_str = f"{sign}{variance:.2f}"

        pdf.set_fill_color(*(_SLATE_BG if row_fill else _WHITE))
        pdf.set_x(14)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_widths[0], 8, r["label"], border="B", align="L", fill=True)
        pdf.cell(col_widths[1], 8, f"{plan:.2f}", border="B", align="R", fill=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[2], 8, f"{actual:.2f}", border="B", align="R", fill=True)

        pdf.set_text_color(*(_GREEN if variance >= 0 else _RED))
        pdf.cell(col_widths[3], 8, v_str, border="B", align="R", fill=True)

        pdf.set_text_color(*_NAVY)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[4], 8, pct, border="B", align="R", fill=True)

        status = _status_label(achieved)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_status_color(achieved))
        pdf.cell(col_widths[5], 8, status, border="B", align="C", fill=True)
        pdf.set_font("Helvetica", "", 9)

        pdf.ln()
        row_fill = not row_fill

    pdf.ln(6)

    # ── Plan vs Actual bar chart (per department) ───────────────────────
    _draw_dept_bar_chart(pdf, rows)

    return bytes(pdf.output())


# ── Save + email orchestration ──────────────────────────────────────────────

def _stem(plant_id: int, target_date: date_cls) -> str:
    return f"Plant{plant_id:02d}_Daily_{target_date.isoformat()}"


def _email_daily_report(plant_id: int, plant_name: str, target_date: date_cls, pdf_bytes: bytes, filename: str) -> None:
    date_display = target_date.strftime("%d-%b-%Y")
    subject = f"Daily DigitalDRM Report – {plant_name} – {date_display}"
    body = (
        f"Hello,\n\n"
        f"The Daily DigitalDRM report for {plant_name} ({date_display}) has been generated "
        f"successfully. The report is attached as a PDF.\n\n"
        f"This is an automated notification from the DigitalDRM system.\n"
    )

    recipients = _resolve_recipients(plant_id)
    if not recipients:
        logger.error(
            "[DAILY REPORT EMAIL] ❌ No recipient configured for plant=%s — "
            "add one in Admin Dashboard > Email Services (Daily Report Recipient or "
            "Combined Report Recipient). Email NOT sent.",
            plant_id,
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
            logger.info("[DAILY REPORT EMAIL] ✅ Report emailed to %s | %s", recipients, filename)
        else:
            logger.error("[DAILY REPORT EMAIL] ❌ Failed to email report to %s | %s", recipients, filename)
    except Exception as exc:
        logger.error("[DAILY REPORT EMAIL] ❌ Unexpected error emailing report: %s", exc, exc_info=True)


def generate_and_save_daily_report(db: Session, plant_id: int, target_date: Optional[date_cls] = None) -> Dict[str, Any]:
    """
    Builds, saves, and emails the Daily Report PDF for ONE plant.
    Defaults to today's date. Returns a status dict identical in shape to
    the existing report-save endpoints' responses.
    """
    if target_date is None:
        target_date = date_cls.today()

    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[DAILY REPORT SAVE] Cannot create directory: %s", exc)
        return {"status": "error", "message": f"Cannot create directory: {exc}"}

    plant_name = _plant_name(db, plant_id)
    report_data = generate_daily_report(db, plant_id, target_date)

    filename = f"{_stem(plant_id, target_date)}.pdf"
    filepath = REPORTS_DIR / filename

    try:
        pdf_bytes = _build_daily_pdf(plant_id, plant_name, target_date, report_data)
        filepath.write_bytes(pdf_bytes)
        logger.info("[DAILY REPORT SAVE] PDF saved: %s (%d bytes)", filepath, len(pdf_bytes))
    except ImportError:
        msg = "fpdf2 is not installed. Run: venv\\Scripts\\pip install fpdf2"
        logger.error("[DAILY REPORT SAVE] %s", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        logger.error("[DAILY REPORT SAVE] Failed: %s", exc, exc_info=True)
        return {"status": "error", "message": str(exc)}

    _email_daily_report(plant_id, plant_name, target_date, pdf_bytes, filename)

    return {
        "status":   "ok",
        "plant_id": plant_id,
        "date":     target_date.isoformat(),
        "filename": filename,
        "path":     str(filepath),
        "format":   "pdf",
    }


def generate_and_save_daily_report_bytes(db: Session, plant_id: int, target_date: Optional[date_cls] = None):
    """Like generate_and_save_daily_report(), but also returns the raw PDF
    bytes + filename so a route can stream them straight back for
    download without re-reading the file from disk."""
    if target_date is None:
        target_date = date_cls.today()

    plant_name = _plant_name(db, plant_id)
    report_data = generate_daily_report(db, plant_id, target_date)
    pdf_bytes = _build_daily_pdf(plant_id, plant_name, target_date, report_data)
    filename = f"{_stem(plant_id, target_date)}.pdf"

    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / filename).write_bytes(pdf_bytes)
    except Exception as exc:
        logger.error("[DAILY REPORT DOWNLOAD] Could not save copy to disk: %s", exc)

    return pdf_bytes, filename


def generate_daily_reports_for_all_plants(db: Session, target_date: Optional[date_cls] = None) -> List[Dict[str, Any]]:
    """Generates, saves, and emails the Daily Report for every plant in
    ALL_PLANT_IDS. Used by both the scheduler and the
    POST /daily-report/generate-all endpoint."""
    if target_date is None:
        target_date = date_cls.today()

    results = []
    for plant_id in ALL_PLANT_IDS:
        try:
            result = generate_and_save_daily_report(db, plant_id, target_date)
        except Exception as exc:
            logger.error("[DAILY REPORT] Plant %s failed: %s", plant_id, exc, exc_info=True)
            result = {"status": "error", "plant_id": plant_id, "message": str(exc)}
        results.append(result)
    return results


# ══════════════════════════════════════════════════════════════════════════
# President's Combined All-Plants Daily Report
# ══════════════════════════════════════════════════════════════════════════
#
# A SEPARATE report from the per-plant Daily Report above — this one
# combines EVERY plant into a SINGLE PDF and emails it to the President,
# with a Plan-vs-Actual bar chart for every daily-reporting department
# (Production, Manpower, OVC, Product Value, Despatch) under each
# plant's own section. Lives in this same file (rather than a separate
# service module) since it's just another Daily Report variant, reusing
# generate_daily_report() and _draw_dept_bar_chart() from above directly
# — no cross-module import needed.
#
# Flow: generate_and_save_president_daily_report(db, target_date=None)
# is called by the scheduler (scheduler.py) once a day, right after the
# per-plant Daily Report job, using the same holiday-aware "previous
# working day" reference date — never simply "yesterday". Emailed to
# the "president" recipient type (Admin Dashboard > Email Services) —
# the same global/plant-wide President recipient already used for
# Monthly/Quarterly/Yearly reports and Level 3 escalation.

def _president_reference_date(target_date: Optional[date_cls]) -> date_cls:
    if target_date is not None:
        return target_date
    from app.services.holiday_service import load_holidays, previous_working_day
    today = date_cls.today()
    return previous_working_day(today, load_holidays())


def _president_plant_rows(report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Same row-shape construction _build_daily_pdf uses — kept
    identical so this report's per-department numbers/status always
    match the individual per-plant report exactly."""
    rows = []
    for label, key in DAILY_DEPTS:
        d = report_data.get(key) or {}
        plan = d.get("plan", 0) or 0
        actual = d.get("actual", 0) or 0
        variance = actual - plan
        achieved = (actual / plan * 100) if plan else None
        rows.append({"label": label, "plan": plan, "actual": actual, "variance": variance, "achieved": achieved})
    return rows


def _build_president_daily_pdf(target_date: date_cls, plants_data: List[Dict[str, Any]]) -> bytes:
    """
    plants_data: list of {"plant_id", "plant_name", "rows"} — one entry
    per plant, already computed by the caller so this function is pure
    PDF-drawing.
    """
    date_display = target_date.strftime("%d-%b-%Y")

    pdf = _DailyReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.report_title = "DAILY REPORT - ALL PLANTS"
    pdf.report_subtitle = f"ECD Division  |  President's Consolidated Daily Report  |  {date_display}"
    pdf.add_page()

    # ── Cover / index: every plant's overall achievement at a glance ────
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 8, f"All-Plants Daily Summary - {date_display}", ln=True)
    pdf.set_x(14)
    pdf.set_draw_color(*_ACCENT_BLUE)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y(), 34, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(6)

    headers = ["Plant", "Total Plan", "Total Actual", "Variance", "Achieved %", "Status", "On Track"]
    col_widths = [42, 26, 26, 24, 24, 30, 20]
    pdf.set_x(14)
    pdf.set_fill_color(*_NAVY)
    pdf.set_text_color(*_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for h, w in zip(headers, col_widths):
        align = "L" if h == "Plant" else "C" if h in ("Status",) else "R"
        pdf.cell(w, 8, h, align=align, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    row_fill = False
    for p in plants_data:
        rows = p["rows"]
        total_plan = sum(r["plan"] for r in rows)
        total_actual = sum(r["actual"] for r in rows)
        variance = total_actual - total_plan
        achieved = (total_actual / total_plan * 100) if total_plan else None
        on_track = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] >= _THRESHOLD_ON_TRACK)

        pdf.set_fill_color(*(_SLATE_BG if row_fill else _WHITE))
        pdf.set_x(14)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_widths[0], 8, p["plant_name"], border="B", align="L", fill=True)
        pdf.cell(col_widths[1], 8, f"{total_plan:.1f}", border="B", align="R", fill=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[2], 8, f"{total_actual:.1f}", border="B", align="R", fill=True)

        pdf.set_text_color(*(_GREEN if variance >= 0 else _RED))
        pdf.cell(col_widths[3], 8, f"{'+' if variance >= 0 else ''}{variance:.1f}", border="B", align="R", fill=True)

        pdf.set_text_color(*_NAVY)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[4], 8, f"{achieved:.1f}%" if achieved is not None else "N/A", border="B", align="R", fill=True)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_status_color(achieved))
        pdf.cell(col_widths[5], 8, _status_label(achieved), border="B", align="C", fill=True)

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_NAVY)
        pdf.cell(col_widths[6], 8, f"{on_track}/{len(rows)}", border="B", align="R", fill=True)

        pdf.ln()
        row_fill = not row_fill

    # ── One page per plant: department table + Plan-vs-Actual chart ────
    for p in plants_data:
        plant_id, plant_name, rows = p["plant_id"], p["plant_name"], p["rows"]

        pdf.report_subtitle = f"ECD Division  |  {plant_name}  |  {date_display}"
        pdf.add_page()

        total_plan = sum(r["plan"] for r in rows)
        total_actual = sum(r["actual"] for r in rows)
        overall_achieved = (total_actual / total_plan * 100) if total_plan else None
        on_track_count = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] >= _THRESHOLD_ON_TRACK)
        attention_count = sum(1 for r in rows if r["achieved"] is not None and r["achieved"] < _THRESHOLD_NEAR_TARGET)

        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*_NAVY)
        pdf.cell(0, 8, plant_name, ln=True)

        card_y = pdf.get_y() + 2
        card_h = 17
        gap = 4
        card_w = (182 - gap * 2) / 3
        overall_txt = f"{overall_achieved:.1f}%" if overall_achieved is not None else "N/A"
        _kpi_card(pdf, 14, card_y, card_w, card_h, "Overall Achieved", overall_txt, _status_color(overall_achieved))
        _kpi_card(pdf, 14 + (card_w + gap) * 1, card_y, card_w, card_h, "On Track", str(on_track_count), _GREEN)
        _kpi_card(pdf, 14 + (card_w + gap) * 2, card_y, card_w, card_h,
                  "Needs Attention", str(attention_count), _RED if attention_count else _SLATE_MUTED)
        pdf.set_y(card_y + card_h + 8)

        # Department table
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

        headers = ["Department", "Plan", "Actual", "Variance", "Achieved %", "Status"]
        col_widths = [42, 24, 24, 26, 28, 38]
        pdf.set_x(14)
        pdf.set_fill_color(*_NAVY)
        pdf.set_text_color(*_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        for h, w in zip(headers, col_widths):
            align = "L" if h == "Department" else "C" if h == "Status" else "R"
            pdf.cell(w, 8, h, align=align, fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        row_fill = False
        for r in rows:
            plan, actual, variance, achieved = r["plan"], r["actual"], r["variance"], r["achieved"]
            pct = f"{(achieved - 100):+.2f}%" if achieved is not None else "N/A"
            v_str = f"{'+' if variance >= 0 else ''}{variance:.2f}"

            pdf.set_fill_color(*(_SLATE_BG if row_fill else _WHITE))
            pdf.set_x(14)
            pdf.set_text_color(*_NAVY)
            pdf.cell(col_widths[0], 8, r["label"], border="B", align="L", fill=True)
            pdf.cell(col_widths[1], 8, f"{plan:.2f}", border="B", align="R", fill=True)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(col_widths[2], 8, f"{actual:.2f}", border="B", align="R", fill=True)

            pdf.set_text_color(*(_GREEN if variance >= 0 else _RED))
            pdf.cell(col_widths[3], 8, v_str, border="B", align="R", fill=True)

            pdf.set_text_color(*_NAVY)
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(col_widths[4], 8, pct, border="B", align="R", fill=True)

            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_status_color(achieved))
            pdf.cell(col_widths[5], 8, _status_label(achieved), border="B", align="C", fill=True)
            pdf.set_font("Helvetica", "", 9)

            pdf.ln()
            row_fill = not row_fill

        pdf.ln(6)

        # Plan-vs-Actual chart — same drawing helper the per-plant Daily
        # Report already uses, so the visual style matches exactly.
        _draw_dept_bar_chart(pdf, rows)

    return bytes(pdf.output())


def _resolve_president_recipients(db: Session) -> List[str]:
    """The "president" recipient type — global (plant_id=None) fallback
    already built into get_recipients(), so a single Admin Dashboard >
    Email Services entry (President, no plant) covers this report."""
    return recipients_svc.get_recipients(db, "president", department=None, plant_id=None)


def _email_president_daily_report(db: Session, target_date: date_cls, pdf_bytes: bytes, filename: str) -> None:
    date_display = target_date.strftime("%d-%b-%Y")
    subject = f"Daily DigitalDRM Report \u2013 All Plants \u2013 {date_display}"
    body = (
        f"Hello,\n\n"
        f"The consolidated Daily DigitalDRM report for ALL plants ({date_display}) has been "
        f"generated successfully. Each plant's department-wise performance, including a "
        f"Plan-vs-Actual chart, is included in the attached PDF.\n\n"
        f"This is an automated notification from the DigitalDRM system.\n"
    )

    recipients = _resolve_president_recipients(db)
    if not recipients:
        logger.error(
            "[PRESIDENT DAILY REPORT EMAIL] \u274c No President recipient configured — "
            "add one in Admin Dashboard > Email Services (type: President). Email NOT sent."
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
            logger.info("[PRESIDENT DAILY REPORT EMAIL] \u2705 Report emailed to %s | %s", recipients, filename)
        else:
            logger.error("[PRESIDENT DAILY REPORT EMAIL] \u274c Failed to email report to %s | %s", recipients, filename)
    except Exception as exc:
        logger.error("[PRESIDENT DAILY REPORT EMAIL] \u274c Unexpected error emailing report: %s", exc, exc_info=True)


def generate_and_save_president_daily_report(db: Session, target_date: Optional[date_cls] = None) -> Dict[str, Any]:
    """
    Builds, saves, and emails the single combined All-Plants Daily
    Report PDF to the President. Defaults to the previous WORKING day
    (skipping Sundays/holidays, never simply "yesterday") — same
    reference-date logic as the per-plant Daily Report job above.
    """
    resolved_date = _president_reference_date(target_date)

    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.error("[PRESIDENT DAILY REPORT SAVE] Cannot create directory: %s", exc)
        return {"status": "error", "message": f"Cannot create directory: {exc}"}

    plants_data = []
    for plant_id in ALL_PLANT_IDS:
        try:
            report_data = generate_daily_report(db, plant_id, resolved_date)
            plants_data.append({
                "plant_id": plant_id,
                "plant_name": _plant_name(db, plant_id),
                "rows": _president_plant_rows(report_data),
            })
        except Exception as exc:
            logger.error("[PRESIDENT DAILY REPORT] Plant %s failed to aggregate: %s", plant_id, exc, exc_info=True)

    filename = f"AllPlants_Daily_{resolved_date.isoformat()}.pdf"
    filepath = REPORTS_DIR / filename

    try:
        pdf_bytes = _build_president_daily_pdf(resolved_date, plants_data)
        filepath.write_bytes(pdf_bytes)
        logger.info("[PRESIDENT DAILY REPORT SAVE] PDF saved: %s (%d bytes)", filepath, len(pdf_bytes))
    except ImportError:
        msg = "fpdf2 is not installed. Run: venv\\Scripts\\pip install fpdf2"
        logger.error("[PRESIDENT DAILY REPORT SAVE] %s", msg)
        return {"status": "error", "message": msg}
    except Exception as exc:
        logger.error("[PRESIDENT DAILY REPORT SAVE] Failed: %s", exc, exc_info=True)
        return {"status": "error", "message": str(exc)}

    _email_president_daily_report(db, resolved_date, pdf_bytes, filename)

    return {
        "status": "ok",
        "date": resolved_date.isoformat(),
        "plants_included": [p["plant_id"] for p in plants_data],
        "filename": filename,
        "path": str(filepath),
        "format": "pdf",
    }