from datetime import date
from sqlalchemy import desc


def get_effective_target(session, model, target_field, date_field, filters, target_date):
    """
    Returns the latest target value that is effective on target_date.

    Example:
        User enters target on 2026-06-01 = 100
        No new target for rest of month

        2026-06-15 -> returns 100
        2026-06-28 -> returns 100

        If user changes target on 2026-06-20 = 120

        2026-06-21 onwards -> returns 120
    """

    query = session.query(model)

    for column, value in filters.items():
        query = query.filter(column == value)

    row = (
        query.filter(date_field <= target_date)
        .order_by(desc(date_field))
        .first()
    )

    if row is None:
        return 0

    value = getattr(row, target_field)

    return value if value is not None else 0


def get_month_target(session, model, target_field, date_field, filters, year, month):
    """
    Returns the carried-forward target for an entire month.

    The target used is the latest target available
    on or before the last day of that month.
    """

    if month == 12:
        month_end = date(year, 12, 31)
    else:
        from calendar import monthrange

        last_day = monthrange(year, month)[1]
        month_end = date(year, month, last_day)

    return get_effective_target(
        session=session,
        model=model,
        target_field=target_field,
        date_field=date_field,
        filters=filters,
        target_date=month_end,
    )


def get_daily_target(session, model, target_field, date_field, filters, target_date):
    """
    Returns the target for a specific day.

    Used by daily dashboard.
    """

    return get_effective_target(
        session=session,
        model=model,
        target_field=target_field,
        date_field=date_field,
        filters=filters,
        target_date=target_date,
    )


def get_yearly_target(session, model, target_field, date_field, filters, year):
    """
    Returns the effective target as of Dec 31 of the year.

    Used in yearly reports.
    """

    return get_effective_target(
        session=session,
        model=model,
        target_field=target_field,
        date_field=date_field,
        filters=filters,
        target_date=date(year, 12, 31),
    )