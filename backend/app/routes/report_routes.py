from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.report_schema import ReportRequest

from app.services.report_service import (
    generate_monthly_report,
    generate_quarterly_report,
    generate_yearly_report
)

router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


@router.post("/monthly")
def monthly_report(
    request: ReportRequest,
    db: Session = Depends(get_db)
):
    return generate_monthly_report(
        db,
        request.plant_id,
        request.year,
        request.month
    )


@router.post("/quarterly")
def quarterly_report(
    request: ReportRequest,
    db: Session = Depends(get_db)
):
    return generate_quarterly_report(
        db,
        request.plant_id,
        request.year,
        request.quarter
    )


@router.post("/yearly")
def yearly_report(
    request: ReportRequest,
    db: Session = Depends(get_db)
):
    return generate_yearly_report(
        db,
        request.plant_id,
        request.year
    )