#!/usr/bin/env bash
# Host dev runner only. The Docker image uses its own exec-form uvicorn CMD.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DOTENV="$ROOT_DIR/.env"

DOCKER_MODE=0

usage() {
    cat <<'USAGE'
Usage: ./run.sh [options]

Options:
  --docker      Jalankan via Docker Compose (butuh .env berisi SECRET_KEY)
  --no-reload   Matikan auto-reload uvicorn
  -h, --help    Tampilkan bantuan

Setting opsional dari environment atau .env:
  HOST    (default 127.0.0.1)
  PORT    (default 8000)
  RELOAD  (1/0, default 1)
  PYTHON  (path interpreter venv, default backend/.venv/bin/python)
USAGE
}

dotenv_value() {
    local key="$1"
    [[ -f "$DOTENV" ]] || return 0
    local line
    line=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$DOTENV" | tail -n 1) || return 0
    [[ -n "$line" ]] || return 0
    local value="${line#*=}"
    value="${value%$'\r'}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" == \"*\" && "$value" == *\" ]] || [[ "$value" == \'*\' && "$value" == *\' ]]; then
        value="${value:1:${#value}-2}"
    fi
    printf '%s' "$value"
}

pick() {
    # pick <env value> <dotenv key> <default>
    local env_val="${1:-}"
    local key="$2"
    local default="$3"
    if [[ -n "$env_val" ]]; then
        printf '%s' "$env_val"
        return
    fi
    local file_val
    file_val="$(dotenv_value "$key")"
    if [[ -n "$file_val" ]]; then
        printf '%s' "$file_val"
    else
        printf '%s' "$default"
    fi
}

for arg in "$@"; do
    case "$arg" in
        --docker) DOCKER_MODE=1 ;;
        --no-reload) RELOAD="0" ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Argumen tidak dikenal: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

HOST="$(pick "${HOST:-}" HOST "127.0.0.1")"
PORT="$(pick "${PORT:-}" PORT "8000")"
RELOAD="$(pick "${RELOAD:-}" RELOAD "1")"
PYTHON="$(pick "${PYTHON:-}" PYTHON "$BACKEND_DIR/.venv/bin/python")"

if [[ "$DOCKER_MODE" == "1" ]]; then
    if [[ ! -f "$DOTENV" ]]; then
        echo "Error: .env tidak ditemukan di $DOTENV. Salin .env.example menjadi .env dan isi SECRET_KEY." >&2
        exit 1
    fi
    if ! command -v docker >/dev/null 2>&1; then
        echo "Error: docker tidak ditemukan di PATH." >&2
        exit 1
    fi
    echo "Menjalankan mode Docker (docker compose up --build)..."
    cd "$ROOT_DIR"
    exec docker compose up --build
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "Error: Python venv tidak ditemukan di $PYTHON. Buat venv atau set PYTHON=... ." >&2
    exit 1
fi

DISPLAY_HOST="$HOST"
[[ "$DISPLAY_HOST" == "0.0.0.0" ]] && DISPLAY_HOST="127.0.0.1"

cat <<EOF
====================================================
 Menjalankan Backend (FastAPI) + UI (satu origin)
====================================================
 Frontend UI  : http://${DISPLAY_HOST}:${PORT}
 Backend API  : http://${DISPLAY_HOST}:${PORT}
 Swagger Docs : http://${DISPLAY_HOST}:${PORT}/docs
 Host bind    : ${HOST}:${PORT} (reload=${RELOAD})
 Tekan Ctrl+C untuk menghentikan service.
====================================================
EOF

UVICORN_ARGS=(-m uvicorn app.main:app --host "$HOST" --port "$PORT")
if [[ "$RELOAD" == "1" ]]; then
    UVICORN_ARGS+=(--reload --reload-dir app)
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
    if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
        kill -KILL -- "-$backend_pid" 2>/dev/null || true
    fi
    wait 2>/dev/null || true
    echo "Selesai."
}

trap cleanup INT TERM EXIT

if command -v setsid >/dev/null 2>&1; then
    ( cd "$BACKEND_DIR" && exec setsid "$PYTHON" "${UVICORN_ARGS[@]}" ) &
else
    ( cd "$BACKEND_DIR" && exec "$PYTHON" "${UVICORN_ARGS[@]}" ) &
fi
backend_pid=$!

while kill -0 "$backend_pid" 2>/dev/null; do
    sleep 0.3
done
