"""
history_utils.py
-----------------
DEPRECATED: this module previously deleted the oldest rows once a
department's record count passed 30, so that "History" screens never
showed more than the most recent 30 entries.

Per the current requirement, History pages must show only the latest 30
records by default (newest first) while RETAINING every older record in
the database - older data is still needed for reporting, auditing, and
the President Dashboard's historical filters. Deleting rows is no longer
acceptable.

The "latest 30, newest first" behavior is now implemented purely as a
read-side concern: every `/history/{plant_id}` endpoint (production,
manpower, despatch, sales, OVC, rejection PPM, product value) already
orders by `date.desc()` and defaults to `limit=30`, with no deletion of
underlying rows. See e.g. `app/routes/production_routes.py`.

`enforce_history_limit()` is kept below as a harmless no-op (it does
NOT delete anything) purely so that any old call site that still
imports/calls it does not break the app. New code should not call it -
there is nothing for it to do.
"""
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger("digitaldrm.history")

# Kept only for readability in any legacy call sites; no longer enforced
# by deleting rows.
HISTORY_LIMIT = 30


def enforce_history_limit(db: Session, model, filters: list, date_col, id_col, limit: int = HISTORY_LIMIT):
    """
    DEPRECATED NO-OP. Previously deleted the oldest rows beyond `limit`.
    Now does nothing and only logs a warning, so that older records are
    always retained in the database. Display-side limiting to the latest
    30 records (newest first) is handled by each `/history/{plant_id}`
    endpoint's own `limit` query parameter instead.
    """
    logger.warning(
        "[DEPRECATED] enforce_history_limit() called for model=%s but is now a "
        "no-op - records are no longer deleted. Use the /history endpoint's "
        "`limit` query parameter for display-only limiting instead.",
        getattr(model, "__tablename__", model),
    )
    return