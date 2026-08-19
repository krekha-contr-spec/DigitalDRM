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

router = APIRouter(prefix="/ovc", tags=["OVC Elements"])

# Once a record exists for a given (plant, date, element_type) it is
# permanently locked — no edit, update, refresh, overwrite, or delete.
KPI_LOCK_MESSAGE = "Data already submitted and locked."


@router.get("/check/{plant_id}/{entry_date}")
def check_ovc_lock(plant_id: int, entry_date: date, element_type: str, db: Session = Depends(get_db)):
    existing = db.query(OVCElement).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.date == entry_date,
        OVCElement.element_type == element_type
    ).first()
    return {"locked": existing is not None, "message": KPI_LOCK_MESSAGE if existing else None}


@router.post("/entry")
def add_ovc(entry: OVCEntry, db: Session = Depends(get_db)):
    existing = db.query(OVCElement).filter(
        OVCElement.plant_id == entry.plant_id,
        OVCElement.date == entry.date,
        OVCElement.element_type == entry.element_type
    ).first()

    if existing is not None:
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)

    db.add(OVCElement(
        plant_id=entry.plant_id,
        date=entry.date,
        element_type=entry.element_type,
        plan=entry.plan,
        actual=entry.actual,
        updated_at=datetime.now()
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)
    return {"message": "OVC data saved!"}


@router.get("/latest-actual/{plant_id}")
def get_latest_actual(plant_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(OVCElement)
        .filter(OVCElement.plant_id == plant_id)
        .order_by(OVCElement.date.desc())
        .first()
    )
    if not record:
        return {"actual": None, "plan": None, "element_type": None, "date": None}
    return {
        "actual": record.actual,
        "plan": record.plan,
        "element_type": record.element_type,
        "date": record.date.strftime("%Y-%m-%d"),
    }


def generate_daily_range(year: int, month: int):
    """Generate all dates for a given month"""
    days_in_month = calendar.monthrange(year, month)[1]
    dates = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        dates.append(d)
    return dates


def get_empty_summary():
    return {
        "plan_total": 0,
        "actual_total": 0,
        "variance": 0,
        "achieved_percent": 0
    }


def calculate_summary(trend_data):
    """Calculate summary metrics"""
    if not trend_data:
        return get_empty_summary()
    
    plan_total = sum(t["plan"] for t in trend_data if t["plan"] is not None)
    actual_total = sum(t["actual"] for t in trend_data if t["actual"] is not None)
    variance = actual_total - plan_total
    achieved_percent = (actual_total / plan_total * 100) if plan_total > 0 else 0
    
    return {
        "plan_total": round(plan_total, 2),
        "actual_total": round(actual_total, 2),
        "variance": round(variance, 2),
        "achieved_percent": round(achieved_percent, 2)
    }


@router.get("/trend/{plant_id}")
def get_ovc_trend(
    plant_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    view: str = "daily",
    db: Session = Depends(get_db)
):
    """Get OVC trend data"""
    
    if year is None or month is None:
        return {"elements": [], "summary": get_empty_summary()}
    
    query = db.query(OVCElement).filter(
        OVCElement.plant_id == plant_id,
        extract('year', OVCElement.date) == year,
        extract('month', OVCElement.date) == month
    )
    
    records = query.order_by(OVCElement.date).all()
    
    # Get unique elements and their latest values
    elements_dict = {}
    for r in records:
        if r.element_type not in elements_dict:
            elements_dict[r.element_type] = {
                "element_type": r.element_type,
                "plan": r.plan,
                "actual": r.actual
            }
        else:
            elements_dict[r.element_type]["actual"] = r.actual
    
    elements = list(elements_dict.values())
    
    # Calculate summary
    summary = calculate_summary(elements)

    # Last updated timestamp — derived from the same records shown on this card
    updated_times = [r.updated_at for r in records if r.updated_at is not None]
    last_dt = max(updated_times) if updated_times else None
    last_updated = last_dt.isoformat() if last_dt else None

    return {
        "elements": elements,
        "summary": summary,
        "last_updated": last_updated,
    }


@router.get("/history/{plant_id}")
def get_ovc_history(plant_id: int, limit: Optional[int] = 30, db: Session = Depends(get_db)):
    """Returns the latest `limit` records (default 30), newest first.
    Older records are never deleted — pass a larger `limit` (or omit it
    via limit=0/None) to retrieve more/all history."""
    query = (
        db.query(OVCElement)
        .filter(OVCElement.plant_id == plant_id)
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
                "achieved_percent": round(((r.actual or 0) / r.plan * 100) if r.plan and r.plan > 0 else 0, 2)
            } for r in records
        ]
    }