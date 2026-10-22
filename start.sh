#!/usr/bin/env bash
set -eu

# Work with absolute entrypoint paths as well as `./start.sh`.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Railway's account resources cannot be created by an application entrypoint.
# Configure only after verifying a real volume; retain normal behavior elsewhere.
if [ -n "${RAILWAY_ENVIRONMENT_ID:-}" ] && [ "${PASARGUARD_RAILWAY_READY:-}" != "1" ]; then
    case "${PASARGUARD_RAILWAY_AUTO_CONFIG:-true}" in
        false) ;;
        *) exec python railway_runtime.py ;;
    esac
fi

# Config also supports ROLE in .env; never source .env as shell code.
if [ -z "${ROLE+x}" ] && [ -f .env ]; then
    ROLE="$(python -c 'from config import runtime_settings; print(runtime_settings.role.value)')"
fi
ROLE="${ROLE:-all-in-one}"
ROLE="${ROLE,,}"
ROLE="${ROLE#"${ROLE%%[![:space:]]*}"}"
ROLE="${ROLE%"${ROLE##*[![:space:]]}"}"
export ROLE

case "$ROLE" in
    node)
        exec python node_worker.py
        ;;
    scheduler)
        exec python scheduler_worker.py
        ;;
    all-in-one|backend)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ${ROLE}..."
        if python -m alembic upgrade head; then
            if [ "${PASARGUARD_RAILWAY_READY:-}" = "1" ]; then
                python -m cli.railway
            fi
            exec python main.py
        else
            exit_code=$?
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Database migrations failed" >&2
            exit "$exit_code"
        fi
        ;;
    *)
        echo "ERROR: Invalid ROLE '$ROLE'; expected all-in-one, backend, node or scheduler" >&2
        exit 2
        ;;
esac
