# PropertyFlow Revenue Dashboard — Bug Fix Assignment

Multi-tenant property revenue dashboard fixes for The Flex / Base360 new-devs assignment.

## Where to look

| What | Link |
|------|------|
| **Full write-up (all 5 bugs, root causes, fixes, how to test)** | [`SOLUTION.md`](./SOLUTION.md) |
| **Loom video walkthrough** | [Watch on Loom](https://www.loom.com/share/0be40fba49174a6089bbc711fb22617c) |
| **Original assignment brief** | [`ASSIGNMENT.md`](./ASSIGNMENT.md) |

## Bugs fixed (summary)

1. **Database never connected** — fake mock revenue instead of real DB data  
2. **Cross-tenant cache leak** — Redis key missing `tenant_id`  
3. **March revenue mismatch** — month bounds in naive UTC, ignored property timezone  
4. **Cents / float drift** — money cast to IEEE float; now Decimal + string on the wire  
5. **Logout on refresh** — localStorage “cleanup” wiped the auth session  

Details, file paths, and verification steps are in **[`SOLUTION.md`](./SOLUTION.md)**.

## Quick start

```powershell
docker compose up --build
```

- Frontend: http://localhost:3000  
- API docs: http://localhost:8000/docs  

**Test logins**

| Client | Email | Password |
|--------|-------|----------|
| Sunset (Client A) | `sunset@propertyflow.com` | `client_a_2024` |
| Ocean (Client B) | `ocean@propertyflow.com` | `client_b_2024` |

Optional checks:

```powershell
.\repro_bugs.ps1
docker compose exec backend python /app/verify_fixes.py
```
