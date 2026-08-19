import os
import sys

# Add the backend directory to sys.path so we can import 'app'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal
from app.models.models import User
from app.services.auth import hash_password

def init_db():
    Base.metadata.create_all(bind=engine)

def create_admin_user():
    db = SessionLocal()
    try:
        # Check if Admin already exists
        admin_user = db.query(User).filter(User.username == "Admin").first()
        if admin_user:
            print("✅ Admin user already exists. Updating password and role to defaults...")
            admin_user.password = hash_password("Admin@123")
            admin_user.role = "admin"
            db.commit()
            return
        
        print("Creating Admin user...")
        new_admin = User(
            username="Admin",
            password=hash_password("Admin@123"),
            role="admin",
            plant_id=None # Admin doesn't belong to a specific plant
        )
        db.add(new_admin)
        db.commit()
        print("✅ Admin user created successfully (Username: Admin, Password: Admin@123).")
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    create_admin_user()
