"""
kpi_lock.py
-----------
Shared helper for the date-wise KPI entry lock.

Rule: only one record may exist per (Plant, EntryDate, KPIType). Once a
record exists for that combination it is permanently locked — no edit,
update, or delete is ever allowed through the API. The POST /entry
endpoints in each department router use `enforce_kpi_lock()` before
inserting a new row, and the underlying tables also carry a DB-level
UNIQUE constraint as a second line of defense against race conditions.
"""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

KPI_LOCK_MESSAGE = "Data for this date has already been submitted and cannot be modified."


def enforce_kpi_lock(existing_record) -> None:
    """Raise 409 Conflict if a record already exists for this (date, KPI type)."""
    if existing_record is not None:
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)


def commit_or_lock_conflict(db) -> None:
    """
    Commit the session; if the DB-level UNIQUE constraint rejects the insert
    (e.g. a concurrent request beat this one to it), surface the same
    409 lock message instead of a raw integrity error.
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=KPI_LOCK_MESSAGE)