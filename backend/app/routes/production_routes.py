from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.models import DailyProduction
from app.schemas.schemas import ProductionEntry
from datetime import date, datetime, timedelta
from typing import Optional
import calendar


router = APIRouter(prefix="/production", tags=["Production"])

# Once a record exists for a given (plant, date) it is permanently locked —
# no edit, update, refresh, overwrite, or delete is ever allowed.
KPI_LOCK_MESSAGE = "Data already submitted and locked."


@router.get("/check/{plant_id}/{entry_date}")
def check_production_lock(plant_id: int, entry_date: date, db: Session = Depends(get_db)):
    """Tell the frontend whether this (plant, date) is already locked."""
    existing = db.query(DailyProduction).filter(
        DailyProduction.plant_id == plant_id,
        DailyProduction.date == entry_date
    ).first()
    return {"locked": existing is not None, "message": KPI_LOCK_MESSAGE if existing else None}


@router.post("/entry")
def add_production(entry: ProductionEntry, db: Session = Depends(get_db)):
    existing = db.query(DailyProduction).filter(
        DailyProduction.plant_id == entry.plant_id,
        DailyProduction.date == entry.date
    ).first()

    # Date-wise lock: once a record exists for this plant + date, it is
    # permanently locked — no edit, update, or delete via this endpoint.
    if existing is not None:
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)

    new_entry = DailyProduction(
        plant_id=entry.plant_id,
        date=entry.date,
        plan=entry.plan,
        actual=entry.actual,
        updated_at=datetime.now()
    )
    db.add(new_entry)
    try:
        db.commit()
    except IntegrityError:
        # DB-level UNIQUE constraint caught a race (two simultaneous saves).
        db.rollback()
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)
    return {"message": "Production data saved!"}


@router.get("/latest-actual/{plant_id}")
def get_latest_actual(plant_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(DailyProduction)
        .filter(DailyProduction.plant_id == plant_id)
        .order_by(DailyProduction.date.desc())
        .first()
    )
    if not record:
        return {"actual": None, "plan": None, "date": None}
    return {
        "actual": record.actual,
        "plan": record.plan,
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


def generate_monthly_range(year: int):
    """Generate all months for a given year"""
    dates = []
    for month in range(1, 13):
        # Use first day of each month
        d = date(year, month, 1)
        dates.append(d)
    return dates


@router.get("/trend/{plant_id}")
def get_production_trend(
    plant_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    view: str = "daily",
    db: Session = Depends(get_db)
):
    """
    Get production trend data.
    
    Args:
        plant_id: Plant ID
        year: Year (required for month view, optional for all data)
        month: Month (required for daily view)
        view: "daily" (by day), "monthly" (by month), "yearly" (by year)
    """
    
    # For daily view, require both year and month
    if view == "daily":
        if year is None or month is None:
            return {"trend": [], "summary": get_empty_summary()}
        
        date_range = generate_daily_range(year, month)
        query = db.query(DailyProduction).filter(
            DailyProduction.plant_id == plant_id,
            extract('year', DailyProduction.date) == year,
            extract('month', DailyProduction.date) == month
        )
    
    # For monthly view, require year
    elif view == "monthly":
        if year is None:
            return {"trend": [], "summary": get_empty_summary()}
        
        date_range = generate_monthly_range(year)
        query = db.query(DailyProduction).filter(
            DailyProduction.plant_id == plant_id,
            extract('year', DailyProduction.date) == year
        )
    
    # For all data
    else:
        date_range = None
        query = db.query(DailyProduction).filter(
            DailyProduction.plant_id == plant_id
        )
    
    records = query.order_by(DailyProduction.date).all()
    
    # Build lookup map
    data_map = {}
    for r in records:
        data_map[r.date] = {"plan": r.plan, "actual": r.actual}
    
    # Build trend with all dates
    if view == "daily" and date_range:
        trend_data = []
        for d in date_range:
            entry = data_map.get(d)
            trend_data.append({
                "date": d.strftime("%d-%b"),  # "01-Jan"
                "date_full": d.strftime("%Y-%m-%d"),
                "plan": entry["plan"] if entry else None,
                "actual": entry["actual"] if entry else None
            })
    
    elif view == "monthly" and date_range:
        # Aggregate by month
        trend_data = []
        for month_date in date_range:
            month_records = [
                r for r in records 
                if r.date.year == month_date.year and r.date.month == month_date.month
            ]
            
            month_plan = sum(r.plan for r in month_records if r.plan is not None)
            month_actual = sum(r.actual for r in month_records if r.actual is not None)
            
            trend_data.append({
                "date": month_date.strftime("%b-%Y"),  # "Jan-2026"
                "date_full": month_date.strftime("%Y-%m-01"),
                "plan": month_plan if month_plan > 0 else None,
                "actual": month_actual if month_actual > 0 else None
            })
    
    else:
        # All historical data
        trend_data = [
            {
                "date": r.date.strftime("%d-%b-%Y"),
                "date_full": r.date.strftime("%Y-%m-%d"),
                "plan": r.plan,
                "actual": r.actual
            } for r in records
        ]
    
    # Calculate summary
    summary = calculate_summary(trend_data)

    # Last updated timestamp for this plant (true modification time, not just business date)
    last_dt = db.query(func.max(DailyProduction.updated_at)).filter(DailyProduction.plant_id == plant_id).scalar()
    last_updated = last_dt.isoformat() if last_dt else None

    return {
        "trend": trend_data,
        "summary": summary,
        "last_updated": last_updated,
    }


def get_empty_summary():
    return {
        "plan_total": 0,
        "actual_total": 0,
        "variance": 0,
        "achieved_percent": 0
    }


def calculate_summary(trend_data):
    """Calculate summary metrics from trend data"""
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


from fastapi import HTTPException
import traceback

@router.get("/history/{plant_id}")
def get_production_history(plant_id: int, db: Session = Depends(get_db)):
    try:
        records = (
            db.query(DailyProduction)
            .filter(DailyProduction.plant_id == plant_id)
            .order_by(DailyProduction.date.desc())
            .limit(30)   # Return only latest 30 records
            .all()
        )

        return {
            "history": [
                {
                    "date": r.date.strftime("%Y-%m-%d") if r.date else None,
                    "month": r.date.strftime("%B") if r.date else None,
                    "plan": r.plan,
                    "actual": r.actual,
                    "variance": round((r.actual or 0) - (r.plan or 0), 2),
                    "achieved_percent": round(
                        ((r.actual or 0) / r.plan * 100) if r.plan and r.plan > 0 else 0,
                        2,
                    ),
                }
                for r in records
            ]
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))