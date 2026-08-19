r"""
holiday_service.py
-------------------
Loads the configurable Government Holiday list used by the DigitalDRM
reminder/scheduler logic to skip non-working days.

Non-working days = Sundays (always, automatically — never needs to be
configured) + whatever dates are listed in the Government Holiday config
file below. On a non-working day, the reminder job must not run at all:
no reminder emails, no escalations, no pending-data checks, no
missing-data validations. Processing resumes automatically on the next
working day, and the reference date used for "yesterday's pending data"
becomes the previous WORKING day (skipping back over any Sundays/
holidays in between) rather than always literally yesterday.

Configurability
----------------
The holiday list lives in a plain JSON file (HOLIDAYS_FILE below), never
in Python code, so an administrator can add, remove, or edit holiday
dates at any time without changing or redeploying the application. The
file is re-read fresh on every call (deliberately not cached), so an
edit takes effect on the very next scheduled run — no restart needed.

File location can be overridden without any code change via the
HOLIDAYS_FILE environment variable (e.g. in backend/.env):
    HOLIDAYS_FILE=D:\Digitalization_DigitalDRM2.o\DigitalDRM\backend\data\Holidays.json

Expected file format (see backend/data/Holidays.json for the shipped
example):
    {
      "holidays": [
        "2026-01-26",
        { "date": "2026-08-15", "name": "Independence Day" }
      ]
    }
Both plain "YYYY-MM-DD" strings and {"date": "...", "name": "..."}
objects are accepted per entry; "name" is documentation only and is
never used by the application logic.
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger("digitaldrm.holidays")

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend/app
# The actual shipped holiday config lives at backend/data/Holidays.json
# (NOT backend/app/config/holidays.json — that path never existed on disk,
# which meant load_holidays() below was silently falling back to "no
# holidays configured" on every run: HOLIDAYS_FILE.exists() was always
# False, so Independence Day / other Government Holidays were never
# actually honored even though the file itself was correctly maintained).
DEFAULT_HOLIDAYS_FILE = BACKEND_DIR.parent / "data" / "Holidays.json"

# Env var lets ops point at a different file/path without touching code.
HOLIDAYS_FILE = Path(os.getenv("HOLIDAYS_FILE", str(DEFAULT_HOLIDAYS_FILE)))

# Safety cap on how far back previous_working_day() will walk before
# giving up — protects against a misconfigured holiday file (e.g.
# hundreds of consecutive dates) ever causing an infinite/near-infinite
# loop in the scheduler.
_MAX_LOOKBACK_DAYS = 30


def _parse_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(value).strip())
    except Exception:
        logger.warning("[HOLIDAYS] Ignoring invalid date entry in %s: %r", HOLIDAYS_FILE, value)
        return None


def load_holidays() -> Set[date]:
    """
    Reads the Government Holiday list fresh from HOLIDAYS_FILE on every
    call. Never raises: a missing or malformed file degrades to "no
    configured holidays" (Sundays are still always skipped regardless),
    so a config mistake can never silently break the reminder pipeline.
    """
    if not HOLIDAYS_FILE.exists():
        logger.info(
            "[HOLIDAYS] No holiday file found at %s; treating as no configured "
            "Government Holidays (Sundays are still always non-working).",
            HOLIDAYS_FILE,
        )
        return set()

    try:
        raw = json.loads(HOLIDAYS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(
            "[HOLIDAYS] Could not read/parse %s: %s. Treating as no configured holidays.",
            HOLIDAYS_FILE, exc,
        )
        return set()

    entries = raw.get("holidays", []) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        logger.error(
            "[HOLIDAYS] %s must contain a list, or an object with a 'holidays' "
            "list — got %s. Ignoring file.",
            HOLIDAYS_FILE, type(entries).__name__,
        )
        return set()

    holidays: Set[date] = set()
    for entry in entries:
        value = entry.get("date") if isinstance(entry, dict) else entry
        if not value:
            continue
        parsed = _parse_date(value)
        if parsed:
            holidays.add(parsed)

    logger.info("[HOLIDAYS] Loaded %d configured Government Holiday date(s) from %s.", len(holidays), HOLIDAYS_FILE)
    return holidays


def is_sunday(d: date) -> bool:
    return d.weekday() == 6  # Monday=0 ... Sunday=6


def is_working_day(d: date, holidays: Optional[Set[date]] = None) -> bool:
    """
    A day is a working day unless it's a Sunday (always non-working,
    regardless of configuration) or it appears in the configured
    Government Holiday list. Pass a pre-loaded `holidays` set to avoid
    re-reading the file when checking many dates in the same run;
    otherwise it is loaded fresh.
    """
    if is_sunday(d):
        return False
    if holidays is None:
        holidays = load_holidays()
    return d not in holidays


def previous_working_day(d: date, holidays: Optional[Set[date]] = None) -> date:
    """
    Returns the most recent working day strictly BEFORE `d`, skipping
    back over any Sundays and/or configured Government Holidays in
    between. This is the reference date reminder checks use for
    "pending DRM data" — e.g. if today is Monday, this normally returns
    Friday (Saturday is checked first, and only returned if it's not
    itself a Sunday/holiday), rather than treating Sunday's absence of
    data as a gap.

    Every date skipped on the way back is logged explicitly (Sunday vs.
    configured holiday, with the holiday's date called out) so a run's
    logs make it obvious exactly why a given reference date was chosen.
    """
    if holidays is None:
        holidays = load_holidays()

    candidate = d - timedelta(days=1)
    for _ in range(_MAX_LOOKBACK_DAYS):
        if is_sunday(candidate):
            logger.info("[HOLIDAYS] Skipping %s (Sunday) while looking back from %s.", candidate.isoformat(), d.isoformat())
            candidate -= timedelta(days=1)
            continue
        if candidate in holidays:
            logger.info(
                "[HOLIDAYS] Skipping %s (configured Government Holiday, from %s) while looking back from %s.",
                candidate.isoformat(), HOLIDAYS_FILE, d.isoformat(),
            )
            candidate -= timedelta(days=1)
            continue

        logger.info("[HOLIDAYS] Reference (previous working) day for %s resolved to %s.", d.isoformat(), candidate.isoformat())
        return candidate

    logger.error(
        "[HOLIDAYS] Could not find a working day within %d days before %s "
        "(check %s for a misconfiguration — e.g. an excessive run of "
        "consecutive holiday dates). Falling back to %s anyway.",
        _MAX_LOOKBACK_DAYS, d, HOLIDAYS_FILE, candidate,
    )
    return candidate