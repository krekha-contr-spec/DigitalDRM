"""
user_admin_routes.py
---------------------
Data Entry Users Management module. EVERY route here requires a valid
Admin JWT (see app.deps.require_admin) — Data Entry Users get a 403 no
matter what they send. This is the only place Data Entry User accounts
(the `users` table rows with role != 'admin') can be created, edited,
deleted, activated/deactivated, or bulk-imported from Excel.

    GET    /admin/data-entry-users                 -> list all
    POST   /admin/data-entry-users                 -> create one
    PUT    /admin/data-entry-users/{id}             -> edit one
    DELETE /admin/data-entry-users/{id}             -> delete one
    PATCH  /admin/data-entry-users/{id}/activate    -> activate
    PATCH  /admin/data-entry-users/{id}/deactivate  -> deactivate
    POST   /admin/data-entry-users/import-excel     -> bulk import
"""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin, TokenPayload
from app.schemas.schemas import (
    DataEntryUserCreate,
    DataEntryUserOut,
    DataEntryUserUpdate,
)
from app.services import user_admin_service as svc

router = APIRouter(
    prefix="/admin/data-entry-users",
    tags=["Admin - Data Entry Users Management"],
    dependencies=[Depends(require_admin)],  # protects every route below
)


def _to_out(user) -> DataEntryUserOut:
    return DataEntryUserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        plant_id=user.plant_id,
        is_active=bool(user.is_active),
    )


@router.get("", response_model=list[DataEntryUserOut])
def list_users(db: Session = Depends(get_db)):
    return [_to_out(u) for u in svc.list_data_entry_users(db)]


@router.post("", response_model=DataEntryUserOut)
def create_user(payload: DataEntryUserCreate, db: Session = Depends(get_db)):
    try:
        user = svc.create_data_entry_user(
            db, payload.username, payload.password, payload.role, payload.plant_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_out(user)


@router.put("/{user_id}", response_model=DataEntryUserOut)
def update_user(user_id: int, payload: DataEntryUserUpdate, db: Session = Depends(get_db)):
    try:
        user = svc.update_data_entry_user(
            db,
            user_id,
            password=payload.password,
            role=payload.role,
            plant_id=payload.plant_id,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_out(user)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    try:
        svc.delete_data_entry_user(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"success": True, "message": "Data entry user deleted."}


@router.patch("/{user_id}/activate", response_model=DataEntryUserOut)
def activate_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = svc.set_active_status(db, user_id, True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _to_out(user)


@router.patch("/{user_id}/deactivate", response_model=DataEntryUserOut)
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = svc.set_active_status(db, user_id, False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _to_out(user)


@router.post("/import-excel")
async def import_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file.")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = svc.import_users_from_excel(db, str(tmp_path))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"success": True, **result}
