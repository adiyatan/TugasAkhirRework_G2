$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment tidak ditemukan di $VenvPython. Silakan buat venv terlebih dahulu."
}

Write-Host "===================================================="
Write-Host " Menjalankan Backend (FastAPI) & Frontend (UI)"
Write-Host "===================================================="
Write-Host " Frontend UI  : http://127.0.0.1:3000"
Write-Host " Backend API  : http://127.0.0.1:8000"
Write-Host " Swagger Docs : http://127.0.0.1:8000/docs"
Write-Host " Tekan Ctrl+C untuk menghentikan kedua service."
Write-Host "===================================================="

$backendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $BackendDir `
    -NoNewWindow `
    -PassThru

$frontendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "http.server", "3000", "--bind", "127.0.0.1" `
    -WorkingDirectory $FrontendDir `
    -NoNewWindow `
    -PassThru

try {
    while (-not $backendProc.HasExited -and -not $frontendProc.HasExited) {
        Start-Sleep -Milliseconds 300
    }
}
finally {
    Write-Host "`nMenghentikan kedua service..."
    foreach ($proc in @($backendProc, $frontendProc)) {
        if ($proc -and -not $proc.HasExited) {
            cmd /c "taskkill /F /T /PID $($proc.Id) >nul 2>&1"
        }
    }
    Write-Host "Selesai."
}
