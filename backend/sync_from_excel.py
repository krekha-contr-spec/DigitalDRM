"""
sync_from_excel.py
-------------------
Run this any time data/users.xlsx changes. It requires NO code changes — ever.

Usage:
    python sync_from_excel.py
    python sync_from_excel.py --user-file path/to/other_users.xlsx
"""

import argparse
from pathlib import Path

from app.database import SessionLocal, Base, engine
from app.services.user_import_service import import_users_from_file

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_USER_FILE = BASE_DIR / "data" / "users.xlsx"


def main():
    parser = argparse.ArgumentParser(description="Sync users from Excel into the DigitalDRM database.")
    parser.add_argument("--user-file", default=str(DEFAULT_USER_FILE), help="Path to users.xlsx")
    args = parser.parse_args()

    # Make sure the table exists even on a fresh DB.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        u = import_users_from_file(db, args.user_file)
    finally:
        db.close()

    print("\n👤 User master sync:")
    print(f"   rows processed: {u['total_rows']} | created: {u['created']} | "
          f"updated: {u['updated']} | unchanged: {u['unchanged']} | "
          f"deactivated: {u['deactivated']} | skipped: {u['skipped']}")

    if u["errors"]:
        print(f"\n⚠️  {len(u['errors'])} warning(s):")
        for e in u["errors"]:
            print(f"   - {e}")

    print("\n✅ Sync complete. No Python code was changed or needs to be changed.")


if __name__ == "__main__":
    main()