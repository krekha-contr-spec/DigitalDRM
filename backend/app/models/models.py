from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, DateTime, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    plant_id = Column(Integer, nullable=True)

class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)

class DailyProduction(Base):
    __tablename__ = "daily_production"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    date = Column(Date, nullable=False)
    plan = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    # Real save/modify timestamp (date + time) — used for the "Last Updated" field.
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=True)

class DailyManpower(Base):
    __tablename__ = "daily_manpower"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    date = Column(Date, nullable=False)
    plan = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=True)

class CustomerDespatch(Base):
    __tablename__ = "customer_despatch"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    date = Column(Date, nullable=False)
    customer_name = Column(String(100), nullable=False)
    month_plan = Column(Float, nullable=True)
    mtd_actual = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=True)
    # Locking is per (plant, date, customer) — NOT per (plant, date) alone.
    # This constraint is the actual source of truth that guarantees no
    # duplicate save/update can ever exist for the same customer on the
    # same date at the same plant, even under concurrent requests; the
    # SELECT-before-INSERT check in despatch_routes.py is only a fast,
    # friendly pre-check — this is what makes it airtight. Different
    # customers (BMW, HMI, etc.) for the same plant+date are unaffected
    # and remain independently insertable.
    __table_args__ = (
        UniqueConstraint("plant_id", "date", "customer_name", name="uq_customer_despatch_plant_date_customer"),
    )

class OVCElement(Base):
    __tablename__ = "ovc_elements"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    date = Column(Date, nullable=False)
    element_type = Column(String(100), nullable=False)
    plan = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=True)

class SalesData(Base):
    __tablename__ = "sales_data"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    date = Column(Date, nullable=False)
    segment = Column(String(100), nullable=False)
    month_plan = Column(Float, nullable=True)
    mtd_actual = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=True)

class PlantCustomer(Base):
    __tablename__ = "plant_customers"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    customer_name = Column(String(100), nullable=False)

class RoleAccess(Base):
    __tablename__ = "role_access"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    role = Column(String(50), nullable=False)
    person_name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    # Added for the Excel import feature (see user_import_service.py).
    # Both are optional so existing rows / the old seed script keep working.
    employee_id = Column(String(50), nullable=True, index=True)
    is_active = Column(Boolean, nullable=True, default=True)
    __table_args__ = (
        UniqueConstraint("plant_id", "person_name", "email", "role",
                         name="uq_role_access_plant_person_email_role"),
    )

class ReminderEmailLog(Base):
    __tablename__ = "reminder_email_log"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    department = Column(String(50), nullable=False)
    for_date = Column(Date, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), nullable=False, default="sent")  # sent / failed
    # 3-level escalation support:
    #   level 1 = Staff Incharge, level 2 = Plant Head (+CC Staff Incharge),
    #   level 3 = President (+CC Staff Incharge & Plant Head).
    level = Column(Integer, nullable=False, default=1)
    recipients = Column(String(500), nullable=True)     # comma-separated To addresses
    cc_recipients = Column(String(500), nullable=True)  # comma-separated CC addresses (blank for level 1)

class EmailRecipient(Base):
    """
    Admin-configurable recipient list that powers ALL automated emails
    (missing-data reminders, 3-level escalation, and generated reports).
    Replaces the hardcoded email addresses that used to live directly in
    reminder_service.py / report_save_routes.py.

    recipient_type is one of: "staff_incharge", "plant_head", "president".
      - staff_incharge rows always have a department (e.g. "production").
      - plant_head / president rows have department = NULL (plant-wide).
    plant_id is nullable: a NULL plant_id row is a global fallback used
    when no plant-specific row exists for that (plant, department, type)
    combination — this lets a single "President" row cover every plant
    until an admin adds plant-specific overrides.
    """
    __tablename__ = "email_recipients"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True)
    department = Column(String(50), nullable=True)
    recipient_type = Column(String(100), nullable=False)  # staff_incharge / plant_head / president
    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class LoginAuditLog(Base):
    """
    Records every login attempt — both the existing local (username +
    app password) flow and the new AD/Windows (GEN ID + domain password)
    flow — so authentication activity stays auditable regardless of
    which method a user signs in with.

    `reason` is an internal-only diagnostic (e.g. "invalid_credentials",
    "ad_service_unavailable", "not_provisioned_for_plant") and is NEVER
    shown to the person logging in — the login screen always shows a
    single generic error message, per security requirement.
    """
    __tablename__ = "login_audit_log"
    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(100), nullable=False)     # username or GEN ID as entered
    auth_method = Column(String(20), nullable=False)      # "local" | "ad"
    success = Column(Boolean, nullable=False)
    role = Column(String(20), nullable=True)
    plant_id = Column(Integer, nullable=True)
    department = Column(String(50), nullable=True)
    reason = Column(String(200), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    report_type = Column(String(20), nullable=False)  # monthly / quarterly / yearly
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    production_plan = Column(Float, default=0)
    production_actual = Column(Float, default=0)
    manpower_plan = Column(Float, default=0)
    manpower_actual = Column(Float, default=0)
    sales_plan = Column(Float, default=0)
    sales_actual = Column(Float, default=0)
    ovc_plan = Column(Float, default=0)
    ovc_actual = Column(Float, default=0)


class UserApprovalRequest(Base):
    """
    Tracks a Plant Head's request to add or deactivate a Data Entry User
    (role_access row), pending Admin approval via a one-time emailed
    link. See app/services/approval_service.py for the full workflow
    (creation, emailing, token verification, applying the change).

    Admin's OWN direct add/remove via the Admin Dashboard is completely
    unaffected by this table — that still goes straight to role_access
    with no approval step, exactly as before. This table only comes
    into play when the actor is a Plant Head.
    """
    __tablename__ = "user_approval_requests"
    id = Column(Integer, primary_key=True, index=True)

    # "add" -> create a new role_access row on approval.
    # "remove" -> mark an existing role_access row inactive on approval
    #             (never a hard delete, per requirement).
    action = Column(String(10), nullable=False)

    # "pending" | "approved" | "rejected" | "expired"
    status = Column(String(15), nullable=False, default="pending")

    # Who asked (the Plant Head), from their JWT at request time.
    requested_by_username = Column(String(50), nullable=False)
    requested_by_email = Column(String(100), nullable=True)

    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)

    # For action="add": the new Data Entry User's details (mirrors
    # RoleAccessCreate). For action="remove": target_user_id points at
    # the existing role_access row instead, and these are left NULL.
    role = Column(String(50), nullable=True)
    person_name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    employee_id = Column(String(50), nullable=True)

    # For action="remove" only — the role_access.id being deactivated.
    target_user_id = Column(Integer, ForeignKey("role_access.id"), nullable=True)

    # One-time approval token: only the SHA-256 hash is stored (never
    # the raw token — same principle as never storing a plaintext
    # password), so a leaked/old database backup alone can't be used to
    # forge approvals. The raw token exists only in the emailed link.
    token_hash = Column(String(64), nullable=False, unique=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    decided_by_ip = Column(String(64), nullable=True)  # best-effort audit trail; the clicker isn't authenticated