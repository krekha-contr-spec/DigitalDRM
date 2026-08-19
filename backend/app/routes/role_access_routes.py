"""
role_access_routes.py
---------------------
Handles role-based data-entry access.

Key rules:
  - A plant + department (role) can have MULTIPLE active Data Entry
    Users at once — e.g. two people both managing Plant 2 - Manpower.
    There is no "one in-charge per department" restriction.
  - What must stay unique is (plant_id, role, person_name, email): the
    same person can't be added twice for the same slot, but different
    people can share it.
  - Verification requires all four fields to match exactly — this
    already worked correctly for multiple people per slot before this
    change, since it looks up by the full (plant_id, person_name,
    email, role) tuple rather than assuming a single record per
    plant+role.

Bidirectional Excel sync (Data Entry Users <-> backend/data/users.xlsx)
-------------------------------------------------------------------------
  - Dashboard -> Excel: every create/update/delete/status-toggle below
    calls _sync_excel_to_disk() straight after committing, so
    users.xlsx on disk is regenerated from the database immediately —
    no manual export needed for the file to stay current.
  - Excel -> Dashboard: app/scheduler.py runs a periodic job (and
    app/main.py runs one at startup) that re-reads users.xlsx and
    upserts any changes into role_access. A row added/edited directly
    in Excel appears in the Dashboard within that interval; a row
    removed from Excel is marked Inactive (not hard-deleted) so a
    blank/corrupted file can never silently wipe data — this mirrors
    the same safety choice already made for Email Services' Excel
    sync (see email_recipient_service.py).
  - Identity / no-duplicates: a Dashboard "Add" is rejected with 409
    only if the EXACT same (plant_id, role, person_name, email) already
    exists — the same identity the Excel importer upserts against —
    never merely because the plant+role slot already has someone else
    in it.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import io
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.deps import require_admin, require_plant_head
from app.models.models import RoleAccess
from app.schemas.schemas import RoleVerification, RoleAccessCreate, RoleAccessUpdate, PlantHeadAddUserRequest
from app.services.user_import_service import export_users_to_excel, write_users_excel_to_disk
from app.services import approval_service

logger = logging.getLogger("digitaldrm.role_access")

router = APIRouter(prefix="/role-access", tags=["Role Access"])

USER_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "users.xlsx"


def _sync_excel_to_disk(db: Session) -> Optional[str]:
    """Best-effort DB -> Excel mirror. Never raises — a failure here must
    not undo or mask the database mutation that already succeeded.
    Returns None on success, or an error message string on failure, so
    callers can surface it to the Admin Dashboard (via _to_dict's
    excel_sync_warning) instead of it only ever showing up in server
    logs where nobody using the UI would ever see it."""
    try:
        write_users_excel_to_disk(db, USER_MASTER_PATH)
        return None
    except Exception as exc:
        logger.error("[ROLE ACCESS] Could not write users.xlsx to disk: %s", exc, exc_info=True)
        return (
            f"The change was saved, but writing it to users.xlsx on disk failed: {exc}. "
            f"Use 'Sync from Excel' once the underlying issue (permissions/disk space) "
            f"is fixed to bring the file back in line with the database."
        )


def _to_dict(rec: RoleAccess) -> dict:
    return {
        "id": rec.id,
        "plant_id": rec.plant_id,
        "role": rec.role,
        "person_name": rec.person_name,
        "email": rec.email,
        "employee_id": rec.employee_id,
        "is_active": bool(rec.is_active) if rec.is_active is not None else True,
    }


# ── Verify ────────────────────────────────────────────────────────────────────

@router.post("/verify")
def verify_role_access(payload: RoleVerification, db: Session = Depends(get_db)):
    
    """
    Validate that the person is authorized for the requested role in this plant.
    All four fields (plant_id, person_name, email, role) must match.
    """
    # Normalize role string: lowercase, underscores
    # Frontend sends e.g. "Rejection PPM" → normalize to "rejection_ppm"
    role_normalized = (
        payload.role.strip().lower()
        .replace(" ", "_")
        .replace("-", "_")
    )

    # Build candidate role values to match against DB
    # DB may store role as "rejection_ppm", "Rejection PPM", etc.
    # We compare case-insensitively on the DB side via Python filter
    all_records = (
        db.query(RoleAccess)
        .filter(
            RoleAccess.plant_id == payload.plant_id,
            RoleAccess.person_name == payload.person_name.strip(),
            RoleAccess.email == payload.email.strip().lower(),
        )
        .all()
    )

    # Find a record whose role matches (normalized comparison)
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

    # Return the normalized role string the frontend expects
    return {
        "success": True,
        "role": role_normalized,
        "email": matched.email,
        "person_name": matched.person_name,
    }


# ── List roles for a person ───────────────────────────────────────────────────

@router.get("/person-roles/{plant_id}")
def get_person_roles(plant_id: int, person_name: str, email: str, db: Session = Depends(get_db)):
    """Return all roles assigned to a person in a plant (for UI dropdowns)."""
    records = (
        db.query(RoleAccess)
        .filter(
            RoleAccess.plant_id == plant_id,
            RoleAccess.person_name == person_name.strip(),
            RoleAccess.email == email.strip().lower(),
        )
        .all()
    )
    return {"roles": [r.role for r in records]}


# ── Add a role assignment ─────────────────────────────────────────────────────

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
        plant_id=payload.plant_id,
        person_name=payload.person_name.strip(),
        email=payload.email.strip().lower(),
        role=role_norm,
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


# ── Admin Dashboard "Data Entry Users" CRUD ─────────────────────────────────
# Everything below requires an Admin JWT (Data Entry Users get a 403), and
# every mutation regenerates users.xlsx on disk immediately afterward — see
# _sync_excel_to_disk() at the top of this file for the Dashboard->Excel
# direction, and app/scheduler.py / app/main.py for the Excel->Dashboard
# direction (periodic + startup re-read).

@router.get("/list", dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    """All Data Entry Users, across every plant — feeds the Admin
    Dashboard's grouped-by-plant table."""
    records = db.query(RoleAccess).order_by(RoleAccess.plant_id, RoleAccess.role).all()
    return [_to_dict(r) for r in records]


@router.post("/user", dependencies=[Depends(require_admin)])
def create_user(payload: RoleAccessCreate, db: Session = Depends(get_db)):
    """
    Creates a new Data Entry User (department in-charge). A plant +
    department can now have MULTIPLE active Data Entry Users at once
    (e.g. two people both managing Plant 2 - Manpower) — the identity
    that must stay unique is (plant_id, role, person_name, email), i.e.
    the same person can't be added twice for the same slot, but
    different people can share it. That's enforced by the DB's
    uq_role_access_plant_person_email_role constraint below; this
    endpoint doesn't reject on plant+role alone anymore.
    """
    role_norm = payload.role.strip().lower().replace(" ", "_").replace("-", "_")

    record = RoleAccess(
        plant_id=payload.plant_id,
        role=role_norm,
        person_name=payload.person_name.strip(),
        email=payload.email.strip().lower(),
        employee_id=(payload.employee_id or None),
        is_active=payload.is_active,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This exact person is already assigned to this role for this plant.",
        )

    excel_warning = _sync_excel_to_disk(db)
    out = _to_dict(record)
    if excel_warning:
        out["excel_sync_warning"] = excel_warning
    return out


@router.put("/user/{user_id}", dependencies=[Depends(require_admin)])
def update_user(user_id: int, payload: RoleAccessUpdate, db: Session = Depends(get_db)):
    """Multiple active Data Entry Users can share the same plant +
    department — see create_user() above. Renaming/moving a record
    to a plant+role+person+email combo that already exists is still
    rejected (same DB constraint), since that would be an exact
    duplicate of an existing row rather than a second person."""
    record = db.query(RoleAccess).filter(RoleAccess.id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Data Entry User not found.")

    if payload.plant_id is not None:
        record.plant_id = payload.plant_id
    if payload.role is not None:
        record.role = payload.role.strip().lower().replace(" ", "_").replace("-", "_")
    if payload.person_name is not None:
        record.person_name = payload.person_name.strip()
    if payload.email is not None:
        record.email = payload.email.strip().lower()
    if payload.employee_id is not None:
        record.employee_id = payload.employee_id or None
    if payload.is_active is not None:
        record.is_active = payload.is_active

    try:
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This exact role assignment already exists.")

    excel_warning = _sync_excel_to_disk(db)
    out = _to_dict(record)
    if excel_warning:
        out["excel_sync_warning"] = excel_warning
    return out


@router.delete("/user/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    record = db.query(RoleAccess).filter(RoleAccess.id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Data Entry User not found.")

    db.delete(record)
    db.commit()

    excel_warning = _sync_excel_to_disk(db)
    out = {"success": True, "message": "Data Entry User deleted."}
    if excel_warning:
        out["excel_sync_warning"] = excel_warning
    return out


@router.patch("/user/{user_id}/status", dependencies=[Depends(require_admin)])
def set_status(user_id: int, is_active: bool, db: Session = Depends(get_db)):
    record = db.query(RoleAccess).filter(RoleAccess.id == user_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Data Entry User not found.")

    record.is_active = is_active
    db.commit()
    db.refresh(record)

    excel_warning = _sync_excel_to_disk(db)
    out = _to_dict(record)
    if excel_warning:
        out["excel_sync_warning"] = excel_warning
    return out


@router.post("/plant-head/request-add", dependencies=[Depends(require_plant_head)])
def plant_head_request_add(
    payload: PlantHeadAddUserRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_plant_head),
):
    """
    A Plant Head asks to add a new Data Entry User for their OWN plant
    (current_user.plant_id from their JWT — never taken from the
    request body, so a Plant Head can't request a change for a
    different plant). This does NOT touch role_access directly — it
    creates a pending UserApprovalRequest and emails the configured
    Admin recipient(s) an Approve/Reject link. See approval_service.py.
    """
    req = approval_service.create_add_request(
        db,
        plant_id=current_user.plant_id,
        role=payload.role,
        person_name=payload.person_name,
        email=payload.email,
        employee_id=payload.employee_id,
        requested_by_username=current_user.username,
        requested_by_email=None,
    )
    return {
        "success": True,
        "message": "Request submitted. An Admin will need to approve this before the user is added.",
        "request_id": req.id,
        "status": req.status,
    }


@router.post("/plant-head/request-remove/{user_id}", dependencies=[Depends(require_plant_head)])
def plant_head_request_remove(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_plant_head),
):
    """
    A Plant Head asks to deactivate an existing Data Entry User. Must
    belong to the Plant Head's OWN plant (from their JWT) — a 404 is
    returned (not 403) if the record exists but belongs to a different
    plant, so this can't be used to probe for other plants' user IDs.
    On approval, the user is marked Inactive — never hard-deleted, per
    requirement.
    """
    record = (
        db.query(RoleAccess)
        .filter(RoleAccess.id == user_id, RoleAccess.plant_id == current_user.plant_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Data Entry User not found for your plant.")
    if not record.is_active:
        raise HTTPException(status_code=400, detail="This user is already inactive.")

    req = approval_service.create_remove_request(
        db,
        plant_id=current_user.plant_id,
        target_user_id=user_id,
        requested_by_username=current_user.username,
        requested_by_email=None,
    )
    return {
        "success": True,
        "message": "Request submitted. An Admin will need to approve this before the user is deactivated.",
        "request_id": req.id,
        "status": req.status,
    }


@router.get("/plant-head/my-users", dependencies=[Depends(require_plant_head)])
def plant_head_list_my_users(db: Session = Depends(get_db), current_user=Depends(require_plant_head)):
    """Read-only list of this Plant Head's OWN plant's Data Entry Users
    (active and inactive), so the 'Manage Team' screen can show who to
    request removal for. Plant-scoped from the JWT — never exposes
    another plant's users."""
    records = (
        db.query(RoleAccess)
        .filter(RoleAccess.plant_id == current_user.plant_id)
        .order_by(RoleAccess.role, RoleAccess.person_name)
        .all()
    )
    return [_to_dict(r) for r in records]


@router.get("/plant-head/my-requests", dependencies=[Depends(require_plant_head)])
def plant_head_list_my_requests(db: Session = Depends(get_db), current_user=Depends(require_plant_head)):
    """This Plant Head's own submitted add/remove requests and their
    current status (pending/approved/rejected/expired), so they can see
    the outcome without needing Admin to tell them."""
    from app.services import approval_service
    all_requests = approval_service.list_requests(db)
    return [r for r in all_requests if r["requested_by_username"] == current_user.username]


@router.get("/plant-head/plant-info", dependencies=[Depends(require_plant_head)])
def plant_head_plant_info(db: Session = Depends(get_db), current_user=Depends(require_plant_head)):
    """Tiny helper so the frontend can show 'Plant X' without needing a
    separate Plants list endpoint just for this."""
    from app.models.models import Plant
    plant = db.query(Plant).filter(Plant.id == current_user.plant_id).first()
    return {"plant_id": current_user.plant_id, "plant_name": plant.name if plant else f"Plant {current_user.plant_id}"}


@router.get("/export", dependencies=[Depends(require_admin)])
def export_users(db: Session = Depends(get_db)):
    """Downloads the exact same workbook that's kept mirrored on disk at
    backend/data/users.xlsx — same columns the Excel->DB importer
    accepts, so a downloaded/edited copy can be re-uploaded (via
    /admin/upload-user-master) or just dropped back at that path."""
    data = export_users_to_excel(db)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=data_entry_users.xlsx"},
    )