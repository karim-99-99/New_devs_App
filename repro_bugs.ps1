# End-to-end check of the revenue dashboard fixes, driven through the public API
# with the two client accounts from ASSIGNMENT.md.
#
#   .\repro_bugs.ps1                 # against the documented port 8000
#   .\repro_bugs.ps1 -Port 8010      # if 8000 is taken on your machine
param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$api = "http://localhost:$Port"

function Login($email, $password) {
    $body = @{ email = $email; password = $password } | ConvertTo-Json
    return Invoke-RestMethod -Uri "$api/api/v1/auth/login" -Method Post -Body $body -ContentType "application/json"
}
function Summary($token, $propertyId) {
    return Invoke-RestMethod -Uri "$api/api/v1/dashboard/summary?property_id=$propertyId" -Headers @{ Authorization = "Bearer $token" } -Method Get
}

$a = Login "sunset@propertyflow.com" "client_a_2024"
$b = Login "ocean@propertyflow.com"  "client_b_2024"
Write-Host "Sunset Properties -> tenant_id=$($a.user.tenant_id)"
Write-Host "Ocean Rentals     -> tenant_id=$($b.user.tenant_id)"

# prop-001 belongs to BOTH tenants, so it is the id that leaked.
Write-Host "`n=== Repeated refreshes on the shared id prop-001 ===" -ForegroundColor Cyan
$ok = $true
for ($i = 1; $i -le 4; $i++) {
    $ra = Summary $a.access_token "prop-001"
    $rb = Summary $b.access_token "prop-001"
    Write-Host ("  refresh {0}:  Sunset={1,8} ({2} bookings)   Ocean={3,8} ({4} bookings)" -f `
        $i, $ra.total_revenue, $ra.reservations_count, $rb.total_revenue, $rb.reservations_count)
    if ($ra.total_revenue -ne "2250.00" -or $rb.total_revenue -ne "0.00") { $ok = $false }
}
if ($ok) { Write-Host "  -> stable and isolated across every refresh" -ForegroundColor Green }
else     { Write-Host "  -> UNSTABLE / LEAKING" -ForegroundColor Red }

Write-Host "`n=== Every property, as each client sees it ===" -ForegroundColor Cyan
foreach ($p in @("prop-001","prop-002","prop-003","prop-004","prop-005")) {
    $ra = Summary $a.access_token $p
    $rb = Summary $b.access_token $p
    Write-Host ("  {0}   Sunset={1,8}  Ocean={2,8}" -f $p, $ra.total_revenue, $rb.total_revenue)
}

Write-Host "`n=== Cache keys are tenant-scoped ===" -ForegroundColor Cyan
docker compose exec -T redis redis-cli --scan --pattern "revenue:*"
