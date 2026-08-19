"""
email_recipient_routes.py
--------------------------
API for the Admin Dashboard's "Email Services" tab. Lets an admin manage
who receives automated reminder / escalation / report emails — by Plant
and Department — without touching any code.

    GET    /admin/email-recipients                 -> list all
    POST   /admin/email-recipients                 -> create one
    PUT    /admin/email-recipients/{id}             -> edit one
    DELETE /admin/email-recipients/{id}             -> delete one
    PATCH  /admin/email-recipients/{id}/status       -> activate/deactivate
    GET    /admin/email-recipients/export            -> download current data as .xlsx
    GET    /admin/email-recipients/template          -> download a blank .xlsx template
    POST   /admin/email-recipients/import            -> upload an .xlsx and upsert recipients
    POST   /admin/email-recipients/sync              -> re-read email_users.xlsx already on the server

Bidirectional Excel <-> DB <-> Admin Dashboard sync
-----------------------------------------------------
Every mutating route below (create/update/delete/status/import) calls
svc.write_email_recipients_excel_to_disk() right after committing, so
backend/data/email_users.xlsx is rewritten from the database on every
change — that's the DB -> Excel direction. The Excel -> DB direction is
covered by /import (manual upload), /sync (re-read the file already on
the server), the startup auto-load in main.py, and a periodic background
job (see app/scheduler.py) that re-reads the file every few minutes so
edits made directly to it are picked up automatically, not just at
startup. All of these funnel through the SAME upsert logic keyed on
(plant_id, department, recipient_type), so nothing is ever duplicated —
re-importing the same file twice, or re-running the sync job repeatedly,
always converges to the same rows.

Every route requires a valid Admin JWT (see app.services.auth.get_current_admin),
matching the pattern already used by user_import_routes.py / admin_routes.py.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import email_recipient_service as svc
from app.services.auth import get_current_admin
from app import scheduler as scheduler_module

router = APIRouter(
    prefix="/admin/email-recipients",
    tags=["Admin - Email Services"],
    dependencies=[Depends(get_current_admin)],
)

ALLOWED_EXTENSIONS = (".xlsx", ".xls")
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB — generous for a recipient list


def _to_out(r) -> dict:
    return {
        "id": r.id,
        "plant_id": r.plant_id,
        "department": r.department,
        "recipient_type": r.recipient_type,
        "name": r.name,
        "email": r.email,
        "is_active": r.is_active if r.is_active is not None else True,
    }


@router.get("")
def list_email_recipients(db: Session = Depends(get_db)):
    return [_to_out(r) for r in svc.list_recipients(db)]


@router.get("/export")
def export_email_recipients(db: Session = Depends(get_db)):
    """Download every Email Services recipient (all plants) as a single .xlsx file."""
    content = svc.export_email_recipients_to_excel(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=email_services_recipients.xlsx"},
    )


@router.get("/template")
def download_email_recipients_template():
    """Download a blank .xlsx template (headers + example rows) for bulk-adding recipients."""
    content = svc.generate_email_recipients_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=email_users_template.xlsx"},
    )


@router.post("/import")
async def import_email_recipients(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload an .xlsx and add/update Email Services recipients (validates
    emails, skips bad rows with a reported error, never creates duplicates —
    see email_recipient_service.import_email_recipients_from_excel). The
    uploaded file also becomes the new on-disk email_users.xlsx, exactly
    like Data Entry Users' /admin/upload-user-master."""
    filename = (file.filename or "").lower()
    if not filename.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx or .xls file.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (max 5 MB).")

    try:
        summary = svc.import_email_recipients_from_excel(db, contents)
    except ValueError as ve:
        # Structural problem (bad file / missing columns) — whole import rejected.
        scheduler_module.record_manual_sync("email_recipients", None, error=str(ve))
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        scheduler_module.record_manual_sync("email_recipients", None, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")

    # Rewrite the canonical on-disk file from the now-updated DB (rather
    # than saving the raw upload verbatim) so it reflects the merged/
    # deduped result, not just whatever the admin happened to upload.
    svc.write_email_recipients_excel_to_disk()
    scheduler_module.record_manual_sync("email_recipients", summary)

    return {"success": True, **summary}


@router.post("/sync")
def sync_email_recipients_from_disk(db: Session = Depends(get_db)):
    """Re-read whatever email_users.xlsx currently lives on the server
    and upsert from it — the manual equivalent of /admin/sync for Data
    Entry Users, for when someone has edited the file directly. Also
    updates the same in-memory sync-status the periodic job updates
    (see app/scheduler.py), so a manual sync shows up in
    /admin/email-recipients/sync-status too."""
    if not svc.EMAIL_USERS_XLSX_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"email_users.xlsx not found at {svc.EMAIL_USERS_XLSX_PATH}. Use Import to upload one first.",
        )
    try:
        summary = svc.import_email_recipients_from_file(db, str(svc.EMAIL_USERS_XLSX_PATH))
    except ValueError as ve:
        scheduler_module.record_manual_sync("email_recipients", None, error=str(ve))
        raise HTTPException(status_code=400, detail=str(ve))
    scheduler_module.record_manual_sync("email_recipients", summary)
    return {"success": True, **summary}


@router.get("/sync-status")
def email_recipients_sync_status():
    """Feeds the Admin Dashboard's "Excel sync" status panel for Email
    Services: when the email_users.xlsx <-> DB sync last ran, what it
    did, and whether the file currently exists on disk."""
    from datetime import datetime, timezone
    status = scheduler_module.get_sync_status()["email_recipients"]
    path = svc.EMAIL_USERS_XLSX_PATH
    return {
        **status,
        "file_exists": path.exists(),
        "file_path": str(path),
        "file_modified": (
            datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            if path.exists() else None
        ),
    }


class RecipientCreate(BaseModel):
    recipient_type: str  # staff_incharge | plant_head | president | report_recipient | overall_summary_recipient
    email: str
    department: Optional[str] = None
    plant_id: Optional[int] = None
    name: Optional[str] = None
    is_active: bool = True


class RecipientUpdate(BaseModel):
    recipient_type: str
    email: str
    department: Optional[str] = None
    plant_id: Optional[int] = None
    name: Optional[str] = None
    is_active: bool = True


@router.post("")
def create_email_recipient(payload: RecipientCreate, db: Session = Depends(get_db)):
    try:
        record = svc.create_recipient(
            db,
            recipient_type=payload.recipient_type,
            email=payload.email,
            department=payload.department,
            plant_id=payload.plant_id,
            name=payload.name,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    svc.write_email_recipients_excel_to_disk()
    return {"success": True, "recipient": _to_out(record)}


@router.put("/{recipient_id}")
def update_email_recipient(recipient_id: int, payload: RecipientUpdate, db: Session = Depends(get_db)):
    try:
        record = svc.update_recipient(
            db,
            recipient_id,
            recipient_type=payload.recipient_type,
            email=payload.email,
            department=payload.department,
            plant_id=payload.plant_id,
            name=payload.name,
            is_active=payload.is_active,
            clear_plant_id=payload.plant_id is None,
            clear_department=payload.department is None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    svc.write_email_recipients_excel_to_disk()
    return {"success": True, "recipient": _to_out(record)}


@router.delete("/{recipient_id}")
def delete_email_recipient(recipient_id: int, db: Session = Depends(get_db)):
    try:
        svc.delete_recipient(db, recipient_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    svc.write_email_recipients_excel_to_disk()
    return {"success": True, "message": "Email recipient deleted."}


@router.patch("/{recipient_id}/status")
def toggle_email_recipient_status(recipient_id: int, is_active: bool, db: Session = Depends(get_db)):
    try:
        record = svc.set_active_status(db, recipient_id, is_active)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    svc.write_email_recipients_excel_to_disk()
    return {"success": True, "recipient": _to_out(record)}