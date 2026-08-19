# scheduler.py
#
# APScheduler-based reminder scheduling for the DigitalDRM API.
# The scheduler starts when the FastAPI app starts and sends the daily
# missing-data reminder emails at the configured time. It also runs a
# daily report-generation job that, on the 1st of every month/quarter/
# year, automatically generates and saves one report PER DEPARTMENT for
# the period that just ended and emails each one to that department's
# own Staff Incharge (see report_save_routes.py's
# generate_all_department_reports_for_period()). Each department's
# report is generated only once per period — a deterministic filename
# in DigitalDRM/Reports acts as the "already generated" guard.

import logging
from pathlib import Path

logger = logging.getLogger("digitaldrm.scheduler")

scheduler = None
JOB_ID = "daily_reminder_email_job"           # kept for the Level 1 job id (backward compatible)
JOB_ID_LEVEL_2 = "daily_reminder_email_job_level2"
JOB_ID_LEVEL_3 = "daily_reminder_email_job_level3"
REPORT_JOB_ID = "scheduled_report_generation_job"
DAILY_ALL_PLANTS_REPORT_JOB_ID = "daily_all_plants_report_job"
# Fixed recipient for the daily all-plants Overall Summary report —
# intentionally separate from the DB-configured Admin Dashboard > Email
# Services recipients used by the President Dashboard's manual "Generate
# Report" button, since this is a specific standing request rather than
# something meant to be reconfigured from that screen.
DAILY_ALL_PLANTS_REPORT_RECIPIENT = "a.prisha-contr@ranegroup.com"
DAILY_PLANT_REPORT_JOB_ID = "daily_plant_report_job"
PRESIDENT_DAILY_REPORT_JOB_ID = "president_daily_report_job"
EMAIL_RECIPIENTS_SYNC_JOB_ID = "email_recipients_excel_sync_job"
EMAIL_RECIPIENTS_SYNC_INTERVAL_MINUTES = 2
ROLE_ACCESS_SYNC_JOB_ID = "role_access_excel_sync_job"
STAFF_INCHARGE_CROSS_SYNC_JOB_ID = "staff_incharge_cross_sync_job"
ROLE_ACCESS_SYNC_INTERVAL_MINUTES = 2
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# ── Excel <-> DB sync status, surfaced to the Admin Dashboard ───────────────
#
# In-memory only (reset on restart, which is fine — the Excel files and
# the DB are always the real source of truth, this is just "when did we
# last look"). Each entry: last_checked (always updated), last_synced
# (only updated when the file's mtime actually changed since the
# previous check — see _mtime_changed() below), last_result, last_error.
_sync_status = {
    "role_access": {"last_checked": None, "last_synced": None, "last_result": None, "last_error": None},
    "email_recipients": {"last_checked": None, "last_synced": None, "last_result": None, "last_error": None},
    "staff_incharge_cross_sync": {"last_checked": None, "last_synced": None, "last_error": None},
}
_last_seen_mtime = {"role_access": None, "email_recipients": None}


def get_sync_status() -> dict:
    """Read-only snapshot for the /sync-status API endpoints."""
    import copy
    return copy.deepcopy(_sync_status)


def record_manual_sync(key: str, result: dict | None, error: str | None = None) -> None:
    """Called by the manual "Sync Now" routes (admin_routes.py's POST
    /admin/sync, email_recipient_routes.py's POST /admin/email-recipients/
    sync) so a manual sync updates the same status the periodic
    background job updates — the Admin Dashboard's sync-status panel
    doesn't need to know or care which one actually ran."""
    from datetime import datetime, timezone
    status = _sync_status[key]
    now = datetime.now(timezone.utc).isoformat()
    status["last_checked"] = now
    if error is None:
        status["last_synced"] = now
        status["last_result"] = result
        status["last_error"] = None
    else:
        status["last_error"] = error


def _mtime_changed(key: str, filepath: Path) -> bool:
    """True if filepath's mtime differs from what we saw last time we
    checked (or we've never checked it before). Lets the periodic job
    skip re-parsing/re-upserting an unchanged file — cheap and avoids
    doing pointless work every couple of minutes."""
    try:
        mtime = filepath.stat().st_mtime
    except OSError:
        return False
    changed = _last_seen_mtime.get(key) != mtime
    _last_seen_mtime[key] = mtime
    return changed


# ── Configurable escalation trigger times ───────────────────────────────────
#
# Level 1 (Staff Incharge) fires first; Level 2 (Plant Head) and Level 3
# (President) fire later in the day, giving each level a window to be
# resolved before the next escalation goes out. Change these to adjust
# the schedule without touching any other logic.
REMINDER_LEVEL_1_TIME = {"hour": 9, "minute": 30}
REMINDER_LEVEL_2_TIME = {"hour": 10, "minute": 30}
REMINDER_LEVEL_3_TIME = {"hour": 11, "minute": 30}


def _load_env():
    if ENV_FILE.exists():
        logger.info("[SCHEDULER] Loading environment from %s", ENV_FILE)
        try:
            from dotenv import load_dotenv

            load_dotenv(ENV_FILE, override=True)
        except Exception as exc:
            logger.warning("[SCHEDULER] Could not load .env: %s", exc)
    else:
        logger.info("[SCHEDULER] No .env file found at %s; using current environment.", ENV_FILE)


def _run_reminder_job(level: int = 1):
    """
    Runs the missing-data reminder/escalation check for the given level.
    This is the SAME function used for all 3 escalation levels — the
    scheduler just calls it 3 times a day with a different `level`
    (see the job registrations below) instead of having 3 separate
    job functions.
    """
    try:
        from app.services.reminder_service import check_and_send_missing_data_reminders

        logger.info("[SCHEDULER] Running reminder job | Level=%s", level)
        check_and_send_missing_data_reminders(level=level)
    except Exception as exc:
        logger.error("[SCHEDULER] Reminder job (level=%s) failed: %s", level, exc, exc_info=True)


def _run_report_generation_job():
    """
    Runs daily; only actually generates anything on the 1st of the month
    (the day boundaries a period "just completed"). For each period
    boundary that applies today (Monthly always; Quarterly/Yearly only on
    their respective boundary days), generates ONE report PER DEPARTMENT
    and emails each one to that department's own Staff Incharge — see
    report_save_routes.generate_all_department_reports_for_period().

    Idempotent per (plant, department, period): each department's report
    filename is fully deterministic, so if it was already generated
    earlier (e.g. the app restarted and this job ran twice on the same
    1st), generation is skipped rather than duplicated or re-emailed.
    """
    from datetime import date

    today = date.today()
    if today.day != 1:
        return  # Only a period boundary triggers generation.

    try:
        from app.database import SessionLocal
        from app.services.reminder_service import TARGET_PLANT_ID
        from app.routes.report_save_routes import generate_all_department_reports_for_period
    except Exception as exc:
        logger.error("[SCHEDULER] Could not import report generation dependencies: %s", exc, exc_info=True)
        return

    db = SessionLocal()
    try:
        # ── Monthly: the month that just ended ──────────────────────────
        if today.month == 1:
            prev_month, prev_month_year = 12, today.year - 1
        else:
            prev_month, prev_month_year = today.month - 1, today.year

        logger.info(
            "[SCHEDULER] Generating Monthly department reports | Plant=%s | %s-%s",
            TARGET_PLANT_ID, prev_month_year, prev_month,
        )
        results = generate_all_department_reports_for_period(
            db, TARGET_PLANT_ID, "Monthly", prev_month_year, month=prev_month,
        )
        for r in results:
            logger.info("[SCHEDULER] Monthly report | dept=%s -> %s", r["department"], r["status"])

        # ── Quarterly (Indian FY: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec,
        # Q4=Jan-Mar): only on the 1st of the month right after a quarter
        # ends ─────────────────────────────────────────────────────────
        quarter_just_ended = {
            7:  (1, today.year),      # Jul 1  -> Q1 (Apr-Jun) of this year
            10: (2, today.year),      # Oct 1  -> Q2 (Jul-Sep) of this year
            1:  (3, today.year - 1),  # Jan 1  -> Q3 (Oct-Dec) of last year
            4:  (4, today.year),      # Apr 1  -> Q4 (Jan-Mar) of this year
        }.get(today.month)

        if quarter_just_ended:
            quarter, q_year = quarter_just_ended
            logger.info(
                "[SCHEDULER] Generating Quarterly department reports | Plant=%s | Q%s %s",
                TARGET_PLANT_ID, quarter, q_year,
            )
            results = generate_all_department_reports_for_period(
                db, TARGET_PLANT_ID, "Quarterly", q_year, quarter=quarter,
            )
            for r in results:
                logger.info("[SCHEDULER] Quarterly report | dept=%s -> %s", r["department"], r["status"])

        # ── Yearly: the calendar year that just ended, on Jan 1 ─────────
        if today.month == 1:
            prev_year = today.year - 1
            logger.info(
                "[SCHEDULER] Generating Yearly department reports | Plant=%s | %s",
                TARGET_PLANT_ID, prev_year,
            )
            results = generate_all_department_reports_for_period(
                db, TARGET_PLANT_ID, "Yearly", prev_year,
            )
            for r in results:
                logger.info("[SCHEDULER] Yearly report | dept=%s -> %s", r["department"], r["status"])
    finally:
        db.close()


def _run_daily_all_plants_report_job():
    """
    Runs EVERY day (unlike _run_report_generation_job above, which only
    fires on period boundaries): generates the current month-to-date
    Overall Summary PDF across every plant and emails it to
    DAILY_ALL_PLANTS_REPORT_RECIPIENT. See
    report_save_routes.run_daily_all_plants_report().
    """
    try:
        from app.database import SessionLocal
        from app.routes.report_save_routes import run_daily_all_plants_report
    except Exception as exc:
        logger.error("[SCHEDULER] Could not import daily all-plants report dependencies: %s", exc, exc_info=True)
        return

    db = SessionLocal()
    try:
        result = run_daily_all_plants_report(db, DAILY_ALL_PLANTS_REPORT_RECIPIENT)
        if result.get("status") == "ok":
            logger.info(
                "[SCHEDULER] Daily all-plants report generated and emailed to %s | %s",
                DAILY_ALL_PLANTS_REPORT_RECIPIENT, result.get("filename"),
            )
        else:
            logger.error("[SCHEDULER] Daily all-plants report failed: %s", result.get("message"))
    except Exception as exc:
        logger.error("[SCHEDULER] Daily all-plants report job crashed: %s", exc, exc_info=True)
    finally:
        db.close()


def _run_daily_plant_report_job():
    """
    Runs every day at 4:15 PM (after all 3 escalation runs at 9:30/10:30/
    11:30 AM have had their chance to chase down missing data): generates
    the per-plant Daily Report PDF (5 departments — Production, Manpower,
    OVC, Product Value, Despatch) for EVERY plant (P2-P6), using the
    PREVIOUS WORKING DAY's data — skipping back over Sundays and any
    configured Government Holiday, exactly like the reminder/escalation
    job (see holiday_service.previous_working_day()) — never simply
    "yesterday". Each report is emailed to that plant's own configured
    "daily_report_recipient" — P5 -> adprisha12@gmail.com, P2/P3/P4/P6
    left empty until an admin configures them (see
    run_daily_report_recipient_seed() in app/database.py). Fully
    additive/separate from _run_daily_all_plants_report_job above (which
    builds one combined 7-department Overall Summary across all plants)
    and from _run_report_generation_job (Monthly/Quarterly/Yearly,
    period-boundary only). See app/services/daily_report_service.py.
    """
    from datetime import date

    try:
        from app.database import SessionLocal
        from app.services.daily_report_service import generate_daily_reports_for_all_plants
        from app.services.holiday_service import load_holidays, previous_working_day
    except Exception as exc:
        logger.error("[SCHEDULER] Could not import daily plant report dependencies: %s", exc, exc_info=True)
        return

    today = date.today()
    holidays = load_holidays()
    reference_date = previous_working_day(today, holidays)

    db = SessionLocal()
    try:
        results = generate_daily_reports_for_all_plants(db, target_date=reference_date)
        ok = sum(1 for r in results if r.get("status") == "ok")
        logger.info(
            "[SCHEDULER] Daily plant reports generated for previous working day %s (today=%s): %d/%d",
            reference_date.isoformat(), today.isoformat(), ok, len(results),
        )
        for r in results:
            if r.get("status") != "ok":
                logger.error("[SCHEDULER] Daily plant report failed | plant=%s | %s", r.get("plant_id"), r.get("message"))
    except Exception as exc:
        logger.error("[SCHEDULER] Daily plant report job crashed: %s", exc, exc_info=True)
    finally:
        db.close()


def _run_president_daily_report_job():
    """
    Runs right after _run_daily_plant_report_job above (same 4:16 PM
    slot, one minute later so it doesn't race the per-plant job for the
    same DB rows): builds ONE combined PDF covering EVERY plant
    (Production/Manpower/OVC/Product Value/Despatch, each with its own
    Plan-vs-Actual chart, per plant) and emails it to the "president"
    recipient (Admin Dashboard > Email Services). Uses the exact same
    PREVIOUS WORKING DAY reference date as the per-plant job. Fully
    additive/separate — does not replace or change the existing
    per-plant Daily Report emails, which keep going out individually to
    each plant's own daily_report_recipient exactly as before. See
    app/services/president_daily_report_service.py.
    """
    from datetime import date

    try:
        from app.database import SessionLocal
        from app.services.daily_report_service import generate_and_save_president_daily_report
        from app.services.holiday_service import load_holidays, previous_working_day
    except Exception as exc:
        logger.error("[SCHEDULER] Could not import president daily report dependencies: %s", exc, exc_info=True)
        return

    today = date.today()
    holidays = load_holidays()
    reference_date = previous_working_day(today, holidays)

    db = SessionLocal()
    try:
        result = generate_and_save_president_daily_report(db, target_date=reference_date)
        if result.get("status") == "ok":
            logger.info(
                "[SCHEDULER] President's all-plants daily report generated for %s (today=%s): %s",
                reference_date.isoformat(), today.isoformat(), result.get("filename"),
            )
        else:
            logger.error("[SCHEDULER] President's daily report failed | %s", result.get("message"))
    except Exception as exc:
        logger.error("[SCHEDULER] President daily report job crashed: %s", exc, exc_info=True)
    finally:
        db.close()


def _run_role_access_excel_sync_job():
    """
    Re-reads backend/data/users.xlsx (if present) and upserts any
    changes into role_access — the Excel -> DB half of the Data Entry
    Users bidirectional sync while the app is running, not just at
    startup. The DB -> Excel half happens immediately, on every Admin
    Dashboard create/update/delete/status-toggle (see
    _sync_excel_to_disk() in role_access_routes.py). Rows missing from
    the file are marked Inactive rather than hard-deleted (see
    import_users_from_file()'s full_sync behavior), so an accidental
    blank/corrupted file can never wipe data. Skips the actual
    parse/upsert entirely when the file's mtime hasn't changed since
    the last check (see _mtime_changed()) — cheap, and still perfectly
    safe to re-run on an unchanged file since the import is a pure
    upsert keyed on (plant_id, role): nothing is ever duplicated.
    """
    from datetime import datetime, timezone
    status = _sync_status["role_access"]
    status["last_checked"] = datetime.now(timezone.utc).isoformat()
    try:
        from app.database import SessionLocal
        from app.services.user_import_service import import_users_from_file

        users_file = BACKEND_DIR / "data" / "users.xlsx"
        if not users_file.exists():
            return
        if not _mtime_changed("role_access", users_file):
            return  # file unchanged since last check — nothing to do

        db = SessionLocal()
        try:
            result = import_users_from_file(db, str(users_file))
            status["last_synced"] = status["last_checked"]
            status["last_result"] = result
            status["last_error"] = None
            if result.get("created") or result.get("updated") or result.get("deactivated"):
                logger.info("[SCHEDULER] Data Entry Users Excel re-sync: %s", result)
        finally:
            db.close()
    except Exception as exc:
        status["last_error"] = str(exc)
        logger.error("[SCHEDULER] Data Entry Users Excel re-sync failed: %s", exc, exc_info=True)


def _run_email_recipients_sync_job():
    """
    Re-reads backend/data/email_users.xlsx (if present) and upserts any
    changes into email_recipients — the Excel -> DB half of the Email
    Services bidirectional sync while the app is running, not just at
    startup (the DB -> Excel half happens immediately, on every Admin
    Dashboard change — see write_email_recipients_excel_to_disk() calls
    in email_recipient_routes.py). Skips the actual parse/upsert when
    the file's mtime hasn't changed since the last check (see
    _mtime_changed()) — cheap, and still perfectly safe to re-run on an
    unchanged file since the import is a pure upsert keyed on
    (plant_id, department, recipient_type): nothing is ever duplicated.
    """
    from datetime import datetime, timezone
    status = _sync_status["email_recipients"]
    status["last_checked"] = datetime.now(timezone.utc).isoformat()
    try:
        from app.database import SessionLocal
        from app.services.email_recipient_service import (
            EMAIL_USERS_XLSX_PATH,
            import_email_recipients_from_file,
        )

        if not EMAIL_USERS_XLSX_PATH.exists():
            return
        if not _mtime_changed("email_recipients", EMAIL_USERS_XLSX_PATH):
            return  # file unchanged since last check — nothing to do

        db = SessionLocal()
        try:
            result = import_email_recipients_from_file(db, str(EMAIL_USERS_XLSX_PATH))
            status["last_synced"] = status["last_checked"]
            status["last_result"] = result
            status["last_error"] = None
            if result.get("created") or result.get("updated"):
                logger.info("[SCHEDULER] Email Services Excel re-sync: %s", result)
        finally:
            db.close()
    except Exception as exc:
        status["last_error"] = str(exc)
        logger.error("[SCHEDULER] Email Services Excel re-sync failed: %s", exc, exc_info=True)


def _run_staff_incharge_cross_sync_job():
    """
    Re-runs the two DB<->DB gap-filling syncs between Data Entry Users
    (role_access) and Email Services' Staff Incharge recipients
    (email_recipients) — previously these only ran once, at app startup,
    which meant a Staff Incharge added/edited AFTER the app was already
    running (the normal case — an admin adding someone through the UI)
    wouldn't get an email_recipients row until the next full restart,
    silently missing that department from reminders/escalation CC until
    then. Running this periodically, alongside the Excel re-syncs above,
    closes that gap without needing a restart.

    Both are pure upsert/fill-gaps operations (see their own docstrings
    in app/database.py) — genuinely safe to re-run on an interval:
    neither ever overwrites an existing row, whether that row came from
    a previous run of this same job, an Excel import, or an admin's own
    edit in the Admin Dashboard.
    """
    from datetime import datetime, timezone
    status = _sync_status["staff_incharge_cross_sync"]
    status["last_checked"] = datetime.now(timezone.utc).isoformat()
    try:
        from app.database import run_staff_incharge_email_sync, run_role_access_email_sync

        run_staff_incharge_email_sync()
        run_role_access_email_sync()
        status["last_synced"] = status["last_checked"]
        status["last_error"] = None
    except Exception as exc:
        status["last_error"] = str(exc)
        logger.error("[SCHEDULER] Staff Incharge <-> Data Entry User cross-sync failed: %s", exc, exc_info=True)


def _job_listener(event):
    if event.exception:
        logger.error("[SCHEDULER] Job %s failed: %s", event.job_id, event.exception)
    else:
        logger.info("[SCHEDULER] Job %s completed successfully.", event.job_id)


def start_scheduler():
    global scheduler
    if scheduler is not None:
        logger.warning("[SCHEDULER] Scheduler already running.")
        return

    _load_env()

    try:
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError as exc:
        logger.error("[SCHEDULER] APScheduler is not installed: %s", exc)
        return

    scheduler = BackgroundScheduler()
    scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # ── 3-level reminder escalation ──────────────────────────────────────
    # Same _run_reminder_job function, called with a different `level` at
    # each configured time — Level 1 (Staff Incharge) first, then Level 2
    # (Plant Head) and Level 3 (President) later in the day if the data
    # gap for a given department is still unresolved by then.
    scheduler.add_job(
        lambda: _run_reminder_job(level=1),
        trigger=CronTrigger(**REMINDER_LEVEL_1_TIME),
        id=JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        lambda: _run_reminder_job(level=2),
        trigger=CronTrigger(**REMINDER_LEVEL_2_TIME),
        id=JOB_ID_LEVEL_2,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        lambda: _run_reminder_job(level=3),
        trigger=CronTrigger(**REMINDER_LEVEL_3_TIME),
        id=JOB_ID_LEVEL_3,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Runs daily; internally no-ops unless today is the 1st of the month
    # (see _run_report_generation_job docstring).
    report_trigger = CronTrigger(hour=6, minute=30)
    scheduler.add_job(
        _run_report_generation_job,
        trigger=report_trigger,
        id=REPORT_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Runs every day (no period-boundary check) — the daily all-plants
    # Overall Summary report, emailed to DAILY_ALL_PLANTS_REPORT_RECIPIENT.
    # 17:00 (5 PM) daily, per requirement — by then the day's data entry
    # for the current month-to-date figures is expected to be in.
    daily_all_plants_trigger = CronTrigger(hour=10, minute=40)
    scheduler.add_job(
        _run_daily_all_plants_report_job,
        trigger=daily_all_plants_trigger,
        id=DAILY_ALL_PLANTS_REPORT_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Runs every day — per-plant Daily Report (5 departments) for P2-P6,
    # each emailed to that plant's own configured recipient (P5 =
    # adprisha12@gmail.com; P2/P3/P4/P6 empty until configured). Fires at
    # 16:15 (4:15 PM), using the PREVIOUS WORKING DAY's data (skipping
    # Sundays/holidays — never simply "yesterday"), deliberately AFTER
    # all 3 missing-data escalation runs (9:30/10:30/11:30 AM) have had
    # their chance to chase down that reference day's gaps.
    daily_plant_report_trigger = CronTrigger(hour=16, minute=15)
    scheduler.add_job(
        _run_daily_plant_report_job,
        trigger=daily_plant_report_trigger,
        id=DAILY_PLANT_REPORT_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # President's combined All-Plants Daily Report — 16:16 (one minute
    # after the per-plant reports above) so it doesn't race them for the
    # same day's DB rows.
    president_daily_report_trigger = CronTrigger(hour=16, minute=16)
    scheduler.add_job(
        _run_president_daily_report_job,
        trigger=president_daily_report_trigger,
        id=PRESIDENT_DAILY_REPORT_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Excel -> DB half of the Email Services bidirectional sync, running
    # continuously (not just at startup) so edits made directly to
    # email_users.xlsx while the app is running get picked up promptly.
    # The DB -> Excel half is immediate (see write_email_recipients_
    # excel_to_disk() calls in email_recipient_routes.py), so together
    # the file and the database stay in sync within minutes either way.
    scheduler.add_job(
        _run_email_recipients_sync_job,
        trigger=IntervalTrigger(minutes=EMAIL_RECIPIENTS_SYNC_INTERVAL_MINUTES),
        id=EMAIL_RECIPIENTS_SYNC_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Excel -> DB half of the Data Entry Users bidirectional sync,
    # running continuously (not just at startup) so edits made directly
    # to users.xlsx while the app is running get picked up promptly.
    # The DB -> Excel half is immediate (see _sync_excel_to_disk() in
    # role_access_routes.py), so together the file and the database
    # stay in sync within minutes either way.
    scheduler.add_job(
        _run_role_access_excel_sync_job,
        trigger=IntervalTrigger(minutes=ROLE_ACCESS_SYNC_INTERVAL_MINUTES),
        id=ROLE_ACCESS_SYNC_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # DB<->DB gap-filling: Staff Incharge (email_recipients) <->
    # Data Entry User (role_access), on the same interval as the Excel
    # re-syncs above, so an admin adding/editing someone while the app
    # is already running is reflected in escalation/reminder CC without
    # needing a full restart. Safe to run frequently — pure upsert,
    # never overwrites an existing row.
    scheduler.add_job(
        _run_staff_incharge_cross_sync_job,
        trigger=IntervalTrigger(minutes=ROLE_ACCESS_SYNC_INTERVAL_MINUTES),
        id=STAFF_INCHARGE_CROSS_SYNC_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.start()

    next_run = scheduler.get_job(JOB_ID).next_run_time
    logger.info(
        "[SCHEDULER] APScheduler started. Level 1 next run at %s | Level 2 at %s | Level 3 at %s",
        next_run,
        scheduler.get_job(JOB_ID_LEVEL_2).next_run_time,
        scheduler.get_job(JOB_ID_LEVEL_3).next_run_time,
    )


def shutdown_scheduler():
    global scheduler
    if scheduler is None:
        logger.info("[SCHEDULER] Scheduler not running; nothing to shut down.")
        return

    scheduler.shutdown(wait=False)
    logger.info("[SCHEDULER] APScheduler shut down.")
    scheduler = None