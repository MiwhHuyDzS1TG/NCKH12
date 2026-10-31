param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$healthUrl = "http://127.0.0.1:8501/_stcore/health"
$teacherUrl = "http://127.0.0.1:8501/?mode=teacher"

Set-Location -LiteralPath $projectRoot
$pythonExe = (Get-Command python -ErrorAction Stop).Source
& $pythonExe -c "import streamlit" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Python is available but Streamlit cannot be imported."
}

$listener = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 3
        if ($health.StatusCode -ne 200) {
            throw "Unexpected health response."
        }
    }
    catch {
        throw "Port 8501 is already occupied by another/unhealthy application."
    }
}
else {
    $arguments = @(
        "-m", "streamlit", "run", "app.py",
        "--server.address", "127.0.0.1",
        "--server.port", "8501",
        "--server.headless", "true"
    )
    Start-Process -FilePath $pythonExe -ArgumentList $arguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            # The server is still starting.
        }
    }
    if (-not $ready) {
        throw "Teacher Rating server did not become ready within 30 seconds."
    }
}

if (-not $NoBrowser) {
    Start-Process $teacherUrl
}
Write-Host "Teacher Rating ready at $teacherUrl"
