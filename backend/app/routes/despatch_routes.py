from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.models import CustomerDespatch
from app.schemas.schemas import DespatchEntry
from datetime import date, datetime
from typing import Optional
import calendar

router = APIRouter(prefix="/despatch", tags=["Customer Despatch"])

# Once a record exists for a given (plant, date, customer) it is
# permanently locked — no edit, update, refresh, overwrite, or delete.
KPI_LOCK_MESSAGE = "Data already submitted and locked."


@router.get("/check/{plant_id}/{entry_date}")
def check_despatch_lock(plant_id: int, entry_date: date, customer_name: str, db: Session = Depends(get_db)):
    existing = db.query(CustomerDespatch).filter(
        CustomerDespatch.plant_id == plant_id,
        CustomerDespatch.date == entry_date,
        CustomerDespatch.customer_name == customer_name
    ).first()
    return {"locked": existing is not None, "message": KPI_LOCK_MESSAGE if existing else None}


@router.post("/entry")
def add_despatch(entry: DespatchEntry, db: Session = Depends(get_db)):
    existing = db.query(CustomerDespatch).filter(
        CustomerDespatch.plant_id == entry.plant_id,
        CustomerDespatch.date == entry.date,
        CustomerDespatch.customer_name == entry.customer_name
    ).first()

    if existing is not None:
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)

    new_entry = CustomerDespatch(
        plant_id=entry.plant_id,
        date=entry.date,
        customer_name=entry.customer_name,
        month_plan=entry.month_plan,
        mtd_actual=entry.mtd_actual,
        updated_at=datetime.now()
    )
    db.add(new_entry)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # The unique constraint on (plant_id, date, customer_name) is the
        # real, race-condition-proof guarantee — this catch is what
        # fires if two saves for the SAME customer land at the same
        # instant (the SELECT-based check above is only a fast
        # pre-check). Re-check whether it's specifically that duplicate
        # scenario so an unrelated integrity error (e.g. a bad plant_id)
        # isn't mislabeled as "already locked".
        still_exists = db.query(CustomerDespatch).filter(
            CustomerDespatch.plant_id == entry.plant_id,
            CustomerDespatch.date == entry.date,
            CustomerDespatch.customer_name == entry.customer_name
        ).first()
        if still_exists is not None:
            raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)
        raise HTTPException(status_code=400, detail=f"Could not save despatch entry: {exc}")
    return {"message": "Despatch data saved!"}


@router.get("/latest-actual/{plant_id}")
def get_latest_actual(plant_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(CustomerDespatch)
        .filter(CustomerDespatch.plant_id == plant_id)
        .order_by(CustomerDespatch.date.desc())
        .first()
    )
    if not record:
        return {"mtd_actual": None, "month_plan": None, "customer_name": None, "date": None}
    return {
        "mtd_actual": record.mtd_actual,
        "month_plan": record.month_plan,
        "customer_name": record.customer_name,
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
        "month_plan_total": 0,
        "mtd_actual_total": 0,
        "variance": 0,
        "achieved_percent": 0
    }


def calculate_summary(trend_data):
    """Calculate summary metrics"""
    if not trend_data:
        return get_empty_summary()
    
    month_plan_total = sum(t["month_plan"] for t in trend_data if t["month_plan"] is not None)
    mtd_actual_total = sum(t["mtd_actual"] for t in trend_data if t["mtd_actual"] is not None)
    variance = mtd_actual_total - month_plan_total
    achieved_percent = (mtd_actual_total / month_plan_total * 100) if month_plan_total > 0 else 0
    
    return {
        "month_plan_total": round(month_plan_total, 2),
        "mtd_actual_total": round(mtd_actual_total, 2),
        "variance": round(variance, 2),
        "achieved_percent": round(achieved_percent, 2)
    }


@router.get("/trend/{plant_id}")
def get_despatch_trend(
    plant_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    view: str = "daily",
    db: Session = Depends(get_db)
):
    """Get despatch trend data"""
    
    if year is None or month is None:
        return {"customers": [], "summary": get_empty_summary()}
    
    query = db.query(CustomerDespatch).filter(
        CustomerDespatch.plant_id == plant_id,
        extract('year', CustomerDespatch.date) == year,
        extract('month', CustomerDespatch.date) == month
    )
    
    records = query.order_by(CustomerDespatch.date).all()
    
    # Group by customer
    customers_dict = {}
    for r in records:
        if r.customer_name not in customers_dict:
            customers_dict[r.customer_name] = {
                "customer_name": r.customer_name,
                "month_plan": r.month_plan,
                "mtd_actual": r.mtd_actual
            }
        else:
            customers_dict[r.customer_name]["mtd_actual"] = r.mtd_actual
    
    customers = list(customers_dict.values())
    
    # Calculate summary
    summary = calculate_summary(customers)

    # Last updated timestamp for this plant (true modification time)
    last_dt = db.query(func.max(CustomerDespatch.updated_at)).filter(CustomerDespatch.plant_id == plant_id).scalar()
    last_updated = last_dt.isoformat() if last_dt else None

    return {
        "customers": customers,
        "summary": summary,
        "last_updated": last_updated,
    }


@router.get("/history/{plant_id}")
def get_despatch_history(plant_id: int, limit: Optional[int] = 30, db: Session = Depends(get_db)):
    """Returns the latest `limit` records (default 30), newest first.
    Older records are never deleted — pass a larger `limit` (or omit it
    via limit=0/None) to retrieve more/all history."""
    query = (
        db.query(CustomerDespatch)
        .filter(CustomerDespatch.plant_id == plant_id)
        .order_by(CustomerDespatch.date.desc())
    )
    records = query.all() if not limit or limit <= 0 else query.limit(limit).all()
    return {
        "history": [
            {
                "date": r.date.strftime("%Y-%m-%d"),
                "month": r.date.strftime("%B"),
                "customer_name": r.customer_name,
                "month_plan": r.month_plan,
                "mtd_actual": r.mtd_actual,
                "variance": round((r.mtd_actual or 0) - (r.month_plan or 0), 2),
                "achieved_percent": round((r.mtd_actual / r.month_plan * 100) if r.month_plan and r.month_plan > 0 else 0, 2)
            } for r in records
        ]
    }

@router.get("/monthly-trend/{plant_id}")
def get_despatch_monthly_trend(
    plant_id: int,
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get month-wise aggregated despatch totals for a full year (Jan-Dec)."""
    if year is None:
        return {"monthly": []}

    records = db.query(CustomerDespatch).filter(
        CustomerDespatch.plant_id == plant_id,
        extract('year', CustomerDespatch.date) == year
    ).all()

    monthly: dict = {}
    for r in records:
        m = r.date.month
        if m not in monthly:
            monthly[m] = {"month": m, "month_name": r.date.strftime("%b"), "month_plan": 0, "mtd_actual": 0}
        monthly[m]["month_plan"] += (r.month_plan or 0)
        monthly[m]["mtd_actual"] += (r.mtd_actual or 0)

    result = sorted(monthly.values(), key=lambda x: x["month"])
    return {"monthly": result}