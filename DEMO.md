# Demo & Loom checklist (Windows PowerShell)

Use this while recording. Target length: **5–10 minutes**.

**Loom URL for SOLUTION.md:** paste your new link over `REPLACE_WITH_NEW_LOOM_URL` after upload.

---

## 0. Before you hit Record

```powershell
cd "d:\ALX Front-End\code\assi\the flex\New_devs_App_submit"
docker compose down
docker compose up --build
```

Wait until both services are healthy, then open:

| What | URL |
|---|---|
| Frontend dashboard | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |

Optional clean Redis cache (recommended once before the privacy demo):

```powershell
docker compose exec redis redis-cli FLUSHALL
```

### Credentials (say them out loud once, then type on camera)

| Client | Email | Password |
|---|---|---|
| Client A — Sunset Properties | `sunset@propertyflow.com` | `client_a_2024` |
| Client B — Ocean Rentals | `ocean@propertyflow.com` | `client_b_2024` |

### Expected totals (seed data)

| Property | Sunset (tenant-a) | Ocean (tenant-b) |
|---|---|---|
| prop-001 | **2250.00** (4) | **0.00** (0) |
| prop-002 | 4975.50 (4) | 0.00 (0) |
| prop-003 | 6100.50 (2) | 0.00 (0) |
| prop-004 | 0.00 (0) | 1776.50 (4) |
| prop-005 | 0.00 (0) | 3256.00 (3) |

---

## 1. Timed Loom outline (~8 min)

| Time | What to do / say |
|---|---|
| **0:00–0:40** | Intro: assignment is a multi-tenant revenue dashboard; found 5 bugs (DB mock, tenant cache leak, timezone March revenue, cents/float, session wipe on refresh). Stack is `docker compose up --build` → :3000 and :8000/docs. |
| **0:40–1:40** | **Bug 1 (DB never connected):** Root cause — bad settings attrs + invalid async pool + broken session helper → exceptions swallowed → hardcoded `mock_data`. Fix — real `database_url` / asyncpg, no QueuePool, no mock. Show Swagger or dashboard loading real numbers (not 1000/3). |
| **1:40–3:10** | **Bug 3 (March / timezone) — Client A:** Log in as Sunset. Select **Beach House Alpha (prop-001)**. Point to **USD 2,250.00 / 4 bookings**. Say: old code used naive UTC month bounds so `res-tz-1` (Paris March 1) was counted as February; missing **1250.00**. Fixed with property-timezone local midnight → UTC. |
| **3:10–5:00** | **Bug 2 (cross-tenant privacy) — Client A vs B:** Still on Sunset prop-001 = 2250. Log out → log in as Ocean → select **prop-001** → **USD 0.00 / 0**. Hit **Refresh several times** — numbers never flip to Sunset’s. Root cause: Redis key was `revenue:{property_id}` with shared id; now `revenue:{tenant_id}:{property_id}`. |
| **5:00–6:00** | **Bug 4 (cents / precision):** Briefly: amounts were `float()` + JS `Math.round`; seed has third decimals. Fix keeps `Decimal` + returns exact string (e.g. `"2250.00"`). Optionally show total as string in Network tab on `/dashboard/summary`. |
| **6:00–7:00** | **Bug 5 (logout on refresh):** While logged in, press **F5** several times — stay on `/dashboard`. Root cause: plain-string version marker treated as “corrupt” → wipe cleared `base360-auth-token`. |
| **7:00–8:00** | Optional scripts (terminal on camera) + wrap-up: list fixes, point to SOLUTION.md, paste Loom URL later. |

---

## 2. On-camera demo order (browser)

### A. Start + health

1. Show terminal: `docker compose up --build` already running.
2. Open http://localhost:3000 and http://localhost:8000/docs briefly.

### B. Client A — March revenue accuracy (timezone)

1. Login: `sunset@propertyflow.com` / `client_a_2024`
2. Select **Beach House Alpha (prop-001)**
3. Confirm **USD 2,250.00**, **4 bookings**
4. Say in one sentence: *“Naive UTC month window missed the Paris-local March reservation worth 1250; timezone-aware bounds fix it.”*

### C. Cross-tenant privacy (refresh / cache isolation)

1. Note Sunset prop-001 = 2250
2. Log out → login: `ocean@propertyflow.com` / `client_b_2024`
3. Select **prop-001** (Mountain Lodge Beta) → **USD 0.00**, **0 bookings**
4. Refresh 3–4 times — still 0.00, never 2250
5. Optionally show Ocean props: Lakeside Cottage **1776.50**, Urban Loft **3256.00**
6. Say: *“Cache key now includes tenant_id so shared property ids cannot leak.”*

### D. Session survives refresh

1. Stay logged in as either client
2. Press F5 several times — remain on dashboard with same numbers

### E. Cents / float (quick)

1. Open DevTools → Network → call summary API (or show after login)
2. Point out `total_revenue` is a **string** like `"2250.00"`, not a float
3. Say: *“Decimal end-to-end with half-up quantize; no IEEE float on the wire.”*

---

## 3. Optional scripts (PowerShell) — run off-camera or show briefly

### End-to-end API check (both clients)

```powershell
cd "d:\ALX Front-End\code\assi\the flex\New_devs_App_submit"
.\repro_bugs.ps1
# if port 8000 is busy:
.\repro_bugs.ps1 -Port 8010
```

Expect: Sunset `tenant-a`, Ocean `tenant-b`; prop-001 always Sunset `2250.00` / Ocean `0.00` across refreshes; Redis keys like `revenue:tenant-a:prop-001`.

### In-container verification harness

```powershell
cd "d:\ALX Front-End\code\assi\the flex\New_devs_App_submit"
docker compose exec backend python /app/verify_fixes.py
```

Expect sections: tenant isolation, timezone boundary (1000.000 vs 2250.00, diff 1250), decimal precision, full matrix.

---

## 4. One-liners for root causes (say on camera)

| Bug | Say this |
|---|---|
| DB / mock data | Connection/pool/session bugs were swallowed; mock dict faked all revenue. |
| Tenant leak | Redis key omitted `tenant_id`; `prop-001` exists for both tenants. |
| March mismatch | Month bounds in naive UTC ignored property timezone (Paris). |
| Cents drift | `float` + JS rounding; money needs Decimal + exact string. |
| Logout on refresh | Plain-string localStorage marked corrupt → wipe deleted auth token. |

---

## 5. After recording

1. Upload Loom → copy share URL  
2. Replace `REPLACE_WITH_NEW_LOOM_URL` in `SOLUTION.md` (and this file if you added it)  
3. Commit + push to the **new** standalone repo (not the old fork)  
4. Submit that repo URL + Loom URL in the form  
