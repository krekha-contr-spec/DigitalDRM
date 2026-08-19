import logging
import os
from pathlib import Path

#from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, run_history_migrations, run_role_access_migrations, run_reminder_log_migrations, run_email_recipient_migrations, run_login_audit_migrations, run_staff_incharge_email_sync, run_role_access_email_sync, run_daily_report_recipient_seed, run_overall_summary_recipient_seed, run_report_recipient_migration, run_email_recipient_department_normalization, run_user_approval_migrations, run_despatch_unique_constraint_migration, SessionLocal
from app.scheduler import start_scheduler, shutdown_scheduler
from app.services.user_import_service import import_users_from_file
from app.services.email_recipient_service import (
    import_email_recipients_from_file,
    write_email_recipients_excel_to_disk,
    EMAIL_USERS_XLSX_PATH,
)

# Load .env from the backend directory (same folder as this package's parent).
# Must happen before any module reads os.getenv() for SMTP/DB settings.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
#load_dotenv(_ENV_FILE, override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

_startup_logger = logging.getLogger("digitaldrm.startup")
_startup_logger.info("[STARTUP] .env loaded from: %s (exists=%s)", _ENV_FILE, _ENV_FILE.exists())
_startup_logger.info(
    "[STARTUP] SMTP_HOST=%s | SMTP_USER=%s",
    os.getenv("SMTP_HOST", "<not set>"),
    os.getenv("SMTP_USER", "<not set>"),
)

from app.routes.auth_routes import router as auth_router
from app.routes.production_routes import router as production_router
from app.routes.manpower_routes import router as manpower_router
from app.routes.despatch_routes import router as despatch_router
from app.routes.ovc_routes import router as ovc_router
from app.routes.sales_routes import router as sales_router
from app.routes.customer_routes import router as customer_router
from app.routes.report_routes import router as report_router
from app.routes.role_access_routes import router as role_access_router
from app.routes.user_import_routes import router as user_import_router
from app.routes.roles_routes import router as roles_router
from app.routes.reminder_routes import router as reminder_router
from app.routes.rejection_ppm_routes import router as rejection_ppm_router
from app.routes.product_value_routes import router as product_value_router
from app.routes.report_save_routes   import router as report_save_router
from app.routes.daily_report_routes  import router as daily_report_router
from app.routes.admin_routes import router as admin_router
from app.routes.email_recipient_routes import router as email_recipient_router
from app.routes.approval_routes import router as approval_router

app = FastAPI(title="DigitalDRM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    run_history_migrations()
    run_despatch_unique_constraint_migration()
    run_role_access_migrations()
    run_user_approval_migrations()
    run_reminder_log_migrations()
    run_email_recipient_migrations()

    # Normalize any already-stored department spellings (e.g. "OVC
    # Elements", "Rejection PPM") to their canonical slug ("ovc",
    # "rejection_ppm") — fixes existing rows so Level 1 (Staff Incharge)
    # reminders find them, in addition to get_recipients() now tolerating
    # spelling variance at read-time too. Must run before the sync
    # functions below so their "does a row already exist" checks compare
    # against clean, normalized department values.
    run_email_recipient_department_normalization()
    run_login_audit_migrations()
    
    # Auto-sync users from Excel on startup
    users_file = Path(__file__).resolve().parent.parent / "data" / "users.xlsx"
    if users_file.exists():
        db = SessionLocal()
        try:
            res = import_users_from_file(db, str(users_file))
            _startup_logger.info("[STARTUP] Auto-synced users from Excel: %s", res)
        except Exception as exc:
            _startup_logger.error("[STARTUP] Failed to auto-sync users: %s", exc)
        finally:
            db.close()

    # Auto-sync Email Services recipients from a master email_users.xlsx
    # file, if it's present on disk (this is the Excel -> DB direction of
    # the bidirectional sync; see write_email_recipients_excel_to_disk()
    # for the DB -> Excel direction, and app/scheduler.py for the
    # periodic re-sync that keeps picking up direct edits to this file
    # while the app is running, not just at startup).
    if EMAIL_USERS_XLSX_PATH.exists():
        db = SessionLocal()
        try:
            res = import_email_recipients_from_file(db, str(EMAIL_USERS_XLSX_PATH))
            _startup_logger.info("[STARTUP] Auto-synced Email Services recipients from Excel: %s", res)
        except Exception as exc:
            _startup_logger.error("[STARTUP] Failed to auto-sync Email Services recipients: %s", exc)
        finally:
            db.close()

    # Populate Email Services' Staff Incharge recipients from the Data
    # Entry Users (role_access) table that Excel import above just
    # populated — every plant, no department-wise email hardcoded
    # anywhere in code. Runs AFTER the Excel auto-sync so role_access is
    # already up to date, and AFTER the email_users.xlsx auto-load above
    # so it only fills slots that file didn't already cover.
    run_staff_incharge_email_sync()

    # Fill any remaining Data Entry User (role_access) gaps with
    # whatever is already configured in Email Services > Staff Incharge
    # (e.g. an Admin added a recipient there directly, with no matching
    # Data Entry User yet). Runs AFTER the sync above so it only fills
    # genuinely empty (plant, department) slots — never overwrites an
    # Excel-imported or admin-edited row, and never gets undone by
    # Excel's own deactivation-of-missing-rows logic.
    run_role_access_email_sync()

    # Seed the Daily Report's per-plant recipient (email_recipients,
    # type="daily_report_recipient"): Plant 5 -> adprisha12@gmail.com
    # (active), Plants 2/3/4/6 -> empty inactive placeholder rows ready
    # for an admin to fill in later. Never overwrites a row that already
    # exists (seeded before, or an admin's own edit). Runs after the
    # syncs above so it never races them for the same table.
    # Migrate any leftover "Combined Report Recipient" rows to
    # "president" (the type was removed — see run_report_recipient_migration
    # docstring). Runs before the seeds below so a converted row counts
    # as "already configured" and doesn't get double-seeded.
    run_report_recipient_migration()

    run_daily_report_recipient_seed()

    # Seed the President's global (all-plants) Overall Summary recipient
    # — a.prisha-contr@ranegroup.com — so the "All Plants" Overall
    # Summary report always has somewhere to go, without an admin having
    # to configure it manually first. Never overwrites an admin's own
    # edit if one already exists.
    run_overall_summary_recipient_seed()

    # Write the now-fully-synced Email Services state back out to
    # email_users.xlsx, so the on-disk file reflects the database even
    # on a fresh install where the file didn't exist yet a moment ago.
    write_email_recipients_excel_to_disk()

    print("✅ Application startup complete.")
    start_scheduler()

@app.on_event("shutdown")
def shutdown():
    shutdown_scheduler()

app.include_router(auth_router)
app.include_router(production_router)
app.include_router(manpower_router)
app.include_router(despatch_router)
app.include_router(ovc_router)
app.include_router(sales_router)
app.include_router(customer_router)
app.include_router(report_router)
app.include_router(role_access_router)
app.include_router(user_import_router)
app.include_router(roles_router)
app.include_router(reminder_router)
app.include_router(rejection_ppm_router)
app.include_router(product_value_router)
app.include_router(report_save_router)
app.include_router(daily_report_router)
app.include_router(admin_router)
app.include_router(email_recipient_router)
app.include_router(approval_router)

@app.get("/")
def root():
    return {"message": "DigitalDRM API Running!"}