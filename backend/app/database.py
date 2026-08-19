import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


import os
from urllib.parse import quote_plus

import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# =========================
# DATABASE CONFIG
# =========================

SERVER = os.getenv("DB_SERVER", "REVLGNDYSQL")
DATABASE = os.getenv("DB_NAME", "DigitalDRM_DB")
USER = os.getenv("DB_USER", "sa")
PASSWORD = os.getenv("DB_PASSWORD", "Password@123")
DB_DRIVER = os.getenv("DB_DRIVER")


def resolve_sql_server_driver():
    preferred_drivers = [
        DB_DRIVER,
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    installed_drivers = set(pyodbc.drivers())

    for driver_name in preferred_drivers:
        if driver_name and driver_name in installed_drivers:
            return driver_name

    return next(iter(installed_drivers), None)


# =========================
# ODBC CONNECTION STRING
# =========================

driver_name = resolve_sql_server_driver()
odbc_str = (
    f"DRIVER={driver_name};"
    f"SERVER={SERVER},1433;"
    f"DATABASE={DATABASE};"
    f"UID={USER};"
    f"PWD={PASSWORD};"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
)

params = quote_plus(odbc_str)
CONNECTION_STRING = f"mssql+pyodbc:///?odbc_connect={params}"


def create_sql_server_engine():
    return create_engine(
        CONNECTION_STRING,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


def create_sqlite_engine():
    sqlite_path = os.path.join(os.path.dirname(__file__), "..", "digitaldrm.db")
    return create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )


# =========================
# SQLALCHEMY ENGINE
# =========================

engine = None
try:
    engine = create_sql_server_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    print("✅ Connected to SQL Server database.")
except Exception as exc:
    print(f"⚠️ SQL Server unavailable: {exc}")
    print("⚠️ Using local SQLite database instead.")
    engine = create_sqlite_engine()

# =========================
# SESSION
# =========================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# =========================
# DB DEPENDENCY
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# STARTUP MIGRATION
# =========================
# Adds the `updated_at` column (used for the "Last Updated" field) to every
# daily-entry table if it doesn't already exist. Safe to run every startup —
# it's a no-op once the column is present. Works on both SQL Server and
# SQLite without needing Alembic. Existing rows are backfilled from their
# `date` value so "Last Updated" is never blank for historical data; every
# row saved from now on gets a real save-time timestamp.
def run_history_migrations():
    from sqlalchemy import inspect

    tables = [
        "daily_production",
        "daily_manpower",
        "customer_despatch",
        "ovc_elements",
        "sales_data",
    ]

    try:
        inspector = inspect(engine)
    except Exception as exc:
        print(f"⚠️ Could not inspect database for migrations: {exc}")
        return

    for table in tables:
        try:
            existing_cols = [c["name"] for c in inspector.get_columns(table)]
        except Exception:
            # Table doesn't exist yet — nothing to migrate.
            continue

        if "updated_at" in existing_cols:
            continue

        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD updated_at DATETIME"))
                conn.execute(text(f"UPDATE {table} SET updated_at = [date] WHERE updated_at IS NULL"))
                conn.commit()
            print(f"✅ Migration: added updated_at column to {table}")
        except Exception as exc:
            print(f"⚠️ Could not add updated_at to {table}: {exc}")


# =========================
# STARTUP MIGRATION — role_access Excel-import columns
# =========================
# Adds `employee_id` and `is_active` to role_access if missing (older DBs
# created before the Excel-import feature). Safe/no-op once present.
# Existing rows are backfilled with is_active = 1 so nobody already in the
# table is accidentally treated as inactive.
def run_role_access_migrations():
    from sqlalchemy import inspect

    try:
        inspector = inspect(engine)
        existing_cols = [c["name"] for c in inspector.get_columns("role_access")]
    except Exception:
        # Table doesn't exist yet — nothing to migrate.
        return

    is_sqlite = engine.dialect.name == "sqlite"

    if "employee_id" not in existing_cols:
        try:
            with engine.connect() as conn:
                col_type = "VARCHAR(50)" if is_sqlite else "NVARCHAR(50)"
                conn.execute(text(f"ALTER TABLE role_access ADD employee_id {col_type} NULL"))
                conn.commit()
            print("✅ Migration: added employee_id column to role_access")
        except Exception as exc:
            print(f"⚠️ Could not add employee_id to role_access: {exc}")

    if "is_active" not in existing_cols:
        try:
            with engine.connect() as conn:
                bool_type = "BOOLEAN" if is_sqlite else "BIT"
                conn.execute(text(f"ALTER TABLE role_access ADD is_active {bool_type} NULL"))
                conn.execute(text("UPDATE role_access SET is_active = 1 WHERE is_active IS NULL"))
                conn.commit()
            print("✅ Migration: added is_active column to role_access")
        except Exception as exc:
            print(f"⚠️ Could not add is_active to role_access: {exc}")

    # ---------------------------------------------------------------
    # De-duplicate existing rows. The (plant_id, role, person_name, email)
    # UniqueConstraint on the RoleAccess model never actually reached the
    # physical table if `role_access` already existed before that
    # constraint was added — so duplicate rows could (and did) get
    # inserted every time the same person appeared in an Excel sync.
    # This collapses each duplicate group down to one row, preferring an
    # active row and the earliest id, before older duplicates.
    # ---------------------------------------------------------------
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, plant_id, role, person_name, email, is_active FROM role_access")
            ).mappings().all()

        groups = {}
        for r in rows:
            key = (r["plant_id"], r["role"], r["person_name"], r["email"])
            groups.setdefault(key, []).append(r)

        ids_to_delete = []
        for key, group_rows in groups.items():
            if len(group_rows) <= 1:
                continue
            # Keep one: prefer an active row, then the lowest (oldest) id.
            group_rows.sort(key=lambda r: (not bool(r["is_active"]), r["id"]))
            ids_to_delete.extend(r["id"] for r in group_rows[1:])

        if ids_to_delete:
            with engine.connect() as conn:
                id_list = ", ".join(str(int(i)) for i in ids_to_delete)
                conn.execute(text(f"DELETE FROM role_access WHERE id IN ({id_list})"))
                conn.commit()
            print(f"✅ Migration: removed {len(ids_to_delete)} duplicate role_access row(s).")
    except Exception as exc:
        print(f"⚠️ Could not de-duplicate role_access: {exc}")

    # ---------------------------------------------------------------
    # Now that duplicates are gone, actually enforce uniqueness on the
    # physical table going forward (this is what the model's
    # UniqueConstraint was supposed to guarantee all along). Safe to run
    # every startup — if the index already exists, the DB rejects the
    # CREATE and we just ignore that.
    # ---------------------------------------------------------------
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE UNIQUE INDEX ux_role_access_dedupe "
                "ON role_access (plant_id, role, person_name, email)"
            ))
            conn.commit()
        print("✅ Migration: added unique index to prevent future role_access duplicates.")
    except Exception:
        # Already exists (most common case on every startup after the
        # first) — nothing to do.
        pass


def run_login_audit_migrations():
    """
    Creates the login_audit_log table if it doesn't exist yet. Safe to
    run every startup (create-if-missing, no data touched).
    """
    from app.models.models import Base as ModelsBase, LoginAuditLog

    try:
        ModelsBase.metadata.create_all(bind=engine, tables=[LoginAuditLog.__table__])
    except Exception as exc:
        print(f"⚠️ Could not create login_audit_log table: {exc}")


def run_user_approval_migrations():
    """
    Creates the user_approval_requests table if it doesn't exist yet —
    see app/models/models.UserApprovalRequest and
    app/services/approval_service.py for the full email-based
    Plant-Head-add/remove-user approval workflow this backs. No default
    rows — every request is created live when a Plant Head submits one.
    """
    from app.models.models import Base as ModelsBase, UserApprovalRequest

    try:
        ModelsBase.metadata.create_all(bind=engine, tables=[UserApprovalRequest.__table__])
    except Exception as exc:
        print(f"⚠️ Could not create user_approval_requests table: {exc}")


def run_email_recipient_migrations():
    """
    Creates the email_recipients table if it doesn't exist yet (new
    feature — no ALTER TABLE needed, just create-if-missing). No default
    rows are hardcoded or auto-inserted here — Staff Incharge recipients
    are populated separately from the existing Data Entry Users table
    (see run_staff_incharge_email_sync() below), and Plant Head /
    President / report recipients are added by an admin directly on the
    Email Services page, which is the sole master source for all of
    them going forward.
    """
    from app.models.models import Base as ModelsBase, EmailRecipient

    try:
        ModelsBase.metadata.create_all(bind=engine, tables=[EmailRecipient.__table__])
    except Exception as exc:
        print(f"⚠️ Could not create email_recipients table: {exc}")


def run_email_recipient_department_normalization():
    """
    One-time cleanup: normalizes every email_recipients.department value
    to the canonical slug (e.g. "OVC Elements" / "OVC" / " ovc " ->
    "ovc", "Rejection PPM" -> "rejection_ppm") that reminder_service.py
    and report_save_routes.py actually query with.

    get_recipients() (email_recipient_service.py) now normalizes this
    comparison at read-time too, so a mismatched value no longer causes
    a silently-skipped reminder email — but fixing the stored value here
    as well keeps the data itself clean and consistent for anyone
    reading it directly (Admin Dashboard listing, Excel export, direct
    DB queries), rather than relying on every reader to normalize.

    Idempotent: only touches rows whose department doesn't already
    exactly equal its own slugified form, so running this repeatedly on
    an already-clean table is a no-op.
    """
    from app.models.models import EmailRecipient
    from app.services.email_recipient_service import _dept_slugify

    db = SessionLocal()
    try:
        rows = (
            db.query(EmailRecipient)
            .filter(EmailRecipient.department.isnot(None))
            .all()
        )
        fixed = 0
        for row in rows:
            slug = _dept_slugify(row.department)
            if slug and slug != row.department:
                row.department = slug
                fixed += 1
        if fixed:
            db.commit()
            print(f"✅ Normalized {fixed} email_recipients.department value(s) to canonical slugs.")
    except Exception as exc:
        print(f"⚠️ Could not normalize email_recipients.department values: {exc}")
        db.rollback()
    finally:
        db.close()


def run_staff_incharge_email_sync():
    """
    Populates Email Services' Staff Incharge recipients from the Admin
    Dashboard's Data Entry Users (role_access) table — for every plant,
    with no department-wise email address ever hardcoded in code. Must
    run AFTER the Excel users.xlsx auto-sync in main.py's startup (so
    role_access is already populated) and is safe to run every startup:
    only fills genuinely missing (plant, department) slots, never
    overwrites an Admin's Email Services edits. See
    app/services/email_recipient_service.sync_staff_incharge_from_role_access().
    """
    from app.services.email_recipient_service import sync_staff_incharge_from_role_access

    db = SessionLocal()
    try:
        result = sync_staff_incharge_from_role_access(db)
        if result.get("created"):
            print(
                f"✅ Synced {result['created']} Staff Incharge recipient(s) into "
                f"Email Services from Data Entry Users."
            )
    except Exception as exc:
        print(f"⚠️ Could not sync Staff Incharge recipients from Data Entry Users: {exc}")
    finally:
        db.close()


def run_role_access_email_sync():
    """
    Fills in any (plant, department) Data Entry User slots that don't
    have someone assigned yet, using the Admin Dashboard's Email
    Services staff-incharge configuration as the default source (Name,
    Email, Role/Department, Plant come straight from there). Safe to run
    every startup: it never overwrites or duplicates a role_access row
    that's already occupied, whether that row came from a previous run
    of this same sync, the Excel importer, or an admin's manual edit.

    Must run AFTER both run_email_recipient_migrations() (so
    email_recipients exists and is seeded) and the Excel users.xlsx
    auto-sync in main.py's startup (so this only fills genuine gaps
    instead of racing the Excel import's full_sync deactivation logic).
    See app/services/email_recipient_service.sync_role_access_from_staff_incharge().
    """
    from app.services.email_recipient_service import sync_role_access_from_staff_incharge

    db = SessionLocal()
    try:
        result = sync_role_access_from_staff_incharge(db)
        if result.get("created"):
            print(
                f"✅ Synced {result['created']} Data Entry User(s) from "
                f"Email Services staff-incharge configuration."
            )
    except Exception as exc:
        print(f"⚠️ Could not sync Data Entry Users from Email Services: {exc}")
    finally:
        db.close()


# Plant IDs the Daily Report is generated for — kept in sync with
# daily_report_service.ALL_PLANT_IDS. Duplicated here (rather than
# imported) to avoid a circular import at startup; both lists must be
# updated together if a plant is ever added/removed.
_DAILY_REPORT_PLANT_IDS = [2, 3, 4, 5, 6]
_DAILY_REPORT_SEED_EMAILS = {
    5: "adprisha12@gmail.com",
}
_DAILY_REPORT_PLACEHOLDER_NAME = "(Not set — add Staff Incharge email in Admin > Email Services)"


def run_report_recipient_migration():
    """
    One-time cleanup: the old "report_recipient" (Combined Report
    Recipient) type has been removed — Monthly/Quarterly/Yearly reports
    now go to "president" instead, since there's only one President per
    plant (or globally), not a separate combined-report role. This
    migrates any existing report_recipient rows over:

    - If that plant already has a "president" row configured, the old
      report_recipient row is just deleted (redundant — president's
      address is already correct and used).
    - Otherwise, the row is converted in place (recipient_type updated
      to "president"), preserving whatever email/name was already set,
      so nothing silently stops sending after this deploys.

    Safe to run every startup — it's a no-op once no report_recipient
    rows remain (which is true after the first run).
    """
    from app.models.models import EmailRecipient

    db = SessionLocal()
    try:
        old_rows = db.query(EmailRecipient).filter(EmailRecipient.recipient_type == "report_recipient").all()
        if not old_rows:
            return

        converted, deleted = 0, 0
        for row in old_rows:
            existing_president = (
                db.query(EmailRecipient)
                .filter(
                    EmailRecipient.recipient_type == "president",
                    EmailRecipient.plant_id == row.plant_id,
                    EmailRecipient.department.is_(None),
                )
                .first()
            )
            if existing_president:
                db.delete(row)
                deleted += 1
            else:
                row.recipient_type = "president"
                converted += 1

        db.commit()
        print(f"✅ Migrated legacy Combined Report Recipient rows: {converted} converted to President, {deleted} removed as duplicates.")
    except Exception as exc:
        print(f"⚠️ Could not migrate legacy report_recipient rows: {exc}")
        db.rollback()
    finally:
        db.close()


def run_overall_summary_recipient_seed():
    """
    Ensures the global (plant_id=None, department=None)
    "overall_summary_recipient" row exists in email_recipients — the
    President's own address, common across ALL plants, that the Overall
    Summary report (report_save_routes.py's _email_overall_summary_report,
    used whenever the President Dashboard's plant filter is set to "All
    Plants") is emailed to. Without this row configured, that email is
    silently skipped (logged as "No Overall Summary recipient
    configured").

    Seeded once with a.prisha-contr@ranegroup.com. Idempotent / safe on
    every startup: only inserts if no global overall_summary_recipient
    row exists yet — never overwrites an admin's own edit made via
    Admin Dashboard > Email Services.
    """
    from app.models.models import EmailRecipient

    SEED_EMAIL = "a.prisha-contr@ranegroup.com"

    db = SessionLocal()
    try:
        existing = (
            db.query(EmailRecipient)
            .filter(
                EmailRecipient.recipient_type == "overall_summary_recipient",
                EmailRecipient.plant_id.is_(None),
                EmailRecipient.department.is_(None),
            )
            .first()
        )
        if existing:
            return  # already configured (seeded before, or admin-added) — never overwrite

        db.add(EmailRecipient(
            plant_id=None,
            department=None,
            recipient_type="overall_summary_recipient",
            name="President",
            email=SEED_EMAIL,
            is_active=True,
        ))
        db.commit()
        print(f"✅ Seeded global Overall Summary recipient (President, all plants): {SEED_EMAIL}")
    except Exception as exc:
        print(f"⚠️ Could not seed Overall Summary recipient: {exc}")
        db.rollback()
    finally:
        db.close()


def run_daily_report_recipient_seed():
    """
    Ensures every plant in _DAILY_REPORT_PLANT_IDS has a
    "daily_report_recipient" row in email_recipients (plant-wide,
    department=None) — the address the per-plant Daily Report
    (daily_report_service.py) is emailed to.

    - Plant 5: seeded with adprisha12@gmail.com, active, so the Daily
      Report actually goes out for Plant 5 immediately.
    - Plants 2, 3, 4, 6: seeded with an empty, INACTIVE placeholder row
      (email="") so they show up in the Admin Dashboard > Email Services
      list ready for an admin to fill in the real Staff Incharge address
      later — get_recipients() only returns active rows, so an empty
      placeholder never causes an email to be sent.

    Idempotent / safe on every startup: only creates a row for a plant
    that doesn't already have a daily_report_recipient row at all. Once
    a row exists (whether from this seed or an admin's own edit via the
    Admin Dashboard), it is never touched or overwritten again — an
    admin's edit is always the new master value.
    """
    from app.models.models import EmailRecipient

    db = SessionLocal()
    created = 0
    try:
        existing_plant_ids = {
            r.plant_id
            for r in db.query(EmailRecipient.plant_id)
            .filter(
                EmailRecipient.recipient_type == "daily_report_recipient",
                EmailRecipient.department.is_(None),
            )
            .all()
        }

        for plant_id in _DAILY_REPORT_PLANT_IDS:
            if plant_id in existing_plant_ids:
                continue  # already configured (seeded before, or admin-added) — never overwrite

            seed_email = _DAILY_REPORT_SEED_EMAILS.get(plant_id)
            if seed_email:
                record = EmailRecipient(
                    plant_id=plant_id,
                    department=None,
                    recipient_type="daily_report_recipient",
                    name="Staff Incharge",
                    email=seed_email,
                    is_active=True,
                )
            else:
                record = EmailRecipient(
                    plant_id=plant_id,
                    department=None,
                    recipient_type="daily_report_recipient",
                    name=_DAILY_REPORT_PLACEHOLDER_NAME,
                    email="",
                    is_active=False,
                )
            db.add(record)
            created += 1

        if created:
            db.commit()
            print(f"✅ Seeded {created} Daily Report recipient row(s) (Plant 5 active, others left as empty placeholders).")
    except Exception as exc:
        print(f"⚠️ Could not seed Daily Report recipients: {exc}")
        db.rollback()
    finally:
        db.close()


def run_despatch_unique_constraint_migration():
    """
    Adds the (plant_id, date, customer_name) UNIQUE constraint to an
    existing customer_despatch table — see
    models.CustomerDespatch.__table_args__ for why this matters: it's
    what makes duplicate-prevention for Despatch airtight at the
    database level (not just a pre-check in despatch_routes.py), while
    still allowing any number of DIFFERENT customers (BMW, HMI, etc.)
    for the same plant+date.

    If any true duplicate rows already exist in an older database
    (multiple rows with the same plant_id+date+customer_name — which
    could only have happened before this constraint existed, e.g. from
    a race condition or a direct DB edit), those are logged and the
    OLDEST row per group is kept; the newer duplicate(s) are removed
    before the constraint is added, since SQL Server will otherwise
    refuse to create a unique index over already-duplicate data.

    Safe to run every startup: checks whether the constraint already
    exists first and is a no-op if so.
    """
    from sqlalchemy import inspect, text
    from app.models.models import CustomerDespatch

    try:
        inspector = inspect(engine)
        existing_constraints = {c["name"] for c in inspector.get_unique_constraints("customer_despatch")}
        existing_indexes = {i["name"] for i in inspector.get_indexes("customer_despatch")}
    except Exception as exc:
        print(f"⚠️ Could not inspect customer_despatch for unique-constraint migration: {exc}")
        return

    constraint_name = "uq_customer_despatch_plant_date_customer"
    if constraint_name in existing_constraints or constraint_name in existing_indexes:
        return  # already applied

    db = SessionLocal()
    try:
        # De-duplicate first (keep the oldest row per plant+date+customer)
        # so the unique index below can actually be created.
        dupes = db.execute(text("""
            SELECT plant_id, date, customer_name, COUNT(*) AS cnt
            FROM customer_despatch
            GROUP BY plant_id, date, customer_name
            HAVING COUNT(*) > 1
        """)).fetchall()

        removed = 0
        for plant_id, dup_date, customer_name, cnt in dupes:
            rows = (
                db.query(CustomerDespatch)
                .filter(
                    CustomerDespatch.plant_id == plant_id,
                    CustomerDespatch.date == dup_date,
                    CustomerDespatch.customer_name == customer_name,
                )
                .order_by(CustomerDespatch.id.asc())
                .all()
            )
            for extra in rows[1:]:  # keep the first (oldest), remove the rest
                db.delete(extra)
                removed += 1
        if removed:
            db.commit()
            print(f"⚠️ Removed {removed} pre-existing duplicate customer_despatch row(s) "
                  f"(same plant+date+customer) before adding the unique constraint.")

        # Dialect-appropriate DDL — SQL Server (production) vs SQLite
        # (local/dev fallback, per database.py's own resolve logic).
        dialect = engine.dialect.name
        if dialect in ("mssql", "sqlite"):
            db.execute(text(
                f"CREATE UNIQUE INDEX {constraint_name} "
                f"ON customer_despatch (plant_id, date, customer_name)"
            ))
        else:
            db.execute(text(
                f"ALTER TABLE customer_despatch "
                f"ADD CONSTRAINT {constraint_name} UNIQUE (plant_id, date, customer_name)"
            ))
        db.commit()
        print(f"✅ Added unique constraint on customer_despatch (plant_id, date, customer_name).")
    except Exception as exc:
        db.rollback()
        print(f"⚠️ Could not add customer_despatch unique constraint: {exc}")
    finally:
        db.close()


def run_reminder_log_migrations():
    """
    Adds the columns needed for 3-level reminder escalation (level,
    recipients, cc_recipients) to an existing reminder_email_log table.
    Safe/no-op if already present. Existing rows default to level=1 with
    no recipients/cc recorded (they predate escalation and were always
    level-1-only sends).
    """
    from sqlalchemy import inspect

    try:
        inspector = inspect(engine)
        existing_cols = [c["name"] for c in inspector.get_columns("reminder_email_log")]
    except Exception:
        # Table doesn't exist yet — SQLAlchemy's create_all() (or the
        # reminder service's own _ensure_log_table()) will create it with
        # the new columns already included. Nothing to migrate.
        return

    is_sqlite = engine.dialect.name == "sqlite"

    try:
        with engine.connect() as conn:
            if "level" not in existing_cols:
                conn.execute(text("ALTER TABLE reminder_email_log ADD level INTEGER NULL"))
                conn.execute(text("UPDATE reminder_email_log SET level = 1 WHERE level IS NULL"))
                print("✅ Migration: added level column to reminder_email_log")
            if "recipients" not in existing_cols:
                col_type = "VARCHAR(500)" if is_sqlite else "NVARCHAR(500)"
                conn.execute(text(f"ALTER TABLE reminder_email_log ADD recipients {col_type} NULL"))
                print("✅ Migration: added recipients column to reminder_email_log")
            if "cc_recipients" not in existing_cols:
                col_type = "VARCHAR(500)" if is_sqlite else "NVARCHAR(500)"
                conn.execute(text(f"ALTER TABLE reminder_email_log ADD cc_recipients {col_type} NULL"))
                print("✅ Migration: added cc_recipients column to reminder_email_log")
            conn.commit()
    except Exception as exc:
        print(f"⚠️ Could not migrate reminder_email_log for escalation columns: {exc}")