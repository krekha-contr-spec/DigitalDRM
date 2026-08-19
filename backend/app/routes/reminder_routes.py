"""
reminder_routes.py
------------------
Provides a manual trigger endpoint so the reminder/escalation job can be
tested without waiting for the scheduler.

Endpoint
--------
  POST /reminders/trigger?level=1|2|3
      Runs check_and_send_missing_data_reminders(level=...) immediately
      and returns a JSON summary of what was checked/sent. Defaults to
      level=1 (Staff Incharge) if not specified.
      No authentication required (internal use only — restrict via
      network/firewall if needed).
"""

import logging
from datetime import date, timedelta
from fastapi import APIRouter, Query

router = APIRouter(prefix="/reminders", tags=["Reminders"])
logger = logging.getLogger("digitaldrm.reminder_routes")


@router.post("/trigger")
def trigger_reminders(
    level: int = Query(1, ge=1, le=3, description="Escalation level to run: 1=Staff Incharge, 2=Plant Head, 3=President"),
):
    """
    Manually triggers the DRM missing-data reminder/escalation check for
    Plant 5 at the given level. Useful for testing SMTP configuration and
    verifying the full escalation pipeline without waiting for the
    scheduled times.
    """
    logger.info("[TRIGGER] Manual reminder trigger called via API | level=%s", level)
    try:
        from app.services.reminder_service import check_and_send_missing_data_reminders
        check_and_send_missing_data_reminders(level=level)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        return {
            "status": "ok",
            "level": level,
            "message": f"Reminder check completed for level {level}. See server logs for details.",
            "checked_date": yesterday,
        }
    except Exception as exc:
        logger.error("[TRIGGER] Error during manual trigger (level=%s): %s", level, exc, exc_info=True)
        return {
            "status": "error",
            "level": level,
            "message": str(exc),
        }