#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Error: Virtual environment tidak ditemukan di $VENV_PYTHON. Silakan buat venv terlebih dahulu." >&2
    exit 1
fi

backend_pid=""

terminate() {
    local pid="${1:-}"
    [[ -n "$pid" ]] || return 0
    kill -0 "$pid" 2>/dev/null || return 0

    # Kill the whole process group (uvicorn --reload spawns child workers).
    kill -TERM -- "-$pid" 2>/dev/null || {
        pkill -TERM -P "$pid" 2>/dev/null || true
        kill -TERM "$pid" 2>/dev/null || true
    }
}

cleanup() {
    trap - INT TERM EXIT
    echo
    echo "Menghentikan backend..."
    terminate "$backend_pid"
    sleep 1
    if [[ -n "$backend_pid" ]]; then
        kill -KILL -- "-$backend_pid" 2>/dev/null || true
    fi
    wait 2>/dev/null || true
    echo "Selesai."
}

trap cleanup INT TERM EXIT

cat <<'EOF'
====================================================
 Menjalankan Backend (FastAPI) + UI (satu origin)
====================================================
 Frontend UI  : http://127.0.0.1:8000
 Backend API  : http://127.0.0.1:8000
 Swagger Docs : http://127.0.0.1:8000/docs
 Tekan Ctrl+C untuk menghentikan service.
====================================================
EOF

if command -v setsid >/dev/null 2>&1; then
    ( cd "$BACKEND_DIR" && exec setsid "$VENV_PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 ) &
else
    ( cd "$BACKEND_DIR" && exec "$VENV_PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 ) &
fi
backend_pid=$!

while kill -0 "$backend_pid" 2>/dev/null; do
    sleep 0.3
done
