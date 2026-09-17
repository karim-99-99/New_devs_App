"""Verification harness for the revenue dashboard fixes.

Run inside the backend container:
    docker compose exec -T backend python /app/verify_fixes.py
"""
import asyncio
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool
from app.services.reservations import calculate_monthly_revenue, calculate_total_revenue


async def naive_monthly_revenue(session, property_id, tenant_id, month, year):
    """The old behaviour: month boundaries built as naive UTC datetimes."""
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), (month % 12) + 1, 1)
    result = await session.execute(
        text("""
            SELECT COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS n
            FROM reservations
            WHERE property_id = :p AND tenant_id = :t
              AND check_in_date >= :s AND check_in_date < :e
        """),
        {"p": property_id, "t": tenant_id, "s": start, "e": end},
    )
    row = result.fetchone()
    return Decimal(row.total), row.n


async def main():
    await db_pool.initialize()

    print("=" * 78)
    print("1. TENANT ISOLATION  (prop-001 exists for BOTH tenants)")
    print("=" * 78)
    async with db_pool.get_session() as s:
        rows = (await s.execute(text(
            "SELECT id, tenant_id, name, timezone FROM properties ORDER BY id, tenant_id"
        ))).fetchall()
        for r in rows:
            print(f"  {r.id}  {r.tenant_id}  {r.name:<26} {r.timezone}")

    print()
    for tenant in ("tenant-a", "tenant-b"):
        res = await calculate_total_revenue("prop-001", tenant)
        print(f"  calculate_total_revenue('prop-001', '{tenant}') -> "
              f"total={res['total']:>10}  count={res['count']}")

    print()
    print("=" * 78)
    print("2. TIMEZONE BOUNDARY  (res-tz-1 checks in 2024-02-29 23:30 UTC)")
    print("=" * 78)
    paris = ZoneInfo("Europe/Paris")
    checkin_utc = datetime(2024, 2, 29, 23, 30, tzinfo=dt_timezone.utc)
    print(f"  stored UTC        : {checkin_utc}")
    print(f"  Europe/Paris local: {checkin_utc.astimezone(paris)}  <- March for the client")
    print()
    async with db_pool.get_session() as s:
        old_total, old_n = await naive_monthly_revenue(s, "prop-001", "tenant-a", 3, 2024)
    new_total = await calculate_monthly_revenue("prop-001", "tenant-a", 3, 2024)
    print(f"  March 2024, naive UTC window (old): {old_total:>10}  ({old_n} reservations)")
    print(f"  March 2024, Paris-local window (new): {new_total:>8}")
    print(f"  difference: {new_total - old_total}  <- the 1250.00 the client was missing")

    print()
    print("=" * 78)
    print("3. DECIMAL PRECISION  (total_amount is NUMERIC(10,3): sub-cent digits exist)")
    print("=" * 78)
    print("  Money values are not exactly representable in binary floating point:")
    for v in ("1080.40", "1255.60", "0.145"):
        print(f"    float({v}) * 100 = {float(v) * 100!r}")
    print()
    print("  So the old float path mis-rounds any third decimal of 5:")
    for v in ("1250.005", "1000.335", "420.125"):
        old = round(float(v) * 100) / 100                      # float() then JS-style rounding
        new = Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        flag = "  <-- one cent lost" if Decimal(repr(old)) != new else ""
        print(f"    {v}: float path -> {old:.2f}   Decimal path -> {new}{flag}")
    print()
    res = await calculate_total_revenue("prop-005", "tenant-b")
    print(f"  API total for prop-005/tenant-b: {res['total']} (exact decimal string, no float)")

    print()
    print("=" * 78)
    print("4. FULL MATRIX  (every property against every tenant)")
    print("=" * 78)
    print(f"  {'property':<10} {'tenant':<10} {'total':>12} {'count':>6}")
    for prop in ("prop-001", "prop-002", "prop-003", "prop-004", "prop-005"):
        for tenant in ("tenant-a", "tenant-b"):
            r = await calculate_total_revenue(prop, tenant)
            print(f"  {prop:<10} {tenant:<10} {r['total']:>12} {r['count']:>6}")

    await db_pool.close()


asyncio.run(main())
