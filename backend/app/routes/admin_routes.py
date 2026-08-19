"""
admin_routes.py
----------------
Lets HR / the DRM coordinator manage users purely through
Excel, without anyone touching Python code:

  POST /admin/sync                     -> re-read the Excel file already
                                           on the server and sync the DB
  POST /admin/upload-user-master       -> upload a new users.xlsx
                                           and sync immediately
  GET  /admin/user-master/template     -> download a blank/starter template
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.user_import_service import import_users_from_file, import_users_from_excel, write_users_excel_to_disk
from app import scheduler as scheduler_module

from app.services.auth import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin - User Sync"], dependencies=[Depends(get_current_admin)])

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_MASTER_PATH = DATA_DIR / "users.xlsx"


@router.post("/sync")
def trigger_sync(db: Session = Depends(get_db)):
    """Re-read whatever Excel file currently lives on the server and sync
    it into the database right now (instead of waiting for the periodic
    background job — see app/scheduler.py). Also updates the same
    in-memory sync-status the periodic job updates, so a manual sync
    shows up in /admin/sync-status too.

    If users.xlsx doesn't exist on disk at all (e.g. the very first
    Dashboard->Excel write after a fresh install failed, or the file
    was manually deleted), this SELF-HEALS by generating it fresh from
    the current database instead of erroring — that's the only
    sensible "sync" when one side of a bidirectional sync is simply
    missing, and it means clicking "Sync from Excel" always leaves you
    with a users.xlsx that matches the database, one way or another.
    """
    if not USER_MASTER_PATH.exists():
        try:
            write_users_excel_to_disk(db, USER_MASTER_PATH)
        except Exception as exc:
            scheduler_module.record_manual_sync("role_access", None, error=str(exc))
            raise HTTPException(
                status_code=500,
                detail=(
                    f"users.xlsx did not exist at {USER_MASTER_PATH} and could not be "
                    f"created: {exc}. Check that the server process can write to that "
                    f"folder (permissions / disk space)."
                ),
            )
        result = {"created_from_database": True}
        scheduler_module.record_manual_sync("role_access", result)
        return {"success": True, "users": result}

    try:
        result = import_users_from_file(db, str(USER_MASTER_PATH))
    except (ValueError, FileNotFoundError) as exc:
        scheduler_module.record_manual_sync("role_access", None, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        # Catch-all so an unexpected DB error (e.g. a duplicate-key
        # IntegrityError from legacy data — see dedupe_role_access())
        # always comes back as a normal JSON 500 response instead of an
        # unhandled crash. An unhandled exception here can escape
        # FastAPI's response cycle entirely, which is why it showed up
        # in the browser as a CORS failure rather than a real error
        # message — CORS headers are only added to responses FastAPI
        # actually gets to finish building.
        db.rollback()
        scheduler_module.record_manual_sync("role_access", None, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=(
                f"Sync failed: {exc}. If this mentions ux_role_access_dedupe or a "
                f"duplicate key, call POST /admin/dedupe-role-access once to clean up "
                f"pre-existing duplicate rows, then try syncing again."
            ),
        )
    scheduler_module.record_manual_sync("role_access", result)
    return {"success": True, "users": result}


@router.post("/dedupe-role-access")
def dedupe_role_access_endpoint(db: Session = Depends(get_db)):
    """One-time cleanup for legacy role_access rows that already violate
    ux_role_access_dedupe (see dedupe_role_access() in
    user_import_service.py for the full explanation). Run this once if
    a sync ever reports 'likely pre-existing duplicate data', then
    re-run /admin/sync — the same rows won't collide again."""
    from app.services.user_import_service import dedupe_role_access
    try:
        result = dedupe_role_access(db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Dedupe failed: {exc}")
    return {"success": True, **result}


@router.post("/run-daily-all-plants-report")
def run_daily_all_plants_report_now(db: Session = Depends(get_db)):
    """Manually triggers the daily all-plants Overall Summary report
    right now instead of waiting for its 07:00 scheduled run (see
    app/scheduler.py's DAILY_ALL_PLANTS_REPORT_JOB_ID) — useful for
    testing that the report generates and emails correctly."""
    from app.routes.report_save_routes import run_daily_all_plants_report
    result = run_daily_all_plants_report(db, scheduler_module.DAILY_ALL_PLANTS_REPORT_RECIPIENT)
    if result.get("status") != "ok":
        raise HTTPException(status_code=500, detail=result.get("message", "Report generation failed"))
    return {"success": True, **result}


@router.get("/sync-status")
def sync_status():
    """Feeds the Admin Dashboard's "Excel sync" status panel: when the
    Data Entry Users Excel <-> DB sync last ran, what it did, and
    whether users.xlsx currently exists on disk."""
    status = scheduler_module.get_sync_status()["role_access"]
    return {
        **status,
        "file_exists": USER_MASTER_PATH.exists(),
        "file_path": str(USER_MASTER_PATH),
        "file_modified": (
            datetime.fromtimestamp(USER_MASTER_PATH.stat().st_mtime, tz=timezone.utc).isoformat()
            if USER_MASTER_PATH.exists() else None
        ),
    }


@router.post("/upload-user-master")
async def upload_user_master(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file.")

    contents = await file.read()
    with open(USER_MASTER_PATH, "wb") as out:
        out.write(contents)

    try:
        result = import_users_from_excel(db, contents)
    except ValueError as exc:
        scheduler_module.record_manual_sync("role_access", None, error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))

    scheduler_module.record_manual_sync("role_access", result)
    return {"success": True, "message": "users.xlsx uploaded and synced.", "users": result}


@router.get("/user-master/template")
def download_user_master_template():
    if not USER_MASTER_PATH.exists():
        raise HTTPException(status_code=404, detail="No template available yet.")
    return FileResponse(
        str(USER_MASTER_PATH),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="users.xlsx",
    )