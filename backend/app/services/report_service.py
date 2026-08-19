from sqlalchemy import func

from app.models.models import (
    DailyProduction,
    DailyManpower,
    SalesData,
    OVCElement,
    CustomerDespatch,
)

REJECTION_PPM_TYPE = "Rejection PPM"
PRODUCT_VALUE_TYPE = "Product Value"

# Quarter Mapping (Indian FY: Q1 = Apr-Jun)
def get_quarter_months(quarter: int):
    quarter_map = {
        1: [4, 5, 6],
        2: [7, 8, 9],
        3: [10, 11, 12],
        4: [1, 2, 3],
    }
    return quarter_map.get(quarter, [])


def _ovc_typed_query(db, plant_id, element_type, year_filter, month_filter=None):
    """Reusable helper: sum plan/actual for a specific OVCElement element_type."""
    q = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == element_type,
    )
    if isinstance(year_filter, list):
        q = q.filter(func.month(OVCElement.date).in_(year_filter[0]))
        q = q.filter(func.year(OVCElement.date) == year_filter[1])
    else:
        q = q.filter(func.year(OVCElement.date) == year_filter)
        if month_filter is not None:
            q = q.filter(func.month(OVCElement.date) == month_filter)
    return q.first()


def _dept(row, key="variance"):
    """Safely build a dept dict from a SQLAlchemy aggregate row."""
    plan   = row.plan   or 0
    actual = row.actual or 0
    return {
        "plan":     plan,
        "actual":   actual,
        "variance": actual - plan,
    }


def _get_departments_needing_attention(dept_data, threshold=80):
    """
    Identify departments that are below the performance threshold.
    
    Args:
        dept_data: Dictionary of department data with plan/actual
        threshold: Performance threshold percentage (default 80%)
    
    Returns:
        List of dictionaries with department name, achievement %, and variance
    """
    needing_attention = []
    
    dept_names = [
        "Production", "Manpower", "Sales", "OVC Elements", 
        "Despatch", "Rejection PPM", "Product Value"
    ]
    
    for dept_name in dept_names:
        if dept_name in dept_data:
            data = dept_data[dept_name]
            plan = data.get("plan", 0)
            actual = data.get("actual", 0)
            
            # Calculate achievement percentage
            achievement = (actual / plan * 100) if plan > 0 else 0
            
            # Check if below threshold and has data (plan > 0)
            if achievement < threshold and plan > 0:
                needing_attention.append({
                    "name": dept_name,
                    "achievement": round(achievement, 2),
                    "plan": plan,
                    "actual": actual,
                    "variance": actual - plan
                })
    
    # Sort by achievement (lowest first)
    needing_attention.sort(key=lambda x: x["achievement"])
    
    return needing_attention


# ── Monthly Report ───────────────────────────────────────────────────────────
def generate_monthly_report(db, plant_id: int, year: int, month: int):
    production = db.query(
        func.sum(DailyProduction.plan).label("plan"),
        func.sum(DailyProduction.actual).label("actual"),
    ).filter(
        DailyProduction.plant_id == plant_id,
        func.year(DailyProduction.date) == year,
        func.month(DailyProduction.date) == month,
    ).first()

    manpower = db.query(
        func.sum(DailyManpower.plan).label("plan"),
        func.sum(DailyManpower.actual).label("actual"),
    ).filter(
        DailyManpower.plant_id == plant_id,
        func.year(DailyManpower.date) == year,
        func.month(DailyManpower.date) == month,
    ).first()

    sales = db.query(
        func.sum(SalesData.month_plan).label("plan"),
        func.sum(SalesData.mtd_actual).label("actual"),
    ).filter(
        SalesData.plant_id == plant_id,
        func.year(SalesData.date) == year,
        func.month(SalesData.date) == month,
    ).first()

    despatch = db.query(
        func.sum(CustomerDespatch.month_plan).label("plan"),
        func.sum(CustomerDespatch.mtd_actual).label("actual"),
    ).filter(
        CustomerDespatch.plant_id == plant_id,
        func.year(CustomerDespatch.date) == year,
        func.month(CustomerDespatch.date) == month,
    ).first()

    ovc = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type.notin_([REJECTION_PPM_TYPE, PRODUCT_VALUE_TYPE]),
        func.year(OVCElement.date) == year,
        func.month(OVCElement.date) == month,
    ).first()

    rejection_ppm = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == REJECTION_PPM_TYPE,
        func.year(OVCElement.date) == year,
        func.month(OVCElement.date) == month,
    ).first()

    product_value = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == PRODUCT_VALUE_TYPE,
        func.year(OVCElement.date) == year,
        func.month(OVCElement.date) == month,
    ).first()

    # Build department data dictionary
    dept_data = {
        "Production": _dept(production),
        "Manpower": _dept(manpower),
        "Sales": _dept(sales),
        "Despatch": _dept(despatch),
        "OVC Elements": _dept(ovc),
        "Rejection PPM": _dept(rejection_ppm),
        "Product Value": _dept(product_value),
    }

    # Calculate departments needing attention
    departments_needing_attention = _get_departments_needing_attention(dept_data, threshold=80)

    return {
        "report_type": "Monthly",
        "year": year,
        "month": month,
        "production": dept_data["Production"],
        "manpower": dept_data["Manpower"],
        "sales": dept_data["Sales"],
        "despatch": dept_data["Despatch"],
        "ovc": dept_data["OVC Elements"],
        "rejection_ppm": dept_data["Rejection PPM"],
        "product_value": dept_data["Product Value"],
        "departments_needing_attention": departments_needing_attention,
        "summary": {
            "total_departments": len([d for d in dept_data.values() if d["plan"] > 0 or d["actual"] > 0]),
            "departments_needing_attention_count": len(departments_needing_attention),
            "departments_needing_attention": departments_needing_attention
        }
    }


# ── Quarterly Report ─────────────────────────────────────────────────────────
def generate_quarterly_report(db, plant_id: int, year: int, quarter: int):
    months = get_quarter_months(quarter)

    production = db.query(
        func.sum(DailyProduction.plan).label("plan"),
        func.sum(DailyProduction.actual).label("actual"),
    ).filter(
        DailyProduction.plant_id == plant_id,
        func.year(DailyProduction.date) == year,
        func.month(DailyProduction.date).in_(months),
    ).first()

    manpower = db.query(
        func.sum(DailyManpower.plan).label("plan"),
        func.sum(DailyManpower.actual).label("actual"),
    ).filter(
        DailyManpower.plant_id == plant_id,
        func.year(DailyManpower.date) == year,
        func.month(DailyManpower.date).in_(months),
    ).first()

    sales = db.query(
        func.sum(SalesData.month_plan).label("plan"),
        func.sum(SalesData.mtd_actual).label("actual"),
    ).filter(
        SalesData.plant_id == plant_id,
        func.year(SalesData.date) == year,
        func.month(SalesData.date).in_(months),
    ).first()

    despatch = db.query(
        func.sum(CustomerDespatch.month_plan).label("plan"),
        func.sum(CustomerDespatch.mtd_actual).label("actual"),
    ).filter(
        CustomerDespatch.plant_id == plant_id,
        func.year(CustomerDespatch.date) == year,
        func.month(CustomerDespatch.date).in_(months),
    ).first()

    ovc = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type.notin_([REJECTION_PPM_TYPE, PRODUCT_VALUE_TYPE]),
        func.year(OVCElement.date) == year,
        func.month(OVCElement.date).in_(months),
    ).first()

    rejection_ppm = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == REJECTION_PPM_TYPE,
        func.year(OVCElement.date) == year,
        func.month(OVCElement.date).in_(months),
    ).first()

    product_value = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == PRODUCT_VALUE_TYPE,
        func.year(OVCElement.date) == year,
        func.month(OVCElement.date).in_(months),
    ).first()

    # Build department data dictionary
    dept_data = {
        "Production": _dept(production),
        "Manpower": _dept(manpower),
        "Sales": _dept(sales),
        "Despatch": _dept(despatch),
        "OVC Elements": _dept(ovc),
        "Rejection PPM": _dept(rejection_ppm),
        "Product Value": _dept(product_value),
    }

    # Calculate departments needing attention
    departments_needing_attention = _get_departments_needing_attention(dept_data, threshold=80)

    return {
        "report_type": "Quarterly",
        "year": year,
        "quarter": quarter,
        "production": dept_data["Production"],
        "manpower": dept_data["Manpower"],
        "sales": dept_data["Sales"],
        "despatch": dept_data["Despatch"],
        "ovc": dept_data["OVC Elements"],
        "rejection_ppm": dept_data["Rejection PPM"],
        "product_value": dept_data["Product Value"],
        "departments_needing_attention": departments_needing_attention,
        "summary": {
            "total_departments": len([d for d in dept_data.values() if d["plan"] > 0 or d["actual"] > 0]),
            "departments_needing_attention_count": len(departments_needing_attention),
            "departments_needing_attention": departments_needing_attention
        }
    }


# ── Yearly Report ────────────────────────────────────────────────────────────
def generate_yearly_report(db, plant_id: int, year: int):
    production = db.query(
        func.sum(DailyProduction.plan).label("plan"),
        func.sum(DailyProduction.actual).label("actual"),
    ).filter(
        DailyProduction.plant_id == plant_id,
        func.year(DailyProduction.date) == year,
    ).first()

    manpower = db.query(
        func.sum(DailyManpower.plan).label("plan"),
        func.sum(DailyManpower.actual).label("actual"),
    ).filter(
        DailyManpower.plant_id == plant_id,
        func.year(DailyManpower.date) == year,
    ).first()

    sales = db.query(
        func.sum(SalesData.month_plan).label("plan"),
        func.sum(SalesData.mtd_actual).label("actual"),
    ).filter(
        SalesData.plant_id == plant_id,
        func.year(SalesData.date) == year,
    ).first()

    despatch = db.query(
        func.sum(CustomerDespatch.month_plan).label("plan"),
        func.sum(CustomerDespatch.mtd_actual).label("actual"),
    ).filter(
        CustomerDespatch.plant_id == plant_id,
        func.year(CustomerDespatch.date) == year,
    ).first()

    ovc = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type.notin_([REJECTION_PPM_TYPE, PRODUCT_VALUE_TYPE]),
        func.year(OVCElement.date) == year,
    ).first()

    rejection_ppm = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == REJECTION_PPM_TYPE,
        func.year(OVCElement.date) == year,
    ).first()

    product_value = db.query(
        func.sum(OVCElement.plan).label("plan"),
        func.sum(OVCElement.actual).label("actual"),
    ).filter(
        OVCElement.plant_id == plant_id,
        OVCElement.element_type == PRODUCT_VALUE_TYPE,
        func.year(OVCElement.date) == year,
    ).first()

    # Build department data dictionary
    dept_data = {
        "Production": _dept(production),
        "Manpower": _dept(manpower),
        "Sales": _dept(sales),
        "Despatch": _dept(despatch),
        "OVC Elements": _dept(ovc),
        "Rejection PPM": _dept(rejection_ppm),
        "Product Value": _dept(product_value),
    }

    # Calculate departments needing attention
    departments_needing_attention = _get_departments_needing_attention(dept_data, threshold=80)

    return {
        "report_type": "Yearly",
        "year": year,
        "production": dept_data["Production"],
        "manpower": dept_data["Manpower"],
        "sales": dept_data["Sales"],
        "despatch": dept_data["Despatch"],
        "ovc": dept_data["OVC Elements"],
        "rejection_ppm": dept_data["Rejection PPM"],
        "product_value": dept_data["Product Value"],
        "departments_needing_attention": departments_needing_attention,
        "summary": {
            "total_departments": len([d for d in dept_data.values() if d["plan"] > 0 or d["actual"] > 0]),
            "departments_needing_attention_count": len(departments_needing_attention),
            "departments_needing_attention": departments_needing_attention
        }
    }