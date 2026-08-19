"""
reminder_service.py
-------------------
Core DRM missing-data reminder logic for Plant 5, with a 3-level email
escalation.

Escalation levels
------------------
  Level 1  ->  Staff Incharge only (the department's existing recipient).
  Level 2  ->  Plant Head, CC: Staff Incharge.
  Level 3  ->  President, CC: Staff Incharge + Plant Head.

Each level is checked and sent by the SAME function
(check_and_send_missing_data_reminders), called with a different
`level` argument by the scheduler at 3 different configured times —
per the requirement to reuse one implementation instead of writing
3 separate ones. Before sending at ANY level, the department's data is
re-checked; if it has since been submitted, no email is sent and no
further escalation happens for that department/date.

Non-working days (Sundays + configured Government Holidays)
--------------------------------------------------------------
Before doing anything else, this module checks whether TODAY (the day
the job is actually running) is a working day via holiday_service. If
it's a Sunday or a date listed in the Government Holiday config file,
the entire run is skipped immediately — no reminder emails, no
escalations, no pending-data checks, no missing-data validations for
any department. Nothing is logged to reminder_email_log on a skipped
day. Processing resumes automatically the next time the scheduler runs
on a working day; no manual intervention is needed.

The reference date used for "pending DRM data" is the previous WORKING
day (skipping back over Sundays/holidays), not simply "yesterday" — so
a Monday run checks Friday's data (assuming no holidays in between)
rather than incorrectly treating Sunday's lack of data as a gap.

The Government Holiday list is fully configurable via
app/config/holidays.json (or the HOLIDAYS_FILE env var) — see
holiday_service.py. No code change or redeploy is needed to update it.

Recipients (Staff Incharge / Plant Head / President)
-------------------------------------------------------
ALL recipient email addresses are resolved at send-time from the
`email_recipients` table (see app/services/email_recipient_service.py)
instead of being hardcoded here. An admin manages every department's
Staff Incharge, the Plant Head, and the President from the Admin
Dashboard's "Email Services" tab — no code change or redeploy is needed
to update who gets these emails.

"Rejection PPM" and "Product Value" are roles that write to the
ovc_elements table with element_type = "Rejection PPM" / "Product Value".
They are treated as separate departments for reminder purposes so that
each recipient gets only their own email.

OVC completeness check (bugfix)
--------------------------------
"OVC" itself is NOT a real `element_type` value — the OVC data-entry
screen (frontend/.../pages/DataEntry.jsx, OVC_CATEGORIES) writes one row
per category, using the category name as element_type: "Consumable
Cost", "Direct Labour Cost", "Freight Cost", "Plant Overall Overrun",
"Power Cost", "Rejection Cost". A previous version of this file filtered
for `element_type == "OVC"` literally, which never matched a real row —
so the OVC reminder fired every day regardless of what had actually been
submitted.

OVC data for a given Plant + Date is now only considered "present" (i.e.
no reminder needed) if ALL 6 categories in OVC_CATEGORIES have a row for
that plant/date — see `_ovc_categories_complete()`. If even one category
is missing, the reminder is triggered, and the log states exactly which
categories were found vs. missing, plus the plant and date being
validated.
"""

import logging
import os
from datetime import date, datetime
from typing import List, Optional

from app.database import SessionLocal
from app.models.models import (
    DailyProduction,
    DailyManpower,
    CustomerDespatch,
    OVCElement,
    SalesData,
    ReminderEmailLog,
)
from app.services.email_service import send_email
from app.services.holiday_service import is_working_day, previous_working_day, load_holidays
from app.services import email_recipient_service as recipients_svc

logger = logging.getLogger("digitaldrm.reminder")

TARGET_PLANT_ID = 5

# ── OVC categories ───────────────────────────────────────────────────────────
#
# MUST match frontend/vite-project/src/pages/DataEntry.jsx OVC_CATEGORIES
# exactly (case/spelling), since these are the literal `element_type`
# values the Staff Incharge's OVC entries are saved with. If a category
# is renamed/added/removed on the frontend, update this list too, or the
# completeness check below will be wrong.
OVC_CATEGORIES = [
    "Consumable Cost",
    "Direct Labour Cost",
    "Freight Cost",
    "Plant Overall Overrun",
    "Power Cost",
    "Rejection Cost",
]

# ── DigitalDRM Base URL ─────────────────────────────────────────────────────
#
# Base URL for the DigitalDRM application, used to build the clickable
# link in reminder/escalation emails. The Staff Incharge login page URL
# is constructed by appending the plant ID.
#
# MUST be set via the DIGITAL_DRM_BASE_URL environment variable to
# whatever address people actually use to reach this app (the same
# hostname/IP:port you use when opening it in a browser on another
# machine) — e.g. "http://10.41.10.146:8000" or "https://digitaldrm.
# ranegroup.com" once that domain is actually live and pointed at this
# server. If it's left unset, the link in emails will point at a
# placeholder domain that doesn't resolve to anything, so the link
# won't open on any machine, even though the app itself is reachable
# fine when visited directly by its real address.
DIGITAL_DRM_BASE_URL = os.getenv("DIGITAL_DRM_BASE_URL", "https://digitaldrm.ranegroup.com")
STAFF_LOGIN_URL = f"{DIGITAL_DRM_BASE_URL}/data-entry/login/{TARGET_PLANT_ID}"

# ── Escalation levels (configurable) ────────────────────────────────────────
#
# level      -> the escalation level number stored in the log and used by
#               the scheduler to pick which run this is.
# label      -> human-readable name used in email subject/body/logs.
# recipients -> a function(db, plant_id, dept) -> List[str] so each level
#               can resolve its own "To" list from the email_recipients
#               table (Admin Dashboard > Email Services).
# cc         -> a function(db, plant_id, dept) -> List[str] for the "CC"
#               list. Level 1 has no CC. Level 2 CCs the Staff Incharge.
#               Level 3 CCs both the Staff Incharge and the Plant Head.
ESCALATION_LEVELS = {
    1: {
        "label": "Staff Incharge Reminder",
        "recipients": lambda db, plant_id, dept: recipients_svc.get_recipients(
            db, "staff_incharge", department=dept["slug"], plant_id=plant_id
        ),
        "cc": lambda db, plant_id, dept: [],
    },
    2: {
        "label": "Plant Head Escalation",
        "recipients": lambda db, plant_id, dept: recipients_svc.get_recipients(
            db, "plant_head", department=None, plant_id=plant_id
        ),
        "cc": lambda db, plant_id, dept: recipients_svc.get_recipients(
            db, "staff_incharge", department=dept["slug"], plant_id=plant_id
        ),
    },
    3: {
        "label": "President Escalation",
        "recipients": lambda db, plant_id, dept: recipients_svc.get_recipients(
            db, "president", department=None, plant_id=plant_id
        ),
        "cc": lambda db, plant_id, dept: (
            recipients_svc.get_recipients(db, "staff_incharge", department=dept["slug"], plant_id=plant_id)
            + recipients_svc.get_recipients(db, "plant_head", department=None, plant_id=plant_id)
        ),
    },
}

# ── Department configuration ────────────────────────────────────────────────
#
# Each entry is a dict with:
#   name        – human-readable label used in subject/body/logs
#   slug        – the `department` key used to look up this department's
#                 recipients in the email_recipients table (also matches
#                 the role_access.role / Admin Dashboard department slugs)
#   model       – SQLAlchemy model to query
#   filter_col  – optional column name + value for sub-type filtering
#                 (used to split ovc_elements by element_type)
#   frequency   – "daily" (default/most departments): checked every working
#                 day against the previous working day's data.
#                 "monthly" (Sales, Rejection PPM only): checked every
#                 working day of the month (starting the 1st) against the
#                 LAST DAY OF THE PREVIOUS MONTH's data — see
#                 _reference_date_for() below. Keeps sending/escalating
#                 every day until that month's data is filled in, then
#                 goes silent for the rest of the month (same
#                 already-notified/fresh-check behavior as daily depts).
DEPARTMENTS = [
    {"name": "Production", "slug": "production", "model": DailyProduction, "filter_col": None, "frequency": "daily"},
    {"name": "Manpower", "slug": "manpower", "model": DailyManpower, "filter_col": None, "frequency": "daily"},
    # OVC does NOT use a plain filter_col match — see _ovc_categories_complete().
    # `element_type` is never literally "OVC"; it's one of OVC_CATEGORIES,
    # and ALL of them must be present for the day to count as complete.
    {"name": "OVC", "slug": "ovc", "model": OVCElement, "filter_col": None, "frequency": "daily"},
    {"name": "Rejection PPM", "slug": "rejection_ppm", "model": OVCElement, "filter_col": ("element_type", "Rejection PPM"), "frequency": "monthly"},
    {"name": "Product Value", "slug": "product_value", "model": OVCElement, "filter_col": ("element_type", "Product Value"), "frequency": "daily"},
    {"name": "Despatch", "slug": "despatch", "model": CustomerDespatch, "filter_col": None, "frequency": "daily"},
    {"name": "Sales", "slug": "sales", "model": SalesData, "filter_col": None, "frequency": "monthly"},
]

# ── Monthly-frequency departments (Sales, Rejection PPM) ────────────────────
#
# These two departments check against the LAST DAY OF THE PREVIOUS MONTH
# (the monthly closing figure) instead of "yesterday"/"previous working
# day" like the daily departments. There is no day-of-month cutoff: the
# check/escalation runs every working day starting the 1st of the month,
# and keeps going until that month's data is filled in — the existing
# fresh-check-every-run + per-level duplicate-guard logic already handles
# "stop once filled" for free, exactly like the daily departments do.
# Once the calendar rolls into the next month, the reference date shifts
# automatically to the new previous month.


def _last_day_of_previous_month(today: date) -> date:
    """Returns the date of the last day of the month before `today`'s
    month — the fixed reference date used for monthly-frequency
    departments (Sales, Rejection PPM)."""
    first_of_this_month = today.replace(day=1)
    from datetime import timedelta
    return first_of_this_month - timedelta(days=1)


def _reference_date_for(dept: dict, today: date, daily_reference_date: date) -> date:
    """Resolves the correct reference date to check for a given
    department: the shared previous-working-day date for "daily"
    departments, or the fixed last-day-of-previous-month date for
    "monthly" departments."""
    if dept.get("frequency") == "monthly":
        return _last_day_of_previous_month(today)
    return daily_reference_date


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_log_table(db):
    """
    Create the reminder_email_log table if it does not yet exist.
    Called once per run so the table is always available before we
    try to read or write it.
    """
    try:
        from app.database import engine
        from app.models.models import Base, ReminderEmailLog  # noqa: F401
        Base.metadata.create_all(bind=engine, tables=[ReminderEmailLog.__table__])
        logger.info("[SETUP] reminder_email_log table verified/created.")
    except Exception as exc:
        logger.error("[SETUP] Could not ensure reminder_email_log table: %s", exc)


def _data_exists(db, dept: dict, plant_id: int, for_date: date) -> bool:
    """
    Returns True if this department's data counts as "present" for the
    given plant/date (i.e. no reminder needed).

    For OVC specifically, this is NOT a plain "does at least one row
    exist" check — see _ovc_categories_complete(): ALL categories in
    OVC_CATEGORIES must have a row for the day to count as complete.
    Every other department (including the Rejection PPM / Product Value
    sub-types of ovc_elements) still uses the simple single-row filter.
    """
    if dept.get("slug") == "ovc":
        return _ovc_categories_complete(db, plant_id, for_date)

    model = dept["model"]
    q = db.query(model.id).filter(
        model.plant_id == plant_id,
        model.date == for_date,
    )
    if dept["filter_col"]:
        col_name, col_value = dept["filter_col"]
        q = q.filter(getattr(model, col_name) == col_value)
    return q.first() is not None


def _ovc_categories_complete(db, plant_id: int, for_date: date) -> bool:
    """
    Validates the correct Plant + Date + ALL OVC categories before a
    reminder decision is made. Returns True only if every category in
    OVC_CATEGORIES has a row for this plant/date (i.e. the Staff
    Incharge has fully completed OVC entry for the day) — otherwise
    returns False so the reminder is triggered.

    Logs, at every call, exactly which categories were found and which
    are missing, so it's always clear from the logs WHY a reminder was
    sent or skipped for OVC.
    """
    rows = (
        db.query(OVCElement.element_type)
        .filter(
            OVCElement.plant_id == plant_id,
            OVCElement.date == for_date,
            OVCElement.element_type.in_(OVC_CATEGORIES),
        )
        .distinct()
        .all()
    )
    found = {r[0] for r in rows}
    missing = [c for c in OVC_CATEGORIES if c not in found]

    logger.info(
        "[OVC CHECK] Plant=%s | Date=%s | Required categories (%d)=%s | Found (%d)=%s",
        plant_id, for_date.isoformat(), len(OVC_CATEGORIES), OVC_CATEGORIES,
        len(found), sorted(found),
    )

    if missing:
        logger.warning(
            "[OVC CHECK] ⚠️ Incomplete OVC data | Plant=%s | Date=%s | Missing categories (%d)=%s "
            "-> reminder WILL be evaluated for sending.",
            plant_id, for_date.isoformat(), len(missing), missing,
        )
        return False

    logger.info(
        "[OVC CHECK] ✅ All %d OVC categories present | Plant=%s | Date=%s -> no reminder needed.",
        len(OVC_CATEGORIES), plant_id, for_date.isoformat(),
    )
    return True


def _already_notified(db, plant_id: int, department: str, for_date: date, level: int) -> bool:
    """
    Returns True if a 'sent' log entry already exists for this exact
    dept/date/level. Scoping the duplicate guard by level (not just by
    dept/date) is what allows level 1, 2, and 3 to each fire exactly once
    per missing-data day, without level 2/3 being blocked by level 1's
    log entry or vice versa.
    """
    return (
        db.query(ReminderEmailLog.id)
        .filter(
            ReminderEmailLog.plant_id == plant_id,
            ReminderEmailLog.department == department,
            ReminderEmailLog.for_date == for_date,
            ReminderEmailLog.level == level,
            ReminderEmailLog.status == "sent",
        )
        .first()
        is not None
    )


def _log_attempt(
    db, plant_id: int, department: str, for_date: date, status: str,
    level: int, recipients: List[str], cc_recipients: List[str],
):
    """Persist a reminder attempt record, including escalation level and
    exactly which To/CC addresses were used — per the requirement to keep
    a full audit trail of level, recipients, CC, timestamp, and status."""
    try:
        entry = ReminderEmailLog(
            plant_id=plant_id,
            department=department,
            for_date=for_date,
            status=status,
            level=level,
            recipients=", ".join(recipients) if recipients else None,
            cc_recipients=", ".join(cc_recipients) if cc_recipients else None,
        )
        db.add(entry)
        db.commit()
        logger.info(
            "[LOG] Reminder attempt recorded | dept=%s date=%s level=%s status=%s recipients=%s cc=%s",
            department, for_date.isoformat(), level, status, recipients, cc_recipients,
        )
    except Exception as exc:
        logger.error("[LOG] Failed to write reminder log entry: %s", exc)
        db.rollback()


def _build_email(dept_name: str, plant_id: int, for_date: date, level: int):
    """Returns (subject, body) for a missing-data reminder/escalation at
    the given level. Subject/body wording escalates in urgency with the
    level so recipients can tell at a glance how serious it is."""
    now_str = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    level_info = ESCALATION_LEVELS[level]
    level_label = level_info["label"]

    if level == 1:
        subject = f"DRM Reminder - Plant {plant_id} - {dept_name}"
        urgency_line = "Yesterday's DRM data for the above department has NOT been updated."
        action_line = "Please log in to DigitalDRM and enter the missing data at the earliest."
    elif level == 2:
        subject = f"DRM ESCALATION (Level 2) - Plant {plant_id} - {dept_name}"
        urgency_line = (
            "Yesterday's DRM data for the above department is STILL missing after the "
            "initial reminder to the Staff Incharge. This has been escalated to you as Plant Head."
        )
        action_line = "Kindly follow up with the Staff Incharge (CC'd above) to ensure the data is entered without further delay."
    else:
        subject = f"DRM FINAL ESCALATION (Level 3) - Plant {plant_id} - {dept_name}"
        urgency_line = (
            "Yesterday's DRM data for the above department remains missing despite reminders "
            "to the Staff Incharge and Plant Head. This is the final escalation to the President."
        )
        action_line = "This is for your awareness and monitoring. The Staff Incharge and Plant Head (CC'd above) are responsible for resolving this at the earliest."

    # ── Build the email body with clickable link ──────────────────────────
    #
    # The link always points to the Staff Incharge's Data Entry Login page
    # for Plant 5, regardless of the escalation level. This ensures that
    # all recipients (including Plant Head and President) can easily access
    # the data entry page if needed, but the intended user is always the
    # Staff Incharge.
    link_text = "Open DigitalDRM"
    link_html = f'<a href="{STAFF_LOGIN_URL}" style="color: #1a73e8; text-decoration: underline;">{link_text}</a>'
    
    body = (
        f"Dear Team,\n\n"
        f"This is an automated {level_label.lower()} from the DigitalDRM system.\n\n"
        f"  Plant       : {plant_id}\n"
        f"  Department  : {dept_name}\n"
        f"  Missing Date: {for_date.strftime('%d-%b-%Y')}\n"
        f"  Escalation  : Level {level} ({level_label})\n\n"
        f"{urgency_line}\n"
        f"{action_line}\n\n"
        f"To enter the missing data, click the link below (this will take you to the Staff Incharge's Data Entry Login page):\n"
        f"{STAFF_LOGIN_URL}\n\n"
        f"Reminder generated at: {now_str}\n\n"
        f"Regards,\n"
        f"DigitalDRM Automated System"
    )
    
    # Also create an HTML version with a clickable link for email clients
    # that support HTML. The email_service.send_email function should handle
    # both plain text and HTML versions. If your send_email function only
    # sends plain text, you can keep just the URL above.
    html_body = (
        f"<p>Dear Team,</p>"
        f"<p>This is an automated {level_label.lower()} from the <strong>DigitalDRM</strong> system.</p>"
        f"<ul>"
        f"  <li><strong>Plant</strong>: {plant_id}</li>"
        f"  <li><strong>Department</strong>: {dept_name}</li>"
        f"  <li><strong>Missing Date</strong>: {for_date.strftime('%d-%b-%Y')}</li>"
        f"  <li><strong>Escalation</strong>: Level {level} ({level_label})</li>"
        f"</ul>"
        f"<p>{urgency_line}</p>"
        f"<p>{action_line}</p>"
        f"<p>To enter the missing data, click the link below (this will take you to the Staff Incharge's Data Entry Login page):</p>"
        f"<p style='font-size: 16px;'><strong>{link_html}</strong></p>"
        f"<p>Direct URL: <a href='{STAFF_LOGIN_URL}'>{STAFF_LOGIN_URL}</a></p>"
        f"<p>Reminder generated at: {now_str}</p>"
        f"<p>Regards,<br>DigitalDRM Automated System</p>"
    )
    
    return subject, body, html_body


# ── Main entry point ─────────────────────────────────────────────────────────

def check_and_send_missing_data_reminders(level: int = 1):
    """
    Entry point called by send_reminders.py (Task Scheduler), the
    /reminders/trigger API endpoint, or the scheduler's 3 escalation
    jobs (one per level).

    This SAME function handles all 3 escalation levels — it is called
    with level=1, level=2, and level=3 at 3 different scheduled times
    (see app/scheduler.py) instead of having 3 separate implementations.

    Steps
    -----
    0. Non-working-day gate: if TODAY (Sunday or a configured Government
       Holiday) is not a working day, skip the entire run immediately —
       no departments are checked, no emails are sent at any level, and
       nothing is written to reminder_email_log. Processing resumes
       automatically the next time the scheduler fires on a working day.
    1. Ensure the reminder_email_log table exists in the DB.
    2. Compute the reference date: the previous WORKING day (skipping
       back over Sundays/holidays), not simply "yesterday" — so a lack
       of data on a Sunday/holiday itself is never treated as a gap.
    3. For each department in DEPARTMENTS:
       a. Check if data exists for the reference date RIGHT NOW (fresh
          check every time, every level) -> if found, skip entirely: no
          email at this level, and no further escalation for this
          department/date, since the data gap that triggered the whole
          escalation chain is resolved.
       b. Skip if a reminder was already sent at THIS level for this
          dept/date (duplicate guard, scoped per level).
       c. Resolve recipients/CC for this level from ESCALATION_LEVELS.
       d. Send the email.
       e. Log the attempt (level, recipients, CC, timestamp, status).
    4. Failures in one department never stop others from being processed.
    """
    if level not in ESCALATION_LEVELS:
        logger.error("[REMINDER JOB] Invalid escalation level=%s — must be 1, 2, or 3.", level)
        return

    today = date.today()
    holidays = load_holidays()

    # ── Step 0: non-working-day gate ────────────────────────────────────────
    if not is_working_day(today, holidays):
        reason = "Sunday" if today.weekday() == 6 else "a configured Government Holiday"
        logger.info("=" * 60)
        logger.info(
            "[REMINDER JOB] Skipped entirely | Level=%s | Today=%s is %s (non-working day). "
            "No reminders, escalations, pending-data checks, or missing-data validations run "
            "today. Processing resumes automatically on the next working day.",
            level, today.isoformat(), reason,
        )
        logger.info("=" * 60)
        return

    daily_reference_date = previous_working_day(today, holidays)
    level_label = ESCALATION_LEVELS[level]["label"]

    logger.info("=" * 60)
    logger.info(
        "[REMINDER JOB] Started | Level=%s (%s) | Plant=%s | Today=%s | "
        "Daily reference (previous working) date=%s",
        level, level_label, TARGET_PLANT_ID, today.isoformat(), daily_reference_date.isoformat(),
    )
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        _ensure_log_table(db)

        for dept in DEPARTMENTS:
            dept_name = dept["name"]
            try:
                reference_date = _reference_date_for(dept, today, daily_reference_date)

                # ── Step A: fresh data check, every level ────────────────────
                logger.info(
                    "[CHECK] Plant=%s | Dept=%s | Date=%s | Level=%s | Frequency=%s",
                    TARGET_PLANT_ID, dept_name, reference_date.isoformat(), level, dept.get("frequency", "daily"),
                )

                exists = _data_exists(db, dept, TARGET_PLANT_ID, reference_date)

                if exists:
                    logger.info(
                        "[CHECK] ✅ Data FOUND for %s | Plant=%s | Date=%s — "
                        "no reminder needed, escalation stops here.",
                        dept_name, TARGET_PLANT_ID, reference_date.isoformat(),
                    )
                    continue

                logger.warning(
                    "[CHECK] ⚠️  Data MISSING for %s | Plant=%s | Date=%s | Level=%s",
                    dept_name, TARGET_PLANT_ID, reference_date.isoformat(), level,
                )

                # ── Step B: duplicate guard (scoped to this level) ───────────
                if _already_notified(db, TARGET_PLANT_ID, dept_name, reference_date, level):
                    logger.info(
                        "[SKIP] Level %s reminder already sent for %s | Plant=%s | Date=%s — skipping duplicate.",
                        level, dept_name, TARGET_PLANT_ID, reference_date.isoformat(),
                    )
                    continue

                # ── Step C: resolve recipients/CC for this level ─────────────
                recipients = ESCALATION_LEVELS[level]["recipients"](db, TARGET_PLANT_ID, dept)
                cc_recipients = ESCALATION_LEVELS[level]["cc"](db, TARGET_PLANT_ID, dept)

                if not recipients:
                    logger.error(
                        "[SKIP] No recipients configured for Level %s (%s) | Dept=%s | Plant=%s — "
                        "add one in Admin Dashboard > Email Services. No email sent.",
                        level, level_label, dept_name, TARGET_PLANT_ID,
                    )
                    continue

                # Safety: if an address (e.g. a department's Staff Incharge)
                # happens to also be the Plant Head/President contact, never
                # let the same address appear in both To and CC — that would
                # deliver a duplicate-looking copy of the same email to one
                # person. De-dup CC against To, case-insensitively, and
                # de-dup CC against itself.
                to_lower = {r.lower() for r in recipients}
                seen = set()
                deduped_cc = []
                for addr in cc_recipients:
                    key = addr.lower()
                    if key in to_lower or key in seen:
                        continue
                    seen.add(key)
                    deduped_cc.append(addr)
                cc_recipients = deduped_cc

                subject, body, html_body = _build_email(dept_name, TARGET_PLANT_ID, reference_date, level)

                logger.info(
                    "[EMAIL] Sending Level %s (%s) for %s -> To: %s | CC: %s",
                    level, level_label, dept_name, recipients, cc_recipients,
                )

                # Send email with both plain text and HTML versions
                # If your send_email function doesn't support HTML, modify it
                # or use the plain text version only.
                sent = send_email(
                    recipients, 
                    subject, 
                    body, 
                    cc=cc_recipients or None,
                    html_body=html_body  # Add this parameter to send_email if it supports HTML
                )

                # ── Step D: log attempt ───────────────────────────────────────
                _log_attempt(
                    db, TARGET_PLANT_ID, dept_name, reference_date,
                    status="sent" if sent else "failed",
                    level=level, recipients=recipients, cc_recipients=cc_recipients,
                )

                if sent:
                    logger.info(
                        "[DONE] ✅ Level %s reminder sent for %s | Plant=%s | Date=%s",
                        level, dept_name, TARGET_PLANT_ID, reference_date.isoformat(),
                    )
                else:
                    logger.error(
                        "[DONE] ❌ Level %s reminder FAILED for %s | Plant=%s | Date=%s",
                        level, dept_name, TARGET_PLANT_ID, reference_date.isoformat(),
                    )

            except Exception as exc:
                logger.error(
                    "[ERROR] Unexpected error processing dept=%s | Plant=%s | Date=%s | Level=%s | %s",
                    dept_name, TARGET_PLANT_ID, reference_date.isoformat(), level, exc,
                    exc_info=True,
                )
                continue  # always continue with the next department

    finally:
        db.close()
        logger.info(
            "[REMINDER JOB] Finished | Level=%s | Plant=%s | Daily reference date=%s | "
            "Monthly reference date (Sales/Rejection PPM)=%s",
            level, TARGET_PLANT_ID, daily_reference_date.isoformat(),
            _last_day_of_previous_month(today).isoformat(),
        )
        logger.info("=" * 60)