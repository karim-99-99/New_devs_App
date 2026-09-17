from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool

# Money is presented to two decimals, but reservations are stored as
# NUMERIC(10, 3), so summing must stay in Decimal and round only once at the end.
CENTS = Decimal("0.01")


def _to_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


async def _ensure_pool():
    if not db_pool.session_factory:
        await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> ZoneInfo:
    """Resolve the property's local timezone, scoped to the owning tenant."""
    result = await session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    if not row or not row.timezone:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(row.timezone)
    except Exception:
        return ZoneInfo("UTC")


def _month_bounds_utc(month: int, year: int, tz: ZoneInfo):
    """Month boundaries as local midnight in the property's timezone, in UTC.

    A stay checking in at 2024-02-29 23:30Z belongs to March for a Paris
    property (00:30 local on 1 March), so the window cannot be built from
    naive UTC datetimes.
    """
    start_local = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)
    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int
) -> Decimal:
    """Calculates revenue for a specific month in the property's local timezone."""
    await _ensure_pool()

    async with db_pool.get_session() as session:
        tz = await _get_property_timezone(session, property_id, tenant_id)
        start_utc, end_utc = _month_bounds_utc(month, year, tz)

        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS total
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                  AND check_in_date >= :start_date
                  AND check_in_date < :end_date
            """),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_date": start_utc,
                "end_date": end_utc,
            },
        )
        row = result.fetchone()
        return _to_money(row.total if row and row.total is not None else Decimal("0"))


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Aggregates revenue from database for one property of one tenant."""
    await _ensure_pool()

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("""
                SELECT
                    COALESCE(SUM(total_amount), 0) AS total_revenue,
                    COUNT(*) AS reservation_count,
                    MIN(currency) AS currency
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
            """),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        row = result.fetchone()

        total = _to_money(row.total_revenue if row and row.total_revenue is not None else Decimal("0"))
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            # Serialised as a string so the exact value survives the JSON cache.
            "total": str(total),
            "currency": (row.currency if row and row.currency else "USD"),
            "count": (row.reservation_count if row else 0),
        }
