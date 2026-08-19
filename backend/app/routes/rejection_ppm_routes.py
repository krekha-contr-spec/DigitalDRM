"""
rejection_ppm_routes.py
-----------------------
API routes for Rejection PPM department.
Data is stored in ovc_elements table with element_type = "Rejection PPM".
All query/write logic mirrors ovc_routes.py, filtered by element_type.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.models import OVCElement
from app.schemas.schemas import OVCEntry
from datetime import date, datetime
from typing import Optional
import calendar

ELEMENT_TYPE = "Rejection PPM"

router = APIRouter(prefix="/rejection-ppm", tags=["Rejection PPM"])

# Once a record exists for a given (plant, date) it is permanently locked —
# no edit, update, refresh, overwrite, or delete is ever allowed.
KPI_LOCK_MESSAGE = "Data already submitted and locked."


@router.get("/check/{plant_id}/{entry_date}")
def check_rejection_ppm_lock(plant_id: int, entry_date: date, db: Session = Depends(get_db)):
    existing = db.query(OVCElement).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.date == entry_date,
        OVCElement.element_type == ELEMENT_TYPE,
    ).first()
    return {"locked": existing is not None, "message": KPI_LOCK_MESSAGE if existing else None}


@router.post("/entry")
def add_rejection_ppm(entry: OVCEntry, db: Session = Depends(get_db)):
    existing = db.query(OVCElement).filter(
        OVCElement.plant_id == entry.plant_id,
        OVCElement.date == entry.date,
        OVCElement.element_type == ELEMENT_TYPE,
    ).first()

    if existing is not None:
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)

    db.add(OVCElement(
        plant_id=entry.plant_id,
        date=entry.date,
        element_type=ELEMENT_TYPE,
        plan=entry.plan,
        actual=entry.actual,
        updated_at=datetime.now(),
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)
    return {"message": "Rejection PPM data saved!"}


@router.get("/latest-actual/{plant_id}")
def get_latest_actual(plant_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(OVCElement)
        .filter(OVCElement.plant_id == plant_id, OVCElement.element_type == ELEMENT_TYPE)
        .order_by(OVCElement.date.desc())
        .first()
    )
    if not record:
        return {"actual": None, "plan": None, "element_type": ELEMENT_TYPE, "date": None}
    return {
        "actual": record.actual,
        "plan": record.plan,
        "element_type": record.element_type,
        "date": record.date.strftime("%Y-%m-%d"),
    }


def _empty_summary():
    return {"plan_total": 0, "actual_total": 0, "variance": 0, "achieved_percent": 0}


def _calc_summary(records):
    if not records:
        return _empty_summary()
    plan_total   = sum((r.plan   or 0) for r in records)
    actual_total = sum((r.actual or 0) for r in records)
    variance     = actual_total - plan_total
    achieved_pct = (actual_total / plan_total * 100) if plan_total > 0 else 0
    return {
        "plan_total":       round(plan_total, 2),
        "actual_total":     round(actual_total, 2),
        "variance":         round(variance, 2),
        "achieved_percent": round(achieved_pct, 2),
    }


@router.get("/trend/{plant_id}")
def get_trend(
    plant_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    view: str = "daily",
    db: Session = Depends(get_db),
):
    """Get trend data. For Rejection PPM, we aggregate by month."""
    if year is None or month is None:
        return {"trend": [], "summary": _empty_summary()}

    # For Rejection PPM, we want monthly aggregated data
    # Get all records for the year
    records = (
        db.query(OVCElement)
        .filter(
            OVCElement.plant_id == plant_id,
            OVCElement.element_type == ELEMENT_TYPE,
            extract("year", OVCElement.date) == year,
        )
        .order_by(OVCElement.date)
        .all()
    )

    # Aggregate by month
    monthly_data = {}
    for r in records:
        m = r.date.month
        if m not in monthly_data:
            monthly_data[m] = {"plan": 0, "actual": 0, "date": f"{year}-{str(m).zfill(2)}-01"}
        monthly_data[m]["plan"] += (r.plan or 0)
        monthly_data[m]["actual"] += (r.actual or 0)

    # Convert to trend format - monthly aggregated
    trend = []
    for m in range(1, 13):
        if m in monthly_data:
            trend.append({
                "date": monthly_data[m]["date"],
                "plan": monthly_data[m]["plan"],
                "actual": monthly_data[m]["actual"],
                "month": m
            })
        else:
            trend.append({
                "date": f"{year}-{str(m).zfill(2)}-01",
                "plan": 0,
                "actual": 0,
                "month": m
            })

    # Calculate summary from all records (yearly total)
    summary = _calc_summary(records)

    # Last updated timestamp
    updated_times = [r.updated_at for r in records if r.updated_at is not None]
    last_dt = max(updated_times) if updated_times else None
    last_updated = last_dt.isoformat() if last_dt else None

    return {"trend": trend, "summary": summary, "last_updated": last_updated}


@router.get("/history/{plant_id}")
def get_history(plant_id: int, limit: Optional[int] = 30, db: Session = Depends(get_db)):
    """Returns the latest `limit` records (default 30), newest first.
    Older records are never deleted — pass a larger `limit` (or omit it
    via limit=0/None) to retrieve more/all history."""
    query = (
        db.query(OVCElement)
        .filter(OVCElement.plant_id == plant_id, OVCElement.element_type == ELEMENT_TYPE)
        .order_by(OVCElement.date.desc())
    )
    records = query.all() if not limit or limit <= 0 else query.limit(limit).all()
    return {
        "history": [
            {
                "date":             r.date.strftime("%Y-%m-%d"),
                "month":            r.date.strftime("%B"),
                "element_type":     r.element_type,
                "plan":             r.plan,
                "actual":           r.actual,
                "variance":         round((r.actual or 0) - (r.plan or 0), 2),
                "achieved_percent": round((r.actual / r.plan * 100) if r.plan and r.plan > 0 else 0, 2),
            }
            for r in records
        ]
    }


@router.get("/monthly-trend/{plant_id}")
def get_rejection_ppm_monthly_trend(
    plant_id: int,
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get month-wise Rejection PPM totals for a full year."""
    if year is None:
        return {"monthly": []}

    records = db.query(OVCElement).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == ELEMENT_TYPE,
        extract('year', OVCElement.date) == year
    ).all()

    monthly: dict = {}
    for r in records:
        m = r.date.month
        if m not in monthly:
            monthly[m] = {"month": m, "month_name": r.date.strftime("%b"), "plan": 0, "actual": 0}
        monthly[m]["plan"]   += (r.plan   or 0)
        monthly[m]["actual"] += (r.actual or 0)

    result = sorted(monthly.values(), key=lambda x: x["month"])
    return {"monthly": result}