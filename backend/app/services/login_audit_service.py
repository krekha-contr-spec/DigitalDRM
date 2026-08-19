"""
login_audit_service.py
------------------------
Records every login attempt (both the existing local username/password
flow and the new AD/Windows GEN ID flow) into login_audit_log, so
authentication activity stays auditable regardless of which method a
user signs in with.

record_login_attempt() NEVER raises — a failure to write an audit row
must never block or break someone's login. Any problem writing the row
is caught and logged server-side instead.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("digitaldrm.login_audit")


def record_login_attempt(
    db: Session,
    identifier: str,
    auth_method: str,
    success: bool,
    role: Optional[str] = None,
    plant_id: Optional[int] = None,
    department: Optional[str] = None,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    identifier   -> the username or GEN ID as entered (never the password).
    auth_method  -> "local" or "ad".
    reason       -> internal-only diagnostic (e.g. "invalid_credentials",
                    "ad_service_unavailable", "not_provisioned_for_plant").
                    Callers must NEVER show this to the person logging in
                    — the login screen always shows one generic error.
    """
    try:
        from app.models.models import LoginAuditLog

        entry = LoginAuditLog(
            identifier=identifier,
            auth_method=auth_method,
            success=success,
            role=role,
            plant_id=plant_id,
            department=department,
            reason=reason,
            ip_address=ip_address,
            created_at=datetime.utcnow(),
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        # Auditing must never take down a login. Roll back so a failed
        # audit write can't leave the session in a broken state for
        # whatever the caller does next (e.g. issuing the JWT).
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(
            "Could not record login audit entry (identifier=%s, method=%s, success=%s): %s",
            identifier, auth_method, success, exc,
        )