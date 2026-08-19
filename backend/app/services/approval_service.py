"""
approval_service.py
--------------------
Email-based approval workflow for a Plant Head's Data Entry User
add/remove requests. See app/models/models.UserApprovalRequest for the
table this is built on.

Flow
----
1. A Plant Head calls POST /role-access/plant-head/request-add (or
   /request-remove/{user_id}) — see role_access_routes.py. This does
   NOT touch role_access at all yet; it only creates a
   UserApprovalRequest row (status="pending") and emails the configured
   "admin" recipient(s) (Admin Dashboard > Email Services) an HTML email
   with Approve/Reject buttons/links.
2. Each link is a one-time, unguessable token (32 bytes of
   secrets.token_urlsafe randomness — same entropy class as a session
   token). Only the SHA-256 HASH of that token is stored in the DB, so
   a database leak alone can't be used to forge an approval — this
   mirrors why we never store a plaintext password.
3. Clicking Approve calls GET /approvals/{token}/approve (public, no
   login required — the token itself IS the credential, same pattern as
   a password-reset email link). This:
     - looks up the request by hashing the incoming token and matching
       token_hash (never a raw-token DB query),
     - checks status == "pending" AND not expired (duplicate/late
       clicks are rejected with a clear message, never silently
       reapplied),
     - applies the actual change: action="add" creates the role_access
       row; action="remove" sets is_active=False (never a hard delete,
       per the requirement) on the target role_access row,
     - marks the request "approved", stamps decided_at.
   Reject (GET /approvals/{token}/reject) does the same lookup/guard but
   only flips status to "rejected" — role_access is never touched.
4. Both routes return a small self-contained HTML confirmation page
   (this is a link clicked from an email client, not an API consumer).
5. GET /approvals (admin-only, JSON) lists all requests for the Admin
   Dashboard's own Pending Approvals view, so an admin doesn't have to
   rely on email at all if they're already logged in.

Nothing about the EXISTING Admin Dashboard direct add/remove
(role_access_routes.py's /user POST/PUT/DELETE/PATCH, all still
require_admin-guarded) changes even slightly — this table and this
service are only ever touched when the actor is a Plant Head.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import UserApprovalRequest, RoleAccess, Plant
from app.services import email_recipient_service as recipients_svc
from app.services.email_service import send_email

logger = logging.getLogger("digitaldrm.approval")

# Same "must be set to the real reachable address" pattern as
# reminder_service.DIGITAL_DRM_BASE_URL — see that file's comment for
# why this can't just be hardcoded.
DIGITAL_DRM_BASE_URL = os.getenv("DIGITAL_DRM_BASE_URL", "https://digitaldrm.ranegroup.com")

APPROVAL_LINK_EXPIRY_HOURS = 72  # 3 days — long enough to reach an admin, short enough to stay meaningful


def _generate_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hash). Only the hash is ever persisted."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, hashed


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _plant_name(db: Session, plant_id: int) -> str:
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    return plant.name if plant else f"Plant {plant_id}"


def _send_approval_email(db: Session, req: UserApprovalRequest, raw_token: str) -> None:
    """Emails the configured 'admin' recipients (Admin Dashboard > Email
    Services) an Approve/Reject request. If nobody is configured yet,
    logs it exactly like every other automated email in this codebase
    does (see reminder_service.py / daily_report_service.py) rather
    than failing the request — the approval row still exists and is
    visible/actionable from the Admin Dashboard's Pending Approvals list
    even if no email goes out."""
    recipients = recipients_svc.get_recipients(db, "admin", department=None, plant_id=None)
    if not recipients:
        logger.error(
            "[APPROVAL EMAIL] \u274c No Admin recipient configured — "
            "add one in Admin Dashboard > Email Services (type: Admin). "
            "Request #%s is still pending and visible in the Admin Dashboard, "
            "but no email was sent.",
            req.id,
        )
        return

    plant_label = _plant_name(db, req.plant_id)
    approve_url = f"{DIGITAL_DRM_BASE_URL}/approvals/{raw_token}/approve"
    reject_url = f"{DIGITAL_DRM_BASE_URL}/approvals/{raw_token}/reject"

    if req.action == "add":
        subject = f"DRM Approval Needed: Add Data Entry User - {plant_label}"
        action_desc = (
            f"<p><b>Action:</b> Add a new Data Entry User</p>"
            f"<p><b>Plant:</b> {plant_label}</p>"
            f"<p><b>Department:</b> {req.role}</p>"
            f"<p><b>Name:</b> {req.person_name}</p>"
            f"<p><b>Email:</b> {req.email}</p>"
            + (f"<p><b>Employee ID:</b> {req.employee_id}</p>" if req.employee_id else "")
        )
    else:
        target = db.query(RoleAccess).filter(RoleAccess.id == req.target_user_id).first()
        subject = f"DRM Approval Needed: Remove Data Entry User - {plant_label}"
        action_desc = (
            f"<p><b>Action:</b> Deactivate a Data Entry User (they will be marked "
            f"Inactive, not deleted, and can be reactivated later if needed)</p>"
            f"<p><b>Plant:</b> {plant_label}</p>"
            + (
                f"<p><b>Department:</b> {target.role}</p>"
                f"<p><b>Name:</b> {target.person_name}</p>"
                f"<p><b>Email:</b> {target.email}</p>"
                if target else "<p><i>(This user no longer exists — approving will do nothing.)</i></p>"
            )
        )

    body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #0f172a;">
      <p>Hello,</p>
      <p>Plant Head <b>{req.requested_by_username}</b> has requested the following change
         in DigitalDRM, which needs your approval:</p>
      {action_desc}
      <div style="margin: 24px 0;">
        <a href="{approve_url}" style="background:#16a34a;color:#fff;padding:10px 22px;
           border-radius:6px;text-decoration:none;font-weight:bold;margin-right:12px;">
           \u2705 Approve
        </a>
        <a href="{reject_url}" style="background:#dc2626;color:#fff;padding:10px 22px;
           border-radius:6px;text-decoration:none;font-weight:bold;">
           \u274c Reject
        </a>
      </div>
      <p style="color:#64748b;font-size:12px;">
        This link is single-use and expires in {APPROVAL_LINK_EXPIRY_HOURS} hours
        ({req.expires_at.strftime('%d %b %Y, %H:%M')}).
        If you don't recognize this request, you can safely ignore this email or click Reject.
      </p>
      <p style="color:#94a3b8;font-size:11px;">This is an automated notification from the DigitalDRM system.</p>
    </body></html>
    """

    plain_fallback = (
        f"Approval needed: {subject}\n\n"
        f"Please view this email in an HTML-capable client to use the Approve/Reject buttons, "
        f"or open these links directly:\n\nApprove: {approve_url}\nReject: {reject_url}\n"
    )

    try:
        ok = send_email(to_email=recipients, subject=subject, body=plain_fallback, html_body=body)
        if ok:
            logger.info("[APPROVAL EMAIL] \u2705 Sent to %s for request #%s (%s)", recipients, req.id, req.action)
        else:
            logger.error("[APPROVAL EMAIL] \u274c Failed to send for request #%s (see email_service logs above)", req.id)
    except Exception as exc:
        logger.error("[APPROVAL EMAIL] \u274c Unexpected error sending for request #%s: %s", req.id, exc, exc_info=True)


def create_add_request(
    db: Session,
    plant_id: int,
    role: str,
    person_name: str,
    email: str,
    employee_id: Optional[str],
    requested_by_username: str,
    requested_by_email: Optional[str],
) -> UserApprovalRequest:
    """Called by a Plant Head — see role_access_routes.py's
    POST /role-access/plant-head/request-add. Creates the pending
    request and emails Admin; does NOT touch role_access."""
    role_norm = role.strip().lower().replace(" ", "_").replace("-", "_")
    raw_token, token_hash = _generate_token()

    req = UserApprovalRequest(
        action="add",
        status="pending",
        requested_by_username=requested_by_username,
        requested_by_email=requested_by_email,
        plant_id=plant_id,
        role=role_norm,
        person_name=person_name.strip(),
        email=email.strip().lower(),
        employee_id=(employee_id or None),
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=APPROVAL_LINK_EXPIRY_HOURS),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    _send_approval_email(db, req, raw_token)
    return req


def create_remove_request(
    db: Session,
    plant_id: int,
    target_user_id: int,
    requested_by_username: str,
    requested_by_email: Optional[str],
) -> UserApprovalRequest:
    """Called by a Plant Head — see role_access_routes.py's
    POST /role-access/plant-head/request-remove/{user_id}. target_user_id
    must belong to this Plant Head's own plant (enforced by the caller)."""
    raw_token, token_hash = _generate_token()

    req = UserApprovalRequest(
        action="remove",
        status="pending",
        requested_by_username=requested_by_username,
        requested_by_email=requested_by_email,
        plant_id=plant_id,
        target_user_id=target_user_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=APPROVAL_LINK_EXPIRY_HOURS),
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    _send_approval_email(db, req, raw_token)
    return req


class ApprovalResult:
    """Simple outcome wrapper for the HTML confirmation page in
    approval_routes.py — success/already-handled/expired/not-found are
    all distinct so the page can show an accurate message rather than a
    generic error."""
    def __init__(self, ok: bool, message: str, detail: str = ""):
        self.ok = ok
        self.message = message
        self.detail = detail


def _find_pending_by_token(db: Session, raw_token: str) -> tuple[Optional[UserApprovalRequest], Optional[ApprovalResult]]:
    """Shared lookup+guard for both approve_request() and
    reject_request(). Returns (request, None) if it's found and still
    actionable, or (None, ApprovalResult) explaining why it isn't —
    this is what makes duplicate/late clicks safe: the SECOND click on
    an already-decided link always hits the status != 'pending' branch
    below and never re-applies the change."""
    token_hash = _hash_token(raw_token)
    req = db.query(UserApprovalRequest).filter(UserApprovalRequest.token_hash == token_hash).first()

    if not req:
        return None, ApprovalResult(False, "Invalid or unrecognized approval link.",
                                     "This link doesn't match any pending request.")

    if req.status != "pending":
        return None, ApprovalResult(
            False,
            f"This request was already {req.status}.",
            f"Decided on {req.decided_at.strftime('%d %b %Y, %H:%M') if req.decided_at else 'an earlier visit'} "
            f"— no further action was taken to prevent a duplicate approval.",
        )

    if datetime.utcnow() > req.expires_at:
        req.status = "expired"
        db.commit()
        return None, ApprovalResult(
            False, "This approval link has expired.",
            f"Links are valid for {APPROVAL_LINK_EXPIRY_HOURS} hours. "
            f"Ask the Plant Head to submit the request again if it's still needed.",
        )

    return req, None


def _apply_approval(db: Session, req: UserApprovalRequest, decided_by_ip: Optional[str]) -> str:
    """Shared by both the emailed-token path and the logged-in-admin
    path below — the actual role_access change is identical either way,
    only how the requester proved they're allowed to decide differs."""
    if req.action == "add":
        record = RoleAccess(
            plant_id=req.plant_id,
            role=req.role,
            person_name=req.person_name,
            email=req.email,
            employee_id=req.employee_id,
            is_active=True,
        )
        db.add(record)
        message = f"Approved: {req.person_name} added as {req.role} for {_plant_name(db, req.plant_id)}."
    else:
        target = db.query(RoleAccess).filter(RoleAccess.id == req.target_user_id).first()
        if not target:
            message = "Approved. That Data Entry User no longer existed, so there was nothing to deactivate."
        else:
            target.is_active = False  # soft-deactivate only — never a hard delete, per requirement
            message = f"Approved: {target.person_name} ({target.role}) marked Inactive."

    req.status = "approved"
    req.decided_at = datetime.utcnow()
    req.decided_by_ip = decided_by_ip
    db.commit()

    # Keep users.xlsx and the Admin Dashboard's Data Entry Users list in
    # sync immediately, exactly like every direct admin add/remove
    # already does — the approval workflow is a gate in FRONT of the
    # same code path, not a separate one.
    try:
        from app.routes.role_access_routes import _sync_excel_to_disk
        _sync_excel_to_disk(db)
    except Exception as exc:
        logger.warning("[APPROVAL] Excel sync after approval failed (non-fatal): %s", exc)

    logger.info("[APPROVAL] \u2705 Request #%s approved | %s", req.id, message)
    return message


def approve_request(db: Session, raw_token: str, decided_by_ip: Optional[str] = None) -> ApprovalResult:
    """Emailed-link path — token IS the credential (no login)."""
    req, err = _find_pending_by_token(db, raw_token)
    if err:
        return err
    message = _apply_approval(db, req, decided_by_ip)
    return ApprovalResult(True, message)


def reject_request(db: Session, raw_token: str, decided_by_ip: Optional[str] = None) -> ApprovalResult:
    """Emailed-link path — token IS the credential (no login)."""
    req, err = _find_pending_by_token(db, raw_token)
    if err:
        return err

    req.status = "rejected"
    req.decided_at = datetime.utcnow()
    req.decided_by_ip = decided_by_ip
    db.commit()

    logger.info("[APPROVAL] \u274c Request #%s rejected (no role_access change made).", req.id)
    return ApprovalResult(True, "Request rejected. No changes were made to Data Entry Users.")


def _find_pending_by_id(db: Session, request_id: int) -> tuple[Optional[UserApprovalRequest], Optional[ApprovalResult]]:
    """Same duplicate-approval guard as _find_pending_by_token(), for the
    logged-in-Admin-Dashboard path instead of the emailed-token path."""
    req = db.query(UserApprovalRequest).filter(UserApprovalRequest.id == request_id).first()
    if not req:
        return None, ApprovalResult(False, "Request not found.")
    if req.status != "pending":
        return None, ApprovalResult(False, f"This request was already {req.status}.")
    return req, None


def approve_request_by_id(db: Session, request_id: int, decided_by_username: str) -> ApprovalResult:
    """Admin Dashboard's own Pending Approvals view — admin is already
    authenticated via JWT (require_admin), so this doesn't need the
    emailed token at all; it's the same duplicate-approval guard keyed
    by request ID instead."""
    req, err = _find_pending_by_id(db, request_id)
    if err:
        return err
    message = _apply_approval(db, req, decided_by_ip=f"admin-dashboard:{decided_by_username}")
    return ApprovalResult(True, message)


def reject_request_by_id(db: Session, request_id: int, decided_by_username: str) -> ApprovalResult:
    req, err = _find_pending_by_id(db, request_id)
    if err:
        return err

    req.status = "rejected"
    req.decided_at = datetime.utcnow()
    req.decided_by_ip = f"admin-dashboard:{decided_by_username}"
    db.commit()

    logger.info("[APPROVAL] \u274c Request #%s rejected via Admin Dashboard by %s.", req.id, decided_by_username)
    return ApprovalResult(True, "Request rejected. No changes were made to Data Entry Users.")


def list_requests(db: Session, status_filter: Optional[str] = None) -> list[dict]:
    """For the Admin Dashboard's Pending Approvals view (GET /approvals,
    admin-only)."""
    query = db.query(UserApprovalRequest)
    if status_filter:
        query = query.filter(UserApprovalRequest.status == status_filter)
    rows = query.order_by(UserApprovalRequest.created_at.desc()).all()

    out = []
    for r in rows:
        target_label = None
        if r.action == "remove" and r.target_user_id:
            target = db.query(RoleAccess).filter(RoleAccess.id == r.target_user_id).first()
            if target:
                target_label = f"{target.person_name} ({target.role})"

        out.append({
            "id": r.id,
            "action": r.action,
            "status": r.status,
            "plant_id": r.plant_id,
            "plant_name": _plant_name(db, r.plant_id),
            "role": r.role,
            "person_name": r.person_name,
            "email": r.email,
            "employee_id": r.employee_id,
            "target_user_id": r.target_user_id,
            "target_label": target_label,
            "requested_by_username": r.requested_by_username,
            "requested_by_email": r.requested_by_email,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        })
    return out