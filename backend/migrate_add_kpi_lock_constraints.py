"""
migrate_add_kpi_lock_constraints.py
------------------------------------
One-time migration: adds the UNIQUE constraints backing the date-wise KPI
entry lock:

    daily_production   (plant_id, date)
    daily_manpower      (plant_id, date)
    customer_despatch   (plant_id, date, customer_name)
    ovc_elements        (plant_id, date, element_type)
    sales_data          (plant_id, date, segment)

Since the old upsert-based /entry endpoints never allowed more than one row
per key, existing data should already satisfy these constraints — but this
script checks for duplicates first and reports them instead of failing
partway through, so you can clean up before re-running.

Works against whichever database `app.database.engine` resolves to
(SQL Server if reachable, otherwise the local SQLite fallback).

Run with:
    python migrate_add_kpi_lock_constraints.py
"""

from sqlalchemy import inspect, text

from app.database import engine

# table -> (key columns, constraint/index name)
CONSTRAINTS = [
    ("daily_production",  ["plant_id", "date"],                   "uq_production_plant_date"),
    ("daily_manpower",    ["plant_id", "date"],                   "uq_manpower_plant_date"),
    ("customer_despatch", ["plant_id", "date", "customer_name"],  "uq_despatch_plant_date_customer"),
    ("ovc_elements",      ["plant_id", "date", "element_type"],   "uq_ovc_plant_date_element_type"),
    ("sales_data",        ["plant_id", "date", "segment"],        "uq_sales_plant_date_segment"),
]


def find_duplicates(conn, table: str, cols: list[str]):
    col_list = ", ".join(cols)
    rows = conn.execute(text(f"""
        SELECT {col_list}, COUNT(*) as cnt
        FROM {table}
        GROUP BY {col_list}
        HAVING COUNT(*) > 1
    """)).fetchall()
    return rows


def constraint_exists(table: str, name: str) -> bool:
    inspector = inspect(engine)
    dialect = engine.dialect.name
    if dialect == "sqlite":
        existing = [ix["name"] for ix in inspector.get_indexes(table)]
    else:
        existing = [uc["name"] for uc in inspector.get_unique_constraints(table)]
        existing += [ix["name"] for ix in inspector.get_indexes(table)]
    return name in existing


def add_constraint(table: str, cols: list[str], name: str):
    dialect = engine.dialect.name
    col_list = ", ".join(cols)
    with engine.begin() as conn:
        if dialect == "sqlite":
            # SQLite: a UNIQUE index enforces the same guarantee as a
            # UNIQUE constraint and doesn't require recreating the table.
            conn.execute(text(f"CREATE UNIQUE INDEX {name} ON {table} ({col_list})"))
        else:
            conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({col_list})"))
    print(f"  + added unique constraint {name} on {table} ({col_list})")


def main():
    print(f"Using DB dialect: {engine.dialect.name}")
    with engine.connect() as conn:
        for table, cols, name in CONSTRAINTS:
            print(f"Checking {table}...")
            dupes = find_duplicates(conn, table, cols)
            if dupes:
                print(f"  ! Found {len(dupes)} duplicate key(s) in {table} for {cols}.")
                print(f"    Resolve these manually before this constraint can be added:")
                for d in dupes[:10]:
                    print(f"      {tuple(d)}")
                continue

            if constraint_exists(table, name):
                print(f"  constraint {name} already exists on {table}, skipping.")
                continue

            add_constraint(table, cols, name)

    print("Migration complete.")


if __name__ == "__main__":
    main()