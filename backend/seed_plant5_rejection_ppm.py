"""
role_access_routes.py
---------------------
Handles role-based data-entry access.

Key rules:
  - One person (name + email) can hold MULTIPLE roles for the same plant.
  - Each (plant_id, person_name, email, role) combination is unique.
  - Verification requires all four fields to match exactly.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from app.database import get_db
from app.models.models import RoleAccess
from app.schemas.schemas import RoleVerification
from pydantic import BaseModel

router = APIRouter(prefix="/role-access", tags=["Role Access"])


# ── Verify ────────────────────────────────────────────────────────────────────

@router.post("/verify")
def verify_role_access(payload: RoleVerification, db: Session = Depends(get_db)):
    """
    Validate that the person is authorized for the requested role in this plant.
    All four fields (plant_id, person_name, email, role) must match.
    """
    role_normalized = (
        payload.role.strip().lower()
        .replace(" ", "_")
        .replace("-", "_")
    )

    all_records = (
        db.query(RoleAccess)
        .filter(
            RoleAccess.plant_id == payload.plant_id,
            RoleAccess.person_name == payload.person_name.strip(),
            RoleAccess.email == payload.email.strip().lower(),
        )
        .all()
    )

    matched = None
    for rec in all_records:
        db_role_norm = (
            rec.role.strip().lower()
            .replace(" ", "_")
            .replace("-", "_")
        )
        if db_role_norm == role_normalized:
            matched = rec
            break

    if not matched:
        raise HTTPException(
            status_code=403,
            detail=f"No access record found for role '{payload.role}'. "
                   f"Contact your administrator."
        )

    return {
        "success":     True,
        "role":        role_normalized,
        "email":       matched.email,
        "person_name": matched.person_name,
    }


# ── List all roles for a plant (diagnostic) ───────────────────────────────────

@router.get("/list/{plant_id}")
def list_plant_roles(plant_id: int, db: Session = Depends(get_db)):
    """
    Returns every role_access row for a plant.
    Use this to verify what is actually in the database.
    GET /role-access/list/5
    """
    records = db.query(RoleAccess).filter(RoleAccess.plant_id == plant_id).all()
    return {
        "plant_id": plant_id,
        "count":    len(records),
        "records":  [
            {"id": r.id, "role": r.role, "person_name": r.person_name, "email": r.email}
            for r in records
        ],
    }


# ── Add a single role assignment ──────────────────────────────────────────────

@router.post("/assign")
def assign_role(payload: RoleVerification, db: Session = Depends(get_db)):
    """
    Create a new role assignment.
    Duplicate (plant+person+email+role) is rejected gracefully.
    """
    role_norm = (
        payload.role.strip().lower()
        .replace(" ", "_")
        .replace("-", "_")
    )
    record = RoleAccess(
        plant_id    = payload.plant_id,
        person_name = payload.person_name.strip(),
        email       = payload.email.strip().lower(),
        role        = role_norm,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"success": True, "id": record.id, "role": role_norm}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This role is already assigned to this person for this plant."
        )


# ── Bulk seed all roles ────────────────────────────────────────────────────────

class BulkSeedRequest(BaseModel):
    records: List[RoleVerification]

@router.post("/bulk-seed")
def bulk_seed_roles(payload: BulkSeedRequest, db: Session = Depends(get_db)):
    """
    Insert multiple role assignments in one call.
    Skips duplicates silently.
    Use via FastAPI /docs to seed the live SQL Server database.

    Example body:
    {
      "records": [
        {"plant_id": 5, "person_name": "A.Manikandan",
         "email": "ca.manikandan@ranegroup.com", "role": "rejection_ppm"}
      ]
    }
    """
    inserted = []
    skipped  = []

    for item in payload.records:
        role_norm = (
            item.role.strip().lower()
            .replace(" ", "_")
            .replace("-", "_")
        )
        existing = db.query(RoleAccess).filter(
            RoleAccess.plant_id    == item.plant_id,
            RoleAccess.person_name == item.person_name.strip(),
            RoleAccess.email       == item.email.strip().lower(),
            RoleAccess.role        == role_norm,
        ).first()

        if existing:
            skipped.append(role_norm)
            continue

        db.add(RoleAccess(
            plant_id    = item.plant_id,
            person_name = item.person_name.strip(),
            email       = item.email.strip().lower(),
            role        = role_norm,
        ))
        inserted.append(role_norm)

    db.commit()
    return {"inserted": inserted, "skipped": skipped}