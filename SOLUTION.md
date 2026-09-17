# Solution: Property Revenue Dashboard — Bug Investigation & Fixes

**Video walkthrough (Loom):** https://www.loom.com/share/0be40fba49174a6089bbc711fb22617c

This document describes every bug found, its root cause, the fix applied, and
how to verify each fix with the two client accounts from `ASSIGNMENT.md`.

## Summary of the reported symptoms

| Report | Reporter | Root cause |
|---|---|---|
| "Revenue numbers don't match our records for March" | Client A (Sunset Properties) | Month boundaries computed in naive UTC, ignoring the property's timezone |
| "Sometimes we see revenue that belongs to another company" | Client B (Ocean Rentals) | Redis cache key did not include the tenant, and `prop-001` exists for **both** tenants |
| "Totals are off by a few cents" | Finance team | Money cast to IEEE-754 `float` at the API boundary; no controlled rounding anywhere |

One deeper defect sat underneath all of them: **the revenue service was never
actually reading the database.** The connection pool failed on startup and a
hardcoded mock dictionary silently served fabricated figures, so every number
on the dashboard was fake while the system looked healthy.

---

## Bug 1 — Database never connected; fabricated fallback data

**Files:** `backend/app/core/database_pool.py`, `backend/app/services/reservations.py`

**Symptom:** Every property showed plausible-looking but wrong totals (e.g.
`prop-001` showed 1000.00 / 3 bookings while the seeded data contains
2250.00 / 4 for tenant-a).

**Root cause — three stacked defects:**

1. The connection string was built from settings that do not exist
   (`settings.supabase_db_user`, `supabase_db_host`, ...). Every request
   raised `'Settings' object has no attribute 'supabase_db_user'`.
2. Even with a correct URL, `create_async_engine(..., poolclass=QueuePool)`
   is rejected by SQLAlchemy: the synchronous `QueuePool` cannot be used with
   an asyncio engine.
3. `get_session` was declared `async def` while callers used
   `async with db_pool.get_session()`. A coroutine has no `__aenter__`, so
   this could never work.

All three exceptions were swallowed by a `try/except` in
`calculate_total_revenue`, which then answered from a hardcoded
`mock_data` dict — fabricating financial data and hiding the outage.

**Fix:**

- Build the URL from `settings.database_url` (already defaulting to the
  Compose Postgres, `postgresql://postgres:postgres@db:5432/propertyflow`)
  and normalise it onto the `asyncpg` driver.
- Remove `poolclass=QueuePool`; async engines supply their own
  `AsyncAdaptedQueuePool`.
- Make `get_session` a plain method returning the `AsyncSession`.
- Delete the mock fallback entirely. A database failure now surfaces as an
  error instead of inventing revenue figures.

---

## Bug 2 — Cross-tenant cache leak (Client B's privacy complaint)

**Files:** `backend/app/services/cache.py`

**Symptom:** Ocean Rentals intermittently saw Sunset Properties' numbers
after a refresh.

**Root cause:** The Redis key was `revenue:{property_id}` — no tenant. The
schema allows the same property id under different tenants (the `properties`
primary key is composite `(id, tenant_id)`), and the seed data deliberately
gives `prop-001` to both: "Beach House Alpha" (tenant-a) and "Mountain Lodge
Beta" (tenant-b). Whichever tenant requested `prop-001` first populated the
cache; the other tenant was then served those figures until the 300-second
TTL expired. The TTL expiry is exactly why the leak appeared "sometimes".

**Fix:** The key is now `revenue:{tenant_id}:{property_id}`, so each tenant
has its own cache entry.

Related hardening in the same area:

- `backend/app/api/v1/dashboard.py` no longer falls back to
  `"default_tenant"` when a user has no tenant — it fails closed with 403.
- `frontend/src/components/RevenueSummary.tsx` and
  `frontend/src/lib/secureApi.ts` no longer send a client-chosen
  `X-Simulated-Tenant` header (it was hardcoded to `'candidate'`). The tenant
  comes only from the authenticated JWT; a client-supplied tenant identifier
  would be trivially forgeable.

---

## Bug 3 — March revenue mismatch (Client A's complaint)

**Files:** `backend/app/services/reservations.py`

**Symptom:** Sunset Properties' own records show more March revenue than the
dashboard.

**Root cause:** `calculate_monthly_revenue` built month boundaries as naive
datetimes (`datetime(year, month, 1)`) and compared them against
`TIMESTAMP WITH TIME ZONE` columns, while the `properties.timezone` column
("Europe/Paris", "America/New_York") was never read. The seeded reservation
`res-tz-1` checks in at `2024-02-29 23:30:00+00`, which is
`2024-03-01 00:30 +01:00` in Paris — March for the client, February for the
buggy query. That reservation is worth exactly the missing **1250.00**.

**Fix:** Month boundaries are now built as **local midnight in the
property's own timezone** and converted to UTC before querying:

- naive UTC window (old): March 2024 = 1000.000 (3 reservations)
- Paris-local window (new): March 2024 = **2250.00** (4 reservations)

The property-timezone lookup is itself scoped by `tenant_id`, and the
function now takes `tenant_id` as a parameter so the monthly query is
tenant-safe too.

---

## Bug 4 — Cents drift (finance team's complaint)

**Files:** `backend/app/api/v1/dashboard.py`,
`backend/app/services/reservations.py`,
`frontend/src/components/RevenueSummary.tsx`

**Symptom:** Totals occasionally off by a cent.

**Root cause:** Amounts are stored as `NUMERIC(10, 3)` (third decimals
genuinely exist in the seed: 333.333, 333.334, ...). The API did
`float(revenue_data['total'])`, and the frontend rounded with
`Math.round(x * 100) / 100`. Money values are not exactly representable in
binary floating point (`1255.60 * 100 === 125559.99999999999`), and
float-based rounding of a third decimal of 5 loses a cent
(`420.125 -> 420.12` instead of `420.13`).

**Fix:**

- Sums stay in `Decimal` end-to-end and are quantised exactly once with
  `ROUND_HALF_UP` to 2 decimal places.
- The API now returns the total as an **exact decimal string**
  (e.g. `"2250.00"`) — money never crosses the wire as a float.
- The frontend formats that string directly instead of round-tripping it
  through a JS number.

---

## Bug 5 — Logged out on every page refresh

**Files:** `frontend/src/utils/StorageHealthChecker.ts`,
`frontend/src/utils/localStorageManager.ts`

**Symptom:** After logging in, refreshing the page (F5) eventually dumps you
back on the login screen — the session does not survive reloads.

**Root cause:** a two-step self-destruct between two storage utilities that
run on every page load:

1. `localStorageManager` writes its version marker as a **plain string**
   (`app_storage_version = "2.0.0"`).
2. `StorageHealthChecker` then scans localStorage and treats every value
   that fails `JSON.parse()` as "corrupted" — `"2.0.0"` is not valid JSON,
   so the version marker is deleted ("Removed 1 corrupted items" in the
   console).
3. On the **next** refresh, `localStorageManager` finds no version marker,
   assumes first-run/corruption, and runs a "migration" that clears all of
   localStorage. Its preserve list only kept keys containing `supabase` /
   `sb-` (leftover from the original Supabase auth), so the actual session
   key `base360-auth-token` was wiped.
4. That page still renders from the in-memory copy of the session, but the
   refresh after that has nothing to restore — you land on `/login`.

**Fix:**

- `StorageHealthChecker.checkForCorruption` no longer flags plain-string
  values as corrupted (they are legitimate: the version marker, i18n
  language, etc.). Only entries in the app's own `{data, timestamp}` format
  are validated.
- Both storage-wipe paths in `localStorageManager` (`clearAllExceptEssentials`
  and `migrateV1ToV2`) now preserve `base360-auth-token`, so even a genuine
  migration can never log the user out.

**Verified:** headless-browser test logs in as each client and refreshes
5 times — the session stays in localStorage, the URL stays on `/dashboard`,
and the revenue figures remain tenant-correct on every reload.

---

## How to test

### 1. Start the stack

```bash
docker-compose up --build
# Frontend:  http://localhost:3000
# API docs:  http://localhost:8000/docs
```

If a previous run is up, clear the cache first so you start clean:

```bash
docker compose exec redis redis-cli FLUSHALL
```

### 2. Automated end-to-end check (Windows PowerShell)

```powershell
.\repro_bugs.ps1          # add -Port 8010 if 8000 is taken on your machine
```

Expected output:

- `Sunset Properties -> tenant_id=tenant-a`, `Ocean Rentals -> tenant_id=tenant-b`
- Four alternating refreshes on the shared `prop-001`:
  Sunset always `2250.00` (4 bookings), Ocean always `0.00` (0 bookings —
  Mountain Lodge Beta genuinely has no reservations in the seed)
- Per-property matrix: each tenant sees only its own properties' revenue
  (`prop-002/003` only for Sunset, `prop-004/005` only for Ocean)
- Redis keys listed as `revenue:tenant-a:prop-001`,
  `revenue:tenant-b:prop-001`, ... (tenant-scoped)

### 3. Backend verification harness (any OS)

```bash
docker compose exec backend python /app/verify_fixes.py
```

Prints four sections with the proof for each bug:

1. **Tenant isolation** — `prop-001` returns 2250.00/4 for tenant-a and
   0.00/0 for tenant-b, plus the full property×tenant matrix.
2. **Timezone boundary** — old naive-UTC March window (1000.000) vs new
   Paris-local window (2250.00); difference exactly 1250.00.
3. **Decimal precision** — float representation errors and the concrete
   one-cent loss on `420.125`, vs the exact Decimal path.
4. **Full matrix** — every property against every tenant.

### 4. Manual browser test (what the clients would do)

1. Open `http://localhost:3000` and log in as
   `sunset@propertyflow.com` / `client_a_2024`.
2. On the dashboard, select **Beach House Alpha (prop-001)** —
   total revenue shows **USD 2,250.00**, 4 bookings.
3. Log out, log in as `ocean@propertyflow.com` / `client_b_2024`.
4. Select **prop-001 (Mountain Lodge Beta for this tenant)** — shows
   **USD 0.00**, 0 bookings, *not* Sunset's 2,250.00. Refresh repeatedly:
   the numbers never flip to the other company's.
5. Check Lakeside Cottage (1,776.50) and Urban Loft Modern (3,256.00) for
   Ocean; City Apartment Downtown (4,975.50) and Country Villa Estate
   (6,100.50) for Sunset.
6. While logged in, press **F5 several times in a row** — you stay logged
   in on the dashboard every time (Bug 5). Before the fix, the second or
   third refresh landed on the login page.

### Expected totals (from `database/seed.sql`)

| Property | Sunset (tenant-a) | Ocean (tenant-b) |
|---|---|---|
| prop-001 | 2250.00 (4) | 0.00 (0) |
| prop-002 | 4975.50 (4) | 0.00 (0) |
| prop-003 | 6100.50 (2) | 0.00 (0) |
| prop-004 | 0.00 (0) | 1776.50 (4) |
| prop-005 | 0.00 (0) | 3256.00 (3) |

## Files changed

| File | Change |
|---|---|
| `backend/app/core/database_pool.py` | Correct connection URL from `settings.database_url` + asyncpg; removed invalid `QueuePool`; `get_session` returns a session, not a coroutine |
| `backend/app/services/reservations.py` | Real DB queries (no mock fallback); timezone-aware month boundaries; tenant-scoped everywhere; exact `Decimal` arithmetic with a single `ROUND_HALF_UP` quantisation |
| `backend/app/services/cache.py` | Tenant-scoped cache key `revenue:{tenant_id}:{property_id}` |
| `backend/app/api/v1/dashboard.py` | Removed `float()` cast (exact decimal string on the wire); fail closed (403) when the user has no tenant; correct `AuthenticatedUser` typing |
| `frontend/src/components/RevenueSummary.tsx` | Removed hardcoded `'candidate'` simulated tenant; renders the exact decimal string; fixed precision-mismatch indicator |
| `frontend/src/lib/secureApi.ts` | Removed the `X-Simulated-Tenant` header option |
| `frontend/src/utils/StorageHealthChecker.ts` | Plain-string localStorage values are no longer deleted as "corrupted" (this deleted the version marker and triggered the session wipe) |
| `frontend/src/utils/localStorageManager.ts` | Storage migration/cleanup now preserves the `base360-auth-token` session key |
| `backend/verify_fixes.py` *(new)* | In-container verification harness for all fixes |
| `repro_bugs.ps1` *(new)* | End-to-end API test using both client accounts |
