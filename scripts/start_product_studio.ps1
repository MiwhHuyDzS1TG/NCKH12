param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "product_frontend"
$distRoot = Join-Path $projectRoot "product_dist"
$healthUrl = "http://127.0.0.1:8765/api/health"
$productUrl = "http://127.0.0.1:8765/"

Set-Location -LiteralPath $projectRoot
$pythonExe = (Get-Command py -ErrorAction Stop).Source
& $pythonExe -3.11 -c "import fastapi, uvicorn, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Python product dependencies are unavailable. Run: py -3.11 -m pip install -e .[product]"
}

if (-not (Test-Path -LiteralPath (Join-Path $distRoot "index.html"))) {
    $pnpmExe = (Get-Command pnpm.cmd -ErrorAction Stop).Source
    Push-Location -LiteralPath $frontendRoot
    try {
        if (-not (Test-Path -LiteralPath "node_modules")) {
            & $pnpmExe install --frozen-lockfile
            if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
        }
        & $pnpmExe run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally {
        Pop-Location
    }
}

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
        if ($health.StatusCode -ne 200) { throw "Unexpected health response." }
    }
    catch {
        throw "Port 8765 is already occupied by another or unhealthy application."
    }
}
else {
    $arguments = @(
        "-3.11", "-m", "uvicorn", "speaking_evidence.product_api:app",
        "--host", "127.0.0.1", "--port", "8765", "--no-access-log"
    )
    Start-Process -FilePath $pythonExe -ArgumentList $arguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null

    $ready = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            if ($health.StatusCode -eq 200) { $ready = $true; break }
        }
        catch { }
    }
    if (-not $ready) { throw "DUET / SPEAK did not become ready within 45 seconds." }
}

if (-not $NoBrowser) { Start-Process $productUrl }
Write-Host "DUET / SPEAK ready at $productUrl"
Write-Host "Legacy fallback: START_COMPETITION_DEMO_LEGACY.bat"
