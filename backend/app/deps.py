"""
deps.py
-------
Shared FastAPI dependencies for authentication & role-based access
control (RBAC). Every route in the app keeps working exactly as before;
this module only adds NEW dependencies that admin-only routes opt into
via `Depends(...)`. Nothing here changes existing architecture.

Usage:
    from app.deps import get_current_user, require_admin

    @router.get("/admin/something")
    def something(current_user: TokenPayload = Depends(require_admin)):
        ...
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import decode_token

# `auto_error=False` lets us return a clean 401 with our own message
# instead of FastAPI's generic "Not authenticated".
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class TokenPayload:
    username: str
    role: str
    plant_id: Optional[int]


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> TokenPayload:
    """
    Decodes and validates the JWT sent in the `Authorization: Bearer <token>`
    header. Raises 401 if missing/invalid/expired.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token. Please log in again.",
        )

    return TokenPayload(
        username=username,
        role=role,
        plant_id=payload.get("plant_id"),
    )


def require_admin(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """
    Guard dependency for admin-only endpoints (Data Entry Users Management,
    admin user CRUD/import, etc). Data Entry Users (role = 'plant' /
    'president') get a 403 — they can never reach these APIs, no matter
    what the frontend does.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges are required to perform this action.",
        )
    return current_user


def require_plant_head(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """
    Guard dependency for the Plant Head's user-approval-request endpoints
    (request-add / request-remove a Data Entry User) — see
    app/services/approval_service.py. Only role="plant" (Plant Head)
    may call these; also requires a plant_id to be present on the token,
    since every request must be scoped to that Plant Head's own plant.
    Admin doesn't need this guard at all — Admin's own add/remove stays
    on the existing require_admin-guarded /role-access/user endpoints,
    completely unaffected by this approval workflow.
    """
    if current_user.role != "plant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a Plant Head can request a Data Entry User change.",
        )
    if current_user.plant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account isn't scoped to a plant — contact an admin.",
        )
    return current_user