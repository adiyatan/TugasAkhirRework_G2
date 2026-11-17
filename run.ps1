# Host dev runner only. The Docker image uses its own exec-form uvicorn CMD.
param(
    [switch]$Docker,
    [switch]$NoReload,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$DotEnv = Join-Path $RootDir ".env"

function Show-Usage {
    Write-Host @"
Usage: .\run.ps1 [-Docker] [-NoReload] [-Help]

  -Docker    Jalankan via Docker Compose (butuh .env berisi SECRET_KEY)
  -NoReload  Matikan auto-reload uvicorn
  -Help      Tampilkan bantuan

Setting opsional dari environment atau .env:
  HOST    (default 127.0.0.1)
  PORT    (default 8000)
  RELOAD  (1/0, default 1)
  PYTHON  (path interpreter venv, default backend\.venv\Scripts\python.exe)
"@
}

function Get-DotEnvValue {
    param([string]$Key)
    if (-not (Test-Path $DotEnv)) { return $null }
    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*="
    $line = Get-Content $DotEnv | Where-Object { $_ -match $pattern } | Select-Object -Last 1
    if (-not $line) { return $null }
    $value = (($line -split "=", 2)[1]).Trim()
    if ($value.Length -ge 2) {
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    return $value
}

function Resolve-Setting {
    param([string]$EnvValue, [string]$Key, [string]$Default)
    if ($EnvValue) { return $EnvValue }
    $fileValue = Get-DotEnvValue $Key
    if ($fileValue) { return $fileValue }
    return $Default
}

if ($Help) {
    Show-Usage
    exit 0
}

if ($Docker) {
    if (-not (Test-Path $DotEnv)) {
        Write-Error "File .env tidak ditemukan di $DotEnv. Salin .env.example menjadi .env dan isi SECRET_KEY."
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "docker tidak ditemukan di PATH."
    }
    Write-Host "Menjalankan mode Docker (docker compose up --build)..."
    Push-Location $RootDir
    try {
        docker compose up --build
    }
    finally {
        Pop-Location
    }
    exit $LASTEXITCODE
}

$HostAddr = Resolve-Setting $env:HOST "HOST" "127.0.0.1"
$Port = Resolve-Setting $env:PORT "PORT" "8000"
$Reload = Resolve-Setting $env:RELOAD "RELOAD" "1"
if ($NoReload) { $Reload = "0" }
$VenvPython = Resolve-Setting $env:PYTHON "PYTHON" (Join-Path $BackendDir ".venv\Scripts\python.exe")

if (-not (Test-Path $VenvPython)) {
    Write-Error "Python venv tidak ditemukan di $VenvPython. Buat venv atau set PYTHON=... ."
}

$displayHost = if ($HostAddr -eq "0.0.0.0") { "127.0.0.1" } else { $HostAddr }

Write-Host "===================================================="
Write-Host " Menjalankan Backend (FastAPI) + UI (satu origin)"
Write-Host "===================================================="
Write-Host " Frontend UI  : http://${displayHost}:${Port}"
Write-Host " Backend API  : http://${displayHost}:${Port}"
Write-Host " Swagger Docs : http://${displayHost}:${Port}/docs"
Write-Host " Host bind    : ${HostAddr}:${Port} (reload=${Reload})"
Write-Host " Tekan Ctrl+C untuk menghentikan service."
Write-Host "===================================================="

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddr, "--port", $Port)
if ($Reload -eq "1") {
    $uvicornArgs += @("--reload", "--reload-dir", "app")
}

$backendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList $uvicornArgs `
    -WorkingDirectory $BackendDir `
    -NoNewWindow `
    -PassThru

try {
    while (-not $backendProc.HasExited) {
        Start-Sleep -Milliseconds 300
    }
}
finally {
    Write-Host "`nMenghentikan backend..."
    if ($backendProc -and -not $backendProc.HasExited) {
        if ($IsWindows -or $env:OS -eq "Windows_NT") {
            cmd /c "taskkill /F /T /PID $($backendProc.Id) >nul 2>&1"
        }
        else {
            Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Selesai."
}
