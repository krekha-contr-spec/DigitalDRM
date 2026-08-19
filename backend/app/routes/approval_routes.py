"""
approval_routes.py
-------------------
Public (no-login) one-time-link endpoints for the email-based user
approval workflow, plus an admin-only JSON listing for the Admin
Dashboard's own Pending Approvals view. See app/services/approval_service.py
for the full workflow explanation.

GET /approvals/{token}/approve  — public, single-use link from the email
GET /approvals/{token}/reject   — public, single-use link from the email
GET /approvals                  — admin-only, JSON list (Admin Dashboard)
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.deps import require_admin
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["User Approvals"])


def _confirmation_page(title: str, message: str, detail: str, ok: bool) -> str:
    """Small self-contained HTML page — no frontend build/assets needed,
    since this is opened straight from an email client, often before
    anyone has even logged into the app."""
    color = "#16a34a" if ok else "#dc2626"
    icon = "&#9989;" if ok else "&#10060;"
    return f"""
    <html>
    <head><title>{title}</title></head>
    <body style="font-family: Arial, sans-serif; background:#f1f5f9; margin:0; padding:40px 20px;">
      <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
                  box-shadow:0 2px 12px rgba(0,0,0,0.08);padding:32px;text-align:center;">
        <div style="font-size:40px;margin-bottom:8px;">{icon}</div>
        <h2 style="color:{color};margin:0 0 12px;">{title}</h2>
        <p style="color:#334155;font-size:15px;margin:0 0 8px;">{message}</p>
        <p style="color:#94a3b8;font-size:13px;">{detail}</p>
      </div>
    </body>
    </html>
    """


@router.get("/{token}/approve", response_class=HTMLResponse)
def approve(token: str, request: Request, db: Session = Depends(get_db)):
    result = approval_service.approve_request(db, token, decided_by_ip=request.client.host if request.client else None)
    title = "Request Approved" if result.ok else "Couldn't Approve"
    return _confirmation_page(title, result.message, result.detail, result.ok)


@router.get("/{token}/reject", response_class=HTMLResponse)
def reject(token: str, request: Request, db: Session = Depends(get_db)):
    result = approval_service.reject_request(db, token, decided_by_ip=request.client.host if request.client else None)
    title = "Request Rejected" if result.ok else "Couldn't Reject"
    return _confirmation_page(title, result.message, result.detail, result.ok)


@router.get("", dependencies=[Depends(require_admin)])
def list_approvals(status: Optional[str] = Query(None, description="pending | approved | rejected | expired"), db: Session = Depends(get_db)):
    """Admin Dashboard's Pending Approvals view — lets an admin see and
    act on requests without needing to check email at all."""
    return approval_service.list_requests(db, status_filter=status)


@router.post("/{request_id}/approve")
def approve_from_dashboard(request_id: int, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    """Admin Dashboard button — approves without needing the emailed
    token, since the admin is already authenticated via JWT here."""
    result = approval_service.approve_request_by_id(db, request_id, decided_by_username=current_user.username)
    return {"success": result.ok, "message": result.message}


@router.post("/{request_id}/reject")
def reject_from_dashboard(request_id: int, db: Session = Depends(get_db), current_user=Depends(require_admin)):
    result = approval_service.reject_request_by_id(db, request_id, decided_by_username=current_user.username)
    return {"success": result.ok, "message": result.message}