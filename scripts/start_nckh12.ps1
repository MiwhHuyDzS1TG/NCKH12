param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $projectRoot "product_dist"
$healthUrl = "http://127.0.0.1:8765/api/health"
$productUrl = "http://127.0.0.1:8765/"
$expectedRelease = "COMPETITION_FINAL_RELEASE"

$host.UI.RawUI.WindowTitle = "NCKH12 Speaking Coach - Backend"
Set-Location -LiteralPath $projectRoot

function Write-Check([string]$Message) {
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " NCKH12 SPEAKING COACH" -ForegroundColor White
Write-Host " Competition Final Release" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Product version: $expectedRelease"
Write-Host "Frontend: React production build"
Write-Host "Backend: Python (local only)"
Write-Host "Address: $productUrl"
Write-Host ""
Write-Host "Checking application..."

$pythonExe = (Get-Command py -ErrorAction Stop).Source
& $pythonExe -3.11 -c "import fastapi, uvicorn, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Required Python product modules are unavailable."
}
Write-Check "Python runtime"

$indexPath = Join-Path $distRoot "index.html"
if (-not (Test-Path -LiteralPath $indexPath)) {
    throw "React production build is missing. Restore the verified product_dist folder."
}
if (-not (Test-Path -LiteralPath (Join-Path $distRoot "assets"))) {
    throw "React production assets are missing. Restore the verified product_dist folder."
}
Write-Check "Frontend build"

$criticalFiles = @(
    "competition_freeze_v1.json",
    "p25_frozen_mini_validation_plan_v1.json",
    "competition_target_profile_v2.json"
)
foreach ($relative in $criticalFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relative))) {
        throw "Critical frozen configuration is missing: $relative"
    }
}
Write-Check "Frozen scorer configuration"

& $pythonExe -3.11 -c "from speaking_evidence.media_library import MediaLibrary; m=MediaLibrary(); m.items_root.mkdir(parents=True, exist_ok=True)" 2>$null
if ($LASTEXITCODE -ne 0) { throw "The private local media library is unavailable." }
Write-Check "Media library"

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    try {
        $existing = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($existing.product_version -eq $expectedRelease) {
            Write-Host ""
            Write-Host "NCKH12 is already running in another terminal." -ForegroundColor Yellow
            if (-not $NoBrowser) { Start-Process $productUrl }
            Write-Host "Use that terminal to view activity or press Ctrl+C to stop it."
            exit 0
        }
        throw "version mismatch"
    }
    catch {
        throw "Port 8765 is already in use by another application or an older NCKH12 server. Close it safely and try again."
    }
}

$arguments = @(
    "-3.11", "-m", "uvicorn", "speaking_evidence.product_api:app",
    "--host", "127.0.0.1", "--port", "8765", "--no-access-log", "--log-level", "warning"
)
$server = Start-Process -FilePath $pythonExe -ArgumentList $arguments `
    -WorkingDirectory $projectRoot -NoNewWindow -PassThru

try {
    $health = $null
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        if ($server.HasExited) {
            throw "The backend stopped during startup (exit code $($server.ExitCode))."
        }
        Start-Sleep -Milliseconds 500
        try {
            $candidate = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
            if ($candidate.status -eq "ok" -and
                $candidate.product_version -eq $expectedRelease -and
                $candidate.frontend -eq "ready" -and
                $candidate.scoring_backend -eq "ready") {
                $health = $candidate
                break
            }
        }
        catch { }
    }
    if (-not $health) { throw "NCKH12 did not become healthy within 45 seconds." }

    Write-Check "Backend server"
    Write-Host ""
    Write-Host "Frontend: $productUrl"
    Write-Host "Backend: Running"
    Write-Host "Scorer: Frozen competition scorer"
    Write-Host "ChatGPT: $($health.chatgpt_connection)"
    Write-Host "Media library: Ready"
    Write-Host ""
    if (-not $NoBrowser) {
        Write-Host "Opening browser..."
        Start-Process $productUrl
    }
    Write-Host "Press Ctrl+C to stop NCKH12." -ForegroundColor Yellow
    Write-Host "==================================================" -ForegroundColor Cyan

    while (-not $server.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($server.ExitCode -ne 0) {
        throw "The backend stopped unexpectedly (exit code $($server.ExitCode))."
    }
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
        $server.WaitForExit(5000)
    }
}
