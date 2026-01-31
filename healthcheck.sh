#!/bin/bash

# Health check script that adapts to different binding scenarios:
# 1. Unix socket (UDS)
# 2. Reverse proxy (Caddy) - health checks through localhost
# 3. Direct HTTP binding
# 4. Direct HTTPS binding

PORT=${UVICORN_PORT:-8000}
CERTFILE=${UVICORN_SSL_CERTFILE}
KEYFILE=${UVICORN_SSL_KEYFILE}
UDS=${UVICORN_UDS}
DEBUG=${DEBUG:-false}

# Function to check health via HTTP/HTTPS
check_http_health() {
    local protocol=$1
    local host=$2
    local port=$3
    local curl_flags="-sf"

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
    curl -sf --unix-socket "$socket_path" "http://localhost/health" 2>/dev/null
    return $?
}

# Main health check logic
main() {
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