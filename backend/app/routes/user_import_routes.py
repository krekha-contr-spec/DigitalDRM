"""
user_import_routes.py
----------------------
API for the "Data Entry Users" admin page:
  - POST /role-access/import  — upload an .xlsx and upsert RoleAccess rows
  - GET  /role-access/list    — list current Data Entry Users for the table

Shares the /role-access prefix with role_access_routes.py (verification /
assignment) — this file only adds import + listing, nothing else changes.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import RoleAccess
from app.services.user_import_service import import_users_from_excel, export_users_to_excel

from app.services.auth import get_current_admin
from pydantic import BaseModel

router = APIRouter(prefix="/role-access", tags=["Role Access"], dependencies=[Depends(get_current_admin)])

ALLOWED_EXTENSIONS = (".xlsx", ".xls")
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB — generous for a user list


@router.get("/export")
def export_data_entry_users(db: Session = Depends(get_db)):
    """Download every Data Entry User (all plants) as a single .xlsx file."""
    content = export_users_to_excel(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=data_entry_users.xlsx"},
    )


@router.post("/import")
async def import_data_entry_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload an Excel file and upsert Data Entry Users (RoleAccess rows)."""
    filename = (file.filename or "").lower()
    if not filename.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx or .xls file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 5 MB).")

    try:
        summary = import_users_from_excel(db, contents)
    except ValueError as ve:
        # Structural problem (bad file / missing columns) — whole import rejected.
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")

    return {"success": True, **summary}


@router.get("/list")
def list_data_entry_users(db: Session = Depends(get_db)):
    """Return all Data Entry Users for the admin table."""
    records = (
        db.query(RoleAccess)
        .order_by(RoleAccess.plant_id, RoleAccess.role, RoleAccess.person_name)
        .all()
    )
    return [
        {
            "id": r.id,
            "plant_id": r.plant_id,
            "role": r.role,
            "person_name": r.person_name,
            "email": r.email,
            "employee_id": r.employee_id,
            "is_active": r.is_active if r.is_active is not None else True,
        }
        for r in records
    ]


class UserCreate(BaseModel):
    plant_id: int
    role: str
    person_name: str
    email: str
    employee_id: str | None = None
    is_active: bool = True

class UserUpdate(BaseModel):
    plant_id: int
    role: str
    person_name: str
    email: str
    employee_id: str | None = None
    is_active: bool

@router.post("/user")
def create_data_entry_user(user: UserCreate, db: Session = Depends(get_db)):
    # Simple check if email/role exists for plant
    existing = db.query(RoleAccess).filter(
        RoleAccess.plant_id == user.plant_id,
        RoleAccess.role == user.role,
        RoleAccess.email == user.email,
        RoleAccess.person_name == user.person_name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists for this role and plant.")
    
    new_user = RoleAccess(
        plant_id=user.plant_id,
        role=user.role,
        person_name=user.person_name,
        email=user.email,
        employee_id=user.employee_id,
        is_active=user.is_active
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"success": True, "user": new_user}

@router.put("/user/{user_id}")
def update_data_entry_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):
    db_user = db.query(RoleAccess).filter(RoleAccess.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.plant_id = user.plant_id
    db_user.role = user.role
    db_user.person_name = user.person_name
    db_user.email = user.email
    db_user.employee_id = user.employee_id
    db_user.is_active = user.is_active
    
    db.commit()
    db.refresh(db_user)
    return {"success": True, "user": db_user}

@router.delete("/user/{user_id}")
def delete_data_entry_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(RoleAccess).filter(RoleAccess.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return {"success": True, "message": "User deleted"}

@router.patch("/user/{user_id}/status")
def toggle_data_entry_user_status(user_id: int, is_active: bool, db: Session = Depends(get_db)):
    db_user = db.query(RoleAccess).filter(RoleAccess.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.is_active = is_active
    db.commit()
    db.refresh(db_user)
    return {"success": True, "user": db_user}