from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User
from app.schemas.schemas import UserLogin, TokenResponse, AdLoginRequest, AdTokenResponse
from app.services.auth import verify_password, create_access_token
from app.services.ad_auth_service import ad_login, resolve_plant_department_role, AdAuthError, AdServiceError
from app.services.login_audit_service import record_login_attempt

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Shown to the person logging in for ANY authentication failure — wrong
# password, unreachable AD service, or valid AD credentials with no
# Plant/Department mapping. The real reason is only ever written to
# login_audit_log server-side; it must never leak here (avoids telling
# an attacker whether a GEN ID/username exists at all).
GENERIC_LOGIN_ERROR = "Invalid username or password"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip_address = _client_ip(request)
    user = db.query(User).filter(User.username == credentials.username).first()

    if not user or not verify_password(credentials.password, user.password):
        record_login_attempt(
            db, identifier=credentials.username, auth_method="local", success=False,
            reason="invalid_credentials", ip_address=ip_address,
        )
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "plant_id": user.plant_id
    })

    record_login_attempt(
        db, identifier=user.username, auth_method="local", success=True,
        role=user.role, plant_id=user.plant_id, ip_address=ip_address,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "plant_id": user.plant_id,
        "username": user.username
    }


@router.post("/ad-login", response_model=AdTokenResponse)
def ad_login_route(credentials: AdLoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Windows/Active Directory login for all plants (SOP ISM_L01 "AD
    Login API"). The GEN ID + Windows/Domain password are authenticated
    against Rane's AD Login API (which itself validates against AD/
    LDAP) — this app never sees a raw domain credential in a way it
    could store, and never talks to LDAP directly.

    On success, the person is mapped to a Plant/Department/Role by
    checking (in order) whether their AD email matches a President
    (email_recipients, global), a Plant Head (email_recipients, one
    plant), or a Staff Incharge (role_access / Data Entry Users, one
    plant + department) — see resolve_plant_department_role() for the
    full precedence. Valid domain credentials alone do not grant
    access — an admin must have already provisioned that person in one
    of those places for them to be let in here.

    Every attempt — success or failure, and whichever way it failed —
    is written to login_audit_log. The person logging in only ever sees
    GENERIC_LOGIN_ERROR; the specific reason is server-side only.
    """
    ip_address = _client_ip(request)
    gen_id = credentials.gen_id.strip()

    try:
        ad_profile = ad_login(gen_id, credentials.password, ip_address=ip_address)
    except AdAuthError as exc:
        record_login_attempt(
            db, identifier=gen_id, auth_method="ad", success=False,
            reason=f"ad_rejected: {exc}", ip_address=ip_address,
        )
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    except AdServiceError as exc:
        record_login_attempt(
            db, identifier=gen_id, auth_method="ad", success=False,
            reason=f"ad_service_unavailable: {exc}", ip_address=ip_address,
        )
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    mailid = (ad_profile.get("mailid") or "").strip()
    mapping = resolve_plant_department_role(db, mailid)

    if not mapping:
        record_login_attempt(
            db, identifier=gen_id, auth_method="ad", success=False,
            reason=f"not_provisioned_for_plant: email={mailid or '<none>'}",
            ip_address=ip_address,
        )
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    token = create_access_token({
        "sub": gen_id,
        "role": mapping["role"],
        "plant_id": mapping["plant_id"],
        "department": mapping["department"],
    })

    record_login_attempt(
        db, identifier=gen_id, auth_method="ad", success=True,
        role=mapping["role"], plant_id=mapping["plant_id"],
        department=mapping["department"], ip_address=ip_address,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": mapping["role"],
        "plant_id": mapping["plant_id"],
        "username": gen_id,
        "department": mapping["department"],
        "person_name": mapping["person_name"],
    }