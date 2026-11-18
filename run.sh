#!/usr/bin/env bash
# Host dev runner only. The Docker image uses its own exec-form app CMD.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DOTENV=""
ENV_FILE=""

DOCKER_MODE=0

usage() {
    cat <<'USAGE'
Usage: ./run.sh [options]

Options:
  --docker           Jalankan via Docker Compose
  --no-reload        Matikan auto-reload uvicorn
  --env-file PATH    Baca konfigurasi dari file .env pada PATH
  -h, --help         Tampilkan bantuan

Tanpa --env-file, tidak ada file .env yang dibaca.
Setting opsional dari environment atau --env-file:
  HOST    (default 127.0.0.1)
  PORT    (default 8000)
  RELOAD  (1/0, default 1)
  PYTHON  (path interpreter venv, default backend/.venv/bin/python)
USAGE
}

dotenv_value() {
    local key="$1"
    [[ -n "$DOTENV" && -f "$DOTENV" ]] || return 0
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

resolve_env_file() {
    local raw="$1"
    if [[ ! -f "$raw" ]]; then
        echo "Error: file .env tidak ditemukan: $raw" >&2
        exit 1
    fi
    local dir
    dir="$(cd "$(dirname "$raw")" && pwd)"
    printf '%s/%s' "$dir" "$(basename "$raw")"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker) DOCKER_MODE=1; shift ;;
        --no-reload) RELOAD="0"; shift ;;
        --env-file)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                echo "Error: --env-file membutuhkan path file." >&2
                usage >&2
                exit 2
            fi
            ENV_FILE="$2"
            shift 2
            ;;
        --env-file=*)
            ENV_FILE="${1#*=}"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Argumen tidak dikenal: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -n "$ENV_FILE" ]]; then
    ENV_FILE="$(resolve_env_file "$ENV_FILE")"
    DOTENV="$ENV_FILE"
fi

HOST="$(pick "${HOST:-}" HOST "127.0.0.1")"
PORT="$(pick "${PORT:-}" PORT "8000")"
RELOAD="$(pick "${RELOAD:-}" RELOAD "1")"
PYTHON="$(pick "${PYTHON:-}" PYTHON "$BACKEND_DIR/.venv/bin/python")"

if [[ "$DOCKER_MODE" == "1" ]]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "Error: docker tidak ditemukan di PATH." >&2
        exit 1
    fi
    echo "Menjalankan mode Docker (docker compose up --build)..."
    cd "$ROOT_DIR"
    if [[ -n "$ENV_FILE" ]]; then
        APP_ENV_FILE="$ENV_FILE" exec docker compose --env-file "$ENV_FILE" up --build
    fi
    exec docker compose --env-file /dev/null up --build
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

APP_ARGS=(-m app --host "$HOST" --port "$PORT")
if [[ "$RELOAD" == "1" ]]; then
    APP_ARGS+=(--reload --reload-dir app)
fi
if [[ -n "$ENV_FILE" ]]; then
    APP_ARGS+=(--env-file "$ENV_FILE")
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
    ( cd "$BACKEND_DIR" && exec setsid "$PYTHON" "${APP_ARGS[@]}" ) &
else
    ( cd "$BACKEND_DIR" && exec "$PYTHON" "${APP_ARGS[@]}" ) &
fi
backend_pid=$!

while kill -0 "$backend_pid" 2>/dev/null; do
    sleep 0.3
done
