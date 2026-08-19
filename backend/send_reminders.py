"""
send_reminders.py
-----------------
Standalone script — entry point for Windows Task Scheduler.

Checks yesterday's DRM data for Plant 5 and sends reminder emails for
every department whose data is missing.  Does NOT require FastAPI/uvicorn
to be running.

Usage
-----
    python send_reminders.py

Windows Task Scheduler configuration
--------------------------------------
  Program/script : C:/path/to/DigitalDRM/venv/Scripts/python.exe
  Arguments      : send_reminders.py
  Start in       : C:/path/to/DigitalDRM/backend

  Trigger        : Daily at 11:20 AM
  Run whether user is logged on or not : YES  (recommended)
  Run with highest privileges           : YES  (recommended)

Note: Replace C:/path/to/DigitalDRM with the actual project path,
      e.g. D:/c102943-Data/DigitalDRM
"""

import logging
import os
import sys
from pathlib import Path

# ── 1. Resolve paths ───────────────────────────────────────────────────────
#
# BACKEND_DIR is the directory that contains this file (…/backend/).
# We add it to sys.path so "from app.xxx import yyy" always resolves,
# regardless of the current working directory.
#
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── 2. Load .env BEFORE any app module is imported ──────────────────────────
#
# CRITICAL: app.database and app.services.email_service read environment
# variables at import time.  load_dotenv() MUST be called first.
#
from dotenv import load_dotenv          # noqa: E402  (import after sys.path tweak)

ENV_FILE = BACKEND_DIR / ".env"
loaded = load_dotenv(ENV_FILE, override=True)

# ── 3. Configure logging ─────────────────────────────────────────────────────
LOG_DIR = BACKEND_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "reminders.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("digitaldrm.send_reminders")

# ── 4. Log startup diagnostics ───────────────────────────────────────────────
logger.info("=" * 60)
logger.info("[STARTUP] send_reminders.py started")
logger.info("[STARTUP] Backend dir : %s", BACKEND_DIR)
logger.info("[STARTUP] .env loaded : %s (%s)", loaded, ENV_FILE)
logger.info(
    "[STARTUP] SMTP_HOST=%s | SMTP_USER=%s | DB_SERVER=%s",
    os.getenv("SMTP_HOST", "<not set>"),
    os.getenv("SMTP_USER", "<not set>"),
    os.getenv("DB_SERVER", "<not set>"),
)
logger.info("=" * 60)


# ── 5. Run reminder check ─────────────────────────────────────────────────────
def main():
    try:
        from app.services.reminder_service import check_and_send_missing_data_reminders
        check_and_send_missing_data_reminders()
        logger.info("[STARTUP] send_reminders.py finished successfully.")
        sys.exit(0)
    except Exception as exc:
        logger.critical(
            "[STARTUP] Unexpected top-level error: %s", exc, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()