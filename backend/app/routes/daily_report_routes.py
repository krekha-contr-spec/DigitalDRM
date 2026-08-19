"""
daily_report_routes.py
-----------------------
New, additive API surface for the Daily Report feature. Does not modify
or import anything from report_routes.py / report_save_routes.py, so the
existing Monthly, Quarterly, and Yearly report endpoints are completely
unaffected.

Endpoints:
  POST /daily-report/generate       -> generate+save+email ONE plant's Daily Report
  POST /daily-report/generate-all   -> generate+save+email EVERY plant's Daily Report
  GET  /daily-report/download/{plant_id} -> generate (if needed) and stream the PDF for download
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.daily_report_service import (
    generate_and_save_daily_report,
    generate_and_save_daily_report_bytes,
    generate_daily_reports_for_all_plants,
    generate_and_save_president_daily_report,
    ALL_PLANT_IDS,
)

router = APIRouter(prefix="/daily-report", tags=["Daily Report"])


def _parse_date(date_str: Optional[str]) -> date:
    if not date_str:
        return date.today()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


class DailyReportRequest(BaseModel):
    plant_id: int
    date: Optional[str] = None  # "YYYY-MM-DD"; defaults to today


class DailyReportAllRequest(BaseModel):
    date: Optional[str] = None  # "YYYY-MM-DD"; defaults to today


@router.post("/generate")
def generate_daily_report_endpoint(req: DailyReportRequest, db: Session = Depends(get_db)):
    """Generates, saves, and emails the Daily Report PDF for one plant."""
    target_date = _parse_date(req.date)
    result = generate_and_save_daily_report(db, req.plant_id, target_date)
    if result.get("status") == "error":
        return JSONResponse(status_code=500, content=result)
    return result


@router.post("/generate-all")
def generate_daily_report_all_endpoint(req: DailyReportAllRequest, db: Session = Depends(get_db)):
    """Generates, saves, and emails the Daily Report PDF for every plant
    (ALL_PLANT_IDS), each sent to that plant's own configured recipients."""
    target_date = _parse_date(req.date)
    results = generate_daily_reports_for_all_plants(db, target_date)
    ok = sum(1 for r in results if r.get("status") == "ok")
    return {"status": "ok", "generated": ok, "total": len(results), "results": results}


@router.get("/download/{plant_id}")
def download_daily_report(
    plant_id: int,
    date_str: Optional[str] = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    """Generates (if not already on disk for today) and streams the Daily
    Report PDF back for the browser to download."""
    target_date = _parse_date(date_str)
    pdf_bytes, filename = generate_and_save_daily_report_bytes(db, plant_id, target_date)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/plants")
def list_daily_report_plants():
    """Convenience endpoint for the frontend to know which plant ids the
    Daily Report covers."""
    return {"plant_ids": ALL_PLANT_IDS}


# ── President's combined All-Plants Daily Report ─────────────────────────
#
# A SEPARATE report from the per-plant ones above — combines EVERY
# plant into a SINGLE PDF (with a Plan-vs-Actual chart per department,
# per plant) and emails it to the "president" recipient. See
# generate_and_save_president_daily_report() in daily_report_service.py
# for the full explanation. Lives under this same /daily-report prefix
# since it's just another Daily Report variant, not a separate feature.

class PresidentDailyReportRequest(BaseModel):
    date: Optional[str] = None  # "YYYY-MM-DD"; defaults to previous working day


@router.post("/president/generate")
def generate_president_daily_report_endpoint(req: PresidentDailyReportRequest, db: Session = Depends(get_db)):
    """Generates, saves, and emails the combined All-Plants Daily Report
    PDF to the configured 'president' recipient. Useful for testing
    without waiting for the scheduled run."""
    target_date = datetime.strptime(req.date, "%Y-%m-%d").date() if req.date else None
    result = generate_and_save_president_daily_report(db, target_date)
    if result.get("status") == "error":
        return JSONResponse(status_code=500, content=result)
    return result


@router.get("/president/download")
def download_president_daily_report(
    date_str: Optional[str] = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    """Generates (saving + emailing as a side effect, same as
    /president/generate) and streams the PDF back for the browser to
    download."""
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
    result = generate_and_save_president_daily_report(db, target_date)
    if result.get("status") == "error":
        return JSONResponse(status_code=500, content=result)

    from pathlib import Path
    pdf_bytes = Path(result["path"]).read_bytes()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )