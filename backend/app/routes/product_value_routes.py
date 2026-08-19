"""
product_value_routes.py
-----------------------
API routes for Product Value department.
Data is stored in ovc_elements table with element_type = "Product Value".
Mirrors rejection_ppm_routes.py exactly — only ELEMENT_TYPE differs.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.models import OVCElement
from app.schemas.schemas import OVCEntry
from datetime import date, datetime
from typing import Optional

ELEMENT_TYPE = "Product Value"

router = APIRouter(prefix="/product-value", tags=["Product Value"])

# Once a record exists for a given (plant, date) it is permanently locked —
# no edit, update, refresh, overwrite, or delete is ever allowed.
KPI_LOCK_MESSAGE = "Data already submitted and locked."


@router.get("/check/{plant_id}/{entry_date}")
def check_product_value_lock(plant_id: int, entry_date: date, db: Session = Depends(get_db)):
    existing = db.query(OVCElement).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.date == entry_date,
        OVCElement.element_type == ELEMENT_TYPE,
    ).first()
    return {"locked": existing is not None, "message": KPI_LOCK_MESSAGE if existing else None}


@router.post("/entry")
def add_product_value(entry: OVCEntry, db: Session = Depends(get_db)):
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
    return {"message": "Product Value data saved!"}


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
    if year is None or month is None:
        return {"trend": [], "summary": _empty_summary()}

    records = (
        db.query(OVCElement)
        .filter(
            OVCElement.plant_id == plant_id,
            OVCElement.element_type == ELEMENT_TYPE,
            extract("year",  OVCElement.date) == year,
            extract("month", OVCElement.date) == month,
        )
        .order_by(OVCElement.date)
        .all()
    )

    trend = [
        {
            "date":   r.date.strftime("%Y-%m-%d"),
            "plan":   r.plan,
            "actual": r.actual,
        }
        for r in records
    ]

    # Last updated timestamp — derived from the same filtered records
    updated_times = [r.updated_at for r in records if r.updated_at is not None]
    last_dt = max(updated_times) if updated_times else None
    last_updated = last_dt.isoformat() if last_dt else None

    return {"trend": trend, "summary": _calc_summary(records), "last_updated": last_updated}

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
        "date": r.date.strftime("%Y-%m-%d"),
        "month": r.date.strftime("%B"),
        "element_type": r.element_type,
        "plan": r.plan,
        "actual": r.actual,
        "variance": round((r.actual or 0) - (r.plan or 0), 2),
        "achieved_percent": round(
            (((r.actual or 0) / (r.plan or 0)) * 100)
            if (r.plan or 0) > 0
            else 0,
            2,
        ),
    }
    for r in records
]}


@router.get("/monthly-trend/{plant_id}")
def get_product_value_monthly_trend(
    plant_id: int,
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get month-wise Product Value totals for a full year."""
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