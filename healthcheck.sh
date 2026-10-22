#!/bin/bash

# Resolve local settings consistently when invoked from another directory.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
# Use the same dotenv parser and environment precedence as the application.
# Capture the command status before mapfile (process substitutions mask failures).
if [ -f .env ]; then
    effective_settings="$(python -c 'from config import runtime_settings, server_settings
for value in (runtime_settings.role.value, server_settings.port, server_settings.ssl_certfile or "", server_settings.ssl_keyfile or "", server_settings.uds or ""):
    print(value)')" || exit 1
    mapfile -t settings <<< "$effective_settings"
    ROLE="${settings[0]}"
    PORT="${settings[1]}"
    CERTFILE="${settings[2]}"
    KEYFILE="${settings[3]}"
    UDS="${settings[4]:-}"
else
    PORT=${UVICORN_PORT:-${PORT:-8000}}
    CERTFILE=${UVICORN_SSL_CERTFILE}
    KEYFILE=${UVICORN_SSL_KEYFILE}
    UDS=${UVICORN_UDS}
fi
ROLE="${ROLE:-all-in-one}"
ROLE="${ROLE,,}"
ROLE="${ROLE#"${ROLE%%[![:space:]]*}"}"
ROLE="${ROLE%"${ROLE##*[![:space:]]}"}"

# Function to check health via HTTP/HTTPS
check_http_health() {
    local protocol=$1
    local host=$2
    local port=$3
    local curl_flags="-sf --connect-timeout 2 --max-time 5"

    # Add --insecure for HTTPS self-signed certs
    if [ "$protocol" = "https" ]; then
        curl_flags="$curl_flags --insecure"
    fi

    curl $curl_flags "${protocol}://${host}:${port}/health" 2>/dev/null
    return $?
}

# Function to check health via Unix socket
check_uds_health() {
    local socket_path=$1

    if [ ! -S "$socket_path" ]; then
        return 1
    fi

    # Use curl with unix socket
    curl -sf --connect-timeout 2 --max-time 5 --unix-socket "$socket_path" "http://localhost/health" 2>/dev/null
    return $?
}

# Main health check logic
main() {
    # Split workers do not expose HTTP. Check their PID-1 command rather than
    # incorrectly marking a healthy worker unhealthy on every /health probe.
    if [ "${ROLE:-all-in-one}" = "node" ] || [ "${ROLE:-all-in-one}" = "scheduler" ]; then
        exec python -c 'import os, pathlib, sys
expected = (sys.argv[1] + "_worker.py").encode()
args = pathlib.Path("/proc/1/cmdline").read_bytes().split(b"\0")
sys.exit(0 if any(os.path.basename(arg) == expected for arg in args) else 1)' "$ROLE"
    fi

    # Case 1: Unix socket binding
    if [ -n "$UDS" ]; then
        if check_uds_health "$UDS"; then
            exit 0
        else
            exit 1
        fi
    fi

    # Case 2: Direct HTTP/HTTPS binding
    if [ -n "$CERTFILE" ] && [ -n "$KEYFILE" ] && [ -f "$CERTFILE" ] && [ -f "$KEYFILE" ]; then
        # SSL certificates provided - use HTTPS
        if check_http_health "https" "127.0.0.1" "$PORT"; then
            exit 0
        else
            exit 1
        fi
    else
        # No SSL certificates - use HTTP
        if check_http_health "http" "127.0.0.1" "$PORT"; then
            exit 0
        else
            exit 1
        fi
    fi
}

main
