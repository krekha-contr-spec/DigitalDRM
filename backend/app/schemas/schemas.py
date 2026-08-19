from pydantic import BaseModel
from typing import Optional
from datetime import date

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    plant_id: Optional[int]
    username: str

class AdLoginRequest(BaseModel):
    """Windows/AD login for the Plant 5 login screen — GEN ID + Windows/
    Domain password, never stored, only relayed (RSA-encrypted) to
    Rane's AD Login API."""
    gen_id: str
    password: str

class AdTokenResponse(TokenResponse):
    """Same shape as the normal TokenResponse (so existing role-based
    routing/authorization works unchanged) plus the Department and
    display Name that were auto-mapped from Data Entry Users, so the
    frontend can show/prefill them without an extra round trip."""
    department: Optional[str] = None
    person_name: Optional[str] = None

class ProductionEntry(BaseModel):
    plant_id: int
    date: date
    plan: Optional[float] = None
    actual: Optional[float] = None


class ManpowerEntry(BaseModel):
    plant_id: int
    date: date
    plan: Optional[float] = None
    actual: Optional[float] = None


class DespatchEntry(BaseModel):
    plant_id: int
    date: date
    customer_name: str
    month_plan: Optional[float] = None
    mtd_actual: Optional[float] = None

class OVCEntry(BaseModel):
    plant_id: int
    date: date
    element_type: str
    plan: Optional[float] = None
    actual: Optional[float] = None

class SalesEntry(BaseModel):
    plant_id: int
    date: date
    segment: str
    month_plan: Optional[float] = None
    mtd_actual: Optional[float] = None

# ============================================
# ROLE ACCESS SCHEMA
# ============================================
class RoleVerification(BaseModel):
    plant_id: int
    person_name: str
    email: str
    role: str


class RoleAccessCreate(BaseModel):
    plant_id: int
    role: str
    person_name: str
    email: str
    employee_id: str | None = None
    is_active: bool = True


class RoleAccessUpdate(BaseModel):
    plant_id: int | None = None
    role: str | None = None
    person_name: str | None = None
    email: str | None = None
    employee_id: str | None = None
    is_active: bool | None = None


class PlantHeadAddUserRequest(BaseModel):
    """Payload for a Plant Head's POST /role-access/plant-head/request-add —
    same shape as RoleAccessCreate minus plant_id/is_active, since those
    are fixed (plant_id from the Plant Head's own JWT; the new user
    starts active only once Admin approves)."""
    role: str
    person_name: str
    email: str
    employee_id: str | None = None