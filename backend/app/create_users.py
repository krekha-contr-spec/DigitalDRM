"""
create_users.py
-----------------
One-time bootstrap script. Its jobs, both idempotent (safe to run more
than once):

  1. Make sure the reference Plant rows exist.
  2. Make sure a default Admin account exists (username: Admin,
     password: Admin@123, stored bcrypt-hashed -- never in plaintext).

It never creates or touches Data Entry User accounts (role = 'plant' /
'president', etc). Those are created, edited, deleted, activated /
deactivated, and imported exclusively through the Admin's "Data Entry
Users Management" module (see app/routes/user_admin_routes.py), and are
always read live from the SQL Server database -- never from this script.

Run with:  python -m app.create_users
"""

from app.database import SessionLocal
from app.models.models import Plant, User
from app.services.auth import hash_password

DEFAULT_ADMIN_USERNAME = "Admin"
DEFAULT_ADMIN_PASSWORD = "Admin@123"  # only ever used to seed the hash below

DEFAULT_PLANTS = [
    (2, "Plant 2"),
    (3, "Plant 3"),
    (4, "Plant 4"),
    (5, "Plant 5"),
    (6, "Plant 6"),
]


def ensure_default_plants(db):
    created = 0
    for plant_id, name in DEFAULT_PLANTS:
        if not db.query(Plant).filter(Plant.id == plant_id).first():
            db.add(Plant(id=plant_id, name=name))
            created += 1
    if created:
        db.commit()
        print(f"Created {created} missing plant row(s).")
    else:
        print("Plants already exist -- nothing to do.")


def ensure_default_admin(db):
    existing = db.query(User).filter(User.username == DEFAULT_ADMIN_USERNAME).first()
    if existing:
        print(f"Admin account '{DEFAULT_ADMIN_USERNAME}' already exists -- nothing to do.")
        return

    admin = User(
        username=DEFAULT_ADMIN_USERNAME,
        password=hash_password(DEFAULT_ADMIN_PASSWORD),
        role="admin",
        plant_id=None,
        is_active=1,
    )
    db.add(admin)
    db.commit()
    print(f"Default Admin account created: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}")
    print("Please log in and change this password as soon as possible.")


def main():
    db = SessionLocal()
    try:
        ensure_default_plants(db)
        ensure_default_admin(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
