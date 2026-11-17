$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment tidak ditemukan di $VenvPython. Silakan buat venv terlebih dahulu."
}

Write-Host "===================================================="
Write-Host " Menjalankan Backend (FastAPI) + UI (satu origin)"
Write-Host "===================================================="
Write-Host " Frontend UI  : http://127.0.0.1:8000"
Write-Host " Backend API  : http://127.0.0.1:8000"
Write-Host " Swagger Docs : http://127.0.0.1:8000/docs"
Write-Host " Tekan Ctrl+C untuk menghentikan service."
Write-Host "===================================================="

$backendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000" `
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
        cmd /c "taskkill /F /T /PID $($backendProc.Id) >nul 2>&1"
    }
    Write-Host "Selesai."
}
